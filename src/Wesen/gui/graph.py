"""Contains 2 classes:
Graph and _SensorData.
Graph plots several curves,
_SensorData plots a single curve."""

from numpy import array as narray
from OpenGL.arrays import vbo
from OpenGL.GL import (
    GL_ARRAY_BUFFER,
    GL_FLOAT,
    GL_LINE_STRIP,
    GL_STREAM_DRAW,
    GL_VERTEX_ARRAY,
    glColor3f,
    glDisableClientState,
    glDrawArrays,
    glEnableClientState,
    glPopMatrix,
    glPushMatrix,
    glScalef,
    glTranslatef,
    glVertexPointer,
)

from .object import GuiObject
from .text import TextPrinter


def SENSORFCT_FROMSTATS_ENERGY(world):
    return lambda x: world.stats[x]["energy"]


def SENSORFCT_FROMSTATS_COUNT(world):
    return lambda x: world.stats[x]["count"]


def SENSORFCT_FROMSTATS_UPKEEP(world):
    return lambda x: world.stats[x].get("upkeep", 0)


def SENSORFCT_CLIMATE(world):
    return lambda _: world.climateState()["growth"]


# What the graph can show. Every curve is scaled on its own unless a mode
# says "shared", in which case the curves of that mode share one scale and
# are therefore comparable with each other. Without this, total energy and
# the food supply dwarf everything else and the plot says nothing.
GRAPH_MODES = [
    {
        "name": "energy per source",
        "groups": ("source-energy",),
        "scale": "shared",
    },
    {
        "name": "population per source",
        "groups": ("source-count",),
        "scale": "shared",
    },
    {
        "name": "energy and population per source",
        "groups": ("source-energy", "source-count"),
        "scale": "own",
    },
    {
        "name": "the world: food, season, upkeep",
        "groups": ("world",),
        "scale": "own",
    },
    {"name": "everything, own scale", "groups": None, "scale": "own"},
    {"name": "everything, one scale", "groups": None, "scale": "shared"},
]


class Graph(GuiObject):
    """A Graph object plots curves for sensors.
    See AddSensor().
    Currently, there are some default sensors."""

    def __init__(self, gui, world, sourceList, colorList):
        GuiObject.__init__(self, gui)
        self.world = world
        self.shadow = True
        self.maxValue = 20000
        # used to compute y axis scaling
        self.sensors = []
        self.history = []
        # both sensors and history are set in AddSensor.
        self.printer = TextPrinter()
        self.resolution = 400
        self.mode = 0
        self._AddDefaultSensors()
        self._AddObjectEnergySensors(sourceList, colorList)

    def _AddDefaultSensors(self):
        """adds the sensors that describe the world rather than a player"""
        self.AddSensor(
            {
                "f": SENSORFCT_CLIMATE,
                "statskey": None,
                "color": [0.35, 0.35, 0.9],
                "name": "season (food growth)",
                "group": "world",
            }
        )
        self.AddSensor(
            {
                "f": SENSORFCT_FROMSTATS_UPKEEP,
                "statskey": "global",
                "color": [0.8, 0.4, 0.1],
                "name": "upkeep",
                "group": "world",
            }
        )
        self.AddSensor(
            {
                "f": SENSORFCT_FROMSTATS_ENERGY,
                "statskey": "global",
                "color": [0.5, 0.5, 0.5],
                "name": "global energy",
                "group": "world",
            }
        )
        self.AddSensor(
            {
                "f": SENSORFCT_FROMSTATS_ENERGY,
                "statskey": "food",
                "color": [0.0, 1.0, 0.0],
                "name": "food energy",
                "group": "world",
            }
        )
        self.AddSensor(
            {
                "f": SENSORFCT_FROMSTATS_COUNT,
                "statskey": "food",
                "color": [0.0, 0.6, 0.3],
                "name": "food count",
                "group": "world",
            }
        )

    def _AddObjectEnergySensors(self, sourceList, colorList):
        """adds an energy and a population sensor for each source."""
        for wesenSource, color in zip(sourceList, colorList):
            self.AddSensor(
                {
                    "f": SENSORFCT_FROMSTATS_ENERGY,
                    "color": color,
                    "statskey": wesenSource,
                    "name": wesenSource + " energy",
                    "group": "source-energy",
                }
            )
            self.AddSensor(
                {
                    "f": SENSORFCT_FROMSTATS_COUNT,
                    "color": [min(1.0, c + 0.35) for c in color],
                    "statskey": wesenSource,
                    "name": wesenSource + " count",
                    "group": "source-count",
                }
            )

    def CycleMode(self, step=1):
        """switch to the next set of curves (bound to a key)"""
        self.mode = (self.mode + step) % len(GRAPH_MODES)
        return GRAPH_MODES[self.mode]["name"]

    def _visible(self):
        """(sensor, data) pairs the current mode shows"""
        groups = GRAPH_MODES[self.mode]["groups"]
        return [
            (sensor, data)
            for sensor, data in zip(self.sensors, self.history)
            if groups is None or sensor.get("group") in groups
        ]

    def Reshape(self, x, y):
        GuiObject.Reshape(self, x, y)
        self.printer.Reshape(x, y)

    def AddSensor(self, newSensor):
        """AddSensor(newSensor) should be called only
        during initialization, as it erases history.
        newSensor = {f=lambda world : lambda statskey : int,
                        statskey=None,
                        color=[0.0,1.0,0.0],
                        name="some value"}"""
        self.sensors.append(newSensor)
        self.history = [_SensorData(self.resolution) for _ in self.sensors]

    def Step(self):
        """adds current world.stats as data point to all sensors."""
        for sensorInfo, data in zip(self.sensors, self.history):
            try:
                value = sensorInfo["f"](self.world)(sensorInfo["statskey"])
            except Exception:
                # a broken sensor must not stop the game
                value = 0
            data.AddValue(value)

    def DrawPlot(self):
        """Plots the curves the current mode shows, each scaled so that
        it fills the plot: a curve of tens and one of hundreds of
        thousands are both readable, which is the whole point."""
        visible = self._visible()
        if not visible:
            return
        shared = GRAPH_MODES[self.mode]["scale"] == "shared"
        peaks = [max(1e-9, data.windowMax()) for _, data in visible]
        self.maxValue = max(peaks)
        for (sensorInfo, data), peak in zip(visible, peaks):
            reference = self.maxValue if shared else peak
            glPushMatrix()
            # TODO the following is "moving away from frame",
            # and should use the framedata (plastic, etc.)
            # from the GuiObject base class.
            # Probably this stuff should be done in GuiObject!
            glTranslatef(0.005, 0.01, 0.0)
            glScalef(0.99 / self.resolution, 0.7 / reference, 1.0)
            glColor3f(*(sensorInfo["color"]))
            data.Draw()
            glPopMatrix()

    def DrawHint(self):
        """Prints a caption for the plot: the mode, and every curve with
        its current value (the curves have different scales, so the
        numbers are the only way to compare them)"""
        p = self.printer
        p.ResetRaster()
        mode = GRAPH_MODES[self.mode]
        glColor3f(0.85, 0.85, 0.85)
        p.Print("\n")
        p.Print(
            "  [g] {} ({}/{})".format(
                mode["name"], self.mode + 1, len(GRAPH_MODES)
            )
        )
        scale = (
            "one shared scale"
            if mode["scale"] == "shared"
            else ("each curve on its own scale")
        )
        p.Print("\n")
        p.Print(f"  {scale}")
        for sensorInfo, data in self._visible():
            glColor3f(*sensorInfo["color"])
            # to make the color effective for text,
            # we have to call glRasterPos by printing a linebreak:
            p.Print("\n")
            p.Print(f"  {sensorInfo['name']}: {data.lastValue():g}")

    def Draw(self):
        GuiObject.Draw(self)
        self.DrawHint()
        self.DrawPlot()


class _SensorData:
    """A _SensorData object holds the data
    for a single sensor, including previous data.
    It can draw itself via Draw()
    and you can update it via AddValue()"""

    def __init__(self, size):
        self.size = size
        initialBuffer = []
        for x, y in enumerate(range(size)):
            initialBuffer.append(x)
            initialBuffer.append(y)
        self.buf = narray(initialBuffer, "f")
        self.vbo = vbo.VBO(
            self.buf,
            usage=GL_STREAM_DRAW,
            target=GL_ARRAY_BUFFER,
            size=4 * 2 * size,
        )
        self.previous_index = -1
        self.buffer_full = False
        self.maxValue = 0

    def AddValue(self, value):
        """supply one more numerical value"""
        if self.previous_index == self.size - 1 and not (self.buffer_full):
            self.buffer_full = True
        self.previous_index = (self.previous_index + 1) % self.size
        self.buf[self.previous_index * 2 + 1] = value
        self.vbo[
            self.previous_index * 2 + 1 : self.previous_index * 2 + 2
        ] = narray([value], "f")
        self.maxValue = max(self.maxValue, value)

    def windowMax(self):
        """largest value still visible in the plot. Unlike maxValue this
        forgets old spikes, so a curve that once peaked does not stay
        squashed against the bottom forever."""
        values = self.buf[1::2]
        if self.buffer_full:
            return float(values.max())
        if self.previous_index < 0:
            return 0.0
        return float(values[: self.previous_index + 1].max())

    def lastValue(self):
        """the most recent value, for the caption"""
        if self.previous_index < 0:
            return 0
        value = float(self.buf[self.previous_index * 2 + 1])
        return round(value, 2) if abs(value) < 100 else int(value)

    def Draw(self):
        """draw a curve of all previous data,
        up to a certain point (self.resolution)"""
        self.vbo.bind()
        self.vbo.copy_data()
        glEnableClientState(GL_VERTEX_ARRAY)
        glVertexPointer(2, GL_FLOAT, 0, self.vbo)
        if self.buffer_full:
            if self.previous_index != self.size - 1:
                glPushMatrix()
                glTranslatef(-1 * (self.previous_index + 1), 0.0, 0.0)
                glDrawArrays(
                    GL_LINE_STRIP,
                    (self.previous_index + 1),
                    (self.size - self.previous_index - 1),
                )
                glPopMatrix()
            glPushMatrix()
            glTranslatef(self.size - self.previous_index - 1, 0.0, 0.0)
            glDrawArrays(GL_LINE_STRIP, 0, (self.previous_index + 1))
            glPopMatrix()
        else:
            glDrawArrays(GL_LINE_STRIP, 0, (self.previous_index + 1))
        glDisableClientState(GL_VERTEX_ARRAY)
        self.vbo.unbind()
