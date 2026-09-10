"""What a source does when it is told nonsense.

`Broadcast` reaches every wesen in range, of every source, so `Receive`
is the one method of a source that is called with input somebody else
chose. A colony's own protocol is the easy case; the interesting one is
a message shaped almost right, from a neighbour who is not a colleague,
or from one who is lying.

The rule these tests hold sources to is narrow and worth stating: a
message must never cost you your turn. Every colony here already means
to work that way - each wraps `Receive` in a `try` - and Rincewind's
handler was itself broken for months (it called a method that does not
exist), because nothing had ever raised inside the `try` for it to
handle. That is exactly the kind of bug that only a deliberately hostile
message finds.
"""

if __name__ == "__main__":
    import sys

    sys.path.append("../src")

import unittest

from Wesen.defaults import CONFIG_DEFAULTS
from Wesen.isolation import sealed
from Wesen.world import World

# the sources that speak, and the mark each puts on its own messages
SPEAKERS = {
    "Rincewind": "clacks/2",
    "Weatherwax": "weatherwax/1",
    "LuTze": "lutze/1",
    "Vetinari": "vetinari/1",
}


def hostileMessages(sigil):
    """what a source may be handed: rubbish, somebody else's protocol,
    and - the case that finds bugs - its own protocol, malformed"""
    return [
        None,
        42,
        "hello",
        [],
        (),
        {},
        {"s": "somebody/else", "news": [1, 2, 3]},
        # its own mark, and then nothing it expects
        {"s": sigil},
        {"s": sigil, "orders": True},
        {"s": sigil, "orders": {}},
        {"s": sigil, "orders": {"uid": None, "home": None}},
        {"s": sigil, "u": None, "cells": None},
        {"s": sigil, "cells": "not a mapping"},
        {"s": sigil, "cells": {"nonsense": object()}},
        {"s": sigil, "clock": "yesterday", "u": ["a", "list"]},
        {"s": sigil, "orders": {"role": 7, "uid": {"deep": [None]}}},
        # its own mark on something that is not a mapping at all
        [sigil, "orders"],
    ]


class TestReceiveSurvivesAnything(unittest.TestCase):
    """One wesen of each talking source, handed every message above."""

    def oneWesen(self, source):
        config = {k: dict(v) for k, v in CONFIG_DEFAULTS.items()}
        config["gui"]["enable"] = False
        config["world"].update(
            {"length": 60, "seed": 99, "Debug": lambda _: None}
        )
        config["wesen"].update({"sources": [source], "count": 1})
        config["food"]["count"] = 20
        world = World(config)
        # a few turns, so the wesen has some state to confuse
        for _ in range(5):
            world.main()
        wesen = next(
            o for o in world.objects.values() if o.objectType == "wesen"
        )
        return world, wesen

    def test_every_talking_source_survives_a_hostile_message(self):
        for source, sigil in sorted(SPEAKERS.items()):
            with self.subTest(source=source):
                world, wesen = self.oneWesen(source)
                for message in hostileMessages(sigil):
                    # delivered as the engine delivers it: frozen, and
                    # anything that is not a plain value replaced
                    try:
                        wesen.wesenSource.Receive(sealed(message))
                    except Exception as exc:  # noqa: BLE001
                        self.fail(
                            f"{source}.Receive raised "
                            f"{type(exc).__name__}: {exc}\n"
                            f"on the message {message!r}"
                        )
                self.assertFalse(wesen.dead, f"{source} died of a word")
                self.assertEqual(world.faults, {})

    def test_a_source_still_hears_its_colleagues(self):
        """the check that the test above is not passing because every
        Receive returns immediately"""
        world, speaker = self.oneWesen("Rincewind")
        info = dict(world.infoAllWorld["wesen"])
        info.update(
            {"source": "Rincewind", "position": list(speaker.position)}
        )
        listener = world.AddObject(info)
        heard = []
        # Broadcast delivers through the wesen's own Receive, which
        # PutInterface bound at birth; Talk goes through the source's.
        # Both are replaced here so the test does not depend on which
        listener.Receive = heard.append
        listener.wesenSource.Receive = heard.append
        speaker.time = speaker.infoTime["max"]
        self.assertTrue(
            speaker.Broadcast({"s": SPEAKERS["Rincewind"], "hello": 1})
        )
        self.assertEqual(len(heard), 1)
        self.assertEqual(heard[0]["hello"], 1)


class TestNobodySpeaksInAnothersName(unittest.TestCase):
    """The engine stamps every message with the source that sent it,
    last, so the note cannot be forged (see isolation.stamped). A wesen
    may still lie about anything it *says* - that is the game."""

    def twoSources(self, mine, theirs="DrunkenSailor"):
        """one wesen of each, standing on the same cell"""
        config = {k: dict(v) for k, v in CONFIG_DEFAULTS.items()}
        config["gui"]["enable"] = False
        config["world"].update(
            {"length": 60, "seed": 5, "Debug": lambda _: None}
        )
        config["wesen"].update({"sources": [mine, theirs], "count": 0})
        config["food"]["count"] = 10
        world = World(config)
        info = dict(world.infoAllWorld["wesen"])
        victim = world.AddObject(
            dict(info, source=mine, position=[30, 30])
        )
        forger = world.AddObject(
            dict(info, source=theirs, position=[30, 30])
        )
        for one in (victim, forger):
            one.time = one.infoTime["max"]
        return world, victim, forger

    def test_a_forged_message_is_ignored_and_costs_nothing(self):
        """the exploit: a stranger puts your sigil on rubbish. Ids come
        from closerLook and sigils are constants in a readable file, so
        both were free to guess"""
        for source, sigil in sorted(SPEAKERS.items()):
            with self.subTest(source=source):
                world, victim, forger = self.twoSources(source)
                before = dict(victim.wesenSource.__dict__)
                for forged in [
                    {"s": sigil, "u": 1},
                    {"s": sigil, "to": victim.wesenSource.id()},
                    {"s": sigil, "to": victim.wesenSource.id(), "o": 7},
                    {"s": sigil, "clock": "yesterday", "u": ["a"]},
                    # and a forged note on top of the forged message
                    {"s": sigil, "from": {"source": source, "id": 1}},
                ]:
                    forger.time = forger.infoTime["max"]
                    forger.Talk(victim.wesenSource.id(), forged)
                    forger.time = forger.infoTime["max"]
                    forger.Broadcast(forged)
                self.assertEqual(world.faults, {})
                self.assertFalse(victim.dead)
                self.assertEqual(
                    victim.wesenSource.__dict__.keys(), before.keys()
                )

    def test_the_note_says_who_really_sent_it(self):
        world, victim, forger = self.twoSources("Rincewind")
        heard = []
        victim.Receive = heard.append
        victim.wesenSource.Receive = heard.append
        forger.Broadcast({"s": "clacks/2", "from": {"source": "lies"}})
        self.assertEqual(len(heard), 1)
        self.assertEqual(
            heard[0]["from"]["source"],
            "DrunkenSailor",
            "a payload of its own overwrote the engine's note",
        )
        self.assertEqual(heard[0]["from"]["id"], forger.wesenSource.id())

    def test_a_colleague_is_still_believed(self):
        """the check that the guard has not simply closed the channel"""
        world, one, _ = self.twoSources("Rincewind")
        info = dict(world.infoAllWorld["wesen"])
        two = world.AddObject(
            dict(info, source="Rincewind", position=[30, 30])
        )
        two.time = two.infoTime["max"]
        one.time = one.infoTime["max"]
        heard = []
        two.Receive = heard.append
        two.wesenSource.Receive = heard.append
        one.Broadcast({"s": "clacks/2", "u": "someone", "t": 1})
        self.assertTrue(heard, "a colleague was not heard at all")
        self.assertTrue(
            two.wesenSource.fromColleague(heard[0]),
            "a genuine colleague failed the check",
        )


class TestEverySharedStateMode(unittest.TestCase):
    """Who sent a message is a rule of the game, not one of the things
    [wesen] shared_state relaxes: every mode stamps. What the setting
    decides is whether the message the listener gets can be written to."""

    def hearOneself(self, mode):
        config = {k: dict(v) for k, v in CONFIG_DEFAULTS.items()}
        config["gui"]["enable"] = False
        config["world"].update(
            {"length": 60, "seed": 5, "Debug": lambda _: None}
        )
        config["wesen"].update(
            {"sources": ["Rincewind"], "count": 0, "shared_state": mode}
        )
        config["food"]["count"] = 10
        world = World(config)
        info = dict(world.infoAllWorld["wesen"])
        speaker = world.AddObject(
            dict(info, source="Rincewind", position=[30, 30])
        )
        listener = world.AddObject(
            dict(info, source="Rincewind", position=[30, 30])
        )
        speaker.time = speaker.infoTime["max"]
        heard = []
        listener.Receive = heard.append
        listener.wesenSource.Receive = heard.append
        speaker.Broadcast({"s": "clacks/2", "u": "x", "t": 1})
        return listener, heard

    def test_a_colleague_is_recognised_in_every_mode(self):
        for mode in ("isolate", "strict", "allow"):
            with self.subTest(mode=mode):
                listener, heard = self.hearOneself(mode)
                self.assertEqual(len(heard), 1)
                self.assertTrue(
                    listener.wesenSource.fromColleague(heard[0]),
                    f"a colleague went unrecognised under {mode}",
                )

    def test_only_the_strict_modes_freeze_what_is_delivered(self):
        for mode in ("isolate", "strict"):
            _, heard = self.hearOneself(mode)
            with self.assertRaises(TypeError):
                heard[0]["mine now"] = 1
        _, heard = self.hearOneself("allow")
        heard[0]["mine now"] = 1  # the old game, unchanged


if __name__ == "__main__":
    unittest.main()
