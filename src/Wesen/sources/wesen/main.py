from ...defaultwesensource import DefaultWesenSource
from ...point import getShortestTranslation


class WesenSource(DefaultWesenSource):

    def __init__(self, infoAllSource):
        """Do all initialization stuff."""
        DefaultWesenSource.__init__(self, infoAllSource)
        self.reproductionEnergy = 400
        self.searchStep = 3

    def __str__(self):
        return "<Simple Wesen>"

    def findNearestFood(self):
        """Find the nearest food in visible range."""
        foods = [o for o in self.closerLook() if o["type"] == "food"]
        if not foods:
            return None
        
        # Find closest food using shortest distance on torus world
        closest = min(foods, key=lambda f: sum(abs(x) for x in getShortestTranslation(
            self.position(), f["position"], self.worldlength)))
        return closest

    def moveTowardsFood(self, food):
        """Move towards the food position."""
        translation = getShortestTranslation(
            self.position(), food["position"], self.worldlength)
        
        # Normalize movement to max step size
        move = [0, 0]
        for i in range(2):
            if translation[i] > 0:
                move[i] = min(translation[i], self.searchStep)
            elif translation[i] < 0:
                move[i] = max(translation[i], -self.searchStep)
        
        self.Move(move)

    def main(self):
        while(self.time() > self.infoTime["move"]):
            # Try to reproduce if we have enough energy
            if self.energy() >= self.reproductionEnergy:
                self.Reproduce()
            
            # Look for food at current position and eat it
            edible = [o for o in self.closerLook() if o["type"] == "food" and 
                     o["position"] == self.position()]
            if edible:
                self.Eat(edible[0]["id"])
            
            # Find and move towards nearest food
            nearest_food = self.findNearestFood()
            if nearest_food:
                self.moveTowardsFood(nearest_food)
            else:
                # If no food visible, move in search pattern
                self.Move([self.searchStep, 0])
