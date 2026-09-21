"""the dwarf: a mining clan, and every dwarf carries an axe.

The old Dwarf swept the world along one vector, fought whatever it
could reach and fattened to 1500 before it split; under upkeep that
grows with the body and a pasture that regrows only where it is
grazed with care, it fed the pasture to its own fat and died. A dwarf
is not a scanner. A dwarf has a mine.

* **Reading the rock.** The ground has seams: `self.fertility([x, y])`
  is free and constant, and a cell on the best ground carries half as
  much again as one on average ground and regrows faster to boot. A
  founding dwarf samples the rock around it and sinks the mine on the
  richest ground in reach. Every dwarf born in that mine is told where
  it is (`Talk`, in the turn it is born); it needs no map after that.
* **Galleries and shifts.** The mine is a disc around the shaft, cut
  into galleries like a pie. The clan works one gallery at a time, on
  a rota kept by a clock the clan agrees on by talking: a shift long
  enough to graze the gallery down to the floor at which a cell
  regrows fastest, and then the whole crew moves on and that gallery
  rests for the other shifts of the rota, long enough to regrow what
  was taken. Rotational grazing, but with the crew kept together -
  which is the point of a clan.
* **Axes.** A thief on a dwarf's own cell that the dwarf can kill
  outright, cheaply, is killed: the first strike wins even fights, and
  a thin grazer costs little. The fat dwarfs of the clan are its
  *guards*: they go for any stranger in reach that they can kill for a
  small share of their body. A dwarf that something bigger is coming
  for does not run into the dark: it runs to the nearest guard.
* **New shafts.** When the mine is crowded - more of the clan in view
  than the gallery can feed - a fat dwarf becomes a *prospector*,
  reads the rock two mine-widths out in every direction, walks to the
  richest, and sinks a new shaft there. Colonies expand by mines, not
  by drift.

Every number with a unit is read from the rules (`readRules`): the
mine's radius from the range of sight, the shift from the bite and the
growth rate, the reserve from upkeep, the reach of a guard from the
time budget.
"""

from math import atan2, cos, pi, sin

from ...defaultwesensource import DefaultWesenSource
from ...point import getDistInMaxMetric, getShortestTranslation

MINE = "mine/1"  # our channel: the clan's clock and the shaft


class WesenSource(DefaultWesenSource):
    # dimensionless policy; everything with a unit is in readRules()
    FLOOR_SHARE = 0.3  # graze a cell down to this share of its capacity
    HUNGRY_SHARE = 0.25  # ... and to this share when hungry
    DESPERATE_TURNS = 15  # upkeep for fewer turns than this: kill cells
    GALLERIES = 6  # galleries to a mine
    REST_CYCLES = 2.0  # a gallery rests this many regrowth cycles
    MINE_SIGHTS = 2.5  # mine radius, in ranges of sight
    RESERVE_TURNS = 60  # upkeep kept in the body, in turns
    BREED_WANTED = 3  # ripe cells in view before a birth
    CROWD = 4  # clan in view that makes the gallery crowded
    CROWDED_TURNS = 15  # turns of crowding before somebody prospects
    GUARD_BODIES = 2.0  # a guard holds this many breeding bodies
    STRIKE_SHARE = 0.3  # a thief may cost this share of my body
    HUNT_SHARE = 0.2  # a guard's prey may cost this share of its body
    CALL_EVERY = 10  # turns between calls of the clock

    def __init__(self, infoAllSource):
        DefaultWesenSource.__init__(self, infoAllSource)
        self.readRules()
        self.clock = 0  # the clan's clock, kept in step by talking
        self.mine = None  # (x, y) of the shaft
        self.crowded = 0  # turns running with too many of us in view
        self.prospect = None  # (x, y) I am walking to, to sink a shaft
        self.called = 0  # clock when I last called the hour

    def __str__(self):
        return "<Dwarf, works the mine and carries an axe>"

    # --- the rules of this game ------------------------------------------

    def readRules(self):
        self.moveTime = self.infoTime["move"]
        self.eatTime = self.infoTime["eat"]
        self.attackTime = self.infoTime["attack"]
        self.turnTime = self.infoTime["init"]
        self.fullTime = self.infoTime["max"]
        self.stepsPerTurn = max(1, self.turnTime // self.moveTime)
        self.fullSteps = max(1, self.fullTime // self.moveTime)
        self.maxamount = self.infoFood["maxamount"]
        self.growrate = self.infoFood.get("growrate", 0.6)
        self.bite = self.foodBite() or self.maxamount
        self.roots = self.foodRoots()
        self.killLine = self.bite + self.roots + 1
        self.sight = self.infoRange["closer_look"]
        self.length = self.worldlength
        self.radius = max(self.sight, int(self.MINE_SIGHTS * self.sight))
        # a cell at its most productive pays one bite per this many turns
        self.cycle = max(1.0, self.bite / max(0.02, 0.5 * self.growrate))
        # the rota: every gallery rests REST_CYCLES between shifts
        self.shift = max(
            3, int(self.REST_CYCLES * self.cycle / (self.GALLERIES - 1))
        )
        self.reach = self.fullSteps + 1
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
        self.guardBody = int(self.GUARD_BODIES * self.breedAt)

    # --- persistence and the clan's channel ------------------------------

    def persist(self):
        return {
            "clock": self.clock,
            "mine": self.mine,
            "crowded": self.crowded,
            "prospect": self.prospect,
            "called": self.called,
        }

    def restore(self, obj):
        me = obj.get("wesensource") or {}
        self.clock = me.get("clock", 0)
        mine = me.get("mine")
        self.mine = (mine[0], mine[1]) if mine else None
        self.crowded = me.get("crowded", 0)
        prospect = me.get("prospect")
        self.prospect = (prospect[0], prospect[1]) if prospect else None
        self.called = me.get("called", 0)

    def Receive(self, message):
        if not self.fromColleague(message):
            return
        if not isinstance(message, dict) or message.get("s") != MINE:
            return
        clock = message.get("clock")
        if isinstance(clock, int) and clock > self.clock:
            self.clock = clock
        mine = message.get("mine")
        if (
            self.mine is None
            and isinstance(mine, (tuple, list))
            and len(mine) == 2
            and all(isinstance(c, int) for c in mine)
        ):
            self.mine = (mine[0], mine[1])

    def call(self):
        return {
            "s": MINE,
            "clock": self.clock,
            "mine": self.mine,
        }

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

    def gallery(self, pos):
        """which gallery of the mine a cell lies in, by its bearing
        from the shaft"""
        v = getShortestTranslation(self.mine, pos, self.length)
        angle = atan2(v[1], v[0]) % (2 * pi)
        return int(angle / (2 * pi) * self.GALLERIES) % self.GALLERIES

    def galleryFace(self, k):
        """the middle of a gallery, where the crew gathers"""
        angle = (k + 0.5) / self.GALLERIES * 2 * pi
        r = 0.5 * self.radius
        return [
            int(self.mine[0] + r * cos(angle)) % self.length,
            int(self.mine[1] + r * sin(angle)) % self.length,
        ]

    def onShift(self):
        return (self.clock // self.shift) % self.GALLERIES

    # --- reading the rock ------------------------------------------------

    def richest(self, centre, radius, step):
        """the richest ground within radius of centre: the sample whose
        neighbourhood of samples has the highest fertility"""
        samples = {}
        n = radius // step
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                cell = (
                    (centre[0] + i * step) % self.length,
                    (centre[1] + j * step) % self.length,
                )
                samples[(i, j)] = self.fertility(cell)
        best, bestCell = -1.0, tuple(centre)
        for (i, j), _ in samples.items():
            total, count = 0.0, 0
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    f = samples.get((i + di, j + dj))
                    if f is not None:
                        total += f
                        count += 1
            score = total / count
            if score > best:
                best = score
                bestCell = (
                    (centre[0] + i * step) % self.length,
                    (centre[1] + j * step) % self.length,
                )
        return bestCell, best

    def sinkShaft(self, pos):
        self.mine, _ = self.richest(
            pos, self.radius, max(2, self.sight // 2)
        )
        self.crowded = 0
        self.prospect = None

    def goProspecting(self, pos):
        """pick the richest ground two mine-widths out, in any
        direction, and walk there"""
        best, bestScore = None, -1.0
        for k in range(8):
            angle = k / 8 * 2 * pi
            r = 2.5 * self.radius
            centre = (
                int(pos[0] + r * cos(angle)) % self.length,
                int(pos[1] + r * sin(angle)) % self.length,
            )
            cell, score = self.richest(centre, self.radius, self.sight)
            if score > bestScore:
                best, bestScore = cell, score
        self.prospect = best
        self.crowded = 0

    # --- grazing ---------------------------------------------------------

    def floorOf(self, food, share=None):
        capacity = self.maxamount * self.fertility(food["position"])
        share = self.FLOOR_SHARE if share is None else share
        return max(self.killLine, int(share * capacity))

    def wanted(self, food, ripe=False):
        """a comfortable dwarf leaves a cell where it regrows fastest,
        a hungry one leaves it alive, a starving one leaves nothing. With `ripe`, only a cell above the
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

    # --- axes ------------------------------------------------------------

    def canKill(self, other, share):
        """would one strike kill it, for no more than that share of my
        body?"""
        mine = self.energy()
        return (
            mine * self.attackDamage() >= other["energy"]
            and self.attackCost() * other["energy"] <= share * mine
        )

    def strikeThief(self, pos, strangers):
        """a thief on my own cell that is cheap to kill: kill it.
        Returns True if a strike was made."""
        for o in strangers:
            if list(o["position"]) == pos and self.canKill(
                o, self.STRIKE_SHARE
            ):
                if self.time() >= self.attackTime:
                    self.Attack(o["id"])
                    return True
        return False

    def hunt(self, pos, strangers):
        """a guard goes for prey in reach: True if the turn went on it"""
        if self.energy() < self.guardBody:
            return False
        steps = (self.time() - self.attackTime) // self.moveTime
        prey = [
            o
            for o in strangers
            if self.dist(pos, o["position"]) <= steps
            and self.canKill(o, self.HUNT_SHARE)
        ]
        if not prey:
            return False
        victim = min(prey, key=lambda o: self.dist(pos, o["position"]))
        if self.stepToward(list(victim["position"]), keep=self.attackTime):
            self.Attack(victim["id"])
        return True

    def flee(self, pos, bullies, clan):
        """run to a guard that could kill the bully, else straight away"""
        worst = max(bullies, key=lambda o: o["energy"])
        guards = [
            c
            for c in clan
            if c["energy"] * self.attackDamage() >= worst["energy"]
            and self.dist(c["position"], worst["position"])
            > self.dist(pos, worst["position"])
        ]
        if guards:
            guard = min(
                guards, key=lambda c: self.dist(pos, c["position"])
            )
            self.stepToward(list(guard["position"]))
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
        clan = [
            o
            for o in seen
            if o["type"] == "wesen" and o["source"] == self.source
        ]
        if self.mine is None:
            self.sinkShaft(pos)

        # the clock and the shaft, called out now and then
        if self.clock - self.called >= self.CALL_EVERY:
            self.Broadcast(self.call())
            self.called = self.clock

        # anything that could kill me and reach me
        damage = self.attackDamage()
        bullies = [
            o
            for o in strangers
            if o["energy"] * damage >= energy
            and self.dist(pos, o["position"]) <= self.reach
        ]
        if bullies:
            self.flee(pos, bullies, clan)
            return

        # old age: split whatever the weather, Reproduce resets the clock
        if self.age() >= self.oldAge and energy >= self.minBirthEnergy():
            child = self.Reproduce()
            if child:
                self.Talk(child, self.call())

        # a thief on my cell, or prey for a guard
        if self.strikeThief(pos, strangers):
            return
        if self.hunt(pos, strangers):
            return

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

        # a prospector walks to the new shaft and sinks it
        if self.prospect is not None:
            if self.stepToward(list(self.prospect)):
                self.sinkShaft(list(self.position()))
            elif not eaten and wanted:
                near = min(
                    wanted, key=lambda f: self.dist(pos, f["position"])
                )
                if self.dist(pos, near["position"]) <= self.stepsPerTurn:
                    if self.stepToward(list(near["position"])):
                        self.eatHere([near], list(self.position()))
            return

        # a birth in the mine
        inMine = self.dist(pos, self.mine) <= self.radius
        if (
            inMine
            and ripe >= self.BREED_WANTED
            and len(clan) < self.CROWD
            and self.energy() >= self.breedAt
            and (not self.lean() or self.energy() >= 2 * self.breedAt)
        ):
            child = self.Reproduce()
            if child:
                self.Talk(child, self.call())

        # crowding: the fattest of the crowd goes prospecting
        self.crowded = self.crowded + 1 if len(clan) >= self.CROWD else 0
        if (
            self.crowded >= self.CROWDED_TURNS
            and self.energy() >= self.breedAt
            and all(c["energy"] <= self.energy() for c in clan)
        ):
            self.goProspecting(pos)
            self.stepToward(list(self.prospect))
            return

        # the shift: work my gallery, else anything in the mine, else
        # anything at all when hungry
        k = self.onShift()
        onShift = [
            f
            for f in wanted
            if self.dist(f["position"], self.mine) <= self.radius
            and self.gallery(f["position"]) == k
        ]
        inside = [
            f
            for f in wanted
            if self.dist(f["position"], self.mine) <= self.radius
        ]
        choice = onShift or inside
        if not choice and self.energy() < self.comfort:
            choice = wanted
        if choice:
            best = max(
                choice,
                key=lambda f: (
                    self.foodYield(f)
                    / (1.0 + self.dist(pos, f["position"]))
                ),
            )
            if self.stepToward(list(best["position"])):
                self.eatHere([best], list(self.position()))
            return
        # nothing worth a bite in view: to the gallery face
        self.stepToward(self.galleryFace(k))
