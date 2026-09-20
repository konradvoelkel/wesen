"""What the game says before it can say anything else.

The first minute after a clone is the one place where the program has
to explain itself with no help from the reader's knowledge of it. Two
things used to go wrong there and neither showed up in a test, because
both happen outside a game: `wesen` on a machine with no screen died
with one line of freeglut's own and no hint that the game runs
perfectly well without a window, and `wesen --version` reported a
number two releases out of date because it was written out by hand in
a second place.

Nothing here imports OpenGL, so it runs on CI, which has no freeglut -
which is the point: this is what a machine without a display sees.
"""

if __name__ == "__main__":
    import sys

    sys.path.append("../src")

import unittest
from importlib.metadata import PackageNotFoundError, version
from unittest import mock

from Wesen.gui import _libraryProblem, displayProblem
from Wesen.strings import VERSIONSTRING


class DisplayCheck(unittest.TestCase):
    """`wesen` looks for a graphical session before it builds a world"""

    def withEnvironment(self, **environment):
        """runs the check with exactly the given variables set"""
        with mock.patch.dict("os.environ", environment, clear=True):
            return displayProblem()

    def testNoDisplayIsReported(self):
        """the case freeglut would answer by calling exit()"""
        with mock.patch("sys.platform", "linux"):
            problem = self.withEnvironment()
        self.assertIsNotNone(problem)

    def testTheReportSaysWhatToDoInstead(self):
        """a message that only says "no" is the one we are replacing:
        the whole point is that the game is still playable here"""
        with mock.patch("sys.platform", "linux"):
            problem = self.withEnvironment()
        self.assertIn("--disablegui", problem)
        self.assertIn("wesen-tournament", problem)

    def testADisplayIsNoProblem(self):
        for variable in ("DISPLAY", "WAYLAND_DISPLAY"):
            with self.subTest(variable=variable):
                with mock.patch("sys.platform", "linux"):
                    problem = self.withEnvironment(**{variable: ":0"})
                self.assertIsNone(problem)

    def testPlatformsWithoutDisplayVariablesAreLeftAlone(self):
        """macOS and Windows open windows without DISPLAY, so the
        absence of it says nothing there and we must not guess"""
        for platform in ("darwin", "win32"):
            with self.subTest(platform=platform):
                with mock.patch("sys.platform", platform):
                    problem = self.withEnvironment()
                self.assertIsNone(problem)


class MissingLibrary(unittest.TestCase):
    """PyOpenGL and freeglut fail the same way and want opposite
    remedies. Telling the one who has not run `uv sync` yet to
    apt-install a system library sends them off in the wrong
    direction, and that is what the first version of this message
    did."""

    def testAMissingPyOpenGLSaysToSync(self):
        error = ImportError("No module named 'OpenGL'", name="OpenGL")
        problem = _libraryProblem(error)
        self.assertIn("uv sync", problem)
        self.assertNotIn("freeglut3-dev", problem)

    def testAnythingElseIsTakenForFreeglut(self):
        """the GLUT platform module failing to load is freeglut's
        absence wearing an ImportError"""
        error = ImportError("cannot load library", name="OpenGL.GLUT")
        problem = _libraryProblem(error)
        self.assertIn("freeglut3-dev", problem)

    def testEitherWaySaysHowToPlayWithoutOne(self):
        for error in (
            ImportError("gone", name="OpenGL"),
            ImportError("gone", name="OpenGL.GLUT"),
        ):
            with self.subTest(name=error.name):
                self.assertIn("--disablegui", _libraryProblem(error))


class Version(unittest.TestCase):
    """one version number, pyproject.toml's"""

    def testVersionStringMatchesThePackage(self):
        try:
            installed = version("wesen")
        except PackageNotFoundError:
            self.skipTest("running from a source tree, no metadata")
        self.assertEqual(VERSIONSTRING, "wesen " + installed)


if __name__ == "__main__":
    unittest.main()
