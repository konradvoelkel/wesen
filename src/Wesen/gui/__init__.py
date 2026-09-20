"""This graphical user interface is the default one for tournaments.
It can be subclassed by AI developers to display more information
about a specific source.

More documentation can be found by running wesen with enabled gui.

This module also answers, before a game is built, whether there can be
a window at all. Every way that question gets answered by default is a
bad one: with no display freeglut calls exit() from C with a single
line of its own, and a missing freeglut is not even an ImportError,
because PyOpenGL imports happily and binds the GLUT names to
placeholders that raise only once the window is being made. Somebody
who has just cloned the project is then left without the one thing
worth saying, which is that the game plays perfectly well without a
window."""

import sys
from os import environ

# Where the GUI's one non-python dependency comes from. Also declared
# in pyproject.toml under [tool.wesen.system-dependencies], for anyone
# who wants to read it off the project rather than off an error.
FREEGLUT_PACKAGES = (
    "apt install freeglut3-dev",
    "pacman -S freeglut",
    "brew install freeglut",
)

WITHOUT_A_WINDOW = """\
The game also runs without a window:

    wesen --disablegui                 # the same game, stats on stdout
    wesen-tournament -s Dwarf,Rincewind    # headless and scored

Set [gui] enable = False in the config file to make that the default.\
"""


def guiProblem():
    """Says why no window can be opened here, or None if one can."""
    display = displayProblem()
    if display is not None:
        return display
    try:
        from OpenGL.GLUT import glutInit
    except ImportError as error:
        return _libraryProblem(error)
    if not bool(glutInit):
        return _freeglutProblem("glutInit is undefined")
    return None


def exitIfGuiUnavailable():
    """Stops with that explanation rather than letting freeglut stop
    with its own. Called from loader.py before a world is built, so
    that the answer arrives before a screenful of setup, and again from
    wesend.py, which is the actual gate and is also reached by code
    that never went through the loader."""
    problem = guiProblem()
    if problem is not None:
        print(problem, file=sys.stderr)
        sys.exit(1)


def displayProblem():
    """Whether there is a graphical session to draw into.

    Only the case we can be sure about is reported: macOS and Windows
    do not use DISPLAY, so its absence says nothing there, and an X or
    Wayland session that is set up at all sets one of these."""
    if sys.platform in ("darwin", "win32"):
        return None
    if environ.get("DISPLAY") or environ.get("WAYLAND_DISPLAY"):
        return None
    return (
        "wesen: cannot open a window - neither DISPLAY nor "
        "WAYLAND_DISPLAY is set, so there is no graphical session to "
        "draw into.\n\n" + WITHOUT_A_WINDOW
    )


def _libraryProblem(error):
    """PyOpenGL missing and freeglut missing both read as "no OpenGL",
    and they want opposite remedies: one is a python package that `uv
    sync` installs, the other a system library only the system's own
    package manager has. Sending somebody who has not run `uv sync`
    yet off to apt-install freeglut is sending them the wrong way
    entirely, so the name Python could not find decides which this
    is."""
    if getattr(error, "name", "") in ("OpenGL", "PyOpenGL"):
        return (
            f"wesen: the GUI could not start ({error}).\n\n"
            "PyOpenGL is not installed. The project's dependencies go "
            "in with:\n\n    uv sync\n\n" + WITHOUT_A_WINDOW
        )
    return _freeglutProblem(error)


def _freeglutProblem(error):
    """The message for a GUI whose one non-python dependency is not
    there."""
    return (
        f"wesen: the GUI could not start ({error}).\n\n"
        "It needs freeglut, the one dependency that is not a python "
        "package:\n\n    "
        + "\n    ".join(FREEGLUT_PACKAGES)
        + "\n\n"
        + WITHOUT_A_WINDOW
    )
