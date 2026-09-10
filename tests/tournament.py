"""Unit tests for the scoreboard.

What a tournament measures decides what sources are written, so the
arithmetic behind the scores is worth pinning down - especially the
thing the new scores exist for: a source that swarms at the last moment
wins on final energy and should not win on the mean.
"""

if __name__ == "__main__":
    import sys

    sys.path.append("../src")

import json
import tempfile
import unittest
from os.path import join

from Wesen import tournament


def played(curve, name="test"):
    """a Result fed one energy figure per turn (count 1 while it has
    energy, which is what being alive means here)"""
    result = tournament.Result(name, len(curve))
    for turn, energy in enumerate(curve, start=1):
        result.note(turn, {"energy": energy, "count": 1 if energy else 0})
    return result


class TestScoring(unittest.TestCase):
    def test_the_mean_is_the_area_under_the_curve(self):
        result = played([10, 20, 30, 40])
        self.assertEqual(result.area, 100)
        self.assertEqual(result.mean, 25)
        self.assertEqual(result.peak, 40)
        self.assertEqual(result.energy, 40)

    def test_a_late_swarm_does_not_win_on_the_mean(self):
        """the whole reason for the change: whoever happens to be
        breeding at the final turn takes the old score"""
        steady = played([100] * 99 + [100])
        latecomer = played([1] * 99 + [5000])
        self.assertGreater(latecomer.energy, steady.energy)
        self.assertGreater(steady.mean, latecomer.mean)

    def test_survival_counts_the_turns_a_source_was_alive(self):
        result = played([50, 50, 50, 0, 0])
        self.assertEqual(result.alive, 3)
        self.assertEqual(result.lastAlive, 3)
        self.assertAlmostEqual(result.survival, 0.6)

    def test_a_source_that_never_lived_scores_nothing(self):
        result = played([0, 0, 0])
        self.assertEqual((result.mean, result.survival), (0, 0))


class TestCombining(unittest.TestCase):
    def test_several_games_are_averaged_and_wins_counted(self):
        games = [
            {
                "A": played([100, 100], "A"),
                "B": played([10, 10], "B"),
            },
            {"A": played([50, 50], "A"), "B": played([10, 10], "B")},
        ]
        _text, rows = tournament.combine(games)
        self.assertEqual([row["source"] for row in rows], ["A", "B"])
        self.assertEqual(rows[0]["mean"], 75)
        self.assertEqual(rows[0]["wins"], 2)
        self.assertEqual(rows[1]["wins"], 0)

    def test_the_table_says_when_the_two_rankings_disagree(self):
        results = {
            "steady": played([100] * 100, "steady"),
            "latecomer": played([1] * 99 + [5000], "latecomer"),
        }
        text = tournament.table(results)
        self.assertIn("by final energy instead", text)
        self.assertLess(
            text.index("steady"), text.index("latecomer"), text
        )


class TestPlayingATournament(unittest.TestCase):
    """the whole thing, on a world small enough to be a unit test"""

    def run_(self, *extra):
        folder = tempfile.mkdtemp()
        out = join(folder, "scores.json")
        tournament.main(
            [
                "--turns",
                "12",
                "--length",
                "40",
                "--count",
                "2",
                "--every",
                "0",
                "--quiet",
                "--sources",
                "DrunkenSailor,GreatRabbit",
                "--json",
                out,
                *extra,
            ]
        )
        with open(out) as handle:
            return json.load(handle)

    def test_a_tournament_scores_every_source(self):
        scores = self.run_("--seeds", "3")
        self.assertEqual(
            scores["sources"], ["DrunkenSailor", "GreatRabbit"]
        )
        self.assertEqual(len(scores["games"]), 1)
        for entry in scores["games"][0].values():
            self.assertEqual(entry["alive"], 12)
            self.assertGreater(entry["mean"], 0)

    def test_several_seeds_are_played_and_summarised(self):
        scores = self.run_("--seeds", "3,4")
        self.assertEqual(scores["seeds"], [3, 4])
        self.assertEqual(len(scores["games"]), 2)
        self.assertEqual(sum(row["wins"] for row in scores["summary"]), 2)

    def test_a_seed_replays(self):
        """everything about a game is a function of its seed - except
        how long the machine took over it, which is the one number in
        the scoreboard that is measured rather than played"""

        def scores(game):
            return {
                name: {
                    key: value
                    for key, value in entry.items()
                    if key != "seconds"
                }
                for name, entry in game.items()
            }

        first = self.run_("--seeds", "5")["games"][0]
        second = self.run_("--seeds", "5")["games"][0]
        self.assertEqual(scores(first), scores(second))
        self.assertNotEqual(first["GreatRabbit"]["seconds"], 0)

    def test_an_unknown_source_is_reported_and_nothing_is_played(self):
        with self.assertRaises(SystemExit) as caught:
            tournament.main(
                ["--sources", "NoSuchWesen", "--turns", "1", "--quiet"]
            )
        self.assertEqual(caught.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
