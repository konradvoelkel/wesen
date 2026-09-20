# Writing and running Wesen sources — compact guide

Read this first. `OVERVIEW.md` has project layout, history and results;
you only need this file to write an AI ("source").

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
`~/.wesen/conf` on first run; `-c FILE` plays from a different one
instead.

GUI keys (press `?` or `h` in the window for this list; right-click also
opens a menu):

| key | does |
|---|---|
| `space` | pause / run |
| `s` | one turn |
| `+` / `-` | faster / slower |
| `g` | **switch what the graph shows**: energy per source, population per source, both, the world, everything |
| `c` | save a screenshot as `wesen-<turn>.png` |
| `m` | movie mode: every frame to disk |
| `?` / `h` | show or hide the key list |
| `q` / `x` / `Esc` | save the game state and quit |
| arrows | add / delete / feed / starve food |

Each curve in the graph is scaled on its own unless the mode says the
curves share one scale, and the caption prints the current value of every
curve: without that, total energy and the food supply dwarf everything
else and the plot says nothing.

Config: INI file, default `~/.wesen/conf` (created from `src/Wesen/defaults.py`
on first run). `[wesen] sources = A,B,C` selects the sources; `-s A,B,C`
overrides it on the command line, `-c FILE` chooses another file. Each
source starts with `count` (5) wesen of `energy` (300) at random cells.

## 2. Where a source lives

A source is your own program and lives wherever you keep it. The game
looks in `~/.wesen/sources` first, then in any folder named by
`[wesen] sourcepath` (or `-p DIR` on the command line), and last among
the sources shipped in `src/Wesen/sources`. Two shapes work:

```
~/.wesen/sources/<Name>.py             # one file: what a first wesen is
~/.wesen/sources/<Name>/main.py        # a package, for code split over files
```

`<Name>` is the string used in the config, and the name of that file or
folder. Since your own folders are searched first, you can copy a shipped
source out of the tree, keep the name, and play your version against the
rest of the field.

Either shape must define a class called `WesenSource` subclassing
`DefaultWesenSource`. Both are checked when the game starts and said
plainly if they are missing, rather than failing halfway into a game.
Your source reaches the game through the installed package, so import it
absolutely:

```python
from Wesen.defaultwesensource import DefaultWesenSource
from Wesen.point import getDistInMaxMetric, getShortestTranslation  # optional
```

A source package may import its own modules the ordinary way
(`from . import helper`), as `Dwarf`, `Nightwatch` and `Rincewind` do.
The sources in `src/Wesen/sources/` are *inside* the game's package and
so use relative imports (`from ...defaultwesensource import ...`); that
form only works in there, and is the one thing to change when you copy
one out.

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
    def Receive(self, message):   ...   # Talk/Broadcast from other wesen (any object)
    def persist(self):            return {}          # JSON state for -r resume
    def restore(self, obj):       ...                # obj["wesensource"] is what persist returned
```

One instance per wesen; a child created by `Reproduce()` gets a fresh
instance and inherits nothing. Class attributes are *genes*, not a
notebook the colony shares: see section 3c.

## 3. The API (methods are injected into the instance by the engine)

Free, no time cost: `self.id()`, `self.age()`, `self.position()` (live
`[x, y]` list), `self.energy()`, `self.time()`.

Every turn, before `main()`: energy − upkeep, `time = min(time + 25, 50)`.
Upkeep is `[wesen] upkeep + upkeep_rate · energy` (1 + 0.005·energy by
default), so a 300-energy wesen burns 2.5 per turn and a 10 000-energy one
burns 51: **hoarding costs and colonies are self-limiting**. Read it with
`self.upkeepOf(energy)` rather than assuming 1.
Actions that cost time silently do nothing and return `False`/`[]` if
`time` is insufficient. Defaults from `defaults.py`:

| call | time | effect / return |
|---|---|---|
| `look()` | 1 | list of `{"position","type","id"}` within 24 cells (max metric), self excluded |
| `closerLook()` | 2 | same within 12 cells, plus `"energy","age","time","source"` (`"food"` for food) |
| `Move([dx, dy])` | 7·(\|dx\|+\|dy\|) | all-or-nothing; wraps around the torus; `True` if moved |
| `MoveToPosition([x, y])` | via Move, one cell per step (diagonal step = 14) | `True` if arrived; stops when time runs out |
| `Eat(id)` | 10 | food on own cell only; adds its energy; `True` on success |
| `Reproduce()` | 20 | child with `(energy − reproduce_cost) // 2` on same cell, own age reset to 0; returns child id or `False`; fails for free below `child_min_energy` |
| `Attack(id)` | 14 | wesen on own cell only; victim −int(`attack_damage`·mine), me −int(`attack_cost`·victim's previous energy); `True` if I survive |
| `Vomit(e)` | 12 | food with energy `e` on own cell (classic rule: growrate 1, seedrate 0.001, maxamount e+1000; life rule: ordinary food); `e > energy` KILLS you |
| `Donate(e, id)` | 13 | wesen on own cell; capped at own energy; donating everything kills you |
| `Talk(id, msg)` | 1 | `Receive(msg)` on that wesen if within 24 cells (fixed 2026-09-09, it used to raise `NameError`) |
| `Broadcast(msg)` | 1 | `Receive(msg)` on all wesen within 16 cells |

A dict message arrives carrying `msg["from"] = {"source", "id"}`, put
there by the engine and unforgeable — see section 3c.

`RuleException` (aborts only this wesen's turn, no other penalty yet):
`Eat`/`Attack` with an id that no longer exists, `Eat` on a different cell
or on a non-food. Any *other* exception crashes the whole game. So: call
`closerLook()` at the start of `main()` and only use ids from that call.

## 3b. The rules are not constants

Three engine features mean the numbers in this file are defaults, not
truths. A source that reads them from its info dicts adapts; a source with
hardcoded thresholds loses games it would otherwise win.

* **One seed per game.** `[world] seed` (0 draws one) seeds `random` and
  `numpy.random` before anything is built and is printed at startup and
  persisted, so any game replays exactly. Use the seeded generators.
* **Seasons** (`[climate]`, on by default): food growth is multiplied by
  a value that swings around 1 with `period` 400 turns and `amplitude`
  0.5. The calendar is fixed but the severity of each half-year is drawn
  at random (`severity_random` 0.3), so winter comes on schedule and its
  depth does not. Read it with `self.season()` (dict with `season`,
  `phase`, `growth`, `severity`, `period`), `self.growthFactor()`,
  `self.lean()` (growth below normal) and `self.turnsUntilSpring()`.
  The wesen themselves are unaffected: what changes is income, so store
  fat in autumn and do not split a body into winter.
* **Biomes** (`[biome]`, on by default): the ground is not uniform. A
  static fertility map, value noise built from the game seed with region
  size `scale` (80 cells) and `strength` 0.5, multiplies both how fast
  food grows at a cell and how much energy that cell can hold, and how
  readily a seed takes root there. So the best ground carries cells of
  150 energy and the worst only 50, and a region is worth migrating to
  and worth holding. Read it with `self.fertility()` for your own cell
  or `self.fertility([x, y])` for another; it is free, and constant for
  the whole game, so it is worth remembering. The GUI paints the map
  under the world in shades of green.
* **Per-game rule variation** (`[variation]`, off by default): with
  `enable = True` the time costs `move`/`eat`/`attack`/`vomit`/
  `reproduce`, the ranges, the food parameters `growrate`/`maxamount`/
  `bite`/`seedrate` and `upkeep_rate`/`reproduce_cost` are each
  multiplied by a factor drawn once per game from
  `uniform(1 ± spread)`. The varied values are what every source
  receives in `infoTime`, `infoRange`, `infoFood` and `infoWesen`, and
  they are printed at startup. Turn it on when developing, or you will
  hardcode the defaults without noticing.

Helpers on `DefaultWesenSource` for all of this: `fertility()`,
`season()`,
`growthFactor()`, `lean()`, `turnsUntilSpring()`, `attackDamage()`,
`attackCost()`, `upkeepOf(energy)`, `birthCost()`, `minBirthEnergy()`,
plus the food helpers listed in section 4.

## 3c. Class attributes are genes, not a shared brain

A source is one program played by many wesen, so anything it keeps on
its class is shared by all of them: one wesen writes a map into a class
attribute and every other wesen of that source reads it, wherever it
stands. Nothing in the world carried the fact from the one to the other.
That is telepathy, and it makes `Talk` and `Broadcast` pointless.

**The rule:** a class attribute is *genetic information* — the same for
every wesen of a source and for the whole game. What a wesen learns
belongs in the instance; what it wants another wesen to know has to be
said out loud.

`[wesen] shared_state` (see `src/Wesen/isolation.py`) decides how the
engine enforces it:

| value | effect |
|---|---|
| `isolate` (default) | the shared class keeps the genes, frozen; every wesen is built from a private subclass holding its own deep copy of every mutable class attribute. Writes through `self` or `cls` keep working and simply stop being shared; a write to the class *by name* (`WesenSource.map[k] = v`) raises `TypeError` |
| `strict` | the genes are frozen and nothing is copied: any attempt to keep state on the class fails, wherever it is written from |
| `allow` | the old behaviour |

In `isolate` and `strict` the engine also closes the two obvious ways
round the rule:

* **A message says truthfully who sent it.** A sigil is a constant in a
  file anybody can read and an id comes free with `closerLook`, so
  before 0.8 any wesen could say anything in another source's name —
  and a single forged word (`Broadcast({"s": "lutze/1", "u": 1})`)
  took a turn away from three of the four colonies here. The engine now
  stamps every dict message with the sender's real source and id, under
  the key `"from"`, written *last*, so a payload carrying a `"from"` of
  its own is simply overwritten. Read it with `self.sender(message)`
  (the note, or `None`) and `self.fromColleague(message)` (is this one
  of ours?) — and make `fromColleague` the first line of any `Receive`
  that reads a protocol of its own. What a wesen *says* may still be a
  lie: an enemy can tell you whatever it likes about food, danger or
  its own intentions, and weighing that is the game. Who is saying it
  is not up for negotiation.
* **A message is a value.** `Talk` and `Broadcast` seal the payload:
  dicts come out frozen (still `dict`, so `isinstance(message, dict)`
  and `message["k"]` work as anybody would write them — writing raises),
  lists come out as tuples, and anything that is not a plain value —
  `Broadcast({"me": self})` — arrives as `"<WesenSource>"`. A handle
  would be a shared brain with extra steps, and it would outlast the
  moment the two wesen were in range of each other.
* **The engine's dicts are not a letterbox.** `infoTime`, `infoRange`,
  `infoFood`, `infoWorld` (and the `climate` inside it) and `infoWesen`
  are shared by every wesen in the game, of every source. A source now
  gets a live read-only view of them: the season still updates under it,
  and writing raises.
* **A source package's module globals are genes as well.** They are
  shared exactly as class attributes are and there is no per-wesen copy
  to hand out (there is one module), so the mutable ones are frozen
  outright. Constant tables (`CHASERS = {...}`, `HARMLESS = {...}`)
  are what they are for and keep working; a module-level registry does
  not.

Rebinding a class attribute (`cls.table = {...}`) cannot be frozen away
— a name can always be pointed at something new — so `World` checks
every 50 turns and reports it once as a rule violation, counted in
`World.faults`.

What this costs, per wesen born: one `type()` call and a deep copy of
the source's *initial* mutable class attributes (which are empty
containers in every source here), so nothing measurable.

It is not airtight and is not meant to be — a source can still hide
state in its own module's globals. It makes the rule the default and the
violation loud.

**The sources in this repo were adapted to it** (2026-09-10). Vetinari,
Weatherwax and LuTze kept their colony's knowledge — pasture map, roll,
claims, estates, orders for newborns — in class attributes, and all
three now pass it around instead, through `src/Wesen/colony.py`: a
colony clock kept in step by talking, a roll of who has been heard
from, uids that need no shared counter (the engine id and the turn it
was issued), orders given by `Talk` in the turn a child is born, and
one broadcast a turn carrying whatever that source has just learned.

Two things had to change beyond the plumbing, and they are the general
lesson:

* **A population rule cannot be measured against a count of the whole
  colony.** Nobody ever hears the whole roll, so every wesen
  under-counts it and concludes on its own that there is room for one
  more. All three now measure the ground *they* keep instead:
  Weatherwax counts the map cells closer to its anchor than to any
  colleague's (`district`), Vetinari and LuTze count the colleagues
  whose home lies within `DISTRICT_RANGE` of their own
  (`roomForAnother`). A local rule needs no global knowledge and stops
  the colony growing where it is full while the empty ground fills.
* **An estimate extrapolated from neighbours needs a floor.** The first
  version of `Colony.census` scaled the local density of colleagues up
  to the whole world, which tells a wesen standing alone that the world
  is full; Weatherwax froze at five. It falls back to the plain count
  when there is nobody to extrapolate from.

`shared_state = allow` still reproduces the old, telepathic behaviour.

## 4. Rules that matter (engine behaviour, defaults)

* World 500×500 torus, for movement and for vision alike: a look window
  wraps around the edge, so a wesen standing on the seam sees the ground
  it is about to walk onto. (Before 0.8 the window was clamped at the
  edge and the seam was a blind spot.)
* Turn loop: all objects (wesen and food) act once, in creation order;
  objects created this turn act next turn. Other wesen do not act in the
  middle of your `main()`.
* Death: energy ≤ 0, or age > 1000 (then all energy becomes growing food
  on the cell). Killed in a fight → nothing left.
* Food, **life rule** (`[food] rule = life`, the default since 2026-09,
  see `objects/food.py`): 600 pieces of 50 energy at start, max 100 each.
  A cell's growth depends on the food density around it (energy within
  `range.seed` = 10 cells, divided by maxamount): fastest near density
  `fertile_peak` (1.0), decay beyond `fertile_width` (1.5) away from it.
  Growth is logistic in the cell's own energy (max `growrate` 0.3/turn at
  50). Seeds cost the parent `seedenergy` (5), take root only where the
  density is near `birth_peak`, and mature cells seed more. `Eat()` takes
  a bite of `bite` (30) energy and always leaves the last `seedenergy`
  (roots) - only a further bite on the bare cell kills it. Food dies at
  age 1000. Vomited food is ordinary food (planting, not free energy).
* Economics that follow: the pasture is the income. A bite that leaves a
  cell at ≥ 50 regrows fastest (maximum sustainable yield); stripping a
  cell to its roots leaves it almost without growth for hundreds of
  turns; killing it removes the income. Crowded gardens decay, so
  `Vomit(1)` plantations no longer work. Roaming grazers that spread out
  beat home-bound colonies, and clear-cutters crash the commons for
  everybody. `DefaultWesenSource` has rule-aware helpers:
  `foodYield(o)`, `foodKills(o)`, `foodSustainable(o)`, `foodRipe(o)`,
  `foodWanted(o, hungry, starving)`, `plantEnergy()` - see
  `defaultwesensource.py`. Tune the numbers headless with
  `wesen-tournament`, or with more knobs by the untracked
  `local/food_tuning.py` described at the end of this file
  (`--climate`, `--biome`, `--wesen`, `--no-climate`, `--variation
  0.2`); its `rich/poor` column is the food energy per cell on the best
  third of the ground against the worst third.
* Food, **classic rule** (`rule = classic`): `Grow` adds
  `int(uniform(0,2)·growrate)` per turn (growrate 0.2 → normal food
  never grows); vomited food grows ~0.5/turn regardless of size, dies at
  age 1000 leaving nothing. Seeds (energy 1) appear with prob. seedrate
  per turn within 10 cells if < 11 food are nearby. `Vomit(1)` = 1 energy
  + 12 time → +0.5 energy per turn for ≤ 1000 turns, so time is the
  bottleneck. Any number of objects may share a cell; a seed landing on
  food merges it. Score shown in the GUI graph = summed energy of living
  wesen per source (patches don't count until eaten).
* Food, **life rule**: a cell only seeds once it has grown to
  `birth_maturity` (0.9) of its own capacity, and a seed starts at
  `seedenergy` and grows slowly. That is what decides how long the
  pasture takes to cover the world — about 2000 turns with the defaults
  against 500 without the gate — while the density rules alone decide how
  dense it ends up. A heavily grazed cell never reaches maturity, so
  grazing suppresses the spread of the pasture around it.
* **Your code has a time limit of its own.** `time` budgets what a wesen
  may *do* in a turn; `[wesen] cpu_budget` (0.5 s, 0 switches it off)
  budgets how long its code may take to decide. Go over it and the turn
  is cut short by a `RuleException` raised wherever you happened to be,
  and counted like any other rule violation — the game plays on without
  you that turn. It is loose on purpose: measured over 18 000 turns of
  the full field, the median wesen thinks for 0.6 ms, the 99th
  percentile is 7.6 ms and the slowest turn seen was 49 ms (Rincewind).
  So it breaks a hang rather than shaving a strategy; a tournament may
  set it tighter. Two consequences: catching the interrupt buys nothing
  (the timer repeats until the turn really ends), and a game in which
  the budget actually fires no longer replays exactly, because where
  the cut falls depends on the machine. Unix only — see `budget.py`.
* A source that raises an exception no longer ends the game: the turn is
  skipped and counted in `World.faults`, and each distinct error is
  printed once with its traceback. Rule violations are counted apart from
  bugs. This is a safety net, not a licence: a source that throws every
  turn simply does nothing.
* Fights: attacker with A hitting V: V loses 0.75A, A loses 0.5V. Kill
  condition 0.75A ≥ V; attacking someone with V > 2A kills the attacker.
  Being fat is the best defence; first strike wins even fights.
* Existing sources attack you when your energy ≤ theirs + 300..375
  (Dwarf, Nightwatch) and eat any food they see (all of them).
  Rincewind kills a cheap thief standing on its own cell since its
  2026-09-09 rewrite (section 6c), so the "harmless" table in
  Weatherwax is out of date about it.
* `Talk` and `Broadcast` cost 1 time each, the same as a seventh of a
  step, and the message is any Python object: the channel is by far the
  cheapest thing in the game and, until Rincewind, nothing used it.
  `Broadcast` reaches every wesen within `range.talk`, including
  enemies, so a message is public; `Talk` reaches one wesen within
  `range.look`. A message is delivered inside the sender's turn, so a
  child can be briefed in the turn it is born.
* **Herding** is what the big sources do under the life rule
  (`grazerTurn` in Vetinari and LuTze; Weatherwax has its own map-based
  version, section 6): bite a cell only
  while it keeps about a third of `maxamount` (free income, since it
  regrows fastest there), strip cells further only below the winter
  reserve, kill a cell only when starving, and walk to the best cell in
  view rather than sitting on an estate. The estate follows the herd, so
  their scouts, bogeymen and hunters keep working unchanged. When they
  found a new estate they pick the most fertile of a few directions.
* Simulation cost: every food object costs ~14 µs per turn, and every
  `closerLook()` costs ~1 µs per object in range. Thousands of patches ×
  dozens of wesen makes the GUI crawl — cap your colony (Vetinari: 32
  wesen, ≤ 1600 patches ≈ 25 turns/s headless).

## 5. Reference implementation

`src/Wesen/sources/Vetinari/main.py` (445 lines, documented) beat every
older source by 10–30× (until Weatherwax, sections 6-7). Read its module docstring and the `main()`
method for a working pattern: per-turn `closerLook`, threat handling,
garden cell, reproduction under a population cap, persistence, class-level
shared state (world-turn estimate, alive registry, claimed targets).

`src/Wesen/sources/example.py` is the minimal template; `Dwarf` is the
best of the older sources; `Manual` is an interactive console AI.

## 6. Weatherwax (2026-09 rewrite): a herding colony on a shared map

> Written before the shared-state rule (section 3c). Its "shared map" is
> a class attribute, so under the default `[wesen] shared_state =
> isolate` every wesen keeps its own copy and the colony stops being one
> mind. It runs, and it is weaker; `allow` restores what is described
> here.

`src/Wesen/sources/Weatherwax/main.py` (~1000 lines, module docstring has
the reasoning) is the reference for the life food rule. It replaced the
2026-09-07 exploit-driven version (bogeymen against Vetinari, statues
against Dwarf): under upkeep and the lean early game that colony starved
on its own by turn ~700, because its herding rule refused any cell under
65 energy and oscillated between distant cells without eating, and its
war machinery needed a colony of 16 that never came.

* **Shared pasture map.** Every wesen writes each `closerLook()` (exact
  energies) and `look()` (positions only) into a class-level map keyed by
  24-cell tile; cells that vanish from a look are deleted. The current
  energy of a remembered cell is estimated from the last sighting plus
  `growrate x 0.5 x fertility` per turn, so a wesen plans for cells out
  of sight and comes back when a bitten cell has regrown.
* **Target choice = energy per time.** Each turn the wesen walks to the
  cell maximising `bites x bite / (eat time + walk time)` within 60
  manhattan cells (one claim per cell for 12 turns), and bites on
  arrival. What a bite may take depends on the body: at or above the
  reserve (300, plus the upkeep to spring, at most 600) only bites that
  leave the cell at 20 % of its capacity; below it, bites down to the
  roots; below 90 energy anything at all.
* **Seeders.** Food only seeds once it has grown to `birth_maturity`
  (90 %) of its capacity and every cell dies at `maxage`: a pasture
  grazed everywhere below maturity never spreads and ages out (that
  collapsed the colony after turn 1200 in the first draft). One cell in
  three, chosen by position, is never bitten unless the wesen is
  starving or the cell holds a body.
* **Exploration by fertility.** The terrain is free to read, so the
  colony samples every tile once and a wesen without a target walks to
  the fertile tile that is longest unseen and nearest, looking on the
  way. Plants a seed (`Vomit`) with spare time and energy where the
  ground is fertile and the neighbourhood density lets it grow.
* **Population follows the ground this wesen keeps** (`district`,
  2026-09-10): the known cells within `DISTRICT_RANGE` of its anchor
  that are closer to that anchor than to any colleague's. It splits
  while that holds `CELLS_PER_WESEN` cells, or while no colleague is
  near it at all (the frontier), with the estimated colony size only as
  a ceiling. The rule it replaced counted the whole colony against the
  whole map, and since nobody can hear the whole colony every wesen
  under-counted it and concluded on its own that there was room for one
  more: it ran to 85 wesen where it used to hold 40. A local rule needs
  no global knowledge - the district shrinks as colleagues settle
  around it - and it stops the colony growing *in the places that are
  full* while the empty ground is still filling. A child is sent to a
  free site at least 16 cells from every other anchor, so the herd
  spreads instead of trampling one cluster. Old age is cured by
  reproducing.
* **Who attacks whom** is read from the opponents' code: Nightwatch and
  Dwarf strike up to their own energy plus 375/300 once above 375/301,
  Vetinari only on its own cell when it kills, GreatRabbit and Rincewind
  never, everything else (LuTze, future sources) whatever it can kill
  within a few cells. The wesen first eats itself out of reach if the
  cell allows it, else flees with its whole time budget along the line
  ending farthest from all threats (so a pursuer cannot time a fixed
  3-cell hop). Thieves on the own cell are killed when the kill costs at
  most 100 energy and 12 % of the body.

* **Old age over target is cured without growth:** the parent splits
  (which resets its age), stays put two turns, and the child gives
  everything back and vanishes. Without this the colony doubled every
  1000 turns whatever the pasture said, overshot to 70 wesen and lost
  half its energy between turns 3000 and 4000.

Results (full default roster, ranking by energy): wins seeds 1-8 of the
2000-turn game every time, typically 10-16k energy with 15-26 wesen
against 0.2-3.4k for the runner-up (Nightwatch or Vetinari; seeds 2 and
8 are the closest). Over 4000 turns (seed 1) it is the only survivor
with 24 wesen and 15k while the pasture is still growing (2500 cells).
Alone it reaches ~33 wesen and 20k by turn 2000. Also wins with
`[variation] enable = True` and with `[food] count = 1200`.

## 6b. Counter-counter-strategy: LuTze

> Same caveat as section 6: its estate registries, orders and claims are
> class attributes and are isolated per wesen under the default rule.

`src/Wesen/sources/LuTze/main.py` beats Weatherwax, Vetinari and the rest
in the same game (module docstring has the reasoning):

* **Bootstrap first, war second.** Each founder splits into 8 gardeners
  of ~37 energy on turn 3; a `Vomit(1)` patch pays for itself in two
  turns, so the five founder cells hold the whole budget (`PATCH_BUDGET`
  3000 patches, 600 per cell) by turn ~60 instead of turn ~500. Income
  (0.5 x patches per turn) is the same as for any gardening source at
  equal budget; what differs is *when* it starts and how many wesen are
  free for other work (four gardeners per cell suffice).
* **Scouts** sweep the map on a tile grid (`TILE` 48, one `look()` per
  tile), register enemy home cells (piles with a Vetinari or Weatherwax
  on them) and roaming enemies, and keep patrolling afterwards.
* **Hunters** take a target the home cell can pay for (bodies above a
  floor plus harvestable patches), pool it in a few turns and go. On a
  Vetinari or Weatherwax cell a hunter with 1.4 x the fattest resident is
  lethal to all of them, so they flee 3 cells and walk back forever
  (paralysed, no gardening, no reproduction). The hunter kills them one
  by one: step next to the resident, it flees exactly 3 cells along one
  axis, walk 4 and strike (`chase()`); the time budget converges because
  a 3-cell move costs 21 of the 25 time a turn brings. Dwarf, Nightwatch,
  rabbits and Rincewind do not flee and are struck when cheap. Stationed
  hunters split children for neighbouring estates, strip the gardens of
  dead estates (they would feed a Nightwatch or rabbit boom) and eat the
  bodies of residents that died of old age.
* **Population** (2026-09-10): a gardener splits while fewer than
  `WESEN_PER_DISTRICT` colleagues keep house within `DISTRICT_RANGE` of
  its own cell (`roomForAnother`), instead of counting the whole colony
  against `MAX_COLONY` — see section 3c. `MAX_COLONY` remains as a
  ceiling for the machine. Its estate registry deliberately does *not*
  travel between wesen: an estate record has a dozen fields the rest of
  the code reads, and a partial one from a message is worse than none,
  so each hunter works from what it has seen itself. That is the part
  of LuTze most weakened by the shared-state rule.
* **Home defence:** anything on a treasury that can be killed for at most
  `KILL_MAX` (or 2.5 % of the colony's wealth) is killed; bodies stay
  above what Dwarf/Nightwatch attack; a cell camped by an eater it
  cannot kill relocates 30 cells away.

## 6c. Rincewind (2026-09 rewrite): the colony that talks

`src/Wesen/sources/Rincewind/` (`main.py`, `ledger.py`, `plan.py`; the
module docstring has the reasoning). Every other source plays solitaire
and keeps whatever colony-wide knowledge it has in class attributes,
which is telepathy — and, since 2026-09-09, against the rules
(section 3c). Rincewind is the only source that uses `Talk`,
`Broadcast` and `Receive` at all, and it keeps **no class-level state at
all**, not even a cache or a debug counter: a fact reaches another wesen
only if somebody paid a message for it. It therefore plays the same
under `isolate`, `strict` and `allow`.

* **Gossip.** Each wesen keeps a ledger of food cells (energy, when
  seen, when bitten, who reserved it), colleagues (position, energy,
  home, role), threats and swept tiles, and broadcasts a delta of what
  it learned once a turn (1 time, 16 cells). Incoming messages are
  merged key by key, newest timestamp wins; the colony's calendar is
  the highest clock anybody quotes; the roll of colleagues is relayed,
  so a wesen at the edge can still count the colony. A wesen out of
  everybody's range goes blind until it walks back into the network.
* **Districts without negotiation.** Homes are published, so every
  wesen can draw the same Voronoi partition and knows which cells are
  its own. A home drifts towards the cells its keeper actually
  harvests (Lloyd relaxation), so the partition follows the pasture.
  A cell is reserved in the ledger before the walk to it starts, and
  the reservation rides on the next broadcast: that is the whole of the
  "two wesen walk to the same cell" problem, for 1 time.
* **The harvest rule.** A fed wesen leaves a third of a cell's capacity
  standing and never touches one cell in four (a hash of the position,
  so the colony agrees for free), because food seeds only above
  `birth_maturity` and a pasture grazed below it ages out. Where the
  alarms say a rival grazes, both rules drop to what a hungry wesen
  takes: interest left standing on contested ground is a gift to
  somebody else. A report loses 1.5 % of its worth per turn of age, so
  a colleague's news from three turns ago beats one's own memory of
  forty - which is what makes the network pay.
* **Population.** A wesen splits while its district holds more known
  cells than one wesen can work (`CELLS_PER_WESEN`, bounded by
  `HOME_RADIUS` so that ignorance of the neighbours cannot be read as
  owning the world), and never with two colleagues within twelve cells.
  The child is briefed by `Talk` at birth - uid, calendar, a district
  of its own and a copy of the map, the only inheritance this engine
  allows. A district that has been eaten bare is abandoned for ground
  the colony knows is free.
* **Alarms.** Every stranger seen is broadcast. An alarm travels 16
  cells a turn while a hunter walks three, so the colony usually knows
  about a killer before it arrives; cells near one are worth less,
  flight uses the whole time budget in a direction chosen at run time,
  and a cheap thief on the own cell is killed.

Measured (full default roster, 2000 turns, ranking by energy; seeds 1,
3 and 5):

| | seed 1 | seed 3 | seed 5 |
|---|---|---|---|
| Rincewind | 40011 (336) | 64047 (407) | 38498 (348) |
| Weatherwax (runner-up) | 20463 (39) | 21993 (39) | 17886 (39) |
| the old Rincewind, same seeds | 247 (2) | 145 (1) | 0 (0) |

It wins every seed by two to three times. The population figures are the
warning: that measurement was taken with the growth rules described
above but *before* the two leaks below were closed, and the score peaks
around turn 1000-1500 (90-118k) and then falls, because a colony of 350
eats the pasture from 4800 cells down to 2100 - and 350 wesen run the
game at 0.3 turns/s, which is no use in the GUI.

* **Old age bypassed every population gate.** Splitting resets the age,
  so a wesen at `maxage` splits whatever the pasture says; with a few
  hundred wesen that alone adds a quarter of a birth per turn forever.
  Now a wesen that may not split dies - and spends its last turn
  turning itself into food on its own ground (`bequeath`), since death
  by old age drops a blob only when there is vomit time left over.
* **A colony cap cannot be read off the census**, because no wesen ever
  hears the whole roll: the census stayed near 12 while the colony was
  400. It is estimated instead from the *density* of known homes around
  one home times the area of the world (`colonySize`), and growth also
  stops while a wesen's own district is shrinking against its own slow
  average (`shrinking`) - which is the ecological feedback the swarms
  in this game all lack.

Engine bug found and fixed for it: **`Talk` never worked**. Its range
filter closed over the loop variables of the loop it was filtering, so
it raised `NameError` as soon as anything at all was within 24 cells -
which is why no source had ever sent a message. One line in
`objects/wesen.py`, plus three tests in `tests/rules.py`.

## 7. Lessons from writing the first Weatherwax (engine facts and pitfalls)

The gardening/bogeyman Weatherwax described here was replaced in the
2026-09 rewrite (section 6); the engine facts still hold.

Engine facts verified while building the counter-strategy:

* **Old-age death drops a blob only if the wesen has ≥ 12 time left**
  (`Die` calls `Vomit`, which needs the vomit time). A wesen that spends
  its time every turn dies leaving nothing; an idle one leaves its whole
  body as food with growrate 1, maxage 1000. Energy death leaves nothing.
* **Fights are a 1:1 energy exchange at best** (attacker loses 0.5 V,
  victim 0.75 A, kills yield nothing), so killing only pays when the
  victim is far cheaper than what it would otherwise take from you
  (a 100-energy rabbit eating your patches: yes; a 20k Vetinari: no).
  Paralysing an enemy that then dies of old age is free and yields its body.
* **Under a patch cap, harvest frequency does not change income**: growth
  is 0.5/turn per living patch whatever its size. Harvest early for body
  score, safety and to keep patches younger than Dwarf's threshold (50);
  eat + replant in the same turn (22 time) keeps the count at the cap.
* Vetinari and Dwarf both act on the energies they *see* at the start of
  their turn; there is no deception except making the numbers true (pool
  energy with `Donate`, split with `Reproduce`).
* An enemy that steps onto your cell cannot attack in the same turn it
  arrived (all existing sources `return` after moving), so you always get
  one turn to leave. Vetinari only ever attacks on its own cell; Dwarf and
  Nightwatch chase targets but only if they are within their thresholds.
* `closerLook()` returns `[]` both when nothing is in range and when time
  is short; ids from it are valid for the rest of your turn only.
  `Donate` to an id that died raises `KeyError` (crashes the game, not a
  `RuleException`): check the target is in this turn's view first.
* Per-source stats can show negative energy for one interval (an attacker
  that lost more than it had and died inside its own turn). Harmless.

Pitfalls that cost real games during development:

* **Thin thieves matter more than fighters.** GreatRabbit swarms (hundreds
  of ~100-energy wesen) walk to the nearest food and eat fresh 1-energy
  patches; ignoring "harmless" enemies below the fight threshold halved
  the colony's income. Kill anything cheap that stands on your garden.
* **Reproduction thresholds must not chase one fat enemy.** Sizing the
  reserve to "strongest aggressor + 450" stalled the colony at 5 wesen for
  400 turns. Size it to survive one hit (0.75 × attacker) and cap the
  remembered threat; handle a real monster locally (fatten/flee/kill).
* **Children with special roles need to be born outside the population
  cap**, otherwise a full colony never produces scouts or bogeymen.
* **Pooling energy per cell is too slow** against an enemy whose bodies
  grow 25/turn each; the recruit has to tour several home cells (or the
  colony needs couriers). The class-level energy ledger is what makes
  "can we afford it" decidable.
* Dispatch counter-measures as early as possible: the needed bogeyman
  energy is 1.5 × the fattest resident, which is 3k at turn 300 and 30k
  at turn 1200. Estates found late may never be affordable; the second
  wave then comes from bogeymen that grew on eaten bodies and merged.
* One stuck wesen costs nothing but hides a loop: a scout oscillated for
  600 turns between "approach the pile" and "flee the resident". Give
  every pursuit a timeout and print role/state per interval
  (`local/probe_ww.py`) rather than only totals.

Workflow that worked: read the opponents' `main.py`/`helper.py` line by
line and write the exploit thresholds as named constants; run headless
with `WESEN_STRICT=1` (so bugs crash instead of being skipped); keep a
probe script that prints per-role counts, shared registries and the
opponent's "at home" count every 100 turns; run 2–3 seeds in parallel in
the background (5–10 turns/s each); check the persistence round trip and
run the real GUI once (`local/gui_check.py`) before calling it done.

## 7b. Lessons from writing LuTze

* **Engine ids are memory addresses and get reused.** A registry keyed
  by `id()` (alive table, "this estate has a hunter", tile claims) can
  point at a *new* object after the old one died; the symptom was an
  enemy estate that never got a hunter again. Number your own wesen with
  a class-level counter and key registries by that; keep the engine id
  only for `Donate`/`Talk`/`Attack`, and only from this turn's view.
* **Thin gardeners must not flee from eaters.** Nightwatch below 375 and
  Dwarf at or below 300 only hunt food; a 300 Nightwatch that eats fresh
  1-energy patches (lowest energy first) is harmless to a wesen but
  fatal to a garden whose 30-energy gardeners run away from it. Model
  *who attacks whom* per source, and relocate when an unkillable eater
  camps on the cell.
* **Early scouts starve the bootstrap.** Sending provisioned scouts at
  turn 15 delayed the full budget from turn 60 to turn 100 and the
  scouts died anyway. Scout after the cell is full; a scout that never
  turns back explores three times as much per energy as one that walks
  home to refuel (all its findings are in the shared registry).
* **Estimate needs per source.** Vetinari's colony stops reproducing when
  it has seen a strong enemy (threshold 3.2 x the enemy) and puts all
  income into bodies, ~25 per turn per wesen; Weatherwax caps its
  threshold and stays thin. Financing a "kill everybody" squad against
  fat late residents is unaffordable: finance a paralyser (1.4 x the
  fattest) plus two kills and take the bodies at old age instead.
* **Abandoned gardens keep growing.** 200 patches of a dead estate are
  100 energy per turn of free food; a Nightwatch that finds them splits
  every 500 energy (62 of them in one run). Strip gardens completely
  (even 1-energy patches) or they come back as a swarm.
* **Dispatch from the nearest cell.** Without a nearest-cell rule, a cell
  claims targets 300 cells away and 40 % of the colony's energy walks
  around the map for 100 turns.
* A full-field game with LuTze runs at ~20 turns/s over 2000 turns
  (versus 6-10 with Weatherwax), because the other colonies are gone by
  turn ~400 and never build their gardens and swarms.

## 7c. Lessons from the Weatherwax rewrite

* **Measure alone first.** The colony died in full games, but it also
  died alone: `--sources Weatherwax` separates economy from predation in
  a minute. Under the current rules everybody hovers at 5 wesen for
  hundreds of turns; the winner is whoever wastes least.
* **A wesen that refuses food it can see starves.** Any threshold on
  what to walk to must fall back to "anything I may eat" before the body
  runs low; and idling wastes the turn's 25 time, so an idle wesen
  should explore (the map brings it back when its cells have regrown).
* **The pasture is the pie.** Grazing every cell below maturity stops
  seeding, and cells die at `maxage`: food fell from 1170 to 680 cells
  in one 2000-turn game and the colony with it. Leave seeders.
* **Population control has three leaks:** old-age births (cure with a
  sacrifice child), several parents splitting in the same turn against
  the same population count (count the child at birth), and a
  population target that follows the map while the map lags the world.
  Check `ours` against `target` in the probe over 4000 turns, not 2000.
* **Do not shadow the base class.** `self.attackCost = infoTime[...]`
  hid `DefaultWesenSource.attackCost()`; the turn was silently skipped
  (only `WESEN_STRICT=1` or the fault counter shows it).
* Dwarf's action loop spun forever on seed 2 (a scan vector that rounds
  to no move costs no time); it now breaks when an iteration used none.
* Turn time with ~35 wesen is ~100 ms, two thirds of it the engine's
  range scan for `look()`/`closerLook()` and food growth; the map code
  is ~20 ms. `look()` is therefore taken every turn only on the move.

## 8. Scoring, and dev tools

`wesen-tournament` (`src/Wesen/tournament.py`) plays sources against each
other headless and reports three numbers per source, because the one the
GUI graph shows — energy held at the final turn — rewards whoever happens
to be breeding when the game is stopped:

| column | is |
|---|---|
| `mean` | the area under the energy curve divided by the length of the game: what the source held *on average*. This is what the ranking uses. |
| `energy` | energy at the last turn — the old score. Printed as a second ranking whenever it disagrees with the first, since the disagreement is the interesting part. |
| `alive` | share of the game the source had at least one wesen. |
| `cpu` | share of the real time spent running source code. In-game `time` budgets what a wesen may *do*, not what its code costs to work out; `[wesen] cpu_budget` caps the latter per turn (section 4), and this column is how you see who is spending it. It is usually the answer to why a game crawls. |

`--seeds 1,2,3` plays each seed and averages, with a `wins` column, so
one lucky game cannot decide a match. `--json FILE` writes it all out.
`-c FILE` uses a config file (the same one `wesen -c FILE` opens in the
GUI); without one the game's own defaults are used. `-p DIR` and
`-s A,B,C` work as they do for `wesen`.

Non-versioned scripts in `local/`:

* `profile_run.py TURNS SOURCES` — cProfile of the last 50 turns.
* `persist_check.py` — persist→restore→persist round trip incl. a source.
* `gui_check.py TURNS OUT.png` — runs the real GUI unattended, screenshot, exit.
* `debug_colony.py` — Vetinari-specific registry check.
* `probe.py` — per-source energy distribution and Vetinari estate gardens
  over time; `probe_ww.py` — Weatherwax energy distribution, modes, known
  pasture, exploration progress and debug counters per interval; `probe_lt.py` — LuTze roles, home cells, estate registry and
  debug counters (`PROBE_HOMES=1` adds per-cell detail);
  `probe_rw.py` — Rincewind roles, ledger sizes and the counters that say
  where its turns actually go (bites, steps, target distance, empty
  arrivals, hungry turns);
  `probe_field.py` — growth of every source (count, sum, max, cells).
* `persist_lt.py` / `persist_diff.py` / `persist_rw.py` — round trip with
  LuTze or Rincewind in the world, and a per-object diff when it is not
  equal. A source's `restore(obj)` gets the *whole* persisted object:
  its own state is `obj["wesensource"]`.
* `debug_cell.py` — turn-by-turn view of one LuTze founder cell.
