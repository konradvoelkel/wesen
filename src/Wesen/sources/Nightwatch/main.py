"""the Night Watch: it protects the city, and it walks the beat.

The old Nightwatch split at 500 energy, hunted whatever was thinner
than itself and otherwise scanned east forever; it was the swarm the
rulebook was rebalanced against, and under the life food rule it eats
its own city flat and dies. A watch does not roam. A watch has a city,
and the city has beats.

* **The city.** The watch house stands where the founder stood; the
  city is the square around it, a few ranges of sight to a side, cut
  into *beats* one range of sight square. A watchman born in the city
  is told where the house is (`Talk`, in the turn it is born).
* **The beat.** Nobody stands on an estate. When nothing in view is
  worth a bite, a watchman walks to the beat that has gone longest
  without a patrol - by anybody's account - and looks at it. Grazing
  therefore goes round the city by staleness: a beat that was just
  eaten down is the last one anybody walks to, and by the time the
  patrol comes round again it has regrown. Every cell is grazed only
  down to the floor at which it regrows fastest, unless the watchman
  is hungry.
* **The lantern.** `look()` costs half of `closerLook()` and sees
  twice as far; it gives no energies, but it says where the food is.
  A watchman raises the lantern every few turns and counts the food
  on each beat it can see, so the patrol goes where there is
  something to patrol.
* **Calling the hours.** Every few turns a watchman calls out
  (`Broadcast`) when each beat was last patrolled and what the
  lantern showed there, and everybody in earshot brings their own
  record up to date, newest word wins. A child gets the whole record
  at birth. That is the entire shared state, and it is all said out
  loud.
* **The Watch protects the city.** A thief on a watchman's own cell
  that can be killed outright and cheaply is arrested (the first
  strike wins even fights). The fat ones are *sergeants*: they go for
  any stranger in the city that they can kill for a small share of
  their body. A watchman that something bigger is coming for runs to
  the nearest sergeant who could take it, else away, and blows the
  whistle: the beat is called dangerous and the patrol keeps off it
  for a while.
* **Precincts.** When more of the watch are in view than the beat can
  feed, the fattest walks out past the city wall, away from the
  crowd, and opens a new watch house. The Watch grows by precincts.

Every number with a unit is read from the rules (`readRules`): the
city and its beats from the range of sight, the reserve from upkeep,
the reach of a sergeant from the time budget, how long a beat stays
dangerous from how far a stranger walks in a turn.
"""

from ...defaultwesensource import DefaultWesenSource
from ...point import getDistInMaxMetric, getShortestTranslation

WATCH = "watch/1"  # our channel: the hours, the house, the whistle


class WesenSource(DefaultWesenSource):
    # dimensionless policy; everything with a unit is in readRules()
    FLOOR_SHARE = 0.3  # graze a cell down to this share of its capacity
    HUNGRY_SHARE = 0.25  # ... and to this share when hungry
    DESPERATE_TURNS = 15  # upkeep for fewer turns than this: kill cells
    CITY_SIGHTS = 4  # half the city's side, in ranges of sight
    RESERVE_TURNS = 60  # upkeep kept in the body, in turns
    BREED_WANTED = 3  # ripe cells in view before a birth
    CROWD = 4  # watch in view that makes a beat crowded
    CROWDED_TURNS = 5  # turns of crowding before a precinct is opened
    PRECINCT_TRIES = 4  # taken quarters looked at before settling anyway
    HARVEST_SLACK = 1.5  # cells per head, over what upkeep strictly needs
    ROLL_CALLS = 8  # not heard of for this many calls: off the roll
    SERGEANT_BODIES = 2.0  # a sergeant holds this many breeding bodies
    ARREST_SHARE = 0.3  # a thief may cost this share of my body
    HUNT_SHARE = 0.2  # a sergeant's prey may cost this share of its body
    LANTERN_EVERY = 3  # turns between raising the lantern
    CALL_EVERY = 8  # turns between calling the hours
    WHISTLE_TURNS = 4  # a beat is dangerous for this many turns of walking
    CALL_BEATS = 40  # beats reported in one call
    CALL_ROLL = 64  # names relayed in one call

    def __init__(self, infoAllSource):
        DefaultWesenSource.__init__(self, infoAllSource)
        self.readRules()
        self.clock = 0  # the Watch's clock, kept in step by calling
        self.house = None  # (x, y) of the watch house
        self.beats = {}  # beat -> [clock last patrolled, food seen]
        self.danger = {}  # beat -> clock until which it is dangerous
        self.crowded = 0
        self.precinct = None  # (x, y) I am walking to, to open one
        self.called = 0
        self.lit = 0
        self.going = None  # the beat I am walking to
        self.roll = {}  # id -> clock last seen or heard, this precinct
        self.tries = 0  # quarters looked at for a precinct and found taken

    def __str__(self):
        return "<Nightwatch, walks the beat>"

    # --- the rules of this game ------------------------------------------

    def readRules(self):
        self.moveTime = self.infoTime["move"]
        self.eatTime = self.infoTime["eat"]
        self.attackTime = self.infoTime["attack"]
        self.lookTime = self.infoTime["look"]
        self.turnTime = self.infoTime["init"]
        self.fullTime = self.infoTime["max"]
        self.stepsPerTurn = max(1, self.turnTime // self.moveTime)
        self.fullSteps = max(1, self.fullTime // self.moveTime)
        self.maxamount = self.infoFood["maxamount"]
        self.growrate = self.infoFood.get("growrate", 0.6)
        self.bite = self.foodBite() or self.maxamount
        self.roots = self.foodRoots()
        self.killLine = self.bite + self.roots + 1
        # a cell at its most productive pays one bite per this many turns
        self.cycle = max(1.0, self.bite / max(0.02, 0.5 * self.growrate))
        self.sight = self.infoRange["closer_look"]
        self.lantern = self.infoRange["look"]
        self.length = self.worldlength
        self.half = self.CITY_SIGHTS * self.sight  # half the city's side
        self.side = max(1, 2 * self.half // self.sight)  # beats per side
        self.reach = self.fullSteps + 1
        self.dangerTurns = self.WHISTLE_TURNS * self.fullSteps
        self.oldAge = self.infoWesen["maxage"] - 3
        self.reserve = max(
            self.minBirthEnergy(),
            int(
                self.RESERVE_TURNS
                * self.upkeepOf(self.infoWesen["energy"])
            )
            + 1,
        )
        # a birth leaves both about at the reserve
        self.breedAt = 2 * self.reserve + self.birthCost()
        # below a birth and a reserve on top: hungry, grazing below the
        # floor; about to starve: a cell is eaten whole
        self.comfort = self.breedAt + self.reserve
        self.desperate = (
            int(
                self.DESPERATE_TURNS
                * self.upkeepOf(self.infoWesen["energy"])
            )
            + 1
        )
        self.sergeantBody = int(self.SERGEANT_BODIES * self.breedAt)
        # a cell pays a bite per cycle: this many cells keep one of us
        self.cellsPerHead = max(
            1,
            int(
                self.HARVEST_SLACK
                * self.upkeepOf(self.infoWesen["energy"])
                * self.cycle
                / self.bite
            ),
        )
        self.rollTurns = self.ROLL_CALLS * self.CALL_EVERY

    # --- persistence and the channel -------------------------------------

    def persist(self):
        return {
            "clock": self.clock,
            "house": self.house,
            "beats": [[k, t, f] for k, (t, f) in self.beats.items()],
            "danger": [[k, t] for k, t in self.danger.items()],
            "crowded": self.crowded,
            "precinct": self.precinct,
            "called": self.called,
            "lit": self.lit,
            "going": self.going,
            "roll": [[k, t] for k, t in self.roll.items()],
            "tries": self.tries,
        }

    def restore(self, obj):
        me = obj.get("wesensource") or {}
        self.clock = me.get("clock", 0)
        house = me.get("house")
        self.house = (house[0], house[1]) if house else None
        self.beats = {k: [t, f] for k, t, f in me.get("beats", [])}
        self.danger = {k: t for k, t in me.get("danger", [])}
        self.crowded = me.get("crowded", 0)
        precinct = me.get("precinct")
        self.precinct = (precinct[0], precinct[1]) if precinct else None
        self.called = me.get("called", 0)
        self.lit = me.get("lit", 0)
        self.going = me.get("going")
        self.roll = {k: t for k, t in me.get("roll", [])}
        self.tries = me.get("tries", 0)

    def Receive(self, message):
        if not self.fromColleague(message):
            return
        if not isinstance(message, dict) or message.get("s") != WATCH:
            return
        clock = message.get("clock")
        if isinstance(clock, int) and clock > self.clock:
            self.clock = clock
        house = message.get("house")
        if (
            isinstance(house, (tuple, list))
            and len(house) == 2
            and all(isinstance(c, int) for c in house)
        ):
            house = (house[0], house[1])
            if self.house is None:
                self.house = house
            if house != self.house:
                # another precinct's hours are about other beats
                return
        # who called, and who they have seen or heard: the roll of the
        # precinct is relayed, so it reaches beyond earshot
        envelope = self.sender(message)
        if envelope and isinstance(envelope.get("id"), int):
            self.roll[envelope["id"]] = self.clock
        for line in message.get("roll") or ():
            if (
                isinstance(line, (tuple, list))
                and len(line) == 2
                and all(isinstance(c, int) for c in line)
            ):
                k, t = line
                if self.roll.get(k, -1) < t:
                    self.roll[k] = t
        for line in message.get("beats") or ():
            if (
                isinstance(line, (tuple, list))
                and len(line) == 3
                and all(isinstance(c, int) for c in line)
            ):
                k, t, f = line
                if k not in self.beats or self.beats[k][0] < t:
                    self.beats[k] = [t, f]
        for line in message.get("danger") or ():
            if (
                isinstance(line, (tuple, list))
                and len(line) == 2
                and all(isinstance(c, int) for c in line)
            ):
                k, t = line
                if self.danger.get(k, 0) < t:
                    self.danger[k] = t

    def call(self, whistle=None):
        lines = sorted(
            ([k, t, f] for k, (t, f) in self.beats.items()),
            key=lambda line: -line[1],
        )[: self.CALL_BEATS]
        message = {
            "s": WATCH,
            "clock": self.clock,
            "house": self.house,
            "beats": lines,
            "roll": sorted(
                ([k, t] for k, t in self.roll.items()),
                key=lambda line: -line[1],
            )[: self.CALL_ROLL],
        }
        if whistle is not None:
            message["danger"] = [[whistle, self.danger[whistle]]]
        return message

    # --- geometry --------------------------------------------------------

    def dist(self, a, b):
        return getDistInMaxMetric(a, b, self.length)

    def stepToward(self, target, keep=0):
        """walk toward a cell as far as this turn's time allows, keeping
        `keep` time in hand. True on arrival."""
        move = self.moveTime
        while True:
            v = getShortestTranslation(
                self.position(), target, self.length
            )
            d = max(abs(v[0]), abs(v[1]))
            if d == 0:
                return True
            sx = (v[0] > 0) - (v[0] < 0)
            sy = (v[1] > 0) - (v[1] < 0)
            n = min(
                d, (self.time() - keep) // (move * (abs(sx) + abs(sy)))
            )
            if n <= 0:
                return False
            dx, dy = sx * min(n, abs(v[0])), sy * min(n, abs(v[1]))
            if not self.Move([dx, dy]):
                return False

    def beatOf(self, pos):
        """the beat a cell lies on, or None outside the city"""
        v = getShortestTranslation(self.house, pos, self.length)
        if abs(v[0]) > self.half or abs(v[1]) > self.half:
            return None
        bx = min(self.side - 1, int((v[0] + self.half) // self.sight))
        by = min(self.side - 1, int((v[1] + self.half) // self.sight))
        return bx * self.side + by

    def beatCentre(self, k):
        bx, by = divmod(k, self.side)
        return [
            int(self.house[0] - self.half + (bx + 0.5) * self.sight)
            % self.length,
            int(self.house[1] - self.half + (by + 0.5) * self.sight)
            % self.length,
        ]

    def inCity(self, pos):
        return self.beatOf(pos) is not None

    # --- the lantern and the hours ---------------------------------------

    def raiseLantern(self, pos):
        """count the food on every beat the lantern reaches"""
        if self.time() < self.lookTime:
            return
        counts = {}
        for o in self.look():
            if o["type"] != "food":
                continue
            k = self.beatOf(o["position"])
            if k is not None:
                counts[k] = counts.get(k, 0) + 1
        for k in range(self.side * self.side):
            centre = self.beatCentre(k)
            # a beat wholly inside the lantern's circle has been counted
            if self.dist(pos, centre) + self.sight // 2 <= self.lantern:
                seen = self.beats.get(k, [0, 0])
                self.beats[k] = [seen[0], counts.get(k, 0)]
        self.lit = self.clock

    def patrolled(self, pos, foods):
        """the beats in sight have been looked at now"""
        counts = {}
        for f in foods:
            k = self.beatOf(f["position"])
            if k is not None:
                counts[k] = counts.get(k, 0) + 1
        for k in range(self.side * self.side):
            if self.dist(pos, self.beatCentre(k)) <= self.sight // 2:
                self.beats[k] = [self.clock, counts.get(k, 0)]

    def staffed(self):
        """is the precinct full: as many of us seen or heard lately as
        the food the lantern counted on the beats can keep? A watchman
        that has met nobody counts itself, so a founder alone is one
        of one and the city's food decides whether it splits"""
        stale = [
            k
            for k, t in self.roll.items()
            if self.clock - t > self.rollTurns
        ]
        for k in stale:
            del self.roll[k]
        heads = 1 + sum(1 for k in self.roll if k != self.id())
        cells = sum(f for _, f in self.beats.values())
        return heads * self.cellsPerHead > cells

    def nextBeat(self, pos):
        """the stalest beat worth a walk: longest since a patrol, with
        food on it if the lantern has seen any, not dangerous, and
        near before far"""
        best, bestScore = None, None
        for k in range(self.side * self.side):
            if self.danger.get(k, 0) > self.clock:
                continue
            last, food = self.beats.get(k, [0, 1])
            stale = self.clock - last
            score = (
                stale * (1 + food)
                - self.dist(pos, self.beatCentre(k)) * self.stepsPerTurn
            )
            if bestScore is None or score > bestScore:
                best, bestScore = k, score
        return best

    # --- grazing ---------------------------------------------------------

    def floorOf(self, food, share=None):
        capacity = self.maxamount * self.fertility(food["position"])
        share = self.FLOOR_SHARE if share is None else share
        return max(self.killLine, int(share * capacity))

    def wanted(self, food, ripe=False):
        """a comfortable watchman leaves a cell where it regrows
        fastest, a hungry one leaves it alive, a starving one nothing. With `ripe`, only a cell above the
        floor counts: the surplus a birth needs"""
        energy = food["energy"]
        if energy - self.bite >= self.floorOf(food):
            return True
        if ripe:
            return False
        mine = self.energy()
        if mine < self.comfort and energy - self.bite >= self.floorOf(
            food, self.HUNGRY_SHARE
        ):
            return True
        return mine < self.desperate and energy > 0

    def eatHere(self, foods, pos):
        eaten = 0
        for food in foods:
            if list(food["position"]) != pos:
                continue
            food = dict(food)
            while self.time() >= self.eatTime and self.wanted(food):
                gain = self.foodYield(food)
                if not self.Eat(food["id"]):
                    break
                eaten += gain
                food["energy"] -= gain
                if food["energy"] <= 0:
                    break
        return eaten

    # --- policing --------------------------------------------------------

    def canKill(self, other, share):
        mine = self.energy()
        return (
            mine * self.attackDamage() >= other["energy"]
            and self.attackCost() * other["energy"] <= share * mine
        )

    def arrest(self, pos, strangers):
        """a thief on my own cell that is cheap to kill: kill it"""
        for o in strangers:
            if list(o["position"]) == pos and self.canKill(
                o, self.ARREST_SHARE
            ):
                if self.time() >= self.attackTime:
                    self.Attack(o["id"])
                    return True
        return False

    def hunt(self, pos, strangers):
        """a sergeant goes for prey in the city and in reach"""
        if self.energy() < self.sergeantBody:
            return False
        steps = (self.time() - self.attackTime) // self.moveTime
        prey = [
            o
            for o in strangers
            if self.inCity(o["position"])
            and self.dist(pos, o["position"]) <= steps
            and self.canKill(o, self.HUNT_SHARE)
        ]
        if not prey:
            return False
        victim = min(prey, key=lambda o: self.dist(pos, o["position"]))
        if self.stepToward(list(victim["position"]), keep=self.attackTime):
            self.Attack(victim["id"])
        return True

    def whistle(self, pos, bullies):
        """the beat the bully stands on is dangerous for a while, and
        everybody in earshot hears so"""
        worst = max(bullies, key=lambda o: o["energy"])
        k = self.beatOf(worst["position"])
        if k is None:
            return
        self.danger[k] = self.clock + self.dangerTurns
        if self.time() >= self.infoTime["broadcast"]:
            self.Broadcast(self.call(whistle=k))

    def flee(self, pos, bullies, watch):
        """run to a sergeant who could take the bully, else away"""
        worst = max(bullies, key=lambda o: o["energy"])
        sergeants = [
            c
            for c in watch
            if c["energy"] * self.attackDamage() >= worst["energy"]
            and self.dist(c["position"], worst["position"])
            > self.dist(pos, worst["position"])
        ]
        if sergeants:
            near = min(
                sergeants, key=lambda c: self.dist(pos, c["position"])
            )
            self.stepToward(list(near["position"]))
            return
        v = [0.0, 0.0]
        for o in bullies:
            t = getShortestTranslation(pos, o["position"], self.length)
            d = max(1, max(abs(t[0]), abs(t[1])))
            v[0] -= t[0] / d
            v[1] -= t[1] / d
        sx = (v[0] > 0.3) - (v[0] < -0.3)
        sy = (v[1] > 0.3) - (v[1] < -0.3)
        if sx == 0 and sy == 0:
            sx, sy = (1, 0) if abs(v[0]) >= abs(v[1]) else (0, 1)
        n = self.time() // (self.moveTime * (abs(sx) + abs(sy)))
        if n > 0:
            self.Move([sx * n, sy * n])

    # --- precincts -------------------------------------------------------

    def openPrecinct(self, pos, watch):
        """walk out past the wall, away from the crowd"""
        v = [0.0, 0.0]
        for c in watch:
            t = getShortestTranslation(pos, c["position"], self.length)
            v[0] -= t[0]
            v[1] -= t[1]
        if abs(v[0]) < 1e-9 and abs(v[1]) < 1e-9:
            rng = self.gameRandom(f"precinct/{self.id()}/{self.tries}")
            v = [rng.uniform(-1, 1), rng.uniform(-1, 1)]
        norm = max(abs(v[0]), abs(v[1])) or 1.0
        r = 2.5 * self.half
        self.precinct = (
            int(pos[0] + r * v[0] / norm) % self.length,
            int(pos[1] + r * v[1] / norm) % self.length,
        )
        self.crowded = 0

    def foundHouse(self, pos):
        self.house = (pos[0], pos[1])
        self.beats = {}
        self.danger = {}
        self.roll = {}
        self.precinct = None
        self.tries = 0
        self.going = None
        self.crowded = 0

    # --- the turn --------------------------------------------------------

    def main(self):
        self.clock += 1
        pos = list(self.position())
        energy = self.energy()
        seen = self.closerLook()
        foods = [o for o in seen if o["type"] == "food"]
        strangers = [
            o
            for o in seen
            if o["type"] == "wesen" and o["source"] != self.source
        ]
        watch = [
            o
            for o in seen
            if o["type"] == "wesen" and o["source"] == self.source
        ]
        if self.house is None:
            self.foundHouse(pos)
        # colleagues in view are on the roll without having to call
        for o in watch:
            if self.inCity(o["position"]):
                self.roll[o["id"]] = self.clock

        # anything that could kill me and reach me: whistle and run
        damage = self.attackDamage()
        bullies = [
            o
            for o in strangers
            if o["energy"] * damage >= energy
            and self.dist(pos, o["position"]) <= self.reach
        ]
        if bullies:
            self.whistle(pos, bullies)
            self.flee(pos, bullies, watch)
            return

        # old age: split whatever the weather, Reproduce resets the clock
        if self.age() >= self.oldAge and energy >= self.minBirthEnergy():
            child = self.Reproduce()
            if child:
                self.Talk(child, self.call())

        if self.arrest(pos, strangers):
            return
        if self.hunt(pos, strangers):
            return

        # the beats in sight have been looked at; the lantern now and
        # then; the hours called
        if self.inCity(pos):
            self.patrolled(pos, foods)
        if self.clock - self.lit >= self.LANTERN_EVERY:
            self.raiseLantern(pos)
        if self.clock - self.called >= self.CALL_EVERY:
            self.Broadcast(self.call())
            self.called = self.clock

        eaten = self.eatHere(foods, pos)
        pos = list(self.position())
        taken = {tuple(o["position"]) for o in strangers}
        wanted = [
            f
            for f in foods
            if list(f["position"]) != pos
            and tuple(f["position"]) not in taken
            and self.wanted(f)
        ]
        # a birth needs a surplus: cells still above the floor at which
        # they regrow fastest, not just something a hungry mouth would take
        ripe = sum(1 for f in foods if self.wanted(f, ripe=True))

        # on the way to open a precinct: a quarter where the Watch
        # already walks is somebody else's precinct, so look further -
        # a few times, and then this one will have to do
        if self.precinct is not None:
            if self.stepToward(list(self.precinct)):
                if watch and self.tries < self.PRECINCT_TRIES:
                    self.tries += 1
                    self.openPrecinct(list(self.position()), watch)
                else:
                    self.foundHouse(list(self.position()))
            elif not eaten and wanted:
                near = min(
                    wanted, key=lambda f: self.dist(pos, f["position"])
                )
                if self.dist(pos, near["position"]) <= self.stepsPerTurn:
                    if self.stepToward(list(near["position"])):
                        self.eatHere([near], list(self.position()))
            return

        # a birth in the city, while the precinct is not fully staffed
        staffed = self.staffed()
        if (
            self.inCity(pos)
            and not staffed
            and ripe >= self.BREED_WANTED
            and len(watch) < self.CROWD
            and self.energy() >= self.breedAt
            and (not self.lean() or self.energy() >= 2 * self.breedAt)
        ):
            child = self.Reproduce()
            if child:
                self.Talk(child, self.call())

        # a full roll and a crowd in view: the fattest of the crowd
        # opens a precinct
        self.crowded = (
            self.crowded + 1 if len(watch) >= self.CROWD and staffed else 0
        )
        if (
            self.crowded >= self.CROWDED_TURNS
            and self.energy() >= self.breedAt
            and all(c["energy"] <= self.energy() for c in watch)
        ):
            self.openPrecinct(pos, watch)
            self.stepToward(list(self.precinct))
            return

        # a bite in the city; when hungry, also one just outside the
        # wall - but no further, or the beat would drift off the city
        safe = [
            f
            for f in wanted
            if self.danger.get(self.beatOf(f["position"]), 0) <= self.clock
        ]
        inside = [f for f in safe if self.inCity(f["position"])]
        choice = inside
        if not choice and self.energy() < self.comfort:
            choice = [
                f
                for f in safe
                if self.dist(f["position"], self.house)
                <= self.half + self.sight
            ]
        if choice:
            best = max(
                choice,
                key=lambda f: (
                    self.foodYield(f)
                    / (1.0 + self.dist(pos, f["position"]))
                ),
            )
            self.going = None
            if self.stepToward(list(best["position"])):
                self.eatHere([best], list(self.position()))
            return

        # nothing worth a bite in view: walk the beat
        if (
            self.going is None
            or self.dist(pos, self.beatCentre(self.going))
            <= self.sight // 2
        ):
            self.going = self.nextBeat(pos)
        if self.going is not None:
            self.stepToward(self.beatCentre(self.going))
