"""Tests for the focus timer.

Time is injected, so these run instantly and deterministically: start, pause,
resume, finish once, and the awkward cases (pausing a finished session,
resetting mid-run, checking while stopped).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import fonts_env  # noqa: F401,E402

import gi  # noqa: E402

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from app.focus import FocusTimer  # noqa: E402


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def main() -> int:
    failures: list[str] = []
    clock = Clock()

    timer = FocusTimer(minutes=25, clock=clock)
    if timer.total != 1500:
        failures.append(f"25 minutes is {timer.total}s, not 1500")
    if timer.remaining != 1500 or timer.running:
        failures.append("a fresh timer should be full and stopped")
    print(f"  fresh: {timer.remaining}s remaining, running={timer.running}")

    # --- pausing freezes the clock --------------------------------------
    timer.start()
    clock.advance(60)
    if timer.remaining != 1440:
        failures.append(f"after 60s remaining={timer.remaining}, wanted 1440")
    timer.pause()
    clock.advance(600)          # ten minutes go by while paused
    if timer.remaining != 1440:
        failures.append(f"paused timer advanced to {timer.remaining}")
    timer.start()               # resume
    clock.advance(30)
    print(f"  resumed: {timer.remaining}s remaining (60+30 elapsed)")
    if timer.remaining != 1410:
        failures.append(f"resume lost time: {timer.remaining}")

    # --- finishing ------------------------------------------------------
    finished = {"count": 0}
    timer.connect("finished", lambda _t: finished.update(
        count=finished["count"] + 1))
    states = []
    timer.connect("state", lambda _t, running: states.append(running))
    clock.advance(1410)
    if not timer.check():
        failures.append("check() did not report a finished session")
    if not timer.finished:
        failures.append("the timer does not consider itself finished")
    if timer.remaining != 0:
        failures.append(f"finished timer has {timer.remaining}s left")
    if timer.running:
        failures.append("a finished timer is still running")
    timer.check()
    print(f"  finished events: {finished['count']}; state events: {states}")
    if finished["count"] != 1:
        failures.append(f"finished fired {finished['count']} times, wanted 1")

    # starting a finished timer is a no-op until reset
    timer.start()
    if timer.running:
        failures.append("a finished timer restarted without reset")

    # --- reset ----------------------------------------------------------
    timer.reset()
    if timer.remaining != 1500 or timer.finished or timer.running:
        failures.append("reset did not restore the timer")
    timer.reset(minutes=5)
    if timer.total != 300:
        failures.append(f"reset with a duration gave {timer.total}s")
    print(f"  reset to 5 min: {timer.remaining}s")

    # --- pausing a stopped timer ---------------------------------------
    timer.pause()
    if timer.running or timer.elapsed != 0:
        failures.append("pausing a stopped timer changed its state")

    # --- no GLib timers left behind ------------------------------------
    timer.start()
    timer.stop()
    print("  stopped cleanly")
    if GLib.MainContext.default().pending():
        failures.append("timers were left pending after stop()")

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        return 1
    print("  focus timer: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
