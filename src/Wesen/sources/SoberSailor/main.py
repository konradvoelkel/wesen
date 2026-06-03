"""
the sober sailor is a smarter implementation of drunken sailor.
it searches food instead of only walking randomly.
"""

from ...defaultwesensource import DefaultWesenSource
from random import choice

class WesenSource(DefaultWesenSource):

    def __init__(self, infoAllSource):
        DefaultWesenSource.__init__(self, infoAllSource)
        self.randRange = [-1, 0, 1]
        self.minimalTime = 20

    def __str__(self):
        return "<Sober Sailor>"

    def sign(self, x):
        if x < 0:
            return -1
        if x > 0:
            return 1
        return 0

    def main(self):
        while self.time() > self.minimalTime:
            lookRange = self.closerLook()

            foodHere = [
                obj for obj in lookRange
                if obj["type"] == "food" and obj["position"] == self.position
            ]

            if foodHere:
                self.Eat(foodHere[0]["id"])
                continue

            foods = [
                obj for obj in lookRange
                if obj["type"] == "food"
            ]

            if foods:
                # Nimm das erste Food, was auf dem Weg ist
                food = foods[0]
                dx = food["position"][0] - self.position[0]
                dy = food["position"][1] - self.position[1]

                # Immer geradeaus laufen
                if abs(dx) > abs(dy):
                    move = [self.sign(dx), 0]
                elif abs(dy) > abs(dx):
                    move = [0, self.sign(dy)]
                else:
                    move = [self.sign(dx), self.sign(dy)]

                self.Move(move)

            else:
                # Wenn kein Food hier ist, bewegt er sich wie DrunkenSailor
                if choice([True, False]):
                    self.Move([choice(self.randRange), 0])
                else:
                    self.Move([0, choice(self.randRange)])