"""These are some helping functions,
that come handy in writing an AI,
and is used by Food.
In future, this code might move elsewhere."""

from math import copysign

from numpy.random import randint


def getRandomPosition(length):  # unused
    """returns a random n-dimensional position."""
    return [randint(0, length - 1), randint(0, length - 1)]


def getRandomPositionInRadius(
    position, radius, length
):  # TODO move to Food
    """x + random(-radius,+radius)"""
    return [
        (length + pc + randint(-radius, radius)) % length
        for pc in position
    ]


def getShortestTranslation(a, b, length):
    """takes ((ax,ay),(bx,by),length),
    computes shortest vector from a to b."""
    return [
        min(c, -1 * copysign(length - c, c), key=abs)
        for c in [(bc - ac) % length for (ac, bc) in zip(a, b)]
    ]


def getDistInMaxMetric(a, b, length):  # TODO move to helper
    """takes ((ax,ay),(bx,by),length),
    computes distance from a to b."""
    return abs(max(getShortestTranslation(a, b, length), key=abs))


def ringBlocks(centre, radius, length):
    """the pieces of one axis covered by [centre-radius, centre+radius]
    on a ring of the given length, as (start, stop) pairs.

    The world is a torus, so a window near the edge continues on the
    other side and is then two pieces rather than one. Returning slice
    bounds instead of a list of coordinates is what lets the caller cut
    the occupancy grid into whole blocks and hand them to numpy."""
    span = 2 * radius + 1
    if span >= length:
        return ((0, length),)
    low = (centre - radius) % length
    high = low + span
    if high <= length:
        return ((low, high),)
    return ((low, length), (0, high - length))
