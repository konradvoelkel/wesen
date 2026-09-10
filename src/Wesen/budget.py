"""A turn has to end.

The rules budget a wesen's ``time``: what it may *do* in a turn - look,
move, eat - and they say nothing at all about how long its code may take
to decide. A source that spends a second of thought per wesen per turn
is playing entirely by the rules and making everybody else's game
unplayable, and a source with a loop that never finishes ends the game
for the whole field.

So there is a second budget, in seconds of processor time, and this is
what enforces it: the timer is armed before a source is asked what to
do, and if it is still thinking when the timer runs out, the exception
the handler raises comes out inside its own code. The engine treats that
like any other rule violation - the turn is skipped and counted, and the
game goes on without it (see ``World.noteFault``).

Two decisions worth knowing about:

*Processor time, not wall clock* (``ITIMER_VIRTUAL``). A budget measured
against the wall would fire because some other program on the machine
happened to be busy, which is not the source's doing and would make a
result depend on what else was running.

*A game that trips the budget no longer replays.* Where a source is cut
off depends on how fast the machine is, so the seed stops being the
whole story. That is a real cost, and the reason the default is loose
enough that nothing sane reaches it: it is here to break a hang, not to
shave a strategy. A tournament that wants the tighter, fairer rule can
set ``[wesen] cpu_budget`` to whatever it likes - the measured spread is
in SOURCES.md - and accept that it is measuring speed as well as play.

Only where the platform has ``setitimer`` and only on the main thread,
which is to say everywhere this game is actually played but not on
Windows. Where it is unavailable, ``arm`` says so and the engine goes on
without a budget rather than pretending to have one.
"""

import signal
import threading

# set while a source is thinking, so the handler knows what to raise
_pending = None
_installed = False


def available():
    """can a source be interrupted at all here?

    ``setitimer`` is Unix-only, and a signal handler runs on the main
    thread, so a game driven from a worker thread cannot use one."""
    return hasattr(signal, "setitimer") and (
        threading.current_thread() is threading.main_thread()
    )


def _install():
    """puts the handler in place, once per process"""
    global _installed
    if _installed:
        return True
    try:
        signal.signal(signal.SIGVTALRM, _fired)
    except (ValueError, OSError, AttributeError):
        # not the main thread, or no such signal here
        return False
    _installed = True
    return True


def _fired(_signum, _frame):
    """raises inside whatever the source was doing at the time"""
    exception, message = _pending or (None, "")
    if exception is None:
        return
    raise exception(message)


def arm(seconds, exception, message):
    """start the clock. Returns True if a budget is really in force.

    `exception` is raised with `message` inside the source's own code
    when it runs out, so the engine sees it exactly where it would see
    a source raising anything else."""
    global _pending
    if not seconds or seconds <= 0 or not available() or not _install():
        return False
    _pending = (exception, message)
    # repeating, not one-shot: a source that catches the interrupt and
    # carries on gets it again, and again, until its turn really ends.
    # Nothing here can stop code that swallows everything and never
    # returns - as with the shared-state rule, this makes the rule the
    # default and the breach loud, it is not a sandbox
    signal.setitimer(signal.ITIMER_VIRTUAL, float(seconds), float(seconds))
    return True


def disarm():
    """stop the clock. Safe to call whether or not it was armed, and
    must be called on the way out however the turn ended."""
    global _pending
    _pending = None
    if available() and _installed:
        signal.setitimer(signal.ITIMER_VIRTUAL, 0.0)
