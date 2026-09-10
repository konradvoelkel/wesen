"""config defaults

For an explanation of these values,
run the config editor (with wesen --editconfig)
or see strings.py"""

from os.path import expanduser, join

DEFAULT_CONFIGFOLDER = join(expanduser("~"), ".wesen")
DEFAULT_CONFIGFILE = join(DEFAULT_CONFIGFOLDER, "conf")
# TODO enable command-line option for filename
DEFAULT_GAME_STATE_FILE = join(DEFAULT_CONFIGFOLDER, "gamestate")
# this configfile is _always_ used before any other specified!
# these default values are used in configed for the defaults in the editor and when no values are specified in the configfile.
# We recommend to use the calculated values as they are.
# For an explanation of these values,
# run the config editor (with wesen --editconfig)

# HINT: While the following could be inferred from the defaults below,
#      It adds a lot of clarity to have it explicitly.
CONFIG_OPTIONS = [
    [
        "gui",
        [("enable", bool), ("source", str), ("size", int), ("pos", str)],
    ],  # x,y
    ["world", [("length", int), ("seed", int)]],
    [
        "wesen",
        [
            ("sources", str),  # comma-separated
            ("sourcepath", str),  # comma-separated directories
            ("count", int),
            ("energy", int),
            ("maxage", int),
            ("upkeep", int),
            ("upkeep_rate", float),
            ("reproduce_cost", int),
            ("child_min_energy", int),
            ("attack_damage", float),
            ("attack_cost", float),
            ("shared_state", str),  # allow | isolate | strict
            ("cpu_budget", float),  # seconds of thought per turn, 0 off
        ],
    ],
    [
        "food",
        [
            ("count", int),
            ("energy", int),
            ("maxamount", int),
            ("maxage", int),
            ("growrate", float),
            ("seedrate", float),
            ("rule", str),  # classic | life
            ("bite", int),
            ("seedenergy", int),
            ("fertile_peak", float),
            ("fertile_width", float),
            ("birth_peak", float),
            ("birth_width", float),
            ("birth_maturity", float),
        ],
    ],
    [
        "climate",
        [
            ("enable", bool),
            ("period", int),
            ("amplitude", float),
            ("severity_random", float),
            ("random_phase", bool),
        ],
    ],
    ["variation", [("enable", bool), ("spread", float)]],
    [
        "biome",
        [("enable", bool), ("scale", int), ("strength", float)],
    ],
    [
        "range",
        [
            ("look", int),
            ("closer_look", int),
            ("talk", int),
            ("seed", int),
        ],
    ],
    [
        "time",
        [
            ("init", int),
            ("max", int),
            ("look", int),
            ("closerlook", int),
            ("move", int),
            ("eat", int),
            ("talk", int),
            ("vomit", int),
            ("broadcast", int),
            ("attack", int),
            ("donate", int),
            ("reproduce", int),
        ],
    ],
]

CONFIG_DEFAULTS = {
    "gui": {"enable": True, "source": "gui", "size": 500, "pos": "50,50"},
    "world": {"length": 500, "seed": 0},
    "wesen": {
        "sources": "Rincewind,Nightwatch,Dwarf,GreatRabbit,Vetinari,"
        "Weatherwax,LuTze",
        # extra folders holding player-written sources; ~/.wesen/sources
        # is always searched as well (see sourceloader.py)
        "sourcepath": "",
        "count": 5,
        "energy": 300,
        "maxage": 1000,
        "upkeep": 1,
        "upkeep_rate": 0.005,
        "reproduce_cost": 20,
        "child_min_energy": 60,
        "attack_damage": 0.75,
        "attack_cost": 0.5,
        "shared_state": "isolate",
        # seconds of processor time one wesen may spend deciding what
        # to do, before its turn is cut short (see budget.py). Loose on
        # purpose: the worst legitimate turn measured is about 0.05 s,
        # so this breaks a hang without touching anybody's strategy
        "cpu_budget": 0.5,
    },
    "climate": {
        "enable": True,
        "period": 400,
        "amplitude": 0.5,
        "severity_random": 0.3,
        "random_phase": True,
    },
    "variation": {"enable": False, "spread": 0.2},
    "biome": {"enable": True, "scale": 80, "strength": 0.5},
    "food": {
        "count": 1200,
        "energy": 50,
        "maxamount": 100,
        "seedrate": 0.05,
        "growrate": 0.6,
        "maxage": 1000,
        "rule": "life",
        "bite": 15,
        "seedenergy": 5,
        "fertile_peak": 1.0,
        "fertile_width": 1.5,
        "birth_peak": 0.8,
        "birth_width": 2.0,
        "birth_maturity": 0.6,
    },
    "range": {"seed": 10, "look": 24, "closer_look": 12, "talk": 16},
    "time": {
        "init": 25,
        "max": 50,
        "look": 1,
        "closerlook": 2,
        "talk": 1,
        "broadcast": 1,
        "move": 7,
        "eat": 10,
        "vomit": 12,
        "donate": 13,
        "attack": 14,
        "reproduce": 20,
    },
}
