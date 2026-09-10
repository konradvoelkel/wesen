"""defines an interface for AI code"""

from hashlib import sha256
from random import Random


class DefaultWesenSource:
    """each AI code should subclass this class."""

    def __init__(self, infoAllSource):
        """links a few variables to infoAllSource contents."""
        self.infoSource = infoAllSource["source"]
        self.infoWesen = infoAllSource["wesen"]
        self.infoFood = infoAllSource["food"]
        self.infoWorld = infoAllSource["world"]
        self.infoTime = infoAllSource["time"]
        self.infoRange = infoAllSource["range"]
        self.worldlength = self.infoWorld["length"]
        self.source = self.infoSource["source"]

    def getDescriptor(self):
        """currently unused, designed for debugging and UI"""
        return {}

    def persist(self):
        """returns JSON serializable object with all information
        needed to restore the state of the object

        subclasses need to add all information they need to restore their state"""
        return {}

    def restore(self, obj):
        """given a dict obj as returned by persist,
        to restore internal state of AI"""

    def Receive(self, message):
        """message should be a dict"""

    # --- food economy helpers (work for both food rules) -----------------
    # food dicts are the entries of closerLook() (they carry "energy").

    def foodRule(self):
        """"classic" or "life", see objects/food.py"""
        return self.infoFood.get("rule", "classic")

    def foodRoots(self):
        """energy a bite leaves behind (life rule: seedenergy), else 0"""
        if self.foodRule() == "life":
            return self.infoFood.get("seedenergy", 0)
        return 0

    def foodBite(self):
        """energy one Eat() takes at most; None means the whole food"""
        bite = self.infoFood.get("bite", 0)
        return bite if bite > 0 else None

    def foodYield(self, food):
        """energy one Eat() on this food would return right now"""
        energy = food["energy"]
        bite = self.foodBite()
        if bite is not None and 0 < bite < energy - self.foodRoots():
            return bite
        return energy

    def foodKills(self, food):
        """True if one Eat() would remove this food for good"""
        return self.foodYield(food) >= food["energy"]

    def foodSustainable(self, food):
        """True if one Eat() leaves the food alive and regrowing"""
        return not self.foodKills(food)

    def foodRipe(self, food):
        """True if one Eat() leaves the food at least half grown, where
        it regrows fastest (life rule); any food under the classic rule"""
        if self.foodRule() != "life":
            return food["energy"] > 0
        bite = self.foodBite() or 0
        return food["energy"] - bite >= self.infoFood["maxamount"] // 2

    def foodWanted(self, food, hungry=100, starving=40):
        """ripe food is always wanted; below `hungry` energy also a bite
        that leaves the food alive; below `starving` anything at all"""
        if self.foodRipe(food):
            return True
        energy = self.energy()
        if energy < hungry and self.foodSustainable(food):
            return True
        return energy < starving and self.foodYield(food) > 0

    # --- the rules of this particular game -------------------------------
    # Time costs, ranges, food parameters and the numbers below may be
    # varied per game (see variation.py) and food growth follows the
    # season (see climate.py), so read them instead of hardcoding them.

    def season(self):
        """the current season as a dict with the keys "enable",
        "season" (spring/summer/autumn/winter), "phase" (0..1 through
        the year), "growth" (food growth multiplier, 1 is normal),
        "severity" and "period". Always safe to call."""
        climate = self.infoWorld.get("climate")
        if not climate:
            return {
                "enable": False,
                "season": "summer",
                "phase": 0.0,
                "growth": 1.0,
                "severity": 1.0,
                "period": 0,
            }
        return climate

    def growthFactor(self):
        """food growth multiplier right now (1.0 without seasons)"""
        season = self.season()
        return season["growth"] if season.get("enable") else 1.0

    def lean(self):
        """True while food grows more slowly than normal: the time to
        live off the body instead of expanding"""
        return self.growthFactor() < 1.0

    def turnsUntilSpring(self):
        """turns until growth is back above normal (0 without seasons)"""
        season = self.season()
        if not season.get("enable") or not season.get("period"):
            return 0
        phase = season["phase"]
        # growth is above 1 for phase in [0, 0.5)
        remaining = (1.0 - phase) if phase >= 0.5 else 0.0
        return int(remaining * season["period"])

    def gameRandom(self, salt=""):
        """a random generator drawn from the game's own seed.

        Every wesen of this source that asks with the same salt gets
        exactly the same numbers, in every game played on that seed, in
        every process. That is what it is for: things a colony has to
        agree on that nobody has to *learn* - a direction to sweep in, a
        division of the map, a rota - where talking would be a waste
        because the answer is the same for everyone from the first turn.

        Never draw at import time or in a class body instead. When a
        module happens to be read is not part of the game, and a draw
        taken then is outside the seed: the same game will play
        differently every time, which is the one thing this project
        cannot afford (see tests/determinism.py).

        For what a wesen *sees*, this is the wrong tool - that has to be
        said out loud (see isolation.py)."""
        material = f"{self.infoWorld.get('seed', 0)}:{self.source}:{salt}"
        return Random(int(sha256(material.encode()).hexdigest()[:16], 16))

    def fertility(self, position=None):
        """how fertile the ground of a cell is (see biome.py): 1.0 is
        average, above 1 grows faster and carries more food, below 1
        less. Defaults to my own cell. Free, and constant over a game."""
        ask = self.infoWorld.get("Fertility")
        if ask is None:
            return 1.0
        return ask(self.position() if position is None else position)

    def attackDamage(self):
        """energy a victim loses per energy of the attacker"""
        return self.infoWesen.get("attack_damage", 0.75)

    def attackCost(self):
        """energy an attacker loses per energy the victim had"""
        return self.infoWesen.get("attack_cost", 0.5)

    def upkeepOf(self, energy):
        """energy per turn a body of the given size burns"""
        return self.infoWesen.get("upkeep", 1) + self.infoWesen.get(
            "upkeep_rate", 0.0
        ) * max(0, energy)

    def birthCost(self):
        """energy destroyed by a birth, on top of the child's half"""
        return self.infoWesen.get("reproduce_cost", 0)

    def minBirthEnergy(self):
        """own energy needed for Reproduce() to succeed at all"""
        return 2 * max(
            1, self.infoWesen.get("child_min_energy", 1)
        ) + self.birthCost()

    def plantEnergy(self):
        """energy to Vomit() for a viable patch: 1 under the classic
        rule; under the life rule at least the roots, and growth is
        proportional to size, so gardening is a slow investment"""
        if self.foodRule() == "life":
            return max(1, self.infoFood.get("seedenergy", 1))
        return 1

    def main(self):
        """called every turn"""
        raise NotImplementedError(
            "Every Wesen Source (AI code) needs a main method"
        )
