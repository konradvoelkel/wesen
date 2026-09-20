"""the drunken sailor: random movement, done the way a drunk actually
finds the next pub.

The old sailor drew a uniform step every turn and only then looked for
food under its feet, so it stepped off whatever it had just found and
spent every bit of time it had on walking. On the life rule's pasture -
sparse, patchy, regrowing - it starved in two hundred turns on an empty
map. Randomness is what a sailor is; it just has to be the right kind.

* **Lévy flight.** A step is either a *stagger* - to the nearest bite in
  view, a cell or two - or a *lurch*: a long straight run into ground it
  has not seen, whose length comes from a heavy-tailed (Pareto)
  distribution. Mostly short, now and then very long, is the provably
  best way to search for targets that are sparse and come back, and
  the stagger spreads the bites over many cells, which is what the
  herding colonies do with a map and a lot of code.
* **Never a step without a reason.** Inside a patch it only walks to a
  bite; it lurches only when nothing in sight is worth eating. Time
  carries over between turns, so a sailor that stood still can lurch
  further next turn.
* **Shanties.** A sailor that has just eaten on a rich patch sings
  (`Broadcast`, 1 time), and a colleague within earshot that would
  otherwise lurch at random lurches toward the song instead. No leader,
  no map, no shared state: a flock by rumour. Enemies hear it too -
  everybody in the harbour knows where the pub is.
"""

from random import choice, paretovariate, random

from ...defaultwesensource import DefaultWesenSource
from ...point import getDistInMaxMetric, getShortestTranslation

SHANTY = "shanty/1"  # our songs, and nobody else's
HEADINGS = [
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, 1),
    (1, -1),
    (-1, 1),
    (-1, -1),
]


class WesenSource(DefaultWesenSource):
    LURCH_MIN = 6  # cells: the shortest lurch
    LURCH_MAX = 60  # cells: the longest (a Pareto tail is unbounded)
    LURCH_ALPHA = 1.5  # Pareto shape: step lengths ~ l^-(1+alpha)
    SONG_TTL = 30  # turns a shanty is worth following
    SONG_MIN = 3  # ripe cells in view that make a patch worth a song
    SONGS_KEPT = 16
    BREED_RIPE = 3  # ripe cells in view before splitting
    FLEE = 12  # cells to lurch away from a bully

    def __init__(self, infoAllSource):
        """Do all initialization stuff."""
        DefaultWesenSource.__init__(self, infoAllSource)
        self.turn = 0
        self.heading = None  # (dx, dy) of the current lurch, or None
        self.left = 0  # cells still to go on it
        self.target = None  # a pub to lurch to instead of a heading
        self.songs = {}  # (x, y) -> [pints, turn heard]

    def __str__(self):
        return "<Sailor, hasn't been on any boat yet>"

    def persist(self):
        return {
            "turn": self.turn,
            "heading": self.heading,
            "left": self.left,
            "target": self.target,
            "songs": [
                [x, y, p, t] for (x, y), (p, t) in self.songs.items()
            ],
        }

    def restore(self, obj):
        me = obj.get("wesensource") or {}
        self.turn = me.get("turn", 0)
        heading = me.get("heading")
        self.heading = tuple(heading) if heading else None
        self.left = me.get("left", 0)
        target = me.get("target")
        self.target = tuple(target) if target else None
        self.songs = {(x, y): [p, t] for x, y, p, t in me.get("songs", [])}

    # --- the shanty ------------------------------------------------------

    def Receive(self, message):
        if not self.fromColleague(message):
            return
        if not isinstance(message, dict) or message.get("s") != SHANTY:
            return
        pub, pints = message.get("pub"), message.get("pints")
        if (
            not isinstance(pub, (tuple, list))
            or len(pub) != 2
            or not all(isinstance(c, int) for c in pub)
            or not isinstance(pints, int)
        ):
            return
        self.songs[(pub[0], pub[1])] = [pints, self.turn]
        if len(self.songs) > self.SONGS_KEPT:
            oldest = min(self.songs, key=lambda k: self.songs[k][1])
            del self.songs[oldest]

    def freshSongs(self, pos):
        """the songs still worth following, minus the one about my own cell"""
        for key in [
            k
            for k, v in self.songs.items()
            if self.turn - v[1] > self.SONG_TTL
        ]:
            del self.songs[key]
        return {k: v for k, v in self.songs.items() if k != tuple(pos)}

    # --- moving ----------------------------------------------------------

    def dist(self, a, b):
        return getDistInMaxMetric(a, b, self.worldlength)

    def stepToward(self, target):
        """walk toward a cell as far as this turn's time allows.
        True on arrival."""
        move = self.infoTime["move"]
        while True:
            v = getShortestTranslation(
                self.position(), target, self.worldlength
            )
            d = max(abs(v[0]), abs(v[1]))
            if d == 0:
                return True
            sx = (v[0] > 0) - (v[0] < 0)
            sy = (v[1] > 0) - (v[1] < 0)
            n = min(d, self.time() // (move * (abs(sx) + abs(sy))))
            if n <= 0:
                return False
            dx, dy = sx * min(n, abs(v[0])), sy * min(n, abs(v[1]))
            if not self.Move([dx, dy]):
                return False

    def newLurch(self, pos):
        """pick where the next lurch goes: toward a song if one is
        fresh, else a heading and a heavy-tailed length"""
        songs = self.freshSongs(pos)
        if songs and random() < 0.8:
            best = max(
                songs,
                key=lambda k: songs[k][0] / (1.0 + self.dist(pos, k)),
            )
            self.target, self.heading, self.left = best, None, 0
            return
        self.target = None
        self.heading = choice(HEADINGS)
        self.left = min(
            self.LURCH_MAX,
            int(self.LURCH_MIN * paretovariate(self.LURCH_ALPHA)),
        )

    def lurch(self, pos):
        """one turn's worth of the current lurch"""
        if self.target is not None:
            if self.stepToward(self.target):
                # arrived: whatever was sung about is in view now
                self.songs.pop(self.target, None)
                self.target = None
            return
        if self.left <= 0 or self.heading is None:
            self.newLurch(pos)
            if self.target is not None:
                self.lurch(pos)
                return
        dx, dy = self.heading
        move = self.infoTime["move"]
        n = min(self.left, self.time() // (move * (abs(dx) + abs(dy))))
        if n > 0 and self.Move([dx * n, dy * n]):
            self.left -= n

    def fleeFrom(self, pos, bully):
        v = getShortestTranslation(
            pos, bully["position"], self.worldlength
        )
        away = (-((v[0] > 0) - (v[0] < 0)), -((v[1] > 0) - (v[1] < 0)))
        if away == (0, 0):
            away = choice(HEADINGS)
        self.target, self.heading, self.left = None, away, self.FLEE
        self.lurch(pos)

    # --- eating ----------------------------------------------------------

    def eatHere(self, foods, pos):
        """bite what is under my feet while it is worth biting.
        Returns the energy eaten."""
        eaten = 0
        eat = self.infoTime["eat"]
        for food in foods:
            if list(food["position"]) != pos:
                continue
            food = dict(food)
            while self.time() >= eat and self.foodWanted(food):
                bite = self.foodYield(food)
                if not self.Eat(food["id"]):
                    break
                eaten += bite
                food["energy"] -= bite
                if food["energy"] <= 0:
                    break
        return eaten

    def main(self):
        self.turn += 1
        pos = list(self.position())
        seen = self.closerLook()
        foods = [o for o in seen if o["type"] == "food"]
        strangers = [
            o
            for o in seen
            if o["type"] == "wesen" and o["source"] != self.source
        ]
        damage = self.attackDamage()

        # a bully that could kill me, on my cell or next to it: stagger off
        bullies = [
            o
            for o in strangers
            if self.dist(pos, o["position"]) <= 2
            and o["energy"] * damage >= self.energy()
        ]
        if bullies:
            self.fleeFrom(pos, max(bullies, key=lambda o: o["energy"]))
            return

        eaten = self.eatHere(foods, pos)
        ripe = [f for f in foods if self.foodRipe(f)]

        # a rich patch is worth a song, and worth another sailor
        if eaten and len(ripe) >= self.SONG_MIN:
            self.Broadcast(
                {"s": SHANTY, "pub": (pos[0], pos[1]), "pints": len(ripe)}
            )
        if (
            eaten
            and len(ripe) >= self.BREED_RIPE
            and self.energy() >= max(300, 2 * self.minBirthEnergy())
            and (not self.lean() or self.energy() >= 800)
        ):
            self.Reproduce()

        # the stagger: the nearest bite in view, never onto a cell where
        # a stranger stands (some of them kill a thief on their own cell)
        taken = {tuple(o["position"]) for o in strangers}
        wanted = [
            f
            for f in foods
            if list(f["position"]) != pos
            and tuple(f["position"]) not in taken
            and self.foodWanted(f)
        ]
        if wanted:
            self.target, self.heading, self.left = None, None, 0
            nearest = min(
                wanted, key=lambda f: self.dist(pos, f["position"])
            )
            if self.stepToward(list(nearest["position"])):
                self.eatHere([nearest], list(self.position()))
            return

        # nothing in sight worth a step: the lurch
        self.lurch(pos)
