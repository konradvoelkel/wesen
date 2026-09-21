"""Vetinari - the Patrician. Rules by patience, economics and first strike.

Strategy (derived from the rules as implemented in objects/wesen.py and
objects/food.py):

* The only sustainable income is gardening: ``Vomit(1)`` turns one energy
  into a food patch that grows by ~0.5 energy per turn for up to 1000
  turns, independent of its size. Time (25 per turn), not energy, is the
  scarce resource, so many small patches are the economy.
* Every wesen keeps a home cell ("estate") and plants there, so the garden
  is compact, cheap to harvest and easy to defend. Each wesen tends a
  bounded number of patches; surplus time is spent harvesting into the
  body, which is what the score (energy per source) actually counts.
* Income is reinvested into reproduction as soon as both halves are safe,
  because every additional wesen means 25 more time units per turn.
  Crowded estates send newborns to found a new estate out of sight, and
  the colony stops growing at a size that keeps the simulation responsive.
* Old age is cured by reproducing (which resets the age); if the colony is
  full, the child donates everything back to its parent and vanishes.
* Defense: an attacker loses half of the victim's energy, so a fat wesen is
  practically immune. Enemies on the estate are struck first whenever that
  kills them and leaves us alive; enemies that could kill us make us bulk
  up from the garden or, failing that, walk away for a while.
* Big foreign food (dead enemies, enemy gardens) nearby is fetched when the
  energy per step is clearly better than gardening.
"""

from math import cos, pi, sin
from random import choice, uniform

from ...colony import Colony
from ...defaultwesensource import DefaultWesenSource
from ...point import getShortestTranslation


class WesenSource(DefaultWesenSource):
    # --- shared knowledge of the whole colony (class attributes) ---------
    worldTurn = 0  # estimate of the current world turn
    alive = {}  # own id -> last world turn seen (children at birth)
    homes = set()  # cells that carry our gardens
    sacrifices = {}  # child id -> parent id (age recovery, see tendGarden)
    threat = 0  # strongest enemy energy seen recently
    threatSeenTurn = 0
    chasers = {}  # known chaser source -> (energy last seen, turn)
    dangerZones = {}  # grid cell -> turn a lethal enemy was seen there
    homeScares = {}  # home cell -> turn count of recent close calls
    claimedFood = {}  # food id -> turn, so only one forager goes per food

    # --- tunables --------------------------------------------------------
    RESERVE = 20  # never plant below this energy
    LOW_ENERGY = 80  # harvest until we are above this
    PATCHES_PER_WESEN = 50  # garden size per wesen on a cell
    MIN_HARVEST_ENERGY = 15  # do not bother with smaller patches
    EXPIRY_AGE = 880  # always harvest before food dies at age 1000
    SAFE_BASE = 200  # minimal energy each half needs after reproducing
    THREAT_FACTOR = 1.6  # be this much stronger than the strongest enemy
    THREAT_DECAY_TURNS = 300
    # the population rule is local (see roomForAnother); this is only
    # a ceiling for the machine, since every wesen costs simulation time
    MAX_COLONY = 56
    MAX_PER_CELL = 6  # newborns beyond this found a new estate
    DISTRICT_RANGE = 60  # how far from home the ground we keep reaches
    WESEN_PER_DISTRICT = 3  # ... and how many of us it feeds
    ESTATE_DISTANCE = 14  # new estates outside closerLook range (12)
    OLD_AGE_MARGIN = 4  # reproduce this many turns before maxage
    FLEE_DISTANCE = 9  # react to killers within this distance
    FORAGE_MIN_ENERGY = 40  # foreign food worth walking to
    FORAGE_ENERGY_PER_CELL = 25  # ... if it yields at least this per cell
    MAX_FORAGE_DISTANCE = 12

    # Sources that strike anything up to their own energy plus a fixed
    # margin, known by name so bulkTarget() can demand exactly the margin
    # that matters instead of an arbitrary multiple. The old Dwarf and
    # Nightwatch were such (their helper.py: acceptableEnemy /
    # minimumEnergyToFight); since the 2026-09-21 rewrite both strike
    # only what they can kill outright, which is what everybody not
    # named here is assumed to do, so the table is empty.
    CHASER_MARGIN = {}
    DANGER_GRID = 8  # cell size of the danger-memory grid
    DANGER_DECAY_TURNS = 200  # forget a danger sighting after this long
    HOME_DANGER_LIMIT = 2  # relocate after this many scares at home

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
        cls.PATCHES_PER_WESEN = 2
        cls.MIN_HARVEST_ENERGY = sustainable
        cls.FORAGE_MIN_ENERGY = sustainable
        cls.FORAGE_ENERGY_PER_CELL = 3
        # upkeep is proportional to the body, so a thin wesen is cheap
        # to run and many mouths capture more pasture than few fat ones
        cls.SAFE_BASE = 400

    def __init__(self, infoAllSource):
        DefaultWesenSource.__init__(self, infoAllSource)
        type(self).tuneForFoodRule(self)
        self.infoAllSource = infoAllSource
        self.home = None
        self.trip = None  # position of foreign food we are fetching
        # the colony's book, kept by talking: a class attribute is
        # genetic information now (see isolation.py), so the roll, the
        # estates and the danger map below are this wesen's own and
        # reach the others only if they are broadcast
        self.colony = Colony(
            type(self).SIGIL, self.worldlength, 80, source=self.source
        )
        self.uid = None
        self.news = {}
        self.said = -99
        self.sacrificeFor = None  # a parent to give everything back to
        self.bornTurn = type(self).worldTurn
        self.turnsLived = 0
        self.maxAge = self.infoWesen["maxage"]
        self.plantCost = self.infoTime["vomit"]
        self.eatCost = self.infoTime["eat"]
        self.moveCost = self.infoTime["move"]
        self.attackCost = self.infoTime["attack"]
        self.reproCost = self.infoTime["reproduce"]
        self.donateCost = self.infoTime["donate"]
        self.lookCost = self.infoTime["closerlook"]

    def __str__(self):
        return "<Lord Vetinari, Patrician of Ankh-Morpork>"

    # --- persistence -----------------------------------------------------

    def persist(self):
        return {
            "home": self.home,
            "trip": self.trip,
            "uid": self.uid,
            "colony": self.colony.persist(),
        }

    def restore(self, obj):
        state = obj.get("wesensource", {}) or {}
        self.home = state.get("home", self.home)
        self.trip = state.get("trip", self.trip)
        self.uid = state.get("uid")
        self.colony.restore(state.get("colony"), uidType=str)
        self.colony.uid = self.uid
        if self.home is not None:
            type(self).homes.add(tuple(self.home))

    # --- bookkeeping -----------------------------------------------------

    SIGIL = "vetinari/1"  # our messages, and nobody else's
    SAY_EVERY = 4  # turns between two broadcasts with nothing new

    def tick(self):
        """keep the calendar, and the roll of who has been heard from.

        Both used to be class attributes, which every wesen of the
        source shared without anybody saying anything. They are this
        wesen's own now (see isolation.py) and are kept in step by
        talking: see `sayWhatISaw`."""
        cls = type(self)
        self.turnsLived += 1
        if self.uid is None:
            # engine ids are addresses and get reused: a name is the
            # address and the turn it was issued
            self.uid = f"{self.id():x}:{self.bornTurn}"
            self.colony.uid = self.uid
        self.colony.tick()
        self.colony.sync(self.bornTurn + self.turnsLived)
        cls.worldTurn = self.colony.clock
        self.colony.note(
            self.uid, self.home or self.position(), self.energy()
        )
        if self.turnsLived % 50 == 0:
            self.colony.forget()

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
        stand: nobody hears the whole colony, and a population rule
        measured against the raw count never stops growing."""
        return self.colony.census(self.position())

    def sayWhatISaw(self):
        """one broadcast a turn: the roll, the estates that have been
        founded or given up, and where something dangerous was seen."""
        cls = type(self)
        if self.time() < self.infoTime["broadcast"]:
            return
        stale = cls.worldTurn - self.said
        if not self.news and stale < cls.SAY_EVERY:
            return
        news = self.news
        self.news = {}
        self.said = cls.worldTurn
        self.Broadcast(
            self.colony.say(self.position(), self.energy(), news)
        )

    def tell(self, kind, item):
        self.news.setdefault(kind, []).append(item)

    def Receive(self, message):
        """what a colleague saw, or a parent's last wish"""
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
                self.sacrificeFor = message.get("parent")
            return
        news = self.colony.hear(message)
        if not news:
            return
        for x, y in news.get("h", ()):
            cls.homes.add((x, y))
        for x, y in news.get("g", ()):
            cls.homes.discard((x, y))
        for x, y, turn in news.get("d", ()):
            if cls.dangerZones.get((x, y), -1) < turn:
                cls.dangerZones[(x, y)] = turn
        for src, energy, turn in news.get("c", ()):
            old = cls.chasers.get(src)
            if old is None or old[1] < turn:
                cls.chasers[src] = (energy, turn)

    def noteEnemies(self, enemies):
        cls = type(self)
        if not enemies:
            return
        strongest = max(e["energy"] for e in enemies)
        if (
            strongest >= cls.threat
            or cls.worldTurn - cls.threatSeenTurn > cls.THREAT_DECAY_TURNS
        ):
            cls.threat = strongest
            cls.threatSeenTurn = cls.worldTurn
        for e in enemies:
            src = e["source"]
            if src in cls.CHASER_MARGIN:
                cls.chasers[src] = (e["energy"], cls.worldTurn)
                self.tell("c", (src, e["energy"], cls.worldTurn))
            if self.canKillMe(e["energy"]):
                cell = self.dangerCell(e["position"])
                cls.dangerZones[cell] = cls.worldTurn
                self.tell("d", (cell[0], cell[1], cls.worldTurn))

    @staticmethod
    def dangerCell(pos):
        grid = WesenSource.DANGER_GRID
        return (pos[0] // grid, pos[1] // grid)

    def isDangerous(self, pos):
        cls = type(self)
        turn = cls.dangerZones.get(self.dangerCell(pos))
        if turn is None:
            return False
        return cls.worldTurn - turn <= cls.DANGER_DECAY_TURNS

    def chaserFloor(self):
        """energy needed right now to survive every known chaser's fixed
        attack margin (see CHASER_MARGIN), if any was seen recently. This
        is a precise, *reachable* target for the immediate "can I outgrow
        this threat instead of running" check in handleThreats - it must
        stay out of safeEnergy()/winterReserve(), which gate reproduction:
        a colony that only breeds once every wesen is chaser-proof never
        breeds once a fat Nightwatch has been sighted, which is worse
        than the risk it is trying to avoid."""
        cls = type(self)
        best = 0
        for src, (energy, turn) in cls.chasers.items():
            if cls.worldTurn - turn > cls.THREAT_DECAY_TURNS:
                continue
            need = energy + cls.CHASER_MARGIN[src]
            if need > best:
                best = need
        return best

    def safeEnergy(self):
        """energy a single wesen should keep given the known threats"""
        cls = type(self)
        threat = cls.threat
        if cls.worldTurn - cls.threatSeenTurn > cls.THREAT_DECAY_TURNS:
            threat = 0
        return max(cls.SAFE_BASE, int(threat * cls.THREAT_FACTOR))

    # --- movement helpers ------------------------------------------------

    @staticmethod
    def viewDist(a, b):
        """distance in the max metric for positions from one look()
        (the engine's range iterator does not wrap, so no torus logic)"""
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        if dx < 0:
            dx = -dx
        if dy < 0:
            dy = -dy
        return dx if dx > dy else dy

    def stepTowards(self, target, maxCells):
        """move up to maxCells cells towards target (torus aware)"""
        moved = 0
        target = list(target)
        while moved < maxCells and self.time() >= self.moveCost:
            pos = self.position()
            if pos == target:
                break
            dx, dy = getShortestTranslation(pos, target, self.worldlength)
            # diagonal moves cost double, so always go straight
            if abs(dx) >= abs(dy):
                step = [1 if dx > 0 else -1, 0]
            else:
                step = [0, 1 if dy > 0 else -1]
            if not self.Move(step):
                break
            moved += 1
        return moved

    def maxMoveBudget(self):
        """cells we could still move this turn if we spent everything on
        it; a wesen fleeing for its life should not stop at the leisurely
        3-cell pace used for grazing, since a hunter closing the gap is
        timed against exactly that budget (see handleThreats)"""
        return max(1, int(self.time() // self.moveCost))

    def stepAway(self, fromPos, maxCells):
        """move up to maxCells cells away from fromPos. When both axes are
        close, the escape axis is picked at random so a pursuer cannot
        always predict which straight line we will run along."""
        pos = self.position()
        dx, dy = getShortestTranslation(pos, fromPos, self.worldlength)
        if dx == 0 and dy == 0:
            dx, dy = choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
        if abs(dx) == 0 or abs(dy) == 0:
            preferX = abs(dx) >= abs(dy)
        elif abs(abs(dx) - abs(dy)) <= 2:
            preferX = choice([True, False])
        else:
            preferX = abs(dx) >= abs(dy)
        if preferX:
            step = [-1 if dx > 0 else 1, 0]
        else:
            step = [0, -1 if dy > 0 else 1]
        moved = 0
        while moved < maxCells and self.Move(step):
            moved += 1
        return moved

    # --- eating / fighting helpers ---------------------------------------

    def eat(self, patches, food):
        """eat one patch and drop it from the local list"""
        if self.time() < self.eatCost:
            return False
        ok = self.Eat(food["id"])
        if food in patches:
            patches.remove(food)
        return ok

    def harvestUntil(self, patches, targetEnergy):
        """eat the richest patches until energy >= targetEnergy"""
        while (
            patches
            and self.energy() < targetEnergy
            and self.time() >= self.eatCost
        ):
            self.eat(patches, patches[0])

    def canKill(self, enemyEnergy):
        """an attack kills if 0.75 * mine >= enemy; we lose 0.5 * enemy"""
        mine = self.energy()
        return (
            0.75 * mine >= enemyEnergy
            and mine - 0.5 * enemyEnergy > type(self).RESERVE
        )

    def canKillMe(self, enemyEnergy):
        return 0.75 * enemyEnergy >= self.energy()

    # --- the turn --------------------------------------------------------

    def main(self):
        cls = type(self)
        self.tick()
        pos = self.position()
        if self.home is None:
            self.home = list(pos)
            cls.homes.add(tuple(pos))
            self.tell("h", (pos[0], pos[1]))

        # a child born only to cure its parent's old age gives back
        # everything and vanishes (see tendGarden)
        if self.sacrificeFor is not None:
            parent, self.sacrificeFor = self.sacrificeFor, None
            if self.Donate(self.energy(), parent):
                return

        view = self.closerLook()
        if not view and self.time() < self.lookCost:
            return

        foodsHere = [
            o for o in view if o["type"] == "food" and o["position"] == pos
        ]
        foodsHere.sort(key=lambda f: f["energy"], reverse=True)
        enemies = [
            o
            for o in view
            if o["type"] == "wesen" and o["source"] != self.source
        ]
        enemiesHere = [e for e in enemies if e["position"] == pos]
        friendsHere = 1 + sum(
            1
            for o in view
            if o["type"] == "wesen"
            and o["source"] == self.source
            and o["position"] == pos
        )
        self.noteEnemies(enemies)
        self.sayWhatISaw()

        # 1. immediate danger: enemies on my cell or killers approaching
        if enemies:
            if self.handleThreats(enemies, enemiesHere, foodsHere):
                return  # we ran away, nothing else to do this turn

        # 2. survival: never run dry while food is under our feet
        self.harvestUntil(foodsHere, cls.LOW_ENERGY)

        # under the life food rule the garden is a pasture (see the
        # herding section), so the whole estate economy is replaced
        if cls.lifeTuned:
            return self.grazerTurn(view, foodsHere, friendsHere)

        # 3. newborn on a crowded estate: found a new one out of sight
        if (
            pos == self.home
            and friendsHere > cls.MAX_PER_CELL
            and self.turnsLived <= 2
        ):
            self.home = self.pickNewHome()
            cls.homes.add(tuple(self.home))
            self.tell("h", (self.home[0], self.home[1]))

        # 4. trips: fetching foreign food, or walking home
        if self.trip is not None:
            if self.continueTrip(foodsHere):
                return
        elif pos != self.home:
            self.stepTowards(self.home, 3)
            return
        else:
            trip = self.findForageTarget(view)
            if trip is not None:
                self.trip = trip
                self.stepTowards(trip, 3)
                return
            if (
                cls.lifeTuned
                and self.turnsLived % 5 == 0
                and not [
                    f
                    for f in foodsHere
                    if f["energy"] >= cls.MIN_HARVEST_ENERGY
                ]
            ):
                # life rule: the pasture here is grazed bare, move on
                self.home = self.pickNewHome()
                cls.homes.add(tuple(self.home))
                self.tell("h", (self.home[0], self.home[1]))
                self.stepTowards(self.home, 3)
                return

        # 5. garden work at home
        self.tendGarden(foodsHere, friendsHere)

    # --- sub-behaviours ------------------------------------------------

    def bulkTarget(self, dangerousEnemies):
        """energy worth trying to reach right now to stop being killable
        by the given enemies. Precise (energy + CHASER_MARGIN) for a
        known chaser, since that is actually reachable in a turn or two
        of grazing; a flat multiple otherwise, as a rough deterrent."""
        cls = type(self)
        target = 0
        for e in dangerousEnemies:
            margin = cls.CHASER_MARGIN.get(e["source"])
            need = (
                e["energy"] + margin
                if margin is not None
                else e["energy"] * 2
            )
            if need > target:
                target = need
        return int(target) + 1

    def handleThreats(self, enemies, enemiesHere, foodsHere):
        """returns True if we fled (turn is over)"""
        cls = type(self)
        # enemies on the cell: get fat, then strike first (cheapest first)
        if enemiesHere:
            self.harvestUntil(
                foodsHere,
                max(self.bulkTarget(enemiesHere), cls.LOW_ENERGY),
            )
            for e in sorted(enemiesHere, key=lambda e: e["energy"]):
                if self.time() < self.attackCost:
                    break
                if self.canKill(e["energy"]):
                    self.Attack(e["id"])
            remaining = [
                e
                for e in enemiesHere
                if not self.canKill(e["energy"])
                and self.canKillMe(e["energy"])
            ]
            if remaining:
                # cannot win this: leave, come back later, as far as this
                # turn's time budget allows (a hunter's pursuit is timed
                # against our distance, not against a fixed walking pace)
                self.noteHomeScare()
                self.stepAway(
                    remaining[0]["position"], self.maxMoveBudget()
                )
                return True
        # killers nearby: bulk up from the garden if that is cheap, run if
        # not. Any enemy that could kill us is worth reacting to, however
        # weak it looks in isolation - a wesen low on energy dies just as
        # dead to a small attacker as to a big one.
        pos = self.position()
        killers = [
            e
            for e in enemies
            if e["position"] != pos
            and self.canKillMe(e["energy"])
            and self.viewDist(e["position"], pos) <= cls.FLEE_DISTANCE
        ]
        if killers:
            strongest = max(e["energy"] for e in killers)
            self.harvestUntil(foodsHere, self.bulkTarget(killers))
            if self.canKillMe(strongest) and not (
                0.75 * self.energy() >= strongest
            ):
                nearest = min(
                    killers,
                    key=lambda e: self.viewDist(e["position"], pos),
                )
                self.noteHomeScare()
                self.stepAway(nearest["position"], self.maxMoveBudget())
                return True
        return False

    def noteHomeScare(self):
        """count close calls at the current estate; a home that keeps
        attracting killers is being camped (e.g. a hunter stationed on a
        known garden) and is worth abandoning rather than defending"""
        cls = type(self)
        if self.home is None or self.position() != self.home:
            return
        count, turn = cls.homeScares.get(tuple(self.home), (0, 0))
        if cls.worldTurn - turn > cls.DANGER_DECAY_TURNS:
            count = 0
        cls.homeScares[tuple(self.home)] = (count + 1, cls.worldTurn)

    def pickNewHome(self, distance=None):
        """a cell ESTATE_DISTANCE away, on the most fertile ground of a
        few directions, and not a cell where something lethal was seen
        recently. The terrain is static (see biome.py), so this is the
        one thing about a place that is worth knowing in advance."""
        cls = type(self)
        pos = self.position()
        length = self.worldlength
        d = distance or cls.ESTATE_DISTANCE
        best, bestGround = None, -1.0
        fallback, fallbackGround = None, -1.0
        for _ in range(8):
            angle = uniform(0, 2 * pi)
            cand = (
                int(round(pos[0] + d * cos(angle))) % length,
                int(round(pos[1] + d * sin(angle))) % length,
            )
            if cand in cls.homes:
                continue
            ground = self.fertility(cand)
            if ground > fallbackGround:
                fallback, fallbackGround = cand, ground
            if self.isDangerous(cand):
                continue
            if ground > bestGround:
                best, bestGround = cand, ground
        chosen = best or fallback
        return list(chosen) if chosen else list(pos)

    def findForageTarget(self, view):
        cls = type(self)
        pos = self.position()
        homes = cls.homes
        best = None
        bestValue = 0
        minEnergy = cls.FORAGE_MIN_ENERGY
        for o in view:
            if o["energy"] < minEnergy or o["type"] != "food":
                continue
            fpos = o["position"]
            if fpos == pos or (fpos[0], fpos[1]) in homes:
                continue
            if o["id"] in cls.claimedFood:
                continue
            d = self.viewDist(fpos, pos)
            if d > cls.MAX_FORAGE_DISTANCE:
                continue
            value = o["energy"] / d
            if value >= cls.FORAGE_ENERGY_PER_CELL and value > bestValue:
                best, bestValue = o, value
        if best is None:
            return None
        cls.claimedFood[best["id"]] = cls.worldTurn
        if len(cls.claimedFood) > 500:
            old = cls.worldTurn - 100
            cls.claimedFood = {
                k: v for k, v in cls.claimedFood.items() if v > old
            }
        return list(best["position"])

    def continueTrip(self, foodsHere):
        """walk to the trip target, eat there, walk home.
        Returns True while busy."""
        cls = type(self)
        if self.position() != self.trip:
            self.stepTowards(self.trip, 3)
            if self.position() != self.trip:
                return True
            # arrived: what is here now?
            foodsHere = [
                o
                for o in self.closerLook()
                if o["type"] == "food" and o["position"] == self.position()
            ]
            foodsHere.sort(key=lambda f: f["energy"], reverse=True)
        worthwhile = [
            f for f in foodsHere if f["energy"] >= cls.FORAGE_MIN_ENERGY
        ]
        for f in worthwhile:
            if not self.eat(foodsHere, f):
                break
        if [f for f in foodsHere if f["energy"] >= cls.FORAGE_MIN_ENERGY]:
            return True  # more to eat next turn
        self.trip = None
        self.stepTowards(self.home, 3)
        return True

    # --- life food rule: herding -----------------------------------------
    # With food.rule = life the pasture, not a plantation, is the income:
    # a bite that leaves a cell about a third grown regrows fastest, and
    # a crowded garden decays. So a gardener herds instead of planting.

    GRAZE_RANGE = 12  # cells worth walking to for better pasture
    GRAZE_FLOOR = 0.35  # share of maxamount a bitten cell should keep
    GRAZE_STARVING = 60  # below this, even a bite that kills the cell

    def grazeFloor(self):
        """energy a bitten cell should keep. Growth is proportional to
        energy times the room left to grow, so a cell held around a
        third of its maximum regrows nearly as fast as it can, while a
        cell stripped to its roots hardly grows at all."""
        return int(self.infoFood["maxamount"] * type(self).GRAZE_FLOOR)

    def grazeWant(self):
        """energy a cell needs before a bite leaves it productive"""
        return self.grazeFloor() + (self.foodBite() or 0)

    def winterReserve(self):
        """body that carries this wesen to spring at its own burn rate"""
        base = self.safeEnergy()
        return base + int(self.upkeepOf(base) * self.turnsUntilSpring())

    def worthBiting(self, food):
        """a bite that leaves the cell productive is free income; a bite
        that leaves it bare but alive only while below the winter
        reserve; the last bite of a cell only when starving"""
        left = food["energy"] - self.foodYield(food)
        if left >= self.grazeFloor():
            return True
        if left > self.foodRoots():
            return self.energy() < self.winterReserve()
        return self.energy() < type(self).GRAZE_STARVING

    def bite(self, patches, food):
        """take one bite and keep the (smaller) food in the local view,
        so a rich cell can be bitten more than once per turn"""
        taken = self.foodYield(food)
        gone = self.foodKills(food)
        if not self.eat(patches, food):
            return 0
        if not gone:
            food["energy"] -= taken
            patches.append(food)
            patches.sort(key=lambda f: -f["energy"])
        return taken

    def grazeHere(self, patches):
        while patches and self.time() >= self.eatCost:
            food = patches[0]
            if food.get("id") is None or not self.worthBiting(food):
                break
            if not self.bite(patches, food):
                break

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
            if key in cls.homes or self.isDangerous(o["position"]):
                continue
            d = self.viewDist(o["position"], pos)
            if d <= near or d > cls.GRAZE_RANGE * 2:
                continue
            if bestDist is None or d < bestDist:
                best, bestDist = o, d
        return list(best["position"]) if best else None

    def bestPasture(self, view):
        """the cell in view worth walking to. Cells rich enough for a
        bite that leaves them productive come first, by energy per step;
        a poorer one is only a destination while we are starving, since
        walking to a cell we then refuse to bite wastes the turn."""
        cls = type(self)
        pos = self.position()
        want = self.grazeWant()
        best, bestValue = None, 0.0
        poor, poorValue = None, 0.0
        for o in view:
            if o["type"] != "food" or o["position"] == pos:
                continue
            key = (o["position"][0], o["position"][1])
            if key in cls.homes or self.isDangerous(o["position"]):
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

    def claimPasture(self, pos):
        """this cell feeds me, so it is my estate for now"""
        cls = type(self)
        if self.home is not None:
            cls.homes.discard(tuple(self.home))
            self.tell("g", (self.home[0], self.home[1]))
        self.home = list(pos)
        cls.homes.add((pos[0], pos[1]))
        self.tell("h", (pos[0], pos[1]))

    def cellIsCamped(self):
        """a home that keeps attracting killers is being watched (e.g. a
        hunter stationed on a known garden): worth abandoning rather than
        defending forever, since every visit risks another kill"""
        cls = type(self)
        if self.home is None:
            return False
        count, turn = cls.homeScares.get(tuple(self.home), (0, 0))
        return (
            count >= cls.HOME_DANGER_LIMIT
            and cls.worldTurn - turn <= cls.DANGER_DECAY_TURNS
        )

    def grazerTurn(self, view, foodsHere, friendsHere):
        """the life-rule replacement for tendGarden and the forage
        trips: follow the pasture, with the estate following the herd"""
        cls = type(self)
        pos = self.position()
        self.grazeHere(foodsHere)
        camped = pos == self.home and self.cellIsCamped()
        if (
            not camped
            and foodsHere
            and foodsHere[0]["energy"] >= self.grazeWant()
        ):
            self.claimPasture(pos)
        if camped:
            # a hunter is stationed here: the whole herd abandons the
            # cell, not just newborns, since staying just feeds it kills
            cls.homeScares.pop(tuple(self.home), None)
            self.home = self.pickNewHome(cls.ESTATE_DISTANCE * 2)
            cls.homes.add(tuple(self.home))
            self.tell("h", (self.home[0], self.home[1]))
        elif (
            pos == self.home
            and friendsHere > cls.MAX_PER_CELL
            and self.turnsLived <= 2
        ):
            # crowding on one cell turns a single kill into a colony-wide
            # disaster: newborns spread out instead of piling on
            self.home = self.pickNewHome()
            cls.homes.add(tuple(self.home))
            self.tell("h", (self.home[0], self.home[1]))
        old = self.age() >= self.maxAge - cls.OLD_AGE_MARGIN
        room = self.roomForAnother()
        rich = self.energy() >= 2 * self.winterReserve() + self.birthCost()
        if self.time() >= self.reproCost and (
            old or (room and rich and not self.lean() and view)
        ):
            child = self.Reproduce()
            if child:
                cls.alive[child] = cls.worldTurn
                if not room:
                    self.Talk(
                        child,
                        {
                            "s": cls.SIGIL,
                            "to": child,
                            "t": cls.worldTurn,
                            "parent": self.id(),
                        },
                    )
        if self.time() < self.moveCost:
            return
        if camped:
            target = self.home
        else:
            target = self.bestPasture(view) or self.distantPasture()
        if target is None:
            target = self.pickNewHome()
        self.stepTowards(target, 3)
        if self.position() == list(target) and not camped:
            self.claimPasture(self.position())

    def tendGarden(self, patches, friendsHere):
        cls = type(self)
        plant = self.plantEnergy()
        # 5a. harvest what would otherwise expire
        for f in [p for p in patches if p["age"] >= cls.EXPIRY_AGE]:
            if not self.eat(patches, f):
                break
        # 5b. reproduce: whenever both halves are safe and there is room,
        #     and in any case shortly before dying of old age
        safe = self.safeEnergy()
        old = self.age() >= self.maxAge - cls.OLD_AGE_MARGIN
        room = self.roomForAnother()
        if self.time() >= self.reproCost and (
            old or (room and self.energy() >= 2 * safe)
        ):
            child = self.Reproduce()
            if child:
                cls.alive[child] = cls.worldTurn
                if not room:
                    self.Talk(
                        child,
                        {
                            "s": cls.SIGIL,
                            "to": child,
                            "t": cls.worldTurn,
                            "parent": self.id(),
                        },
                    )
        # 5c. plant up to the garden size, then harvest the surplus
        cap = cls.PATCHES_PER_WESEN * friendsHere
        while (
            len(patches) < cap
            and self.time() >= self.plantCost
            and self.energy() > cls.RESERVE + plant
        ):
            if not self.Vomit(plant):
                break
            patches.append({"energy": plant, "age": 0, "id": None})
        # 5d. remaining time: bring the richest patches into the body
        while patches and self.time() >= self.eatCost:
            best = patches[0]
            if (
                best["id"] is None
                or best["energy"] < cls.MIN_HARVEST_ENERGY
            ):
                break
            self.eat(patches, best)
