"""model and controller for single objects in the simulation"""

from random import random

import numpy as np

from ..point import getRandomPosition, ringBlocks


def stochasticRound(x):
    """rounds x to an int, with the fractional part deciding the
    probability of rounding up, so the expected value is preserved.
    Used wherever a rate smaller than one energy per turn has to be
    applied to integer energies (food growth, wesen upkeep).

    Draws from the standard library rather than from numpy: both are
    seeded from the game seed (see variation.applySeed), and a single
    numpy scalar draw costs about seventy times as much as this one,
    which is worth noticing in a function called once per object per
    turn."""
    base = int(x // 1)
    return base + (1 if random() < (x - base) else 0)


class WorldObject:
    """this class is an abstraction to all world objects,
    as Wesen, Food and maybe some day something else.
    """

    def __init__(self, infoAllObject):
        # self.infoAllObject = infoAllObject;
        self.infoWorld = infoAllObject["world"]
        self.infoObject = infoAllObject["object"]
        self.infoRange = infoAllObject["range"]
        self.objectType = self.infoObject["type"]
        self.energy = self.infoObject["energy"]
        self.DeleteObject = self.infoWorld["DeleteObject"]
        self.AddObject = self.infoWorld["AddObject"]
        self.worldObjects = self.infoWorld["objects"]
        self.map = self.infoWorld["map"]
        self.UpdatePos = self.infoWorld["UpdatePos"]
        self.age = 0
        self.time = 0
        self.source = ""
        self.dead = False
        self.position = self.infoObject.get(
            "position", getRandomPosition(self.infoWorld["length"])
        )

    def __repr__(self):
        return f"<worldobject id={id(self)} pos={self.position} energy={self.energy}>"

    def getRangeIterator(self, radius, condition):
        """returns an iterator of pairs (id, object)
        with all objects in radius that match the condition.

        The radius is taken in the maximum metric on the torus, where
        norm(v) = max(abs(v[0]),abs(v[1])) and both coordinates wrap
        around the edge of the world - exactly as movement does, so a
        wesen standing on the seam sees the ground it is about to walk
        onto."""
        length = self.infoWorld["length"]
        x = self.position[0] % length
        y = self.position[1] % length
        grid = self.map
        if radius <= 0:
            cells = (grid[x][y],)
        else:
            cells = self._occupiedCells(x, y, radius, length)
        for cell in cells:
            # a listener may act on what it hears (Broadcast reaches
            # source code, which can move or attack), so the cell is
            # read as it stands rather than iterated live
            for i, o in list(cell.items()):
                if condition is None or condition(o):
                    yield i, o

    def _occupiedCells(self, x, y, radius, length):
        """the cells of the window around (x, y) that hold anything.

        A look window is a square of side 2*radius+1 on a torus, so it
        is covered by at most four rectangular blocks of the map. Asking
        the world's occupancy grid which cells of a block are non-empty
        costs one numpy call per block and skips the thousands of empty
        cells the window would otherwise walk one at a time, which is
        what used to make looking around the most expensive thing in the
        game by a wide margin."""
        counts = self.infoWorld["counts"]
        grid = self.map
        cells = []
        for x0, x1 in ringBlocks(x, radius, length):
            rows = counts[x0:x1]
            for y0, y1 in ringBlocks(y, radius, length):
                xs, ys = np.nonzero(rows[:, y0:y1])
                if xs.size:
                    for cx, cy in zip(
                        (xs + x0).tolist(), (ys + y0).tolist()
                    ):
                        cells.append(grid[cx][cy])
        return cells

    def Die(self):
        """deletes WorldObject instance from world."""
        self.dead = True
        self.DeleteObject(id(self))

    def getDescriptor(self):
        """return descriptive data for the gui,
        included by the world in World.getDescriptor.
        """
        return {
            "position": self.position,
            "id": id(self),
            "energy": self.energy,
            "age": self.age,
            "type": self.objectType,
        }

    def persist(self):
        """returns JSON serializable object with all information
        needed to restore the state of the object"""
        return {
            "type": self.objectType,
            "energy": self.energy,
            "age": self.age,
            "position": self.position,
            "source": self.source,
            "time": self.time,
        }

    def restore(self, obj):
        """restores state of this objects from obj"""
        self.age = obj["age"]
        self.energy = obj["energy"]
        self.position = obj["position"]
        self.time = obj["time"]

    def _AgeCheck(self):
        """virtual function, look in wesen or food"""
        assert not self.dead

    def _EnergyCheck(self):
        """virtual function, look in wesen or food"""
        assert not self.dead

    def main(self):
        """run one turn of object code"""
        if not self.dead:
            self._EnergyCheck()
        if not self.dead:
            self.age += 1
            self._AgeCheck()
