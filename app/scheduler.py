"""The runner: fires due schedules while the app is open.

One timer for the whole app. On each tick it looks for schedules whose slot
has passed and runs them through the engine, recording the result against the
schedule and telling the UI so a notification can be raised.

It is deliberately conservative:

* only one run at a time, so a slow prompt never stacks up;
* a slot missed while the app was closed fires once on the next tick, not
  once per missed minute;
* a failed run is recorded with its error rather than retried in a loop.
"""
from __future__ import annotations

import time

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib, GObject  # noqa: E402

from app import engine as engine_mod
from app import schedules as store
from app import session as session_mod
from app.store import Store

#: How often the timer looks for work.
TICK_SECONDS = 30


class Scheduler(GObject.Object):
    """Runs schedules and reports what happened."""

    __gsignals__ = {
        # schedule, run
        "ran": (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
        # schedule, error message
        "failed": (GObject.SignalFlags.RUN_FIRST, None, (object, str)),
    }

    def __init__(self, engine: engine_mod.Engine, on_notify=None,
                 store: Store | None = None):
        super().__init__()
        self.engine = engine
        self.on_notify = on_notify
        self.store = store
        self._timer_id = 0
        self._running = False
        self._turn = None
        self._thread = None

    # -- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        if self._timer_id:
            return
        self._timer_id = GLib.timeout_add_seconds(TICK_SECONDS, self._tick)
        # an immediate pass catches up anything missed while the app was shut
        GLib.timeout_add_seconds(5, self._tick)

    def stop(self) -> None:
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = 0
        if self._turn is not None:
            self._turn.cancel()
            self._turn = None
        self._thread = None

    @property
    def running(self) -> bool:
        return self._running

    # -- the tick -----------------------------------------------------------
    def _tick(self) -> bool:
        if not self._running:
            for schedule in store.list_schedules():
                if schedule.due:
                    self.run(schedule)
                    break          # one at a time
        return True

    def run(self, schedule: store.Schedule) -> None:
        """Run one schedule now."""
        if self._running:
            return
        if not self.engine.available:
            return
        self._running = True
        started = time.time()
        self._thread = self._open_thread(schedule)
        session = session_mod.Session(
            self.engine, mode=schedule.mode, approval=schedule.approval,
            workspace=schedule.workspace)
        self._turn = self.engine.run(
            prompt=session.brief(schedule.prompt),
            conversation_id="",
            cwd=schedule.workspace or None,
            extra_flags=tuple(session.flags()),
        )
        self._turn.connect("finished",
                           lambda _t, r: self._finish(schedule, started, r))
        self._turn.connect("failed",
                           lambda _t, m: self._fail(schedule, started, m))

    # -- the thread --------------------------------------------------------
    def _open_thread(self, schedule: store.Schedule):
        """A conversation per run, so a scheduled result reads like any turn."""
        if self.store is None:
            return None
        try:
            conv = self.store.new(cwd=schedule.workspace or "")
            conv.title = (f"{schedule.title} · "
                          f"{time.strftime('%d %b %H:%M')}")
            conv.add("user", schedule.prompt)
            conv.begin_turn(schedule.prompt)
            self.store.save(conv)
            return conv
        except Exception:  # noqa: BLE001 - a thread is a bonus, not the run
            return None

    def _close_thread(self, text: str, error: str = "") -> str:
        """Finish the run's conversation; returns its id (or "")."""
        conv = self._thread
        self._thread = None
        if conv is None:
            return ""
        try:
            if error:
                # keep any partial answer, but the thread must show it failed
                conv.add("assistant", text or error, error=error)
            else:
                conv.add("assistant", text)
            conv.end_turn()
            self.store.save(conv)
            return conv.id
        except Exception:  # noqa: BLE001
            return ""

    def _finish(self, schedule: store.Schedule, started: float,
                result: dict) -> None:
        self._running = False
        self._turn = None
        status = str((result or {}).get("status") or "")
        text = str((result or {}).get("text") or "")
        error = str((result or {}).get("error") or "")
        thread_id = self._close_thread(text, error)
        run = store.Run(
            started=started, finished=time.time(),
            status=status or ("SUCCESS" if not error else "ERROR"),
            text=text[:2000], error=error[:500],
            conversation_id=thread_id or str(
                (result or {}).get("conversation_id") or ""),
        )
        store.record_run(schedule.id, run)
        if error or (status and status != "SUCCESS"):
            self.emit("failed", schedule, error or status)
        else:
            self.emit("ran", schedule, run)

    def _fail(self, schedule: store.Schedule, started: float,
              message: str) -> None:
        self._running = False
        self._turn = None
        thread_id = self._close_thread("", str(message))
        run = store.Run(started=started, finished=time.time(),
                        status="ERROR", error=str(message)[:500],
                        conversation_id=thread_id)
        store.record_run(schedule.id, run)
        self.emit("failed", schedule, str(message))

    # -- helpers ------------------------------------------------------------
    def next_due(self) -> float | None:
        """When the soonest schedule fires, for the UI to show."""
        times = [s.next_run for s in store.list_schedules()]
        times = [t for t in times if t]
        return min(times) if times else None
