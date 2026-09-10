"""The Food class, which is present in every simulation."""

from random import random, uniform

import numpy as np

from ..biome import fertilityAt
from ..climate import growthFactor, seedingFactor
from ..point import getRandomPositionInRadius
from .base import WorldObject, stochasticRound


def _bell(n, peak, width):
    """quadratic bump: 1 at n == peak, 0 at |n - peak| == width,
    negative beyond that (clipped at -1)."""
    if width <= 0:
        return 1.0 if n == peak else -1.0
    return max(-1.0, 1.0 - ((n - peak) / width) ** 2)


class Food(WorldObject):
    """unlike wesen, who are programmable and capable of intelligence,
    food can only grow every turn and reproduce over distance.

    Two rule sets are available via the config option food.rule:

    classic
        every turn, grow by uniform(0,2)*growrate and, with probability
        seedrate, drop a seed somewhere within range.seed (unless there
        is already too much food around).

    life
        a semi-continuous cellular automaton in the spirit of Conway's
        Game of Life (or rather Lenia/SmoothLife): the growth of a cell
        depends on the food density in its neighbourhood (sum of the
        energy of all food within range.seed, divided by maxamount).
        Growth is positive near fertile_peak and turns into decay once the
        density is further than fertile_width away from it, so isolated
        cells grow slowly, clusters grow fast, and overcrowded clusters
        starve. Within that, growth is logistic in the cell's own energy
        (see growth()). Seeds only take root where the density is near
        birth_peak (within birth_width), the parent pays seedenergy
        for the seed (so energy is conserved), and the chance to seed
        grows with the parent's energy, so only mature food spreads.
        Food has roots: a bite leaves a cell alive as long as it keeps
        more than seedenergy behind, so a well-grown cell can be grazed
        again and again (see getEaten). A cell with no more than
        bite + seedenergy left is pulled out whole instead, which is
        what stops a herd from mining the whole pasture down to its
        roots: over-grazed cells leave the map rather than lingering as
        a bare cell that still pays a little. Keeping food alive is
        therefore the eater's job, and `bite` is the strongest single
        knob on how hard grazing hits the world.
    """

    # diagnostics: total energy grown by all food (life rule) so far
    totalGrown = 0

    def __init__(self, infoAllWorld):
        WorldObject.__init__(self, infoAllWorld)
        self.source = "food"
        # the global food config, used as fallback for objects created
        # with a partial infoObject (e.g. by Wesen.Vomit)
        self.infoFood = infoAllWorld["food"]
        self.seedrate = self._cfg("seedrate")
        self.growrate = self._cfg("growrate")
        self.rangeseed = self.infoRange["seed"]
        self.maxamount = self._cfg("maxamount")
        self.maxage = self._cfg("maxage")
        self.rule = self._cfg("rule")
        self.seedenergy = self._cfg("seedenergy")
        self.fertilePeak = self._cfg("fertile_peak")
        self.fertileWidth = self._cfg("fertile_width")
        self.birthPeak = self._cfg("birth_peak")
        self.birthWidth = self._cfg("birth_width")
        self.birthMaturity = self._cfg("birth_maturity")
        # the ground under this cell, looked up once (see fertility)
        self._ground = None
        self._fertility = 1.0
        self._capacity = 1

    def _cfg(self, key):
        """returns a config value from this object's info,
        falling back to the global food config."""
        return self.infoObject.get(key, self.infoFood[key])

    def __repr__(self):
        return f"<food id={id(self)} growrate={self.growrate} pos={self.position} energy={self.energy}>"

    def getDescriptor(self):
        """currently doing nothing than returning the WorldObjects getDescriptor."""
        return WorldObject.getDescriptor(self)

    def persist(self):
        """returns JSON serializable object with all information
        needed to restore the state of the object"""
        d = WorldObject.persist(self)
        d.update(
            {
                "seedrate": self.seedrate,
                "growrate": self.growrate,
                "rangeseed": self.rangeseed,
                "maxamount": self.maxamount,
                "maxage": self.maxage,
            }
        )
        return d

    def restore(self, obj):
        """restores the state of the food object"""
        WorldObject.restore(self, obj)
        self.seedrate = obj["seedrate"]
        self.growrate = obj["growrate"]
        self.rangeseed = obj["rangeseed"]
        self.maxamount = obj["maxamount"]
        self.maxage = obj["maxage"]

    def getEaten(self, amount=None):
        """returns the energy taken by the eater.
        With amount None or <= 0 (or amount >= energy) the whole food
        is eaten and dies; otherwise only a bite of the given size is
        taken and the food survives (with less energy).

        With the life rule, food has roots: a bite that still leaves
        more than seedenergy behind keeps the cell alive, so a grown
        patch can be grazed and regrows (slowly, since growth is
        proportional to energy). A bite that would not leave that much
        takes the whole cell and kills it, so grazing a small cell is
        always fatal to it - see the class docstring for why."""
        if (
            self.rule == "life"
            and amount is not None
            and 0 < amount < self.energy - self.seedenergy
        ):
            self.energy -= amount
            return amount
        if amount is None or amount <= 0 or amount >= self.energy:
            energy = self.energy
            if not self.dead:
                self.Die()
            return energy
        self.energy -= amount
        return amount

    def Grow(self):
        """increment energy by some amount (classic rule)."""
        rate = (
            self.growrate * growthFactor(self.infoWorld) * self.fertility()
        )
        self.energy += int(uniform(0, 2) * rate)

    def Seed(self, energy=None):
        """create a new Food instance in seedrange."""
        infoFood = dict(self.infoObject)
        infoFood["energy"] = 1 if energy is None else energy
        infoFood["position"] = getRandomPositionInRadius(
            self.position, self.rangeseed, self.infoWorld["length"]
        )
        newFood = self.AddObject(infoFood)
        newFood._eatFoodAtSamePlace()
        return newFood

    def _AgeCheck(self):
        WorldObject._AgeCheck(self)
        if self.age >= self.maxage:
            self.Die()

    def fertility(self):
        """how good the ground under this cell is (1.0 without a biome).

        Kept rather than looked up: food does not move, and reading one
        value out of the terrain array is expensive enough to notice
        when it happens several times per cell per turn. The position
        and the maximum amount are still checked, because the GUI, a
        restore and the tests can all put a cell down somewhere else,
        and then the ground under it has to follow."""
        position = self.position
        ground = (position[0], position[1], self.maxamount)
        if ground != self._ground:
            self._ground = ground
            self._fertility = fertilityAt(self.infoWorld, position)
            self._capacity = max(1, int(self.maxamount * self._fertility))
        return self._fertility

    def capacity(self):
        """the energy this cell can hold: maxamount on average ground,
        more where the biome is fertile and less where it is poor"""
        self.fertility()
        return self._capacity

    def _EnergyCheck(self):
        WorldObject._EnergyCheck(self)
        if self.energy >= self.capacity():
            self.energy = self.capacity()
        elif self.energy < 0:
            self.energy = 0
            # this happens only if one manipulates food via the GUI
            # TODO the GUI should be more careful and this raise an Error.
            print("warning: food energy lower than zero detected")

    def _hasTooMuchFoodNearby(self):
        """return True as soon as there is a lot of food nearby."""
        for i, _ in enumerate(
            self.getRangeIterator(
                self.rangeseed, condition=lambda o: o.objectType == "food"
            )
        ):
            if i == 10:  # TODO make this number configurable!
                return True
        return False

    def _eatFoodAtSamePlace(self):
        """looks for Food with same position but different id than self and eats it."""
        for obj in [
            obj  # implemented with range iterator to enable changing range to 1 or more later
            for oid, obj in self.getRangeIterator(
                0, condition=lambda o: o.objectType == "food"
            )
            if oid != id(self)
        ]:
            self.energy += obj.getEaten()

    # life rule

    def _foodEnergyAround(self, position):
        """sum of the energy of all food within range.seed of position
        (including food at position itself).
        Uses the field precomputed by the world for this turn if
        available, otherwise iterates the map."""
        field = self.infoWorld.get("foodfield")
        if field is not None:
            return float(field[position[0], position[1]])
        x, y = self.position
        self.position = position
        try:
            return float(
                sum(
                    o.energy
                    for _, o in self.getRangeIterator(
                        self.rangeseed,
                        condition=lambda o: o.objectType == "food",
                    )
                )
            )
        finally:
            self.position = (x, y)

    def density(self):
        """food density around this cell, excluding this cell:
        neighbourhood energy divided by maxamount."""
        around = self._foodEnergyAround(self.position) - self.energy
        return max(0.0, around) / self.maxamount

    def growth(self, n=None):
        """growth factor in [-1, 1] for a given (or the current)
        neighbourhood density n, times growrate this is the expected
        energy change per turn.

        Growth is logistic in the cell's own energy: proportional to
        energy when small, fastest at maxamount/2 (where it equals
        growrate at peak density), zero at maxamount. So a seed needs
        time before it yields, and harvesting a cell down to about half
        its maximum keeps it at its most productive (maximum
        sustainable yield), while eating it up kills the income."""
        if n is None:
            n = self.density()
        season = growthFactor(self.infoWorld)
        fertility = self.fertility()
        # in a hard winter (season < 1) the fertile band narrows, so
        # crowded stands thin out instead of merely growing slower
        width = self.fertileWidth * min(1.0, 0.5 + season)
        g = _bell(n, self.fertilePeak, width)
        # poor ground both grows slower and carries less: e is measured
        # against the local carrying capacity, so growth stops there and
        # a cell pushed above it shrinks back
        e = self.energy / (self.maxamount * fertility)
        if g > 0:
            # only growth follows the season; decay is never slowed by it
            g *= max(-1.0, 4.0 * e * (1.0 - e)) * season * fertility
        else:
            # decay is proportional to size too, but never stalls
            g *= min(1.0, max(e, 0.05))
        return g

    def _lifeGrow(self):
        delta = self.growrate * self.growth() * uniform(0.5, 1.5)
        delta = stochasticRound(delta)
        self.energy += delta
        Food.totalGrown += delta
        if self.energy <= 0:
            self.Die()

    def _lifeSeed(self):
        """with probability seedrate * energy / maxamount, try to drop a
        seed at a random position in range; the seed only takes root if
        the density there is near birth_peak.

        Only a cell that has grown to birth_maturity of its own capacity
        seeds at all. A seed starts small and grows slowly, so this is
        what sets how long the pasture takes to spread over the world;
        the density rules alone decide how dense it ends up."""
        if not self._readyToSeed():
            return None
        return self._placeSeed()

    def _readyToSeed(self):
        """the cheap half of _lifeSeed: is this cell grown enough to try
        at all this turn? Kept apart from the rest because it is a
        handful of comparisons that the batch step asks of the whole
        pasture at once (see stepLifeBatch), while the other half has
        to touch the world."""
        if self.energy <= 2 * self.seedenergy:
            return False
        if self.energy < self.birthMaturity * self.capacity():
            return False
        rate = self.seedrate * seedingFactor(self.infoWorld)
        return random() < rate * self.energy / self.maxamount

    def _placeSeed(self):
        """the other half of _lifeSeed: pick a spot within range and put
        a seed there, if the ground and the local density allow it."""
        target = getRandomPositionInRadius(
            self.position, self.rangeseed, self.infoWorld["length"]
        )
        # a seed takes root more readily on good ground
        if random() >= fertilityAt(self.infoWorld, target):
            return None
        n = self._foodEnergyAround(target) / self.maxamount
        p = _bell(n, self.birthPeak, self.birthWidth)
        if p <= 0 or random() >= p:
            return None
        self.energy -= self.seedenergy
        infoFood = dict(self.infoObject)
        infoFood["energy"] = self.seedenergy
        infoFood["position"] = target
        newFood = self.AddObject(infoFood)
        newFood._eatFoodAtSamePlace()
        return newFood

    def main(self):
        """randomly grow or seed, based on growrate and seedrate.
        When too old, die."""
        WorldObject.main(self)
        # handles age and low-energy death
        if self.dead:
            return
        if self.rule == "life":
            self._lifeSeed()
            if not self.dead:
                self._lifeGrow()
        else:
            if self.age > 10:  # TODO numbers should be a config option
                if random() < self.seedrate:
                    if not self._hasTooMuchFoodNearby():
                        self.Seed()
            self.Grow()


def stepLifeBatch(foods, infoWorld):
    """runs one turn for a whole pasture of life-rule food at once.

    The life rule is the same arithmetic for every cell - clamp to the
    local capacity, grow a turn older, maybe seed, grow - and at a few
    thousand cells the interpreter overhead of doing that one object at
    a time cost more than everything the wesen do put together. Here it
    is done for all of them in a handful of numpy operations. The two
    parts that are not arithmetic, a cell that dies and a cell that
    seeds, are still handled one at a time: both are rare, and both
    have to touch the world.

    ``Food.main`` and the scalar methods it calls remain the readable
    definition of the rule; ``TestLifeBatch`` checks that this agrees
    with them cell for cell.
    """
    living = [food for food in foods if not food.dead]
    if not living:
        return
    field = infoWorld.get("foodfield")
    if field is None:
        # no density field to read: let every cell run its own turn
        for food in living:
            food.main()
        return

    n = len(living)
    energy = np.fromiter((f.energy for f in living), np.float64, n)
    age = np.fromiter((f.age for f in living), np.int64, n)
    maxage = np.fromiter((f.maxage for f in living), np.int64, n)
    maxamount = np.fromiter((f.maxamount for f in living), np.float64, n)
    growrate = np.fromiter((f.growrate for f in living), np.float64, n)
    seedrate = np.fromiter((f.seedrate for f in living), np.float64, n)
    seedenergy = np.fromiter((f.seedenergy for f in living), np.float64, n)
    maturity = np.fromiter(
        (f.birthMaturity for f in living), np.float64, n
    )
    peak = np.fromiter((f.fertilePeak for f in living), np.float64, n)
    spread = np.fromiter((f.fertileWidth for f in living), np.float64, n)
    # fertility() refreshes the cached capacity, so it is read first
    fertility = np.fromiter((f.fertility() for f in living), np.float64, n)
    capacity = np.fromiter((f._capacity for f in living), np.float64, n)
    xs = np.fromiter((f.position[0] for f in living), np.intp, n)
    ys = np.fromiter((f.position[1] for f in living), np.intp, n)
    alive = np.ones(n, dtype=bool)

    # --- WorldObject.main and Food._EnergyCheck / _AgeCheck ---
    # a cell is held to the capacity of the ground it stands on, then
    # grows a turn older, and dies once it is too old
    if (energy < 0).any():
        # only reachable by manipulating food through the GUI
        print("warning: food energy lower than zero detected")
    np.clip(energy, 0.0, capacity, out=energy)
    age += 1
    for i in np.nonzero(age >= maxage)[0].tolist():
        food = living[i]
        food.age = int(age[i])
        food.energy = int(energy[i])
        food.Die()
        alive[i] = False

    # --- Food._readyToSeed ---
    rate = seedrate * seedingFactor(infoWorld)
    ready = (
        alive
        & (energy > 2.0 * seedenergy)
        & (energy >= maturity * capacity)
        & (np.random.random(n) < rate * energy / maxamount)
    )
    seeders = np.nonzero(ready)[0].tolist()
    if seeders:
        for i in seeders:
            food = living[i]
            food.age = int(age[i])
            food.energy = int(energy[i])
            food._placeSeed()
            energy[i] = food.energy
        # a seed can land on a grown cell and swallow it whole, so who
        # is still alive has to be asked again rather than assumed
        alive &= np.fromiter((not f.dead for f in living), bool, n)

    # --- Food.growth ---
    season = growthFactor(infoWorld)
    density = np.maximum(0.0, field[xs, ys] - energy) / maxamount
    width = spread * min(1.0, 0.5 + season)
    safe = np.where(width > 0, width, 1.0)
    bell = np.maximum(-1.0, 1.0 - ((density - peak) / safe) ** 2)
    # a width of zero is a spike: exactly at the peak and nowhere else
    bell = np.where(width > 0, bell, np.where(density == peak, 1.0, -1.0))
    relative = energy / (maxamount * fertility)
    growth = np.where(
        bell > 0,
        # only growth follows the season; decay is never slowed by it
        bell
        * np.maximum(-1.0, 4.0 * relative * (1.0 - relative))
        * season
        * fertility,
        # decay is proportional to size too, but never stalls
        bell * np.minimum(1.0, np.maximum(relative, 0.05)),
    )

    # --- Food._lifeGrow, with stochasticRound over the whole pasture ---
    delta = growrate * growth * np.random.uniform(0.5, 1.5, n)
    floor = np.floor(delta)
    delta = floor + (np.random.random(n) < (delta - floor))
    delta[~alive] = 0.0
    energy += delta
    Food.totalGrown += int(delta.sum())

    for i in np.nonzero(alive)[0].tolist():
        food = living[i]
        food.age = int(age[i])
        food.energy = int(energy[i])
        if food.energy <= 0:
            food.Die()
