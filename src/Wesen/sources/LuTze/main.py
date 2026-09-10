"""LuTze - the Sweeper. Wins on time, because time is all anyone has.

Lu-Tze of the History Monks knows that the only thing anybody on the Disc
ever runs out of is time. In Wesen every wesen gets 25 time per turn, a
food patch grows by 0.5 energy per turn whatever its size, and the score
is the energy of living bodies. That gives three rules.

Rule One: reach the patch budget before the others have started.
    ``Vomit(1)`` patches on the founders' cells ("treasuries") are the
    income, exactly as for Vetinari and Weatherwax. But a patch pays for
    itself in two turns, so each founder splits into eight tiny gardeners
    on turn 3 and the colony holds its whole budget (``PATCH_BUDGET``
    food objects) by turn ~60 instead of turn ~500. From then on income is
    0.5 x budget per turn; four gardeners per cell keep the patches
    cycling into bodies, so patches stay small and nobody wants them.

Rule Two: the surplus wesen are the army, and the war is over early.
    Scouts sweep the map on a tile grid with cheap ``look()`` calls and
    register enemy home cells (piles of food with a Vetinari or Weatherwax
    on them) and roaming enemies. Both gardening opponents flee three
    cells from any enemy that could kill them and walk back when it is
    out of range, forever, without gardening or reproducing. A hunter with
    1.4 x their energy on their home cell paralyses the cell, and kills
    the residents one by one: step next to a resident, let it flee its
    three cells along one axis, then walk four and strike (the chase
    converges because a three-cell move costs less than a turn's time).
    Their colonies are still five cells at turn 100 and the residents
    have less than 1000 energy, so a kill costs a few hundred energy and
    removes a wesen that would have earned 20-25 per turn for the rest of
    the game and multiplied. Dwarf, Nightwatch and the rest never flee and
    are hunted when cheap; anything that steps on a treasury is killed by
    the gardeners if the kill is affordable.

Rule Three: do not act incautiously.
    Bodies at home stay above what a Dwarf or Nightwatch would attack
    (they only attack wesen up to their own energy + 300/375), hunters are
    only dispatched when the home cell can pool the energy the target
    needs, and a hunter that meets something it cannot kill walks away.

The budget (3000 food objects) is below what Weatherwax and Vetinari
together keep in a full-field game (~3500 at turn 200-400), so a game with
LuTze is not slower than one without; income is linear in the budget.

``WESEN_STRICT=1`` in the environment makes internal errors crash the game
(development); by default the failing turn is skipped and the error is
printed once.
"""

import os
from random import choice

from ...colony import Colony
from ...defaultwesensource import DefaultWesenSource
from ...objects.wesen import RuleException
from ...point import getShortestTranslation

STRICT = bool(os.environ.get("WESEN_STRICT"))

# sources with a flight reflex: they flee 3 cells from killers this close
FLEE_RADIUS = {"Vetinari": 6, "Weatherwax": 5}
# sources that hunt wesen once they have the first energy, attacking any
# wesen up to their own energy + the second (they strike on arrival)
CHASERS = {"Dwarf": (301, 300), "Nightwatch": (375, 375)}
# energy per turn an untouched resident of a garden source gains
GROWTH = {"Vetinari": 25, "Weatherwax": 8}


class WesenSource(DefaultWesenSource):
    # --- shared knowledge of the whole colony (class attributes) ---------
    worldTurn = 0  # estimate of the current world turn
    alive = {}  # own uid -> last world turn seen
    ledger = {}  # own uid -> {energy, cell, turn, role, phase, home}
    homes = {}  # treasury cell -> {"recruit": {..}|None, "founded": turn}
    sightings = {}  # enemy id -> {pos, source, energy, turn, hunter uid}
    estates = {}  # enemy garden cell -> registry entry (see noteEstate)
    explored = {}  # scouting tile -> turn it was last looked at
    claims = {}  # tile -> (scout uid, turn)
    aggressorMax = 0  # strongest Dwarf/Nightwatch seen recently
    aggressorSeenTurn = 0
    reported = set()  # exception messages already printed
    stats = {}  # debug counters: hunts, strikes, aborts by reason
    moves = {}  # abandoned home cell -> new home cell

    # --- tunables --------------------------------------------------------
    PATCH_BUDGET = 3000  # food objects the whole colony keeps
    PILE_MIN = 5  # food objects on one cell that mark a garden
    BOOT_CHILD = 30  # founders split while a child would get this much
    BOOT_PER_CELL = 8  # gardeners per cell during the bootstrap
    HOME_MEMBERS = 4  # gardeners kept per cell afterwards
    DISTRICT_RANGE = 60  # how far from home the ground we keep reaches
    WESEN_PER_DISTRICT = 4  # ... and how many of us it feeds
    CHILD_MIN = 120  # energy a replacement gardener is born with
    MAX_COLONY = 64
    MIN_COLONY = 16  # below this, old-age children stay instead of dying
    RESERVE = 4  # never plant below this energy
    EAT_BELOW = 10  # bootstrap: eat when below ...
    EAT_TARGET = 24  # ... until above
    HARVEST_MIN = 10  # rolling harvest only of patches this rich
    KEEP_BASE = 600  # body a gardener keeps before donating
    POOL_KEEP = 100  # ... while a recruit is pooling on the cell
    POOL_EATS = 3  # patches a gardener harvests per turn for a recruit
    NEIGHBOUR_RANGE = 60  # a stationed hunter splits for estates this near
    AGGRESSOR_CAP = 2500  # reserves never chase a single monster
    AGGRESSOR_DECAY = 300
    KILL_MAX = 4000  # never pay more than this (0.5 x victim) for a kill
    KILL_FLOOR = 100  # and keep at least this after the strike
    OLD_AGE_MARGIN = 4  # reproduce this many turns before maxage
    FOREIGN_MIN = 15  # foreign food worth eating with spare time
    # scouting
    TILE = 48  # tile edge; look() covers 49 cells around the centre
    SCOUT_ENERGY = 200  # provisions a scout eats before leaving
    SCOUT_PROVISION_TURNS = 4  # ... for at most this many turns
    SCOUT_KEEP = 2  # gardeners that must stay at home
    SCOUTS_MAX = 24
    SIGIL = "lutze/1"  # our messages, and nobody else's
    SAY_EVERY = 4  # turns between two broadcasts with nothing new
    HEARD_TTL = 30  # turns a colleague counts as alive after its last word
    CLAIM_TTL = 40  # a tile claim expires after this many turns
    DETOUR_MAX = 8  # turns spent identifying a distant wesen
    # hunting
    BULK = 300  # what a resident can eat from its garden as we come
    NEED_MARGIN = 400
    CHASER_MARGIN = 450  # stay this much above Dwarf/Nightwatch targets
    POOL_TIMEOUT = 120  # give up pooling after this many turns
    KILL_RESERVE = 2  # kills a hunter is financed for beyond paralysing
    STALE = 40  # no resident seen for this long -> estate dead
    LOST = 8  # turns a roaming target may be out of sight
    SIGHTING_TTL = 80
    MAX_TRIP = 300  # manhattan distance a hunter travels for a target
    TRIP_SLACK = (
        1.25  # a cell only takes targets it is (nearly) nearest to
    )
    MIN_GARDENERS = 3  # a cell keeps this many gardeners when dispatching
    CAMP_TURNS = 12  # an unbeatable enemy at home this long -> relocate
    RELOCATE_DISTANCE = 30
    GARDEN_MIN = 1  # strip a dead estate's garden completely ...
    GARDEN_TURNS = 200  # ... for at most this long
    GARDEN_TARGET = 100  # abandoned gardens this rich get a hunter
    GLEAN_MIN = 30  # foreign food a patrolling scout detours for
    GLEAN_RANGE = 4
    PATROL_AGE = 200  # tiles are looked at again after this many turns
    PATROLS = 4  # scouts kept once the map has been swept
    DISPATCH_EVERY = 5
    DANGER_DISTANCE = 8  # thin wesen avoid chasers from this distance

    lifeTuned = False  # set once the class is tuned for food.rule=life

    @classmethod
    def tuneForFoodRule(cls, me):
        """Under the life food rule (objects/food.py) a Vomit(1) patch
        barely grows and a crowded garden decays, so the estate is a base
        for grazing wild food nearby in bites that leave it alive, not a
        plantation. Thresholds are derived from the food config."""
        if cls.lifeTuned or me.foodRule() != "life":
            return
        cls.lifeTuned = True
        sustainable = me.foodRoots() + (me.foodBite() or 0) + 1
        cls.BOOT_PER_CELL = cls.HOME_MEMBERS
        cls.BOOT_CHILD = cls.CHILD_MIN
        cls.HARVEST_MIN = sustainable
        cls.FOREIGN_MIN = sustainable
        cls.GLEAN_MIN = sustainable
        # upkeep is proportional to the body, so a thin wesen is cheap
        # to run and many mouths capture more pasture than few fat ones
        cls.KEEP_BASE = 400

    LIFE_CAP = 2  # patches per treasury under the life rule
    grazeClaims = {}  # food id -> world turn a gardener went for it

    def __init__(self, infoAllSource):
        DefaultWesenSource.__init__(self, infoAllSource)
        type(self).tuneForFoodRule(self)
        self.role = None  # gardener | scout | hunter | sacrifice
        # scout: provision|sweep; hunter: pool|travel|station|chase|home
        self.phase = None
        self.home = None
        self.target = (
            None  # hunter: {"kind": "estate"|"wesen", "cell", "id"}
        )
        self.tile = None
        self.detour = None
        self.detourSince = 0
        self.glean = None
        self.gleanSince = 0
        self.parent = None
        self.since = 0
        self.lastSeen = 0
        self.waitTurns = 0  # stand still for a sacrifice child
        self.uid = None
        # the colony's book, kept by talking: class attributes are
        # genetic information now (see isolation.py), so the roll, the
        # estates and the homes below are this wesen's own and reach the
        # others only if somebody broadcasts them
        self.colony = Colony(
            type(self).SIGIL, self.worldlength, 80, source=self.source
        )
        self.news = {}
        self.said = -99
        self.inbox = None  # orders talked to us at birth
        self.bornTurn = type(self).worldTurn
        self.turnsLived = 0
        self.maxAge = self.infoWesen["maxage"]
        t = self.infoTime
        self.plantCost = t["vomit"]
        self.eatCost = t["eat"]
        self.moveCost = t["move"]
        self.attackCost = t["attack"]
        self.reproCost = t["reproduce"]
        self.donateCost = t["donate"]
        self.lookCost = t["closerlook"]
        self.cheapLookCost = t["look"]
        # per-turn view classification
        self.foodsHere = []
        self.foodsByCell = {}
        self.foodEnergyByCell = {}
        self.enemies = []
        self.enemiesHere = []
        self.friendsHere = []
        self.lethal = set()
        self.killed = set()

    def __str__(self):
        return "<Lu-Tze, the Sweeper>"

    # --- persistence -----------------------------------------------------

    def persist(self):
        return {
            "role": self.role,
            "phase": self.phase,
            "home": self.home,
            "target": self.target,
            "uid": self.uid,
            "colony": self.colony.persist(),
        }

    def restore(self, obj):
        state = obj.get("wesensource", {}) or {}
        for key in ("role", "phase", "home", "target", "uid"):
            setattr(self, key, state.get(key, getattr(self, key)))
        self.colony.restore(state.get("colony"), uidType=str)
        self.colony.uid = self.uid
        if self.home is not None:
            self.home = list(self.home)
            self.registerHome(self.home)
        if self.role == "sacrifice":
            self.role = "gardener"
        if self.role == "hunter":
            if self.phase == "pool":
                # the pooling recruit table is not persisted: start over
                self.role = "gardener"
                self.target = None
                self.phase = None
            elif self.target is None:
                self.phase = "home"
            else:
                self.assignTarget(self.target)

    # --- bookkeeping -----------------------------------------------------

    def tick(self):
        cls = type(self)
        self.turnsLived += 1
        if self.uid is None:
            # engine ids are addresses and get reused, and a shared
            # counter would be a shared brain: a name is the address and
            # the turn it was issued. A newborn takes the name its
            # parent dispatched it under, which is the same formula
            order = self.inbox or {}
            self.uid = order.get("uid") or f"{self.id():x}:{self.bornTurn}"
            self.colony.uid = self.uid
        self.colony.tick()
        self.colony.sync(self.bornTurn + self.turnsLived)
        cls.worldTurn = self.colony.clock
        now = cls.worldTurn
        self.colony.note(
            self.uid, self.home or self.position(), self.energy()
        )
        cls.alive[self.uid] = now
        pos = self.position()
        cls.ledger[self.uid] = {
            "energy": self.energy(),
            "cell": (pos[0], pos[1]),
            "turn": now,
            "role": self.role,
            "phase": self.phase,
            "home": tuple(self.home) if self.home else None,
        }
        if self.turnsLived % 25 == 0:
            self.colony.forget()
            # a colleague counts as alive while its last word is fresh:
            # we hear from it every few turns, not every turn
            cutoff = now - cls.HEARD_TTL
            cls.alive = {k: v for k, v in cls.alive.items() if v >= cutoff}
            cls.ledger = {
                k: v for k, v in cls.ledger.items() if k in cls.alive
            }
            for e in cls.estates.values():
                if (
                    e["hunter"] is not None
                    and e["hunter"] not in cls.alive
                ):
                    e["hunter"] = None
            cls.sightings = {
                k: v
                for k, v in cls.sightings.items()
                if now - v["turn"] <= cls.SIGHTING_TTL
            }
            for s in cls.sightings.values():
                if (
                    s["hunter"] is not None
                    and s["hunter"] not in cls.alive
                ):
                    s["hunter"] = None
            for h in cls.homes.values():
                rc = h.get("recruit")
                if rc is not None and rc["uid"] not in cls.alive:
                    h["recruit"] = None
            cls.claims = {
                k: v
                for k, v in cls.claims.items()
                if v[0] in cls.alive and now - v[1] <= cls.CLAIM_TTL
            }

    def roomForAnother(self):
        """local carrying capacity: how many of us already live off the
        ground around my home.

        This replaces a count of the whole colony against a fixed cap.
        That count cannot be had honestly once a class attribute is
        genetic information (see isolation.py): nobody ever hears the
        whole roll, so every wesen under-counts the colony and concludes
        on its own that there is room for one more. The ground a wesen
        keeps is something it can measure for itself, from the homes it
        has heard about, and it stops the colony growing *where it is
        full* while the empty ground is still filling."""
        cls = type(self)
        if self.colonySize() >= cls.MAX_COLONY:
            # a ceiling for the machine rather than for the game: every
            # wesen costs the simulation time, and the estimate is only
            # ever good enough to catch a runaway
            return False
        home = self.home or self.position()
        near = len(self.colony.near(home, cls.DISTRICT_RANGE))
        return near < cls.WESEN_PER_DISTRICT

    def colonySize(self):
        """estimated from how closely the colleagues we have heard from
        stand: nobody hears the whole colony (see colony.py)"""
        return self.colony.census(self.position())

    def sayWhatISaw(self):
        """one broadcast a turn: who and where I am, what I am doing,
        and the estates, sightings and claims I have learned of.

        This is what used to be a class attribute the whole colony
        wrote into. It costs 1 time and it is the only thing that makes
        the dispatching below work at all."""
        cls = type(self)
        if self.time() < self.infoTime["broadcast"]:
            return
        stale = cls.worldTurn - self.said
        if not self.news and stale < cls.SAY_EVERY:
            return
        news = self.news
        self.news = {}
        self.said = cls.worldTurn
        entry = cls.ledger.get(self.uid)
        if entry is not None:
            news["me"] = [
                entry["energy"],
                entry["cell"][0],
                entry["cell"][1],
                entry["turn"],
                entry["role"] or "",
                entry["phase"] or "",
                list(entry["home"]) if entry["home"] else None,
            ]
        self.Broadcast(
            self.colony.say(
                self.position(), self.energy(), news, self.role or ""
            )
        )

    def tell(self, kind, item):
        self.news.setdefault(kind, []).append(item)

    def Receive(self, message):
        """a colleague's word, or orders from a parent at birth"""
        cls = type(self)
        if not isinstance(message, dict) or message.get("s") != cls.SIGIL:
            return
        if not self.fromColleague(message):
            # the engine's own note of who sent it. Without this, the
            # sigil below says only what a stranger chose to claim
            return
        if message.get("to") is not None:
            if message["to"] == self.id():
                self.colony.sync(int(message.get("t", 0)))
                self.bornTurn = self.colony.clock
                self.inbox = {k: v for k, v in message["o"].items()}
            return
        news = self.colony.hear(message)
        if news is None:
            return
        uid = message.get("u")
        me = news.get("me")
        if uid is not None and me:
            energy, x, y, turn, role, phase, home = me
            old = cls.ledger.get(uid)
            if old is None or old["turn"] <= turn:
                cls.ledger[uid] = {
                    "energy": energy,
                    "cell": (x, y),
                    "turn": turn,
                    "role": role or None,
                    "phase": phase or None,
                    "home": tuple(home) if home else None,
                }
                cls.alive[uid] = turn
        for x, y, founded in news.get("h", ()):
            cls.homes.setdefault(
                (x, y), {"recruit": None, "founded": founded}
            )

    @classmethod
    def count(cls, key, n=1):
        cls.stats[key] = cls.stats.get(key, 0) + n

    def setRole(self, role, phase=None):
        """change role; keep the shared ledger current within the turn"""
        self.role = role
        self.phase = phase
        entry = type(self).ledger.get(self.uid)
        if entry is not None:
            entry["role"] = role
            entry["phase"] = phase

    def cellMembers(self, cell, role="gardener"):
        """own wesen of that home cell currently in that role"""
        cls = type(self)
        cell = tuple(cell)
        fresh = cls.worldTurn - 1
        return sum(
            1
            for v in cls.ledger.values()
            if v["home"] == cell
            and v["role"] == role
            and v["turn"] >= fresh
        )

    def countRole(self, role):
        cls = type(self)
        fresh = cls.worldTurn - 1
        return sum(
            1
            for v in cls.ledger.values()
            if v["role"] == role and v["turn"] >= fresh
        )

    def registerHome(self, cell):
        cls = type(self)
        key = (cell[0], cell[1])
        if key not in cls.homes:
            cls.homes[key] = {"recruit": None, "founded": cls.worldTurn}
            # where the colony keeps house is worth saying: it is what
            # the budget per cell and the dispatching are divided by
            self.tell("h", (key[0], key[1], cls.worldTurn))
        return cls.homes[key]

    def cellCap(self):
        cls = type(self)
        if cls.lifeTuned:
            return cls.LIFE_CAP
        return cls.PATCH_BUDGET // max(1, len(cls.homes))

    def takeOrders(self):
        cls = type(self)
        order = self.inbox or {}
        self.inbox = None
        self.role = order.get("role", "gardener")
        self.home = order.get("home")
        self.parent = order.get("parent")
        self.target = order.get("target")
        self.phase = order.get("phase")
        self.lastSeen = cls.worldTurn
        if self.home is None:
            self.home = list(self.position())
        else:
            self.home = list(self.home)
        self.registerHome(self.home)
        self.since = cls.worldTurn

    # --- life food rule: herding -----------------------------------------
    # With food.rule = life the pasture, not a plantation, is the income:
    # a bite that leaves a cell at least half grown regrows fastest, and a
    # crowded garden decays. So a "gardener" herds instead of planting.

    GRAZE_RANGE = 12  # cells worth walking to for better pasture
    GRAZE_FLOOR = 0.35  # share of maxamount a bitten cell should keep
    GRAZE_STARVING = 60  # below this, even a bite that kills the cell

    def grazeFloor(self):
        """energy a bitten cell should keep. Growth is proportional to
        energy times the room left to grow, so a cell held around a
        third of its maximum regrows nearly as fast as it possibly can,
        while a cell stripped to its roots hardly grows at all."""
        return int(self.infoFood["maxamount"] * type(self).GRAZE_FLOOR)

    def worthBiting(self, food):
        """a bite that leaves the cell productive is free income and is
        always taken; a bite that leaves it alive but bare is taken only
        while we are below our winter reserve; the last bite of a cell
        only when starving"""
        left = food["energy"] - self.foodYield(food)
        if left >= self.grazeFloor():
            return True
        if left > self.foodRoots():
            return self.energy() < self.winterReserve()
        return self.energy() < type(self).GRAZE_STARVING

    def bite(self, food):
        """take one bite and keep the (now smaller) food in the local
        view, so a rich cell can be bitten more than once per turn"""
        taken = self.foodYield(food)
        gone = self.foodKills(food)
        if not self.eat(food):
            return 0
        if not gone:
            food["energy"] -= taken
            self.foodsHere.append(food)
            self.foodsHere.sort(key=lambda f: -f["energy"])
        return taken

    def grazeHere(self):
        """eat from my own cell: ripe food always (that bite leaves the
        cell where it regrows fastest), smaller bites while hungry, and
        the last of a cell only when starving"""
        while self.foodsHere and self.time() >= self.eatCost:
            food = self.foodsHere[0]
            if food.get("id") is None:
                break
            if not self.worthBiting(food):
                break
            if not self.bite(food):
                break

    def grazeWant(self):
        """energy a cell needs before a bite leaves it productive"""
        return self.grazeFloor() + (self.foodBite() or 0)

    def distantPasture(self):
        """Where food is at all, when nothing worth biting is within
        closerLook range. The wide look() costs less time and reports no
        energies, but in a sparse world knowing *where* the pasture is
        matters more than knowing how rich it is."""
        cls = type(self)
        if self.time() < self.infoTime["look"] + self.moveCost:
            return None
        pos = self.position()
        # closerLook has already judged everything nearby and found
        # nothing worth biting, so only food beyond that range is news;
        # heading for a neighbouring cell we just refused would loop
        near = self.infoRange["closer_look"]
        best, bestDist = None, None
        for o in self.look():
            if o["type"] != "food":
                continue
            key = (o["position"][0], o["position"][1])
            if key in self.grazedCells() or key in self.lethal:
                continue
            d = self.viewDist(o["position"], pos)
            if d <= near or d > cls.GRAZE_RANGE * 2:
                continue
            if bestDist is None or d < bestDist:
                best, bestDist = o, d
        return list(best["position"]) if best else None

    def bestPasture(self):
        """the cell in view worth walking to. Cells rich enough for a
        bite that leaves them productive come first, by energy per step;
        a poorer one is only a destination while we are hungry, since
        walking to a cell we then refuse to bite wastes the turn."""
        cls = type(self)
        pos = self.position()
        want = self.grazeWant()
        best, bestValue = None, 0.0
        poor, poorValue = None, 0.0
        for o in self.foodsAway:
            key = (o["position"][0], o["position"][1])
            if key in self.lethal or key in self.grazedCells():
                continue
            d = self.viewDist(o["position"], pos)
            if d < 1 or d > cls.GRAZE_RANGE:
                continue
            value = o["energy"] / d
            if o["energy"] >= want:
                if value > bestValue:
                    best, bestValue = o, value
            elif value > poorValue:
                poor, poorValue = o, value
        if best is None and self.energy() < type(self).GRAZE_STARVING:
            best = poor
        return list(best["position"]) if best else None

    def winterReserve(self):
        """body that carries this wesen to spring at its own burn rate.
        Splitting below twice this means both halves starve in winter."""
        base = self.grazeKeep()
        return base + int(self.upkeepOf(base) * self.turnsUntilSpring())

    def grazeKeep(self):
        return self.keep()

    def grazedCells(self):
        return type(self).homes

    def claimPasture(self, pos):
        """this cell feeds me, so the treasury moves here. No entry in
        cls.moves: a grazer's cell is its own, nobody has to follow."""
        cls = type(self)
        cell = (pos[0], pos[1])
        if cell == tuple(self.home):
            return
        previous = tuple(self.home)
        fresh = cls.worldTurn - 1
        others = sum(
            1
            for uid, v in cls.ledger.items()
            if v["home"] == previous
            and uid != self.uid
            and v["turn"] >= fresh
        )
        if not others:
            cls.homes.pop(previous, None)
        self.home = list(pos)
        self.registerHome(self.home)

    def keep(self):
        """body a gardener keeps: above what a Dwarf/Nightwatch attacks"""
        cls = type(self)
        threat = min(cls.aggressorMax, cls.AGGRESSOR_CAP)
        if cls.worldTurn - cls.aggressorSeenTurn > cls.AGGRESSOR_DECAY:
            threat = 0
        return max(cls.KEEP_BASE, int(1.4 * threat) + 100)

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

    def safeStep(self, steps, force=False):
        """first candidate step that does not end on a cell holding an
        enemy able to kill me (unless force)"""
        if force:
            return steps[0] if steps else None
        pos = self.position()
        length = self.worldlength
        for step in steps:
            nxt = (
                (pos[0] + step[0]) % length,
                (pos[1] + step[1]) % length,
            )
            if nxt not in self.lethal:
                return step
        return None

    def stepTowards(self, target, maxCells, force=False):
        """move up to maxCells cells towards target, axis-aligned,
        torus aware; returns the number of cells moved"""
        moved = 0
        target = list(target)
        while moved < maxCells and self.time() >= self.moveCost:
            pos = self.position()
            if pos == target:
                break
            dx, dy = getShortestTranslation(pos, target, self.worldlength)
            steps = []
            if dx:
                steps.append([1 if dx > 0 else -1, 0])
            if dy:
                steps.append([0, 1 if dy > 0 else -1])
            if abs(dy) > abs(dx):
                steps.reverse()
            step = self.safeStep(steps, force)
            if step is None or not self.Move(step):
                break
            moved += 1
        return moved

    def stepAway(self, fromPos, maxCells):
        pos = self.position()
        dx, dy = getShortestTranslation(pos, fromPos, self.worldlength)
        if dx == 0 and dy == 0:
            dx, dy = choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
        steps = [[-1 if dx > 0 else 1, 0], [0, -1 if dy > 0 else 1]]
        if abs(dy) > abs(dx):
            steps.reverse()
        moved = 0
        while moved < maxCells and self.time() >= self.moveCost:
            step = self.safeStep(steps)
            if step is None or not self.Move(step):
                break
            moved += 1
        return moved

    def nearestHome(self, pos):
        cls = type(self)
        best = None
        for cell in cls.homes:
            d = self.torusManhattan(pos, cell)
            if best is None or d < best[0]:
                best = (d, cell)
        return list(best[1]) if best else None

    # --- eating / fighting helpers ---------------------------------------

    def eat(self, food):
        if self.time() < self.eatCost or food.get("id") is None:
            return False
        ok = self.Eat(food["id"])
        if food in self.foodsHere:
            self.foodsHere.remove(food)
        return ok

    def harvestUntil(self, targetEnergy, minPatch=2):
        """eat the richest food on my cell until energy >= target"""
        while (
            self.foodsHere
            and self.energy() < targetEnergy
            and self.time() >= self.eatCost
        ):
            if self.foodsHere[0]["energy"] < minPatch:
                break
            if not self.eat(self.foodsHere[0]):
                break

    def canKill(self, enemyEnergy):
        mine = self.energy()
        if 0.75 * mine < enemyEnergy:
            return False
        return mine - 0.5 * enemyEnergy > type(self).KILL_FLOOR

    def canKillMe(self, enemyEnergy):
        return 0.75 * enemyEnergy >= self.energy()

    def strike(self, e):
        """attack an enemy on my cell (once per id per turn)"""
        if e["id"] in self.killed or self.time() < self.attackCost:
            return False
        self.Attack(e["id"])
        self.killed.add(e["id"])
        self.count("strikes")
        self.count("strike_" + e["source"])
        type(self).sightings.pop(e["id"], None)
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
                print("LuTze: internal error, turn skipped:", msg)

    def turn(self):
        self.tick()
        self.sayWhatISaw()
        if self.role is None:
            self.takeOrders()
        view = self.closerLook()
        if not view and self.time() < self.lookCost:
            return
        self.classify(view)
        self.noteEnemies()
        if self.role == "sacrifice":
            if any(f["id"] == self.parent for f in self.friendsHere):
                if self.Donate(self.energy(), self.parent):
                    return
            self.setRole("gardener")
        if self.handleDanger():
            return
        if self.role == "scout":
            if self.age() >= self.maxAge - self.OLD_AGE_MARGIN:
                self.retireScout(self.nearestHome(self.position()))
                self.gardenerTurn()
                return
            self.scoutTurn()
        elif self.role == "hunter":
            self.hunterTurn()
        else:
            self.gardenerTurn()

    def classify(self, view):
        pos = self.position()
        here = (pos[0], pos[1])
        self.foodsHere = []
        self.foodsAway = []  # wild food in view (life rule: grazing)
        self.enemies = []
        self.enemiesHere = []
        self.friendsHere = []
        self.lethal = set()
        self.killed = set()
        byCell = {}
        energyByCell = {}
        for o in view:
            opos = o["position"]
            key = (opos[0], opos[1])
            if o["type"] == "food":
                byCell[key] = byCell.get(key, 0) + 1
                energyByCell[key] = energyByCell.get(key, 0) + o["energy"]
                if key == here:
                    self.foodsHere.append(o)
                else:
                    self.foodsAway.append(o)
            elif o["source"] == self.source:
                if key == here:
                    self.friendsHere.append(o)
            else:
                self.enemies.append(o)
                if key == here:
                    self.enemiesHere.append(o)
                if self.canKillMe(o["energy"]):
                    self.lethal.add(key)
        self.foodsHere.sort(key=lambda f: f["energy"], reverse=True)
        self.foodsByCell = byCell
        self.foodEnergyByCell = energyByCell

    # --- enemy registry --------------------------------------------------

    def noteEnemies(self):
        cls = type(self)
        now = cls.worldTurn
        pos = self.position()
        for e in self.enemies:
            src = e["source"]
            epos = e["position"]
            key = (epos[0], epos[1])
            if src in CHASERS and (
                e["energy"] >= cls.aggressorMax
                or now - cls.aggressorSeenTurn > cls.AGGRESSOR_DECAY
            ):
                cls.aggressorMax = e["energy"]
                cls.aggressorSeenTurn = now
            if src in FLEE_RADIUS:
                est = cls.estates.get(key)
                onPile = self.foodsByCell.get(key, 0) >= cls.PILE_MIN
                if onPile or (
                    est is not None and est["source"] in (None, src)
                ):
                    self.noteEstate(key, src, e)
                    continue
                near = self.nearestEstate(key, src, 10)
                if near is not None:
                    near["seen"] = now
                    near["dead"] = False
                    if e["energy"] > near["rmax"]:
                        near["rmax"] = e["energy"]
                    continue
            self.noteSighting(e)
        # estates in view without residents grow stale and die
        for cell, est in cls.estates.items():
            if self.viewDist(cell, pos) > 12:
                continue
            est["checked"] = now
            est["garden"] = self.foodEnergyByCell.get(cell, 0)
            if est["source"] is None and now - est["seen"] > 2:
                est["dead"] = True  # a pile nobody of interest stands on
            elif now - est["seen"] > cls.STALE:
                est["dead"] = True

    def noteEstate(self, key, src, e):
        cls = type(self)
        now = cls.worldTurn
        est = cls.estates.get(key)
        if est is None:
            est = {
                "source": src,
                "rmax": 0,
                "rsum": 0,
                "count": 0,
                "garden": 0,
                "seen": now,
                "checked": now,
                "hunter": None,
                "dead": False,
                "turn": None,
                "residents": {},
            }
            cls.estates[key] = est
        est["source"] = src
        est["dead"] = False
        est["seen"] = now
        est["checked"] = now
        est["garden"] = self.foodEnergyByCell.get(key, 0)
        if est["turn"] != now:
            est["turn"] = now
            est["residents"] = {}
        est["residents"][e["id"]] = e["energy"]
        est["rmax"] = max(est["residents"].values())
        est["rsum"] = sum(est["residents"].values())
        est["count"] = len(est["residents"])
        return est

    def suspectEstate(self, key):
        """a pile seen with look(): somebody's garden, residents unknown"""
        cls = type(self)
        if key in cls.estates or key in cls.homes:
            return
        cls.estates[key] = {
            "source": None,
            "rmax": 0,
            "rsum": 0,
            "count": 0,
            "garden": 0,
            "seen": cls.worldTurn,
            "checked": 0,
            "hunter": None,
            "dead": False,
            "turn": None,
            "residents": {},
        }

    def nearestEstate(self, key, src, maxDist):
        cls = type(self)
        best = None
        for cell, est in cls.estates.items():
            if est["dead"] or est["source"] != src:
                continue
            d = self.torusDist(key, cell)
            if d <= maxDist and (best is None or d < best[0]):
                best = (d, est)
        return best[1] if best else None

    def noteSighting(self, e):
        cls = type(self)
        old = cls.sightings.get(e["id"])
        cls.sightings[e["id"]] = {
            "pos": list(e["position"]),
            "source": e["source"],
            "energy": e["energy"],
            "turn": cls.worldTurn,
            "hunter": old["hunter"] if old else None,
        }

    def noteLook(self, lookView):
        """from a cheap look(): piles are gardens, wesen beyond
        closerLook range are worth a detour to identify"""
        cls = type(self)
        pos = self.position()
        counts = {}
        unknown = []
        for o in lookView:
            opos = o["position"]
            key = (opos[0], opos[1])
            if o["type"] == "food":
                counts[key] = counts.get(key, 0) + 1
            elif self.viewDist(opos, pos) > 12:
                unknown.append(key)
        for key, n in counts.items():
            if n >= cls.PILE_MIN:
                self.suspectEstate(key)
        return unknown

    # --- danger ----------------------------------------------------------

    def isFighter(self, e):
        rule = CHASERS.get(e["source"])
        return rule is not None and e["energy"] >= rule[0]

    def wouldAttack(self, e):
        """would this enemy attack me where it stands / on arrival?"""
        src = e["source"]
        mine = self.energy()
        if src == "Vetinari":
            return self.canKillMe(e["energy"])
        if src == "Weatherwax":
            return (
                self.canKillMe(e["energy"]) and mine <= e["energy"] + 375
            )
        rule = CHASERS.get(src)
        if rule is None:
            return False
        return e["energy"] >= rule[0] and mine <= e["energy"] + rule[1]

    def handleDanger(self):
        """returns True if the turn is over (we fled)"""
        cls = type(self)
        pos = self.position()
        atHome = self.home is not None and pos == self.home
        for e in sorted(self.enemiesHere, key=lambda e: e["energy"]):
            if e["id"] in self.killed:
                continue
            if self.canKill(e["energy"]) and self.worthKilling(
                e["energy"]
            ):
                self.strike(e)
                continue
            if not self.wouldAttack(e):
                continue
            if atHome:
                self.harvestUntil(int(e["energy"] / 0.75) + 50)
                if self.canKill(e["energy"]):
                    self.strike(e)
                    continue
                self.threatened(e)
            self.stepAway(e["position"], 3)
            self.count("flee_" + e["source"])
            return True
        # Dwarf / Nightwatch pick targets up to their own energy + margin
        # and strike on arrival: thin wesen keep out of their reach
        for e in self.enemies:
            if e["position"] == pos or e["source"] not in CHASERS:
                continue
            if not self.wouldAttack(e) or not self.canKillMe(e["energy"]):
                continue
            if self.viewDist(e["position"], pos) > cls.DANGER_DISTANCE:
                continue
            if atHome:
                self.harvestUntil(
                    e["energy"] + CHASERS[e["source"]][1] + 1
                )
                if not self.wouldAttack(e):
                    continue
            if (
                self.role == "gardener"
                and self.home is not None
                and (self.torusDist(pos, self.home) <= cls.DANGER_DISTANCE)
            ):
                self.threatened(e)
            self.stepAway(e["position"], 3)
            self.count("flee_" + e["source"])
            return True
        return False

    def threatened(self, e):
        """a gardener notes an enemy it cannot handle at its home"""
        cls = type(self)
        if self.role != "gardener" or self.home is None:
            return
        rec = cls.homes.get(tuple(self.home))
        if rec is None:
            return
        now = cls.worldTurn
        if rec.get("threatTurn", -100) < now - 10:
            rec["threatSince"] = now
        rec["threatTurn"] = now
        rec["threatEnergy"] = e["energy"]
        rec["threatPos"] = list(e["position"])

    def maybeRelocate(self, rec):
        """the home is camped by an enemy the cell cannot kill: move"""
        cls = type(self)
        now = cls.worldTurn
        if rec.get("threatTurn", -100) < now - 5:
            return False
        if now - rec.get("threatSince", now) < cls.CAMP_TURNS:
            return False
        cell = tuple(self.home)
        fresh = now - 1
        bodies = sum(
            v["energy"]
            for v in cls.ledger.values()
            if v["home"] == cell and v["turn"] >= fresh
        )
        if bodies >= rec["threatEnergy"] / 0.75 + 100:
            return False  # pooled into one wesen this cell can strike
        dx, dy = getShortestTranslation(
            rec["threatPos"], self.home, self.worldlength
        )
        if dx == 0 and dy == 0:
            dx, dy = choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
        norm = max(abs(dx), abs(dy))
        length = self.worldlength
        d = cls.RELOCATE_DISTANCE
        new = (
            int(round(self.home[0] + d * dx / norm)) % length,
            int(round(self.home[1] + d * dy / norm)) % length,
        )
        cls.homes.pop(cell, None)
        cls.homes[new] = {"recruit": None, "founded": now}
        self.tell("h", (new[0], new[1], now))
        cls.moves[cell] = new
        self.home = list(new)
        self.count("relocations")
        return True

    # --- gardener --------------------------------------------------------

    def grazerTurn(self):
        """the life-rule replacement for gardenerTurn: the treasury is a
        pasture, so gardeners graze around it and the cell drifts after
        the food. Scouts and hunters, which are dispatched from home
        cells, are untouched."""
        cls = type(self)
        pos = self.position()
        self.followHome()
        rec = self.registerHome(self.home)
        if self.maybeRelocate(rec):
            self.stepTowards(self.home, 3)
            return
        self.grazeHere()
        self.maybeReproduce(len(self.foodsHere), self.cellCap())
        if self.turnsLived % cls.DISPATCH_EVERY == 0 and self.maybeScout():
            return
        rc = rec.get("recruit")
        if rc is not None and rc["uid"] != self.uid:
            self.poolFor(rc)
            return
        if self.turnsLived % cls.DISPATCH_EVERY == 0 and self.maybeHunt():
            return
        if self.foodsHere and self.foodsHere[0]["energy"] >= (
            self.grazeWant()
        ):
            self.claimPasture(pos)
        if self.time() < self.moveCost:
            return
        target = self.bestPasture() or self.distantPasture()
        if target is None:
            # nothing in sight at all: move on, the world is large
            self.driftHome()
            target = self.home
        self.stepTowards(target, 3)
        if self.position() == list(target):
            self.claimPasture(self.position())

    def followHome(self):
        """a treasury that has moved takes its members with it"""
        cls = type(self)
        moved = cls.moves.get(tuple(self.home))
        hops = 0
        while moved is not None and hops < 50:
            self.home = list(moved)
            moved = cls.moves.get(tuple(self.home))
            hops += 1

    def gardenerTurn(self):
        cls = type(self)
        if cls.lifeTuned:
            return self.grazerTurn()
        pos = self.position()
        moved = cls.moves.get(tuple(self.home))
        hops = 0
        while moved is not None and hops < 50:
            self.home = list(moved)
            moved = cls.moves.get(tuple(self.home))
            hops += 1
        rec = self.registerHome(self.home)
        if self.maybeRelocate(rec):
            self.stepTowards(self.home, 3)
            return
        if getattr(self, "trip", None) is not None:
            if self.continueGraze():
                return
        if pos != self.home:
            self.stepTowards(self.home, 3)
            return
        cap = self.cellCap()
        plant = self.plantEnergy()
        patches = self.foodsHere  # richest first
        if self.energy() < cls.EAT_BELOW:
            self.harvestUntil(cls.EAT_TARGET)
        count = len(patches)
        self.maybeReproduce(count, cap)
        if self.turnsLived % cls.DISPATCH_EVERY == 0 and self.maybeScout():
            return
        rc = rec.get("recruit")
        if rc is not None and rc["uid"] != self.uid:
            # everybody on the cell harvests for the recruit
            self.poolFor(rc)
            self.plant(patches, cap)
            return
        if count < cap:
            # bootstrap / refill: all time into planting
            self.plant(patches, cap)
            if self.energy() < cls.EAT_BELOW:
                self.harvestUntil(cls.EAT_TARGET)
            self.startGraze()
            return
        if self.turnsLived % cls.DISPATCH_EVERY == 0 and self.maybeHunt():
            return
        # shrink after the cap dropped
        while (
            len(patches) > cap
            and self.time() >= self.eatCost
            and patches[0]["id"] is not None
            and patches[0]["energy"] >= 2
        ):
            if not self.eat(patches[0]):
                break
        # rolling cycle: richest into the body, replant in the same turn
        while (
            patches
            and len(patches) >= cap
            and self.time() >= self.eatCost + self.plantCost
            and patches[0]["id"] is not None
            and patches[0]["energy"] >= cls.HARVEST_MIN
        ):
            if not self.eat(patches[0]):
                break
            if not self.Vomit(plant):
                break
            patches.append({"energy": plant, "age": 0, "id": None})
        self.startGraze()

    # --- life food rule: grazing near home ----------------------------

    GRAZE_RANGE = 12  # cells (max metric) a gardener walks for a bite
    GRAZE_CLAIM_TURNS = 20  # before another gardener may go for it
    GRAZE_STARVING = 60  # below this energy any bite will do
    DRIFT_AFTER = 5  # turns without anything to graze -> move the estate
    DRIFT_DISTANCE = 12

    def startGraze(self):
        """life rule: wild food near home regrows after a bite that
        leaves it alive, so a gardener with spare time fetches the best
        bite in reach and walks back (like Vetinari's forage trips)."""
        cls = type(self)
        if not cls.lifeTuned:
            return False
        if self.time() < self.moveCost + self.eatCost:
            return False
        pos = self.position()
        now = cls.worldTurn
        best, bestValue = None, 0
        minEnergy = cls.FOREIGN_MIN
        if self.energy() < cls.GRAZE_STARVING:
            minEnergy = 1  # starving: even a bite that kills the food
        # the view from the start of the turn (ids stay valid this turn)
        for o in getattr(self, "foodsAway", []):
            if o["energy"] < minEnergy:
                continue
            key = (o["position"][0], o["position"][1])
            if key in cls.homes:
                continue
            claim = cls.grazeClaims.get(o["id"])
            if claim is not None and now - claim < cls.GRAZE_CLAIM_TURNS:
                continue
            d = self.viewDist(pos, o["position"])
            if d > cls.GRAZE_RANGE:
                continue
            value = self.foodYield(o) / d
            if value > bestValue:
                best, bestValue = o, value
        if best is None:
            self.grazeMiss = getattr(self, "grazeMiss", 0) + 1
            if self.grazeMiss >= cls.DRIFT_AFTER:
                self.grazeMiss = 0
                self.driftHome()
                self.stepTowards(self.home, 3)
            return False
        self.grazeMiss = 0
        cls.grazeClaims[best["id"]] = now
        if len(cls.grazeClaims) > 1000:
            cls.grazeClaims = {
                k: v
                for k, v in cls.grazeClaims.items()
                if now - v < cls.GRAZE_CLAIM_TURNS
            }
        self.trip = list(best["position"])
        self.stepTowards(self.trip, 3)
        return True

    def driftHome(self):
        """life rule: nothing to graze here for a while: move the estate
        (its members follow via cls.moves, as after a relocation) a dozen
        cells towards the richest wild food in view, else somewhere"""
        cls = type(self)
        now = cls.worldTurn
        cell = tuple(self.home)
        if self.foodsAway:
            richest = max(self.foodsAway, key=lambda o: o["energy"])
            dx, dy = getShortestTranslation(
                self.home, richest["position"], self.worldlength
            )
        else:
            dx, dy = 0, 0
        if dx == 0 and dy == 0:
            dx, dy = choice(
                [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1)]
            )
        norm = max(abs(dx), abs(dy))
        length = self.worldlength
        d = cls.DRIFT_DISTANCE
        new = (
            int(round(self.home[0] + d * dx / norm)) % length,
            int(round(self.home[1] + d * dy / norm)) % length,
        )
        cls.homes.pop(cell, None)
        cls.homes[new] = {"recruit": None, "founded": now}
        self.tell("h", (new[0], new[1], now))
        cls.moves.pop(new, None)  # no cycles in the move chain
        cls.moves[cell] = new
        self.home = list(new)
        self.count("drifts")

    def continueGraze(self):
        """walk to the food, take the bites, walk home; True while busy"""
        cls = type(self)
        if self.position() != self.trip:
            self.stepTowards(self.trip, 3)
            if self.position() != self.trip:
                return True
            pos = self.position()
            # the target was within 3 cells at the start of the turn,
            # so its food is in the turn's view (ids stay valid)
            self.foodsHere = sorted(
                (o for o in self.foodsAway if o["position"] == pos),
                key=lambda f: -f["energy"],
            )
        minEnergy = cls.FOREIGN_MIN
        if self.energy() < cls.GRAZE_STARVING:
            minEnergy = 1
        self.eatForeign(minEnergy)
        if (
            self.foodsHere
            and self.foodsHere[0]["energy"] >= minEnergy
            and self.time() < self.eatCost
        ):
            return True  # more bites next turn
        self.trip = None
        self.stepTowards(self.home, 3)
        return True

    def plant(self, patches, cap):
        cls = type(self)
        plant = self.plantEnergy()
        while (
            len(patches) < cap
            and self.time() >= self.plantCost
            and self.energy() > cls.RESERVE + plant
        ):
            if not self.Vomit(plant):
                break
            patches.append({"energy": plant, "age": 0, "id": None})

    def poolFor(self, rc):
        """harvest the richest patches, hand the energy to the recruit"""
        cls = type(self)
        recruit = [f for f in self.friendsHere if f["id"] == rc["id"]]
        if not recruit:
            return
        missing = rc["need"] + 100 - recruit[0]["energy"]
        if missing <= 0:
            return
        eats = 0
        while (
            eats < cls.POOL_EATS
            and self.foodsHere
            and self.time() >= self.eatCost + self.donateCost
            and self.foodsHere[0]["energy"] >= cls.HARVEST_MIN
            and self.energy() - cls.POOL_KEEP < missing
        ):
            if not self.eat(self.foodsHere[0]):
                break
            eats += 1
        amount = min(self.energy() - cls.POOL_KEEP, missing)
        if amount >= 50 and self.time() >= self.donateCost:
            self.Donate(amount, rc["id"])

    def maybeReproduce(self, count, cap):
        cls = type(self)
        if self.time() < self.reproCost:
            return None
        old = self.age() >= self.maxAge - cls.OLD_AGE_MARGIN
        colony = self.colonySize()
        room = self.roomForAnother()
        wanted = False
        if cls.lifeTuned:
            if self.role == "gardener" and room and not self.lean():
                wanted = self.energy() >= 2 * self.winterReserve() + (
                    self.birthCost()
                ) and bool(self.foodsHere or self.foodsAway)
        elif self.role == "gardener" and room:
            members = self.cellMembers(self.home)
            if count < cap:
                wanted = (
                    self.energy() >= 2 * cls.BOOT_CHILD
                    and members < cls.BOOT_PER_CELL
                )
            else:
                wanted = (
                    self.energy() >= 2 * cls.CHILD_MIN
                    and members < cls.HOME_MEMBERS
                )
        if not (old or wanted):
            return None
        child = self.Reproduce()
        if not child:
            return None
        now = cls.worldTurn
        childUid = self.provisionalUid(child)
        if wanted or (old and colony < cls.MIN_COLONY and self.home):
            role = "gardener"
            order = {
                "role": role,
                "home": list(self.home),
                "uid": childUid,
            }
        else:
            role = "sacrifice"
            order = {
                "role": role,
                "parent": self.id(),
                "home": list(self.home) if self.home else None,
                "uid": childUid,
            }
        # the only inheritance the engine allows: one Talk, in the turn
        # the child is born and before it has ever acted
        self.Talk(
            child,
            {
                "s": cls.SIGIL,
                "to": child,
                "t": cls.worldTurn,
                "o": order,
            },
        )
        cls.ledger[childUid] = {
            "energy": self.energy(),
            "cell": tuple(self.position()),
            "turn": now,
            "role": role,
            "phase": None,
            "home": tuple(self.home) if self.home else None,
        }
        return child

    def provisionalUid(self, child):
        """the name the newborn will give itself on its first tick, so
        that this turn's dispatching can already count it. It is the
        child's engine id and the turn it was born, which is what the
        child works out for itself - no shared counter, and no way for
        two wesen to end up with the same name."""
        uid = f"{child:x}:{type(self).worldTurn}"
        type(self).alive[uid] = type(self).worldTurn
        return uid

    # --- dispatch --------------------------------------------------------

    def tileStale(self, tile):
        cls = type(self)
        seen = cls.explored.get(tile)
        return seen is None or cls.worldTurn - seen > cls.PATROL_AGE

    def maybeScout(self):
        cls = type(self)
        if cls.lifeTuned:
            # a grazer has no garden to leave behind, only a full belly
            if self.energy() < cls.SCOUT_ENERGY:
                return False
        elif len(self.foodsHere) < self.cellCap():
            return False
        stale = sum(
            1 for t in range(self.numTiles() ** 2) if self.tileStale(t)
        )
        if stale == 0:
            return False
        swept = len(cls.explored) >= self.numTiles() ** 2
        limit = cls.PATROLS if swept else cls.SCOUTS_MAX
        if self.countRole("scout") >= limit:
            return False
        if self.cellMembers(self.home) <= cls.SCOUT_KEEP:
            return False
        self.setRole("scout", "provision")
        self.since = cls.worldTurn
        self.count("scouts")
        return True

    def killBudget(self):
        """what a kill may cost: grows with the colony's wealth"""
        cls = type(self)
        wealth = sum(v["energy"] for v in cls.ledger.values())
        return max(cls.KILL_MAX, wealth // 40)

    def worthKilling(self, enemyEnergy):
        return 0.5 * enemyEnergy <= self.killBudget()

    def estateNeed(self, cell, dist):
        cls = type(self)
        est = cls.estates[tuple(cell)]
        age = min(100, max(0, cls.worldTurn - est["seen"]))
        growth = GROWTH.get(est["source"], 10)
        rmax = est["rmax"] + growth * (age + dist / 3.0)
        kills = min(
            est["rsum"],
            cls.KILL_RESERVE * est["rmax"],
            cls.KILL_RESERVE * cls.KILL_MAX,
        )
        return int(1.4 * (rmax + cls.BULK) + 0.5 * kills + cls.NEED_MARGIN)

    def wesenNeed(self, energy, src):
        cls = type(self)
        need = int(1.4 * energy) + 200
        if src in CHASERS:
            need = max(need, energy + cls.CHASER_MARGIN + 100)
        return need

    def nearestHomeDist(self, cell):
        cls = type(self)
        return min(
            (self.torusManhattan(cell, h) for h in cls.homes), default=0
        )

    def openTargets(self, fromPos, nearestOnly=False):
        cls = type(self)
        now = cls.worldTurn
        out = []
        for cell, est in cls.estates.items():
            if est["hunter"] is not None:
                continue
            d = self.torusManhattan(fromPos, cell)
            if d > cls.MAX_TRIP:
                continue
            if nearestOnly and (
                d > cls.TRIP_SLACK * self.nearestHomeDist(cell) + 20
            ):
                continue
            if est["dead"]:
                # an abandoned garden keeps growing and would feed a boom
                # of Nightwatch, rabbits or Dwarves: strip it
                if est["garden"] >= cls.GARDEN_TARGET:
                    out.append(
                        (
                            cls.KEEP_BASE,
                            d,
                            {"kind": "garden", "cell": list(cell)},
                        )
                    )
                continue
            if est["source"] is None:
                continue
            need = self.estateNeed(cell, d)
            out.append((need, d, {"kind": "estate", "cell": list(cell)}))
        for wid, s in cls.sightings.items():
            if (
                s["hunter"] is not None
                or now - s["turn"] > cls.SIGHTING_TTL
            ):
                continue
            d = self.torusManhattan(fromPos, s["pos"])
            if d > cls.MAX_TRIP:
                continue
            if nearestOnly and (
                d > cls.TRIP_SLACK * self.nearestHomeDist(s["pos"]) + 20
            ):
                continue
            need = self.wesenNeed(s["energy"], s["source"])
            out.append(
                (
                    need,
                    d,
                    {
                        "kind": "wesen",
                        "id": wid,
                        "cell": list(s["pos"]),
                        "source": s["source"],
                    },
                )
            )
        return out

    @staticmethod
    def targetScore(cand):
        need, d, target = cand
        kind = target["kind"]
        return d + (
            0 if kind == "estate" else 80 if kind == "wesen" else 200
        )

    def assignTarget(self, target):
        cls = type(self)
        if target["kind"] in ("estate", "garden"):
            key = tuple(target["cell"])
            if key not in cls.estates:
                self.suspectEstate(key)
            cls.estates[key]["hunter"] = self.uid
        else:
            s = cls.sightings.get(target["id"])
            if s is not None:
                s["hunter"] = self.uid

    def releaseTarget(self):
        cls = type(self)
        t = self.target
        if t is None:
            return
        if t["kind"] in ("estate", "garden"):
            est = cls.estates.get(tuple(t["cell"]))
            if est is not None and est["hunter"] == self.uid:
                est["hunter"] = None
        else:
            s = cls.sightings.get(t["id"])
            if s is not None and s["hunter"] == self.uid:
                s["hunter"] = None
        self.target = None

    def maybeHunt(self):
        """the fattest gardener of a cell claims a target the cell
        can pay for: bodies above the pool floor plus the harvestable
        patches"""
        cls = type(self)
        rec = cls.homes.get(tuple(self.home))
        if rec is None or rec.get("recruit") is not None:
            return False
        if any(f["energy"] > self.energy() for f in self.friendsHere):
            return False
        if self.cellMembers(self.home) <= cls.MIN_GARDENERS:
            return False
        bank = self.energy()
        bank += sum(
            max(0, f["energy"] - cls.POOL_KEEP) for f in self.friendsHere
        )
        bank += int(
            0.9
            * sum(
                f["energy"]
                for f in self.foodsHere
                if f["energy"] >= cls.HARVEST_MIN
            )
        )
        cands = [
            c
            for c in self.openTargets(self.position(), nearestOnly=True)
            if c[0] <= bank
        ]
        if not cands:
            return False
        need, d, target = min(cands, key=self.targetScore)
        self.target = target
        self.assignTarget(target)
        self.setRole("hunter", "pool")
        self.since = cls.worldTurn
        self.lastSeen = cls.worldTurn
        rec["recruit"] = {
            "id": self.id(),
            "uid": self.uid,
            "need": need,
            "since": cls.worldTurn,
        }
        self.count("hunts")
        return True

    # --- scout -----------------------------------------------------------

    def numTiles(self):
        cls = type(self)
        return (self.worldlength + cls.TILE - 1) // cls.TILE

    def tileCentre(self, tile):
        cls = type(self)
        n = self.numTiles()
        i, j = divmod(tile, n)
        half = cls.TILE // 2
        return [
            min(i * cls.TILE + half, self.worldlength - 1),
            min(j * cls.TILE + half, self.worldlength - 1),
        ]

    def claimTile(self):
        cls = type(self)
        now = cls.worldTurn
        pos = self.position()
        best = None
        for tile in range(self.numTiles() ** 2):
            if not self.tileStale(tile):
                continue
            claim = cls.claims.get(tile)
            if claim is not None and claim[0] != self.uid:
                if (
                    claim[0] in cls.alive
                    and now - claim[1] <= cls.CLAIM_TTL
                ):
                    continue
            d = self.torusManhattan(pos, self.tileCentre(tile))
            if best is None or d < best[0]:
                best = (d, tile)
        if best is None:
            return None
        cls.claims[best[1]] = (self.uid, now)
        return best[1]

    def scoutTurn(self):
        cls = type(self)
        now = cls.worldTurn
        pos = self.position()
        if self.phase == "provision":
            if pos != self.home:
                self.stepTowards(self.home, 3)
                return
            self.harvestUntil(cls.SCOUT_ENERGY, minPatch=3)
            if (
                self.energy() >= cls.SCOUT_ENERGY
                or now - self.since >= cls.SCOUT_PROVISION_TURNS
                or not any(f["energy"] >= 3 for f in self.foodsHere)
            ):
                self.phase = "sweep"
                self.since = now
            return
        # snack on natural food and seeds along the way
        if self.energy() < cls.SCOUT_ENERGY:
            while (
                self.foodsHere
                and self.time() >= self.eatCost + self.moveCost
                and self.foodsHere[0]["energy"] >= 5
            ):
                if not self.eat(self.foodsHere[0]):
                    break
        if self.detour is not None:
            if (
                now - self.detourSince > cls.DETOUR_MAX
                or self.torusDist(pos, self.detour) <= 10
            ):
                self.detour = None
            else:
                self.stepTowards(self.detour, 3)
                return
        # glean rich foreign food nearby (old Dwarf seeds, blobs)
        if self.glean is None:
            rich = [
                (self.viewDist(c, pos), c)
                for c, e in self.foodEnergyByCell.items()
                if e >= cls.GLEAN_MIN
                and c not in cls.homes
                and c not in cls.estates
                and c not in self.lethal
                and self.viewDist(c, pos) <= cls.GLEAN_RANGE
            ]
            if rich:
                self.glean = list(min(rich)[1])
                self.gleanSince = now
        if self.glean is not None:
            if pos == self.glean:
                self.eatForeign(cls.FOREIGN_MIN)
                if not self.foodsHere or (
                    self.foodsHere[0]["energy"] < cls.FOREIGN_MIN
                ):
                    self.glean = None
                return
            if now - self.gleanSince > 4:
                self.glean = None
            else:
                self.stepTowards(self.glean, 3)
                return
        if self.tile is None:
            self.tile = self.claimTile()
            if self.tile is None:
                self.retireScout(self.nearestHome(pos))
                return
        centre = self.tileCentre(self.tile)
        if pos != centre:
            self.stepTowards(centre, (self.time() - 1) // self.moveCost)
            if self.position() != centre:
                return
        if self.time() < self.cheapLookCost:
            return
        self.noteLook(self.look())
        cls.explored[self.tile] = now
        cls.claims.pop(self.tile, None)
        self.tile = None
        # identify the nearest unidentified pile in look() range
        suspects = [
            cell
            for cell, est in cls.estates.items()
            if est["source"] is None
            and not est["dead"]
            and self.viewDist(cell, pos) <= 24
        ]
        if suspects:
            self.detour = list(
                min(suspects, key=lambda c: self.viewDist(c, pos))
            )
            self.detourSince = now

    def retireScout(self, homeCell):
        cls = type(self)
        if self.tile is not None:
            cls.claims.pop(self.tile, None)
            self.tile = None
        self.setRole("gardener")
        if homeCell is not None:
            self.home = list(homeCell)
        elif self.home is None:
            self.home = list(self.position())
        self.registerHome(self.home)

    # --- hunter ----------------------------------------------------------

    def hunterTurn(self):
        cls = type(self)
        if self.waitTurns > 0:
            self.waitTurns -= 1
            self.eatForeign()
            return
        if self.age() >= self.maxAge - cls.OLD_AGE_MARGIN:
            if self.maybeReproduce(0, 1):
                self.waitTurns = 1
                return
        if self.phase == "pool":
            self.hunterPool()
        elif self.phase == "travel":
            self.hunterTravel()
        elif self.phase == "station":
            self.hunterStation()
        elif self.phase == "chase":
            self.hunterChase()
        else:
            self.hunterHome()

    def abortHunt(self, reason="abort"):
        cls = type(self)
        self.count(reason)
        self.releaseTarget()
        rec = cls.homes.get(tuple(self.home)) if self.home else None
        if (
            rec is not None
            and rec.get("recruit", {})
            and (rec["recruit"]["uid"] == self.uid)
        ):
            rec["recruit"] = None
        self.goHome()

    def goHome(self):
        """walk to the nearest treasury and garden there"""
        cls = type(self)
        nearest = self.nearestHome(self.position())
        if nearest is not None:
            self.home = nearest
        self.phase = "home"
        self.since = cls.worldTurn

    def finishHunt(self):
        """target done: take the next affordable one, or walk home"""
        cls = type(self)
        self.releaseTarget()
        pos = self.position()
        bank = self.energy() - self.keep()
        cands = [c for c in self.openTargets(pos) if c[0] <= bank]
        if cands:
            need, d, target = min(cands, key=self.targetScore)
            self.target = target
            self.assignTarget(target)
            self.phase = "travel"
            self.since = cls.worldTurn
            self.lastSeen = cls.worldTurn
            self.count("rehunts")
            self.stepTowards(target["cell"], 3)
            return
        self.goHome()

    def hunterPool(self):
        cls = type(self)
        now = cls.worldTurn
        rec = cls.homes.get(tuple(self.home))
        rc = rec.get("recruit") if rec else None
        if rc is None or rc["uid"] != self.uid:
            self.abortHunt("abort_recruit")
            return
        if self.energy() >= rc["need"]:
            rec["recruit"] = None
            self.phase = "travel"
            self.since = now
            self.lastSeen = now
            self.stepTowards(self.target["cell"], 3)
            return
        if now - self.since > cls.POOL_TIMEOUT:
            self.abortHunt("abort_pool")
            return
        if self.position() != self.home:
            self.stepTowards(self.home, 3)
            return
        self.harvestUntil(rc["need"], minPatch=3)

    def hunterTravel(self):
        cls = type(self)
        now = cls.worldTurn
        pos = self.position()
        target = self.target
        cell = target["cell"]
        if target["kind"] == "garden":
            est = cls.estates.get(tuple(cell))
            if est is None:
                self.finishHunt()
                return
            self.stepTowards(cell, 3)
            if self.position() == list(cell):
                self.phase = "station"
                self.since = now
                self.lastSeen = now - cls.STALE - 1
                est["deadSince"] = now
            return
        if target["kind"] == "estate":
            est = cls.estates.get(tuple(cell))
            if est is None or est["dead"]:
                self.finishHunt()
                return
            if self.torusDist(pos, cell) <= 12:
                residents = [
                    e
                    for e in self.enemies
                    if e["source"] == est["source"]
                    and self.torusDist(e["position"], cell) <= 8
                ]
                if (
                    residents
                    and max(e["energy"] for e in residents)
                    > 0.7 * self.energy()
                ):
                    self.abortHunt("abort_travel")  # plan not sound
                    return
            self.stepTowards(cell, 3, force=self.torusDist(pos, cell) <= 3)
            if self.position() == list(cell):
                self.phase = "station"
                self.since = now
                self.lastSeen = now
            return
        # roaming target: chase as soon as it is in view
        if any(e["id"] == target["id"] for e in self.enemies):
            self.phase = "chase"
            self.since = now
            self.hunterChase()
            return
        if self.opportunity():
            return
        self.stepTowards(cell, 3)
        if self.position() == list(cell):
            self.phase = "chase"
            self.since = now

    def opportunity(self):
        """cheap non-fleeing enemy within reach: kill it in passing"""
        pos = self.position()
        prey = [
            e
            for e in self.enemies
            if e["source"] not in FLEE_RADIUS
            and e["id"] not in self.killed
            and self.canKill(e["energy"])
            and self.worthKilling(e["energy"])
            and self.torusManhattan(pos, e["position"]) <= 3
        ]
        if not prey:
            return False
        e = min(
            prey, key=lambda e: self.torusManhattan(pos, e["position"])
        )
        self.chase(e)
        return True

    def chase(self, e):
        """approach and strike. A fleeing wesen steps 3 cells away along
        one axis whenever we are within its radius, so we step next to it
        and strike after its flight; the time budget converges because a
        3-cell move costs less than one turn of time."""
        pos = self.position()
        d = self.torusManhattan(pos, e["position"])
        if self.moveCost * d + self.attackCost <= self.time():
            self.stepTowards(e["position"], d, force=True)
            if self.position() == list(e["position"]):
                return self.strike(e)
            return False
        steps = min(max(d - 1, 0), self.time() // self.moveCost)
        if steps > 0:
            self.stepTowards(e["position"], steps, force=True)
        return False

    def hunterStation(self):
        cls = type(self)
        now = cls.worldTurn
        pos = self.position()
        cell = tuple(self.target["cell"])
        est = cls.estates.get(cell)
        if est is None:
            self.finishHunt()
            return
        est["hunter"] = self.uid
        src = est["source"]
        residents = [e for e in self.enemies if e["source"] == src]
        if residents:
            self.lastSeen = now
            est["seen"] = now
            est["dead"] = False
            rmax = max(e["energy"] for e in residents)
            if rmax > 0.75 * self.energy():
                self.abortHunt("abort_station")
                return
            prey = [
                e
                for e in residents
                if e["id"] not in self.killed
                and self.worthKilling(e["energy"])
                and self.canKill(e["energy"])
            ]
            if prey:
                e = min(
                    prey,
                    key=lambda e: self.torusManhattan(pos, e["position"]),
                )
                self.chase(e)
                return
            # residents too expensive to kill: paralyse them from the cell
        elif (
            now - est["seen"] > cls.STALE
            and now - self.lastSeen > cls.STALE
        ):
            if not est["dead"]:
                est["dead"] = True
                est["deadSince"] = now
                self.count("estates_dead")
            if pos != list(cell):
                self.stepTowards(cell, 3, force=True)
                return
            # strip the abandoned garden: it would feed a Nightwatch or
            # rabbit boom otherwise
            garden = [
                f for f in self.foodsHere if f["energy"] >= cls.GARDEN_MIN
            ]
            if (
                not garden
                or now - est.get("deadSince", now) > cls.GARDEN_TURNS
            ):
                est["garden"] = sum(f["energy"] for f in self.foodsHere)
                self.finishHunt()
                return
            self.eatForeign(cls.GARDEN_MIN)
            return
        if pos != list(cell):
            self.stepTowards(cell, 3, force=True)
            return
        self.eatForeign()
        if self.turnsLived % 10 == 0 and self.time() >= self.cheapLookCost:
            self.noteLook(self.look())
        if self.turnsLived % 10 == 5:
            if not self.maybeReproduce(0, 1):
                self.splitFor(est)

    def splitFor(self, est):
        """send a child hunter to an open estate in the neighbourhood"""
        cls = type(self)
        if self.time() < self.reproCost:
            return
        if not self.roomForAnother():
            return
        half = self.energy() // 2
        if half < int(1.4 * est["rmax"]) + 300:
            return
        pos = self.position()
        best = None
        for need, d, target in self.openTargets(pos):
            if d > cls.NEIGHBOUR_RANGE or need > half:
                continue
            if best is None or d < best[1]:
                best = (need, d, target)
        if best is None:
            return
        child = self.Reproduce()
        if not child:
            return
        need, d, target = best
        now = cls.worldTurn
        childUid = self.provisionalUid(child)
        self.Talk(
            child,
            {
                "s": cls.SIGIL,
                "to": child,
                "t": cls.worldTurn,
                "o": {
                    "uid": childUid,
                    "role": "hunter",
                    "phase": "travel",
                    "target": target,
                    "home": list(self.home) if self.home else None,
                },
            },
        )
        cls.ledger[childUid] = {
            "energy": half,
            "cell": tuple(pos),
            "turn": now,
            "role": "hunter",
            "phase": "travel",
            "home": tuple(self.home) if self.home else None,
        }
        if target["kind"] in ("estate", "garden"):
            cls.estates[tuple(target["cell"])]["hunter"] = childUid
        else:
            s2 = cls.sightings.get(target["id"])
            if s2 is not None:
                s2["hunter"] = childUid
        self.count("splits")

    def eatForeign(self, minEnergy=None):
        cls = type(self)
        if minEnergy is None:
            minEnergy = cls.FOREIGN_MIN
        while (
            self.foodsHere
            and self.time() >= self.eatCost
            and self.foodsHere[0]["energy"] >= minEnergy
        ):
            if not self.eat(self.foodsHere[0]):
                break

    def hunterChase(self):
        cls = type(self)
        now = cls.worldTurn
        pos = self.position()
        tid = self.target["id"]
        seen = [e for e in self.enemies if e["id"] == tid]
        if seen:
            e = seen[0]
            self.lastSeen = now
            self.target["cell"] = list(e["position"])
            if not self.canKill(e["energy"]) or not self.worthKilling(
                e["energy"]
            ):
                cls.sightings.pop(tid, None)
                self.finishHunt()
                return
            self.chase(e)
            return
        if self.opportunity():
            return
        if pos != self.target["cell"]:
            self.stepTowards(self.target["cell"], 3)
            return
        if now - self.lastSeen > cls.LOST:
            cls.sightings.pop(tid, None)
            self.finishHunt()

    def hunterHome(self):
        if self.home is None:
            self.home = self.nearestHome(self.position()) or list(
                self.position()
            )
        if self.position() != self.home:
            if self.opportunity():
                return
            self.stepTowards(self.home, 3)
            return
        self.setRole("gardener")
        self.target = None
