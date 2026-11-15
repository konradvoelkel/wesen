"""The game as it was, written down.

`tests/determinism.py` asks whether a seed replays, and it can only ever
ask that *inside one environment*: it plays the game twice on the
machine it is running on and compares the two halves against each other.
So the version of numpy, the C library's libm and the CPU's rounding are
all invisible to it. The game can change completely between two Tuesdays
and that test stays green, because both halves of its comparison changed
together.

This is the other half of the promise. It holds the digest of a game
played once and written down, and compares the game that plays now
against it. A failure here usually does not mean somebody broke the
engine: it means the floor moved. A numpy bump is enough. So is a new
glibc under the runner - 2.43 brought a correctly-rounded `asinh`, and
one ULP is a different game once a comparison lands on it. That is
exactly the news this project wants to hear early, because a changed
game quietly invalidates every ranking in `SOURCES.md` and every
measurement in the docs.

The key records what the arithmetic depends on. Python's minor version
and numpy's version, because those two are the arithmetic the engine
runs on and a bump in either is exactly what has to be noticed. (Until
the floor rose to 3.12 the lock held three numpys at once, one per
Python, and no single digest could speak for the whole matrix; it holds
one now, but the key still records which.) The platform and the
machine, because a reference recorded on linux-x86_64 has nothing to
say about what Apple's libm will do. What is deliberately
*not* in the key is the C library - a glibc that changes the game is the
thing this test exists to catch, so it has to arrive as a failure and
not as a polite lookup miss.

To write down the environment you are in:

    uv run python tests/digests.py --record

That rewrites `tests/digests.json` and belongs in a commit of its own,
saying which dependency moved and what it did to the ranking.
"""

if __name__ == "__main__":
    import sys
    from os.path import abspath, dirname, join

    _project = dirname(dirname(abspath(__file__)))
    sys.path[:0] = [_project, join(_project, "src")]

import json
import platform
import sys
import unittest
from os.path import abspath, dirname, join

import numpy

from tests.determinism import playAndDigest

REFERENCES = join(dirname(abspath(__file__)), "digests.json")

# Three seeds rather than one: a single game can agree by luck when a
# change only shows up once a particular comparison is reached, and
# these are cheap next to what determinism.py already plays.
SEEDS = (20260910, 1, 2)


def environmentKey():
    """everything the recorded game is allowed to depend on"""
    machine = platform.machine()
    major, minor = sys.version_info[:2]
    return (
        f"{sys.platform}-{machine}"
        f"-py{major}.{minor}-numpy{numpy.__version__}"
    )


def platformPrefix():
    return f"{sys.platform}-{platform.machine()}-"


def playTheReferenceGames():
    return {str(seed): playAndDigest(seed=seed) for seed in SEEDS}


def loadReferences():
    try:
        with open(REFERENCES) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def writeReferences(references):
    with open(REFERENCES, "w") as f:
        json.dump(references, f, indent=2, sort_keys=True)
        f.write("\n")


class TestTheGameIsStillTheGameItWas(unittest.TestCase):
    def test_the_recorded_games_play_the_same_way_here(self):
        references = loadReferences()
        key = environmentKey()
        here = {
            k: v
            for k, v in references.items()
            if k.startswith(platformPrefix())
        }
        if not here:
            self.skipTest(
                f"no reference game recorded for {platformPrefix()}* - "
                "this platform has never been measured, and nothing "
                "says its libm agrees with the ones that have. "
                "Record it with: "
                "uv run python tests/digests.py --record"
            )
        played = playTheReferenceGames()
        if key in references:
            recorded = references[key]
            for seed in sorted(recorded):
                with self.subTest(seed=seed):
                    self.assertEqual(
                        played.get(seed),
                        recorded[seed],
                        f"seed {seed} does not play the game that was "
                        f"recorded for {key}. The engine may be "
                        "perfectly fine: a numpy bump, a new libm in "
                        "this machine's C library, or different "
                        "hardware is enough to do this. Find out "
                        "which before writing a new reference, "
                        "because every ranking in the docs was "
                        "measured on the old game.",
                    )
            return
        # A combination nobody has measured. Still a failure - an
        # unmeasured environment is not a verified one - but the games
        # have just been played, so the message can say whether the
        # new environment brought a new game with it.
        differs = sorted(
            {
                seed
                for recorded in here.values()
                for seed, digest in recorded.items()
                if played.get(seed) != digest
            }
        )
        known = ", ".join(sorted(here))
        if differs:
            self.fail(
                f"{key} has never been measured, and it does not play "
                f"the game recorded for {known}: seed(s) "
                f"{', '.join(differs)} came out differently. Something "
                "under the game moved along with the interpreter or "
                "numpy. Find out what it did to the ranking before "
                "writing the new reference down:\n"
                "    uv run python tests/digests.py --record"
            )
        self.fail(
            f"{key} has never been measured. It plays the same game as "
            f"{known}, so this is only a new environment to write "
            "down, not a changed game:\n"
            "    uv run python tests/digests.py --record"
        )


def record():
    """plays the reference games here and writes them down"""
    references = loadReferences()
    key = environmentKey()
    before = references.get(key)
    played = playTheReferenceGames()
    if before == played:
        print(f"{key}: unchanged, nothing to write")
        return
    for seed in sorted(played):
        was = (before or {}).get(seed)
        if was is None:
            print(f"  seed {seed}: new, {played[seed]}")
        elif was != played[seed]:
            print(
                f"  seed {seed}: CHANGED\n    was {was}\n    now {played[seed]}"
            )
    references[key] = played
    writeReferences(references)
    print(f"{key}: written to {REFERENCES}")
    if before is not None:
        print(
            "This environment had a reference already and the game has "
            "changed. Say in the commit message what moved, and check "
            "whether the ranking in SOURCES.md still holds."
        )


if __name__ == "__main__":
    if "--record" in sys.argv:
        record()
    else:
        unittest.main()
