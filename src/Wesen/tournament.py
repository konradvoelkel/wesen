"""Playing sources against each other, headless, and scoring the result.

The game has always been scored by one number: the energy held by a
source's living wesen when the game is stopped. That rewards whoever
happens to be swarming at the final turn, and says nothing about the
source that held the field for two thousand turns and was overrun at the
end. So three numbers are reported here:

``energy``
    the old one - what a source holds at the last turn.
``mean``
    the area under its energy curve divided by the length of the game:
    what it held *on average*, over the whole game. A late swarm barely
    moves it; being rich early and staying rich is the only way to make
    it large.
``alive``
    the turns on which the source had at least one wesen, as a share of
    the game. Surviving is not winning, but a source that dies on turn
    400 did not win a 3000-turn game whatever its curve looked like.
``cpu``
    its share of the real time spent running source code. The rules
    budget a wesen's in-game ``time``, not the interpreter's, so this is
    the only place where a source that thinks for a second a turn shows
    up at all - and it is usually the answer to why a game crawls.

The ranking is by ``mean``, and the ranking by ``energy`` is printed
next to it whenever the two disagree, because the disagreement is the
interesting part.

    wesen-tournament --turns 2000 --sources Dwarf,Rincewind --seeds 1,2,3

Runs without a config file, on the same defaults the game itself uses;
``-c FILE`` takes one, so the GUI can be pointed at the same rules with
``wesen -c FILE``.
"""

import argparse
import json
import time

from .configed import ConfigEd
from .defaults import CONFIG_DEFAULTS
from .sourceloader import SourceError, loadSource, setSearchPath
from .wesend import Wesend


class Result:
    """what one source did in one game"""

    def __init__(self, name, turns):
        self.name = name
        self.turns = turns
        self.energy = 0
        self.count = 0
        self.area = 0
        self.peak = 0
        self.alive = 0
        self.lastAlive = 0
        self.seconds = 0.0

    def note(self, turn, entry):
        """one turn's statistics for this source"""
        self.energy = entry["energy"]
        self.count = entry["count"]
        self.area += entry["energy"]
        self.peak = max(self.peak, entry["energy"])
        self.seconds += entry.get("seconds", 0.0)
        if entry["count"]:
            self.alive += 1
            self.lastAlive = turn

    @property
    def mean(self):
        """energy held per turn, averaged over the whole game"""
        return self.area / max(1, self.turns)

    @property
    def survival(self):
        """share of the game the source was alive for"""
        return self.alive / max(1, self.turns)

    def asDict(self):
        return {
            "source": self.name,
            "energy": self.energy,
            "count": self.count,
            "mean": round(self.mean, 1),
            "peak": self.peak,
            "alive": self.alive,
            "lastAlive": self.lastAlive,
            "survival": round(self.survival, 3),
            "seconds": round(self.seconds, 2),
        }


def buildConfig(args):
    """the rules this tournament is played under: the game's own
    defaults, or a config file if one was named"""
    if args.config:
        config = ConfigEd(args.config).getConfig()
    else:
        config = {k: dict(v) for k, v in CONFIG_DEFAULTS.items()}
    config["gui"]["enable"] = False
    config["resume"] = False
    if args.sources:
        config["wesen"]["sources"] = args.sources
    if args.sourcepath:
        config["wesen"]["sourcepath"] = args.sourcepath
    if args.length:
        config["world"]["length"] = args.length
    if args.count:
        config["wesen"]["count"] = args.count
    setSearchPath(config["wesen"].get("sourcepath", ""))
    return config


def sourceNames(config):
    """the sources of a config, however the config spells them"""
    names = config["wesen"]["sources"]
    if isinstance(names, str):
        names = names.split(",")
    return sorted(name.strip() for name in names if name.strip())


def playOne(config, seed, turns, every=0, quiet=True):
    """plays one game and returns {source: Result}.

    The whole point of the extra scores is that they are accumulated
    every turn, not sampled: `--every` only decides how often a line is
    printed."""
    config = {
        k: (dict(v) if isinstance(v, dict) else v)
        for k, v in config.items()
    }
    config["world"]["seed"] = seed
    names = sourceNames(config)
    # built before the header is printed: Wesend announces the seed and
    # what it made of the sources' shared state as it goes
    wesend = Wesend(config)
    world = wesend.world
    if every and not quiet:
        print(header(names), flush=True)
    results = {name: Result(name, turns) for name in names}
    food = Result("food", turns)
    started = time.perf_counter()
    for turn in range(1, turns + 1):
        world.main()
        for name, result in results.items():
            result.note(turn, world.stats.get(name, EMPTY))
        food.note(turn, world.stats.get("food", EMPTY))
        if every and (turn % every == 0 or turn == turns) and not quiet:
            print(turnLine(turn, world.stats, names), flush=True)
    elapsed = time.perf_counter() - started
    if not quiet:
        print(
            f"# {turns} turns in {elapsed:.1f}s "
            f"({turns / max(elapsed, 1e-9):.0f} turns/s), "
            f"{len(world.objects)} objects left"
        )
        reportFaults(world)
    return results, food, elapsed


EMPTY = {"count": 0, "energy": 0, "upkeep": 0}


def reportFaults(world):
    """a source that spent the game raising did not really play"""
    for source, counts in sorted(world.faults.items()):
        print(
            f"# {source} faulted: {counts['rule']} rule violations, "
            f"{counts['error']} errors"
        )


def turnLine(turn, stats, names):
    cells = [f"{turn:7d}"]
    for name in ["food"] + names:
        entry = stats.get(name, EMPTY)
        cells.append(f"{entry['count']:5d}/{entry['energy']:8d}")
    return " ".join(cells)


def header(names):
    return "turn    " + " ".join(
        f"{name:>14s}" for name in ["food"] + names
    )


def table(results):
    """the scoreboard for one game, best mean energy first"""
    order = sorted(results.values(), key=lambda r: r.mean, reverse=True)
    # each source's share of the time spent in source code (the food
    # economy and the rest of the engine are not in this total: the
    # question here is how the players divide the machine between them)
    machine = sum(r.seconds for r in results.values()) or 1.0
    lines = [
        f"{'source':>14} {'mean':>10} {'energy':>10} {'peak':>10} "
        f"{'count':>6} {'alive':>7} {'cpu':>6}"
    ]
    for result in order:
        lines.append(
            f"{result.name:>14} {result.mean:>10.0f} "
            f"{result.energy:>10d} {result.peak:>10d} "
            f"{result.count:>6d} {result.survival:>6.0%} "
            f"{result.seconds / machine:>5.0%}"
        )
    byEnergy = sorted(
        results.values(), key=lambda r: r.energy, reverse=True
    )
    if [r.name for r in order] != [r.name for r in byEnergy]:
        lines.append(
            "# by final energy instead: "
            + ", ".join(f"{r.name}={r.energy}" for r in byEnergy)
        )
    return "\n".join(lines)


def combine(games):
    """the mean of each score over several games, so that one lucky
    seed cannot decide a match"""
    names = sorted({name for game in games for name in game})
    rows = []
    for name in names:
        runs = [game[name] for game in games if name in game]
        rows.append(
            {
                "source": name,
                "mean": sum(r.mean for r in runs) / len(runs),
                "energy": sum(r.energy for r in runs) / len(runs),
                "survival": sum(r.survival for r in runs) / len(runs),
                "wins": sum(
                    1
                    for game in games
                    if game
                    and max(game.values(), key=lambda r: r.mean).name
                    == name
                ),
                "games": len(runs),
            }
        )
    rows.sort(key=lambda row: row["mean"], reverse=True)
    lines = [
        f"{'source':>14} {'mean':>10} {'energy':>10} {'alive':>7} "
        f"{'wins':>6}"
    ]
    for row in rows:
        lines.append(
            f"{row['source']:>14} {row['mean']:>10.0f} "
            f"{row['energy']:>10.0f} {row['survival']:>6.0%} "
            f"{row['wins']:>4d}/{row['games']}"
        )
    return "\n".join(lines), rows


def parseArgs(argv=None):
    parser = argparse.ArgumentParser(
        prog="wesen-tournament",
        description=(
            "play wesen sources against each other without a GUI and "
            "score the result by energy held over the whole game, not "
            "only at the last turn"
        ),
    )
    parser.add_argument("--turns", type=int, default=2000)
    parser.add_argument(
        "-s",
        "--sources",
        default=None,
        help="comma-separated, overrides the config",
    )
    parser.add_argument(
        "-p",
        "--sourcepath",
        default=None,
        help="extra folders to look for sources in",
    )
    parser.add_argument(
        "--seeds",
        default="1",
        help="comma-separated game seeds; each is played once",
    )
    parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="config file; without one the game's own defaults are used",
    )
    parser.add_argument("--length", type=int, default=None)
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="wesen per source at the start",
    )
    parser.add_argument(
        "--every",
        type=int,
        default=250,
        help="print a line of statistics every this many turns (0: never)",
    )
    parser.add_argument(
        "--json", default=None, help="write the scores to this file"
    )
    parser.add_argument("-q", "--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parseArgs(argv)
    config = buildConfig(args)
    names = sourceNames(config)
    # loaded up front, so a name that is not there is said plainly
    # before anything is played, and the exit status says it too
    if not names:
        print("wesen: no sources to play")
        raise SystemExit(1)
    for name in names:
        try:
            loadSource(name)
        except SourceError as exc:
            print(f"wesen: {exc}")
            raise SystemExit(1) from exc
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    games = []
    for seed in seeds:
        if not args.quiet:
            print(f"# seed {seed}")
        results, _food, _elapsed = playOne(
            config, seed, args.turns, args.every, args.quiet
        )
        games.append(results)
        if not args.quiet:
            print(table(results), flush=True)
    rows = None
    if len(games) > 1 and not args.quiet:
        summary, rows = combine(games)
        print(f"\n# {len(games)} games, averaged")
        print(summary)
    if args.json:
        if rows is None:
            rows = combine(games)[1]
        with open(args.json, "w") as handle:
            json.dump(
                {
                    "turns": args.turns,
                    "seeds": seeds,
                    "sources": names,
                    "games": [
                        {
                            name: result.asDict()
                            for name, result in game.items()
                        }
                        for game in games
                    ],
                    "summary": rows,
                },
                handle,
                indent=1,
            )


if __name__ == "__main__":
    main()
