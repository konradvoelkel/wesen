"""The Loader function determines which configfile to use
and interprets command-line arguments.
It makes sure that the configured wesen sources exist.
It then runs a Wesend instance."""

import sys
from argparse import Action, ArgumentParser
from os import makedirs

from .configed import ConfigEd
from .defaults import DEFAULT_CONFIGFILE
from .sourceloader import (
    DEFAULT_SOURCE_DIR,
    SourceError,
    loadSource,
    setSearchPath,
)
from .strings import (
    STRING_USAGE_CONFIGFILE,
    STRING_USAGE_DEFAULTCONFIG,
    STRING_USAGE_DESCRIPTION,
    STRING_USAGE_EDITCONFIG,
    STRING_USAGE_EPILOG,
    STRING_USAGE_OVERWRITE,
    STRING_USAGE_PRINTCONFIG,
    STRING_USAGE_RESUME,
    VERSIONSTRING,
)
from .variation import applySeed
from .wesend import Wesend


def Loader(run_immediately=True):
    """Calling a Loader object will start a Wesen simulation,
    if the found configuration allows it.

    First, looks for the config file location
    provided by command-line (or using a fallback).
    Then, using ConfigEd, getting the config
    (using fallback config from defaults.py)
    and modifying it according to command-line parameters.
    Then it checks whether the provided sources exist,
    and runs a Wesen simulation with the given config.

    If you want to manipulate the Wesen simulation
    before the start, pass run_immediately=False,
    then Loader returns a Wesend instance,
    which you can start by start()"""
    _ensureSourceFolder()
    parsedArgs, extraArgs = _parseArgs()
    configEd = ConfigEd(parsedArgs.configfile)
    if parsedArgs.invoke_defaultconfig:
        configEd.writeDefaults()
    if parsedArgs.invoke_editconfig:
        configEd.edit()
    if parsedArgs.invoke_printconfig:
        configEd.printConfig()
    config = configEd.getConfig()
    if "_config" in parsedArgs:
        for section, sectionDict in parsedArgs._config.items():
            config[section].update(sectionDict)
    config["resume"] = parsedArgs.resume
    if len(extraArgs) > 0:
        print(
            "handing over the following command-line arguments to OpenGL: ",
            " ".join(extraArgs),
        )
    setSearchPath(config["wesen"].get("sourcepath", ""))
    # The sources are imported next. A source that draws random numbers
    # while its module is being read would be drawing them outside the
    # game, and the same seed would play a different game every time;
    # seeding here means even that is reproducible. Wesend seeds again
    # from the same number - or from a resumed game's - and announces
    # it. Sources should use self.gameRandom() and not draw at import.
    applySeed(config, announce=False)
    _checkSourcesAvailability(config["wesen"]["sources"])
    wesend = Wesend(config)
    if run_immediately:
        wesend.start()
        # the console script exits with whatever this returns, and
        # sys.exit(anything but None or an int) prints it and fails, so
        # a game that ran to its end must return nothing
        return None
    return wesend


def _ensureSourceFolder():
    """Makes sure the folder where a player keeps their own AI code
    exists, so that it can be found rather than explained. Where the
    game looks is decided in sourceloader.py."""
    makedirs(DEFAULT_SOURCE_DIR, exist_ok=True)


def _parseArgs():
    """returns the result of an ArgumentParser.parse_known_args call"""
    # HINT: If you consider adding an option,
    #      please consider adding a config file option first.
    parser = ArgumentParser(
        description=STRING_USAGE_DESCRIPTION, epilog=STRING_USAGE_EPILOG
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s (" + VERSIONSTRING + ")",
    )
    parser.add_argument(
        "-c",
        "--configfile",
        action="store",
        dest="configfile",
        default=DEFAULT_CONFIGFILE,
        help=STRING_USAGE_CONFIGFILE,
    )
    parser.add_argument(
        "-e",
        "--editconfig",
        action="store_true",
        dest="invoke_editconfig",
        default=False,
        help=STRING_USAGE_EDITCONFIG,
    )
    parser.add_argument(
        "--defaultconfig",
        action="store_true",
        dest="invoke_defaultconfig",
        default=False,
        help=STRING_USAGE_DEFAULTCONFIG,
    )
    parser.add_argument(
        "--printconfig",
        action="store_true",
        dest="invoke_printconfig",
        default=False,
        help=STRING_USAGE_PRINTCONFIG,
    )
    _addOverwriteBool(parser, "gui", "gui", "enable")
    parser.add_argument(
        "-s",
        "--sources",
        section="wesen",
        dest="sources",
        action=_OverwriteConfigAction,
    )
    parser.add_argument(
        "-p",
        "--sourcepath",
        section="wesen",
        dest="sourcepath",
        action=_OverwriteConfigAction,
    )
    parser.add_argument(
        "-r",
        "--resume",
        dest="resume",
        action="store_true",
        default=False,
        help=STRING_USAGE_RESUME,
    )
    return parser.parse_known_args()


def _addOverwriteBool(parser, argName, section, key):
    """for convenience, adds a mutually exclusive group
    with --enable and --disable argName, to modify [section] key"""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--enable" + argName,
        section=section,
        dest=key,
        storeValue=True,
        action=_OverwriteConfigActionBool,
    )
    group.add_argument(
        "--disable" + argName,
        section=section,
        dest=key,
        storeValue=False,
        action=_OverwriteConfigActionBool,
    )


def _checkSourcesAvailability(sourcesList):
    """loads every source listed in sourcesList, so that a name that is
    not there, or code that does not import, is said plainly now rather
    than found halfway into building the world."""
    if isinstance(sourcesList, str):
        sourcesList = sourcesList.split(",")
    for source in sourcesList:
        try:
            loadSource(source.strip())
        except SourceError as e:
            print(f"wesen: {e}")
            sys.exit(1)


class _OverwriteConfigAction(Action):
    """An ArgumentParser Action that stores in a dict
    called _config in the namespace
    which config option should be overwritten by command-line."""

    # TODO change name _config to sth else, as its not a protected member

    def __init__(self, option_strings, dest, section, nargs=1):
        helpMessage = STRING_USAGE_OVERWRITE % (section, dest)
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=nargs,
            const=False,
            default=None,
            required=False,
            help=helpMessage,
        )
        self.section = section

    def __call__(self, parser, namespace, values, option_string=None):
        if len(values) != 1:
            raise ValueError(
                "wrong number of values for config option to overwrite: [",
                self.section,
                "]",
                self.dest,
                "=",
                ",".join(values),
            )
        else:
            # print("Overwritten config option: [",
            #      self.section, "]",
            #      self.dest, "=",
            #      values[0]);
            if "_config" not in namespace:
                namespace._config = {}
            if self.section not in namespace._config.keys():
                namespace._config[self.section] = {}
            namespace._config[self.section][self.dest] = values[0]


class _OverwriteConfigActionBool(_OverwriteConfigAction):
    """For convenience, storing True/False as specified"""

    def __init__(self, option_strings, dest, section, storeValue=None):
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            section=section,
            nargs=0,
        )
        self.storeValue = storeValue

    def __call__(self, parser, namespace, values, option_string=None):
        if self.storeValue is not None:
            values = [self.storeValue]
        super().__call__(parser, namespace, values)
