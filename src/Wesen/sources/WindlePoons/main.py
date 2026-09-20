"""Windle Poons, 130, the oldest wizard of Unseen University, who knew
the hour of his death to the minute, died on schedule, and came back -
Death having been sacked that week - to find that being dead suited
him. This source is about the one rule in the game that fits him: what
becomes of a wesen's energy when it stops being a wesen.

`Vomit(e)` under the life rule (objects/wesen.py) lays e energy down as
food with `maxamount = e`, a blob bigger than any cell can hold, which
"neither shrinks nor grows: it lies there until eaten". It never seeds
(its own maxamount is the denominator of its density test) and it only
expires at food age 1000. And food pays no upkeep. A body burns
`upkeep + upkeep_rate * energy` a turn - 16 for a 3000-energy wizard -
while the same energy in the ground under its wheelchair burns nothing.
That is the Fresh Start Club: a wizard that is mostly dead keeps, every
turn, what a live one would have breathed away. And every hunter in this
game sizes its attack from the residents' visible energy, so a thin
wizard on a fat grave is not worth their trouble.

The catch is the density rule: food growth turns negative once the
energy within `range.seed` is far above `fertile_peak`, so a big blob
is a dead zone twenty cells across. Which is why the wizard keeps the
calendar:

* **Summer** it roams and grazes like anybody, biting only what regrows,
  and splits when fat.
* **Autumn**, at the first lean turn, it picks a cell of good ground
  (a cell's capacity is maxamount x fertility, so on poor ground a
  deposit is clipped on the spot), lays down everything but a fighting
  body, and sits. Being dead in winter costs the pasture nothing it was
  not losing anyway.
* **Winter** it sits on the grave, bites from it as the body needs,
  and says "Hah!" to anything that steps onto the grave that it can
  kill outright: first strike wins, and a thief bites fifteen a turn.
* **Spring** the bank becomes the litter: withdraw and split, withdraw
  and split, until the grave is empty. A child is told at birth where
  the grave is, so that it does not eat its inheritance, and walks off
  to graze. Then the wizard rises and roams.
* **It knows the hour of its death.** `Reproduce()` resets age to 0, so
  at 950 it splits whatever the season, and Death goes away empty-handed.

Without seasons there is no autumn; the wizard settles when it is fat
instead, and the grave is simply where fat is turned into children.

Measured (2026-09-20, solo, 2000 turns, seeds 1-2): the bank saves
0.5% of what is buried per turn, and a child grazing earns several
times that on the same energy, so a wizard that buries 300 loses a
quarter of its score to one that never settles, and one that buries
600 breaks even. Hence SETTLE_MIN: only the fat go to ground. Fat is
rarely right in this game - the field is won by whoever has the most
mouths - and a bank for fat has little to do; it is here for the
winters in which breeding is not.
"""

from random import choice

from ...defaultwesensource import DefaultWesenSource
from ...point import getDistInMaxMetric, getShortestTranslation

POONS = "poons/1"  # our words, and nobody else's
DRIFTS = [
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
]


class WesenSource(DefaultWesenSource):
    BODY_MIN = 400  # the fighting body kept out of the ground
    BODY_MAX = 1000
    DEPOSIT_MIN = 150  # not worth a Vomit below this
    SETTLE_MIN = 1000  # energy before autumn is worth a grave
    SETTLE_FAT = 1500  # without seasons: a grave when this fat
    GRAVE_REACH = 10  # cells to look for good ground
    GRAVE_SPACE = 8  # cells kept from another grave
    THREAT_TTL = 40  # turns a fat stranger is remembered
    LEAVE_HOME = 10  # cells a child walks from its parent's grave
    ROAM_BREED = 600
    EXCURSION = 6  # cells: a winter bite worth leaving the grave for
    LAST_HOUR = 950  # age at which a split is the only thing to do

    def __init__(self, infoAllSource):
        """Do all initialization stuff."""
        DefaultWesenSource.__init__(self, infoAllSource)
        self.turn = 0
        self.state = "roam"
        self.grave = None
        self.parentGrave = None
        self.drift = choice(DRIFTS)
        self.threat = [0, 0]  # fattest stranger seen lately, and when

    def __str__(self):
        return "<Windle Poons, mostly dead>"

    def persist(self):
        return {
            "turn": self.turn,
            "state": self.state,
            "grave": self.grave,
            "parentGrave": self.parentGrave,
            "drift": self.drift,
            "threat": self.threat,
        }

    def restore(self, obj):
        me = obj.get("wesensource") or {}
        self.turn = me.get("turn", 0)
        self.state = me.get("state", "roam")
        self.grave = tuple(me["grave"]) if me.get("grave") else None
        self.parentGrave = (
            tuple(me["parentGrave"]) if me.get("parentGrave") else None
        )
        self.drift = tuple(me.get("drift", (1, 0)))
        self.threat = list(me.get("threat", [0, 0]))

    def Receive(self, message):
        if not self.fromColleague(message):
            return
        if not isinstance(message, dict) or message.get("s") != POONS:
            return
        grave = message.get("grave")
        if (
            isinstance(grave, (tuple, list))
            and len(grave) == 2
            and all(isinstance(c, int) for c in grave)
        ):
            self.parentGrave = (grave[0], grave[1])

    # --- moving and eating ----------------------------------------------

    def dist(self, a, b):
        return getDistInMaxMetric(a, b, self.worldlength)

    def stepToward(self, target, stopAt=0):
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

    def stepAway(self, pos, other, cells):
        v = getShortestTranslation(pos, other, self.worldlength)
        away = [-((v[0] > 0) - (v[0] < 0)), -((v[1] > 0) - (v[1] < 0))]
        if away == [0, 0]:
            away = list(choice(DRIFTS))
        move = self.infoTime["move"]
        n = min(
            cells, self.time() // (move * (abs(away[0]) + abs(away[1])))
        )
        if n > 0:
            self.Move([away[0] * n, away[1] * n])

    def bites(self, foods, pos, until=None, wanted=True):
        """bite the food under my feet: while it is worth biting, or up
        to an energy `until`. Returns the energy eaten."""
        eaten = 0
        eat = self.infoTime["eat"]
        for food in sorted(foods, key=lambda f: -f["energy"]):
            if list(food["position"]) != pos:
                continue
            food = dict(food)
            while self.time() >= eat and food["energy"] > 0:
                if until is not None and self.energy() >= until:
                    return eaten
                if wanted and until is None and not self.foodWanted(food):
                    break
                bite = self.foodYield(food)
                if not self.Eat(food["id"]):
                    break
                eaten += bite
                food["energy"] -= bite
        return eaten

    def bodyTarget(self):
        """the body kept out of the ground: enough to kill outright the
        fattest stranger seen lately, within reason"""
        if self.turn - self.threat[1] > self.THREAT_TTL:
            self.threat = [0, self.turn]
        need = int(self.threat[0] / max(0.05, self.attackDamage())) + 30
        return max(self.BODY_MIN, min(self.BODY_MAX, need))

    def split(self):
        """a child, told where the grave is"""
        child = self.Reproduce()
        if child and self.grave is not None:
            self.Talk(
                child,
                {"s": POONS, "grave": (self.grave[0], self.grave[1])},
            )
        return child

    # --- the grave -------------------------------------------------------

    def isGrave(self, food):
        """a blob bigger than any cell can hold: somebody's bank, or a
        body. Not to be settled next to, and not ours to eat when it
        is the parent's"""
        return food["energy"] > 1.6 * self.infoFood["maxamount"]

    def pickGrave(self, pos, foods, strangers):
        """the most fertile cell in reach that would hold a deposit
        without clipping it, away from other graves and strangers"""
        graves = [tuple(f["position"]) for f in foods if self.isGrave(f)]
        best, bestScore = None, 0.0
        reach = self.GRAVE_REACH
        length = self.worldlength
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                cell = ((pos[0] + dx) % length, (pos[1] + dy) % length)
                fertility = self.fertility(list(cell))
                if fertility < 1.0:
                    continue
                score = fertility - 0.01 * max(abs(dx), abs(dy))
                if score <= bestScore:
                    continue
                if any(
                    self.dist(cell, g) < self.GRAVE_SPACE for g in graves
                ):
                    continue
                if any(
                    self.dist(cell, o["position"]) <= 2 for o in strangers
                ):
                    continue
                best, bestScore = cell, score
        return best

    def hah(self, pos, strangers):
        """strike a stranger on the grave that I can kill outright and
        afford to. True if I struck."""
        cost = self.attackCost()
        damage = self.attackDamage()
        thieves = [
            o
            for o in strangers
            if list(o["position"]) == pos
            and o["energy"] <= self.energy() * damage
            and self.energy() - o["energy"] * cost >= self.BODY_MIN // 2
        ]
        if not thieves or self.time() < self.infoTime["attack"]:
            return False
        return bool(
            self.Attack(max(thieves, key=lambda o: o["energy"])["id"])
        )

    # --- the turns -------------------------------------------------------

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
        if strangers:
            fattest = max(o["energy"] for o in strangers)
            if (
                fattest >= self.threat[0]
                or self.turn - self.threat[1] > self.THREAT_TTL
            ):
                self.threat = [fattest, self.turn]

        # the hour of his death
        if self.age() >= self.LAST_HOUR:
            if self.energy() < self.minBirthEnergy():
                self.bites(
                    foods, pos, until=self.minBirthEnergy(), wanted=False
                )
            if self.split():
                return

        if self.state == "sit":
            self.sitTurn(pos, foods, strangers)
        else:
            self.roamTurn(pos, foods, strangers)

    def roamTurn(self, pos, foods, strangers):
        damage = self.attackDamage()
        bullies = [
            o
            for o in strangers
            if self.dist(pos, o["position"]) <= 1
            and o["energy"] * damage >= self.energy()
        ]
        if bullies:
            self.stepAway(
                pos, max(bullies, key=lambda o: o["energy"])["position"], 3
            )
            return

        # autumn: the fat go to ground
        seasons = self.season().get("enable")
        settle = self.energy() >= max(
            self.SETTLE_MIN if seasons else self.SETTLE_FAT,
            self.bodyTarget() + self.DEPOSIT_MIN,
        )
        if settle and (self.lean() or not seasons):
            grave = self.pickGrave(pos, foods, strangers)
            if grave is not None:
                self.grave, self.state = grave, "sit"
                self.sitTurn(pos, foods, strangers)
                return

        # a child leaves its inheritance alone, and leaves
        if self.parentGrave is not None:
            if self.dist(pos, self.parentGrave) >= self.LEAVE_HOME:
                self.parentGrave = None
            else:
                foods = [
                    f
                    for f in foods
                    if tuple(f["position"]) != self.parentGrave
                ]

        self.bites(foods, pos)
        ripe = sum(1 for f in foods if self.foodRipe(f))
        if (
            self.energy() >= self.ROAM_BREED
            and ripe >= 3
            and not self.lean()
        ):
            self.split()

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
                self.bites([nearest], list(self.position()))
            return

        # nothing in view: drift, away from the parent's grave if any
        if self.parentGrave is not None:
            self.stepAway(pos, self.parentGrave, 3)
            return
        if self.turn % 12 == 0:
            self.drift = choice(DRIFTS)
        dx, dy = self.drift
        move = self.infoTime["move"]
        n = self.time() // (move * (abs(dx) + abs(dy)))
        if n > 0:
            self.Move([dx * n, dy * n])

    def sitTurn(self, pos, foods, strangers):
        grave = list(self.grave)
        if pos != grave:
            if not self.stepToward(grave):
                return
            pos = list(self.position())
        bank = [f for f in foods if list(f["position"]) == pos]
        banked = sum(f["energy"] for f in bank)
        target = self.bodyTarget()

        if self.hah(pos, strangers):
            return

        if self.lean():
            # winter: the body stays what it needs to be, the rest is ground
            surplus = self.energy() - target
            if surplus >= self.DEPOSIT_MIN and self.fertility() >= 1.0:
                if self.time() >= self.infoTime["vomit"]:
                    self.Vomit(surplus)
                return
            if self.energy() < target and banked:
                self.bites(bank, pos, until=target, wanted=False)
                return
            # an excursion: a ripe cell in view is still income, and the
            # wheelchair comes back to the grave next turn
            taken = {tuple(o["position"]) for o in strangers}
            wanted = [
                f
                for f in foods
                if list(f["position"]) != pos
                and tuple(f["position"]) not in taken
                and self.foodRipe(f)
                and self.dist(pos, f["position"]) <= self.EXCURSION
            ]
            if wanted:
                nearest = min(
                    wanted, key=lambda f: self.dist(pos, f["position"])
                )
                if self.stepToward(list(nearest["position"])):
                    self.bites([nearest], list(self.position()))
                return
            if not banked and self.energy() < target:
                # nothing left to live on: the wheelchair goes grazing
                self.grave, self.state = None, "roam"
            return

        # spring: the grave becomes the litter
        if banked:
            litter = max(self.minBirthEnergy(), 2 * 240 + self.birthCost())
            if self.energy() >= litter:
                self.split()
            elif self.time() >= self.infoTime["eat"]:
                self.bites(bank, pos, until=litter, wanted=False)
            return
        self.grave, self.state = None, "roam"
