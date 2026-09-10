from numpy.random import randint

from ...defaultwesensource import DefaultWesenSource
from . import helper


class WesenSource(DefaultWesenSource):
    def __init__(self, infoAllSource):
        """Do all initialization stuff."""
        DefaultWesenSource.__init__(self, infoAllSource)
        self.infoAllSource = infoAllSource
        # The whole colony sweeps the world along one vector. It used to
        # be drawn in the class body, which is to say while this module
        # was being imported - before the game was seeded, so the same
        # seed played a different game every time. Drawn from the game
        # seed instead: every Dwarf works it out for itself and they all
        # get the same answer, without a word between them.
        self.globalScanVector = tuple(
            self.gameRandom("scan").uniform(-1, 1) for _ in range(2)
        )
        self.minimalTime = 20
        # TODO should be something to prevent infinite loops!!
        self.minimumEnergyToEat = 2
        self.minimalGardenAge = 50
        self.minimumEnergyToReproduce = 1500
        self.minimumEnergyToFight = 300
        self.target = None
        self.targetType = None
        self.forbiddenTargets = []

    def __str__(self):
        return "<Dwarf Fighter, coming out of the Broken Drum>"

    def main(self):
        # save age death and reproduce
        if self.energy() > self.minimumEnergyToReproduce:
            if self.Reproduce():
                for _ in range(10):
                    helper.ScannerMove(
                        self,
                        scanVector=[
                            self.globalScanVector[1],
                            -self.globalScanVector[0],
                        ],
                    )
        helper.recoverAge(self)
        # action loop
        while self.time() > self.minimalTime:
            timeBefore = self.time()
            # Look around again every time round: our own eating and
            # fighting invalidates ids from an earlier look, and acting
            # on those is a rule violation ("non-existing food").
            lookRange = self.closerLook()
            # try to finish something that already started:
            if self.targetType == "food":
                helper.lookForFoodTarget(self, lookRange)
            elif self.targetType == "wesen":
                helper.lookForEnemyTarget(self, lookRange)
            # TODO the 4 lines above this comment are wrong.
            helper.HandleTarget(self)
            # nothing to do? OK, find something to do.
            if not self.target:
                foundFood = helper.lookForFoodTarget(self, lookRange)
                if foundFood:
                    # fine, this will be handled next loop iteration!
                    pass
                else:
                    foundEnemy = False
                    if self.energy() > self.minimumEnergyToFight:
                        foundEnemy = helper.lookForEnemyTarget(
                            self, lookRange
                        )
                        # if found, this will be handled next loop iteration!
                    if not foundEnemy:
                        # nothing to eat, no fights. OK. Time for gardening.
                        if helper.lookAtYoungGarden(self, lookRange):
                            # well, wait for the garden to grow!
                            self.target = None
                            # TODO find out whether necessary
                            break
                        else:
                            decision = randint(0, 9)
                            # TODO move magic number to constants above
                            if decision == 0:
                                # seed out!
                                helper.seedOut(self)
                            elif decision <= 4:
                                # move away!
                                helper.ScannerMove(
                                    self,
                                    scanVector=self.globalScanVector,
                                )
                            else:
                                # move back!
                                helper.ScannerMove(
                                    self,
                                    scanVector=[
                                        -c
                                        for c in self.globalScanVector
                                    ],
                                )
            if self.time() == timeBefore:
                # nothing above cost any time (e.g. a scan vector that
                # rounds to no move): a second pass would loop forever
                break
