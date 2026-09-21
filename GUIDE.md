# Writing a Wesen source

A source is the program that plays one species of wesen. This file is
everything you need to write one: how to run the game, what a source
looks like, the API, the rules that decide games, and how to measure
what you wrote. What the shipped sources do is in `SOURCES.md`; the
project's layout and history are in `OVERVIEW.md`.

## 1. Run

```sh
uv sync                                   # once; needs freeglut3-dev for the GUI
uv run wesen                              # GUI (starts PAUSED: press space)
uv run wesen --disablegui                 # headless, Ctrl+C stops
uv run wesen -s MyWesen,Dwarf -p ~/my-wesen              # sources of your own
uv run wesen-tournament --turns 2000 --seeds 1,2,3 \
    --sources Vetinari,Dwarf,Nightwatch,Rincewind,GreatRabbit   # headless, scored
uv run python -m unittest discover -s tests -t . -p '*.py'   # the whole suite
uv run ruff check src/Wesen/sources/<Name>/ && uv run ruff format src/Wesen/sources/<Name>/
```

Without a config file the game uses its own defaults and writes them to
`~/.wesen/conf` on first run; `-c FILE` plays from a different one.
`[wesen] sources = A,B,C` selects the sources; `-s A,B,C` overrides it
on the command line. Each source starts with `count` (5) wesen of
`energy` (300) at random cells.

GUI keys (`?` or `h` in the window shows this list; right-click opens a
menu):

| key | does |
|---|---|
| `space` | pause / run |
| `s` | one turn |
| `+` / `-` | faster / slower |
| `g` | switch what the graph shows: energy per source, population per source, both, the world, everything |
| `c` | save a screenshot as `wesen-<turn>.png` |
| `m` | movie mode: every frame to disk |
| `q` / `x` / `Esc` | save the game state and quit |
| arrows | add / delete / feed / starve food |

Each curve in the graph is scaled on its own unless the mode says the
curves share one scale, and the caption prints the current value of
every curve.

## 2. Where a source lives

The game looks in `~/.wesen/sources` first, then in any folder named by
`[wesen] sourcepath` (or `-p DIR`), and last among the sources shipped
in `src/Wesen/sources`. Two shapes work:

```
~/.wesen/sources/<Name>.py             # one file
~/.wesen/sources/<Name>/main.py        # a package, for code split over files
```

`<Name>` is the string used in the config. Since your own folders are
searched first, you can copy a shipped source out of the tree, keep the
name, and play your version against the rest of the field.

Either shape must define a class called `WesenSource` subclassing
`DefaultWesenSource`. Both are checked when the game starts and said
plainly if missing. Your source reaches the game through the installed
package, so import it absolutely:

```python
from Wesen.defaultwesensource import DefaultWesenSource
from Wesen.point import getDistInMaxMetric, getShortestTranslation  # optional
```

A source package may import its own modules the ordinary way
(`from . import ledger`), as `Rincewind` does. The sources shipped in
`src/Wesen/sources/` are *inside* the game's package and use relative
imports (`from ...defaultwesensource import ...`); that form only works
in there, and is the one thing to change when you copy one out.

Skeleton:

```python
from Wesen.defaultwesensource import DefaultWesenSource

class WesenSource(DefaultWesenSource):
    def __init__(self, infoAllSource):
        DefaultWesenSource.__init__(self, infoAllSource)
        # self.infoTime, self.infoRange, self.infoWesen, self.infoFood,
        # self.infoWorld, self.worldlength (500), self.source (own name)
    def __str__(self):            return "<name shown in debug output>"
    def main(self):               ...   # called once per turn, spend self.time()
    def Receive(self, message):   ...   # Talk/Broadcast from other wesen
    def persist(self):            return {}          # JSON state for -r resume
    def restore(self, obj):       ...                # obj["wesensource"] is what persist returned
```

One instance per wesen; a child created by `Reproduce()` gets a fresh
instance and inherits nothing but what its parent tells it (section 3c).
`src/Wesen/sources/example.py` is this skeleton as a file.

## 3. The API

The engine injects these methods into the instance. Free, no time cost:
`self.id()`, `self.age()`, `self.position()` (live `[x, y]` list),
`self.energy()`, `self.time()`.

Every turn, before `main()`: energy − upkeep, `time = min(time + 25, 50)`.
Upkeep is `[wesen] upkeep + upkeep_rate · energy` (1 + 0.005·energy), so
a 300-energy wesen burns 2.5 per turn and a 10 000-energy one burns 51:
hoarding costs, and colonies are self-limiting. Actions that cost time
silently do nothing and return `False`/`[]` if `time` is insufficient.
Defaults from `src/Wesen/defaults.py`:

| call | time | effect / return |
|---|---|---|
| `look()` | 1 | list of `{"position","type","id"}` within 24 cells (max metric), self excluded |
| `closerLook()` | 2 | same within 12 cells, plus `"energy","age","time","source"` (`"food"` for food) |
| `Move([dx, dy])` | 7·(\|dx\|+\|dy\|) | all-or-nothing; wraps around the torus; `True` if moved |
| `MoveToPosition([x, y])` | via Move, one cell per step (diagonal step = 14) | `True` if arrived; stops when time runs out |
| `Eat(id)` | 10 | food on own cell only; adds one bite of its energy; `True` on success |
| `Reproduce()` | 20 | child with `(energy − 20) // 2` on the same cell, own age reset to 0; returns the child's id, or `False` (for free) when the child would have under `child_min_energy` (60) |
| `Attack(id)` | 14 | wesen on own cell only; victim −int(0.75·mine), me −int(0.5·victim's previous energy); `True` if I survive |
| `Vomit(e)` | 12 | food with energy `e` on own cell; `e > energy` kills you |
| `Donate(e, id)` | 13 | wesen on own cell; capped at own energy; donating everything kills you |
| `Talk(id, msg)` | 1 | `Receive(msg)` on that wesen if within 24 cells |
| `Broadcast(msg)` | 1 | `Receive(msg)` on every wesen within 16 cells, whatever its source |

A message is delivered inside the sender's turn, so a child can be
briefed by `Talk` in the turn it is born. A dict message arrives
carrying `msg["from"] = {"source", "id"}`, put there by the engine and
unforgeable; read it with `self.sender(message)` and make
`self.fromColleague(message)` the first line of any `Receive` that
reads a protocol of its own. What the message *says* may still be a lie.

`RuleException` (aborts only this wesen's turn): `Eat`/`Attack`/`Donate`
with an id that no longer exists, `Eat` on a different cell or on a
non-food, and running over the processor budget (section 4). Any other
exception is caught too: the turn is skipped, counted in `World.faults`
and the traceback printed once. So: call `closerLook()` at the start of
`main()` and only use ids from that call; ids are valid for the rest of
your turn only.

Helpers on `DefaultWesenSource` (see `src/Wesen/defaultwesensource.py`):

* food: `foodRule()`, `foodBite()`, `foodRoots()`, `foodYield(o)`,
  `foodKills(o)`, `foodSustainable(o)`, `foodRipe(o)`,
  `foodWanted(o, hungry, starving)`, `plantEnergy()`;
* rules: `upkeepOf(energy)`, `birthCost()`, `minBirthEnergy()`,
  `attackDamage()`, `attackCost()`;
* the world: `fertility([x, y])` (free, constant for the game),
  `season()`, `growthFactor()`, `lean()`, `turnsUntilSpring()`,
  `gameRandom(salt)` (a generator every wesen of your source draws the
  same numbers from - for things a colony must agree on that nobody
  has to learn, never for what a wesen *sees*).

## 3b. The rules are not constants

The numbers in this file are defaults. Read them from `infoTime`,
`infoRange`, `infoFood`, `infoWesen`, `infoWorld` and derive every
dimensioned threshold from them; a source with hardcoded numbers loses
the games it would otherwise win.

* **One seed per game.** `[world] seed` (0 draws one) seeds `random`
  and `numpy.random` before anything is built; it is printed at startup
  and persisted, so any game replays exactly. Never draw random numbers
  at import time or in a class body: that is outside the seed.
* **Seasons** (`[climate]`, on): food growth is multiplied by a value
  swinging around 1 with `period` 400 and `amplitude` 0.5; each
  half-year's severity is drawn at random (`severity_random` 0.3). The
  wesen are unaffected, the income is not: store fat in autumn and do
  not split into winter. `self.season()`, `self.lean()`,
  `self.turnsUntilSpring()`.
* **Biomes** (`[biome]`, on): a static fertility map from the seed
  (`scale` 80, `strength` 0.5) multiplies how fast food grows at a
  cell, how much it can hold (best ground 150, worst 50) and how
  readily a seed roots there. `self.fertility([x, y])` is free.
* **Per-game rule variation** (`[variation]`, off): with `enable =
  True` the time costs, ranges, `growrate`/`maxamount`/`bite`/
  `seedrate`, `upkeep_rate` and `reproduce_cost` are each multiplied
  by a factor drawn once per game from `uniform(1 ± spread)`. Turn it
  on while developing, or you will hardcode the defaults without
  noticing.

## 3c. Class attributes are genes, not a shared brain

A source is one program played by many wesen, so a class attribute is
shared by all of them: one wesen writes a map into it and every other
reads it wherever it stands, and nothing in the world carried the fact
between them. That is telepathy, and it makes `Talk` and `Broadcast`
pointless. **The rule:** a class attribute is genetic information, the
same for every wesen and for the whole game. What a wesen learns
belongs in the instance; what it wants another wesen to know has to
be said out loud.

`[wesen] shared_state` (see `src/Wesen/isolation.py`) decides how the
engine enforces it:

| value | effect |
|---|---|
| `isolate` (default) | the shared class keeps the genes, frozen; every wesen is built from a private subclass holding its own deep copy of every mutable class attribute. Writes through `self` or `cls` keep working and simply stop being shared; a write to the class *by name* raises `TypeError` |
| `strict` | the genes are frozen and nothing is copied: keeping state on the class fails, wherever it is written from |
| `allow` | class attributes are shared, the old way |

Under `isolate` and `strict` the engine also seals the side channels:
messages are values (dicts arrive frozen but still `dict`, lists as
tuples, anything else as its `repr`), every dict message is stamped
with its real sender, the engine's own info dicts are read-only views,
and a source package's mutable module globals are frozen (constant
tables keep working; a module-level registry does not). Rebinding a
class attribute cannot be frozen away, so `World` checks every 50
turns and counts it as a rule violation.

Two consequences for a colony that wants to coordinate: a clock, a
roll of who has been heard from, and "what I learned this turn" have
to travel by message (`src/Wesen/colony.py` is a general form of that
bookkeeping); and a population rule cannot be measured against a count
of the whole colony, because nobody ever hears the whole roll -
measure the ground or the neighbours a wesen keeps instead, or relay
the roll.

## 4. Rules that decide games (defaults)

* The world is a 500×500 torus for movement and vision alike.
* Turn loop: all objects act once per turn in creation order; objects
  created this turn act next turn. Nobody acts in the middle of your
  `main()`.
* Death: energy ≤ 0, or age > `maxage` (1000). Death by old age leaves
  the body as food only if the wesen still has the 12 time a `Vomit`
  costs; killed in a fight, or starved, it leaves nothing.
* **Food** (`[food] rule = life`, see `src/Wesen/objects/food.py`):
  1200 cells of 50 energy at the start, capacity `maxamount` (100)
  times the ground's fertility. A cell's growth depends on the food
  density around it - the energy within `range.seed` (10 cells)
  divided by `maxamount` - fastest at `fertile_peak` (1.0), zero
  `fertile_width` (1.5) away from it and negative beyond; within that,
  logistic in the cell's own energy (at most `growrate` 0.6 per turn,
  at half capacity). A mature pasture is therefore density-limited:
  its cells sit near half capacity, one or two cells per hundred
  on the map. Seeds cost the parent `seedenergy` (5), come only from cells
  above `birth_maturity` (0.6) of capacity, and root only where the
  density is near `birth_peak` (0.8); a seed starts small and takes a
  few hundred turns to grow. Cells die at age 1000. `Eat()` takes a
  bite of `bite` (15); a bite that would leave no more than
  `seedenergy` kills the cell - so a cell at 20 or less is eaten whole,
  and a killed cell comes back only by a neighbour's seed. Vomited
  food is ordinary food; a blob above capacity neither grows nor
  shrinks and lies there until eaten.
* **The economics that follow.** The pasture is the income and a cell
  pays at most one bite every 25 turns. A wesen has 25 time a turn, a
  bite costs 10 and a step 7, so income is decided by walking, not by
  eating: knowing which cells are ripe *now* is worth more than any
  amount of cleverness on the cell. Grazing a cell to 25-30 % of its
  capacity costs little regrowth; killing it removes the income for
  hundreds of turns. Many thin wesen out-harvest few fat ones, since
  upkeep is a flat 1 plus 0.5 % of the body, so the population that
  wins is the one the pasture can just feed - and on a shared pasture
  whatever one side leaves standing, the other eats. Gardening
  (`Vomit` as an investment) does not pay under this rule: a planted
  cell returns less than carrying the energy costs, and the pasture
  fills the same ground by itself.
* **The classic rule** (`rule = classic`) is the old game: food grows
  by `int(uniform(0,2)·growrate)` per turn and seeds at `seedrate` when
  fewer than 11 cells are near; vomited food grows 0.5 per turn
  regardless of size. Nothing shipped is tuned for it any more.
* **Fights:** an attacker with A striking a victim with V costs the
  victim 0.75·A and the attacker 0.5·V; a kill (0.75·A ≥ V) yields
  nothing. First strike wins even fights, a victim with V > 2A kills
  its attacker, and being fat is the best defence. A kill only pays
  when the victim is far cheaper than what it would otherwise eat of
  yours: a thin thief on your own cell, yes; a rival's colony, no.
* **Talking** costs 1 time, a seventh of a step, and a message may
  carry as much as you like. `Broadcast` is public - every source in
  range hears it, and one shipped source lives by listening to others.
* **Your code has a time limit of its own.** `[wesen] cpu_budget`
  (0.5 s of processor time per wesen and turn, 0 switches it off)
  cuts a turn short with a `RuleException` wherever you happened to
  be. It breaks a hang rather than shaving a strategy (the median
  wesen thinks for about half a millisecond); a tournament may set it
  tighter. A game in which it fires no longer replays exactly. Unix
  only - see `src/Wesen/budget.py`. `wesen-tournament`'s `cpu` column
  shows who is spending the machine; do the arithmetic of a birth once,
  not on every food in view.
* **Simulation cost** scales with the number of wesen, not of food
  cells: a diverse game runs at ~50 ms a turn, one source swarming to
  300 wesen makes it crawl.

## 5. Measuring a source

`wesen-tournament` (`src/Wesen/tournament.py`) plays sources headless
and reports, per source:

| column | is |
|---|---|
| `mean` | the area under the energy curve divided by the length of the game: what the source held *on average*. The ranking uses this. |
| `energy` | energy at the last turn, the score the GUI graph shows. Printed as a second ranking whenever it disagrees with the first. |
| `alive` | share of the game the source had at least one wesen. |
| `cpu` | share of the real time spent running source code. |

`--seeds 1,2,3` plays each seed and averages, with a `wins` column;
`--json FILE` writes it all out; `-c FILE` uses a config file (the
same one `wesen -c FILE` opens in the GUI); `-p DIR` and `-s A,B,C`
work as they do for `wesen`; `--every N` prints a line of counts and
energies every N turns, which is where you watch the food count - a
shrinking pasture means somebody is eating their future.

What to run, in this order:

1. **Alone** (`-s MyWesen`, 2000 turns): separates the economy from
   predation. A source that starves alone has nothing to defend.
2. **Duels** against one shipped source at a time, two seeds each.
3. **The full field** (every shipped source, ten seeds, 1000 turns):
   survival first, rank second. A source that dies by turn 500 did not
   play.

Run with `WESEN_STRICT=1` in the environment while developing: the
big shipped sources then crash on their own internal errors instead
of skipping the turn, and the fault counter printed at the end of a
tournament (`X faulted: N rule violations, M errors`) is the first
line to read - a source that raises every turn still produces a
scoreboard, it is just one where it did nothing. Two runs that come
back byte-identical after an edit mean the changed branch never fired.
Check the persistence round trip (`persist` → JSON → `restore` →
`persist`) once before calling a source done, and run the real GUI once.

`tools/profile_wesen.py` profiles a game; `tests/` has the engine's
tests, including determinism (`tests/determinism.py`), which is what
catches a random draw taken outside the seed.
