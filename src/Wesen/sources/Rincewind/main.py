"""Rincewind - the colony that runs a message network.

Every other source in this game plays solitaire: each wesen looks
around, decides for itself, and whatever it learns dies with it. The
engine has offered `Talk`, `Broadcast` and `Receive` from the beginning
and nobody has ever sent a single message. This source is built the
other way round: sensing is a colony-wide service, the plan is made
from what the colony knows, and an individual wesen is mostly a
subscriber to it.

(`Talk` did not in fact work - the range filter closed over the loop
variable of the loop it was filtering, so it raised `NameError` the
moment anything was within 24 cells. One line in `objects/wesen.py`.)

Why that wins, in one paragraph. A cell of food grows by at most
`growrate x 4 e (1-e)` per turn - about 0.6 - so a cell can pay one
15-energy bite every 25 turns and no persuasion will make it pay more.
A wesen has 25 time a turn, a bite costs 10 and a step costs 7, so its
income is decided almost entirely by the walking: bites are worth 0.9
energy per time on an adjacent cell and 0.4 three cells away. Everything
that matters is therefore knowing which cells are ripe *now*, not
walking to one a colleague emptied five turns ago, and not keeping two
wesen where the pasture feeds one. None of that is visible to a single
wesen with a 12-cell eye - and all of it is cheap to say out loud:
a `Broadcast` costs 1 time, the same as a step costs 7, and carries as
much as we like.

The five parts:

Gossip (`ledger.py`).
    Each wesen keeps a ledger of food cells (energy, when seen, when
    bitten, who reserved it), colleagues (position, energy, home,
    role), threats and explored tiles. Once a turn it broadcasts a
    delta of what it learned; anything that arrives is merged
    key by key, newest timestamp wins. Nothing is shared through class
    attributes: a fact travels only as far as somebody carries or
    broadcasts it, the colony's calendar is kept in step by taking the
    highest clock anybody quotes, and a wesen out of everybody's range
    goes blind until it walks back into the network.

Districts.
    Colleagues' homes are the one thing everybody publishes, so every
    wesen can draw the same Voronoi partition of the pasture and know
    which cells are its own to work. A home drifts towards the cells its
    keeper actually harvests (Lloyd relaxation), so the districts follow
    the pasture instead of a fixed grid, and they push each other apart
    without any negotiation at all.

Reservations.
    Before walking to a cell a wesen reserves it in the ledger and the
    reservation rides on the next broadcast. A colleague that hears it
    strikes the cell off its own list. This is the whole of the "two
    wesen walk to the same cell" problem, solved for 1 time.

The harvest rule (`plan.py`).
    A fed wesen leaves a third of a cell's capacity standing, where it
    regrows fastest, and one cell in four - picked by a hash of its
    position, so the whole colony protects the same ones without a word
    - is never touched at all, because food seeds only above
    `birth_maturity` and a pasture grazed everywhere below that quietly
    ages out. On ground where the alarms say a rival grazes, the rule
    drops to what a hungry wesen takes: interest left standing there is
    not an investment, it is a gift. With spare energy it plants
    (`Vomit`) where the neighbourhood density says a seed will take,
    because the pasture is the pie and the pie can be made bigger.

Population and alarms.
    A wesen splits while it is on the frontier or while its own
    district holds more known cells than one wesen can work, and the
    child is briefed by `Talk` at birth: its uid, the colony clock, a
    district of its own and a copy of the map, which is the only
    inheritance this engine allows. So the colony stops growing exactly
    where the pasture stops paying, and a wesen whose district has been
    eaten bare moves to ground the colony knows is free instead of
    starving on it. Nobody ever hears the whole roll, so the size of
    the colony is *estimated* from the density of homes around one home
    (`colonySize`) and growth stops at `MAX_COLONY` - which is a knob
    for the machine rather than for the game: this colony can fill a
    world, and every wesen in it costs the simulation time.

    Threats are broadcast the moment they are seen, and an alarm
    travels a whole talk range in the turn it is raised while a hunter
    walks three cells, so the colony usually knows about a killer
    before it arrives.

Nothing is kept on the class: a class attribute is genetic information
(the same for every wesen, for the whole game, see `isolation.py`), so
everything this colony knows lives in an instance and travels as a
message. Errors are left to the engine, which skips the turn and prints
each distinct one once with its traceback.
"""

from math import log

from ...defaultwesensource import DefaultWesenSource
from ...objects.wesen import RuleException
from .ledger import SIGIL, SOFT_CELLS, Ledger
from .plan import (
    bitesAvailable,
    cellValue,
    chebyshev,
    districtRank,
    drift,
    fleeVector,
    growthRate,
    harvestFloor,
    manhattan,
    regrow,
    seedStock,
    stepVector,
)

# Who attacks whom. These two numbers are the *other sources'* own
# hardcoded thresholds (see Dwarf/helper.py and Nightwatch/helper.py):
# they hunt anything up to their own energy plus a fixed margin, once
# they hold the first amount. They are not rules of the game and are
# not read from the config, and any source not named here is judged by
# what its attack would do, which is (see `wouldAttack`).
CHASERS = {"Dwarf": (301, 300), "Nightwatch": (375, 375)}
# sources that never attack anybody at all
HARMLESS = {
    "GreatRabbit",
    "DrunkenSailor",
    "SoberSailor",
    "Scanner",
    "WindlePoons",
    "Manual",
}


class WesenSource(DefaultWesenSource):
    """one member of the colony; the design is in the module docstring"""

    # There is no class-level state at all, not even a cache: a class
    # attribute is genetic information, the same for every wesen and for
    # the whole game (see isolation.py). Everything this source learns
    # lives in the instance, and travels only as a message. That is the
    # point of it.

    # --- policy ---------------------------------------------------
    # Only dimensionless choices live here. Everything with a unit -
    # energies, distances, turns - is worked out in `readRules` from
    # what this particular game hands the source, because the config
    # varies from tournament to tournament and `[variation]` scales the
    # rules again per game.
    OUTSIDE_PENALTY = 0.45  # worth of a cell per colleague nearer to it
    HEARSAY = 0.7  # worth of a cell nobody has looked at closely
    STALE = 0.97  # ... and per turn since the report was made
    CROWD_ALARMS = 2  # rival sightings that end the gardening
    FERT_GRID = 4  # cells per square of the remembered terrain
    PASTURE_MEMORY = 0.02  # weight of one scan in the pasture average
    PASTURE_FALL = 0.9  # of that average: below it, the pasture is
    # shrinking and the colony may not grow
    SEED_STOCK = 4  # one cell in this many is never touched at all
    CLUSTER_BONUS = 0.22  # extra worth per neighbour of a cell
    CLUSTER_CAP = 5  # ... counted up to this many
    CELL_SHARE = 2.0  # known cells per cell actually in rotation
    WALK_TURNS = 12  # turns of walking a bite may be worth
    RESERVE_TURNS = 90  # turns of upkeep a wesen wants in the bank
    STARVE_TURNS = 40  # ... below which it eats the seed corn
    WINTER_SHARE = 0.35  # of the winter's upkeep, saved in advance
    PLANT_FACTOR = 4.0  # of the reserve, before planting is affordable
    PLANT_GROUND = 0.9  # fertility a seed is worth planting on (1 is
    # average ground, see biome.py)
    MAX_COLONY = 120  # colony size the world is not to be filled past
    FREE_GROWTH = 8  # colleagues known, below which growth is free
    REPLAN = 5  # turns between two scans of the ledger
    PUBLISH_EVERY = 3  # broadcast at least this often
    SILENT_CALL = 8  # ... or this often with nobody within earshot
    NEWS_WORTH_SAYING = 3  # records that make a broadcast worth its time
    DOWRY = 150  # cell records a newborn is given at birth
    PRUNE_EVERY = 16  # turns between two housekeepings of the ledger
    RECONSIDER_EVERY = 25  # turns between two "is this ground still
    # worth keeping" questions
    SETTLE_GRACE = 80  # turns a new district gets before that question
    THREAT_MEMORY = 60  # turns an alarm still counts for
    CROWD_MEMORY = 150  # ... and still says the colony is not alone
    PEER_MEMORY = 120  # turns a colleague still bounds my district
    CENSUS_MEMORY = 200  # ... and still counts in the colony census
    CELL_MEMORY = 500  # turns a cell report still counts as district
    KILL_SHARE = 0.16  # of the body, the most a kill may cost
    BODY_FACTOR = 1.3  # of a cell's capacity: above that it is a corpse

    def __init__(self, infoAllSource):
        DefaultWesenSource.__init__(self, infoAllSource)
        self.readRules()
        self.ledger = Ledger(
            # a report about a cell that could have died of old age
            # meanwhile is worth nothing
            cellTTL=int(0.6 * self.infoFood.get("maxage", 1000)),
            peerTTL=self.CENSUS_MEMORY,
            threatTTL=self.THREAT_MEMORY + self.CROWD_MEMORY,
            # a reservation lasts as long as the walk it is made for
            holdTTL=max(4, self.targetRange // self.stepsPerTurn),
        )
        self.uid = None
        self.clock = 0
        self.home = None
        self.role = "founder"
        self.target = None  # cell we are walking to
        self.targetSince = -99
        self.lastPublish = -99
        self.lastPlan = -99
        self.districtCells = 0
        self.pastureEma = 0.0  # what the district has been holding
        self.neighbours = 0  # colleagues whose ground touches mine
        self.harvest = None  # centre of what we actually harvest
        self.briefed = False
        self.stats = {}  # debug counters (see count)
        self.fertCache = {}  # terrain this wesen has looked up
        self.crowd = []  # colleagues seen this turn, with their homes
        self.ate = 0  # bites taken this turn (a debug counter)
        self.settledAt = 0  # when this wesen last took up a district
        self.length = self.worldlength

    def readRules(self):
        """every number with a unit, worked out from this game's rules.

        Nothing here is a constant of the game: the time costs, the
        ranges, the size of a bite, the growth rate and the upkeep are
        all config, and `[variation]` multiplies them again once per
        game. A source that hardcodes the defaults plays a game that is
        not the one it is in."""
        self.moveTime = self.infoTime["move"]
        self.eatTime = self.infoTime["eat"]
        self.lookTime = self.infoTime["look"]
        self.closerTime = self.infoTime["closerlook"]
        self.talkTime = self.infoTime["talk"]
        self.castTime = self.infoTime["broadcast"]
        self.reproduceTime = self.infoTime["reproduce"]
        self.vomitTime = self.infoTime["vomit"]
        self.attackTime = self.infoTime["attack"]
        self.donateTime = self.infoTime["donate"]
        self.turnTime = self.infoTime["init"]
        self.fullTime = self.infoTime["max"]
        self.maxamount = self.infoFood["maxamount"]
        self.growrate = self.infoFood.get("growrate", 0.6)
        self.bite = self.foodBite() or self.maxamount
        self.roots = self.foodRoots()
        self.maxage = self.infoWesen["maxage"]
        self.seedRange = self.infoRange["seed"]
        self.tile = self.infoRange["look"]
        # how far a wesen gets in one turn, and in a turn of saved time
        self.stepsPerTurn = max(1, self.turnTime // self.moveTime)
        self.fullSteps = max(1, self.fullTime // self.moveTime)
        # a cell pays one bite per this many turns and no faster:
        # growth peaks at growrate (half capacity), and the season and
        # the ground only make it slower
        self.cycleTurns = max(
            1.0, self.bite / max(0.02, 0.5 * self.growrate)
        )
        # ... so this is the number of cells one wesen can keep in
        # rotation, and `CELL_SHARE` of them are ripe at any one time
        self.bitesPerTurn = self.turnTime / (
            self.eatTime + self.moveTime * self.stepsPerTurn
        )
        self.cellsPerWesen = max(
            8, int(self.CELL_SHARE * self.bitesPerTurn * self.cycleTurns)
        )
        self.targetRange = max(
            4, int(self.WALK_TURNS * self.turnTime / self.moveTime)
        )
        self.homeRadius = int(1.5 * self.targetRange)
        self.homeRange = 2 * self.targetRange
        self.settledRange = self.stepsPerTurn
        self.siteSpacing = max(2, self.targetRange // 2)
        self.siteReach = tuple(
            max(4, int(f * self.targetRange)) for f in (0.6, 0.95, 1.3)
        )
        # an enemy with a full time budget crosses this much ground
        self.threatReach = self.fullSteps
        self.chaserReach = self.fullSteps + 2
        self.unknownEnergy = 0.3 * self.maxamount
        self.ripeWait = max(4, int(0.6 * self.cycleTurns))
        self.reserveBase = max(
            self.minBirthEnergy(), self.bodyFor(self.RESERVE_TURNS)
        )
        self.reserveMax = 3 * self.reserveBase
        self.starveLevel = max(
            3 * self.bite, self.bodyFor(self.STARVE_TURNS)
        )
        self.plantEnergy = max(2 * max(1, self.roots), self.maxamount // 4)
        # a seed only takes where the neighbourhood density is inside
        # the fertile band of `Food.growth`
        self.plantDensity = self.infoFood.get(
            "fertile_peak", 1.0
        ) + 0.5 * self.infoFood.get("fertile_width", 1.5)

    def bodyFor(self, turns):
        """the body that lives `turns` turns on its own reserves:
        upkeep is `base + rate x energy`, so this is the fixed point of
        E = turns x upkeep(E), and it runs away once the rate alone
        eats the body inside that time."""
        base = self.infoWesen.get("upkeep", 1)
        rate = self.infoWesen.get("upkeep_rate", 0.0)
        room = 1.0 - turns * rate
        if room <= 0.05:
            return int(20 * turns * base)
        return int(turns * base / room)

    def __str__(self):
        return "<Rincewind, and the clacks>"

    def getDescriptor(self):
        return {"role": self.role, "uid": self.uid or "?"}

    # --- the network ----------------------------------------------------

    def Receive(self, message):
        """a message from a colleague (nobody else in this game speaks).

        Anything that is not ours is ignored rather than trusted: the
        channel is open to every source in range."""
        try:
            if not isinstance(message, dict) or message.get("s") != SIGIL:
                return
            if "orders" in message:
                self.takeOrders(message)
                return
            if message.get("u") == self.uid:
                return
            heard = self.ledger.merge(message, self.clock)
            if heard > self.clock:
                # the colony's calendar: whoever counted furthest is
                # right, a turn skipped by an error must not drift
                self.clock = heard
            self.count("heard")
        except Exception:  # noqa: BLE001
            self.fault("Receive")

    def takeOrders(self, message):
        """birth papers: uid, calendar, district and the colony's map.

        A child is a fresh object with no memory, so everything it knows
        it is told, in one `Talk`, by the parent that made it."""
        orders = message["orders"]
        if orders.get("to") != self.id():
            return
        self.uid = orders["uid"]
        self.clock = orders["clock"]
        self.home = list(orders["home"])
        self.role = orders["role"]
        self.briefed = True
        self.ledger.merge(message, self.clock)
        self.ledger.fresh.clear()
        self.count("briefed")

    def publish(self, force=False):
        """one broadcast a turn with what we learned, at most"""
        if self.time() < self.castTime:
            return
        news = len(self.ledger.fresh)
        silent = self.clock - self.lastPublish
        if not force:
            if (
                news < self.NEWS_WORTH_SAYING
                and silent < self.PUBLISH_EVERY
            ):
                return
            if (
                not self.crowd
                and not self.peerNear()
                and silent < self.SILENT_CALL
            ):
                # nobody within earshot: a call every eight turns is
                # enough to find whoever has just walked into range
                return
        self.lastPublish = self.clock
        self.Broadcast(
            self.ledger.digest(
                self.uid,
                self.clock,
                self.position(),
                self.energy(),
                self.home,
                self.role,
            )
        )
        self.count("cast")

    def peerNear(self):
        """is a colleague near enough for a broadcast to reach it?"""
        clock = self.clock
        pos = self.position()
        for uid, rec in self.ledger.peers.items():
            if uid == self.uid or clock - rec[3] > self.PUBLISH_EVERY * 4:
                continue
            earshot = self.infoRange["talk"] + 2 * self.stepsPerTurn
            if chebyshev(pos, rec[0], self.length) <= earshot:
                return True
        return False

    def brief(self, childId, uid, home, role):
        """hand a newborn its papers and the map (1 time)"""
        if self.time() < self.talkTime:
            return
        message = self.ledger.digest(
            self.uid,
            self.clock,
            self.position(),
            self.energy(),
            self.home,
            self.role,
            budget=0,
            clear=False,
        )
        # the whole map, not just a delta: this is an inheritance
        cells = sorted(
            self.ledger.cells.items(),
            key=lambda i: -i[1][1],
        )[: self.DOWRY]
        message["c"] = [
            (k[0], k[1], r[0], r[1], r[2], r[3], r[4]) for k, r in cells
        ]
        message["a"] = [
            (t[0], t[1], r[0], r[1], r[2], r[3], r[4])
            for t, r in self.ledger.threats.items()
        ][: self.DOWRY // 12]
        message["x"] = [
            (t[0], t[1], turn) for t, turn in self.ledger.tiles.items()
        ][: self.DOWRY // 2]
        message["orders"] = {
            "to": childId,
            "uid": uid,
            "clock": self.clock,
            "home": [int(home[0]), int(home[1])],
            "role": role,
        }
        self.Talk(childId, message)
        self.count("briefings")

    # --- perception -----------------------------------------------------

    def fert(self, pos):
        """fertility of a cell, remembered by this wesen.

        The terrain never changes and every wesen may read any of it for
        free, so this is arithmetic and not knowledge: the cache saves
        the call, it does not carry anything from one wesen to another,
        and it is per wesen for exactly that reason."""
        key = (pos[0] // self.FERT_GRID, pos[1] // self.FERT_GRID)
        value = self.fertCache.get(key)
        if value is None:
            half = self.FERT_GRID // 2
            value = self.fertility(
                [
                    key[0] * self.FERT_GRID + half,
                    key[1] * self.FERT_GRID + half,
                ]
            )
            self.fertCache[key] = value
        return value

    def capacityAt(self, pos):
        return max(1.0, self.maxamount * self.fert(pos))

    def readView(self, view):
        """write everything a closerLook() saw into the ledger, and
        delete the cells it should have seen and did not"""
        clock = self.clock
        pos = self.position()
        radius = self.infoRange["closer_look"]
        seen = set()
        threats = []
        friends = []
        for o in view:
            if o["type"] == "food":
                key = (o["position"][0], o["position"][1])
                seen.add(key)
                self.ledger.sawCell(key, o["energy"], clock)
            elif o["source"] == self.source:
                friends.append(o)
            else:
                threats.append(o)
        # vision does not wrap: the engine clamps the box at the border
        minX, maxX = (
            max(0, pos[0] - radius),
            min(self.length, pos[0] + radius + 1),
        )
        minY, maxY = (
            max(0, pos[1] - radius),
            min(self.length, pos[1] + radius + 1),
        )
        gone = [
            key
            for key in self.ledger.cells
            if minX <= key[0] < maxX
            and minY <= key[1] < maxY
            and key not in seen
        ]
        for key in gone:
            self.ledger.lostCell(key)
        self.ledger.sawTile(
            (pos[0] // self.tile, pos[1] // self.tile), clock
        )
        # colleagues standing in my own eyeshot contest this ground
        # whether or not I have ever heard from them
        self.crowd = [tuple(o["position"]) for o in friends]
        return threats, friends

    def readWide(self, wide):
        """look() gives positions only, which is still worth 1 time:
        an unknown cell is better than an empty map, and the energy
        follows when somebody walks past it"""
        clock = self.clock
        cells = self.ledger.cells
        room = len(cells) < SOFT_CELLS
        for o in wide:
            if o["type"] == "food":
                key = (o["position"][0], o["position"][1])
                if room or key in cells:
                    self.ledger.sawCell(key, None, clock)
        pos = self.position()
        step = self.tile
        # a look reaches one tile's width in every direction, which is
        # about the nine tiles around us: mark them all as swept, so
        # the colony does not send a second wesen over the same ground
        for dx in (-step, 0, step):
            for dy in (-step, 0, step):
                self.ledger.sawTile(
                    (
                        ((pos[0] + dx) % self.length) // step,
                        ((pos[1] + dy) % self.length) // step,
                    ),
                    clock,
                )

    # --- the body -------------------------------------------------------

    def reserve(self):
        """energy a wesen wants to keep: enough to survive a lean spell
        and to be an unattractive target"""
        winter = self.turnsUntilSpring()
        if winter:
            base = self.reserveBase
            keep = base + self.WINTER_SHARE * winter * self.upkeepOf(base)
        else:
            keep = self.reserveBase
        return min(self.reserveMax, keep)

    def rate(self, fertility):
        return growthRate(
            self.growrate,
            self.maxamount * fertility,
            max(0.3, self.growthFactor()),
            fertility,
        )

    def estimate(self, key, rec):
        """what a remembered cell probably holds now"""
        fertility = self.fert(key)
        capacity = self.maxamount * fertility
        energy = rec[0]
        if energy < 0:
            energy = self.unknownEnergy * fertility
        return regrow(
            energy,
            self.clock - rec[1],
            max(capacity, energy),
            self.rate(fertility),
        )

    def ripeIn(self, energy, wanted, capacity, fertility):
        """turns until a cell reaches `wanted`"""
        if energy >= wanted:
            return 0
        if wanted >= capacity:
            return self.ripeWait + 1
        rate = self.rate(fertility)
        if energy <= 0 or rate <= 0:
            return self.ripeWait + 1
        try:
            return (
                log(
                    ((capacity - energy) / energy)
                    / ((capacity - wanted) / wanted)
                )
                / rate
            )
        except (ValueError, ZeroDivisionError):  # pragma: no cover
            return self.ripeWait + 1

    # --- planning -------------------------------------------------------

    def neighbourHomes(self):
        """the homes that bound my district (see plan.districtRank)"""
        clock = self.clock
        homes = []
        for uid, rec in self.ledger.peers.items():
            if uid == self.uid or clock - rec[3] > self.PEER_MEMORY:
                continue
            if manhattan(self.home, rec[2], self.length) <= self.homeRange:
                homes.append(rec[2])
        return homes + self.crowd

    def census(self):
        """how many colleagues this wesen has actually heard of"""
        clock = self.clock
        return 1 + sum(
            1
            for rec in self.ledger.peers.values()
            if clock - rec[3] < self.CENSUS_MEMORY
        )

    def colonySize(self):
        """an estimate of the *whole* colony, not just the part within
        earshot.

        A message only travels as far as somebody carries it, so no
        wesen ever hears the whole roll - but the colony spreads itself
        evenly (districts push each other apart), so the density of
        homes around this one, times the world, is a fair estimate of
        it. That is the number the colony is not to grow past: past it
        the wesen are not short of pasture, they are short of world."""
        clock = self.clock
        radius = self.homeRange
        home = self.home
        length = self.length
        seen = 1
        for uid, rec in self.ledger.peers.items():
            if uid == self.uid or clock - rec[3] > self.CENSUS_MEMORY:
                continue
            if manhattan(home, rec[2], length) <= radius:
                seen += 1
        if seen < 3:
            # nothing to extrapolate from: a wesen standing alone must
            # not conclude that the world is full
            return self.census()
        # a manhattan disc of radius r holds 2 r^2 cells
        area = 2.0 * radius * radius
        return max(self.census(), int(seen * length * length / area))

    def crowded(self):
        """is anybody else grazing the ground this colony works?

        The seed stock only pays where the colony is alone with it: a
        cell kept at capacity for its seeds is exactly the cell a rabbit
        walks to first, so gardening in a crowd is a gift to the crowd.
        The alarms are what the colony knows about that, so this is a
        judgement made out of the network and not out of one pair of
        eyes."""
        clock = self.clock
        seen = 0
        for rec in self.ledger.threats.values():
            if clock - rec[2] < self.CROWD_MEMORY:
                seen += 1
                if seen >= self.CROWD_ALARMS:
                    return True
        return False

    def contested(self, tile):
        """what the alarms say about a patch of ground: how recently a
        stranger was seen there (fading over 60 turns), and whether it
        was one that could kill us.

        Both matter, and differently. A killer is a reason to work
        somewhere else. Anything else - a rabbit, a Dwarf too small to
        bother us - is a rival grazer, and a cell it will eat next week
        is not an investment: on contested ground the harvest rule
        drops to what a hungry wesen takes, because leaving the
        interest standing there is a gift to somebody else."""
        rec = self.ledger.threats.get(tile)
        if rec is None:
            return 0.0, False
        age = self.clock - rec[2]
        if age > self.THREAT_MEMORY:
            return 0.0, False
        killer = rec[1] * self.attackDamage() >= self.energy()
        return 1.0 - age / self.THREAT_MEMORY, killer

    def dangerous(self, tile):
        """how much a killer seen on that tile still counts"""
        weight, killer = self.contested(tile)
        return weight if killer else 0.0

    def scan(self):
        """the plan: pick the cell with the best energy per time.

        Cells a colleague has reserved are struck off, cells in somebody
        else's district count less, cells near a remembered killer count
        much less, and a cell that will be ripe in a few turns is still
        worth walking towards."""
        clock = self.clock
        pos = self.position()
        length = self.length
        half = length // 2
        px, py = pos[0], pos[1]
        homes = self.neighbourHomes()[:8]
        self.neighbours = len(homes)
        energy = self.energy()
        keep = self.reserve()
        reach = max(self.targetRange, self.homeRadius)
        walk = self.targetRange
        home = self.home
        best = None
        bestValue = 0.0
        district = 0
        # what to leave standing depends on the body, not on the cell
        floor = harvestFloor(
            energy, self.starveLevel, self.bite, self.roots
        )
        # the pasture is only worth gardening where we are alone with it
        garden = not self.crowded()
        # Where cells stand close together a bite costs one step and
        # not nine, and nine steps is what the walking actually costs
        # in a pasture this thin. So a cell is worth what it holds
        # *and* what stands next to it: the colony's map is the only
        # way to see that, since a cluster is bigger than one eye.
        near = {}
        span = max(2, self.stepsPerTurn)
        for key in self.ledger.cells:
            tile = (key[0] // span, key[1] // span)
            near[tile] = near.get(tile, 0) + 1
        for key, rec in self.ledger.cells.items():
            # inlined manhattan distance on the torus: this loop runs
            # over the whole ledger and is the only expensive thing
            # this source does
            dx = key[0] - px
            if dx < 0:
                dx = -dx
            if dx > half:
                dx = length - dx
            if dx > reach:
                continue
            dy = key[1] - py
            if dy < 0:
                dy = -dy
            if dy > half:
                dy = length - dy
            distance = dx + dy
            if distance > reach:
                continue
            fertility = self.fert(key)
            # is this cell part of the ground I keep? The district is
            # what the colony's population policy is measured in, so it
            # is counted whether the cell is ripe or not, and it is
            # bounded by a radius as well as by the neighbours: a wesen
            # that has not yet heard of its neighbours must not conclude
            # that it owns the whole world
            rank = districtRank(key, home, homes, length)
            capacity = self.maxamount * fertility
            if not rank and clock - rec[1] < self.CELL_MEMORY:
                hx = key[0] - home[0]
                if hx < 0:
                    hx = -hx
                if hx > half:
                    hx = length - hx
                hy = key[1] - home[1]
                if hy < 0:
                    hy = -hy
                if hy > half:
                    hy = length - hy
                if hx + hy <= self.homeRadius:
                    district += 1
            if distance > walk:
                continue
            estimate = self.estimate(key, rec)
            body = estimate > capacity * self.BODY_FACTOR
            weight, killer = self.contested(
                (key[0] // self.tile, key[1] // self.tile)
            )
            if self.ledger.heldByOther(key, self.uid, clock):
                continue
            if (
                garden
                and energy >= keep
                and not body
                and not weight
                and seedStock(key, self.SEED_STOCK)
            ):
                continue  # the colony's seed corn
            bites = bitesAvailable(
                estimate, capacity, floor, self.bite, self.roots, body
            )
            wait = 0.0
            if bites <= 0:
                wait = self.ripeIn(
                    estimate, floor + self.bite, capacity, fertility
                )
                if wait > self.ripeWait:
                    continue
                bites = 1
            value = cellValue(
                bites * self.bite,
                distance,
                self.moveTime,
                self.eatTime,
                bites,
                wait,
                self.turnTime,
            )
            if rec[0] < 0:
                value *= self.HEARSAY  # nobody has been close to it
            # an old report is worth less than a new one, and not only
            # because the cell has grown since: in a shared world
            # somebody else has probably been there. This is what makes
            # the network pay - a colleague's news from three turns ago
            # beats my own memory of forty turns ago
            value *= self.STALE ** min(200, clock - rec[1])
            value *= 1.0 + self.CLUSTER_BONUS * min(
                self.CLUSTER_CAP,
                near.get((key[0] // span, key[1] // span), 1) - 1,
            )
            if rank:
                value *= self.OUTSIDE_PENALTY**rank
            if killer:
                value *= 1.0 - 0.8 * weight
            if value > bestValue:
                bestValue = value
                best = key
        self.districtCells = district
        # a slow average of it, so that a shrinking pasture can be told
        # from a bad turn: the colony must stop growing while the ground
        # it lives off is going backwards, and there is no other way to
        # notice that than to watch one's own district over time
        if self.pastureEma <= 0:
            self.pastureEma = float(district)
        else:
            self.pastureEma += self.PASTURE_MEMORY * (
                district - self.pastureEma
            )
        self.lastPlan = clock
        if best is not None:
            self.target = best
            self.targetSince = clock
            self.ledger.hold(best, self.uid, clock)
            self.count("targets")
            self.count("target distance", manhattan(pos, best, length))
        else:
            self.target = None
            self.count("no target")
        return best

    def targetStale(self):
        """a plan is worth keeping until the world contradicts it"""
        if self.target is None:
            return True
        rec = self.ledger.cells.get(self.target)
        if rec is None:
            return True
        if rec[2] > self.targetSince:  # somebody bit it after we chose
            return True
        if self.clock - self.targetSince > 3 * self.REPLAN:
            return True
        return False

    # --- acting ----------------------------------------------------------

    def foodHere(self, view):
        pos = self.position()
        return [
            o
            for o in view
            if o["type"] == "food"
            and o["position"][0] == pos[0]
            and o["position"][1] == pos[1]
        ]

    def graze(self, view):
        """eat on this cell as far as the harvest rule allows"""
        eaten = 0
        for food in self.foodHere(view):
            energy = food["energy"]
            pos = food["position"]
            capacity = self.capacityAt(pos)
            body = energy > capacity * self.BODY_FACTOR
            weight, killer = self.contested(
                (pos[0] // self.tile, pos[1] // self.tile)
            )
            keep = self.reserve()
            if (
                not body
                and not weight
                and self.energy() >= keep
                and not self.crowded()
                and seedStock((pos[0], pos[1]), self.SEED_STOCK)
            ):
                continue
            while self.time() >= self.eatTime:
                floor = harvestFloor(
                    self.energy(),
                    self.starveLevel,
                    self.bite,
                    self.roots,
                )
                if (
                    bitesAvailable(
                        energy,
                        capacity,
                        floor,
                        self.bite,
                        self.roots,
                        body,
                    )
                    <= 0
                ):
                    break
                try:
                    if not self.Eat(food["id"]):
                        break
                except RuleException:
                    break
                energy = max(0, energy - self.bite)
                eaten += 1
                self.ate += 1
                self.count("bites")
                if energy <= self.roots:
                    self.ledger.lostCell((pos[0], pos[1]))
                    break
                self.ledger.bitCell((pos[0], pos[1]), energy, self.clock)
                self.harvest = (pos[0], pos[1])
        if eaten and self.target == (
            self.position()[0],
            self.position()[1],
        ):
            self.target = None
        return eaten

    def travel(self, view):
        """walk towards the plan, eating what the plan is made of"""
        for _ in range(4):
            if self.time() < self.moveTime:
                return
            if (
                self.targetStale()
                or self.clock - self.lastPlan >= self.REPLAN
            ):
                self.scan()
            if self.target is None:
                return
            pos = self.position()
            distance = manhattan(pos, self.target, self.length)
            if distance == 0:
                if not self.graze(view):
                    # the plan was made on a cell that is not there any
                    # more: strike it off and pick another
                    self.count("empty arrival")
                    self.ledger.lostCell(self.target)
                self.target = None
                continue
            # time carries over to the next turn (up to `max`), so the
            # only thing to do with it is to get there sooner
            steps = min(distance, self.time() // self.moveTime)
            if steps <= 0:
                return
            before = tuple(self.position())
            self.Move(
                stepVector(pos, self.target, self.length, int(steps))
            )
            if tuple(self.position()) == before:
                return
            self.count("steps", int(steps))
            if manhattan(self.position(), self.target, self.length) == 0:
                # ids from this turn's view stay valid all turn, but
                # they only cover 12 cells around where the turn began:
                # a longer walk has to pay for a fresh look
                if not self.graze(view) and self.time() >= (
                    self.closerTime + self.eatTime
                ):
                    fresh = self.closerLook()
                    if fresh:
                        view = fresh
                        self.readView(fresh)
                        if not self.graze(fresh):
                            self.count("empty arrival")
                self.target = None

    def improve(self, view):
        """what to do with time that is left over: plant, or look"""
        if (
            self.time() >= self.vomitTime
            and self.energy() > self.PLANT_FACTOR * self.reserve()
            and not self.foodHere(view)
            and self.fert(self.position()) > self.PLANT_GROUND
            and self.plantable()
        ):
            if self.Vomit(self.plantEnergy):
                self.count("planted")
                self.ledger.sawCell(
                    tuple(self.position()), self.plantEnergy, self.clock
                )
                return
        if self.time() >= self.lookTime + self.castTime:
            wide = self.look()
            if wide:
                self.readWide(wide)
                self.count("looks")

    def plantable(self):
        """a seed only grows where the neighbourhood is neither empty
        of food nor crowded (see Food.growth): the bell around a density
        of one full cell within range.seed"""
        pos = self.position()
        total = 0.0
        for key, rec in self.ledger.cells.items():
            if chebyshev(pos, key, self.length) <= self.seedRange:
                total += max(0.0, self.estimate(key, rec))
        density = total / self.maxamount
        return density < self.plantDensity

    # --- neighbours ------------------------------------------------

    def wouldAttack(self, other):
        """does that source strike a wesen like me?

        For the two that hunt by a fixed margin this is read from their
        own code (see CHASERS), which is a claim about *them* and not
        about the rules. For everybody else - and for any source written
        after this one - the test is derived from the config: they
        strike whatever their attack would kill."""
        source = other["source"]
        if source in HARMLESS:
            return False
        energy = other["energy"]
        if source in CHASERS:
            floor, margin = CHASERS[source]
            return energy > floor and self.energy() <= energy + margin
        # everything else (Vetinari, Weatherwax, LuTze, anything new)
        # strikes what it can kill
        return energy * self.attackDamage() >= self.energy()

    def alarm(self, threats):
        clock = self.clock
        for o in threats:
            pos = o["position"]
            self.ledger.sawThreat(
                (pos[0] // self.tile, pos[1] // self.tile),
                o["source"],
                o["energy"],
                clock,
                pos,
            )

    def defend(self, threats, view):
        """kill a cheap thief on my own cell, run from anything that can
        kill me. Returns True if the turn is spent on it."""
        pos = self.position()
        mine = self.energy()
        killers = []
        for o in threats:
            distance = chebyshev(pos, o["position"], self.length)
            reach = (
                self.chaserReach
                if o["source"] in CHASERS
                else self.threatReach
            )
            if distance <= reach and self.wouldAttack(o):
                killers.append(o)
        if killers:
            self.publish(force=True)
            near = min(
                chebyshev(pos, o["position"], self.length) for o in killers
            )
            escape = self.eatTime + self.stepsPerTurn * self.moveTime
            if near > self.stepsPerTurn and self.time() >= escape:
                # it cannot reach me this turn: take the bite I came
                # for and run afterwards, with what is left
                self.graze(view)
            steps = self.time() // self.moveTime
            if steps > 0:
                direction = fleeVector(
                    pos,
                    [tuple(o["position"]) for o in killers],
                    self.length,
                    int(steps),
                )
                if direction:
                    self.Move(direction)
                    self.count("fled")
            self.target = None
            return True
        for o in threats:
            if (
                o["position"][0] == pos[0]
                and o["position"][1] == pos[1]
                and self.time() >= self.attackTime
                and o["energy"] * self.attackDamage() < mine
                and o["energy"] * self.attackCost()
                < self.KILL_SHARE * mine
            ):
                try:
                    self.Attack(o["id"])
                    self.count("kills")
                except RuleException:
                    pass
                break
        return False

    def relieve(self, friends):
        """feed a colleague that is about to starve on my own cell: a
        death by starvation costs the colony the whole body, and the
        map it was carrying"""
        if (
            self.energy() < 2 * self.reserve()
            or self.time() < self.donateTime
        ):
            return
        pos = self.position()
        for o in friends:
            if (
                o["energy"] < self.starveLevel
                and o["position"][0] == pos[0]
                and o["position"][1] == pos[1]
            ):
                try:
                    self.Donate(int(self.reserveBase), o["id"])
                    self.count("donated")
                except RuleException:
                    pass
                return

    # --- the colony ------------------------------------------------------

    def childHome(self, split):
        """where the next wesen should keep house.

        Splitting a district: the far end of the ground I work, so the
        two halves share it. A pioneer: the most fertile direction that
        no colleague's home is near, biased towards pasture we know of."""
        pos = self.position()
        length = self.length
        if split:
            far = None
            best = 0
            for key, rec in self.ledger.cells.items():
                if self.clock - rec[1] > self.CELL_MEMORY:
                    continue
                distance = manhattan(self.home, key, length)
                if (
                    2 * self.stepsPerTurn < distance <= self.targetRange
                    and distance > best
                ):
                    best = distance
                    far = key
            if far is not None:
                return [far[0], far[1]]
        homes = [
            rec[2]
            for uid, rec in self.ledger.peers.items()
            if uid != self.uid and self.clock - rec[3] < self.CENSUS_MEMORY
        ] + [tuple(self.home)]
        best = None
        bestScore = None
        for dx, dy in (
            (1, 0),
            (-1, 0),
            (0, 1),
            (0, -1),
            (1, 1),
            (1, -1),
            (-1, 1),
            (-1, -1),
        ):
            for reach in self.siteReach:
                site = (
                    (pos[0] + dx * reach) % length,
                    (pos[1] + dy * reach) % length,
                )
                near = min(
                    (manhattan(site, h, length) for h in homes),
                    default=999,
                )
                if near < self.siteSpacing:
                    continue
                tile = (site[0] // self.tile, site[1] // self.tile)
                known = sum(
                    1
                    for key in self.ledger.cells
                    if chebyshev(site, key, length) <= self.tile
                )
                # good ground, pasture the colony already knows of,
                # room from the neighbours, no killer remembered
                # there, and near rather than far
                score = (
                    3.0 * self.fert(site)
                    + 0.05 * known
                    + 0.004 * near
                    - 2.0 * self.dangerous(tile)
                    - 0.01 * reach
                )
                if bestScore is None or score > bestScore:
                    bestScore = score
                    best = site
        return list(best) if best else [pos[0], pos[1]]

    def shrinking(self):
        """is the ground this wesen works getting poorer?

        The pasture is the colony's income, and a colony that keeps
        growing while the pasture shrinks eats its own future - that is
        how the swarms in this game die. Each wesen watches its own
        district against a slow average of itself; nobody has to see
        the whole world for the colony to stop."""
        return (
            self.pastureEma > 0
            and self.districtCells < self.PASTURE_FALL * self.pastureEma
        )

    def maybeReproduce(self):
        """split when the district feeds more than one, or when old age
        would otherwise end the line (splitting resets the age)"""
        if self.time() < self.reproduceTime + self.talkTime:
            return
        energy = self.energy()
        if energy < self.minBirthEnergy() + self.bite:
            return
        if self.colonySize() >= self.MAX_COLONY or self.shrinking():
            # the world is full, or the ground is going backwards.
            # Then not even old age is a reason to split: the wesen
            # dies and its body goes back into the pasture, which is
            # where the colony's next meal comes from, and the colony
            # shrinks back to what the land carries.
            return
        # splitting resets the age, so a wesen that is about to die of
        # old age splits whatever the pasture says: the line survives
        old = self.age() > self.maxage - 2 * self.cycleTurns
        keep = self.reserve()
        split = self.districtCells >= 2 * self.cellsPerWesen
        if not old:
            if energy < keep + self.minBirthEnergy() + 4 * self.bite:
                return
            if len(self.crowd) > 1:
                return  # two colleagues within twelve cells is crowded
            # The population policy, and all of it. While the colony
            # is small, and on the frontier - no colleague within reach
            # of my district - a child is always worth making, because
            # the ground next door is nobody's and an empty world is
            # not worth being careful in. Inside a grown colony the
            # ground is shared, so a child needs a district that feeds
            # it: the Voronoi districts shrink as colleagues move in,
            # and the colony therefore stops growing exactly where the
            # pasture stops paying. The last line is the world itself.
            if (
                self.census() > self.FREE_GROWTH
                and self.neighbours
                and self.districtCells < self.cellsPerWesen
            ):
                return
        home = self.childHome(split)
        childId = self.Reproduce()
        if not childId:
            return
        self.count("births")
        uid = f"{childId:x}:{self.clock}"
        role = "grazer" if split else "pioneer"
        self.brief(childId, uid, home, role)

    def bequeath(self):
        """a wesen at the end of its life leaves its body to the colony.

        Death by old age drops a blob only if there is vomit time left
        over, and death by starvation drops nothing at all, so a wesen
        that may not split (the world is full) spends its last turn
        turning itself into food on its own ground, where a colleague
        will find it - the ledger says so - instead of taking a few
        hundred energy out of the game."""
        if self.age() < self.maxage - 1:
            return False
        energy = self.energy()
        if energy <= 0 or self.time() < self.vomitTime:
            return False
        if self.Vomit(energy):
            self.count("bequeathed")
            self.ledger.sawCell(tuple(self.position()), energy, self.clock)
            self.publish(force=True)
            return True
        return False

    def settle(self):
        """a pioneer walks to its district before it starts working"""
        if self.role != "pioneer":
            return
        if (
            manhattan(self.position(), self.home, self.length)
            <= self.settledRange
        ):
            self.role = "grazer"
            self.settledAt = self.clock
            self.count("settled")
            return
        # walk, but eat anything ripe that happens to be on the way
        steps = self.time() // self.moveTime
        if steps <= 1:
            return
        self.Move(
            stepVector(
                self.position(), self.home, self.length, int(steps) - 1
            )
        )
        self.target = None

    def reconsider(self):
        """a district that has stopped paying is worth leaving.

        The colony's map is full of ground nobody keeps; a wesen whose
        own is bare moves rather than starve on it, which is the other
        half of the population policy: the colony not only stops growing
        where the pasture is poor, it drains away from there."""
        if self.role != "grazer" or self.clock % self.RECONSIDER_EVERY:
            return
        if self.clock - self.settledAt < self.SETTLE_GRACE:
            return  # give the ground (and the map of it) a chance first
        if self.districtCells >= self.cellsPerWesen // 3:
            return
        site = self.childHome(False)
        if (
            site
            and manhattan(site, self.home, self.length) > self.siteSpacing
        ):
            self.home = list(site)
            self.role = "pioneer"
            self.count("moved")

    def keepHouse(self):
        """the home drifts towards what we actually harvest, so the
        districts follow the pasture (Lloyd relaxation)"""
        if self.harvest is not None:
            self.home = drift(self.home, self.harvest, self.length)
            self.harvest = None
        elif (
            self.target is not None
            and manhattan(self.home, self.target, self.length)
            > self.targetRange
        ):
            self.home = drift(self.home, self.target, self.length)

    # --- turn ------------------------------------------------------

    def count(self, key, n=1):
        """a debug counter, per wesen: `local/probe_rw.py` adds them up
        over the colony. Even counters would be shared state on the
        class, and a source that may write numbers into a shared dict
        can write anything into it."""
        self.stats[key] = self.stats.get(key, 0) + n

    def wakeUp(self):
        """a founder has no papers: it names itself and starts the
        calendar. Engine ids are addresses and get reused, so a uid is
        the address *and* the turn it was issued."""
        if self.uid is None:
            self.uid = f"F{self.id():x}:{self.clock}"
        if self.home is None:
            self.home = list(self.position())
        if self.role == "founder":
            self.role = "grazer"

    def main(self):
        """one turn. Anything that goes wrong here is reported by the
        engine (`World.noteFault`), which prints each distinct error
        once with its traceback and skips the turn."""
        self.turn()

    def turn(self):
        self.clock += 1
        self.wakeUp()
        self.count("turns")
        self.ate = 0
        view, threats, friends = [], [], []
        if self.time() >= self.closerTime:
            # a look with too little time returns an empty list, which
            # would read as "everything around me is gone"
            view = self.closerLook()
            threats, friends = self.readView(view)
        if threats:
            self.alarm(threats)
            if self.defend(threats, view):
                return
        self.publish()
        self.graze(view)
        self.relieve(friends)
        self.maybeReproduce()
        if self.bequeath():
            return
        if self.role == "pioneer":
            self.settle()
        else:
            self.travel(view)
        self.improve(view)
        self.keepHouse()
        self.reconsider()
        if not self.ate:
            self.count("hungry turns")
        if self.clock % self.PRUNE_EVERY == 0:
            self.ledger.prune(self.clock, self.position(), self.length)

    # --- persistence -----------------------------------------------

    def persist(self):
        return {
            "uid": self.uid,
            "clock": self.clock,
            "home": self.home,
            "role": self.role,
            "settledAt": self.settledAt,
            "pastureEma": self.pastureEma,
            "target": list(self.target) if self.target else None,
            "ledger": self.ledger.persist(),
        }

    def restore(self, obj):
        # the engine hands the whole persisted object; our own state is
        # the part `persist` returned
        obj = (obj or {}).get("wesensource") or {}
        if not obj:
            return
        self.uid = obj.get("uid")
        self.clock = obj.get("clock", 0)
        home = obj.get("home")
        self.home = list(home) if home else None
        self.role = obj.get("role", "grazer")
        self.settledAt = obj.get("settledAt", 0)
        self.pastureEma = obj.get("pastureEma", 0.0)
        target = obj.get("target")
        self.target = tuple(target) if target else None
        self.ledger.restore(obj.get("ledger", {}))
        self.briefed = True
