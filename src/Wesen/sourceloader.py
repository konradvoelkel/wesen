"""Finding the program a player wrote.

A wesen source is a player's own code, and until now the only place the
game ever looked for it was inside its own installation: `objects/wesen`
imported `..sources.<Name>.main` relative to the package, so writing a
wesen meant editing the game. `loader.py` created `~/.wesen/sources` and
put it on the import path, which looks like the opposite and was used by
nothing.

This module is the one place a source is looked up, for the engine and
for the launcher alike. A source may be

* ``<dir>/<Name>/main.py`` - a package, the shape the sources shipped
  with the game have, for code split over several files; or
* ``<dir>/<Name>.py`` - a single file, which is what a first wesen is,

in any of the search directories - ``~/.wesen/sources`` by default, plus
whatever ``[wesen] sourcepath`` names - and otherwise among the sources
shipped in ``Wesen.sources``. A player's own directories are searched
first, so a shipped source can be copied out, renamed and changed
without touching the installation.

What is found in a search directory is imported as an ordinary top-level
module, with its directory on ``sys.path``, so ``import`` inside it means
what it means everywhere else and a source package can import its own
helper modules. It reaches the game through the installed package::

    from Wesen.defaultwesensource import DefaultWesenSource
"""

import importlib
import sys
from os.path import expanduser, isfile, join

from .defaultwesensource import DefaultWesenSource

DEFAULT_SOURCE_DIR = join(expanduser("~"), ".wesen", "sources")

# where the sources shipped with the game live
BUNDLED_PACKAGE = __package__ + ".sources"


class SourceError(Exception):
    """a source could not be loaded: it is nowhere to be found, it does
    not import, or what it defines is not a wesen source. Raised with
    the message the player is meant to read."""


_searchPath: list[str] = [DEFAULT_SOURCE_DIR]
_cache: dict[str, type] = {}


def searchPath():
    """the directories a player's own sources are looked for in, in
    order. The sources shipped with the game are the fallback and are
    not a directory: they are found inside the installed package."""
    return list(_searchPath)


def setSearchPath(directories):
    """replaces the search path. Takes a list, or the comma-separated
    string a config file holds. The default directory is always kept,
    last, so a config file can add places to look and not lose one."""
    if isinstance(directories, str):
        directories = directories.split(",")
    path = []
    for directory in list(directories) + [DEFAULT_SOURCE_DIR]:
        directory = expanduser(str(directory).strip())
        if directory and directory not in path:
            path.append(directory)
    _searchPath[:] = path
    forget()


def forget():
    """drop the cache (a source has been edited, or the search path has
    changed). Note that Python itself caches imported modules, so this
    finds a source that has moved, not one that has been rewritten."""
    _cache.clear()


def sourceFile(name, directory):
    """where a source of this name would be in a directory: the package
    ``<Name>/main.py`` that the shipped sources use, or the single file
    ``<Name>.py`` that a first wesen usually is. None if it is neither,
    which is the normal answer for most directories."""
    package = join(directory, name, "main.py")
    if isfile(package):
        return package
    module = join(directory, name + ".py")
    if isfile(module):
        return module
    return None


def findSource(name):
    """(directory, file) where this source is, or None if it is only
    among the ones shipped with the game (or nowhere at all)."""
    for directory in _searchPath:
        path = sourceFile(name, directory)
        if path is not None:
            return directory, path
    return None


def loadSource(name):
    """the WesenSource class that a source of this name defines.

    Answered from a cache after the first call, which is what the note
    in `objects/wesen.py` about importing a source once per wesen was
    asking for."""
    cls = _cache.get(name)
    if cls is None:
        cls = _cache[name] = _importSource(name)
    return cls


def describe(name):
    """where a source of this name was looked for, for an error
    message: every search directory, and then the game's own."""
    places = [
        f"  {join(directory, name)}/main.py or {join(directory, name)}.py"
        for directory in _searchPath
    ]
    places.append(f"  the sources shipped with the game ({name})")
    return "\n".join(places)


def _importSource(name):
    """imports a source and returns its WesenSource class, looking in
    the player's own directories before the game's own."""
    _checkName(name)
    found = findSource(name)
    if found is not None:
        directory, path = found
        if directory not in sys.path:
            # appended rather than prepended: a source directory is the
            # player's and may hold anything, and it must not be able
            # to shadow the standard library for the whole game
            sys.path.append(directory)
        single = path == join(directory, name + ".py")
        moduleName = name if single else name + ".main"
        module = _import(moduleName, name, directory, path)
        return _classOf(module, name, path)
    try:
        module = importlib.import_module(
            "." + name + ".main", BUNDLED_PACKAGE
        )
    except ImportError as exc:
        raise SourceError(
            f"no wesen source called '{name}'. Looked in:\n"
            f"{describe(name)}\n"
            f"({exc})"
        ) from exc
    return _classOf(module, name, getattr(module, "__file__", name))


def _import(moduleName, name, directory, path):
    """imports a source found in a search directory, and says something
    useful when Python cannot see it under that name."""
    try:
        return importlib.import_module(moduleName)
    except ImportError as exc:
        raise SourceError(
            f"the wesen source '{name}' ({path}) could not be "
            f"imported: {exc}{_shadowHint(name, directory)}"
        ) from exc


def _shadowHint(name, directory):
    """A source is imported under its own name, so a source called
    `json` or `numpy` is asking Python for something it already has.
    Worth saying, because the ImportError on its own points at the
    wrong file entirely."""
    other = sys.modules.get(name)
    if other is None:
        return ""
    where = getattr(other, "__file__", None) or "built into Python"
    if where.startswith(directory):
        return ""
    return (
        f"\nSomething else in this Python is already called '{name}' "
        f"({where}), so the game cannot import yours under that name. "
        f"Rename your source."
    )


def _classOf(module, name, where):
    """the WesenSource class of an imported source module, checked, so
    that a source that is not one fails here and says why, rather than
    somewhere in the middle of a game."""
    cls = getattr(module, "WesenSource", None)
    if cls is None:
        raise SourceError(
            f"the wesen source '{name}' ({where}) defines no class "
            f"called WesenSource. A source is a module holding a class "
            f"of exactly that name; see the template in "
            f"Wesen/sources/example.py."
        )
    if not (isinstance(cls, type) and issubclass(cls, DefaultWesenSource)):
        raise SourceError(
            f"the WesenSource in '{name}' ({where}) does not subclass "
            f"DefaultWesenSource. Write 'from Wesen.defaultwesensource "
            f"import DefaultWesenSource' and subclass it: that is how a "
            f"source is handed the rules of this particular game, and "
            f"where the helpers live."
        )
    return cls


def _checkName(name):
    """a source name is a name, not a path: it ends up in an import and
    in a directory name, and both of those would take a '..' or a '/'
    rather more literally than the player meant it."""
    if not name or not all(c.isalnum() or c == "_" for c in name):
        raise SourceError(
            f"'{name}' is not a usable name for a wesen source: use "
            f"letters, digits and underscores. A name is the directory "
            f"or file the source lives in, not a path to it."
        )
