"""Reproducible randomness: one seed per game, and per-game variation
of the rules themselves.

Two separate things live here.

``applySeed`` seeds both random number generators used by the engine and
the AI sources (``random`` and ``numpy.random``) from ``[world] seed``,
drawing and storing one if the config says 0. Every game is therefore
reproducible from the number printed at startup.

``applyVariation`` multiplies a whitelist of rule parameters by a factor
drawn per game from ``uniform(1 - spread, 1 + spread)``. The point is not
noise for its own sake: the varied values reach every source through the
info dicts it already receives, so code that reads the rules adapts and
code with hardcoded constants degrades. Outcome noise (attacks that
sometimes miss) would only add variance and is deliberately absent.
"""

import random

import numpy.random

# section -> keys that may be varied per game.
# Only rules a source can read from its info dicts are listed here.
VARIED = {
    "time": ["move", "eat", "attack", "vomit", "reproduce"],
    "range": ["look", "closer_look", "talk", "seed"],
    "food": ["growrate", "maxamount", "bite", "seedrate"],
    "wesen": ["upkeep_rate", "reproduce_cost"],
}


def applySeed(config, announce=True):
    """seeds random and numpy.random from config["world"]["seed"],
    drawing one when it is 0 (or missing). Returns the seed used and
    writes it back into the config, so it is persisted with the game."""
    world = config.setdefault("world", {})
    seed = int(world.get("seed", 0) or 0)
    if seed <= 0:
        seed = random.randrange(1, 2**31 - 1)
    world["seed"] = seed
    random.seed(seed)
    numpy.random.seed(seed)
    if announce:
        print("wesen: game seed", seed)
    return seed


def varyValue(value, spread):
    """scale one value; ints stay ints and never fall below 1"""
    factor = random.uniform(1.0 - spread, 1.0 + spread)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return max(1, int(round(value * factor)))
    return type(value)(value * factor)


def applyVariation(config, announce=True):
    """varies the whitelisted rules in place, if [variation] enables it.
    Must run after applySeed, so the variation is part of the seed."""
    info = config.get("variation") or {}
    if not info.get("enable", False):
        return {}
    spread = float(info.get("spread", 0.0))
    if spread <= 0:
        return {}
    changed = {}
    for section, keys in VARIED.items():
        target = config.get(section)
        if not target:
            continue
        for key in keys:
            if key not in target:
                continue
            new = varyValue(target[key], spread)
            if new != target[key]:
                changed[f"{section}.{key}"] = (target[key], new)
            target[key] = new
    if announce and changed:
        print(
            f"wesen: rules varied by up to {int(spread * 100)}%:",
            ", ".join(
                f"{k} {old}->{new}" for k, (old, new) in changed.items()
            ),
        )
    return changed
