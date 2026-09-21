"""the sober sailor: the one who stayed off the rum and can still read
a chart.

The drunken sailor (see DrunkenSailor/main.py) searches the sea at
random and finds the next pub by luck and by song. The sober one does
not search at all. Before it casts off it draws a chart, and then it
sails a route.

* **The chart.** The ground is not uniform: `self.fertility([x, y])`
  is free, constant for the whole game and built from the game seed
  (see biome.py), so the best ground is knowable before the first turn
  without anyone having been there. Every sailor samples the world on
  a coarse grid, marks the local peaks of fertility as *ports*, and
  strings them into one *trade route*, a loop over every block of
  the world. It is worked out on board, from the seed
  alone, so every sailor of the fleet holds the same chart without a
  word between them (see `gameRandom` in defaultwesensource.py for why
  that is the right kind of agreement).
* **The voyage.** A sailor sails the route port to port. Under way it
  keeps a lookout and puts in for any bite close to its course, but it
  does not chase the horizon. In harbour it takes *shore leave*: it
  grazes the harbour to the floor at which a cell regrows fastest, and
  no further, and then casts off for the next port. Every port is
  therefore visited, grazed, and left to regrow while the fleet is
  elsewhere on the loop: rotational grazing at the scale of the world,
  which is what a pasture that regrows logistically wants and what no
  herd standing on an estate can do.
* **The log.** A sailor writes a line in its log at every port - when
  it was there and what it found - and reads the line out on the quay
  (`Broadcast`), so that a colleague in earshot sails past a port that
  was grazed dry yesterday. A child is handed the log at birth
  (`Talk`), and its first port is the *next* one on the route, so a
  litter strings itself out along the loop instead of eating one
  harbour flat.
* **Sober.** It never fights; it runs from anything that could kill
  it, with the whole time budget, and gets back on course.

Every number with a unit is read from the rules (`readRules`): the
size of a harbour is the range of sight, the grazing floor is where
logistic growth peaks, the time a port needs to recover is a bite
divided by that growth, and the reserve a sailor keeps is upkeep for
the longest leg of the route.
"""

from ...defaultwesensource import DefaultWesenSource
from ...point import getDistInMaxMetric, getShortestTranslation

LOG = "log/1"  # our channel: port reports and a child's briefing


class WesenSource(DefaultWesenSource):
    # dimensionless policy; everything with a unit is in readRules()
    FLOOR_SHARE = 0.3  # graze a cell down to this share of its capacity
    HUNGRY_SHARE = 0.25  # ... and to this share when hungry
    DESPERATE_TURNS = 15  # upkeep for fewer turns than this: kill cells
    RESERVE_LEGS = 1.5  # keep upkeep for this many longest legs on board
    BREED_RIPE = 3  # ripe cells in view before a birth in harbour
    CROWD = 3  # colleagues in view that make a harbour crowded
    BUSY = 0.5  # share of recent landfalls that found the harbour dry
    LANDFALLS = 8  # landfalls the sailor judges the coast by
    MAX_STAY_CYCLES = 0.6  # shore leave, in cell regrowth cycles
    DETOUR = 5  # cells off course a bite is still worth putting in for
    BLOCK_HARBOURS = 3  # a port per block this many harbours wide
    LOG_LINES = 32  # port reports carried in one message

    def __init__(self, infoAllSource):
        DefaultWesenSource.__init__(self, infoAllSource)
        self.readRules()
        self.ports, self.route = self.chart()
        # what a sailor keeps on board follows from the longest leg
        legTurns = self.longestLeg() / self.stepsPerTurn
        self.reserve = max(
            self.minBirthEnergy(),
            self.bodyFor(self.RESERVE_LEGS * legTurns),
        )
        # a birth leaves both about at the reserve
        self.breedAt = 2 * self.reserve + self.birthCost()
        # below a birth and a reserve on top a sailor is hungry and
        # grazes below the floor; about to starve, it eats a cell whole
        self.comfort = self.breedAt + self.reserve
        self.desperate = self.bodyFor(self.DESPERATE_TURNS)
        self.turn = 0
        self.leg = None  # index into self.route of the port I sail to
        self.stay = 0  # turns spent in the current harbour
        self.arrived = 0  # turn I made this harbour
        self.log = {}  # port index -> [turn, energy left when leaving]
        self.landfalls = []  # the last few: 1 if the harbour was dry

    def __str__(self):
        return "<Sober Sailor, keeps the log>"

    # --- the rules of this game ------------------------------------------

    def readRules(self):
        self.moveTime = self.infoTime["move"]
        self.eatTime = self.infoTime["eat"]
        self.turnTime = self.infoTime["init"]
        self.fullTime = self.infoTime["max"]
        self.stepsPerTurn = max(1, self.turnTime // self.moveTime)
        self.fullSteps = max(1, self.fullTime // self.moveTime)
        self.maxamount = self.infoFood["maxamount"]
        self.growrate = self.infoFood.get("growrate", 0.6)
        self.bite = self.foodBite() or self.maxamount
        self.roots = self.foodRoots()
        self.killLine = self.bite + self.roots + 1
        self.harbour = self.infoRange["closer_look"]
        self.length = self.worldlength
        # a cell at its most productive pays one bite per this many turns
        self.cycle = max(1.0, self.bite / max(0.02, 0.5 * self.growrate))
        self.maxStay = max(5, int(self.MAX_STAY_CYCLES * self.cycle))
        # how far a stranger with a full time budget can come at me
        self.reach = self.fullSteps + 1
        self.oldAge = self.infoWesen["maxage"] - 3

    def bodyFor(self, turns):
        """energy that lasts the given number of turns of upkeep, for a
        body the size a wesen is born with"""
        return int(turns * self.upkeepOf(self.infoWesen["energy"])) + 1

    # --- the chart -------------------------------------------------------

    def chart(self):
        """the ports and the route, from the seed alone.

        The world is cut into square blocks a few harbours wide, and
        the port of a block is the most fertile of the samples in it:
        every block has a port, so the route covers the whole world,
        and every port lies on the best ground of its block. The route
        runs the blocks boustrophedon - along one row, back along the
        next - which on a torus closes into a loop whose every leg is
        about one block long, at no cost worth mentioning (a wesen is
        born with this, and a tour worth the name took a quarter of a
        second). Which axis the rows run along, and which row is
        first, come from the seed."""
        step = max(2, self.harbour)
        block = max(1, self.BLOCK_HARBOURS)
        n = max(2, self.length // step)
        rows = (n + block - 1) // block
        blocks = {}
        for i in range(n):
            for j in range(n):
                cell = [i * step, j * step]
                f = self.fertility(cell)
                key = (i // block, j // block)
                if key not in blocks or f > blocks[key][0]:
                    blocks[key] = (f, (cell[0], cell[1]))
        rng = self.gameRandom("route")
        flip = rng.random() < 0.5
        first = rng.randrange(rows)
        ports, route = [], []
        for r in range(rows):
            row = (first + r) % rows
            cols = range(rows) if r % 2 == 0 else range(rows - 1, -1, -1)
            for c in cols:
                key = (c, row) if flip else (row, c)
                if key in blocks:
                    route.append(len(ports))
                    ports.append(blocks[key][1])
        if len(ports) < 2:
            ports = [(0, 0), (self.length // 2, self.length // 2)]
            route = [0, 1]
        return ports, route

    def portAt(self, leg):
        return self.ports[self.route[leg % len(self.route)]]

    def nearestLeg(self, pos):
        return min(
            range(len(self.route)),
            key=lambda k: self.dist(pos, self.portAt(k)),
        )

    def longestLeg(self):
        return max(
            self.dist(self.portAt(k), self.portAt(k + 1))
            for k in range(len(self.route))
        )

    # --- the log ---------------------------------------------------------

    def persist(self):
        return {
            "turn": self.turn,
            "leg": self.leg,
            "stay": self.stay,
            "arrived": self.arrived,
            "log": [[k, t, e] for k, (t, e) in self.log.items()],
            "landfalls": self.landfalls,
        }

    def restore(self, obj):
        me = obj.get("wesensource") or {}
        self.turn = me.get("turn", 0)
        self.leg = me.get("leg")
        self.stay = me.get("stay", 0)
        self.arrived = me.get("arrived", 0)
        self.log = {k: [t, e] for k, t, e in me.get("log", [])}
        self.landfalls = list(me.get("landfalls", []))

    def Receive(self, message):
        if not self.fromColleague(message):
            return
        if not isinstance(message, dict) or message.get("s") != LOG:
            return
        clock = message.get("turn")
        if isinstance(clock, int) and clock > self.turn:
            self.turn = clock
        lines = message.get("log")
        if isinstance(lines, (tuple, list)):
            for line in lines:
                if (
                    isinstance(line, (tuple, list))
                    and len(line) == 3
                    and all(isinstance(c, int) for c in line)
                    and 0 <= line[0] < len(self.ports)
                ):
                    k, t, e = line
                    if k not in self.log or self.log[k][0] < t:
                        self.log[k] = [t, e]
        leg = message.get("leg")
        if isinstance(leg, int) and self.leg is None:
            self.leg = leg % len(self.route)

    def logLines(self):
        lines = sorted(
            ([k, t, e] for k, (t, e) in self.log.items()),
            key=lambda line: -line[1],
        )
        return lines[: self.LOG_LINES]

    def readOut(self, leg=None):
        """say the log on the quay, or brief a child"""
        message = {
            "s": LOG,
            "turn": self.turn,
            "log": self.logLines(),
        }
        if leg is not None:
            message["leg"] = leg
        return message

    def landfall(self, dry):
        """note whether the harbour I have just made was already grazed"""
        self.landfalls.append(1 if dry else 0)
        del self.landfalls[: -self.LANDFALLS]

    def busy(self):
        """is the coast busy: were most of the last harbours I made
        already grazed when I got there? The log of one sailor never
        shows the whole fleet, but every harbour drunk dry ahead of it
        does: then the fleet is as big as the coast can keep"""
        if len(self.landfalls) < self.LANDFALLS:
            return False
        return sum(self.landfalls) >= self.BUSY * len(self.landfalls)

    def dryUntil(self, port):
        """turn from which a port is worth another call"""
        line = self.log.get(port)
        if line is None:
            return 0
        t, left = line
        if left >= self.bite:
            # something was left when the last sailor cast off
            return t + int(0.3 * self.cycle)
        return t + int(self.cycle)

    # --- geometry --------------------------------------------------------

    def dist(self, a, b):
        return getDistInMaxMetric(a, b, self.length)

    def stepToward(self, target):
        """walk toward a cell as far as this turn's time allows.
        True on arrival."""
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
            n = min(d, self.time() // (move * (abs(sx) + abs(sy))))
            if n <= 0:
                return False
            dx, dy = sx * min(n, abs(v[0])), sy * min(n, abs(v[1]))
            if not self.Move([dx, dy]):
                return False

    def offCourse(self, pos, cell, port):
        """how far a cell lies off the straight course to the port:
        its distance to me plus its distance to the port, minus the
        length of the course"""
        return (
            self.dist(pos, cell)
            + self.dist(cell, port)
            - self.dist(pos, port)
        )

    # --- grazing ---------------------------------------------------------

    def floorOf(self, food, share=None):
        """energy to leave in a cell so that it regrows fastest"""
        capacity = self.maxamount * self.fertility(food["position"])
        share = self.FLOOR_SHARE if share is None else share
        return max(self.killLine, int(share * capacity))

    def wanted(self, food, ripe=False):
        """is one bite of this cell worth taking, given how hungry I am:
        a comfortable sailor leaves a cell where it regrows fastest, a
        hungry one leaves it alive, a starving one leaves nothing. With `ripe`, only a cell above the
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
        """bite what is under my feet while it is worth biting.
        Returns the energy eaten."""
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

    def harbourLeft(self, foods, pos):
        """energy still worth taking in view, for the log"""
        return sum(
            max(0, f["energy"] - self.bite - self.floorOf(f))
            for f in foods
            if self.dist(pos, f["position"]) <= self.harbour
            and f["energy"] - self.bite >= self.floorOf(f)
        )

    # --- the voyage ------------------------------------------------------

    def castOff(self, foods, pos, left):
        """log the port and set course for the next one worth a call"""
        port = self.route[self.leg % len(self.route)]
        self.log[port] = [self.turn, int(left)]
        self.Broadcast(self.readOut())
        n = len(self.route)
        for k in range(1, n):
            leg = (self.leg + k) % n
            if self.dryUntil(self.route[leg]) <= self.turn:
                break
        else:
            leg = (self.leg + 1) % n
        self.leg = leg
        self.stay = 0
        self.arrived = 0

    def flee(self, pos, bullies):
        v = [0, 0]
        for o in bullies:
            t = getShortestTranslation(pos, o["position"], self.length)
            d = max(1, max(abs(t[0]), abs(t[1])))
            v[0] -= t[0] / d
            v[1] -= t[1] / d
        if abs(v[0]) < 1e-9 and abs(v[1]) < 1e-9:
            v = [1, 0]
        sx = (v[0] > 0.3) - (v[0] < -0.3)
        sy = (v[1] > 0.3) - (v[1] < -0.3)
        if sx == 0 and sy == 0:
            sx = 1 if abs(v[0]) >= abs(v[1]) else 0
            sy = 0 if sx else 1
        n = self.time() // (self.moveTime * (abs(sx) + abs(sy)))
        if n > 0:
            self.Move([sx * n, sy * n])

    def main(self):
        self.turn += 1
        pos = list(self.position())
        energy = self.energy()
        seen = self.closerLook()
        foods = [o for o in seen if o["type"] == "food"]
        strangers = [
            o
            for o in seen
            if o["type"] == "wesen" and o["source"] != self.source
        ]
        crew = sum(
            1
            for o in seen
            if o["type"] == "wesen" and o["source"] == self.source
        )
        if self.leg is None:
            self.leg = self.nearestLeg(pos)

        # anything that could kill me and reach me: run, whole budget
        damage = self.attackDamage()
        bullies = [
            o
            for o in strangers
            if o["energy"] * damage >= energy
            and self.dist(pos, o["position"]) <= self.reach
        ]
        if bullies:
            self.flee(pos, bullies)
            return

        # old age: split whatever the weather, Reproduce resets the clock
        if self.age() >= self.oldAge and energy >= self.minBirthEnergy():
            child = self.Reproduce()
            if child:
                self.Talk(child, self.readOut(self.leg + 1))

        eaten = self.eatHere(foods, pos)
        pos = list(self.position())
        port = self.portAt(self.leg)
        inHarbour = self.dist(pos, port) <= self.harbour
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

        if inHarbour:
            if not self.arrived:
                self.arrived = self.turn
                self.stay = 0
                self.landfall(ripe < self.BREED_RIPE)
            self.stay += 1
            # a birth on the quay, unless the log says the coast is
            # busy: the child sails on to the next port
            if (
                ripe >= self.BREED_RIPE
                and not self.busy()
                and crew < self.CROWD
                and self.energy() >= self.breedAt
                and (not self.lean() or self.energy() >= 2 * self.breedAt)
            ):
                child = self.Reproduce()
                if child:
                    self.Talk(child, self.readOut(self.leg + 1))
            left = self.harbourLeft(foods, pos)
            if (
                not wanted
                or self.stay > self.maxStay
                or crew >= self.CROWD
            ):
                self.castOff(foods, pos, left)
                self.stepToward(list(self.portAt(self.leg)))
                return
            best = max(
                wanted,
                key=lambda f: (
                    self.foodYield(f)
                    / (1.0 + self.dist(pos, f["position"]))
                ),
            )
            if self.stepToward(list(best["position"])):
                self.eatHere([best], list(self.position()))
            return

        # under way: a bite close to the course is worth putting in for
        near = [
            f
            for f in wanted
            if self.offCourse(pos, f["position"], port) <= self.DETOUR
            or (
                self.energy() < self.comfort
                and self.dist(pos, f["position"]) <= self.stepsPerTurn * 2
            )
        ]
        if near and not eaten:
            best = min(near, key=lambda f: self.dist(pos, f["position"]))
            if self.stepToward(list(best["position"])):
                self.eatHere([best], list(self.position()))
                return
        self.stepToward(list(port))
