"""Genes, not a shared brain.

A source is one program played by many wesen, so anything it keeps on
its class is shared by every one of them. That is how the older colonies
in this game pass knowledge around: one wesen writes a map of the world
into a class attribute and every other wesen of that source reads it,
wherever it happens to stand. Nothing in the world carried the fact from
the one to the other - it is telepathy, and it makes `Talk` and
`Broadcast` pointless.

The rule this module enforces:

    **Class attributes are genetic information.** Every wesen of a
    source starts the game with the same values, they are the same for
    the whole game, and whatever a wesen learns afterwards is its own.
    Knowledge that is to travel from one wesen to another has to be
    said out loud.

`[wesen] shared_state` chooses how hard the rule is:

``allow``
    the old behaviour: class attributes are shared and writable.
``isolate`` (default)
    the shared class keeps the genes, frozen, and every wesen is given
    its own deep copy of the mutable ones. Code that writes through
    ``self`` or ``cls`` keeps working and simply stops being shared;
    code that writes to the class *by name* raises, because that is the
    telepathy itself.
``strict``
    the genes are frozen and nothing is copied: any attempt to keep
    state on the class fails, wherever it is written from. State
    belongs in the instance.

No setting can be airtight in Python - a determined source can still
hide state in its own module's globals, and this module reports what it
can see of that rather than preventing it. What the setting does is make
the rule the default and the violation loud. The other obvious way round
it, handing another wesen a mutable object through a message, is closed
in `Wesen.Talk` and `Wesen.Broadcast`, which freeze what they deliver.
"""

import sys
from copy import deepcopy
from types import FunctionType


class FrozenDict(dict):
    """a dict that cannot be written to.

    A `MappingProxyType` would do the same job, but it is not a `dict`,
    and the first thing anybody writes when a message arrives is
    `isinstance(message, dict)`. This is a real dict: it reads, copies,
    serialises and type-checks like one, and every way of changing it
    raises. (`dict.__setitem__` can still be called on it by name. The
    rule is a rule, not a sandbox.)"""

    __slots__ = ()

    def _no(self, *args, **kwargs):
        raise TypeError(
            "this mapping is frozen: class attributes are genetic "
            "information and a message is a value (see isolation.py)"
        )

    __setitem__ = _no
    __delitem__ = _no
    __ior__ = _no
    clear = _no
    pop = _no
    popitem = _no
    setdefault = _no
    update = _no

    def copy(self):
        return dict(self)

    # a copy of something frozen is your own, and mutable
    def __copy__(self):
        return dict(self)

    def __deepcopy__(self, memo):
        return {
            deepcopy(k, memo): deepcopy(v, memo) for k, v in self.items()
        }

    def __reduce__(self):
        return (dict, (dict(self),))


# containers a source can keep state in
MUTABLE = (dict, list, set, bytearray)
MODES = ("allow", "isolate", "strict")
DEFAULT_MODE = "isolate"
# how deep `deepFreeze` follows a structure before it gives up
MAX_DEPTH = 12


def deepFreeze(value, depth=0):
    """an immutable copy of value: dicts become read-only views, lists
    tuples, sets frozensets, and the same again for what is inside
    them. Anything else (numbers, strings, objects, functions) is
    returned unchanged, since it is either immutable or code."""
    if depth > MAX_DEPTH:
        return value
    if isinstance(value, dict):
        return FrozenDict(
            (k, deepFreeze(v, depth + 1)) for k, v in value.items()
        )
    if isinstance(value, (list, tuple)):
        return tuple(deepFreeze(v, depth + 1) for v in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(deepFreeze(v, depth + 1) for v in value)
    if isinstance(value, bytearray):
        return bytes(value)
    return value


# what a message may carry: values, not handles
VALUES = (bool, int, float, complex, str, bytes, type(None))


def sealed(value, depth=0):
    """a message as a value: containers frozen (see deepFreeze) and
    anything that is not a plain value replaced by a note of what it
    was. Handing another wesen a live object - `Broadcast({"me": self})`
    - would be a shared brain with extra steps, and it would outlast the
    moment the two were in range of each other."""
    if isinstance(value, VALUES):
        return value
    if depth > MAX_DEPTH:
        return f"<{type(value).__name__}>"
    if isinstance(value, dict):
        return FrozenDict(
            (sealed(k, depth + 1), sealed(v, depth + 1))
            for k, v in value.items()
        )
    if isinstance(value, (list, tuple)):
        return tuple(sealed(v, depth + 1) for v in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(sealed(v, depth + 1) for v in value)
    if isinstance(value, bytearray):
        return bytes(value)
    return f"<{type(value).__name__}>"


# the one key in a message that belongs to the engine and not to the
# wesen sending it
SENDER_KEY = "from"


def stamped(message, source, wesenid, freeze=True):
    """a sealed message with the engine's own note of who sent it.

    A sigil is a constant sitting in a file anybody can read and an id
    comes free with `closerLook`, so before this a wesen could say
    anything at all in another source's name - and three of the four
    colonies in this game could be stopped for a turn by a single
    forged word. The note is written by the engine and written *last*,
    so a payload carrying a `from` of its own is simply overwritten.

    What a wesen *says* may be a lie: that is the game, and a colony
    has to weigh what it is told. Who is saying it is not up for
    negotiation.

    Only a message that is a mapping can carry a note, there being
    nowhere to put one otherwise; a source that wants to be recognised
    sends a dict, as every one of them does.

    Every message is stamped, in every mode: who sent something is a
    rule of the game and not one of the things `[wesen] shared_state`
    relaxes. `freeze` is what that setting decides - under `allow` the
    note goes onto a plain copy, so the message stays as writable as it
    always was there."""
    if not isinstance(message, dict):
        return message
    envelope = {"source": source, "id": wesenid}
    if not freeze:
        return {**message, SENDER_KEY: envelope}
    return FrozenDict({**message, SENDER_KEY: FrozenDict(envelope)})


class ReadOnly(dict):
    """a live, read-only view of one of the engine's own dicts.

    The rules, the season and the terrain belong to the engine and every
    wesen in the game reads the same dicts, so a source may read them
    and may not use them as a letterbox. It has to stay *live* - the
    climate is updated in place every turn - so this is a real dict that
    shares its storage with the original through `__missing__` rather
    than a copy of it."""

    __slots__ = ("_source",)

    def __init__(self, source):
        super().__init__()
        object.__setattr__(self, "_source", source)

    def __missing__(self, key):
        return self._source[key]

    def __contains__(self, key):
        return key in self._source

    def __len__(self):
        return len(self._source)

    def __iter__(self):
        return iter(self._source)

    def keys(self):
        return self._source.keys()

    def values(self):
        return self._source.values()

    def items(self):
        return self._source.items()

    def get(self, key, default=None):
        return self._source.get(key, default)

    def copy(self):
        return dict(self._source)

    def __copy__(self):
        return dict(self._source)

    def __deepcopy__(self, memo):
        return deepcopy(dict(self._source), memo)

    def __reduce__(self):
        return (dict, (dict(self._source),))

    def __repr__(self):
        return repr(dict(self._source))

    def _no(self, *args, **kwargs):
        raise TypeError(
            "the engine's own dicts are read-only for a source: they "
            "are shared by every wesen in the game (see isolation.py)"
        )

    __setitem__ = _no
    __delitem__ = _no
    __ior__ = _no
    clear = _no
    pop = _no
    popitem = _no
    setdefault = _no
    update = _no


def readOnly(mapping):
    """a live, read-only view of one of the engine's dicts"""
    if isinstance(mapping, dict):
        return ReadOnly(mapping)
    return mapping


def isGeneticName(name):
    """dunder names are Python's own, not the source's"""
    return not (name.startswith("__") and name.endswith("__"))


def isState(value):
    """does this class attribute hold state rather than code?

    Methods, class- and staticmethods, properties and nested classes
    are the source's program; everything else is what it knows."""
    if isinstance(
        value, (FunctionType, classmethod, staticmethod, property, type)
    ):
        return False
    return not callable(value) and not hasattr(value, "__get__")


class Genes:
    """the shared class of one source: what it starts the game with,
    and what it is not allowed to change."""

    def __init__(self, cls):
        self.cls = cls
        # Wesen.sources.Dwarf.main, or Dwarf.main for a player's own
        # source package, or plain Dwarf for a single-file one
        parts = cls.__module__.split(".")
        self.source = parts[-2] if len(parts) > 1 else parts[-1]
        # a source is a package, and its modules have globals, which are
        # shared exactly as class attributes are. They cannot be handed
        # out per wesen (there is one module), so they are simply frozen
        package = cls.__module__.rsplit(".", 1)[0]
        self.modules = [
            module
            for name, module in list(sys.modules.items())
            if name == package or name.startswith(package + ".")
        ]
        # the mutable class attributes, as they were before any wesen
        # of this source existed: this is the material every wesen gets
        # a copy of
        self.template = {
            name: value
            for name, value in vars(cls).items()
            if isGeneticName(name) and isinstance(value, MUTABLE)
        }
        self.frozen = {
            name: deepFreeze(value)
            for name, value in self.template.items()
        }
        self.expected = {}
        self.globals = {}
        self.reported = set()

    def freeze(self):
        """replace the mutable genes on the shared class with frozen
        copies, and remember every gene, so that a rebinding can be
        told from the outside afterwards."""
        for name, value in self.frozen.items():
            setattr(self.cls, name, value)
        for module in self.modules:
            for name, value in list(vars(module).items()):
                if isGeneticName(name) and isinstance(value, MUTABLE):
                    setattr(module, name, deepFreeze(value))
        self.globals = {
            (module.__name__, name): value
            for module in self.modules
            for name, value in vars(module).items()
            if isGeneticName(name) and isState(value)
        }
        # what the class holds now, as the class itself holds it:
        # `getattr` on a classmethod builds a new bound method every
        # time, which would look like a change on every check
        self.expected = {
            name: value
            for name, value in vars(self.cls).items()
            if isGeneticName(name) and isState(value)
        }

    def child(self):
        """a private class for one wesen: the same genes, but its own
        copy of everything it could write into."""
        if not self.template:
            return self.cls
        return type(
            self.cls.__name__,
            (self.cls,),
            {
                name: deepcopy(value)
                for name, value in self.template.items()
            },
        )

    def rebound(self):
        """genes the source has replaced on the shared class since the
        game started - shared state that the freezing cannot catch,
        because a name can always be pointed at something new."""
        out = []
        classDict = vars(self.cls)
        for name, value in self.expected.items():
            now = classDict.get(name)
            if now is not value and name not in self.reported:
                self.reported.add(name)
                out.append(name)
        for (moduleName, name), value in self.globals.items():
            where = f"{moduleName.split('.')[-1]}.{name}"
            if where in self.reported:
                continue
            module = sys.modules.get(moduleName)
            if module is None:
                continue
            if vars(module).get(name) is not value:
                self.reported.add(where)
                out.append(where)
        return out


_genes: dict[type, Genes] = {}


def prepare(cls, mode=DEFAULT_MODE):
    """the class one new wesen of this source is to be built from.

    Called once per wesen, so it is on the hot path of a birth: all it
    does after the first call is copy a handful of small containers."""
    if mode not in MODES:
        mode = DEFAULT_MODE
    if mode == "allow":
        return cls
    genes = _genes.get(cls)
    if genes is None:
        genes = _genes[cls] = Genes(cls)
        genes.freeze()
    if mode == "strict":
        return cls
    return genes.child()


def audit():
    """[(source, name)] for every gene a source has rebound on its
    shared class since the last call. Cheap: an identity check per
    class attribute, and each name is reported only once."""
    found = []
    for genes in _genes.values():
        for name in genes.rebound():
            found.append((genes.source, name))
    return found


def sharing():
    """{source: [names]} of the mutable class attributes that were
    found and isolated, for the report at the start of a game."""
    return {
        genes.source: sorted(genes.template)
        for genes in _genes.values()
        if genes.template
    }


def forget():
    """drop everything (a new game in the same process)"""
    _genes.clear()
