"""Seasons: a periodic, partly random modulation of food growth.

The climate is a single object owned by the World and stepped once per
turn. It publishes its state as a dict in
``infoAllWorld["world"]["climate"]``, which is updated in place, so both
Food objects and AI sources see the current season without any plumbing
of their own (see DefaultWesenSource.season).

The cycle is deliberately predictable in its calendar and random in its
severity: a source can plan for winter, but not for how hard it will be.

    phase   = ((turn + offset) / period) mod 1
    growth  = 1 + amplitude * severity * sin(2 pi phase)
    seeding = growth

``growth`` multiplies the growth of every food cell (never its decay, so
a hard winter means no growth rather than slow decay) and ``seeding``
multiplies the chance of a food cell to seed. A new severity is drawn
whenever the sine crosses zero, i.e. once for the abundant half of the
cycle and once for the lean half.
"""

from math import pi, sin

from numpy.random import uniform

SEASONS = ("spring", "summer", "autumn", "winter")

GROWTH_MIN = 0.05  # even the hardest winter grows a little
GROWTH_MAX = 2.0


class Climate:
    """seasons; see the module docstring"""

    def __init__(self, infoClimate):
        self.info = infoClimate
        self.enabled = bool(infoClimate.get("enable", False))
        self.period = max(1, int(infoClimate.get("period", 400)))
        self.amplitude = float(infoClimate.get("amplitude", 0.0))
        self.severityRandom = float(
            infoClimate.get("severity_random", 0.0)
        )
        if infoClimate.get("random_phase", False):
            self.offset = int(uniform(0, self.period))
        else:
            self.offset = 0
        self.half = None  # 0 = abundant half of the cycle, 1 = lean half
        self.severity = 1.0
        self.state = {
            "enable": self.enabled,
            "season": "summer",
            "phase": 0.0,
            "growth": 1.0,
            "seeding": 1.0,
            "severity": 1.0,
            "period": self.period,
        }
        self.step(0)

    def _drawSeverity(self):
        """how hard this half of the cycle turns out to be"""
        spread = self.severityRandom
        if spread <= 0:
            return 1.0
        return float(uniform(1.0 - spread, 1.0 + spread))

    def step(self, turn):
        """advance to the given world turn and update the shared state"""
        if not self.enabled:
            return self.state
        phase = ((turn + self.offset) / self.period) % 1.0
        wave = sin(2 * pi * phase)
        half = 0 if wave >= 0 else 1
        if half != self.half:
            # a zero crossing: the next half of the year is drawn now
            self.half = half
            self.severity = self._drawSeverity()
        growth = 1.0 + self.amplitude * self.severity * wave
        growth = min(GROWTH_MAX, max(GROWTH_MIN, growth))
        # seasons are the quarters of the cycle centred on the extremes,
        # so the peak lies in the middle of summer, the trough in winter
        index = int(((phase + 0.125) % 1.0) * 4) % 4
        self.state.update(
            {
                "season": SEASONS[index],
                "phase": phase,
                "growth": growth,
                "seeding": growth,
                "severity": self.severity,
            }
        )
        return self.state

    def persist(self):
        """JSON serializable state (the config itself is persisted by
        the world as the [climate] section)"""
        return {
            "offset": self.offset,
            "half": self.half,
            "severity": self.severity,
        }

    def restore(self, obj):
        self.offset = obj.get("offset", 0)
        self.half = obj.get("half")
        self.severity = obj.get("severity", 1.0)


def growthFactor(infoWorld):
    """the current growth multiplier of the world a food object lives in
    (1.0 when there is no climate, so callers need no special case)"""
    climate = infoWorld.get("climate")
    if not climate or not climate.get("enable"):
        return 1.0
    return climate.get("growth", 1.0)


def seedingFactor(infoWorld):
    climate = infoWorld.get("climate")
    if not climate or not climate.get("enable"):
        return 1.0
    return climate.get("seeding", 1.0)
