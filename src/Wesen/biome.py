"""Biomes: a static map of how fertile each cell of the world is.

The world is uniform ground otherwise, so every place is worth as much as
every other and there is nothing to hold. A fertility map turns the map
into terrain: food grows faster and to a higher local carrying capacity in
the rich regions, so those regions are worth defending, worth migrating
to, and worth fighting over.

The map is value noise: a coarse random grid, drawn from the game seed and
interpolated smoothly over the world with wrap-around (the world is a
torus), in two octaves so the regions have some structure rather than
being round blobs. It is generated from the seed alone, so nothing but the
seed has to be persisted, and the same game always has the same terrain.

Fertility lies in ``[1 - strength, 1 + strength]`` and multiplies both the
growth rate of a food cell and the energy it can reach (see
``Food.growth``), and the chance of a seed to take root at a place (see
``Food._lifeSeed``).
"""

import numpy as np

# used when no game seed is set, so a world built without Wesend (tests,
# tuning scripts) still has a reproducible map
DEFAULT_SEED = 20260908


def _octave(length, cells, rs):
    """one octave of value noise: a cells x cells random grid, smoothly
    interpolated up to length x length, wrapping at the edges"""
    grid = rs.uniform(-1.0, 1.0, (cells, cells))
    steps = np.arange(length) * (cells / length)
    low = np.floor(steps).astype(int) % cells
    high = (low + 1) % cells
    t = steps - np.floor(steps)
    t = t * t * (3.0 - 2.0 * t)  # smoothstep, so the seams are invisible
    tx = t[:, None]
    ty = t[None, :]
    return (
        grid[np.ix_(low, low)] * (1 - tx) * (1 - ty)
        + grid[np.ix_(high, low)] * tx * (1 - ty)
        + grid[np.ix_(low, high)] * (1 - tx) * ty
        + grid[np.ix_(high, high)] * tx * ty
    )


class Biome:
    """the fertility map; see the module docstring"""

    def __init__(self, infoBiome, length, seed=0):
        self.enabled = bool(infoBiome.get("enable", False))
        self.length = length
        self.scale = max(2, int(infoBiome.get("scale", 80)))
        self.strength = float(infoBiome.get("strength", 0.0))
        self.seed = int(seed) or DEFAULT_SEED
        self.field = self._build()

    def _build(self):
        """the fertility array, or None when biomes are switched off"""
        if not self.enabled or self.strength <= 0:
            return None
        rs = np.random.RandomState(self.seed % (2**32))
        cells = max(2, round(self.length / self.scale))
        noise = _octave(self.length, cells, rs)
        # a second, finer octave at half the weight, so a region has
        # some texture instead of being one smooth blob
        noise += 0.5 * _octave(self.length, cells * 2, rs)
        peak = float(np.abs(noise).max()) or 1.0
        return 1.0 + self.strength * (noise / peak)

    def at(self, position):
        """fertility of one cell (1.0 when biomes are switched off)"""
        if self.field is None:
            return 1.0
        return float(self.field[position[0] % self.length][
            position[1] % self.length
        ])

    def describe(self):
        """min/mean/max, for the tuning scripts"""
        if self.field is None:
            return {"enable": False, "min": 1.0, "mean": 1.0, "max": 1.0}
        return {
            "enable": True,
            "min": float(self.field.min()),
            "mean": float(self.field.mean()),
            "max": float(self.field.max()),
        }


def fertilityAt(infoWorld, position):
    """fertility of a cell of the world a food object lives in, 1.0 when
    there is no biome, so callers need no special case"""
    field = infoWorld.get("fertility")
    if field is None:
        return 1.0
    return float(field[position[0]][position[1]])
