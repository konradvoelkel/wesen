"""A colony that talks: the bookkeeping a source needs once it may not
keep a shared brain (see `isolation.py`).

Three of the sources in this game were written when class attributes
were shared, and did their coordinating through them: a registry of who
is alive, a map of the pasture, claims on targets, orders for newborns.
None of that works when every wesen has its own copy - and it should
not, since nothing in the world carried the facts from one wesen to the
other. What they need instead is small and always the same:

* a **clock** the colony agrees on, since a wesen only knows its own age;
* a **roll** of who was heard from, where and how fat, which is what a
  population rule has to be measured against;
* a way to say *what I learned this turn* and to hear the same from
  others, cheaply enough to do every turn (`Broadcast` costs 1 time and
  carries as much as we like).

This class is the general form of that; what the news actually *is*
stays with the source, which knows what it is looking at. A source calls
`tick()` once a turn, `say(...)` to build the message it broadcasts, and
`hear(message)` from its `Receive`, which hands back the news other
wesen sent so it can be written into whatever the source keeps it in.

Everything sent has to be a plain value - numbers, strings, tuples,
lists, dicts of those - because the engine seals a message before it is
delivered (`isolation.sealed`): the receiver gets a frozen copy, never
a handle into the sender.
"""


def _whole(value, default=0):
    """a number that was meant to be one, or None if it was not.

    Booleans are numbers in Python and are not meant here; a string
    that looks like a number is not a number somebody sent us."""
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _cell(value):
    """a pair of whole coordinates, or None"""
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return None
    x, y = _whole(value[0], None), _whole(value[1], None)
    return None if x is None or y is None else (x, y)


def _colleague(entry):
    """one row of the roll a message carries, checked field by field"""
    if not isinstance(entry, (tuple, list)) or len(entry) != 6:
        return None
    uid, x, y, energy, turn, role = entry
    cell = _cell((x, y))
    energy, turn = _whole(energy, None), _whole(turn, None)
    if cell is None or energy is None or turn is None:
        return None
    if not isinstance(uid, (str, int, tuple)):
        return None
    return (
        uid,
        cell[0],
        cell[1],
        energy,
        turn,
        role if isinstance(role, str) else "",
    )


class Colony:
    """one wesen's share of its colony's bookkeeping"""

    # how long a wesen stays on the roll without being heard from
    ROLL_TTL = 200

    def __init__(self, sigil, worldLength, radius=80):
        self.sigil = sigil
        self.length = worldLength
        # the radius the census extrapolates from (see census())
        self.radius = radius
        self.clock = 0
        self.uid = None
        self.roll = {}  # uid -> [pos, energy, turn, role]
        self.heard = 0  # messages merged, for diagnostics

    # --- the calendar ----------------------------------------------------

    def tick(self):
        """one turn older. The colony's clock is the highest anybody has
        counted to: a wesen that skipped a turn (or was just born) falls
        in behind the others as soon as it hears one of them."""
        self.clock += 1
        return self.clock

    def sync(self, clock):
        if clock > self.clock:
            self.clock = clock

    # --- the roll --------------------------------------------------------

    def note(self, uid, pos, energy, turn=None, role=""):
        """somebody was seen or heard"""
        turn = self.clock if turn is None else turn
        old = self.roll.get(uid)
        if old is not None and old[2] > turn:
            return
        self.roll[uid] = [
            (int(pos[0]), int(pos[1])),
            int(energy),
            int(turn),
            role or (old[3] if old else ""),
        ]

    def peers(self, within=None):
        """uid -> record of everybody heard from recently"""
        cutoff = self.clock - (self.ROLL_TTL if within is None else within)
        return {
            uid: rec
            for uid, rec in self.roll.items()
            if rec[2] >= cutoff and uid != self.uid
        }

    def near(self, pos, radius, within=None):
        """the ones whose last known position is within radius"""
        length = self.length
        half = length // 2
        out = {}
        for uid, rec in self.peers(within).items():
            dx = abs(rec[0][0] - pos[0])
            dy = abs(rec[0][1] - pos[1])
            dx = length - dx if dx > half else dx
            dy = length - dy if dy > half else dy
            if dx + dy <= radius:
                out[uid] = rec
        return out

    def census(self, pos):
        """an estimate of the *whole* colony, not the part within
        earshot.

        No wesen ever hears the whole roll: a message travels as far as
        somebody carries it, and a colony spread over the world is not
        spread over one wesen's hearing. But it is spread more or less
        evenly, so the density of colleagues around this one, times the
        world, is a fair estimate - and a population rule that is
        measured against the raw count instead will let the colony grow
        until it eats the world."""
        known = len(self.peers())
        near = len(self.near(pos, self.radius))
        if near < 2:
            # nobody, or almost nobody, within reach: there is nothing
            # to extrapolate from, and pretending otherwise would say
            # "the world is full" to a wesen standing alone in it
            return known + 1
        area = 2.0 * self.radius * self.radius
        spread = int((near + 1) * self.length * self.length / area)
        return max(known + 1, spread)

    # --- talking ---------------------------------------------------------

    def say(self, pos, energy, news=None, role=""):
        """the message to broadcast: who and where I am, my clock, and
        whatever the source wants to pass on. Small on purpose - the
        cost is not the broadcast, it is the merging at the other end."""
        if self.uid is not None:
            self.note(self.uid, pos, energy, self.clock, role)
        roll = sorted(
            (
                (uid, rec[0][0], rec[0][1], rec[1], rec[2], rec[3])
                for uid, rec in self.roll.items()
                if self.clock - rec[2] < self.ROLL_TTL
            ),
            key=lambda e: -e[4],
        )[:10]
        message = {
            "s": self.sigil,
            "u": self.uid,
            "t": self.clock,
            "p": (int(pos[0]), int(pos[1])),
            "e": int(energy),
            "r": role,
            "w": roll,
        }
        if news:
            message["n"] = news
        return message

    def hear(self, message):
        """merge a message from a colleague and hand back its news.

        Returns None for anything that is not one of ours, so a source
        can use it as the whole body of its `Receive`.

        "Not one of ours" has to include a message wearing our own mark
        that is nonsense underneath. `Broadcast` reaches every wesen in
        range whatever its source, a sigil is a constant sitting in a
        file anybody can read, and an id comes free with `closerLook`,
        so a rival can say anything it likes in our name. A colony that
        can be stopped by a malformed word is not much of a colony:
        every field is checked before it is believed, and a message
        that does not hold together is dropped whole rather than
        applied in part."""
        if not isinstance(message, dict) or message.get("s") != self.sigil:
            return None
        uid = message.get("u")
        if uid is not None and uid == self.uid:
            return None
        turn = _whole(message.get("t"))
        if turn is None:
            return None
        self.sync(turn)
        if uid is not None and not self._noteFrom(message, uid, turn):
            return None
        for entry in message.get("w", ()):
            heard = _colleague(entry)
            if heard is None:
                continue
            other, x, y, energy, seen, role = heard
            if other != uid and other != self.uid:
                self.note(other, (x, y), energy, seen, role)
        self.heard += 1
        news = message.get("n")
        return news if isinstance(news, dict) else {}

    def _noteFrom(self, message, uid, turn):
        """what the sender says about itself, if it says it properly"""
        position = _cell(message.get("p"))
        energy = _whole(message.get("e"))
        if position is None or energy is None:
            return False
        role = message.get("r", "")
        self.note(
            uid,
            position,
            energy,
            turn,
            role if isinstance(role, str) else "",
        )
        return True

    def forget(self):
        """drop what is too old to be worth carrying"""
        cutoff = self.clock - self.ROLL_TTL
        for uid in [u for u, r in self.roll.items() if r[2] < cutoff]:
            del self.roll[uid]

    # --- persistence -----------------------------------------------------

    def persist(self):
        return {
            "clock": self.clock,
            "uid": self.uid,
            "roll": {
                str(uid): [list(r[0]), r[1], r[2], r[3]]
                for uid, r in self.roll.items()
            },
        }

    def restore(self, obj, uidType=int):
        if not obj:
            return
        self.clock = obj.get("clock", 0)
        self.uid = obj.get("uid")
        self.roll = {}
        for uid, rec in obj.get("roll", {}).items():
            try:
                key = uidType(uid)
            except (TypeError, ValueError):
                key = uid
            self.roll[key] = [
                (rec[0][0], rec[0][1]),
                rec[1],
                rec[2],
                rec[3] if len(rec) > 3 else "",
            ]
