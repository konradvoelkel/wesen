"""Unit tests for the game rules: seeding, per-game variation,
seasons, metabolism and reproduction cost."""

if __name__ == "__main__":
    import sys

    sys.path.append("../src")

import unittest

from Wesen import isolation
from Wesen.biome import Biome
from Wesen.climate import GROWTH_MAX, GROWTH_MIN, SEASONS, Climate
from Wesen.defaults import CONFIG_DEFAULTS
from Wesen.variation import VARIED, applySeed, applyVariation
from Wesen.world import World


def makeConfig(**sections):
    """a full default config, with the given sections overridden"""
    config = {k: dict(v) for k, v in CONFIG_DEFAULTS.items()}
    for section, values in sections.items():
        config[section].update(values)
    return config


def makeWorld(**sections):
    config = makeConfig(**sections)
    config["gui"]["enable"] = False
    config["wesen"].setdefault("sources", [])
    if isinstance(config["wesen"]["sources"], str):
        config["wesen"]["sources"] = []
    config["wesen"]["count"] = 0
    config["world"]["Debug"] = lambda _: None
    return World(config)


class TestSeed(unittest.TestCase):
    def test_seed_is_drawn_and_recorded(self):
        config = makeConfig(world={"seed": 0})
        seed = applySeed(config, announce=False)
        self.assertGreater(seed, 0)
        self.assertEqual(config["world"]["seed"], seed)

    def test_same_seed_gives_same_world(self):
        def run():
            config = makeConfig(
                world={"seed": 4242, "length": 60},
                food={"count": 40},
                climate={"enable": True},
            )
            applySeed(config, announce=False)
            world = makeWorld(
                world={"seed": 4242, "length": 60}, food={"count": 40}
            )
            for _ in range(20):
                world.main()
            return sorted(
                (o.position[0], o.position[1], o.energy)
                for o in world.objects.values()
            )

        self.assertEqual(run(), run())


class TestVariation(unittest.TestCase):
    def test_disabled_by_default(self):
        config = makeConfig()
        self.assertEqual(applyVariation(config, announce=False), {})

    def test_varies_only_whitelisted_keys(self):
        config = makeConfig(variation={"enable": True, "spread": 0.2})
        applySeed(config, announce=False)
        before = {s: dict(v) for s, v in config.items()}
        changed = applyVariation(config, announce=False)
        self.assertTrue(changed)
        for name in changed:
            section, key = name.split(".")
            self.assertIn(key, VARIED[section])
        for section, values in before.items():
            for key, value in values.items():
                if f"{section}.{key}" not in changed:
                    self.assertEqual(config[section][key], value)

    def test_stays_within_spread_and_keeps_types(self):
        for _ in range(20):
            config = makeConfig(variation={"enable": True, "spread": 0.2})
            applySeed(config, announce=False)
            before = {s: dict(v) for s, v in config.items()}
            applyVariation(config, announce=False)
            for section, keys in VARIED.items():
                for key in keys:
                    old, new = before[section][key], config[section][key]
                    self.assertIsInstance(new, type(old))
                    self.assertGreaterEqual(new, 1 if isinstance(old, int) else 0)
                    self.assertLessEqual(new, old * 1.2 + 1)
                    self.assertGreaterEqual(new, old * 0.8 - 1)


class TestClimate(unittest.TestCase):
    def info(self, **over):
        return dict(CONFIG_DEFAULTS["climate"], **over)

    def test_disabled_is_neutral(self):
        climate = Climate(self.info(enable=False))
        for turn in range(0, 1000, 37):
            state = climate.step(turn)
            self.assertEqual(state["growth"], 1.0)

    def test_periodic(self):
        climate = Climate(
            self.info(random_phase=False, severity_random=0.0, period=400)
        )
        first = [climate.step(t)["growth"] for t in range(400)]
        second = [climate.step(t)["growth"] for t in range(400, 800)]
        for a, b in zip(first, second):
            self.assertAlmostEqual(a, b, places=9)

    def test_growth_within_bounds(self):
        climate = Climate(self.info(amplitude=5.0, severity_random=0.9))
        for turn in range(2000):
            growth = climate.step(turn)["growth"]
            self.assertGreaterEqual(growth, GROWTH_MIN)
            self.assertLessEqual(growth, GROWTH_MAX)

    def test_severity_within_range(self):
        climate = Climate(self.info(severity_random=0.3))
        seen = set()
        for turn in range(3000):
            severity = climate.step(turn)["severity"]
            self.assertGreaterEqual(severity, 0.7)
            self.assertLessEqual(severity, 1.3)
            seen.add(round(severity, 6))
        self.assertGreater(len(seen), 4, "severity should be redrawn")

    def test_seasons_cycle_in_order(self):
        climate = Climate(
            self.info(random_phase=False, severity_random=0.0, period=400)
        )
        names = [climate.step(t)["season"] for t in range(400)]
        self.assertEqual(names[0], "spring")
        # the peak of the year lies in summer, the trough in winter
        growths = [climate.step(t)["growth"] for t in range(400)]
        peak = max(range(400), key=lambda t: growths[t])
        trough = min(range(400), key=lambda t: growths[t])
        self.assertEqual(names[peak], "summer")
        self.assertEqual(names[trough], "winter")
        self.assertEqual(set(names), set(SEASONS))

    def test_persist_roundtrip(self):
        climate = Climate(self.info())
        for turn in range(500):
            climate.step(turn)
        other = Climate(self.info())
        other.restore(climate.persist())
        self.assertEqual(other.step(500), climate.step(500))

    def test_food_growth_follows_the_season(self):
        world = makeWorld(
            world={"length": 60},
            food={"count": 30},
            climate={"enable": True},
        )
        food = next(iter(world.objects.values()))
        food.energy = food.maxamount // 2
        # an explicit neighbourhood density, so the result does not
        # depend on where the food happened to be placed
        peak = food.fertilePeak
        world.climate.state["growth"] = 1.0
        normal = food.growth(n=peak)
        world.climate.state["growth"] = 0.2
        winter = food.growth(n=peak)
        world.climate.state["growth"] = 1.8
        summer = food.growth(n=peak)
        self.assertLess(winter, normal)
        self.assertGreater(summer, normal)


class TestBiome(unittest.TestCase):
    def info(self, **over):
        return dict(CONFIG_DEFAULTS["biome"], **over)

    def test_disabled_is_neutral(self):
        biome = Biome(self.info(enable=False), 200, seed=1)
        self.assertIsNone(biome.field)
        self.assertEqual(biome.at([7, 11]), 1.0)

    def test_same_seed_gives_the_same_terrain(self):
        a = Biome(self.info(), 200, seed=77)
        b = Biome(self.info(), 200, seed=77)
        c = Biome(self.info(), 200, seed=78)
        self.assertTrue((a.field == b.field).all())
        self.assertFalse((a.field == c.field).all())

    def test_within_strength(self):
        biome = Biome(self.info(strength=0.4), 200, seed=5)
        self.assertGreaterEqual(biome.field.min(), 0.6 - 1e-9)
        self.assertLessEqual(biome.field.max(), 1.4 + 1e-9)
        # the extremes are actually reached, or strength means nothing
        self.assertLess(biome.field.min(), 0.8)
        self.assertGreater(biome.field.max(), 1.2)

    def test_wraps_around_the_torus(self):
        biome = Biome(self.info(scale=40), 200, seed=9)
        field = biome.field
        # the world wraps for movement, so the terrain has to wrap too:
        # the seam must be no sharper than a step inside the map
        seamX = abs(field[0] - field[-1]).max()
        insideX = abs(field[1:] - field[:-1]).max()
        self.assertLessEqual(seamX, insideX * 1.5 + 1e-9)
        seamY = abs(field[:, 0] - field[:, -1]).max()
        insideY = abs(field[:, 1:] - field[:, :-1]).max()
        self.assertLessEqual(seamY, insideY * 1.5 + 1e-9)

    def test_food_grows_faster_on_good_ground(self):
        world = makeWorld(
            world={"length": 200, "seed": 3},
            food={"count": 10},
            biome={"enable": True, "strength": 0.5},
        )
        field = world.biome.field
        food = next(iter(world.objects.values()))
        food.energy = food.maxamount // 4
        best = list(divmod(int(field.argmax()), field.shape[1]))
        worst = list(divmod(int(field.argmin()), field.shape[1]))
        food.position = best
        rich = food.growth(n=food.fertilePeak)
        food.position = worst
        poor = food.growth(n=food.fertilePeak)
        self.assertGreater(rich, poor)

    def test_sources_may_ask_about_one_cell_only(self):
        world = makeWorld(
            world={"length": 120, "seed": 4}, food={"count": 0}
        )
        info = dict(world.infoAllWorld["wesen"])
        info["source"] = "DrunkenSailor"
        info["energy"] = 200
        wesen = world.AddObject(info)
        source = wesen.wesenSource
        self.assertNotIn("fertility", source.infoWorld)
        self.assertAlmostEqual(
            source.fertility(), world.biome.at(wesen.position), places=9
        )

    def test_persist_rebuilds_the_same_terrain(self):
        world = makeWorld(
            world={"length": 120, "seed": 55},
            food={"count": 10},
            biome={"enable": True},
        )
        d = world.persist()
        self.assertIn("biome", d)
        self.assertNotIn("fertility", d["world"])
        self.assertNotIn("Fertility", d["world"])
        other = World(d, createObjects=False)
        self.assertTrue((other.biome.field == world.biome.field).all())


class TestFoodSpread(unittest.TestCase):
    """the maturity gate is what decides how long the pasture takes to
    spread over the world (see Food._lifeSeed)"""

    def food(self, energy, **over):
        world = makeWorld(
            world={"length": 80, "seed": 2},
            food={"count": 1, **over},
            biome={"enable": False},
        )
        item = next(iter(world.objects.values()))
        item.energy = energy
        return item

    def test_a_young_cell_does_not_seed(self):
        food = self.food(20, birth_maturity=0.9)
        food.age = 100
        self.assertIsNone(food._lifeSeed())

    def test_a_grown_cell_may_seed(self):
        food = self.food(100, birth_maturity=0.9, seedrate=1.0)
        food.age = 100
        seeded = any(food._lifeSeed() for _ in range(200))
        self.assertTrue(seeded)

    def test_maturity_is_measured_against_the_local_capacity(self):
        food = self.food(60, birth_maturity=0.9)
        self.assertEqual(food.capacity(), food.maxamount)
        self.assertLess(food.energy, food.birthMaturity * food.capacity())


class TestLifeBatch(unittest.TestCase):
    """The life rule is run for the whole pasture at once, with numpy,
    rather than one cell at a time (see food.stepLifeBatch). The scalar
    methods stay the readable definition of the rule, so the batch has
    to agree with them."""

    def pasture(self, **over):
        """a world holding both kinds of cell: scattered ones, which
        have room to grow, and one tight clump, which is crowded enough
        to decay. Both signs of the growth curve are then covered."""
        world = makeWorld(
            world={"length": 200, "seed": 11},
            food={"count": 60, **over},
            biome={"enable": True, "strength": 0.5},
            climate={"enable": True},
        )
        world.climate.step(7)
        infoFood = dict(world.infoAllWorld["food"])
        for n in range(15):
            world.AddObject(
                dict(infoFood, position=[20 + n % 4, 20 + n // 4])
            )
        cells = [
            o for o in world.objects.values() if o.objectType == "food"
        ]
        for n, cell in enumerate(cells):
            # a spread of sizes, so both halves of the logistic growth
            # curve are covered; the initial food is given a random age
            cell.age = 0
            cell.energy = min(1 + (n * 7) % 120, cell.capacity())
        world.updateFoodField()
        return world, cells

    def pinDraws(self, chance=1.0, jitter=1.0):
        """makes every draw the batch takes come out at a known value,
        so what is left of it is the rule itself. A chance of 1.0 passes
        no probability below one: nothing seeds and nothing rounds up."""
        import numpy as np

        realRandom, realUniform = np.random.random, np.random.uniform
        np.random.random = lambda n: np.full(n, chance)
        np.random.uniform = lambda low, high, n: np.full(n, jitter)
        self.addCleanup(setattr, np.random, "random", realRandom)
        self.addCleanup(setattr, np.random, "uniform", realUniform)

    def test_both_signs_of_the_rule_are_exercised(self):
        """the equivalence test below is only worth something if the
        pasture holds cells that grow and cells that decay"""
        _, cells = self.pasture()
        self.assertEqual(
            {cell.growth() > 0 for cell in cells}, {True, False}
        )

    def test_growth_matches_the_scalar_rule(self):
        from math import floor

        from Wesen.objects.food import stepLifeBatch

        world, cells = self.pasture()
        self.pinDraws()
        expected = {
            id(cell): cell.energy
            + floor(cell.growrate * cell.growth() * 1.0)
            for cell in cells
        }
        self.assertTrue(any(v != 0 for v in expected.values()))
        stepLifeBatch(cells, world.infoAllWorld["world"])
        for cell in cells:
            want = expected[id(cell)]
            if want <= 0:
                self.assertTrue(
                    cell.dead, "a cell grown down to nothing still lives"
                )
                continue
            self.assertFalse(cell.dead)
            self.assertEqual(cell.energy, want)
            self.assertEqual(cell.age, 1)

    def test_a_cell_is_held_to_the_capacity_of_its_ground(self):
        from Wesen.objects.food import stepLifeBatch

        world, cells = self.pasture()
        self.pinDraws()
        cell = cells[0]
        cell.energy = cell.capacity() * 10
        stepLifeBatch([cell], world.infoAllWorld["world"])
        self.assertLessEqual(cell.energy, cell.capacity())

    def test_a_cell_dies_of_old_age_in_the_batch(self):
        from Wesen.objects.food import stepLifeBatch

        world, cells = self.pasture()
        old = cells[0]
        old.age = old.maxage - 1
        stepLifeBatch(cells, world.infoAllWorld["world"])
        self.assertTrue(old.dead)
        self.assertNotIn(id(old), world.objects)

    def test_the_batch_still_seeds(self):
        from Wesen.objects.food import stepLifeBatch

        world, _ = self.pasture(seedrate=1.0)
        before = len(world.objects)
        for _ in range(10):
            world.updateFoodField()
            stepLifeBatch(
                [
                    o
                    for o in list(world.objects.values())
                    if o.objectType == "food"
                ],
                world.infoAllWorld["world"],
            )
        self.assertGreater(len(world.objects), before)

    def test_food_eaten_by_a_wesen_does_not_also_take_its_turn(self):
        """the world snapshots the food before the wesen act, so a cell
        eaten in between has to be skipped rather than grown"""
        world, cells = self.pasture()
        victim = cells[0]
        victim.Die()
        world.stepFood(cells)
        self.assertTrue(victim.dead)
        self.assertNotIn(id(victim), world.objects)

    def test_the_occupancy_grid_stays_in_step_with_the_map(self):
        """every range scan trusts the grid, so a cell that is added,
        moved or removed without it is an object that stops existing"""
        import numpy as np

        world, _ = self.pasture()
        info = dict(world.infoAllWorld["wesen"])
        info.update({"source": "DrunkenSailor", "energy": 400})
        for _ in range(6):
            world.AddObject(dict(info))
        for _ in range(25):
            world.main()
        counted = np.array(
            [[len(cell) for cell in row] for row in world.map]
        )
        self.assertTrue((counted == world.counts).all())
        self.assertEqual(int(counted.sum()), len(world.objects))


class TestHardening(unittest.TestCase):
    def brokenWorld(self, exception):
        import Wesen.sources.DrunkenSailor.main as source

        world = makeWorld(
            world={"length": 60}, food={"count": 5}
        )
        info = dict(world.infoAllWorld["wesen"])
        info["source"] = "DrunkenSailor"
        info["energy"] = 500
        world.AddObject(info)
        original = source.WesenSource.main

        def boom(self):
            raise exception

        source.WesenSource.main = boom
        self.addCleanup(setattr, source.WesenSource, "main", original)
        return world

    def test_a_buggy_source_does_not_end_the_game(self):
        world = self.brokenWorld(ValueError("deliberate bug"))
        for _ in range(5):
            world.main()  # must not raise
        self.assertEqual(world.turns, 5)
        self.assertEqual(world.faults["DrunkenSailor"]["error"], 5)
        self.assertEqual(
            1,
            sum(
                1
                for o in world.objects.values()
                if o.objectType == "wesen"
            ),
        )

    def test_rule_violations_are_counted_apart_from_bugs(self):
        from Wesen.objects.wesen import RuleException

        world = self.brokenWorld(RuleException("broke a rule"))
        for _ in range(3):
            world.main()
        counts = world.faults["DrunkenSailor"]
        self.assertEqual(counts["rule"], 3)
        self.assertEqual(counts["error"], 0)

    def test_each_distinct_error_is_reported_only_once(self):
        world = self.brokenWorld(ValueError("deliberate bug"))
        for _ in range(4):
            world.main()
        self.assertEqual(len(world.reported), 1)


class TestLoader(unittest.TestCase):
    def test_a_finished_game_returns_nothing(self):
        """the console script runs sys.exit(Loader()), and sys.exit of
        anything but None or an int prints that object and fails, so a
        game that ran to its end must not return the Wesend"""
        import sys
        import tempfile
        from os.path import join

        from Wesen import loader

        started = []

        class FakeWesend:
            def __init__(self, config):
                self.config = config

            def start(self, extraArgs=""):
                started.append(True)

        argv = sys.argv
        real = loader.Wesend
        folder = tempfile.mkdtemp()
        loader.Wesend = FakeWesend
        sys.argv = ["wesen", "-c", join(folder, "conf"), "--disablegui"]
        try:
            self.assertIsNone(loader.Loader())
            self.assertTrue(started)
            self.assertIsInstance(
                loader.Loader(run_immediately=False), FakeWesend
            )
        finally:
            sys.argv = argv
            loader.Wesend = real


class TestMetabolism(unittest.TestCase):
    def wesen(self, energy, world=None, position=None, **over):
        if world is None:
            world = makeWorld(world={"length": 40}, food={"count": 0})
        info = dict(world.infoAllWorld["wesen"], **over)
        info["source"] = "DrunkenSailor"
        info["energy"] = energy
        if position is not None:
            info["position"] = list(position)
        return world.AddObject(info)

    def test_upkeep_grows_with_the_body(self):
        small = self.wesen(100)
        big = self.wesen(10000)
        self.assertGreater(big.upkeep(), small.upkeep())
        self.assertAlmostEqual(
            big.upkeep(), 1 + 0.005 * 10000, places=6
        )

    def test_flat_upkeep_when_rate_is_zero(self):
        w = self.wesen(5000, upkeep_rate=0.0, upkeep=1)
        self.assertEqual(w.upkeep(), 1)

    def test_reproduce_costs_energy(self):
        w = self.wesen(1000, reproduce_cost=20, child_min_energy=60)
        w.time = 100
        before = w.energy
        child = w.Reproduce()
        self.assertTrue(child)
        childEnergy = w.worldObjects[child].energy
        self.assertEqual(childEnergy, (before - 20) // 2)
        self.assertEqual(w.energy, before - childEnergy - 20)

    def test_reproduce_fails_below_minimum_without_costing_time(self):
        w = self.wesen(100, reproduce_cost=20, child_min_energy=60)
        w.time = 100
        self.assertFalse(w.Reproduce())
        self.assertEqual(w.time, 100)

    def test_attack_factors_come_from_the_config(self):
        world = makeWorld(world={"length": 40}, food={"count": 0})
        attacker = self.wesen(
            600, world, [5, 5], attack_damage=0.5, attack_cost=0.25
        )
        victim = self.wesen(
            400, world, [5, 5], attack_damage=0.5, attack_cost=0.25
        )
        attacker.time = 100
        attacker.Attack(id(victim))
        self.assertEqual(victim.energy, 400 - int(600 * 0.5))
        self.assertEqual(attacker.energy, 600 - int(400 * 0.25))


class TestPersistenceOfNewState(unittest.TestCase):
    def test_world_roundtrip_keeps_seed_and_climate(self):
        world = makeWorld(
            world={"length": 60, "seed": 99},
            food={"count": 20},
            climate={"enable": True},
        )
        for _ in range(50):
            world.main()
        d = world.persist()
        self.assertEqual(d["world"]["seed"], 99)
        self.assertIn("climatestate", d)
        self.assertNotIn("climate", d["world"])
        other = World(d, createObjects=False)
        other.restore(d)
        self.assertEqual(
            other.climate.persist(), world.climate.persist()
        )
        self.assertEqual(
            other.climateState()["growth"],
            world.climateState()["growth"],
        )


class TestMessages(unittest.TestCase):
    """Talk and Broadcast, the two capabilities no source used until
    Rincewind: `Talk` used to raise NameError as soon as anything was
    within look range, because its range filter closed over the loop
    variable of the loop it was filtering."""

    def makeTwo(self, distance, where=10):
        world = makeWorld(world={"length": 60}, food={"count": 0})
        length = world.infoAllWorld["world"]["length"]
        info = dict(world.infoAllWorld["wesen"])
        info.update({"source": "GreatRabbit", "position": [10, 10]})
        speaker = world.AddObject(dict(info, position=[10, where]))
        info["position"] = [10, (where + distance) % length]
        listener = world.AddObject(dict(info))
        heard = []
        listener.wesenSource.Receive = lambda m: heard.append(m)
        listener.Receive = listener.wesenSource.Receive
        speaker.time = world.infoAllWorld["time"]["max"]
        return speaker, listener, heard

    def test_talk_reaches_a_wesen_in_look_range(self):
        speaker, listener, heard = self.makeTwo(5)
        self.assertTrue(speaker.Talk(id(listener), {"hello": 1}))
        self.assertEqual(heard, [{"hello": 1}])

    def test_talk_does_not_reach_beyond_look_range(self):
        # 30 apart in a world of 60 is the farthest two wesen can be:
        # any smaller gap would be within look range the short way round
        speaker, listener, heard = self.makeTwo(30)
        self.assertFalse(speaker.Talk(id(listener), {"hello": 1}))
        self.assertEqual(heard, [])

    def test_talk_reaches_across_the_seam(self):
        """the world is a torus for looking as well as for walking, so
        the edge of the map is not a wall to talk over"""
        speaker, listener, heard = self.makeTwo(5, where=58)
        self.assertEqual(listener.position, [10, 3])
        self.assertTrue(speaker.Talk(id(listener), {"hello": 1}))
        self.assertEqual(heard, [{"hello": 1}])

    def test_broadcast_reaches_everybody_in_talk_range(self):
        speaker, listener, heard = self.makeTwo(5)
        self.assertTrue(speaker.Broadcast({"news": 2}))
        self.assertEqual(heard, [{"news": 2}])


class TestSharedState(unittest.TestCase):
    """class attributes are genetic information: the same for every
    wesen of a source and for the whole game (see isolation.py)"""

    def makeSource(self):
        class Fake:
            __module__ = "Wesen.sources.Fake.main"
            TABLE = {"a": [1, 2]}
            notes = {}
            LIMIT = 7

            @classmethod
            def touch(cls):
                return cls.notes

        return Fake

    def tearDown(self):
        isolation.forget()

    def test_deep_freeze_is_read_only_all_the_way_down(self):
        frozen = isolation.deepFreeze({"a": [1, {"b": 2}], "c": {3}})
        with self.assertRaises(TypeError):
            frozen["a"] = 1
        self.assertEqual(frozen["a"][0], 1)
        with self.assertRaises(TypeError):
            frozen["a"][1]["b"] = 3
        self.assertIsInstance(frozen["c"], frozenset)

    def test_a_copy_of_something_frozen_is_ones_own(self):
        from copy import deepcopy

        frozen = isolation.deepFreeze({"a": {"b": [1, 2]}})
        mine = deepcopy(frozen)
        mine["a"] = 1
        self.assertEqual(dict(frozen)["a"]["b"], (1, 2))
        self.assertEqual(dict(frozen.copy()), {"a": frozen["a"]})

    def test_isolate_gives_every_wesen_its_own_copy(self):
        cls = self.makeSource()
        one = isolation.prepare(cls, "isolate")
        two = isolation.prepare(cls, "isolate")
        one.notes["x"] = 1
        self.assertEqual(two.notes, {})
        self.assertEqual(cls.notes, {})
        # ... and every wesen starts from the same genes, its own copy
        # of them, while the shared class keeps them frozen
        self.assertEqual(one.LIMIT, two.LIMIT)
        self.assertEqual(one.TABLE["a"], [1, 2])
        self.assertIsNot(one.TABLE, two.TABLE)
        self.assertEqual(cls.TABLE["a"], (1, 2))

    def test_isolate_refuses_a_write_to_the_shared_class(self):
        cls = self.makeSource()
        isolation.prepare(cls, "isolate")
        with self.assertRaises(TypeError):
            cls.notes["x"] = 1

    def test_strict_keeps_no_state_at_all(self):
        cls = self.makeSource()
        same = isolation.prepare(cls, "strict")
        self.assertIs(same, cls)
        with self.assertRaises(TypeError):
            same.notes["x"] = 1

    def test_allow_is_the_old_behaviour(self):
        cls = self.makeSource()
        same = isolation.prepare(cls, "allow")
        self.assertIs(same, cls)
        same.notes["x"] = 1
        self.assertEqual(cls.notes, {"x": 1})

    def test_module_globals_are_genes_too(self):
        import sys
        from types import ModuleType

        name = "Wesen.sources.Fake.main"
        module = ModuleType(name)
        module.TABLE = {"a": 1}
        cls = self.makeSource()
        module.WesenSource = cls
        sys.modules[name] = module
        try:
            isolation.prepare(cls, "isolate")
            with self.assertRaises(TypeError):
                module.TABLE["b"] = 2
            self.assertEqual(isolation.audit(), [])
            module.TABLE = {}
            self.assertIn(("Fake", "main.TABLE"), isolation.audit())
        finally:
            del sys.modules[name]

    def test_audit_reports_a_rebound_gene_once(self):
        cls = self.makeSource()
        isolation.prepare(cls, "isolate")
        self.assertEqual(isolation.audit(), [])
        cls.LIMIT = 8
        self.assertEqual(isolation.audit(), [("Fake", "LIMIT")])
        self.assertEqual(isolation.audit(), [])

    def test_a_method_is_not_state(self):
        cls = self.makeSource()
        isolation.prepare(cls, "isolate")
        for _ in range(3):
            self.assertEqual(isolation.audit(), [])

    def test_the_rules_are_readable_and_not_writable(self):
        world = makeWorld(world={"length": 60}, food={"count": 0})
        info = dict(world.infoAllWorld["wesen"])
        info.update({"source": "GreatRabbit", "position": [10, 10]})
        source = world.AddObject(dict(info)).wesenSource
        self.assertEqual(
            source.infoTime["move"], world.infoAllWorld["time"]["move"]
        )
        for shared in (
            source.infoTime,
            source.infoRange,
            source.infoFood,
            source.infoWorld,
            source.infoWorld["climate"],
        ):
            with self.assertRaises(TypeError):
                shared["letterbox"] = "hello"
        # ... and the season is still live under the view
        before = source.infoWorld["climate"]["growth"]
        world.climate.state["growth"] = before + 1
        self.assertEqual(
            source.infoWorld["climate"]["growth"], before + 1
        )

    def test_a_message_may_not_carry_a_live_object(self):
        world = makeWorld(world={"length": 60}, food={"count": 0})
        info = dict(world.infoAllWorld["wesen"])
        info.update({"source": "GreatRabbit", "position": [10, 10]})
        speaker = world.AddObject(dict(info))
        listener = world.AddObject(dict(info))
        heard = []
        listener.Receive = lambda m: heard.append(m)
        listener.wesenSource.Receive = listener.Receive
        speaker.time = world.infoAllWorld["time"]["max"]
        speaker.Broadcast({"me": speaker.wesenSource, "n": 3})
        self.assertEqual(heard[0]["n"], 3)
        self.assertIsInstance(heard[0]["me"], str)

    def test_a_message_is_delivered_as_a_value(self):
        world = makeWorld(world={"length": 60}, food={"count": 0})
        info = dict(world.infoAllWorld["wesen"])
        info.update({"source": "GreatRabbit", "position": [10, 10]})
        speaker = world.AddObject(dict(info))
        listener = world.AddObject(dict(info))
        heard = []
        listener.Receive = lambda m: heard.append(m)
        listener.wesenSource.Receive = listener.Receive
        speaker.time = world.infoAllWorld["time"]["max"]
        payload = {"cells": [1, 2, 3]}
        self.assertTrue(speaker.Broadcast(payload))
        self.assertEqual(heard[0]["cells"], (1, 2, 3))
        with self.assertRaises(TypeError):
            heard[0]["cells"] = 4
        # the sender keeps its own object, unfrozen
        payload["cells"].append(4)


if __name__ == "__main__":
    unittest.main()
