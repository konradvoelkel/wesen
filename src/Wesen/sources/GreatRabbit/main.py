from numpy.random import randint

from ...defaultwesensource import DefaultWesenSource


class WesenSource(DefaultWesenSource):
    def __init__(self, infoAllSource):
        DefaultWesenSource.__init__(self, infoAllSource)
        self.infoAllSource = infoAllSource

    def __str__(self):
        return "<Great Rabbit, the Insatiable>"

    def main(self):
        # devour everything in sight - but ripe food first, so the
        # pasture keeps growing (bites when hungry, anything when starving)
        visible = self.closerLook()
        foods = [o for o in visible if o["type"] == "food"]
        wanted = [f for f in foods if self.foodWanted(f)]

        if wanted:
            nearest = min(
                wanted,
                key=lambda f: max(
                    abs(f["position"][0] - self.position()[0]),
                    abs(f["position"][1] - self.position()[1]),
                ),
            )
            if self.MoveToPosition(nearest["position"]):
                self.Eat(nearest["id"])
        else:
            self.Move([randint(-2, 3), randint(-2, 3)])

        # multiply while the pasture is rich
        ripe = sum(1 for f in foods if self.foodRipe(f))
        if self.energy() > 150 and ripe >= 3:
            self.Reproduce()
