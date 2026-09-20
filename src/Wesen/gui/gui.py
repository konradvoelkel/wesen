"""This GUI is an example how visualization may help
in developing AI code and watch tournaments.

For implementation details, see basicgui.py,
as this code only adds features on top:
* movie capture
* world manipulation
"""

import traceback
from os.path import abspath

from OpenGL.GL import GL_RGB, GL_UNSIGNED_BYTE, glReadPixels
from OpenGL.GLU import GLubyte
from OpenGL.GLUT import (
    GLUT_RIGHT_BUTTON,
    glutAddMenuEntry,
    glutAttachMenu,
    glutCreateMenu,
)
from PIL import Image

from .basicgui import BasicGUI

cl_freak = [
    [0.4, 0.2, 0.6],
    [0.6, 0.2, 0.4],
    [0.8, 0.2, 0.2],
    [0.2, 0.2, 0.8],
    [0.7, 0.3, 0.1],
    [0.1, 0.3, 0.7],
]

colorList = cl_freak


class GUI(BasicGUI):
    """The GUI class is the usual class to use as GUI in Wesen.
    If you want to use Wesen to do something else than AI tournaments,
    you may be better off subclassing BasicGUI."""

    def __init__(self, infoGUI, GameLoop, world, extraArgs):
        """infoGUI should be a dict,
        GameLoop a method,
        world a World object and
        extraArgs is a string which is passed to OpenGL"""
        self.movieMode = False
        # the following starts glutMainLoop:
        BasicGUI.__init__(
            self, infoGUI, GameLoop, world, extraArgs, colorList=cl_freak
        )

    def ModifyFood(self, action):
        """action can be "delete" "add" "increase" "decrease" """
        if action == "delete":  # FIXME broken?
            for o in self.world.objects.values():
                if o.objectType == "food":
                    if self.world.DeleteObject(id(o)):
                        break
        if action == "add":  # FIXME broken?
            infoFood = self.infoFood
            infoFood["type"] = "food"
            if "position" in infoFood:
                del infoFood["position"]
            self.world.AddObject(infoFood)
        if action == "increase":
            for o in self.world.objects.values():
                if o.objectType == "food":
                    o.energy += 10
        if action == "decrease":
            for o in self.world.objects.values():
                if o.objectType == "food":
                    o.energy -= 10

    def initMenu(self):
        """sets up the popup-menu for right mouse button"""
        self.menu = glutCreateMenu(self.HandleAction)
        glutAddMenuEntry(b"display key bindings", 55)
        glutAddMenuEntry(b"pause   (space)", 100)
        glutAttachMenu(GLUT_RIGHT_BUTTON)

    def HandleAction(self, action):
        """handles actions from the popup-menu"""
        try:
            if action == 55:
                self.ShowKeys()
            elif action == 100:
                self.Pause()
            else:
                print("wesen: unknown popup-menu action", action)
        except Exception:
            print("wesen: popup-menu action failed:")
            print(traceback.format_exc())
        return 0

    def initKeyBindings(self):
        """sets up all key bindings,
        inheriting some from BasicGUI"""
        BasicGUI.initKeyBindings(self)
        self.keybindings.update(
            {
                b"m": self.ToggleMovie,
                b"c": self.SaveScreenshot,
                # now following left,up,right,down keys:
                100: lambda: self.ModifyFood("delete"),
                101: lambda: self.ModifyFood("increase"),
                102: lambda: self.ModifyFood("add"),
                103: lambda: self.ModifyFood("decrease"),
            }
        )
        self._generateKeyExplanations()
        self.keyExplanation = {
            self._getKeyRepresentation(key): str(
                self.keybindings[key].__doc__
            )
            for key in self.keybindings
        }
        self.keyExplanation[self._getKeyRepresentation(100)] = (
            "delete food"
        )
        self.keyExplanation[self._getKeyRepresentation(101)] = (
            "increase food"
        )
        self.keyExplanation[self._getKeyRepresentation(102)] = "add food"
        self.keyExplanation[self._getKeyRepresentation(103)] = (
            "decrease food"
        )

    def ToggleMovie(self):
        """Toggle movie mode on/off. In movie mode, each frame is saved to disk."""
        self.movieMode = not self.movieMode
        print("wesen: movie mode", "on" if self.movieMode else "off")

    def SaveScreenshot(self):
        """Save a screenshot of the map as wesen-<turn>.png"""
        filename = f"wesen-{self.world.turns:08d}.png"
        try:
            self.takeScreenshot().save(filename)
        except Exception:
            print("wesen: could not save", filename)
            print(traceback.format_exc())
            return
        print("wesen: wrote", abspath(filename))

    def HandleMouse(self, button, state, x, y):
        """handles all mouse events as clicks, dragdrops, etc."""
        BasicGUI.HandleMouse(self, button, state, x, y)
        if state == 1:
            # every click also refreshes screenshot.png (the one in the
            # README); press "c" for a numbered shot that is kept.
            # The whole window, not the map: what the README is for is
            # showing somebody who has not run the game what running it
            # looks like, and three quarters of that is outside the map
            # - the energy curves are the game's own account of who is
            # winning, and the map alone is a field of green dots.
            try:
                self.takeWindowShot().save("screenshot.png")
            except Exception:
                print("wesen: could not save screenshot.png")
                print(traceback.format_exc())

    def takeScreenshot(self):
        """takes a screenshot of the map region"""
        width, height = self.windowSize
        image = self.takeWindowShot()
        # take only the Map part of the screenshot:
        image = image.crop((0, 0, width // 2, height // 2))
        # resize to a uniform format (important for movie mode):
        image = image.resize((800, 800), Image.LANCZOS)
        return image

    def takeWindowShot(self):
        """reads the whole window back out of OpenGL as an image"""
        width, height = self.windowSize
        buffer = (GLubyte * (3 * width * height))(0)
        glReadPixels(0, 0, width, height, GL_RGB, GL_UNSIGNED_BYTE, buffer)
        image = Image.frombytes(
            mode="RGB", size=(width, height), data=buffer
        )
        # use image coordinates, not OpenGL coordinates:
        return image.transpose(Image.FLIP_TOP_BOTTOM)

    def RenderScene(self):
        """draws the actual descriptor"""
        BasicGUI.RenderScene(self)
        if self.movieMode:
            try:
                self.takeScreenshot().save(f"m{self.world.turns:08d}.png")
            except Exception:
                print("wesen: movie frame failed, movie mode off:")
                print(traceback.format_exc())
                self.movieMode = False
