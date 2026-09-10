"""Unit tests for the processor-time budget.

A source is somebody else's program running inside your game, and the
rules of the game say nothing about how long it may take to think. These
tests are about what happens when it takes too long: it loses that turn,
and everyone else plays on (see `Wesen/budget.py`).
"""

if __name__ == "__main__":
    import sys

    sys.path.append("../src")

import unittest

from Wesen import budget
from Wesen.defaults import CONFIG_DEFAULTS
from Wesen.objects.wesen import RuleException
from Wesen.world import World

# small enough to be reached quickly, far above any real turn (the worst
# measured is about 0.05 s)
BUDGET = 0.05
# so that a broken budget fails the test instead of hanging it
PATIENCE = 40_000_000


def burn(rounds=PATIENCE):
    """spends processor time and nothing else"""
    total = 0
    for n in range(rounds):
        total += n * n
    return total


class BudgetTestCase(unittest.TestCase):
    def playWith(self, main, turns=1, cpuBudget=BUDGET, other=None):
        """a world with one greedy source in it, and optionally an
        ordinary one to check that it went on playing"""
        import Wesen.sources.DrunkenSailor.main as greedy

        original = greedy.WesenSource.main
        greedy.WesenSource.main = main
        self.addCleanup(setattr, greedy.WesenSource, "main", original)
        self.addCleanup(budget.disarm)
        sources = ["DrunkenSailor"] + ([other] if other else [])
        config = {k: dict(v) for k, v in CONFIG_DEFAULTS.items()}
        config["gui"]["enable"] = False
        config["world"].update({"length": 40, "Debug": lambda _: None})
        config["wesen"].update(
            {"sources": sources, "count": 1, "cpu_budget": cpuBudget}
        )
        config["food"]["count"] = 5
        world = World(config)
        for _ in range(turns):
            world.main()
        return world


class TestASlowSourceLosesItsTurn(BudgetTestCase):
    def test_a_source_that_thinks_too_long_is_interrupted(self):
        world = self.playWith(lambda self: burn())
        counts = world.faults.get("DrunkenSailor")
        self.assertIsNotNone(counts, "the overrun was not noticed")
        self.assertEqual(counts["rule"], 1)
        self.assertEqual(counts["error"], 0)

    def test_the_rest_of_the_field_plays_on(self):
        world = self.playWith(
            lambda self: burn(), turns=2, other="GreatRabbit"
        )
        self.assertEqual(world.stats["GreatRabbit"]["count"], 1)
        self.assertNotIn("GreatRabbit", world.faults)
        self.assertEqual(world.faults["DrunkenSailor"]["rule"], 2)

    def test_a_source_within_the_budget_is_left_alone(self):
        world = self.playWith(lambda self: self.look(), turns=3)
        self.assertEqual(world.faults, {})

    def test_the_budget_can_be_switched_off(self):
        """0 means no budget, which is the old behaviour: a short
        overrun then simply runs to the end"""
        world = self.playWith(lambda self: burn(2_000_000), cpuBudget=0)
        self.assertEqual(world.faults, {})

    def test_a_source_that_swallows_the_interrupt_gets_it_again(self):
        """the timer repeats, so catching it does not buy a free turn"""
        caught = []

        def greedy(self):
            for _ in range(6):
                try:
                    burn(PATIENCE // 4)
                except RuleException:
                    caught.append(1)
            raise RuleException("done")

        self.playWith(greedy)
        self.assertGreater(len(caught), 1, "the budget fired only once")


class TestTheTimerItself(unittest.TestCase):
    def tearDown(self):
        budget.disarm()

    def test_no_budget_means_no_timer(self):
        self.assertFalse(budget.arm(0, RuleException, "x"))
        self.assertFalse(budget.arm(-1, RuleException, "x"))

    def test_arming_and_disarming_leaves_nothing_behind(self):
        if not budget.available():
            self.skipTest("no setitimer on this platform")
        self.assertTrue(budget.arm(BUDGET, RuleException, "x"))
        budget.disarm()
        burn(PATIENCE // 2)  # would have fired had it stayed armed

    def test_running_out_raises_what_it_was_given(self):
        if not budget.available():
            self.skipTest("no setitimer on this platform")
        budget.arm(BUDGET, RuleException, "out of thought")
        with self.assertRaises(RuleException) as caught:
            burn()
        self.assertIn("out of thought", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
