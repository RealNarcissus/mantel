"""Focus sessions: a timer that belongs to the day, not to a widget.

A pomodoro timer is trivial to draw and easy to get subtly wrong: pausing must
freeze the clock, a session that finishes while the window is closed must not
count as running, and the state has to be read from the model rather than from
a UI signal that may have been missed.

The timer here is a small state machine over a monotonic clock, with the clock
injectable so the tests can move time without sleeping.
"""
from __future__ import annotations

import time

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib, GObject  # noqa: E402

TICK_MS = 1000


class FocusTimer(GObject.Object):
    """One focus session, optionally ticking on the main loop."""

    __gsignals__ = {
        # remaining_seconds, total_seconds
        "tick": (GObject.SignalFlags.RUN_FIRST, None, (int, int)),
        "finished": (GObject.SignalFlags.RUN_FIRST, None, ()),
        # running: bool
        "state": (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
    }

    def __init__(self, minutes: int = 25, clock=time.monotonic) -> None:
        super().__init__()
        self.total = max(1, int(minutes)) * 60
        self._clock = clock
        self._elapsed = 0.0          # frozen progress, in seconds
        self._started_at = 0.0
        self._running = False
        self._finished = False
        self._timer_id = 0

    # -- derived -----------------------------------------------------------
    @property
    def elapsed(self) -> float:
        if self._running:
            return self._elapsed + (self._clock() - self._started_at)
        return self._elapsed

    @property
    def remaining(self) -> int:
        return max(0, int(self.total - self.elapsed))

    @property
    def running(self) -> bool:
        return self._running

    @property
    def finished(self) -> bool:
        return self._finished or self.remaining <= 0

    # -- control -----------------------------------------------------------
    def start(self) -> None:
        if self._running or self.finished:
            return
        self._running = True
        self._started_at = self._clock()
        self._arm()
        self.emit("tick", self.remaining, self.total)
        self.emit("state", True)

    def pause(self) -> None:
        if not self._running:
            return
        self._elapsed = self.elapsed
        self._running = False
        self._disarm()
        self.emit("tick", self.remaining, self.total)
        self.emit("state", False)

    def toggle(self) -> None:
        (self.pause if self._running else self.start)()

    def reset(self, minutes: int | None = None) -> None:
        self._disarm()
        if minutes is not None:
            self.total = max(1, int(minutes)) * 60
        self._elapsed = 0.0
        self._running = False
        self._finished = False
        self.emit("tick", self.remaining, self.total)
        self.emit("state", False)

    def stop(self) -> None:
        """Release the GLib timer (window closing)."""
        self._disarm()

    # -- the clock ---------------------------------------------------------
    def check(self) -> bool:
        """Recompute; emit `finished` once when the session runs out."""
        self.emit("tick", self.remaining, self.total)
        if self._running and self.remaining <= 0:
            self._elapsed = self.total
            self._running = False
            self._finished = True
            self._disarm()
            self.emit("state", False)
            self.emit("finished")
            return True
        return False

    def _arm(self) -> None:
        if not self._timer_id:
            self._timer_id = GLib.timeout_add(TICK_MS, self._on_tick)

    def _disarm(self) -> None:
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = 0

    def _on_tick(self) -> bool:
        if not self._running:
            return False
        if self.check():
            return False
        return True
