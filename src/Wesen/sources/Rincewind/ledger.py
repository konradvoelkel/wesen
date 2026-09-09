"""The Clacks: what one Rincewind knows, and how it travels.

Every wesen of this source keeps its own `Ledger`. Nothing in it is
shared through class attributes on purpose: a fact only reaches another
wesen if somebody paid a `Broadcast` (1 time, 16 cells) or a `Talk`
(1 time, 24 cells) to send it. So the colony's picture of the world is
built by gossip, and a Rincewind that walks out of range of everybody
slowly goes blind - which is exactly what makes the network worth
running.

Four registers, all keyed so that a merge is a per-key comparison of
timestamps (last writer wins), which is all an unreliable, unordered,
partition-prone channel can support:

cells    (x, y) -> [energy, seen, bit, holder, held]
         what a food cell held when it was last seen, when it was last
         bitten by one of us, and who has reserved it for the next few
         turns. The reservation is what keeps two colleagues from
         walking to the same cell.
peers    uid -> [pos, energy, home, turn, role]
         the colony roll: who is where, how fat, which district they
         keep and what they are doing. Districts are drawn from this
         (see plan.districtRank), and the colony census follows it.
threats  tile -> [source, energy, turn, x, y]
         where somebody dangerous was seen. An alarm travels further
         than the enemy walks, so a warning usually arrives first.
tiles    tile -> turn it was last looked at, so the colony explores
         each tile once instead of twenty times.

The wire format is a plain dict of tuples (see `digest`), built fresh
for every message: a receiver never gets a reference into the sender's
live state, so this is communication and not telepathy.
"""

SIGIL = "clacks/2"

# How many turns a record survives without being refreshed. These are
# defaults; a source hands the Ledger the numbers this game's rules
# imply (a cell report is worthless once the cell could have died of
# old age, a reservation lasts as long as the walk to the cell).
CELL_TTL = 900
PEER_TTL = 240
THREAT_TTL = 90
HOLD_TTL = 14

# how much one message carries: a broadcast costs the same whatever is
# in it, but merging costs the receiver time, and stale news is noise
CELLS_PER_MESSAGE = 20
ALARMS_PER_MESSAGE = 8
TILES_PER_MESSAGE = 8
ROLL_PER_MESSAGE = 10
NEWS_WINDOW = 25  # turns: older alarms and sweeps are not worth saying

MAX_CELLS = 320  # ledger caps, so the merge stays cheap
SOFT_CELLS = 280  # above this, a bare sighting is not worth a record
MAX_PEERS = 96
MAX_THREATS = 48
MAX_TILES = 260


def _key(pos):
    return (int(pos[0]), int(pos[1]))


class Ledger:
    """the knowledge of a single wesen (see the module docstring)"""

    def __init__(
        self,
        cellTTL=CELL_TTL,
        peerTTL=PEER_TTL,
        threatTTL=THREAT_TTL,
        holdTTL=HOLD_TTL,
    ):
        self.cellTTL = cellTTL
        self.peerTTL = peerTTL
        self.threatTTL = threatTTL
        self.holdTTL = holdTTL
        self.cells = {}
        self.peers = {}
        self.threats = {}
        self.tiles = {}
        # keys changed since the last message went out
        self.fresh = set()

    # --- writing what we see ourselves ---------------------------------

    def sawCell(self, pos, energy, turn):
        """a food cell seen. `energy` None means it was seen from afar
        (a `look`), which tells us the cell exists but nothing about
        what it holds: an existing reading is then left alone, together
        with the turn it was taken, since that is what the regrowth
        estimate is measured from."""
        key = _key(pos)
        rec = self.cells.get(key)
        if rec is None:
            self.cells[key] = [
                -1 if energy is None else int(energy),
                turn,
                -1,
                "",
                -1,
            ]
        elif energy is None:
            if rec[0] < 0:
                rec[1] = turn
            return
        elif turn >= rec[1]:
            rec[0] = int(energy)
            rec[1] = turn
        else:
            return
        self.fresh.add(key)

    def lostCell(self, pos):
        """a cell we looked at and did not find: it is gone"""
        key = _key(pos)
        if key in self.cells:
            del self.cells[key]
            self.fresh.discard(key)

    def bitCell(self, pos, energy, turn):
        """we have just eaten here"""
        key = _key(pos)
        rec = self.cells.setdefault(key, [0, turn, -1, "", -1])
        rec[0] = int(energy)
        rec[1] = turn
        rec[2] = turn
        self.fresh.add(key)

    def hold(self, pos, uid, turn):
        """reserve a cell for ourselves, so colleagues look elsewhere"""
        key = _key(pos)
        rec = self.cells.setdefault(key, [-1, turn, -1, "", -1])
        rec[3] = uid
        rec[4] = turn
        self.fresh.add(key)

    def heldByOther(self, key, uid, clock):
        rec = self.cells.get(key)
        if rec is None:
            return False
        return rec[3] and rec[3] != uid and clock - rec[4] < self.holdTTL

    def sawPeer(self, uid, pos, energy, home, turn, role):
        old = self.peers.get(uid)
        if old is not None and old[3] > turn:
            return
        if not role and old is not None:
            role = old[4]  # a record relayed by a third party has none
        self.peers[uid] = [_key(pos), int(energy), _key(home), turn, role]

    def sawThreat(self, tile, source, energy, turn, pos):
        old = self.threats.get(tile)
        if old is not None and old[2] > turn and old[1] >= energy:
            return
        self.threats[tile] = [source, int(energy), turn, pos[0], pos[1]]

    def sawTile(self, tile, turn):
        if self.tiles.get(tile, -1) < turn:
            self.tiles[tile] = turn

    # --- the wire ------------------------------------------------------

    def digest(
        self,
        uid,
        clock,
        pos,
        energy,
        home,
        role,
        budget=CELLS_PER_MESSAGE,
        clear=True,
    ):
        """the message one Broadcast carries: a small delta of what we
        learned since the last one, plus who and where we are.

        Everything is copied into tuples: the receiver must not end up
        holding a reference into our own live state."""
        cells = []
        sent = []
        # an exact energy is worth saying, a bare "there is something
        # there" much less, so the delta carries the readings first
        order = sorted(
            self.fresh,
            key=lambda k: -1 if self.cells.get(k, (0,))[0] >= 0 else 0,
        )
        for key in order[:budget]:
            rec = self.cells.get(key)
            sent.append(key)
            if rec is not None:
                cells.append(
                    (
                        key[0],
                        key[1],
                        rec[0],
                        rec[1],
                        rec[2],
                        rec[3],
                        rec[4],
                    )
                )
        if clear:
            self.fresh.difference_update(sent)
        threats = [
            (t[0], t[1], rec[0], rec[1], rec[2], rec[3], rec[4])
            for t, rec in self.threats.items()
            if clock - rec[2] < NEWS_WINDOW
        ][:ALARMS_PER_MESSAGE]
        tiles = [
            (t[0], t[1], turn)
            for t, turn in self.tiles.items()
            if clock - turn < NEWS_WINDOW
        ][:TILES_PER_MESSAGE]
        # the roll travels too, so that a wesen at the edge of the
        # colony can still count the whole of it: the census is what
        # decides whether the colony may grow, and it must not be the
        # number of colleagues that happen to stand next to me
        roll = sorted(
            (
                (u, r[0][0], r[0][1], r[1], r[2][0], r[2][1], r[3])
                for u, r in self.peers.items()
                if clock - r[3] < self.peerTTL
            ),
            key=lambda e: -e[6],
        )[:ROLL_PER_MESSAGE]
        return {
            "s": SIGIL,
            "u": uid,
            "t": clock,
            "p": (int(pos[0]), int(pos[1])),
            "e": int(energy),
            "h": (int(home[0]), int(home[1])),
            "r": role,
            "c": cells,
            "a": threats,
            "x": tiles,
            "w": roll,
        }

    def merge(self, msg, clock):
        """apply a message from a colleague. Returns the sender's clock,
        so a wesen can keep its calendar in step with the colony."""
        for c in msg.get("c", ()):
            x, y, energy, seen, bit, holder, held = c
            key = (x, y)
            rec = self.cells.get(key)
            if rec is None:
                self.cells[key] = [energy, seen, bit, holder, held]
                continue
            if seen > rec[1]:
                rec[0] = energy
                rec[1] = seen
            if bit > rec[2]:
                rec[2] = bit
            if held > rec[4]:
                rec[3] = holder
                rec[4] = held
        for a in msg.get("a", ()):
            tx, ty, source, energy, turn, x, y = a
            self.sawThreat((tx, ty), source, energy, turn, (x, y))
        for x, y, turn in msg.get("x", ()):
            self.sawTile((x, y), turn)
        for u, px, py, energy, hx, hy, turn in msg.get("w", ()):
            if u != msg.get("u"):
                self.sawPeer(u, (px, py), energy, (hx, hy), turn, "")
        uid = msg.get("u")
        if uid:
            self.sawPeer(
                uid,
                msg["p"],
                msg["e"],
                msg["h"],
                msg["t"],
                msg.get("r", ""),
            )
        return int(msg.get("t", 0))

    # --- housekeeping ---------------------------------------------------

    def prune(self, clock, pos, length):
        """drop what is stale, then what is far away, so the ledger
        stays small enough to scan every few turns."""
        cells = self.cells
        for key in [
            k for k, r in cells.items() if clock - r[1] > self.cellTTL
        ]:
            del cells[key]
        if len(cells) > MAX_CELLS:
            half = length // 2

            def far(item):
                (x, y), rec = item
                dx = abs(x - pos[0])
                dy = abs(y - pos[1])
                dx = length - dx if dx > half else dx
                dy = length - dy if dy > half else dy
                # keep what is near, what was seen recently, and what
                # somebody actually read the energy of
                return (
                    -(dx + dy)
                    + (clock - rec[1]) * 0.05
                    - (40 if rec[0] >= 0 else 0)
                )

            for key, _ in sorted(cells.items(), key=far)[
                : len(cells) - MAX_CELLS
            ]:
                del cells[key]
        for uid in [
            u for u, r in self.peers.items() if clock - r[3] > self.peerTTL
        ]:
            del self.peers[uid]
        if len(self.peers) > MAX_PEERS:
            for uid, _ in sorted(
                self.peers.items(), key=lambda i: i[1][3]
            )[: len(self.peers) - MAX_PEERS]:
                del self.peers[uid]
        stale = self.threatTTL
        for tile in [
            t for t, r in self.threats.items() if clock - r[2] > stale
        ]:
            del self.threats[tile]
        if len(self.threats) > MAX_THREATS:
            for tile, _ in sorted(
                self.threats.items(), key=lambda i: i[1][2]
            )[: len(self.threats) - MAX_THREATS]:
                del self.threats[tile]
        if len(self.tiles) > MAX_TILES:
            for tile, _ in sorted(self.tiles.items(), key=lambda i: i[1])[
                : len(self.tiles) - MAX_TILES
            ]:
                del self.tiles[tile]
        self.fresh = {k for k in self.fresh if k in cells}

    # --- persistence -----------------------------------------------------

    def persist(self):
        return {
            "cells": {f"{k[0]},{k[1]}": v for k, v in self.cells.items()},
            "peers": self.peers,
            "threats": {
                f"{k[0]},{k[1]}": v for k, v in self.threats.items()
            },
            "tiles": {f"{k[0]},{k[1]}": v for k, v in self.tiles.items()},
        }

    def restore(self, obj):
        def unkey(d):
            out = {}
            for k, v in d.items():
                x, _, y = k.partition(",")
                out[(int(x), int(y))] = v
            return out

        self.cells = unkey(obj.get("cells", {}))
        self.peers = {
            u: [tuple(v[0]), v[1], tuple(v[2]), v[3], v[4]]
            for u, v in obj.get("peers", {}).items()
        }
        self.threats = unkey(obj.get("threats", {}))
        self.tiles = unkey(obj.get("tiles", {}))
        self.fresh = set()
