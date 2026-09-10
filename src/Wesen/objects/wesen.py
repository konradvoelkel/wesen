"""The class for all data and operations a single Wesen has"""

from ..isolation import DEFAULT_MODE, prepare, readOnly, sealed
from ..sourceloader import loadSource
from .base import WorldObject, stochasticRound


class RuleException(Exception):
    """This exception is thrown whenever a wesen source
    violates the rules of the game."""

    def __init__(self, ruleDescription):
        super().__init__(ruleDescription)


class Wesen(WorldObject):
    """Wesen(infoObject) creates a new Wesen instance.
    infoObject is a Dictionary of Dictionaries, time,range,world,etc.
    """

    # initialization

    def __init__(self, infoAllObject):
        """imports the sourcecode of WesenSource and links the capabilities."""
        WorldObject.__init__(self, infoAllObject)
        self.infoTime = infoAllObject["time"]
        self.infoFood = infoAllObject["food"]
        self.source = self.infoObject["source"]
        self.lastUpkeep = 0
        # the player's own directories first, then the sources shipped
        # with the game; cached, so this costs an import once per source
        WesenSource = loadSource(self.source)
        # class attributes are genetic information, not a shared brain:
        # see isolation.py and [wesen] shared_state
        self.sharedState = self.infoObject.get(
            "shared_state", DEFAULT_MODE
        )
        WesenSource = prepare(WesenSource, self.sharedState)
        infoSource = {"source": self.source}
        infoSourceWorld = self.infoWorld.copy()
        del infoSourceWorld["objects"]
        del infoSourceWorld["AddObject"]
        del infoSourceWorld["DeleteObject"]
        infoSourceWorld.pop("foodfield", None)
        # the occupancy grid is the map counted up, so a source may no
        # more read it than the map itself
        infoSourceWorld.pop("counts", None)
        # a source may ask about a cell, not read the whole terrain
        infoSourceWorld.pop("fertility", None)
        infoAllSource = {
            "world": infoSourceWorld,
            "source": infoSource,
            "time": self.infoTime,
            "range": self.infoRange,
            "wesen": self.infoObject,
            "food": infoAllObject["food"],
        }
        if self.sharedState != "allow":
            # the rules, the season and the terrain are the engine's,
            # and every wesen in the game reads the same dicts: a source
            # may read them, and may not use them as a letterbox. The
            # views stay live, so the climate still changes under them
            infoAllSource["world"] = {
                key: readOnly(value)
                for key, value in infoSourceWorld.items()
            }
            infoAllSource = {
                key: readOnly(value)
                for key, value in infoAllSource.items()
            }
        self.wesenSource = WesenSource(infoAllSource)
        self.Receive = None
        self.PutInterface(self.wesenSource)

    def __repr__(self):
        return f"<wesen id={id(self)} pos={self.position} energy={self.energy} source={str(self.wesenSource)}>"

    def PutInterface(self, source):
        """maps the source functions to the corresponding wesen functions."""
        source.id = self.getId
        source.age = self.getAge
        source.position = self.getPosition
        source.energy = self.getEnergy
        source.time = self.getTime
        source.look = self.look
        source.closerLook = self.closerLook
        source.Move = self.Move
        source.MoveToPosition = self.MoveToPosition
        source.Talk = self.Talk
        source.Eat = self.Eat
        source.Reproduce = self.Reproduce
        source.Attack = self.Attack
        source.Vomit = self.Vomit
        source.Donate = self.Donate
        source.Broadcast = self.Broadcast
        self.Receive = source.Receive

    # small capabilites, no time cost

    def getTime(self):
        """returns time left to do stuff (for free).
        A dead wesen has no time, so that source code looping
        "while self.time() > x" terminates when the wesen dies
        mid-turn (e.g. by vomiting or attacking with too little energy)."""
        return 0 if self.dead else self.time

    def getEnergy(self):
        """returns energy left (for free)"""
        return self.energy

    def getPosition(self):
        """returns own position (for free)"""
        return self.position

    def getId(self):
        """returns own object id (for free)"""
        return id(self)

    def getAge(self):
        """returns own age (for free)"""
        return self.age

    # standard capabilities

    def look(self):
        """returns a list of dictionaries with all visible WorldObjects position,
        objecttype and python id.
        """
        if self._UseTime("look"):
            return [
                {"position": o.position, "type": o.objectType, "id": oid}
                for oid, o in self.getRangeIterator(
                    self.infoRange["look"], condition=lambda x: self != x
                )
            ]
        else:
            return []

    def closerLook(self):
        """returns look() and a few more information, as
        energy, age, time, source (which equals to friend/foe).
        """
        if self._UseTime("closerlook"):
            return [
                {
                    "position": o.position,
                    "type": o.objectType,
                    "id": oid,
                    "energy": o.energy,
                    "age": o.age,
                    "time": o.time,
                    "source": o.source,
                }
                for oid, o in self.getRangeIterator(
                    self.infoRange["closer_look"],
                    condition=lambda x: self != x,
                )
            ]
        else:
            return []

    def Move(self, direction):
        """moves the wesen into a specified direction,
        returns true if any position change happened."""
        if self.dead:
            return False
        direction = [int(dc) for dc in direction]
        # the following code is a more time-efficient way to do
        # usedTime = self.infoTime["move"]*(abs(direction[0])+abs(direction[1]));
        if direction[0] < 0:
            if direction[1] < 0:
                usedTime = (
                    self.infoTime["move"]
                    * -1
                    * (direction[0] + direction[1])
                )
            elif direction[1] > 0:
                usedTime = self.infoTime["move"] * (
                    direction[1] - direction[0]
                )
            else:
                usedTime = self.infoTime["move"] * -1 * direction[0]
        elif direction[0] > 0:
            if direction[1] < 0:
                usedTime = self.infoTime["move"] * (
                    direction[0] - direction[1]
                )
            elif direction[1] > 0:
                usedTime = self.infoTime["move"] * (
                    direction[1] + direction[0]
                )
            else:
                usedTime = self.infoTime["move"] * direction[0]
        else:
            if direction[1] < 0:
                usedTime = self.infoTime["move"] * -1 * direction[1]
            elif direction[1] > 0:
                usedTime = self.infoTime["move"] * direction[1]
            else:
                return False
        if self.time >= usedTime:
            self.time -= usedTime
            oldPos = self.position
            self.position = [
                (pc + dc) % self.infoWorld["length"]
                for (pc, dc) in zip(self.position, direction)
            ]
            self.UpdatePos(id(self), oldPos, self.getDescriptor())
            return True
        else:
            return False

    def MoveToPosition(self, newPosition):
        """moves the wesen to a specified position"""
        newPosition = [int(pc) for pc in newPosition]
        while self.position != newPosition:
            if not self.Move(
                [
                    -1 if nc < pc else 1 if nc > pc else 0
                    for (nc, pc) in zip(newPosition, self.position)
                ]
            ):
                return False
        return True

    def Talk(self, wesenid, message):
        """calls Receive(message) in the wesen specified by wesenid when in range."""
        if self._UseTime("talk"):
            message = self._sealed(message)
            # the condition gets the candidate object, and only that:
            # closing over the loop variables of the loop below made
            # this raise NameError on the first candidate in range
            for _, o in self.getRangeIterator(
                self.infoRange["look"],
                condition=lambda x: (
                    (id(x) == wesenid) and (x.objectType == "wesen")
                ),
            ):
                o.wesenSource.Receive(message)
                return True
        return False

    def Eat(self, foodid):
        """if it's at the same position, eat the food with python object id foodid."""
        if self.dead:
            return False
        if foodid not in self.worldObjects:
            raise RuleException("Tried to eat non-existing food")
        o = self.worldObjects[foodid]
        if (o.position == self.position) and (o.objectType == "food"):
            if self._UseTime("eat"):
                # bite 0 means: eat the whole food at once
                self.energy += o.getEaten(self.infoFood.get("bite", 0))
                return True
        else:
            if o.position != self.position:
                raise RuleException(
                    "In order to eat something, one has to be at the same position. Keep in mind that wesen move and you have to look where they are each turn, as the information from looking around becomes stale quickly!"
                )
            if o.objectType != "food":
                raise RuleException(
                    "In order to eat something, it has to be food."
                )
        return False

    def Reproduce(self):
        """Create a new Wesen instance with the same source and half of
        the remaining energy, which is then subtracted from the
        reproducing wesen. reproduce_cost energy is destroyed by the
        birth, and a birth that would leave the child below
        child_min_energy fails (without costing time).
        """
        if self.dead:
            return False
        cost = self.infoObject.get("reproduce_cost", 0)
        minChild = max(1, self.infoObject.get("child_min_energy", 1))
        childEnergy = (self.energy - cost) // 2
        if childEnergy < minChild:
            return False
        if self._UseTime("reproduce"):
            infoWesen = self.infoObject.copy()
            infoWesen["energy"] = childEnergy
            infoWesen["source"] = self.source
            infoWesen["position"] = self.position
            child = self.AddObject(infoWesen)
            self.energy -= childEnergy + cost
            self.age = 0
            self._EnergyCheck()
            return id(child)
        return False

    def Attack(self, wesenid):
        """attacks the wesen specified by wesenid when it's at the same position.
        the energy of the enemy is subtracted from the own energy,
        so the one who had more energy than his enemy can survive.
        The other Wesen dies.
        """
        if self.dead:
            return False
        try:
            o = self.worldObjects[wesenid]
        except KeyError:
            raise RuleException(
                f"May not attack non-existent enemy with id '{wesenid}'"
            )
        if (o.objectType == "wesen") and (o.position == self.position):
            if self._UseTime("attack"):
                cost = self.infoObject.get("attack_cost", 0.5)
                self.energy -= int(o.getAttacked(self.energy) * cost)
                return not self._EnergyCheck()
        return False

    def getAttacked(self, energy):
        """called when this Wesen is attacked"""
        previousEnergy = self.energy
        damage = self.infoObject.get("attack_damage", 0.75)
        self.energy -= int(energy * damage)
        self._EnergyCheck()
        return previousEnergy

    # advanced capabilites

    def Vomit(self, energy, deathOnLowEnergy=True):
        """turns the given energy into strange food
        (other growing and seeding behaviour).
        the energy is subtracted from the wesen"""
        if self.dead:
            return False
        if self._UseTime("vomit"):
            if energy > self.energy:
                energy = self.energy
                if deathOnLowEnergy:
                    self.Die()
            if not energy <= 0:
                if self.infoFood.get("rule", "classic") == "life":
                    # vomited food is ordinary food: it obeys the same
                    # density rules as everything else, so vomiting is
                    # planting, not free energy
                    infoFood = dict(self.infoFood)
                    infoFood.pop("count", None)
                    infoFood.update(
                        {"energy": energy, "position": self.position}
                    )
                    # a blob bigger than maxamount (a dead body) neither
                    # shrinks nor grows: it lies there until eaten
                    infoFood["maxamount"] = max(
                        infoFood["maxamount"], energy
                    )
                else:
                    # TODO the magic numbers here should be configurable
                    infoFood = {
                        "energy": energy,
                        "position": self.position,
                        "growrate": 1,
                        "seedrate": 0.001,
                        "maxamount": energy + 1000,
                        "maxage": 1000,
                        "type": "food",
                    }
                self.AddObject(infoFood)
                self.energy -= energy
                return True
        return False

    def Donate(self, energy, wesenid):
        """transfer energy from this wesen to another specified by wesenid"""
        if self.dead:
            return False
        try:
            o = self.worldObjects[wesenid]
        except (KeyError, TypeError):
            raise RuleException(
                f"May not donate to non-existent wesen with id '{wesenid}'"
            )
        if (o.objectType == "wesen") and (o.position == self.position):
            if self._UseTime("donate"):
                if energy > self.energy:
                    energy = self.energy
                if not energy <= 0:
                    o.energy += energy
                    self.energy -= energy
                    self._EnergyCheck()
                    return True
        return False

    def Broadcast(self, message):
        """calls Talk(message) with all wesen in range"""
        if self.dead:
            return False
        if self._UseTime("broadcast"):
            # once, not once per listener
            message = self._sealed(message)
            for _, o in self.getRangeIterator(
                self.infoRange["talk"],
                condition=lambda x: self != x and x.objectType == "wesen",
            ):
                o.Receive(message)
            return True
        return False

    def _sealed(self, message):
        """what a message may carry: a value, not a handle.

        Handing another wesen a mutable object would be a shared brain
        with extra steps - both sides would go on reading and writing
        the same dict - so unless the rules allow shared state, what is
        delivered is a frozen copy (see isolation.deepFreeze)."""
        if self.sharedState == "allow":
            return message
        return sealed(message)

    def Die(self):
        if self.energy:
            self.Vomit(self.energy, deathOnLowEnergy=False)
        WorldObject.Die(self)

    # general methods

    def getDescriptor(self):
        """returns a dictionary
        with descriptive information about the wesen for the GUI"""
        descriptor = {
            "source": self.source,
            "sourcedescriptor": self.wesenSource.getDescriptor(),
        }
        descriptor.update(WorldObject.getDescriptor(self))
        return descriptor

    def persist(self):
        """returns JSON serializable object with all information
        needed to restore the state of the object"""
        d = WorldObject.persist(self)
        d.update(
            {
                "wesensource": self.wesenSource.persist(),
                "maxage": self.infoObject["maxage"],
            }
        )
        return d

    def restore(self, obj):
        """restores the state of the wesen object"""
        WorldObject.restore(self, obj)
        self.wesenSource.restore(obj)

    def _UseTime(self, function):
        """if the wesen has enough time,
        return true and subtract the time needed for function;
        else return false.
        """
        usedTime = self.infoTime[function]
        if self.time >= usedTime:
            self.time -= usedTime
            return True
        return False

    def _AgeCheck(self):
        """kills the wesen if it's too old"""
        WorldObject._AgeCheck(self)
        if self.age > self.infoObject["maxage"]:
            self.Die()

    def _EnergyCheck(self):
        """kills the Wesen when energy <= 0"""
        WorldObject._EnergyCheck(self)
        if self.energy <= 0:
            self.Die()
            return True
        return False

    def upkeep(self):
        """energy burnt this turn: a flat base plus a share of the own
        energy. Holding a big body therefore costs, which limits both
        hoarding and unchecked population growth."""
        info = self.infoObject
        return info.get("upkeep", 1) + info.get(
            "upkeep_rate", 0.0
        ) * max(0, self.energy)

    def main(self):
        """runs one turn of wesen code and it's AI code"""
        WorldObject.main(self)
        if not self.dead:
            self.lastUpkeep = stochasticRound(self.upkeep())
            self.energy -= self.lastUpkeep
            if self._EnergyCheck():
                return
            self.time = min(
                self.time + self.infoTime["init"], self.infoTime["max"]
            )
            self.wesenSource.main()
