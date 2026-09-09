"""The arithmetic Rincewind plans with.

Pure functions: no engine calls, no state. Everything here follows from
the rules the engine hands a source (`infoFood`, `infoTime`, the climate
and the biome), so the same code plays a game with different numbers.

The three results worth stating outright, because the whole strategy
rests on them, and all three were measured in play rather than guessed
(the counters are in `main.py`, `local/probe_rw.py` prints them):

*The yield of a cell is fixed, the cost of taking it is not.* Under the
life rule a cell grows by `growrate x 4 e (1-e) x season x fertility`
per turn, at most `growrate` at half its capacity, so a cell can feed
one bite every `bite / (growrate / 2)` turns - about 50 with the
defaults - and no faster, whatever anybody does. A turn buys a fixed
time budget, a bite costs `time.eat` and a step `time.move`, so a bite
costs `eat + move x distance`. Income is decided by *how far apart the
ripe cells are*, which is the one thing a single wesen with a 12-cell
eye cannot see and a colony that talks can.

*Walking is what a bite costs.* With food on some 2 % of the map the
nearest usable cell is four to eight steps away, and a wesen ends about
four turns in five without a bite. Everything follows from that: leave
a cell only what keeps it alive (`harvestFloor`), because the next bite
where you already stand is worth four times the bite you would walk
to; prefer cells that stand in a cluster, because there the next bite
costs one step; and value a report by how fresh it is, because a walk
to a cell somebody has emptied is the most expensive thing there is.

*A cell that is grazed below `birth_maturity` of its capacity stops
seeding.* Food only reproduces above that share (`Food._lifeSeed`) and
every cell dies of old age, so a pasture kept below it ages away - the
classic tragedy of the commons, and how most colonies here eventually
starve. Since the harvest floor cannot save it (a grazed cell rarely
climbs back that far), what keeps the pasture breeding is the seed
stock: `seedStock` marks one cell in N, by position, so a whole colony
protects the same cells without a word being said - and only where it
is alone with them, since a cell kept at capacity is exactly the cell a
rival walks to first.
"""

from math import exp


def wrapDelta(a, b, length):
    """shortest signed step from a to b on one axis of the torus"""
    d = (b - a) % length
    return d - length if d > length // 2 else d


def wrapVector(a, b, length):
    return (
        wrapDelta(a[0], b[0], length),
        wrapDelta(a[1], b[1], length),
    )


def manhattan(a, b, length):
    """steps needed to walk from a to b (what a move actually costs)"""
    return abs(wrapDelta(a[0], b[0], length)) + abs(
        wrapDelta(a[1], b[1], length)
    )


def chebyshev(a, b, length):
    """distance in the metric the engine uses for sight and range"""
    return max(
        abs(wrapDelta(a[0], b[0], length)),
        abs(wrapDelta(a[1], b[1], length)),
    )


def stepVector(pos, target, length, cells):
    """a direction for one `Move` of at most `cells` steps towards
    target. The engine's own MoveToPosition compares coordinates
    without wrapping and happily walks the long way round the world."""
    dx, dy = wrapVector(pos, target, length)
    out = [0, 0]
    left = cells
    # spend the budget on the longer axis first: that is the one a
    # pursuer cannot predict and it keeps the path off the diagonal
    for axis, delta in sorted(
        ((0, dx), (1, dy)), key=lambda p: -abs(p[1])
    ):
        step = max(-left, min(left, delta))
        out[axis] = step
        left -= abs(step)
        if left <= 0:
            break
    return out


def regrow(energy, turns, capacity, rate):
    """what a cell of `energy` holds `turns` later, if nobody touches
    it: logistic growth with intrinsic rate `rate` (see growthRate)."""
    if energy <= 0 or turns <= 0:
        return max(0.0, float(energy))
    if energy >= capacity:
        return float(capacity)
    try:
        k = exp(-rate * turns)
    except OverflowError:  # pragma: no cover
        k = 0.0
    return capacity / (1.0 + ((capacity - energy) / energy) * k)


def growthRate(growrate, capacity, season, fertility, density=0.8):
    """intrinsic rate of the logistic above, from the engine's growth
    formula: growth is `growrate x bell(density) x 4e(1-e)` per turn,
    which is logistic with r = 4 x growrate x bell x season x fert / cap.
    `density` is the bell factor we assume for a cell we cannot see the
    neighbourhood of; 0.8 is a stand for "in a normal pasture"."""
    return (
        4.0
        * max(0.05, growrate)
        * density
        * max(0.1, season)
        * max(0.1, fertility)
        / max(1.0, capacity)
    )


def harvestFloor(energy, starving, bite, roots):
    """how much of a cell we leave standing.

    Travel is what a bite really costs. Cells sit several steps apart,
    so a bite bought with a walk is worth a quarter of what the bite
    after it is worth, taken standing still - which means the marginal
    bite at the cell one is already on nearly always beats the walk to
    the next cell. What stops the harvest is therefore not the point of
    fastest regrowth but the point where the next bite would take the
    whole cell: `getEaten` pulls a cell out of the ground once it holds
    no more than `bite + roots`, so leaving that much plus one keeps it
    alive and regrowing.

    What keeps the *pasture* breeding is not this floor - a grazed cell
    rarely climbs back to `birth_maturity` - but the seed stock: one
    cell in `SEED_STOCK`, picked by its position, is never touched at
    all. In a good season a fed wesen still leaves a little more than
    the minimum, where regrowth is faster; in a bad one it does not,
    because what is left standing in a hard winter is lost anyway."""
    alive = bite + roots + 1
    if energy < starving:
        return 0.0  # kill it: a body now beats a pasture later
    return alive


def seedStock(key, every=4):
    """cells kept out of the harvest, so the pasture keeps seeding.
    A hash of the position: no communication needed for the colony to
    agree, and rivals grazing everything cannot exhaust it as fast."""
    return (key[0] * 3 + key[1] * 5) % every == 0


def bitesAvailable(cellEnergy, capacity, floor, bite, roots, body=False):
    """how many bites this cell offers without going under `floor`.

    A body (a dead wesen's blob, bigger than any cell's capacity) never
    regrows, so it is stripped whole."""
    if cellEnergy <= 0:
        return 0
    if body or floor <= roots:
        # the last bite of a cell takes the whole of it (getEaten)
        return max(1, int(cellEnergy // max(1, bite)))
    room = cellEnergy - floor
    if room < bite:
        return 0
    return int(room // bite)


def cellValue(
    gain, distance, moveTime, eatTime, bites, ripeIn=0, patience=40.0
):
    """energy per unit of time for going there and eating.

    `ripeIn` turns of waiting are charged as if they were time spent:
    a cell that is not ready yet is worth less than one that is, but
    not worthless, since walking there takes turns anyway."""
    cost = moveTime * distance + eatTime * max(1, bites)
    cost += patience * max(0, ripeIn)
    return gain / max(1.0, cost)


def districtRank(cell, home, peerHomes, length):
    """how many colleagues keep a home closer to this cell than we do.

    Zero means the cell is in our own district (a Voronoi cell of the
    colony's homes). The homes drift towards what their keeper actually
    harvests, so the partition follows the pasture instead of a grid."""
    mine = manhattan(cell, home, length)
    return sum(1 for h in peerHomes if manhattan(cell, h, length) < mine)


def drift(home, target, length, share=0.12):
    """move a home a small step towards target (Lloyd relaxation: every
    keeper walks towards the middle of what it actually harvests, and
    the districts settle into a partition of the pasture)."""
    dx, dy = wrapVector(home, target, length)
    return [
        int(home[0] + share * dx) % length,
        int(home[1] + share * dy) % length,
    ]


def fleeVector(pos, threats, length, cells):
    """the move of at most `cells` steps that ends up farthest from
    every threat, chosen from the eight directions plus the diagonals.

    Sources that chase (LuTze's hunters) exploit a victim that always
    hops the same fixed distance along one axis, so the distance is the
    full time budget and the direction is whatever the ground says."""
    best = None
    bestScore = None
    for dx, dy in (
        (1, 0),
        (-1, 0),
        (0, 1),
        (0, -1),
        (1, 1),
        (1, -1),
        (-1, 1),
        (-1, -1),
    ):
        steps = cells if dx == 0 or dy == 0 else cells // 2
        if steps <= 0:
            continue
        target = (
            (pos[0] + dx * steps) % length,
            (pos[1] + dy * steps) % length,
        )
        score = (
            min(chebyshev(target, t, length) for t in threats)
            + 0.1 * steps
        )
        if bestScore is None or score > bestScore:
            bestScore = score
            best = [dx * steps, dy * steps]
    return best
