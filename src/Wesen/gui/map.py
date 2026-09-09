"""Contains the Map, a visualization of all object's positions."""

import OpenGL

OpenGL.ERROR_ON_COPY = True
from math import ceil, log

from numpy import array as narray
from numpy import zeros as nzeros
from OpenGL.arrays import vbo
from OpenGL.GL import (
    GL_ARRAY_BUFFER,
    GL_COLOR_ARRAY,
    GL_DYNAMIC_DRAW,
    GL_FLOAT,
    GL_TRIANGLES,
    GL_VERTEX_ARRAY,
    glColor3f,
    glColorPointer,
    glDisableClientState,
    glDrawArrays,
    glEnableClientState,
    glPopMatrix,
    glPushMatrix,
    glRectf,
    glScale,
    glTranslatef,
    glVertexPointer,
)

from .object import GuiObject


class Map(GuiObject):
    """A Map() object plots the descriptor data onto a 2d-grid."""

    TERRAIN_TILES = 24  # resolution the fertility map is drawn at

    def __init__(
        self, gui, infoWorld, sourceList, colorList, fertility=None
    ):
        GuiObject.__init__(self, gui)
        self.worldLength = infoWorld["length"]
        self._terrain = self._BuildTerrain(fertility)
        self.colorDescriptor = {
            wesenSource: color
            for (wesenSource, color) in zip(sourceList, colorList)
        }
        self._indices = {}
        self._data = None
        self._vbo = None  # VBO = vertex buffer object
        self._empty_indices = []
        self._max_index = -1
        self._data_size = -1
        self._dirty_objects = {}

    __num_values = 6 * (2 + 4)
    # 6 points with 2 coordinates and 4 color values

    def __descToArray(self, desc):
        """returns list that contains the vertex and color data for one object"""
        color = (
            self.colorDescriptor[desc["source"]]  # color
            if desc["type"] == "wesen"
            else [0.0, 1.0, 0.0]
        )
        return [
            desc["position"][0],
            desc["position"][1],
            color[0],
            color[1],
            color[2],
            1.0,  # first triangle
            desc["position"][0],
            desc["position"][1] - 1.0,
            color[0],
            color[1],
            color[2],
            1.0,
            desc["position"][0] + 1.0,
            desc["position"][1],
            color[0],
            color[1],
            color[2],
            1.0,
            # second triangle
            desc["position"][0] + 1.0,
            desc["position"][1],
            color[0],
            color[1],
            color[2],
            1.0,
            desc["position"][0],
            desc["position"][1] - 1.0,
            color[0],
            color[1],
            color[2],
            1.0,
            desc["position"][0] + 1.0,
            desc["position"][1] - 1.0,
            color[0],
            color[1],
            color[2],
            1.0,
        ]

    def _BuildData(self, descriptor):
        """Builds data array from scratch and creates VBO object"""
        if len(descriptor) == 0:
            return
        num_objects = len(descriptor)
        values_per_object = len(self.__descToArray(descriptor[0]))
        self._data_size = 2 ** ceil(log(num_objects, 2))
        self._data = nzeros(self._data_size * values_per_object, "f")
        self._indices = {}
        for i, obj in enumerate(descriptor):
            _id = obj["id"]
            values = self.__descToArray(obj)
            for j, v in enumerate(values):
                self._data[i * values_per_object + j] = v
            self._indices[_id] = i
        self._empty_indices = []
        self._max_index = num_objects - 1
        self._vbo = vbo.VBO(
            self._data,
            usage=GL_DYNAMIC_DRAW,
            target=GL_ARRAY_BUFFER,
            size=self._data_size * values_per_object * 4,
        )
        self._dirty_objects = {}

    def _AddObject(self, _id, obj):
        """Adds an object to the VBO"""
        if self._vbo is None:
            return
        index = -1
        if len(self._empty_indices) > 0:
            index = self._empty_indices.pop()
        elif self._max_index < self._data_size - 1:
            self._max_index += 1
            index = self._max_index
        if index > 0:
            values = self.__descToArray(obj)
            num_values = len(values)
            self._vbo[index * num_values : (index + 1) * num_values] = (
                narray(values, "f")
            )
            self._indices[_id] = index
        else:
            self._vbo = None
            # trigger _BuildData for next draw

    def _DelObject(self, _id):
        """Removes an object from the VBO"""
        if self._vbo is None:
            return
        index = self._indices[_id]
        num_values = type(self).__num_values
        del self._indices[_id]
        if not (index == self._max_index):
            self._empty_indices.append(index)
        else:
            self._max_index -= 1
        self._vbo[index * num_values : (index + 1) * num_values] = nzeros(
            num_values, "f"
        )

    def _UpdateObject(self, _id, obj):
        """Updates an object in the VBO"""
        if self._vbo is None:
            return
        index = self._indices.get(_id, -1)
        # have to check since object could have been deleted since marked as
        # dirty
        if index < 0:
            return
        num_values = type(self).__num_values
        self._vbo[index * num_values : (index + 1) * num_values] = narray(
            self.__descToArray(obj), "f"
        )

    def _MarkDirty(self, _id, obj):
        """Marks an object in the VBO for updating"""
        if self._vbo is None:
            return
        self._dirty_objects[_id] = obj

    def _BuildTerrain(self, fertility):
        """the fertility map (see biome.py) as a list of coloured tiles
        in world coordinates. Built once: the terrain never changes."""
        if fertility is None:
            return []
        length = self.worldLength
        tiles = min(type(self).TERRAIN_TILES, length)
        low = float(fertility.min())
        span = float(fertility.max()) - low
        if span <= 0:
            return []
        edges = [round(i * length / tiles) for i in range(tiles + 1)]
        terrain = []
        for i in range(tiles):
            x0, x1 = edges[i], edges[i + 1]
            for j in range(tiles):
                y0, y1 = edges[j], edges[j + 1]
                value = (
                    float(fertility[x0:x1, y0:y1].mean()) - low
                ) / span
                # dark green ground on the near-black background, kept
                # far below the brightness of the food drawn on top
                terrain.append(
                    (
                        x0,
                        y0 - 1,
                        x1,
                        y1 - 1,
                        0.02 + 0.03 * value,
                        0.05 + 0.13 * value,
                        0.02 + 0.03 * value,
                    )
                )
        return terrain

    def _DrawTerrain(self, frame, scaleFactor):
        """draws the fertility map underneath the objects"""
        if not self._terrain:
            return
        glPushMatrix()
        glTranslatef(frame, 2 * frame, 0.0)
        glScale(scaleFactor, scaleFactor, 1.0)
        for x0, y0, x1, y1, red, green, blue in self._terrain:
            glColor3f(red, green, blue)
            glRectf(x0, y0, x1, y1)
        glPopMatrix()

    def Draw(self, descriptor=[]):
        """Draws a map with all objects in the world,
        according to the descriptor."""
        GuiObject.Draw(self)
        # TODO get rid of any frame mechanism parts here
        frame = self._getFrameData()["frame"]
        glTranslatef(frame, 2 * frame, 0.0)
        # moving away from the frame
        blockSize = (1 - 2 * frame) / self.worldLength
        scaleFactor = blockSize
        self._DrawTerrain(frame, scaleFactor)
        # data = narray(reduce(lambda a,b: a + b,
        # 		     map(self.__descToArray,
        # 			 descriptor)),
        # 	      "f");
        if len(descriptor) > 0:
            # valuesPerObject = len(self.__descToArray(descriptor[0]))
            if self._vbo is None:
                self._BuildData(descriptor)
            for _id, obj in self._dirty_objects.items():
                self._UpdateObject(_id, obj)
            self._dirty_objects = {}
            glTranslatef(frame, 2 * frame, 0.0)
            # moving away from the frame
            glScale(scaleFactor, scaleFactor, 1.0)
            self._vbo.bind()
            self._vbo.copy_data()
            try:
                glEnableClientState(GL_VERTEX_ARRAY)
                glEnableClientState(GL_COLOR_ARRAY)
                # 2 coordinates with 4 color values with 4 bytes each in
                # between
                glVertexPointer(2, GL_FLOAT, 24, self._vbo)
                # 4 color values with 2 coordinates with 4 bytes each in
                # between
                glColorPointer(4, GL_FLOAT, 24, self._vbo + 8)
                glDrawArrays(
                    GL_TRIANGLES, 0, 3 * 2 * (self._max_index + 1)
                )
            finally:
                self._vbo.unbind()
                glDisableClientState(GL_VERTEX_ARRAY)
                glDisableClientState(GL_COLOR_ARRAY)

    def GetCallbacks(self):
        """returns the callbacks used in the world
        to inform the Map GuiObject about changes"""
        return {
            "UpdatePos": self._MarkDirty,
            "DeleteObject": self._DelObject,
            "AddObject": self._AddObject,
        }
