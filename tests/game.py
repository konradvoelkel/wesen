"""A whole game, played.

The other tests each hold one part of the engine still and check it. This
one just plays: every source shipped with the game, on a fixed seed, for
long enough that food spreads, wesen breed, and somebody gets eaten. What
it asserts is that nothing went wrong - no source raised, no rule was
broken, the map and the world agree afterwards - which is the check that
catches the things unit tests are not looking at.

It is also the sanity check for the rules that are not the default:
per-game variation, and the classic food rule.
"""

if __name__ == "__main__":
    import sys

    sys.path.append("../src")

import unittest

from Wesen.defaults import CONFIG_DEFAULTS
from Wesen.variation import applySeed, applyVariation
from Wesen.world import World

SEED = 20260910
TURNS = 100
LENGTH = 180


def play(turns=TURNS, seed=SEED, variation=False, **sections):
    """plays a game of every shipped source and hands back the world"""
    config = {k: dict(v) for k, v in CONFIG_DEFAULTS.items()}
    for section, values in sections.items():
        config[section].update(values)
    config["gui"]["enable"] = False
    config["world"].update(
        {"length": LENGTH, "seed": seed, "Debug": lambda _: None}
    )
    config["wesen"]["sources"] = CONFIG_DEFAULTS["wesen"]["sources"].split(
        ","
    )
    config["food"].setdefault("count", 400)
    config["food"]["count"] = min(config["food"]["count"], 400)
    config["variation"]["enable"] = variation
    applySeed(config, announce=False)
    if variation:
        applyVariation(config, announce=False)
    world = World(config)
    for _ in range(turns):
        world.main()
    return world


class GameTestCase(unittest.TestCase):
    def assertPlayedCleanly(self, world):
        """what a finished game has to be able to say for itself"""
        self.assertEqual(
            world.faults,
            {},
            "a source broke a rule or raised during the game",
        )
        alive = {
            name: entry["count"]
            for name, entry in world.stats.items()
            if name not in ("food", "global") and entry["count"]
        }
        self.assertTrue(alive, "every source died")
        self.assertGreater(
            world.stats["food"]["count"], 0, "the pasture died out"
        )
        counted = sum(len(cell) for row in world.map for cell in row)
        self.assertEqual(
            counted,
            len(world.objects),
            "the map and the world disagree about what exists",
        )
        self.assertEqual(
            int(world.counts.sum()),
            len(world.objects),
            "the occupancy grid and the world disagree about what exists",
        )


class TestAWholeGame(GameTestCase):
    def test_every_shipped_source_plays_a_game_without_faulting(self):
        self.assertPlayedCleanly(play())

    def test_a_game_with_the_rules_varied(self):
        """[variation] moves every time cost, range and food parameter
        by up to a fifth, which is exactly what a source with a hard
        coded threshold trips over"""
        self.assertPlayedCleanly(play(variation=True))

    def test_a_game_under_the_classic_food_rule(self):
        """the rule the game had until 2026-09; still selectable, so it
        still has to run"""
        self.assertPlayedCleanly(play(food={"rule": "classic"}))

    def test_a_game_without_seasons_or_biomes(self):
        """the flat world the older sources were written for"""
        self.assertPlayedCleanly(
            play(climate={"enable": False}, biome={"enable": False})
        )


class TestTheRulesAreEnforcedInAGame(GameTestCase):
    def test_nobody_keeps_state_on_a_shared_class(self):
        """the colonies were rewritten to talk instead (see
        isolation.py); the audit runs every 50 turns and reports a
        rebinding as a rule violation, so a clean game is the check"""
        world = play(turns=80)
        rebound = [
            source
            for source, counts in world.faults.items()
            if counts["rule"]
        ]
        self.assertEqual(rebound, [])


if __name__ == "__main__":
    unittest.main()
