# Wesen — project overview

Layout, history and results: how the pieces fit together and what
happened when they were played against each other. Started 2026-09-07 as
working notes and kept as the project's own record since 0.8. To *write*
a source, read `SOURCES.md` instead of this file; `local/` holds
throwaway development scripts and is not tracked.

## What it is

A predator/prey style programming game (2003, Python 2; 2013 Python 3; 2026
`uv`/pyproject): players write an AI ("Wesen source") that controls
creatures ("Wesen") on a toroidal grid. Food grows on the grid. The GUI
plots the total energy per source; the source that survives and hoards the
most energy wins.

## Layout

```
wesen                    # launcher script: runs the game from a clone
pyproject.toml           # uv/setuptools, deps numpy, PyOpenGL, Pillow; script `wesen`
src/Wesen/
  loader.py              # CLI args, config file lookup, checks sources, starts Wesend
  sourceloader.py        # where a player's source is looked for and loaded
  tournament.py          # headless matches, scored over the whole game
  budget.py              # processor-time limit on a source's turn
  configed.py            # INI config reader/editor (~/.wesen/conf by default)
  defaults.py            # CONFIG_OPTIONS / CONFIG_DEFAULTS (all tunables)
  strings.py             # help strings + VERSIONSTRING (read from the package metadata)
  wesend.py              # runs one game: builds World, optional GUI, headless loop
  world.py               # World: grid map, objects dict, per-turn loop, stats, persistence
  point.py               # torus helpers: getShortestTranslation, getDistInMaxMetric
  persistence.py         # unused decorator helper
  defaultwesensource.py  # base class every AI must subclass
  objects/base.py        # WorldObject: position, energy, age, getRangeIterator
  objects/wesen.py       # Wesen: the whole action API (Move, Eat, Vomit, ...)
  objects/food.py        # Food: Grow, Seed, merge food on same cell
  sources/<Name>/main.py # AIs, class must be called WesenSource
  gui/                   # freeglut/PyOpenGL GUI: map + energy graph + text stats
                         #   __init__.py says why a window cannot open here
tests/                   # unittest: rules, persistence, sources,
                         #   determinism (same seed, two interpreters),
                         #   game (a whole game of every shipped source)
tools/                   # profile_wesen.py, bench_distance.py, bench_range.py
data/                    # old changelog / release plan
```

## Running

```sh
sudo apt install freeglut3-dev       # needed for the GUI
uv venv && uv sync                   # creates .venv
uv run wesen                         # GUI, config from ~/.wesen/conf
uv run wesen --disablegui            # headless, prints stats every 1000 turns, Ctrl+C dumps ~/.wesen/gamestate
uv run wesen -c FILE -s A,B,C        # alternative config file, override sources
uv run wesen --defaultconfig         # (re)write defaults; -e interactive editor; --printconfig
uv run wesen -r                      # resume ~/.wesen/gamestate
uv run python -m unittest discover -s tests -t . -p '*.py'   # the whole suite
```

GUI keys: space pause, `s` single step (when paused), `+`/`-` speed,
`m` movie mode (writes m*.png), arrows add/delete/increase/decrease food,
`q`/ESC quit, right click menu. The GUI starts *paused*. Left click
saves screenshot.png.

Headless tournament (`src/Wesen/tournament.py`, since 0.8):

```sh
uv run wesen-tournament --turns 3000 --seeds 1,2,3 --sources Vetinari,Dwarf,Nightwatch,Rincewind,GreatRabbit
```

Ranks by the area under each source's energy curve rather than by its
energy at the final turn; `SOURCES.md` section 8 explains the columns.
Runs on the game's own defaults without a config file. The older
`local/tournament.py` is what it grew out of and is superseded by it.

`local/tournament.conf` is a copy of `~/.wesen/conf` (identical to
`defaults.py`) and can be passed to `wesen -c local/tournament.conf`;
without `-c` the same defaults are used, so it is a convenience, not a
requirement.

Source discovery (`sourceloader.py`, since 0.8): a source is looked for
in `~/.wesen/sources`, then in the folders named by `[wesen] sourcepath`
(`-p DIR`), then among the ones shipped in `src/Wesen/sources`. It may be
a single file `<Name>.py` or a package `<Name>/main.py`. Before 0.8 the
launcher put `~/.wesen/sources` on `sys.path` while the engine imported
`..sources.<Name>.main` relative to its own package, so that folder had
been created and never read since 2022 and a source could only be written
by editing the installation.

## Game rules and the source API

See `SOURCES.md` (compact, complete). Short version: gardening via
`Vomit(1)` is the only sustainable income, time is the bottleneck, fat
wesen are nearly immune.

## Existing sources (src/Wesen/sources)

| source | behaviour | default tournament outcome (2000 turns, seed 1) |
|---|---|---|
| Dwarf | targets food (age ≥ 50)/enemies, "seedOut" vomits 1 energy 3× while random walking, scan moves along a shared random vector | wins: 153 wesen / 153k energy |
| Nightwatch | eats lowest-energy food, hunts weaker enemies once rich, scans east | extinct by ~1000 |
| Rincewind | state machine: search food, then circle around energy-weighted food midpoint eating the biggest food older than 100 | extinct by ~500 |
| GreatRabbit | walks to nearest food, reproduces at 150 | extinct by ~500 |
| Scanner | walks a raster, eats what it stands on, reproduces at 500 | not in default config |
| DrunkenSailor | random walk | trivial |
| SoberSailor | buggy (self.position used as attribute) | would crash |
| WindlePoons | walks to (5,5) then eats around there | trivial |
| Manual | interactive console AI for debugging | dev tool |
| example.py | template | — |

Default config sources (defaults.py): Rincewind,Nightwatch,Dwarf,GreatRabbit,Vetinari. Outcomes above are from the baseline without Vetinari.
Simulation speed headless: ~40 turns/s at 500×500 with ~1000 objects.

## Ideas noted in data/releaseplan.md

Wesen eating wesen, other topologies, more complex AI. Version strings
are inconsistent (pyproject 0.7.0 vs strings.py 0.6.0-alpha).

## New source: Vetinari (src/Wesen/sources/Vetinari/main.py)

Added 2026-09-07 and put into the default source list in `defaults.py`
(the user's `~/.wesen/conf` still has the old list; run
`uv run wesen -c local/tournament.conf` or `uv run wesen -s Rincewind,Nightwatch,Dwarf,GreatRabbit,Vetinari`).

Economy analysis behind it: normal food never grows (growrate 0.2 rounds
to 0), only vomited food grows (0.5/turn, any size), a wesen burns 1
energy/turn, and the score is the energy held by living wesen. So the
game is "plant 1-energy patches, harvest them later", and the limiting
resource is time (25 units/turn), which scales with the number of wesen.

Behaviour per turn (see docstring in the file):

1. `closerLook()`; classify food on own cell, enemies, friends on cell.
2. Threats: enemies on the cell are attacked cheapest-first if
   0.75×mine ≥ theirs (kills) and mine − 0.5×theirs stays positive; before
   that the wesen bulks up from its patches. Killers approaching within 6
   cells trigger bulking or, if hopeless, walking away.
3. Keep energy ≥ 80 by eating own patches.
4. Newborns on a full estate (> 4 wesen per cell) found a new estate 14
   cells away (outside closerLook range, so views don't overlap — keeps
   the simulation fast).
5. Foraging: foreign food ≥ 40 energy yielding ≥ 25 energy per cell of
   distance is fetched (one forager per food, class-level claim table),
   then the wesen returns home.
6. Garden: harvest patches with age ≥ 880 (they die at 1000); reproduce
   when energy ≥ 2 × safe (safe = max(200, 1.6 × strongest enemy seen in
   the last 300 turns)) and the colony is below 32; at age ≥ 996 always
   reproduce, and if the colony is full the child donates everything back
   and dies (age reset without growth); plant `Vomit(1)` up to 50 patches
   per wesen on the cell; harvest the richest patches with leftover time.

Class attributes hold shared colony knowledge: world turn estimate,
alive registry (for the population cap), estate cells, sacrifices,
threat level, claimed forage targets. `persist()`/`restore()` keep home
and trip across `-r` resume.

Tunables are class constants at the top of the file. The caps
(MAX_COLONY 32, PATCHES_PER_WESEN 50 → ≤ 1600 food objects) are chosen
for simulation speed (~25 turns/s headless with all default sources),
not because more would not score higher: an uncapped run reached 1.7M
energy with 124 wesen by turn 1000 but slowed the engine to 2 turns/s.

Dev tools in `local/` (non-versioned): `tournament.py` (headless runs,
`--sources`, `--seed`, `--turns`, `--every`, `--json`),
`debug_colony.py` (registry vs real count), `profile_run.py`
(cProfile of 50 turns), `persist_check.py` (round trip with Vetinari),
`gui_check.py` (runs the real GUI N turns, saves a screenshot, exits
without touching ~/.wesen/gamestate).

### Results (2000 turns, headless, `local/tournament.py`)

| seed | opponents | Vetinari energy (count) | runner-up |
|---|---|---|---|
| 1 | Dwarf, Nightwatch, Rincewind, GreatRabbit | 1,376,676 (32) | Dwarf 40,207 (41) |
| 2 | same | 1,433,937 (33) | Dwarf 105,789 (101) |
| 3 | same | 1,456,086 (34) | Dwarf 51,064 (51) |
| 4 | same | 1,364,462 (32) | Dwarf 152,029 (152) |
| 5 | Dwarf only | 1,460,509 (34) | Dwarf 59,273 (58) |
| 6 | Nightwatch, Scanner, DrunkenSailor | 1,471,138 (34) | all extinct |

Counts above 32 are sacrificial children that vanish the next turn.
Rincewind, GreatRabbit and Nightwatch go extinct before turn ~1000 in
every run, as they do without Vetinari; Dwarf survives on its own
gardening but with 10-30× less energy.

## New source: Weatherwax (src/Wesen/sources/Weatherwax/main.py)

Added 2026-09-07 to beat Vetinari and Dwarf by exploiting their code
(see the module docstring and SOURCES.md 5b). Also added to the default
source list in `defaults.py` and to `local/tournament.conf`.

Roles per wesen: gardener (rolling patch cycle, harvest before age 44),
scout (11 children sweep horizontal bands with `look()`, register food
piles, identify Vetinari residents with `closerLook()`), bogey (pool
energy by touring home cells, travel, station on the estate: residents
flee forever, garden and bodies get eaten, children bogeymen split off
to neighbouring estates), sacrifice (old-age child that donates back).
Shared class state: estate registry (`estates`), energy ledger of all
wesen (`ledger`, used to decide whether a bogeyman is affordable),
recruit table for donations, blob claims.

Timeline in a full-field game (seed 4): 11 scouts out at turn ~200, all
Vetinari estates known by turn 450, all 32 Vetinaris paralysed by turn
1050, 30 of them dead (bodies eaten) by turn 1200.

### Results (headless, `local/tournament.py`, strict mode, energy (count))

| seed | turns | opponents | Weatherwax | Vetinari | Dwarf |
|---|---|---|---|---|---|
| 1 | 2500 | full field | 1,065,825 (44) | 171,702 (8) | 69,984 (74) |
| 4 | 2000 | full field | 1,931,966 (53) | 10,236 (2) | 240,902 (253) |
| 5 | 2000 | Vetinari only | 1,717,793 (45) | 136,442 (8) | – |
| 6 | 2000 | Dwarf only | 1,814,331 (54) | – | 209,643 (213) |
| 2 | 2500 | full field | 2,214,615 (44) | 0 (0) | 524,477 (644) |

Vetinari's total peaks around turn 700-1000 and collapses as the
paralysed residents die; the few survivors are estates that were found
late, when their residents were already too fat for the bogeymen the
colony could finance. Dwarf's late boom (hundreds of thin wesen fed by
its own old seeds far from any Weatherwax estate) is what keeps the
simulation at 6-10 turns/s in the second half of a game.

## New source: LuTze (src/Wesen/sources/LuTze/main.py)

Added 2026-09-08 to beat every other source in the same game, including
Weatherwax (see the module docstring and SOURCES.md 6b/7b). Also added
to the default source list in `defaults.py` and to `local/tournament.conf`.

Roles per wesen: gardener (bootstrap: founders split into 8 gardeners of
~37 energy on turn 3, all time into `Vomit(1)` until the cell holds its
share of `PATCH_BUDGET` = 3000 patches, reached by turn ~60; afterwards a
rolling harvest into bodies, pooling for recruits, guard duty), scout
(48-cell tile grid, one `look()` per tile, patrols afterwards, gleans rich
foreign food), hunter (pool -> travel -> station/chase -> next target or
home: paralyses a Vetinari/Weatherwax cell with 1.4 x the fattest
resident, kills residents with the adjacent-step-then-strike chase, strips
abandoned gardens, splits children for neighbouring estates), sacrifice
(old-age child that donates back). Shared class state: alive table and
ledger keyed by a colony-wide counter (engine ids are reused addresses),
home cells, enemy sightings, estate registry, tile exploration, debug
counters (`stats`).

Timeline in a full-field game: five cells full by turn ~60, map swept by
turn ~250, Vetinari and Weatherwax home cells paralysed and emptied
between turn ~100 and ~500, all opponents extinct by turn ~400-1000.

### Results (2000 turns, headless, `local/tournament.py`, strict mode)

Full field = Weatherwax, Vetinari, Dwarf, Nightwatch, Rincewind,
GreatRabbit. Energy (count) at the end; "turn 500" column lists what was
still alive then.

| seed | opponents | LuTze | turn 500 survivors | end |
|---|---|---|---|---|
| 1 | full field | 2,646,427 (61) | Weatherwax 15,941 (8), Dwarf 67 (1) | all extinct |
| 2 | full field | 2,536,899 (55) | Vetinari 19,779 (2), Weatherwax 20,699 (8) | Dwarf 1,257 (1) |
| 3 | full field | 2,629,591 (60) | Dwarf 1,263 (2) | all extinct |
| 4 | full field | 2,693,376 (58) | Dwarf 1,115 (2), Nightwatch 633 (3) | Dwarf 1,049 (1) |
| 5 | full field | 2,506,815 (64) | Vetinari 64,237 (6), Weatherwax 1,505 (1) | all extinct |
| 6 | full field | 2,656,326 (58) | Vetinari 11,693 (1), Weatherwax 11,610 (5) | all extinct |
| 7 | full field | 2,669,518 (55) | GreatRabbit 619 (15), Weatherwax 9,310 (4) | all extinct |
| 8 | full field | 2,591,541 (60) | Vetinari 14,027 (1), Weatherwax 6,678 (6) | all extinct |
| 9 | full field | 2,547,182 (59) | Weatherwax 26,860 (12), Dwarf 1,319 (1) | all extinct |
| 7 | Weatherwax only | 2,722,834 (58) | none | extinct by turn 500 |
| 8 | Dwarf only | 2,694,966 (57) | Dwarf 2,066 (2) | Dwarf 5,471 (6) |

Seeds 1-3 ran with an earlier revision (before the unique-id registries);
seed 5 was run three times with the final code and gave the identical
result each time, i.e. the game is deterministic per seed now. For
comparison, Weatherwax's own best full-field result was 2.2M with
Vetinari at 0 and Dwarf at 524k. Runs take 100-160 s (12-20 turns/s over
the whole game, versus 6-10 turns/s in the Weatherwax games), because
the opponents' gardens and swarms never come into being. In seed 5
Vetinari recovered to 26 wesen around turn 1000 (its threat memory had
decayed, hunters had aborted on residents fatter than the registry
said) before being wiped out; that lag is the known weak spot.
