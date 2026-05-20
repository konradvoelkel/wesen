from numpy.random import randint
from ...defaultwesensource import DefaultWesenSource


class WesenSource(DefaultWesenSource):

    def __init__(self, infoAllSource):
        DefaultWesenSource.__init__(self, infoAllSource)
        self.infoAllSource = infoAllSource

    def __str__(self):
        return "<Great Rabbit, the Insatiable>"

    def main(self):
        # devour everything in sight
        visible = self.look()
        foods = [o for o in visible if o["type"] == "food"]

        if foods:
            nearest = min(foods, key=lambda f:
                max(abs(f["position"][0] - self.position()[0]),
                    abs(f["position"][1] - self.position()[1])))
            if self.MoveToPosition(nearest["position"]):
                self.Eat(nearest["id"])
        else:
            self.Move([randint(-2, 3), randint(-2, 3)])

        # multiply endlessly
        if self.energy() > 150:
            self.Reproduce()
