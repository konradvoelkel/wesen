"""This class contains the code to run a Wesen game,
with or without GUI,
with or without savegame,
provided a configuration is given."""

import importlib
import json
from os.path import exists
from pprint import pprint

from .defaults import CONFIG_DEFAULTS, DEFAULT_GAME_STATE_FILE
from .isolation import sharing
from .variation import applySeed, applyVariation
from .world import World

# TODO change the name of this class (it is not a daemon)


class Wesend:
    """Wesend(config)
    Runs one Wesen game by start(), with given config data.
    This module intruments a World object
    and, if enabled in the config, a Gui object.
    """

    def __init__(self, config):
        """config should be a dictionary (see loader.py),
        extraArgs are all passed to OpenGL"""
        resume = config.pop("resume", False) and exists(
            DEFAULT_GAME_STATE_FILE
        )
        savedState = None
        if resume:
            with open(DEFAULT_GAME_STATE_FILE) as f:
                savedState = json.loads(f.read())
            # a resumed game keeps the seed and the varied rules it was
            # started with, so it replays identically
            config["world"]["seed"] = savedState.get("world", {}).get(
                "seed", config["world"].get("seed", 0)
            )
            applySeed(config)
        else:
            applySeed(config)
            applyVariation(config)
        self.infoGui = config["gui"]
        self.infoWorld = config["world"]
        self.infoWesen = config["wesen"]
        self.infoFood = config["food"]
        self.infoRange = config["range"]
        self.infoTime = config["time"]
        self.infoClimate = dict(
            CONFIG_DEFAULTS["climate"], **config.get("climate", {})
        )
        if isinstance(self.infoWesen["sources"], str):
            self.infoWesen["sources"] = [
                name.strip()
                for name in self.infoWesen["sources"].split(",")
                if name.strip()
            ]
        self.infoWorld["Debug"] = self.Debug
        infoAllWorld = {
            "world": self.infoWorld,
            "wesen": self.infoWesen,
            "food": self.infoFood,
            "range": self.infoRange,
            "time": self.infoTime,
            "climate": self.infoClimate,
        }
        if savedState is not None:
            infoAllWorld.update(savedState)
            infoAllWorld["world"]["Debug"] = self.Debug
            self.world = World(infoAllWorld, False)
            self.world.restore(infoAllWorld)
        else:
            self.world = World(infoAllWorld)
        self.reportSharedState()

    def reportSharedState(self):
        """say which sources keep state on their class, and what the
        engine did about it (see isolation.py). Silent when there is
        nothing to say or when the rule is switched off."""
        if self.infoWesen.get("shared_state", "isolate") == "allow":
            return
        for source, names in sorted(sharing().items()):
            print(
                f"wesen: {source} keeps state on its class "
                f"({', '.join(names)}); every wesen was given its own "
                f"copy. Class attributes are genetic information, the "
                f"same for every wesen and for the whole game - see "
                f"[wesen] shared_state."
            )

    def start(self, extraArgs=""):
        """starts the simulation (with GUI, if configured)"""
        if self.infoGui["enable"]:
            self.initGUI(extraArgs)
        else:
            self.main()

    def initGUI(self, extraArgs):
        """handing over all control to the gui

        Everything that can keep a window from opening is turned into
        one message that says what to install or which flag to use
        instead: see gui/__init__.py for why the alternative is a
        traceback out of PyOpenGL, or nothing at all. The loader has
        usually asked already; this is the gate for everything that
        did not come through it."""
        from .gui import exitIfGuiUnavailable

        exitIfGuiUnavailable()
        GUI = importlib.import_module(
            ".gui." + self.infoGui["source"], __package__
        ).GUI
        infoGui = {
            "wesend": self,
            "world": self.infoWorld,
            "wesen": self.infoWesen,
            "food": self.infoFood,
            "gui": self.infoGui,
        }
        GUI(infoGui, self.mainLoop, self.world, extraArgs)

    def Debug(self, message):
        """currently just prints the message."""
        # TODO change or remove the Debug mechanism.
        print("debug message: ", message)

    def mainLoop(self):
        """calls world.main() in gui-mode (returns world descriptor)"""
        self.world.main()
        return self.world.getDescriptor()

    def main(self):
        """calls world.main() in gui-less mode,
        until KeyboardInterrupt
        and prints stats every 1000 turns to show some action"""
        while True:
            try:
                self.world.main()
            except KeyboardInterrupt:
                print(" got keyboard interrupt, stopping now.")
                self.world.DumpGameState()
                break
            if (self.world.turns % 1000) == 0:
                print("turn", self.world.turns, "stats:")
                pprint(self.world.stats, indent=3, depth=4, width=80)
