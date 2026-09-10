"""One seed, one game.

`[world] seed` is the promise the whole project rests on: a game can be
replayed, a source can be compared against itself, and a measurement
means something. It is also the easiest promise in a simulation to break
by accident - an unseeded draw, a value that depends on when a module
was imported, an iteration order that follows Python's per-process hash
randomisation - and none of those show up in a single run.

So this runs the same game twice in two fresh interpreters, with
different `PYTHONHASHSEED` values, and compares what the world looks
like afterwards. It is the slowest test in the suite by far and worth
every second of it.
"""

if __name__ == "__main__":
    import sys

    sys.path.append("../src")

import hashlib
import os
import subprocess
import sys
import unittest
from os.path import abspath, dirname, join

SRC = join(dirname(dirname(abspath(__file__))), "src")

# a small, quick world holding one source of each kind there is: a
# forager, a grazer, a scanner-and-fighter and a colony that talks
SOURCES = "Dwarf,GreatRabbit,Nightwatch,Rincewind"
TURNS = 60
LENGTH = 120
SEED = 20260910


def playAndDigest(seed=SEED, sources=SOURCES, turns=TURNS, preload=False):
    """runs a game and returns a fingerprint of the world afterwards.

    Everything the game is made of goes in - where each object is, how
    much energy and how old it is, and the per-source statistics - so
    any difference at all in how the game went changes the answer.

    `preload` imports every source before the game is seeded, which is
    what the launcher does when it checks that the sources named in the
    config are all there. The digest must not depend on it."""
    from Wesen.defaults import CONFIG_DEFAULTS
    from Wesen.sourceloader import loadSource
    from Wesen.variation import applySeed
    from Wesen.world import World

    config = {k: dict(v) for k, v in CONFIG_DEFAULTS.items()}
    config["gui"]["enable"] = False
    config["world"].update(
        {"length": LENGTH, "seed": seed, "Debug": lambda _: None}
    )
    config["wesen"].update({"sources": sources.split(","), "count": 3})
    config["food"]["count"] = 300
    if preload:
        for name in sources.split(","):
            loadSource(name)
    applySeed(config, announce=False)
    world = World(config)
    for _ in range(turns):
        world.main()
    state = sorted(
        (
            o.objectType,
            getattr(o, "source", ""),
            o.position[0],
            o.position[1],
            o.energy,
            o.age,
        )
        for o in world.objects.values()
    )
    stats = sorted(
        (name, entry["count"], entry["energy"])
        for name, entry in world.stats.items()
    )
    return hashlib.sha256(repr((state, stats)).encode()).hexdigest()


RUNNER = """
import sys
sys.path.insert(0, %r)
sys.path.insert(0, %r)
from tests.determinism import playAndDigest
print(playAndDigest(preload=%r))
"""


def digestInFreshProcess(hashSeed, preload=False):
    """plays the game in a new interpreter, so that anything decided
    when a module is first imported is decided again"""
    env = dict(os.environ, PYTHONHASHSEED=str(hashSeed))
    env.pop("PYTHONWARNINGS", None)
    project = dirname(dirname(abspath(__file__)))
    out = subprocess.run(
        [sys.executable, "-c", RUNNER % (SRC, project, preload)],
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
        check=False,
    )
    if out.returncode != 0:
        raise AssertionError(
            f"the game did not run:\n{out.stdout}\n{out.stderr}"
        )
    return out.stdout.strip().splitlines()[-1]


class TestOneSeedOneGame(unittest.TestCase):
    def test_the_same_seed_replays_in_the_same_process(self):
        self.assertEqual(playAndDigest(), playAndDigest())

    def test_a_different_seed_is_a_different_game(self):
        """the cheap check that the test above is checking anything"""
        self.assertNotEqual(playAndDigest(), playAndDigest(seed=SEED + 1))

    def test_the_same_seed_replays_in_a_fresh_interpreter(self):
        """Two new processes, and different hash randomisation in each.

        This is what catches a draw taken while a module is being
        imported - when that happens is not part of the game - and any
        place where the order of a dict or a set has leaked into the
        rules."""
        first = digestInFreshProcess(0)
        second = digestInFreshProcess(1)
        self.assertEqual(
            first,
            second,
            "the same seed gave two different games in two "
            "interpreters: something in the engine or in a source is "
            "drawing random numbers outside the seed, or is following "
            "an iteration order that is not the same every run",
        )

    def test_a_game_replays_however_the_sources_were_loaded(self):
        """The launcher imports every source before the world is built,
        so that a missing one is said plainly; a script that drives the
        engine imports them while building it. When a source's module is
        first imported is not part of the game and must not change how
        the game goes - which it does the moment anything is drawn while
        a module is being read."""
        self.assertEqual(
            digestInFreshProcess(0),
            digestInFreshProcess(0, preload=True),
            "the game came out differently depending on when its "
            "sources were imported: something is drawing random "
            "numbers at import time, before the game is seeded",
        )

    def test_every_shipped_source_replays(self):
        """the sources in the default config, played together"""
        from Wesen.defaults import CONFIG_DEFAULTS

        every = CONFIG_DEFAULTS["wesen"]["sources"]
        self.assertEqual(
            playAndDigest(sources=every, turns=25),
            playAndDigest(sources=every, turns=25),
        )


if __name__ == "__main__":
    unittest.main()
