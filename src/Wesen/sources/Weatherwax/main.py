"""Weatherwax - headology. Wins by knowing the land and knowing the others.

Granny Weatherwax has no use for magic when plain knowledge does: she
knows every field, every path and every neighbour's habits. This source
plays the same way under the "life" food rule: the pasture, not a garden,
is the income, and the whole colony shares one map of it.

Why the old approach failed: with `[wesen] upkeep = 1 + 0.005 x energy`
and 600 scattered food cells at the start, the world is lean for the
first few hundred turns. The earlier Weatherwax (a gardening colony with
scouts and "bogeymen" against Vetinari) starved on its own because its
herding rule refused any cell under 65 energy unless it was nearly dead,
and its war machinery needed a colony of 16 that never came. So:

Economy - herding on a shared map.
    Every wesen looks (cheap) and closerLooks (energies) each turn and
    writes what it sees into a class-level map of food cells, keyed by
    tile so lookups stay local. A cell's current energy is estimated
    from the last sighting and the regrowth rate, so a wesen can plan for
    cells out of sight and return to a bitten cell when it has regrown.
    Each turn it walks to the cell with the best energy per time (bites
    x bite / (eat time + walk time)) and eats. What it eats depends on
    its body: with a full reserve it takes only the bites that leave a
    cell around a third of its capacity, where it regrows fastest and
    where no hungry rival bothers with it; below the reserve it bites
    down to the roots; only when starving does it kill a cell.

Land - fertility and exploration.
    The terrain (biome.py) is free to read and constant, so the colony
    samples it once, tile by tile, and explores fertile tiles first.
    A wesen without a worthwhile target claims the most promising
    unexplored tile and walks there, looking on the way. With spare time
    and energy it plants seeds (`Vomit`) on fertile empty ground where
    the neighbourhood density lets them grow: the pasture is the pie,
    and a bigger pie is the only long-term win.

People - the colony.
    Population follows the pasture *this wesen keeps*: it splits while
    the ground closer to its anchor than to any colleague's holds more
    than `CELLS_PER_WESEN` known cells, or while there is no colleague
    near it at all. A child is sent
    to a free site of the map away from every other anchor, so the herd
    spreads over the land instead of trampling one cluster. Old age is
    cured by reproducing. Upkeep grows with the body, so many moderate
    bodies beat a few fat ones, but bodies still fill up with whatever
    the pasture yields beyond upkeep: that is the score.

Neighbours - who attacks whom (read from their code).
    Nightwatch and Dwarf strike anything up to their own energy plus a
    fixed margin once they are above a threshold; Vetinari strikes only
    on its own cell and only when it kills; GreatRabbit and Rincewind
    never strike; everything else (LuTze and any future source) is
    assumed to strike whatever it can kill within a few cells. A wesen
    first tries to eat itself out of reach, then flees with its whole
    time budget along a direction chosen at run time, so a pursuer
    cannot time its approach against a fixed three-cell hop. Cheap
    thieves on the wesen's own cell are killed.

``WESEN_STRICT=1`` in the environment makes internal errors crash the
game (development); by default the failing turn is skipped and the error
is printed once.
"""

import os
from random import random

from ...colony import Colony
from ...defaultwesensource import DefaultWesenSource
from ...objects.wesen import RuleException
from ...point import getShortestTranslation

STRICT = bool(os.environ.get("WESEN_STRICT"))

# sources that hunt wesen once they hold the first energy, attacking any
# wesen up to their own energy plus the second (see their helper.py)
CHASERS = {"Dwarf": (301, 300), "Nightwatch": (375, 375)}
# sources that never attack anybody
HARMLESS = {"GreatRabbit", "Rincewind"}
# sources that strike only on their own cell, and only when it kills
CELL_STRIKERS = {"Vetinari"}


class WesenSource(DefaultWesenSource):
    # --- what one wesen knows (its own, since 2026-09-09) ----------------
    # These were shared by the whole colony through the class, which is
    # telepathy and no longer allowed (see isolation.py). They are now
    # one wesen's own, and what the colony knows is what it has passed
    # around: see `sayWhatISaw` and `Receive`.
    worldTurn = 0  # estimate of the current world turn
    pasture = {}  # tile -> {cell -> [energy|None, turn seen, fertility]}
    cellCount = 0  # number of cells in the pasture map
    claims = {}  # cell -> (uid, turn): one wesen per target
    explored = {}  # tile -> turn it was last looked at
    tileClaims = {}  # tile -> (uid, turn): one explorer per tile
    fertTiles = None  # tile -> mean fertility (computed once)
    tileCentres = None
    danger = {}  # tile -> (turn, energy) of the last killer seen there
    stats = {}  # debug counters
    reported = set()  # exception messages already printed

    # --- tunables --------------------------------------------------------
    SIGIL = "weatherwax/1"  # our messages, and nobody else's
    CELLS_PER_MESSAGE = 16  # cells one broadcast carries
    SAY_EVERY = 3  # turns between two broadcasts with nothing new
    TILE = 24  # map tile edge (look range 24 covers ~2x2 tiles)
    GRAZE_FLOOR = 0.2  # share of capacity a sustainable bite leaves
    GROWTH_SHARE = (
        0.5  # regrowth assumed for a remembered cell, x growrate
    )
    UNKNOWN_ENERGY = 45  # assumed energy of a cell only seen from afar
    RESERVE_BASE = 300  # body below which we bite cells to the roots
    RESERVE_MAX = 600  # ... at most this, however long the winter
    STARVING = 90  # below this even the last bite of a cell
    CELLS_PER_WESEN = 100  # cells a district needs per extra wesen
    DISTRICT_RANGE = 60  # how far from its anchor a district reaches
    DISTRICT_EVERY = 8  # turns between two counts of it
    SEEDER_SHARE = 3  # one cell in this many is left to mature and seed
    MAX_COLONY = 64
    ANCHOR_SEP = 16  # a child's site keeps this far from other anchors
    SITE_RANGE = 80  # ... and is looked for this far from the parent
    TARGET_RANGE = 60  # manhattan distance worth walking for a bite
    HOME_RADIUS = 24  # cells beyond this from the anchor count less
    AWAY_FACTOR = 0.7
    LOST = 400  # turns after which a cell report is not worth having
    CLAIM_TTL = 12  # turns a target claim lasts
    TILE_CLAIM_TTL = 60
    EXPLORE_TTL = 300  # a tile is worth looking at again after this
    DANGER_TTL = 60  # turns a killer sighting keeps a tile off limits
    DANGER_DISTANCE = 6  # react to killers from this distance
    KILL_COST_MAX = 200  # never pay more than this (0.5 x victim) per kill
    KILL_COST_SHARE = 0.3  # ... nor more than this share of the body
    OLD_AGE_MARGIN = 4  # reproduce this many turns before maxage
    REANCHOR_AFTER = 40  # turns without a bite -> the anchor is given up
    PLANT = True  # plant seeds with spare time
    PLANT_MIN_FERTILITY = 1.0
    PLANT_MAX_DENSITY = 1.2  # neighbourhood energy / maxamount
    PLANT_MIN_DENSITY = 0.1
    PLANT_MARGIN = 100  # energy above the reserve before planting

    def __init__(self, infoAllSource):
        DefaultWesenSource.__init__(self, infoAllSource)
        cls = type(self)
        self.uid = None
        # the colony's book, kept by talking: class attributes are
        # genetic information now (see isolation.py), so the map, the
        # roll and the claims below are this wesen's own and reach the
        # others only if they are broadcast
        self.colony = Colony(cls.SIGIL, self.worldlength, cls.SITE_RANGE)
        self.news = {}  # what to say next time we speak
        self.said = -99  # when we last spoke
        self.inbox = None  # orders a parent talked to us at birth
        self.bornTurn = cls.worldTurn
        self.turnsLived = 0
        self.anchor = None  # cell my grazing centres on
        self.goal = None  # cell I am walking to (site or exploration)
        self.goalKind = None  # "site" or "explore"
        self.lastBite = cls.worldTurn
        self.parent = None  # sacrifice: engine id to give everything to
        self.hold = 0  # turns to stay put (a sacrifice is coming back)
        self.maxAge = self.infoWesen["maxage"]
        self.eatCost = self.infoTime["eat"]
        self.moveCost = self.infoTime["move"]
        self.attackTime = self.infoTime["attack"]
        self.reproCost = self.infoTime["reproduce"]
        self.vomitCost = self.infoTime["vomit"]
        self.lookCost = self.infoTime["look"]
        self.closerLookCost = self.infoTime["closerlook"]
        self.lookRange = self.infoRange["look"]
        self.closerRange = self.infoRange["closer_look"]
        self.seedRange = self.infoRange["seed"]
        self.maxamount = self.infoFood["maxamount"]
        self.bite = self.foodBite() or self.maxamount
        self.roots = self.foodRoots()
        # per-turn view
        self.foodsHere = []
        self.foods = []
        self.enemies = []
        self.enemiesHere = []
        self.friendsHere = 0
        self.districtCells = 0  # local carrying capacity (see district)
        self.districtTurn = -99
        self.neighbours = 0
        if cls.fertTiles is None:
            cls.sampleTerrain(self)

    def __str__(self):
        return "<Granny Weatherwax, headologist>"

    def getDescriptor(self):
        return {
            "mode": self.mode(),
            "anchor": self.anchor,
            "goal": self.goal,
        }

    # --- persistence -----------------------------------------------------

    def persist(self):
        return {
            "anchor": self.anchor,
            "goal": self.goal,
            "goalKind": self.goalKind,
            "uid": self.uid,
            "colony": self.colony.persist(),
        }

    def restore(self, obj):
        state = obj.get("wesensource", {}) or {}
        for key in ("anchor", "goal", "goalKind"):
            value = state.get(key)
            if value is not None and key != "goalKind":
                value = (value[0], value[1])
            setattr(self, key, value)
        self.uid = state.get("uid")
        self.colony.restore(state.get("colony"), uidType=str)
        self.colony.uid = self.uid

    # --- bookkeeping -----------------------------------------------------

    @classmethod
    def count(cls, key, n=1):
        cls.stats[key] = cls.stats.get(key, 0) + n

    @classmethod
    def sampleTerrain(cls, me):
        """the fertility of every tile, from a few free samples each"""
        length = me.worldlength
        tile = cls.TILE
        n = (length + tile - 1) // tile
        cls.fertTiles = {}
        cls.tileCentres = {}
        for tx in range(n):
            for ty in range(n):
                cx = min(length - 1, tx * tile + tile // 2)
                cy = min(length - 1, ty * tile + tile // 2)
                q = tile // 4
                points = [
                    (cx, cy),
                    (cx - q, cy - q),
                    (cx + q, cy - q),
                    (cx - q, cy + q),
                    (cx + q, cy + q),
                ]
                total = 0.0
                for p in points:
                    total += me.fertility([p[0] % length, p[1] % length])
                cls.fertTiles[(tx, ty)] = total / len(points)
                cls.tileCentres[(tx, ty)] = (cx, cy)

    def tick(self):
        cls = type(self)
        if self.uid is None:
            # engine ids are addresses and get reused, so a name is the
            # address and the turn it was issued. A shared counter would
            # be a shared brain, and every wesen would be number one
            self.uid = f"{self.id():x}:{self.bornTurn}"
            self.colony.uid = self.uid
        self.turnsLived += 1
        estimate = self.bornTurn + self.turnsLived
        self.colony.tick()
        self.colony.sync(estimate)
        cls.worldTurn = self.colony.clock
        now = cls.worldTurn
        pos = self.position()
        self.colony.note(self.uid, self.anchor or pos, self.energy(), now)
        if self.turnsLived % 25 == 0:
            self.colony.forget()
            cls.claims = {
                k: v
                for k, v in cls.claims.items()
                if now - v[1] <= cls.CLAIM_TTL
            }
            cls.tileClaims = {
                k: v
                for k, v in cls.tileClaims.items()
                if now - v[1] <= cls.TILE_CLAIM_TTL
            }

    def colonySize(self):
        """how many of us there are, estimated from how close together
        the ones we have heard from stand: nobody ever hears the whole
        roll, and a population rule measured against the raw count lets
        the colony grow until it has eaten the world."""
        return self.colony.census(self.position())

    def sayWhatISaw(self):
        """one broadcast a turn: where I am, how fat, and the cells,
        killers and claims I have seen since I last spoke.

        A broadcast costs 1 time and carries as much as we like, so the
        only reason not to say everything is the work it makes for the
        listeners; a wesen that has nothing new still calls out every
        few turns, so that whoever has walked into range hears it."""
        cls = type(self)
        if self.time() < self.infoTime["broadcast"]:
            return
        news = self.news
        stale = cls.worldTurn - self.said
        if not news and stale < cls.SAY_EVERY:
            return
        cells = news.get("c")
        if cells and len(cells) > cls.CELLS_PER_MESSAGE:
            # the richest are worth saying; the rest keep
            cells.sort(key=lambda c: -c[2])
            news["c"] = cells[: cls.CELLS_PER_MESSAGE]
        self.said = cls.worldTurn
        self.news = {}
        self.Broadcast(
            self.colony.say(
                self.position(), self.energy(), news, self.mode()
            )
        )
        cls.count("said")

    def tell(self, kind, item):
        """put one thing on the list to be said next time we speak"""
        self.news.setdefault(kind, []).append(item)

    def Receive(self, message):
        """what a colleague has seen, and orders from a parent.

        Everything here arrives frozen (the engine seals a message), so
        it is read and written into our own book, never kept."""
        cls = type(self)
        if not isinstance(message, dict) or message.get("s") != cls.SIGIL:
            return
        if message.get("to") is not None:
            if message["to"] == self.id():
                self.colony.sync(int(message.get("t", 0)))
                self.bornTurn = self.colony.clock
                self.inbox = dict(message["o"])
            return
        news = self.colony.hear(message)
        if not news:
            return
        for x, y, energy, turn in news.get("c", ()):
            if cls.worldTurn - turn > cls.LOST:
                continue
            self.mapSet((x, y), energy if energy >= 0 else None)
        for tx, ty, turn, energy in news.get("d", ()):
            old = cls.danger.get((tx, ty))
            if old is None or old[0] < turn:
                cls.danger[(tx, ty)] = (turn, energy)
        for x, y, uid, turn in news.get("k", ()):
            old = cls.claims.get((x, y))
            if old is None or old[1] < turn:
                cls.claims[(x, y)] = (uid, turn)
        for tx, ty, turn in news.get("x", ()):
            if cls.explored.get((tx, ty), -1) < turn:
                cls.explored[(tx, ty)] = turn

    def takeOrders(self):
        cls = type(self)
        order = self.inbox
        self.inbox = None
        if not order:
            return
        self.parent = order.get("sacrifice")
        site = order.get("site")
        if site is not None:
            self.goal = (site[0], site[1])
            self.goalKind = "site"
        tile = order.get("tile")
        if tile is not None:
            tile = (tile[0], tile[1])
            self.goal = cls.tileCentres[tile]
            self.goalKind = "explore"
            cls.tileClaims[tile] = (self.uid, cls.worldTurn)
            self.tell("x", (tile[0], tile[1], cls.worldTurn))

    # --- geometry --------------------------------------------------------

    @staticmethod
    def viewDist(a, b):
        """max metric for positions from one look() (no wrap there)"""
        dx = abs(a[0] - b[0])
        dy = abs(a[1] - b[1])
        return dx if dx > dy else dy

    def torusDist(self, a, b):
        dx, dy = getShortestTranslation(a, b, self.worldlength)
        return int(max(abs(dx), abs(dy)))

    def torusManhattan(self, a, b):
        dx, dy = getShortestTranslation(a, b, self.worldlength)
        return int(abs(dx) + abs(dy))

    def tileOf(self, cell):
        tile = type(self).TILE
        return (cell[0] // tile, cell[1] // tile)

    def numTiles(self):
        return (self.worldlength + self.TILE - 1) // self.TILE

    def stepTowards(self, target, maxCells):
        """move up to maxCells cells towards target (torus aware); never
        onto a cell holding an enemy that would strike me there"""
        moved = 0
        target = (target[0], target[1])
        while moved < maxCells and self.time() >= self.moveCost:
            pos = self.position()
            if (pos[0], pos[1]) == target:
                break
            dx, dy = getShortestTranslation(pos, target, self.worldlength)
            steps = []
            if dx:
                steps.append([1 if dx > 0 else -1, 0])
            if dy:
                steps.append([0, 1 if dy > 0 else -1])
            if abs(dy) > abs(dx):
                steps.reverse()
            step = None
            for cand in steps:
                if self.safeCell(
                    (
                        (pos[0] + cand[0]) % self.worldlength,
                        (pos[1] + cand[1]) % self.worldlength,
                    )
                ):
                    step = cand
                    break
            if step is None or not self.Move(step):
                break
            moved += 1
        return moved

    def safeCell(self, cell):
        """no enemy that would strike me stands on that cell"""
        for e in self.enemies:
            p = e["position"]
            if (p[0], p[1]) == cell and self.strikesOnCell(e):
                return False
        return True

    # --- the pasture map -------------------------------------------------

    def tilesInBox(self, x0, x1, y0, y1, wrap):
        """tiles overlapping the box (inclusive corners)"""
        tile = type(self).TILE
        n = self.numTiles()
        tx0, tx1 = x0 // tile, x1 // tile
        ty0, ty1 = y0 // tile, y1 // tile
        out = []
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                if wrap:
                    out.append((tx % n, ty % n))
                elif 0 <= tx < n and 0 <= ty < n:
                    out.append((tx, ty))
        return out

    def cellsNear(self, pos, r):
        """(cell, entry) pairs of the map around pos (torus box)"""
        cls = type(self)
        seen = set()
        for tile in self.tilesInBox(
            pos[0] - r, pos[0] + r, pos[1] - r, pos[1] + r, True
        ):
            if tile in seen:
                continue
            seen.add(tile)
            block = cls.pasture.get(tile)
            if block:
                yield from block.items()

    def mapSet(self, cell, energy, fert=None):
        cls = type(self)
        tile = self.tileOf(cell)
        block = cls.pasture.setdefault(tile, {})
        entry = block.get(cell)
        if entry is None:
            if fert is None:
                fert = self.fertility([cell[0], cell[1]])
            block[cell] = [energy, cls.worldTurn, fert]
            cls.cellCount += 1
        else:
            if energy is not None or entry[0] is None:
                entry[0] = energy
            entry[1] = cls.worldTurn

    def mapDel(self, cell):
        cls = type(self)
        block = cls.pasture.get(self.tileOf(cell))
        if block and block.pop(cell, None) is not None:
            cls.cellCount -= 1
            if not block:
                del cls.pasture[self.tileOf(cell)]

    def capacity(self, fert):
        return max(1, int(self.maxamount * fert))

    def estimate(self, entry):
        """what a remembered cell probably holds now"""
        cls = type(self)
        energy, turn, fert = entry
        if energy is None:
            energy = cls.UNKNOWN_ENERGY
        cap = self.capacity(fert)
        if energy >= cap:
            return energy  # a body: it does not grow, and hardly shrinks
        rate = self.infoFood["growrate"] * cls.GROWTH_SHARE * fert
        return min(cap, energy + rate * (cls.worldTurn - turn))

    def noteView(self, view):
        """closerLook: exact energies, enemies, killers"""
        cls = type(self)
        pos = self.position()
        self.foodsHere = []
        self.foods = []
        self.enemies = []
        self.enemiesHere = []
        self.friendsHere = 0
        for o in view:
            p = o["position"]
            if o["type"] == "food":
                self.foods.append(o)
                self.mapSet((p[0], p[1]), o["energy"])
                self.tell("c", (p[0], p[1], o["energy"], cls.worldTurn))
                if p == pos:
                    self.foodsHere.append(o)
            elif o["source"] == self.source:
                if p == pos:
                    self.friendsHere += 1
            else:
                self.enemies.append(o)
                if p == pos:
                    self.enemiesHere.append(o)
                if self.wouldStrike(o, 0):
                    tile = self.tileOf(p)
                    old = cls.danger.get(tile)
                    if old is None or old[1] <= o["energy"]:
                        cls.danger[tile] = (cls.worldTurn, o["energy"])
                        self.tell(
                            "d",
                            (tile[0], tile[1], cls.worldTurn, o["energy"]),
                        )
        self.foodsHere.sort(key=lambda f: -f["energy"])

    def noteLook(self, lookView):
        """look(): where food is at all (no energies), what has vanished,
        and which tiles have been seen"""
        cls = type(self)
        pos = self.position()
        r = self.lookRange
        length = self.worldlength
        x0, x1 = max(0, pos[0] - r), min(length - 1, pos[0] + r)
        y0, y1 = max(0, pos[1] - r), min(length - 1, pos[1] + r)
        seen = set()
        for o in lookView:
            if o["type"] == "food":
                p = o["position"]
                seen.add((p[0], p[1]))
        for cell in seen:
            self.mapSet(cell, None)
        for tile in self.tilesInBox(x0, x1, y0, y1, False):
            block = cls.pasture.get(tile)
            if block:
                gone = [
                    c
                    for c in block
                    if c not in seen
                    and x0 <= c[0] <= x1
                    and y0 <= c[1] <= y1
                ]
                for c in gone:
                    self.mapDel(c)
            centre = cls.tileCentres[tile]
            if self.viewDist(centre, pos) <= r - 4:
                cls.explored[tile] = cls.worldTurn

    def dangerous(self, cell):
        cls = type(self)
        rec = cls.danger.get(self.tileOf(cell))
        if rec is None:
            return False
        if cls.worldTurn - rec[0] > cls.DANGER_TTL:
            return False
        return self.attackDamage() * rec[1] >= self.energy()

    # --- eating ----------------------------------------------------------

    def reserve(self):
        """body below which a wesen bites cells down to the roots"""
        cls = type(self)
        base = cls.RESERVE_BASE
        winter = int(self.upkeepOf(base) * self.turnsUntilSpring())
        return min(cls.RESERVE_MAX, base + winter)

    def mode(self):
        energy = self.energy()
        if energy < type(self).STARVING:
            return "starving"
        if energy < self.reserve():
            return "hungry"
        return "sustain"

    def floorFor(self, fert):
        return int(type(self).GRAZE_FLOOR * self.capacity(fert))

    def isSeeder(self, cell):
        """Food only seeds once it has grown to birth_maturity of its
        capacity, and every cell dies at maxage: a pasture grazed
        everywhere below maturity never spreads and ages out. So a
        fixed share of cells, chosen by position, is left alone."""
        share = type(self).SEEDER_SHARE
        return share > 0 and (cell[0] * 7 + cell[1] * 13) % share == 0

    def bitesAllowed(self, energy, fert, mode, cell=None):
        """bites this wesen may take from a cell holding energy"""
        bite = self.bite
        if mode == "starving":
            return max(0, int(-(-energy // bite)))
        if cell is not None and self.isSeeder(cell):
            # a body (above the cell's capacity) is food for anybody
            if energy <= self.capacity(fert):
                return 0
        if mode == "hungry":
            left = self.roots + 1
        else:
            left = max(self.roots + 1, self.floorFor(fert))
        if energy - bite < left:
            return 0
        return int((energy - left) // bite)

    def eatFood(self, food):
        """one Eat() on a food of this turn's view; keeps the view and
        the map in step"""
        if self.time() < self.eatCost:
            return False
        try:
            ok = self.Eat(food["id"])
        except RuleException:
            ok = False
        if not ok:
            return False
        cls = type(self)
        taken = self.foodYield(food)
        cell = (food["position"][0], food["position"][1])
        if taken >= food["energy"]:
            food["energy"] = 0
            self.mapDel(cell)
            if food in self.foodsHere:
                self.foodsHere.remove(food)
        else:
            food["energy"] -= taken
            self.mapSet(cell, food["energy"])
        self.lastBite = cls.worldTurn
        self.moveAnchor(cell)
        cls.count("bites")
        return True

    def moveAnchor(self, cell):
        if self.anchor is None:
            self.anchor = cell
            return
        dx, dy = getShortestTranslation(
            self.anchor, cell, self.worldlength
        )
        length = self.worldlength
        self.anchor = (
            int(round(self.anchor[0] + 0.25 * dx)) % length,
            int(round(self.anchor[1] + 0.25 * dy)) % length,
        )

    def grazeHere(self, mode=None):
        """eat from my own cell as the mode allows, richest cell first"""
        if mode is None:
            mode = self.mode()
        while self.foodsHere and self.time() >= self.eatCost:
            food = self.foodsHere[0]
            cell = (food["position"][0], food["position"][1])
            fert = self.fertilityOf(cell)
            if self.bitesAllowed(food["energy"], fert, mode, cell) < 1:
                # a smaller cell allows no more than the biggest
                break
            if not self.eatFood(food):
                break
            self.foodsHere.sort(key=lambda f: -f["energy"])
            mode = self.mode()

    def fertilityOf(self, cell):
        cls = type(self)
        block = cls.pasture.get(self.tileOf(cell))
        entry = block.get(cell) if block else None
        if entry is not None:
            return entry[2]
        return self.fertility([cell[0], cell[1]])

    def harvestUntil(self, target):
        """eat anything here until energy >= target (survival)"""
        while (
            self.foodsHere
            and self.energy() < target
            and self.time() >= self.eatCost
        ):
            if not self.eatFood(self.foodsHere[0]):
                break
            self.foodsHere.sort(key=lambda f: -f["energy"])

    # --- fighting and fleeing --------------------------------------------

    def canKill(self, enemyEnergy):
        mine = self.energy()
        if self.attackDamage() * mine < enemyEnergy:
            return False
        return mine - self.attackCost() * enemyEnergy > 50

    def lethal(self, enemyEnergy):
        return self.attackDamage() * enemyEnergy >= self.energy()

    def wouldStrike(self, e, dist):
        """would this enemy attack me at that distance (this turn or the
        next), judging by its source's code?"""
        src = e["source"]
        if src in HARMLESS:
            return False
        if src in CELL_STRIKERS:
            return dist == 0 and self.lethal(e["energy"])
        rule = CHASERS.get(src)
        if rule is not None:
            return (
                e["energy"] >= rule[0]
                and self.energy() <= e["energy"] + rule[1]
                and dist <= type(self).DANGER_DISTANCE
            )
        # unknown or LuTze: strikes what it can kill, from a few cells
        return self.lethal(e["energy"]) and dist <= 4

    def strikesOnCell(self, e):
        """would stepping onto this enemy's cell get me struck?"""
        src = e["source"]
        if src in HARMLESS:
            return False
        rule = CHASERS.get(src)
        if rule is not None:
            return (
                e["energy"] >= rule[0]
                and self.energy() <= e["energy"] + rule[1]
            )
        return self.lethal(e["energy"])

    def safeBody(self, e):
        """energy from which this enemy leaves me alone"""
        rule = CHASERS.get(e["source"])
        if rule is not None:
            return e["energy"] + rule[1] + 1
        return int(self.attackDamage() * e["energy"]) + 1

    def handleDanger(self):
        """returns True if the turn is over (we fled)"""
        cls = type(self)
        pos = self.position()
        threats = []
        for e in self.enemies:
            d = self.viewDist(e["position"], pos)
            if self.wouldStrike(e, d):
                threats.append(e)
        if not threats:
            return False
        # eat myself out of reach if the cell allows it
        need = max(self.safeBody(e) for e in threats)
        if self.foodsHere and need - self.energy() <= 3 * self.bite:
            self.harvestUntil(need)
            threats = [
                e
                for e in threats
                if self.wouldStrike(e, self.viewDist(e["position"], pos))
            ]
            if not threats:
                cls.count("outgrew")
                return False
        # a thief that came too close: strike first when that kills
        for e in threats:
            if e["position"] == pos and self.canKill(e["energy"]):
                if self.time() >= self.attackTime:
                    self.Attack(e["id"])
                    cls.count("strike_" + e["source"])
                    threats.remove(e)
                    break
        if not threats:
            return False
        self.flee(threats)
        cls.count(
            "flee_" + max(threats, key=lambda e: e["energy"])["source"]
        )
        return True

    def flee(self, threats):
        """run with the whole time budget along the straight line that
        ends farthest from every threat; ties broken at random"""
        pos = self.position()
        length = self.worldlength
        budget = self.time() // self.moveCost
        if budget < 1:
            return 0
        best, bestScore = None, None
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            end = (
                (pos[0] + d[0] * budget) % length,
                (pos[1] + d[1] * budget) % length,
            )
            score = (
                min(
                    self.torusManhattan(end, e["position"])
                    for e in threats
                )
                + random() * 0.5
            )
            if not self.safeCell(end):
                score -= 100
            if bestScore is None or score > bestScore:
                best, bestScore = d, score
        moved = 0
        while moved < budget and self.Move([best[0], best[1]]):
            moved += 1
        return moved

    def killThieves(self):
        """enemies on my cell that are cheap to kill eat my pasture"""
        cls = type(self)
        for e in list(self.enemiesHere):
            if self.time() < self.attackTime:
                return
            cost = self.attackCost() * e["energy"]
            if (
                cost > cls.KILL_COST_MAX
                or cost > cls.KILL_COST_SHARE * self.energy()
            ):
                continue
            if not self.canKill(e["energy"]):
                continue
            try:
                self.Attack(e["id"])
            except RuleException:
                continue
            cls.count("kill_" + e["source"])
            self.enemiesHere.remove(e)
            if e in self.enemies:
                self.enemies.remove(e)

    # --- the colony ------------------------------------------------------

    def district(self):
        """the cells this wesen keeps: the ones it knows of within
        reach of its anchor and closer to that anchor than to any
        colleague's - the local carrying capacity, and what the
        population rule is measured against.

        A colony-wide count cannot be had honestly: nobody ever hears
        the whole roll, so every wesen under-counts and every wesen
        concludes on its own that there is room for one more. This does
        not need the whole roll. The ground a wesen keeps shrinks as
        colleagues settle around it - it is the Voronoi cell of the
        anchors it knows about - so the colony stops growing exactly
        where the pasture stops paying, and it stops locally, in the
        places that are full, while the empty ground is still filling.

        Recomputed every `DISTRICT_EVERY` turns: it is a scan of the
        map around the anchor and it does not change quickly."""
        cls = type(self)
        if cls.worldTurn - self.districtTurn < cls.DISTRICT_EVERY:
            return self.districtCells
        self.districtTurn = cls.worldTurn
        home = self.anchor or tuple(self.position())
        anchors = [
            rec[0]
            for rec in self.colony.peers().values()
            if self.torusManhattan(home, rec[0]) <= cls.DISTRICT_RANGE * 2
        ]
        count = 0
        for cell, entry in self.cellsNear(home, cls.DISTRICT_RANGE):
            mine = self.torusManhattan(home, cell)
            if mine > cls.DISTRICT_RANGE:
                continue
            if any(self.torusManhattan(a, cell) < mine for a in anchors):
                continue  # a colleague keeps this ground, not I
            count += 1
        self.districtCells = count
        self.neighbours = len(anchors)
        return count

    def roomForAnother(self):
        """may the colony grow, as far as this wesen can tell?

        On the frontier - no colleague anywhere near the ground I keep -
        the answer is yes: the land next door is nobody's. Inside the
        colony it takes a district that feeds another mouth. The
        estimated colony size is only a ceiling, and one for the
        machine rather than for the game: every wesen costs the
        simulation time."""
        cls = type(self)
        cells = self.district()
        if self.colonySize() >= cls.MAX_COLONY:
            return False
        if not self.neighbours:
            return True
        return cells >= cls.CELLS_PER_WESEN

    def freeSite(self):
        """a known, live cell away from every other wesen's anchor"""
        cls = type(self)
        pos = self.position()
        # where the others keep house, as far as we have heard
        anchors = [rec[0] for rec in self.colony.peers().values()]
        best, bestValue = None, 0.0
        for cell, entry in self.cellsNear(pos, cls.SITE_RANGE):
            est = self.estimate(entry)
            if est < self.roots + self.bite + 1:
                continue
            if self.dangerous(cell):
                continue
            d = self.torusManhattan(pos, cell)
            if d > cls.SITE_RANGE:
                continue
            value = est / (d + 10.0)
            if value <= bestValue:
                continue
            if any(
                self.torusDist(a, cell) < cls.ANCHOR_SEP for a in anchors
            ):
                continue
            best, bestValue = cell, value
        return best

    def maybeReproduce(self):
        cls = type(self)
        if self.time() < self.reproCost:
            return
        if self.energy() < self.minBirthEnergy():
            return
        old = self.age() >= self.maxAge - cls.OLD_AGE_MARGIN
        order = None
        room = self.roomForAnother()
        if old and not room:
            # reproducing resets my age; the child is only there to
            # give everything back, so the colony does not double
            # every maxage turns whatever the pasture says
            order = {"sacrifice": self.id()}
        elif not old:
            if not room:
                return
            reserve = self.reserve()
            if self.energy() < 2 * reserve + self.birthCost():
                return
            if self.lean() and self.energy() < 3 * reserve:
                return
            pos = self.position()
            for e in self.enemies:
                if (
                    self.viewDist(e["position"], pos)
                    <= cls.DANGER_DISTANCE
                ):
                    half = (self.energy() - self.birthCost()) // 2
                    if self.strikesOnCellWith(e, half):
                        return
            site = self.freeSite()
            if site is not None:
                order = {"site": site}
            else:
                tile = self.chooseTile()
                if tile is None:
                    return
                order = {"tile": tile}
        child = self.Reproduce()
        if not child:
            return
        cls.count("births")
        # count the child at once, or every parent in this turn splits
        # against the same population (its own uid replaces this entry)
        # count the child on our own roll at once, or every parent in
        # this turn splits against the same population
        self.colony.note(f"{child:x}:{cls.worldTurn}", self.position(), 1)
        if order:
            # the only inheritance the engine allows: one Talk, in the
            # turn the child is born, before it has ever acted
            self.Talk(
                child,
                {
                    "s": cls.SIGIL,
                    "to": child,
                    "t": cls.worldTurn,
                    "o": order,
                },
            )
            if "sacrifice" in order:
                # the child acts after me next turn: stay put until then
                self.hold = 2
                cls.count("sacrifices")

    def strikesOnCellWith(self, e, energy):
        """strikesOnCell() judged for a body of the given energy"""
        src = e["source"]
        if src in HARMLESS:
            return False
        rule = CHASERS.get(src)
        if rule is not None:
            return (
                e["energy"] >= rule[0] and energy <= e["energy"] + rule[1]
            )
        return self.attackDamage() * e["energy"] >= energy

    # --- choosing where to go --------------------------------------------

    def chooseTarget(self):
        """the remembered cell with the best energy per time"""
        cls = type(self)
        pos = self.position()
        here = (pos[0], pos[1])
        mode = self.mode()
        now = cls.worldTurn
        best, bestRate = None, 0.0
        for cell, entry in self.cellsNear(pos, cls.TARGET_RANGE):
            if cell == here:
                continue
            claim = cls.claims.get(cell)
            if (
                claim is not None
                and claim[0] != self.uid
                and now - claim[1] <= cls.CLAIM_TTL
            ):
                continue
            est = self.estimate(entry)
            n = self.bitesAllowed(est, entry[2], mode, cell)
            if n < 1:
                if (
                    entry[0] is not None
                    or mode == "sustain"
                    or self.isSeeder(cell)
                ):
                    continue
                n = 1  # unknown cell: worth a look while hungry
            d = self.torusManhattan(pos, cell)
            if d > cls.TARGET_RANGE:
                continue
            rate = n * self.bite / (n * self.eatCost + d * self.moveCost)
            if entry[0] is None:
                rate *= 0.6
            if self.anchor is not None and (
                self.torusManhattan(self.anchor, cell) > cls.HOME_RADIUS
            ):
                rate *= cls.AWAY_FACTOR
            if rate <= bestRate:
                continue
            if self.dangerous(cell) or not self.safeCell(cell):
                continue
            best, bestRate = cell, rate
        return best

    def chooseTile(self):
        """the best tile to explore: fertile, long unseen, near"""
        cls = type(self)
        pos = self.position()
        now = cls.worldTurn
        best, bestScore = None, 0.0
        for tile, fert in cls.fertTiles.items():
            claim = cls.tileClaims.get(tile)
            if (
                claim is not None
                and claim[0] != self.uid
                and now - claim[1] <= cls.TILE_CLAIM_TTL
            ):
                continue
            seen = cls.explored.get(tile)
            if seen is None:
                stale = 1.0
            else:
                stale = min(1.0, (now - seen) / cls.EXPLORE_TTL)
            if stale < 0.3:
                continue
            centre = cls.tileCentres[tile]
            d = self.torusManhattan(pos, centre)
            if d < 8:
                continue
            score = fert * fert * stale / (d + 24.0)
            if score > bestScore:
                rec = cls.danger.get(tile)
                if rec is not None and now - rec[0] <= cls.DANGER_TTL:
                    continue
                best, bestScore = tile, score
        return best

    def walk(self, target):
        """walk with everything I have; a turn's refill is 25, so time
        kept beyond that would be lost anyway"""
        return self.stepTowards(target, self.time() // self.moveCost)

    def act(self):
        cls = type(self)
        pos = self.position()
        if self.time() < self.moveCost:
            return
        if self.goal is not None:
            if self.torusDist(pos, self.goal) <= 4:
                if self.goalKind == "site":
                    self.anchor = self.goal
                    self.lastBite = cls.worldTurn
                self.goal = None
                self.goalKind = None
            else:
                # walking to a site or a tile; still eat what is under
                # my feet on the way
                self.walk(self.goal)
                return
        target = self.chooseTarget()
        if target is not None:
            cls.claims[target] = (self.uid, cls.worldTurn)
            self.tell("k", (target[0], target[1], self.uid, cls.worldTurn))
            self.walk(target)
            if (
                (self.position()[0], self.position()[1]) == target
                and self.time() >= self.eatCost + self.closerLookCost
            ):
                # arrived: ids from this turn's view are still valid, but
                # a far target was never in it
                if not any(
                    (f["position"][0], f["position"][1]) == target
                    for f in self.foods
                ):
                    self.noteView(self.closerLook())
                else:
                    p = self.position()
                    self.foodsHere = [
                        f for f in self.foods if f["position"] == p
                    ]
                    self.foodsHere.sort(key=lambda f: -f["energy"])
                self.grazeHere()
            return
        settled = (
            self.anchor is not None
            and cls.worldTurn - self.lastBite <= cls.REANCHOR_AFTER
        )
        if settled and self.maybePlant():
            return
        if not settled:
            self.anchor = None
        # nothing worth a bite is known: idling wastes the turn's time,
        # so look at the nearest stale tile (the map brings me back to
        # my cells once they have regrown)
        tile = self.chooseTile()
        if tile is None:
            return
        cls.tileClaims[tile] = (self.uid, cls.worldTurn)
        self.tell("x", (tile[0], tile[1], cls.worldTurn))
        self.goal = cls.tileCentres[tile]
        self.goalKind = "explore"
        cls.count("explore")
        self.walk(self.goal)

    def localDensity(self, pos):
        """food energy within range.seed of pos, over maxamount (what the
        food rule calls density), from the map"""
        total = 0.0
        r = self.seedRange
        for cell, entry in self.cellsNear(pos, r):
            if self.torusDist(pos, cell) <= r:
                total += self.estimate(entry)
        return total / self.maxamount

    def maybePlant(self):
        """a seed on fertile empty ground where it can grow"""
        cls = type(self)
        if not cls.PLANT or self.time() < self.vomitCost:
            return False
        if self.foodsHere or self.enemies:
            return False
        if self.energy() < self.reserve() + cls.PLANT_MARGIN:
            return False
        pos = self.position()
        if self.fertility() < cls.PLANT_MIN_FERTILITY:
            return False
        density = self.localDensity(pos)
        if (
            density > cls.PLANT_MAX_DENSITY
            or density < cls.PLANT_MIN_DENSITY
        ):
            return False
        seed = self.plantEnergy()
        if not self.Vomit(seed):
            return False
        self.mapSet((pos[0], pos[1]), seed)
        cls.count("plants")
        return True

    # --- the turn --------------------------------------------------------

    def main(self):
        try:
            self.turn()
        except RuleException:
            raise
        except Exception as exc:  # never crash the whole game
            if STRICT:
                raise
            msg = f"{type(exc).__name__}: {exc}"
            if msg not in type(self).reported:
                type(self).reported.add(msg)
                print("Weatherwax: internal error, turn skipped:", msg)

    def turn(self):
        self.tick()
        if self.turnsLived == 1:
            self.takeOrders()
        pos = self.position()
        view = self.closerLook()
        self.noteView(view)
        if self.time() >= self.lookCost:
            self.noteLook(self.look())
        self.sayWhatISaw()
        if self.parent is not None:
            # born only to cure the parent's old age: give everything
            # back (which ends me) if the parent is still here
            if any(
                o["id"] == self.parent
                for o in view
                if o["type"] == "wesen" and o["position"] == pos
            ):
                if self.Donate(self.energy(), self.parent):
                    return
            self.parent = None
        if self.handleDanger():
            return
        self.killThieves()
        self.grazeHere()
        self.maybeReproduce()
        if self.hold > 0:
            self.hold -= 1
            return
        self.act()
