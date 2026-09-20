"""the scanner: it used to run over the world like a scanner head, one
row at a time, eating what it happened to cross. On a torus of 500 cells
with 12 cells of sight that is a look at each cell once every 140 turns
whether or not there was ever anything there, and it starved in 200.

It still scans - it is a *police* scanner now. `Broadcast` reaches every
wesen within `range.talk` whatever its source, and the big colonies in
this game run on it: a Rincewind broadcasts its ledger every turn - food
cells with the energy it read there, alarms, where its colleagues are
and how fat - and Weatherwax says what it saw of the pasture. The engine
stamps every message with who really sent it, so the Scanner knows whose
channel it is listening to; it does not need to know their protocol.
Anything inside a stranger's message that looks like `(x, y, energy)`
is a tip, and a tip about a cell nobody is standing on is a meal it did
not have to find.

So the Scanner does no surveying of its own. It drifts toward the crowd,
listens, walks to the best fresh tip, and relays the best of what it
heard to its colleagues on a channel of its own. Where the air is
silent it falls back to the sweep it was born with, which at least
finds the crowd. It is a parasite, and it gets stronger the more the
others talk.
"""

from ...defaultwesensource import DefaultWesenSource
from ...point import getDistInMaxMetric, getShortestTranslation

CHANNEL = "scanner/1"  # our relays, and nobody else's


class WesenSource(DefaultWesenSource):
    TIP_TTL = 80  # turns a tip stays worth walking to
    TIPS_KEPT = 60
    TIP_REACH = 50  # cells: further than that it is stale on arrival
    RELAY_EVERY = 8  # turns between relays to colleagues
    RELAY_TIPS = 8
    SCAN_ITEMS = (
        300  # most entries read out of one message (cpu, not time)
    )
    STAND_OFF = 6  # cells to keep from the crowd we listen to
    BREED_AT = 350

    def __init__(self, infoAllSource):
        """Do all initialization stuff."""
        DefaultWesenSource.__init__(self, infoAllSource)
        self.turn = 0
        self.movecount = 0
        self.tips = {}  # (x, y) -> [energy, turn heard]
        self.going = None  # the tip I am walking to

    def __str__(self):
        return "<Police Scanner>"

    def persist(self):
        return {
            "turn": self.turn,
            "movecount": self.movecount,
            "going": self.going,
            "tips": [[x, y, e, t] for (x, y), (e, t) in self.tips.items()],
        }

    def restore(self, obj):
        me = obj.get("wesensource") or {}
        self.turn = me.get("turn", 0)
        self.movecount = me.get("movecount", 0)
        going = me.get("going")
        self.going = tuple(going) if going else None
        self.tips = {(x, y): [e, t] for x, y, e, t in me.get("tips", [])}

    # --- listening -------------------------------------------------------

    def tip(self, x, y, energy, heard):
        """a cell somebody says holds food: worth keeping if a bite there
        would leave it growing, i.e. if it is worth the walk"""
        if energy < self.infoFood["maxamount"] // 2 + (
            self.foodBite() or 0
        ):
            return
        self.tips[(x, y)] = [energy, heard]
        if len(self.tips) > self.TIPS_KEPT:
            oldest = min(self.tips, key=lambda k: self.tips[k][1])
            del self.tips[oldest]

    def overhear(self, value, budget, depth=0):
        """everything in a stranger's message that looks like a food
        reading: a tuple starting with two coordinates and an amount.
        Returns the budget of entries left to read."""
        if budget <= 0 or depth > 4:
            return budget
        if isinstance(value, dict):
            for item in value.values():
                budget = self.overhear(item, budget - 1, depth + 1)
            return budget
        if not isinstance(value, (tuple, list)):
            return budget
        length = self.worldlength
        if (
            len(value) >= 3
            and all(
                isinstance(c, int) and not isinstance(c, bool)
                for c in value[:3]
            )
            and 0 <= value[0] < length
            and 0 <= value[1] < length
            and 0 < value[2] <= 2 * self.infoFood["maxamount"]
        ):
            self.tip(value[0], value[1], value[2], self.turn)
            return budget - 1
        for item in value:
            budget = self.overhear(item, budget - 1, depth + 1)
        return budget

    def Receive(self, message):
        if not isinstance(message, dict) or self.sender(message) is None:
            return
        if self.fromColleague(message):
            if message.get("s") != CHANNEL:
                return
            for entry in message.get("tips", ()):
                if (
                    isinstance(entry, (tuple, list))
                    and len(entry) == 4
                    and all(isinstance(c, int) for c in entry)
                ):
                    self.tip(
                        entry[0],
                        entry[1],
                        entry[2],
                        self.turn - max(0, entry[3]),
                    )
            return
        self.overhear(message, self.SCAN_ITEMS)

    def relay(self):
        """pass the best tips on to colleagues in earshot"""
        if self.turn % self.RELAY_EVERY or not self.tips:
            return
        best = sorted(self.tips.items(), key=lambda kv: -kv[1][0])[
            : self.RELAY_TIPS
        ]
        self.Broadcast(
            {
                "s": CHANNEL,
                "tips": [
                    (x, y, e, self.turn - t) for (x, y), (e, t) in best
                ],
            }
        )

    # --- moving ----------------------------------------------------------

    def dist(self, a, b):
        return getDistInMaxMetric(a, b, self.worldlength)

    def stepToward(self, target, stopAt=0):
        """walk toward a cell as far as this turn's time allows, stopping
        `stopAt` cells short. True once there."""
        move = self.infoTime["move"]
        while True:
            v = getShortestTranslation(
                self.position(), target, self.worldlength
            )
            d = max(abs(v[0]), abs(v[1]))
            if d <= stopAt:
                return True
            sx = (v[0] > 0) - (v[0] < 0)
            sy = (v[1] > 0) - (v[1] < 0)
            n = min(
                d - stopAt, self.time() // (move * (abs(sx) + abs(sy)))
            )
            if n <= 0:
                return False
            dx, dy = sx * min(n, abs(v[0])), sy * min(n, abs(v[1]))
            if not self.Move([dx, dy]):
                return False

    def sweep(self):
        """the scanner head: along the row, next row at the end. It finds
        the crowd sooner or later, and the crowd is where the talk is."""
        move = self.infoTime["move"]
        n = self.time() // move
        if n <= 0:
            return
        if self.movecount >= self.worldlength:
            self.Move([1, 1])
            self.movecount = 1
        elif self.Move([n, 0]):
            self.movecount += n

    # --- eating ----------------------------------------------------------

    def eatHere(self, foods, pos):
        eaten = 0
        eat = self.infoTime["eat"]
        for food in foods:
            if list(food["position"]) != pos:
                continue
            food = dict(food)
            while self.time() >= eat and self.foodWanted(food):
                bite = self.foodYield(food)
                if not self.Eat(food["id"]):
                    break
                eaten += bite
                food["energy"] -= bite
                if food["energy"] <= 0:
                    break
        return eaten

    def main(self):
        self.turn += 1
        pos = list(self.position())
        seen = self.closerLook()
        foods = [o for o in seen if o["type"] == "food"]
        strangers = [
            o
            for o in seen
            if o["type"] == "wesen" and o["source"] != self.source
        ]
        damage = self.attackDamage()

        # tips about cells in view are checked against what is there
        reach = self.infoRange["closer_look"]
        here = {tuple(f["position"]): f["energy"] for f in foods}
        for key in [k for k in self.tips if self.dist(pos, k) <= reach]:
            if key in here:
                self.tips[key][0] = here[key]
            else:
                del self.tips[key]
        for key in [
            k
            for k, v in self.tips.items()
            if self.turn - v[1] > self.TIP_TTL
        ]:
            del self.tips[key]
        if self.going is not None and self.going not in self.tips:
            self.going = None

        # something that could kill me, on my cell or next to it: away
        bullies = [
            o
            for o in strangers
            if self.dist(pos, o["position"]) <= 1
            and o["energy"] * damage >= self.energy()
        ]
        if bullies:
            v = getShortestTranslation(
                pos,
                max(bullies, key=lambda o: o["energy"])["position"],
                self.worldlength,
            )
            away = [
                -((v[0] > 0) - (v[0] < 0)) * 3,
                -((v[1] > 0) - (v[1] < 0)) * 3,
            ]
            if away == [0, 0]:
                away = [3, 0]
            self.Move(away)
            return

        self.eatHere(foods, pos)
        self.relay()

        ripe = sum(1 for f in foods if self.foodRipe(f))
        if (
            self.energy() >= self.BREED_AT
            and (ripe >= 2 or len(self.tips) >= 3)
            and (not self.lean() or self.energy() >= 800)
        ):
            self.Reproduce()

        # a bite in view beats any tip; never onto a stranger's cell
        taken = {tuple(o["position"]) for o in strangers}
        wanted = [
            f
            for f in foods
            if list(f["position"]) != pos
            and tuple(f["position"]) not in taken
            and self.foodWanted(f)
        ]
        if wanted:
            nearest = min(
                wanted, key=lambda f: self.dist(pos, f["position"])
            )
            if self.stepToward(list(nearest["position"])):
                self.eatHere([nearest], list(self.position()))
            return

        # the best tip: rich, fresh and not too far
        if self.going is None and self.tips:
            best = max(
                self.tips,
                key=lambda k: (
                    self.tips[k][0]
                    - 3 * self.dist(pos, k)
                    - (self.turn - self.tips[k][1])
                ),
            )
            if self.dist(pos, best) <= self.TIP_REACH:
                self.going = best
        if self.going is not None:
            self.stepToward(list(self.going))
            return

        # nothing heard: keep near the crowd, or sweep for one
        if strangers:
            nearest = min(
                strangers, key=lambda o: self.dist(pos, o["position"])
            )
            if self.dist(pos, nearest["position"]) > self.STAND_OFF + 4:
                self.stepToward(list(nearest["position"]), self.STAND_OFF)
            return
        self.sweep()
