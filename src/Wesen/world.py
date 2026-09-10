"""The world in which Wesen takes place"""

import json
import traceback

import numpy as np

from . import isolation
from .biome import Biome
from .climate import Climate
from .defaults import CONFIG_DEFAULTS, DEFAULT_GAME_STATE_FILE
from .objects.food import Food, stepLifeBatch
from .objects.wesen import RuleException, Wesen


class World:
    """A World object contains a single Wesen simulation,
    In the MVC paradigm it is M+C.
    The main() method runs a single simulation turn.
    The getDescriptor() method returns descriptive data for viewers.
    Via AddObject(info) and DeleteObject(id)
    one can manipulate the simulation."""

    def __init__(
        self, infoAllWorld=None, createObjects=True, callbacks={}
    ):
        """infoAllWorld is a dictionary of dictionaries"""
        self.callbacks = callbacks
        if infoAllWorld is not None:
            self.setInfoAllWorld(infoAllWorld)
            if createObjects:
                self.createDefaultObjects()
            self.initStats()

    def setInfoAllWorld(self, infoAllWorld):
        """sets the infoAllWorld and initializes member variables"""
        # copy everything that will be modified
        self.infoAllWorld = infoAllWorld.copy()
        self.infoAllWorld.update(
            {k: infoAllWorld[k].copy() for k in ("wesen", "world", "food")}
        )
        # config files written before seasons or biomes existed have
        # neither section
        for section in ("climate", "biome"):
            self.infoAllWorld[section] = dict(
                CONFIG_DEFAULTS[section],
                **infoAllWorld.get(section, {}),
            )
        self.objects = {}
        self.turns = infoAllWorld.get("turns", 0)
        self.stats = {}
        # source name -> number of turns that ended in an error, and the
        # error messages already reported (see noteFault)
        self.faults = {}
        self.reported = set()
        self.sharedState = self.infoAllWorld["wesen"].get(
            "shared_state", isolation.DEFAULT_MODE
        )
        length = infoAllWorld["world"]["length"]
        # a plain list of lists, not a numpy object array: the map is
        # only ever indexed one cell at a time, and double-indexing an
        # object array is about three times slower than a nested list,
        # which matters because the range iterators are the hot loop
        self.map = [[{} for _ in range(length)] for _ in range(length)]
        # how many objects stand on each cell, kept in step with the map
        # by AddObject, DeleteObject and UpdatePos. This is what lets a
        # range scan ask numpy for the handful of occupied cells in a
        # window instead of walking every cell of it (see
        # WorldObject._occupiedCells)
        self.counts = np.zeros((length, length), dtype=np.int32)
        # is initialized depending on sources in initStats()
        self.infoAllWorld["world"].update(
            {
                "DeleteObject": self.DeleteObject,
                "AddObject": self.AddObject,
                "UpdatePos": self.UpdatePos,
                "objects": self.objects,
                "map": self.map,
                "counts": self.counts,
            }
        )
        self.infoAllWorld["food"]["type"] = "food"
        self.infoAllWorld["wesen"]["type"] = "wesen"
        self.infoAllWorld["wesen"]["sources"].sort()
        # the climate state dict is shared (never rebound), so food
        # objects and AI sources always read the current season
        self.climate = Climate(self.infoAllWorld["climate"])
        self.infoAllWorld["world"]["climate"] = self.climate.state
        # the terrain is derived from the game seed alone, so restoring
        # a game rebuilds exactly the same map
        self.biome = Biome(
            self.infoAllWorld["biome"],
            length,
            self.infoAllWorld["world"].get("seed", 0),
        )
        self.infoAllWorld["world"]["fertility"] = self.biome.field
        # sources may ask about a single cell, not read the whole map
        self.infoAllWorld["world"]["Fertility"] = self.biome.at

    def setCallbacks(self, callbacks):
        """used by UI to manipulate the world
        >>> set(callbacks.keys()) == set(["DeleteObject", "AddObject", "UpdatePos"])
        True
        """
        self.callbacks = callbacks

    def createDefaultObjects(self):
        """creates all objects (wesen and food) as specified by self.infoAllWorld"""
        self.objects = {}
        for entry in self.infoAllWorld["wesen"]["sources"]:
            for _ in range(self.infoAllWorld["wesen"]["count"]):
                temp = self.infoAllWorld["wesen"].copy()
                temp["source"] = entry
                self.AddObject(temp)
        infoFood = self.infoAllWorld["food"]
        for _ in range(infoFood["count"]):
            food = self.AddObject(infoFood)
            # random initial age, so the initial food does not all die
            # of old age in the same turn
            food.age = np.random.randint(0, infoFood["maxage"])

    def initStats(self):
        """resets self.stats to count and energy 0 for all object-types"""
        stats = {
            "food": {"count": 0, "energy": 0, "upkeep": 0},
            "global": {"count": 0, "energy": 0, "upkeep": 0},
        }
        for source in self.infoAllWorld["wesen"]["sources"]:
            stats[source] = {"count": 0, "energy": 0, "upkeep": 0}
        self.stats = stats

    def DeleteObject(self, objectid):
        """removes an object from the world."""
        pos = self.objects[objectid].position
        del self.map[pos[0]][pos[1]][objectid]
        self.counts[pos[0], pos[1]] -= 1
        del self.objects[objectid]
        self.callbacks.get("DeleteObject", lambda _id: None)(objectid)
        return True

    def AddObject(self, infoObject):
        """adds an object to the world."""
        infoAllObject = {
            "world": self.infoAllWorld["world"],
            "range": self.infoAllWorld["range"],
            "time": self.infoAllWorld["time"],
            "food": self.infoAllWorld["food"],
            "object": infoObject,
        }
        infoAllObject["world"].update({"objects": self.objects})
        if infoObject["type"] == "wesen":
            newObject = Wesen(infoAllObject)
        elif infoObject["type"] == "food":
            newObject = Food(infoAllObject)
        else:
            raise Exception("invalid objectType: " + infoObject["type"])
        self.objects[id(newObject)] = newObject
        self.map[newObject.position[0]][newObject.position[1]][
            id(newObject)
        ] = newObject
        self.counts[newObject.position[0], newObject.position[1]] += 1
        self.callbacks.get("AddObject", lambda _id, obj: None)(
            id(newObject), newObject.getDescriptor()
        )
        return newObject

    def UpdatePos(self, _id, oldPos, obj):
        """updates the map about an objects position"""
        del self.map[oldPos[0]][oldPos[1]][_id]
        self.counts[oldPos[0], oldPos[1]] -= 1
        newPos = obj["position"]
        self.map[newPos[0]][newPos[1]][_id] = self.objects[_id]
        self.counts[newPos[0], newPos[1]] += 1
        self.callbacks.get("UpdatePos", lambda _id, obj: None)(_id, obj)

    def updateFoodField(self):
        """precomputes, for every position, the sum of the energy of all
        food within range.seed (maximum metric), as used by the "life"
        food rule. Stored in infoAllWorld["world"]["foodfield"], where
        Food objects find it. A no-op for the classic rule."""
        if self.infoAllWorld["food"].get("rule", "classic") != "life":
            self.infoAllWorld["world"]["foodfield"] = None
            return
        length = self.infoAllWorld["world"]["length"]
        r = self.infoAllWorld["range"]["seed"]
        cells = [
            o for o in self.objects.values() if o.objectType == "food"
        ]
        count = len(cells)
        energies = np.fromiter(
            (o.energy for o in cells), np.float64, count
        )
        total = float(energies.sum())
        # every energy is a whole number, so as long as the whole
        # pasture stays well inside the range where a float32 counts
        # integers exactly, the prefix sums below are exact in it and
        # cost about a third of what they cost in double precision
        dtype = np.float32 if total < 2**23 else np.float64
        grid = np.bincount(
            np.fromiter(
                (o.position[0] * length + o.position[1] for o in cells),
                np.intp,
                count,
            ),
            weights=energies,
            minlength=length * length,
        ).reshape(length, length)
        # box sum via 2D prefix sums; pad by r+1 on the low side and r
        # on the high side, so the box never leaves the array. The world
        # is a torus and food seeds across the seam, so the padding
        # wraps too: without it the edges would look like empty ground
        # and the density rules would read them as room to grow
        padded = np.pad(
            grid.astype(dtype, copy=False),
            ((r + 1, r), (r + 1, r)),
            mode="wrap",
        )
        s = padded.cumsum(0, dtype=dtype)
        s.cumsum(1, dtype=dtype, out=s)
        low = slice(None, -2 * r - 1)
        high = slice(2 * r + 1, None)
        # written in place after the first subtraction: the whole point
        # of this function is to touch the map once instead of once per
        # food cell, and the temporaries were most of what was left
        field = s[high, high] - s[low, high]
        field -= s[high, low]
        field += s[low, low]
        self.infoAllWorld["world"]["foodfield"] = field

    def checkSharedState(self):
        """A source's class attributes are its genes, not a notebook the
        whole colony writes in (see isolation.py). The engine freezes
        them and gives every wesen its own copy, but a name can always
        be pointed at something new, so what is left is checked here
        and reported once, like any other rule violation."""
        if self.sharedState == "allow":
            return
        for source, name in isolation.audit():
            counts = self.faults.setdefault(
                source, {"rule": 0, "error": 0}
            )
            counts["rule"] += 1
            print(
                f"wesen: {source}: rule violation in turn {self.turns}: "
                f"replaced the shared class attribute '{name}'. Class "
                f"attributes are genetic information: they are the same "
                f"for every wesen of a source and for the whole game. "
                f"Use the instance for what a wesen learns, and Talk or "
                f"Broadcast for what it wants to pass on."
            )

    def noteFault(self, obj, exc, rule):
        """One object's turn raised. A buggy AI source must not end the
        game for everybody, so the turn is skipped and counted; the first
        occurrence of each distinct error is printed in full, and rule
        violations are counted separately because they are the source
        breaking a game rule rather than crashing."""
        source = getattr(obj, "source", "?")
        kind = "rule violation" if rule else "error"
        counts = self.faults.setdefault(source, {"rule": 0, "error": 0})
        counts["rule" if rule else "error"] += 1
        key = (source, kind, str(exc))
        if key in self.reported:
            return
        self.reported.add(key)
        print(f"wesen: {source}: {kind} in turn {self.turns}: {exc}")
        if not rule:
            print(traceback.format_exc())
        print(f"wesen: {source} keeps playing, this turn was skipped.")

    def climateState(self):
        """the current season, for the GUI (see climate.py)"""
        return self.climate.state

    def fertilityMap(self):
        """the terrain, for the GUI (see biome.py); None when off"""
        return self.biome.field

    def getDescriptor(self):
        """returns a list of descriptive information for the GUI"""
        return [o.getDescriptor() for o in self.objects.values()]

    def DumpGameState(self, filename=DEFAULT_GAME_STATE_FILE):
        """writes the whole game state to a given filename (as JSON)"""
        # TODO move this to wesend, where it belongs!
        with open(filename, "w") as f:
            jsonDump = self.persistToJSON()
            f.write(jsonDump)

    def persist(self):
        """returns a JSON serializable object.

        This object contains all information needed to restore the exact same
        state of the world."""
        d = {
            "world": self.infoAllWorld[
                "world"
            ].copy(),  # need to copy, since we are modifying it
            "climate": self.infoAllWorld["climate"],
            "climatestate": self.climate.persist(),
            "biome": self.infoAllWorld["biome"],
            "wesen": self.infoAllWorld["wesen"],
            "range": self.infoAllWorld["range"],
            "time": self.infoAllWorld["time"],
            "food": self.infoAllWorld["food"],
            "objects": [o.persist() for o in self.objects.values()],
            "turns": self.turns,
        }
        d["world"].pop("Debug", None)
        d["world"].pop("map", None)
        d["world"].pop("counts", None)
        d["world"].pop("DeleteObject", None)
        d["world"].pop("AddObject", None)
        d["world"].pop("objects", None)
        d["world"].pop("UpdatePos", None)
        d["world"].pop("foodfield", None)
        d["world"].pop("climate", None)
        d["world"].pop("fertility", None)
        d["world"].pop("Fertility", None)
        return d

    def restore(self, obj):
        """restores the state of the world represented by obj"""
        if "climatestate" in obj:
            self.climate.restore(obj["climatestate"])
            self.climate.step(self.turns)
        # emptied in place: the map and the occupancy grid are published
        # in infoAllWorld and held by every object already built, so
        # they have to stay the same two objects
        self.objects.clear()
        for row in self.map:
            for cell in row:
                cell.clear()
        self.counts[:] = 0
        for infoObj in obj["objects"]:
            newObj = self.AddObject(infoObj)
            newObj.restore(infoObj)

    def persistToJSON(self):
        """returns the persistency info as a JSON string"""
        d = self.persist()
        return json.dumps(d)

    def restoreFromJson(self, string):
        # TODO figure out if restore and restoreFromJson are both needed
        """restores the state of the world from a JSON string"""
        obj = json.loads(string)
        self.setInfoAllWorld(obj)
        self.restore(obj)

    def stepFood(self, food):
        """the food half of a turn.

        The life rule is the same arithmetic for every cell, so the
        whole pasture is stepped at once (see food.stepLifeBatch); a
        few thousand cells taking their turns one at a time used to
        cost as much as everything the wesen do. Anything else still
        runs object by object."""
        batched = []
        for o in food:
            if o.dead:
                # eaten while the wesen were taking their turns
                continue
            if o.rule == "life":
                batched.append(o)
                continue
            try:
                o.main()
            except Exception as exc:  # noqa: BLE001
                self.noteFault(o, exc, rule=False)
        if not batched:
            return
        try:
            stepLifeBatch(batched, self.infoAllWorld["world"])
        except Exception as exc:  # noqa: BLE001
            # a bug in here is the engine's, not a player's, but it
            # still must not end the game for everybody
            self.noteFault(batched[0], exc, rule=False)

    def main(self):
        """runs one turn of Game code (and all objects code, including the AI)"""
        self.turns += 1
        self.initStats()
        stats = self.stats
        self.climate.step(self.turns)
        self.updateFoodField()
        if self.turns % 50 == 0:
            self.checkSharedState()
        # the snapshot is inevitable, as a turn adds and removes
        # objects; taking it up front is also what keeps an object born
        # this turn from acting in it
        wesen = []
        food = []
        for o in list(self.objects.values()):
            if o.objectType == "wesen":
                # a restored game may hold wesen of a source that is not
                # in this config's list, so the entry is made on demand
                counts = stats.setdefault(
                    o.source, {"count": 0, "energy": 0, "upkeep": 0}
                )
                counts["count"] += 1
                counts["energy"] += o.energy
                counts["upkeep"] += o.lastUpkeep
                wesen.append(o)
            else:
                stats["food"]["count"] += 1
                stats["food"]["energy"] += o.energy
                food.append(o)
        for o in wesen:
            try:
                o.main()
            except RuleException as exc:
                # the source broke a rule of the game (see wesen.py)
                self.noteFault(o, exc, rule=True)
            except Exception as exc:  # noqa: BLE001
                # the source (or the engine) has a bug: skip its turn,
                # never end the game for the other players
                self.noteFault(o, exc, rule=False)
        self.stepFood(food)
        stats["global"] = {
            "count": len(self.objects),
            "energy": sum(
                objectType["energy"] for objectType in stats.values()
            ),
            "upkeep": sum(
                objectType["upkeep"] for objectType in stats.values()
            ),
        }
        self.stats = stats
