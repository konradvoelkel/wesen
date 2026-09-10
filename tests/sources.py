"""Unit tests for finding a player's own source code.

A wesen source is a program somebody wrote, and until 0.8 the only place
the game looked for one was inside its own installation. These tests are
about the places it looks now (see `Wesen/sourceloader.py`): a folder of
the player's own first, the sources shipped with the game after that.
"""

if __name__ == "__main__":
    import sys

    sys.path.append("../src")

import sys
import tempfile
import unittest
from itertools import count
from os import makedirs
from os.path import join

from Wesen import isolation, sourceloader
from Wesen.defaults import CONFIG_DEFAULTS
from Wesen.sourceloader import SourceError
from Wesen.world import World

# a source is imported under its own name and Python remembers modules
# for the life of the process, so every test invents a fresh one
_names = count()

MINIMAL = '''
from Wesen.defaultwesensource import DefaultWesenSource


class WesenSource(DefaultWesenSource):
    """the smallest source that does something"""

    remembered = {}

    def main(self):
        self.remembered[self.age()] = self.energy()
        self.look()
'''


class SourceTestCase(unittest.TestCase):
    """a temporary folder of player-written sources"""

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(sourceloader.setSearchPath, [])
        self.addCleanup(isolation.forget)
        sourceloader.setSearchPath([self.folder])

    def newName(self, prefix="Testling"):
        return f"{prefix}{next(_names)}"

    def writeFile(self, name, body=MINIMAL):
        """a source as a single file: <folder>/<Name>.py"""
        with open(join(self.folder, name + ".py"), "w") as f:
            f.write(body)
        return name

    def writePackage(self, name, body=MINIMAL, **others):
        """a source as a package: <folder>/<Name>/main.py, plus any
        other modules of its own it was given"""
        makedirs(join(self.folder, name), exist_ok=True)
        with open(join(self.folder, name, "main.py"), "w") as f:
            f.write(body)
        for module, text in others.items():
            with open(join(self.folder, name, module + ".py"), "w") as f:
                f.write(text)
        return name

    def play(self, name, turns=3):
        """a small world in which that source is the only player"""
        config = {k: dict(v) for k, v in CONFIG_DEFAULTS.items()}
        config["gui"]["enable"] = False
        config["world"].update({"length": 40, "Debug": lambda _: None})
        config["wesen"].update({"sources": [name], "count": 2})
        config["food"]["count"] = 5
        world = World(config)
        for _ in range(turns):
            world.main()
        return world


class TestWhereASourceMayLive(SourceTestCase):
    def test_a_single_file_source_is_found_and_played(self):
        name = self.writeFile(self.newName())
        cls = sourceloader.loadSource(name)
        self.assertEqual(cls.__name__, "WesenSource")
        world = self.play(name)
        self.assertEqual(world.stats[name]["count"], 2)
        self.assertEqual(world.faults, {})

    def test_a_source_package_may_import_its_own_modules(self):
        """the shape the shipped sources have: a folder with main.py
        and whatever else the player split their code into"""
        name = self.newName()
        self.writePackage(
            name,
            body=MINIMAL.replace(
                "self.look()", "self.look()\n        helper.note(self)"
            ).replace(
                "from Wesen.defaultwesensource",
                "from . import helper\nfrom Wesen.defaultwesensource",
            ),
            helper="def note(source):\n    source.noted = True\n",
        )
        world = self.play(name)
        self.assertEqual(world.faults, {})
        played = [
            o
            for o in world.objects.values()
            if o.objectType == "wesen"
        ]
        self.assertTrue(
            all(o.wesenSource.noted for o in played),
            "the source's own helper module was never reached",
        )

    def test_a_player_source_wins_over_a_shipped_one(self):
        """copying a source out of the game, changing it and keeping
        the name has to give you your version, not the game's"""
        self.writeFile("Dwarf", MINIMAL)
        self.addCleanup(sys.modules.pop, "Dwarf", None)
        cls = sourceloader.loadSource("Dwarf")
        self.assertEqual(cls.__module__, "Dwarf")

    def test_shipped_sources_still_load(self):
        cls = sourceloader.loadSource("DrunkenSailor")
        self.assertEqual(
            cls.__module__, "Wesen.sources.DrunkenSailor.main"
        )

    def test_the_default_folder_is_always_searched(self):
        sourceloader.setSearchPath(["/nowhere/at/all"])
        self.assertIn(
            sourceloader.DEFAULT_SOURCE_DIR, sourceloader.searchPath()
        )

    def test_a_config_line_of_folders_is_split(self):
        sourceloader.setSearchPath(f" {self.folder} , ")
        self.assertEqual(sourceloader.searchPath()[0], self.folder)


class TestSayingWhatIsWrong(SourceTestCase):
    """A player's first source is usually broken, so the message it
    gets is part of the game."""

    def test_an_unknown_source_names_every_place_looked(self):
        with self.assertRaises(SourceError) as caught:
            sourceloader.loadSource(self.newName("Absent"))
        message = str(caught.exception)
        self.assertIn(self.folder, message)
        self.assertIn(sourceloader.DEFAULT_SOURCE_DIR, message)
        self.assertIn("shipped with the game", message)

    def test_a_module_without_a_WesenSource_says_so(self):
        name = self.writeFile(self.newName(), "x = 1\n")
        with self.assertRaises(SourceError) as caught:
            sourceloader.loadSource(name)
        self.assertIn("no class called WesenSource", str(caught.exception))

    def test_a_WesenSource_that_is_not_one_says_so(self):
        name = self.writeFile(
            self.newName(), "class WesenSource:\n    pass\n"
        )
        with self.assertRaises(SourceError) as caught:
            sourceloader.loadSource(name)
        self.assertIn(
            "does not subclass DefaultWesenSource", str(caught.exception)
        )

    def test_code_that_does_not_import_says_which_file(self):
        name = self.writeFile(self.newName(), "import nonexistentmodule\n")
        with self.assertRaises(SourceError) as caught:
            sourceloader.loadSource(name)
        self.assertIn(name + ".py", str(caught.exception))

    def test_a_name_is_a_name_and_not_a_path(self):
        for bad in ("../etc", "a/b", "", "with.dots"):
            with self.assertRaises(SourceError):
                sourceloader.loadSource(bad)


class TestIsolationOfPlayerSources(SourceTestCase):
    """The shared-state rule has to hold for a source wherever it was
    loaded from; it used to work out which source it was looking at
    from the shape of a shipped module's name."""

    def test_a_single_file_source_is_isolated_under_its_own_name(self):
        name = self.writeFile(self.newName())
        self.play(name)
        self.assertEqual(
            isolation.sharing().get(name), ["remembered"]
        )

    def test_wesen_of_a_player_source_do_not_share_a_class_attribute(self):
        name = self.writeFile(self.newName())
        world = self.play(name, turns=4)
        remembered = [
            o.wesenSource.remembered
            for o in world.objects.values()
            if o.objectType == "wesen"
        ]
        self.assertEqual(len(remembered), 2)
        self.assertTrue(all(r for r in remembered))
        self.assertIsNot(remembered[0], remembered[1])


if __name__ == "__main__":
    unittest.main()
