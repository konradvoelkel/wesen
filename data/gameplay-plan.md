# Gameplay plan: seasons, randomness, and a sturdier economy

Status: 2026-09-08. Builds on the life food rule (`food.rule = life`) and
the adapted sources.

**Phases 0 to 3 and phase 6 are implemented** (game seed, metabolism
scaling and reproduction cost, seasons, per-game rule variation, and the
biome fertility map), together with the herding rewrite of Vetinari,
Weatherwax and LuTze that they made necessary. Phases 4, 5, 7 and 8 are
still proposals. See the notes at the end of
each implemented phase for what actually landed.

## Goals

1. Make the economy self-limiting: no population explosions, no free hoarding.
2. Add periodic, partly random variation (seasons) so planning and storage matter.
3. Randomize rules per game so sources must read the config instead of
   hardcoding numbers or exploiting exact behaviour of other sources.
4. Keep games reproducible (seed), persistable (resume), and visible (GUI).

Guiding rule: randomize the *rules*, not the *dice*. Parameter variation
rewards adaptable code; outcome noise only adds variance.

## Phases and order

| # | Phase | Size | Status |
|---|-------|------|------------|
| 0 | Groundwork: game seed, rules dict, tests | S | done |
| 1 | Metabolism scaling and reproduction cost | S | done |
| 2 | Seasons (climate) | M | done |
| 3 | Per-game parameter variation | S | done |
| 4 | Inheritance (parent to child payload) | S | - |
| 5 | Corpse decay | S | - |
| 6 | Biomes (fertility map) | M | done |
| 7 | Shocks (blight, plague) | S | 2, 6 |
| 8 | Markers (stigmergy), scoring | L | - |

S: under two hours. M: half a day. L: a day or more. Phases 1 to 3 change
the balance the most and should land first, with a tuning pass after each.

## Phase 0: groundwork

**Game seed.** New option `[world] seed = 0` (0 means draw one). `Wesend.__init__`
seeds `random` and `numpy.random` before the world is built and prints the seed.
The effective seed is stored in the world persist dict so a resumed game keeps it.
The local scripts already accept `--seed`; route them through the same option.

**Rules dict.** Sources get their parameters through `infoAllSource`
(`time`, `range`, `wesen`, `food`, `world`). Keep that, but document it as the
only legitimate source of numbers. Add the new sections (`climate`, `variation`,
`biome`, `events`) to `CONFIG_OPTIONS` in `defaults.py`, explanations in
`strings.py`. `ConfigEd` already falls back to defaults for missing keys and
sections, so old config files keep working.

**Tests.** `tests/persistence.py` is the only test. Add `tests/rules.py` with
unit tests for every formula introduced below, and extend the persistence
round-trip with the new world state (climate, biome seed, corpses).

## Phase 1: metabolism scaling and reproduction cost

**Problem.** Upkeep is one energy per turn while a bite yields 30, so any
source that reproduces whenever fed grows to the carrying capacity (Nightwatch
reaches 900 wesen) and fat bodies cost nothing to hold.

**Design.** In `Wesen.main`, replace `self.energy -= 1` with

    upkeep = base + rate * energy          # stochastic rounding to int

Config `[wesen] upkeep = 1`, `upkeep_rate = 0.005`. A 300-energy wesen pays
2.5 per turn, a 3000-energy one 16, a 20000-energy one 101. Holding energy
becomes a cost, so hoarding and swarming are both limited.

Reproduction: `[wesen] reproduce_cost = 20` (destroyed on split) and
`child_min_energy = 60` (Reproduce returns False below it). Optional later:
`maturity = 20` turns during which a child gets half the time per turn.

**Touch points.** `objects/wesen.py` (`main`, `Reproduce`), `defaults.py`,
`strings.py`, `SOURCES.md` table. Stats: add `upkeep` to the per-source stats so
the GUI graph can show burn versus income.

**Tuning targets** (`local/food_tuning.py`): Nightwatch alone levels off below
300 wesen; all seven sources, at least four alive at turn 3000 in two of three
seeds; turn time under 60 ms at the population plateau.

**Source adaptation.** Vetinari, Weatherwax and LuTze keep large bodies
(`SAFE_BASE`, `KEEP_BASE`); lower those under the new rule via their existing
`tuneForFoodRule` hooks, reading `upkeep_rate` from `infoWesen`.

## Phase 2: seasons

**Design.** A `Climate` object (new module `src/Wesen/climate.py`) owned by
`World`, stepped once per turn in `World.main` before `updateFoodField`:

    phase   = (turn + offset) / period
    season  = spring | summer | autumn | winter   (quarters of the cycle)
    growth  = 1 + amplitude * severity[current half] * sin(2 pi phase)
    seeding = growth clipped to [0, 2]

Config `[climate]`: `enable = True`, `period = 400`, `amplitude = 0.6`,
`severity_random = 0.3`, `random_phase = True`. At every zero crossing a new
severity is drawn: `uniform(1 - severity_random, 1 + severity_random)`, so
winters differ but the calendar is predictable. A period of 400 gives each
wesen (maxage 1000) two or three seasons.

**Effects.** Food growth (`Food._lifeGrow`, and `Food.Grow` for the classic
rule) is multiplied by `growth`; `_lifeSeed` multiplies `seedrate` by `seeding`.
In deep winter (growth below 0.5) decay applies at half the usual density, so
overcrowded stands thin out. No effect on wesen directly; the storage economy
comes from the food curve alone.

**Plumbing.** The climate state lives as a dict in `infoAllWorld["world"]["climate"]`,
updated in place, like `foodfield`. Food objects read it through
`self.infoWorld`. Sources get it for free: `Wesen.__init__` makes a shallow
copy of the world dict, so the nested climate dict is shared and always live.
Document `self.infoWorld["climate"]` with keys `season`, `phase`, `growth`,
`severity`. Persist `offset`, the current severities and the cycle index in
`World.persist` and restore them.

**GUI.** A sensor in `gui/graph.py` for the growth multiplier (it needs its own
accessor, the stats dict expects `energy` and `count` per entry). The text
overlay shows the season name; optionally tint the background by season.

**Tests.** Periodicity, bounds of `growth`, severity within range, persistence
round-trip. Tuning targets without wesen: food never goes extinct, winter
trough at least 20 percent of the summer peak, no runaway in summer (cells
under 6000). With sources: the same survival target as phase 1.

**Source adaptation.** One helper in `DefaultWesenSource`: `season()` returning
the climate dict. Grazers should store fat in autumn and hold reproduction in
winter; add that to GreatRabbit, Nightwatch and Rincewind as a demonstration.

## Phase 3: per-game parameter variation

**Design.** `[variation] enable = True`, `spread = 0.2`. In `Wesend.__init__`,
after the seed and before the world is built, multiply each parameter on a
whitelist by `uniform(1 - spread, 1 + spread)` (ints rounded, minimum 1):
time costs (`move`, `eat`, `attack`, `vomit`, `reproduce`), ranges
(`look`, `closer_look`, `talk`, `seed`), food (`growrate`, `maxamount`,
`bite`, `seedrate`), wesen (`upkeep_rate`, `reproduce_cost`). Print the
effective values with the seed. The world persist dict already stores the
effective sections, so resume works unchanged.

**Why this shape.** The variation is visible to every source through the info
dicts it already receives. Code that reads the rules adapts; code with
hardcoded 300s or 375s, or exploits built on another source's exact constants,
degrades gracefully instead of failing outright.

**Source adaptation.** Replace hardcoded numbers with config reads where they
represent rules: Dwarf and Nightwatch thresholds, Weatherwax and LuTze
`AGGRESSOR_*` and `CHASERS` tables, the `0.75` and `0.5` attack factors (expose
them as `[wesen] attack_damage = 0.75`, `attack_cost = 0.5` while at it).

## Phase 4: inheritance

**Design.** `Reproduce(payload=None)`: a JSON-serializable dict, capped at
4 KB, handed to the child. `Wesen.Reproduce` puts it into the child's
`infoWesen["inherited"]`; `Wesen.__init__` copies it into
`infoAllSource["source"]["inherited"]`. `DefaultWesenSource` exposes
`self.inherited` (empty dict by default).

**Why.** Children start with a fresh instance and no state; Weatherwax and
LuTze work around this with class-level order books keyed by child id.
A payload enables lineages, roles at birth, and evolutionary strategies inside
one source without shared class state. No engine balance impact.

## Phase 5: corpse decay

**Design.** Under the life rule a dead wesen's body becomes food with
`maxamount = energy` (static). Mark such blobs `corpse = True` and let them
lose `corpse_decay` (default 0.01, half-life about 70 turns) of their energy
per turn while above the global maxamount, then follow the normal rules.
Persist the flag. A kill or a body becomes a time-limited prize instead of a
permanent bank.

## Phase 6: biomes

**Design.** `[biome] enable = True`, `scale = 80`, `strength = 0.5`. A
fertility map `F(x, y)` in `[1 - strength, 1 + strength]` from value noise:
a coarse random grid (world length / scale) upsampled bilinearly with numpy,
generated from the game seed (persist only the seed). Food growth is
multiplied by `F` at the cell; seeding uses `F` at the target. Optional
season coupling: phase offset proportional to `y`, so winter moves across
the map.

**Plumbing.** `World.fertility` ndarray, exposed as
`infoAllWorld["world"]["fertility"]` (Food reads it next to `foodfield`).
Sources get a free `fertility()` call for their own cell. GUI: draw the map as
a background tint in `basicgui.py` (cache as a texture or coarse quads).

**Tuning.** Fertile regions become territories: check that food does not go
extinct in the poor regions and that the rich ones do not saturate the cell
count.

### What phase 6 actually landed

`src/Wesen/biome.py` builds the map as two octaves of value noise: a
coarse random grid drawn from the game seed, smoothstep-interpolated over
the world with wrap-around, so the terrain is seamless on the torus and
identical every time the same seed is played. Nothing but the seed is
persisted. Config is `[biome] enable` (on), `scale` 80, `strength` 0.5.

Fertility does three things, all in `objects/food.py`: it scales the
growth rate of a cell, it scales the *carrying capacity* of that cell
(`Food.capacity`, which is what `_EnergyCheck` clamps to), and it gates
whether a seed takes root at a target. The carrying capacity is what
makes the biome visible: the best ground holds cells of about 150 energy
and the worst about 50, against the flat 100 before.

Sources get `self.fertility()` for their own cell or
`self.fertility([x, y])` for another, free and constant for the game. The
raw array is deliberately not in the source's world dict; they see the
terrain one cell at a time. Vetinari and Weatherwax now found new estates
on the most fertile of a few candidate directions. The GUI paints the map
under the world in shades of green.

**Measured.** Food alone over 2500 turns: the richest cells now reach 139
energy where the flat cap was 100, and the mean energy per cell is 46 on
the best third of the ground against 37 to 42 on the worst. The food
population stays stable through the seasons.

**Biomes cost no speed and do not buy any.** A controlled pair, same seed
and turn count, food only: 33.4 ms per turn with biomes and 32.3 ms
without, with 3612 against 3718 food cells. An earlier reading that
credited biomes with a large speed win was confounded: turn time is
dominated by the *wesen* population, not by food cells, and the slow games
(120 to 140 ms) were the ones where Nightwatch had swarmed to 130 to 210
wesen by turn 3000. Games that stay diverse run at 48 to 53 ms either way.

Biomes are neutral for the endgame problem too: Nightwatch still takes the
commons late in two of three seeds, exactly as it did without them. In the
third (seed 1) five sources are alive at turn 3000 with Nightwatch extinct,
which is the best result seen so far, but one seed is not a trend.

### Follow-up: hardening and the pace of the food economy

Three things came out of playing the game rather than measuring it.

**A buggy source no longer ends the game.** `World.main` caught only
`RuleException`; anything else propagated and killed every player's game.
It now catches both, skips that object's turn, counts the fault per source
in `World.faults` and prints each distinct error once with its traceback.
The per-source stats entry is created on demand too, so a restored game
holding a source that is not in the current config no longer crashes.

**Two real crashes were found and fixed.** Movie mode (`m`) referenced
`self.turns`, which never existed on the GUI, so it raised
`AttributeError` on the first frame after being switched on. The popup
menu raised `NotImplementedError` for an unknown entry. Key handling, menu
actions, screenshots, movie frames and the whole render pass are now
wrapped: a drawing bug pauses the game instead of ending it.

**The graph was useless because every curve shared one scale**, so total
energy and the food supply flattened everything else. Each curve is now
scaled on its own, `g` cycles five modes (energy per source, population
per source, both, the world, everything), and the caption prints the
current value of each curve, since curves on different scales cannot be
compared by eye. Per-source population sensors were added, and a
screenshot key (`c`) and a key list (`?`), which only existed as a
right-click menu entry before.

**Two more bugs found by playing it.** Dwarf looked around once per turn
and then acted several times on that stale view, so after eating a cell it
tried to eat it again: the "tried to eat non-existing food" rule violation
every game reported. It now looks around each time round its action loop
(the code even carried a `# could be done in-loop...` note). And the
console script printed `<Wesen.wesend.Wesend object at 0x...>` and exited
non-zero on every clean quit, because `Loader` returned the Wesend and the
generated script runs `sys.exit(Loader())`; a finished game now returns
nothing. Four 2500-turn games afterwards reported no rule violation and no
error at all.

**The pasture now takes about 2000 turns to cover the world** instead of
500, through `[food] birth_maturity` (0.9): a cell only seeds once it has
grown to that share of its own capacity, and a seed starts small and grows
slowly. Lowering `seedrate` was the obvious lever and the wrong one — it
changes where the food economy settles rather than how long it takes to
get there. `birth_width` went to 2.0 to keep the same endpoint of about
4000 cells. The lean early game is much harder on the gardening sources,
so all three now fall back to the cheap wide `look()` when nothing worth
biting is within `closerLook` range, and only for food beyond that range,
since heading for a neighbouring cell they just refused would loop.

## Phase 7: shocks

**Design.** `[events] enable = True`, `rate = 0.0005` per turn. Blight: a
random centre and radius 40, food inside loses 80 percent. Plague: wesen inside
lose 30 percent. Log to stdout and flash the region in the GUI for a few
turns. Keep rare; the point is to punish strategies that assume stability.

## Phase 8: markers and scoring (later)

**Markers.** Cells hold a small dict `{source: value}` that fades per turn;
`Mark(value)` costs 1 time; `closerLook` entries of type `mark` report them.
Enables trails and coordination beyond talk range. This is an API change and a
GUI feature, so it is last.

**Scoring.** `local/tournament.py` reports area under the energy curve and
survival turns next to the final energy, so late swarms stop dominating the
result. The GUI graph can show the running integral.

## What phases 0 to 3 actually landed (2026-09-08)

New modules `src/Wesen/climate.py` and `src/Wesen/variation.py`, new
config sections `[climate]` and `[variation]`, new keys `[world] seed`
and `[wesen] upkeep, upkeep_rate, reproduce_cost, child_min_energy,
attack_damage, attack_cost`. 20 unit tests in `tests/rules.py`. The GUI
plots the season and the colony-wide upkeep and names the season in the
overlay. `local/food_tuning.py` grew `--climate`, `--wesen`,
`--no-climate` and `--variation`.

Two engine bugs surfaced and were fixed: `Reproduce()` now fails when
energy is short, and `recoverAge` in Nightwatch, Rincewind and Dwarf fed
that `False` straight into `Donate`, crashing the whole game; `Donate`
now raises `RuleException` for an unknown id, as `Eat` and `Attack` do.

**The sources had to be rewritten, not retuned.** With the life food rule
and upkeep, gardening yields nothing, and Vetinari, Weatherwax and LuTze
starved next to a 200 000-energy pasture (5 wesen each, shrinking). All
three now have a `grazerTurn` that replaces the estate economy with
herding: bite a cell only while it keeps about a third of `maxamount`,
where regrowth is fastest; strip it further only below the winter
reserve; kill it only when starving; walk to the best cell in view; and
let the estate follow the herd, so the scouts, bogeymen and hunters keep
working unchanged. Alone, each of the three now grows from 1500 to
6000-9000 energy over 1200 turns instead of shrinking.

**Measured, seven sources, seeds 1, 3 and 7:**

| what | result |
|---|---|
| sources alive at turn 2250 | 5 to 7 |
| sources alive at turn 3000 | 1 to 3 |
| leader at turn 1500-2250 | Weatherwax, then LuTze or Rincewind |
| turn time at the plateau | 48-53 ms diverse, 120-140 ms once a source swarms |

**The open balance problem** is the late game: Nightwatch splits at 500
energy with no colony cap, and from about turn 2500 its numbers take the
commons. Two experiments:

* Raising the flat `[wesen] upkeep` does suppress the swarm, but it
  starves the sophisticated sources first: at 2 Weatherwax dies in all
  three seeds, at 3 only two or three sources survive at all, at 5 seed 1
  goes extinct. Left at 1.
* Making Weatherwax and LuTze keep a bigger body when many enemies are
  in view (a "swarm factor") made things worse, not better: hoarding
  slowed their breeding and Nightwatch won sooner. Reverted.

The lever that has not been tried is the one the economy actually turns
on: fewer, richer food cells (lower `[food] count` and `seedrate`, higher
`growrate`). Phase 6 applied a version of it to space rather than to the
global count, which did not change the turn time; the honest measurement
is in the note at the end of that phase.

## Phase 9: shared state (done, 2026-09-09)

**Problem.** A source is one program played by many wesen, so a class
attribute is shared by all of them. Vetinari, Weatherwax and LuTze keep
their colony's map, registries and claims there: one wesen sees a cell
and every other wesen of that source knows about it, wherever it stands.
Nothing in the world carried the fact, which makes `Talk` and
`Broadcast` (and the whole of `range.talk`) pointless, and makes a
colony a single mind rather than a group of agents.

**Rule.** A class attribute is genetic information: the same for every
wesen of a source and for the whole game. What a wesen learns lives in
the instance; what it wants to pass on has to be said out loud.

**Implementation** (`src/Wesen/isolation.py`, `[wesen] shared_state`):
`isolate` (default) freezes the mutable class attributes on the shared
class (deep: `MappingProxyType`, tuples, frozensets) and builds every
wesen from a private subclass carrying its own deep copy, so writes
through `self`/`cls` keep working and stop being shared, while a write
to the class by name raises. `strict` freezes and copies nothing.
`allow` is the old behaviour. `Talk` and `Broadcast` freeze what they
deliver, so a mutable message is not a way round it. Rebinding a class
attribute cannot be frozen away, so `World` audits every 50 turns and
reports it once as a rule violation. Cost: one `type()` call and a copy
of a few empty containers per birth.

**Consequence.** The three older colonies still run (they write through
`cls`), but they lose the shared map *and* the population governors
that were built on the same registries, so they breed much harder than
they used to. Adapting them means putting that knowledge into messages,
which is what `Rincewind` does; it keeps no class state at all and is
unaffected by the setting.

## Tuning protocol (every phase)

1. `uv run python local/food_tuning.py --turns 4000` without sources: food
   stable, no extinction, no runaway.
2. Each source alone for 2000 turns: survives, population plateaus.
3. All seven sources, seeds 1, 3, 7, 3000 turns: at least four alive at the
   end in two of three seeds; turn time under 60 ms at the plateau.
4. Classic rule sanity: `--food rule=classic ...` for 600 turns, no crash.
5. `uv run python -m unittest tests.persistence tests.rules`.

## Risks

- Seasons plus metabolism can cause winter die-offs of whole sources. Start
  with amplitude 0.4 and raise it; keep the winter floor above zero growth
  for isolated cells.
- Per-game variation breaks the exploit math in Weatherwax and LuTze. That is
  intended, but adapt them so they read the rules, or they will lose every game.
- Old `gamestate` files lack the new state; restore must default gracefully.
- Performance: biome and climate lookups are numpy indexing per food object,
  negligible next to the existing range iterator.
