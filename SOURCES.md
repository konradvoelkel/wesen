# The sources

What each source shipped in `src/Wesen/sources/` does, as it plays
under the default rules. How to write one is in `GUIDE.md`; every
source's module docstring has the reasoning behind its design.

How they rank, measured with `wesen-tournament` on the default rules:
in the full field (all eleven, 1000 turns, ten seeds) Rincewind wins
every seed by a wide margin, Weatherwax is second and Nightwatch
third, then Dwarf and SoberSailor, then LuTze and Vetinari, GreatRabbit,
and DrunkenSailor, WindlePoons and Scanner at the bottom. In duels the
picture differs: GreatRabbit beats everything but Rincewind head to
head, and the three small colonies beat LuTze and Vetinari. Rincewind
beats all of them.

## The colonies

### Rincewind - the colony that talks

`Rincewind/` (`main.py`, `ledger.py`, `plan.py`). Sensing is a
colony-wide service and the individual wesen is a subscriber to it.
It keeps no class-level state at all, so it plays the same under every
`shared_state` mode.

* **Gossip.** Each wesen keeps a ledger of food cells (energy, when
  seen, when bitten, who reserved it), colleagues (position, energy,
  home, role), threats and explored tiles, and broadcasts a delta of
  what it learned once a turn. Incoming ledgers are merged key by key,
  newest timestamp wins; the calendar is the highest clock anybody
  quotes; the roll of colleagues is relayed. A report loses 1.5 % of
  its worth per turn of age, so a colleague's news beats one's own
  stale memory.
* **Districts without negotiation.** Homes are published, so every
  wesen draws the same Voronoi partition and knows which cells are its
  own; a home drifts toward the cells its keeper harvests. A cell is
  reserved in the ledger before the walk to it starts.
* **Harvest.** A fed wesen leaves a third of a cell standing and never
  touches one cell in four (a hash of the position, so the colony
  agrees for free), which keeps the pasture seeding; where the alarms
  say a rival grazes, both rules drop to what a hungry wesen takes.
* **Population.** A wesen splits while its district holds more known
  cells than one wesen can work and never with two colleagues within
  twelve cells; the colony's size is estimated from the density of
  known homes, and growth stops while a district is shrinking against
  its own average. A child is briefed by `Talk` at birth - clock,
  district, a copy of the map. A wesen that may not split at old age
  turns itself into food on its own ground instead.
* **Alarms.** Every stranger seen is broadcast; cells near a killer are
  worth less, flight uses the whole time budget, and a cheap thief on
  the own cell is killed.
* Every dimensioned number is derived from the rules (`readRules`).

### Weatherwax - herding on a map

`Weatherwax/main.py`. A herding colony that knows the land: every
wesen writes what it sees into a map of food cells keyed by tile,
estimates the current energy of remembered cells from the regrowth
rate, and each turn walks to the cell with the best energy per time
(bites × bite / (eat time + walk time)) within reach. What it bites
depends on the body: with a full reserve only bites that leave a cell
around a third of its capacity; below the reserve down to the roots;
only when starving does it kill a cell. One cell in three, chosen by
position, is a seeder and never bitten unless the wesen is starving.
The terrain is sampled once and unexplored fertile tiles are visited
first. Population follows the ground a wesen keeps (the known cells
closer to its anchor than to any colleague's); children are sent to
free sites away from every other anchor. Threats are judged by what
their attack would do; a wesen eats itself out of reach if it can,
else flees with the whole time budget in a direction chosen at run
time; cheap thieves on the own cell are killed. What the colony knows
travels through `colony.py` (a shared clock, a roll, one broadcast a
turn); old age is cured by a sacrifice child that gives its energy
back.

### LuTze - the sweeper

`LuTze/main.py`. Roles: gardeners, scouts, hunters. Gardeners keep an
estate that serves as a base for grazing the wild pasture nearby in
bites that leave cells alive (the estate follows the herd when the
ground is bare), and split while fewer than a set number of colleagues
keep house within the district. Scouts sweep the map on a tile grid
with cheap `look()` calls and register enemy homes and roaming
enemies. Hunters are financed by the home cell and dispatched against
Vetinari and Weatherwax residents: a hunter fatter than a resident's
flight threshold paralyses a cell and kills the residents one by one
by walking after their flight. Anything else is hunted only when the
kill is cheap; anything that steps on a treasury is killed by the
gardeners if affordable, and a cell camped by an eater it cannot kill
is abandoned. Colony knowledge travels through `colony.py`.

### Vetinari - the Patrician

`Vetinari/main.py`. Every wesen keeps a home cell (estate) as the base
of a herd: it grazes the best cell in view in bites that leave it
alive, strips further only below its winter reserve, kills a cell only
when starving, and the estate follows the herd. Income goes into
reproduction as soon as both halves are safe; crowded estates send
newborns to found a new estate out of sight, and the local population
rule counts the colleagues within the district. Enemies on the estate
are struck first whenever that kills them; enemies that could kill the
wesen make it bulk up or walk away with its whole time budget along a
randomised axis. A danger memory keeps the herd off ground where
something lethal was seen, and a camped estate relocates the whole
herd. Old age is cured by reproducing; if the colony is full the child
donates everything back and vanishes.

## The small colonies

Three sources built each around one idea and one grazing policy,
worked out from the rules: bite a cell while it keeps 30 % of its
capacity; below a birth and a reserve of 60 turns' upkeep the wesen is
hungry and goes to 25 %; only with upkeep for fewer than 15 turns left
does it eat a cell whole. A birth needs three cells above the floor in
view; old age is cured by splitting; anything that could kill the wesen
and reach it in a turn makes it run with the whole time budget. They
keep no class state; what a wesen knows it saw or was told.

### SoberSailor - the chart and the log

`SoberSailor/main.py`. The ground is knowable before the first turn,
since `fertility()` is free and built from the seed. Every sailor cuts
the world into blocks three harbours wide, takes the most fertile
sample of each block as its *port*, and runs the blocks boustrophedon
into one loop - a route with every leg a block long, the same for the
whole fleet without a word said. A sailor sails port to port, puts in
for a bite within five cells of its course, takes shore leave in
harbour until nothing is left above the floor, logs the port and reads
the log out on the quay so colleagues sail past a port grazed dry.
Rotational grazing at the scale of the world. It stops splitting once
most of its last eight landfalls found the harbour already dry, and it
never fights.

### Dwarf - the mine, the shift and the axe

`Dwarf/main.py`. A founder samples the rock around it and sinks a
shaft on the richest ground; the mine is a disc of 2.5 sights around
it, cut into six galleries like a pie, and the clan works one gallery
per *shift* on a clock kept in step by talking, so each gallery rests
five shifts and the crew stays together. A cheap thief on the own cell
is killed; a dwarf holding two breeding bodies is a *guard* and goes
for prey within reach; a threatened dwarf runs to the nearest guard
that could take the bully. When more of the clan than the gallery
feeds are in view for a while, the fattest reads the rock two
mine-widths out and sinks a new shaft. The most restrained of the
three: it holds about 180 wesen alone with the pasture intact.

### Nightwatch - the beat, the lantern and the hours

`Nightwatch/main.py`. The watch house stands where the founder stood;
the city is the square eight sights to a side around it, cut into
beats one sight square. With nothing in view worth a bite a watchman
walks to the beat longest unpatrolled by anybody's account, so grazing
goes round the city by staleness. `look()` costs half of
`closerLook()` and sees twice as far: the lantern is raised every third
turn to count the food per beat. Every eighth turn the hours are
called: last patrol and food per beat, the *roll* of everyone seen or
heard (relayed, so it reaches beyond earshot), and a whistle for the
beat a bully stands on, which the patrol keeps off for a while. The
precinct is staffed when the roll holds as many as the counted food
keeps; then the fattest of a crowd walks out to open a precinct in an
unwatched quarter. Thieves on the own cell are arrested and sergeants
hunt within reach.

## The loners

### GreatRabbit - the insatiable

`GreatRabbit/main.py`, forty lines. Walks to the nearest food it
wants (ripe first, bites when hungry, anything when starving), eats,
and splits at 150 energy whenever three ripe cells are in view. It
swarms an empty pasture to several hundred and beats every colony but
Rincewind head to head; in the full field it starves once four
colonies share the pasture.

### DrunkenSailor - the Lévy flight

`DrunkenSailor/main.py`. Random movement done the way a drunk finds
the next pub: a step is either a *stagger* to the nearest bite in view
or a *lurch* - a straight run of heavy-tailed (Pareto) length into
ground it has not seen - and it lurches only when nothing in sight is
worth a step. On a rich patch it sings a shanty (`Broadcast`), and a
colleague in earshot that would otherwise lurch at random lurches
toward the song.

### Scanner - the police scanner

`Scanner/main.py`. Does no surveying of its own. `Broadcast` reaches
every wesen in range whatever its source, the colonies run on it, and
the engine says who sent what; anything inside a stranger's message
shaped like `(x, y, energy)` is a tip. The Scanner drifts toward the
crowd, listens, walks to the best fresh tip, relays the best of what it
heard to colleagues on a channel of its own, and sweeps the raster only
when the air is silent. It gets stronger the more the others talk.

### WindlePoons - the Fresh Start Club

`WindlePoons/main.py`. Built on one rule: a `Vomit` blob bigger than a
cell's capacity neither grows nor shrinks, lies there until eaten, and
pays no upkeep. In summer it roams and grazes; fat at the first lean
turn it buries all but a fighting body on a fertile cell and sits the
winter on the grave, striking thieves; in spring the bank is withdrawn
and split into a litter, each child told at birth where the grave is;
at 950 it splits to reset its age. The bank saves half a percent of
what is buried per turn, which a grazing child out-earns, so only the
fat go to ground.

## Tools, not players

* `Manual/main.py` executes what you type at the console as that
  wesen's turn - an interactive AI for debugging.
* `example.py` is the empty skeleton to copy.
