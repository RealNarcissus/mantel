"""Reminders: the minute-level check that turns a due time into a poke.

Scheduled prompts run on a cron engine (`app/scheduler.py`); reminders are
different — they are the user's own tasks coming due, so they are checked far
more often and never leave the machine.

The honest contract, same as Claude desktop's local tasks: a reminder fires
while Mantel is open. A task whose time passed while the app was closed fires
once on the next tick rather than being skipped.
"""
from __future__ import annotations

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib, GObject  # noqa: E402

from app import todos

#: How often reminders are checked. A minute is the natural granularity.
TICK_SECONDS = 30


class ReminderRunner(GObject.Object):
    """Watches the task store and reports reminders as they come due."""

    __gsignals__ = {
        # task
        "due": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self) -> None:
        super().__init__()
        self._timer_id = 0

    def start(self) -> None:
        if self._timer_id:
            return
        self._timer_id = GLib.timeout_add_seconds(TICK_SECONDS, self._tick)
        GLib.timeout_add_seconds(3, self._tick)

    def stop(self) -> None:
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = 0

    def _tick(self) -> bool:
        try:
            due = todos.due_reminders()
        except Exception:  # noqa: BLE001 - never let a reminder kill the timer
            due = []
        for task in due:
            # mark first: a notification that fails must not repeat forever
            try:
                todos.mark_reminded(task.id)
            except Exception:  # noqa: BLE001
                pass
            self.emit("due", task)
        return True
