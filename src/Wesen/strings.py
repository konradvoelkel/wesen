"""string definitions"""

from .defaults import DEFAULT_CONFIGFILE, DEFAULT_GAME_STATE_FILE

# for I18N, insert here a stringtable-loader or replace this file.

VERSIONSTRING = "wesen 0.6.0-alpha"
URL = "https://github.com/reims/wesen"

STRING_ERROR_NOTSAMEPATH = "There is a path problem. The program could not find the desired files."
STRING_ERROR_FILEEXISTS = "file %s already exists, overwrite? (y, n) "
STRING_ERROR_NOTWROTE = "didn't write file %s"


STRING_MESSAGE_WROTE = "wrote file %s"
STRING_MESSAGE_PROCESSING = "processing file %s"
STRING_MESSAGE_REMOVED = "removed file %s"


STRING_CONFIGED = {
    "WESEN": {
        "SOURCES": "(comma-seperated wesen sources)\nsources=",
        "COUNT": "(how much wesen are created during startup from each source)\ncount=",
        "ENERGY": "(starting energy of every wesen at the beginning)\nenergy=",
        "MAXAGE": "(maximum age of wesen until they die)\nmaxage=",
        "UPKEEP": "(energy every wesen burns per turn, whatever its size)\nupkeep=",
        "UPKEEP_RATE": "(energy burnt per turn per own energy, 0.005 means a 1000 energy wesen burns 5)\nupkeep_rate=",
        "REPRODUCE_COST": "(energy destroyed by a birth, on top of the half given to the child)\nreproduce_cost=",
        "CHILD_MIN_ENERGY": "(a birth needs to leave the child at least this much, or it fails)\nchild_min_energy=",
        "ATTACK_DAMAGE": "(energy a victim loses, per energy of the attacker)\nattack_damage=",
        "ATTACK_COST": "(energy an attacker loses, per energy the victim had)\nattack_cost=",
        "SHARED_STATE": "(what a source may keep on its class: allow = anything, isolate = every wesen gets its own copy of it, strict = it must not change at all)\nshared_state=",
    },
    "GUI": {
        "ENABLE": "\nenable=",
        "SOURCE": "\nsource=",
        "SIZE": "\nsize=",
        "POS": "\npos=",
    },
    "WORLD": {
        "LENGTH": "(length of the worlds x-axis and y-axis)\nlength=",
        "SEED": "(random seed of the game, 0 draws a new one and prints it)\nseed=",
    },
    "CLIMATE": {
        "ENABLE": "(seasons: food growth varies periodically)\nenable=",
        "PERIOD": "(turns of one full year)\nperiod=",
        "AMPLITUDE": "(how far growth swings from 1, 0.5 means 0.5 to 1.5)\namplitude=",
        "SEVERITY_RANDOM": "(how much the severity of a single season is drawn at random)\nseverity_random=",
        "RANDOM_PHASE": "(start the game at a random point of the year)\nrandom_phase=",
    },
    "BIOME": {
        "ENABLE": "(fertile and poor regions instead of uniform ground)\nenable=",
        "SCALE": "(size of a region in cells)\nscale=",
        "STRENGTH": "(0.5 means the best ground grows 1.5x and the worst 0.5x)\nstrength=",
    },
    "VARIATION": {
        "ENABLE": "(vary time costs, ranges and food rules per game, so sources have to read the config)\nenable=",
        "SPREAD": "(how far the rules may be varied, 0.2 means 20%%)\nspread=",
    },
    "FOOD": {
        "COUNT": "(how many food places at start)\ncount=",
        "ENERGY": "(starting energy of every food place at the beginning)\namount=",
        "MAXAMOUNT": "(maximum food amount without growth stop)\nmaxamount=",
        "MAXAGE": "(maximum age without self-destruction)\nmaxage=",
        "SEEDRATE": "(probability per round that a food place tries to seed, 1 means every round)\nseedrate=",
        "GROWRATE": "(classic rule: mean energy gained per round; life rule: energy gained per round at peak fertility)\ngrowrate=",
        "RULE": "(classic: independent growth and seeding; life: growth depends on food density around, like game of life)\nrule=",
        "BITE": "(maximum energy a wesen takes from a food place per eat, 0 means all at once)\nbite=",
        "SEEDENERGY": "(life rule: energy a seed starts with, paid by the parent)\nseedenergy=",
        "FERTILE_PEAK": "(life rule: food density (energy around / maxamount) with fastest growth)\nfertile_peak=",
        "FERTILE_WIDTH": "(life rule: distance from fertile_peak where growth becomes decay)\nfertile_width=",
        "BIRTH_PEAK": "(life rule: food density at which seeds take root best)\nbirth_peak=",
        "BIRTH_WIDTH": "(life rule: distance from birth_peak beyond which seeds never take root)\nbirth_width=",
        "BIRTH_MATURITY": "(life rule: share of its own capacity a food place needs before it may seed, so the pasture spreads slowly)\nbirth_maturity=",
    },
    "RANGE": {
        "LOOK": "(how far the wesen can look)\nlook=",
        "CLOSER_LOOK": "(how far the wesen can look closely)\nlook=",
        "TALK": '(how "far" the wesen can talk)\ntalk=',
        "SEED": "(how far the food can seed)\nseed=",
    },
    "TIME": {
        "INIT": "(time a wesen gets each turn)\ninit=",
        "MAX": "(maximum time a wesen can have in a turn)\nmax=",
        "LOOK": "(time needed for looking around)\nlook=",
        "CLOSERLOOK": "(time needed for a closer look)\ncloserlook=",
        "MOVE": "(time needed for moving)\nmove=",
        "EAT": "(time needed for eating)\neat=",
        "TALK": "(time needed for talking)\ntalk=",
        "VOMIT": "(time needed for vomiting)\nvomit=",
        "ATTACK": "(time needed for attacking)\nattack=",
        "BROADCAST": "(time needed for broadcasting)\nbroadcast=",
        "DONATE": "(time needed for donations)\ndonate=",
        "REPRODUCE": "(time needed for reproduction)\nreproduce=",
    },
}

STRING_USAGE_DESCRIPTION = (
    "Predator-prey simulation for learning python and AI. See also " + URL
)
STRING_USAGE_CONFIGFILE = (
    "specify the configfile to use, defaults to " + DEFAULT_CONFIGFILE
)
STRING_USAGE_EDITCONFIG = "start the config editor"
STRING_USAGE_DEFAULTCONFIG = "write the default config"
STRING_USAGE_PRINTCONFIG = (
    "print the config (without changes from command-line options)"
)
STRING_USAGE_OVERWRITE = "overwrite config [%s] %s"
STRING_USAGE_RESUME = (
    f"resumes game stored in {DEFAULT_GAME_STATE_FILE} if exists"
)
STRING_USAGE_EPILOG = "all other arguments are passed to OpenGL"
