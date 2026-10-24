"""End-to-end: a schedule actually fires an agent turn.

Creates a schedule that is due, runs the scheduler against the real engine,
and checks that the run is recorded with a real answer. Uses a throwaway data
directory so it never touches the user's schedules.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import fonts_env  # noqa: F401,E402

import gi  # noqa: E402

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from app import engine as engine_mod  # noqa: E402
from app import schedules as store  # noqa: E402
from app.scheduler import Scheduler  # noqa: E402


def main() -> int:
    engine = engine_mod.Engine()
    if not engine.available:
        print("  SKIP: no engine binary")
        return 0

    tmp = tempfile.mkdtemp(prefix="gemini-schedrun-")
    os.environ["XDG_DATA_HOME"] = tmp

    # a schedule that is overdue: created an hour ago, never run
    schedule = store.Schedule(
        title="Scheduler smoke test",
        prompt="Reply with exactly: SCHEDULE-FIRED",
        cron="0 * * * *",
        mode="chat",
        created=time.time() - 7200,
    )
    store.save(schedule)
    schedule = store.list_schedules()[0]
    print(f"  schedule: {schedule.title!r} due={schedule.due}")

    failures: list[str] = []
    if not schedule.due:
        failures.append("an overdue schedule did not report itself due")

    loop = GLib.MainLoop()
    state: dict = {}

    scheduler = Scheduler(engine)
    scheduler.connect("ran", lambda _s, sch, run: (
        state.update(ran=True, run=run, title=sch.title), loop.quit()))
    scheduler.connect("failed", lambda _s, sch, msg: (
        state.update(ran=False, error=msg), loop.quit()))

    print("  running the schedule through the engine…")
    scheduler.run(schedule)

    GLib.timeout_add_seconds(240, lambda: (loop.quit(), False)[1])
    loop.run()

    run = state.get("run")
    if run is None:
        failures.append(f"the schedule produced no run: "
                        f"{state.get('error', 'timed out')}")
    else:
        print(f"  status: {run.status}")
        print(f"  answer: {run.text.strip()[:80]!r}")
        if "SCHEDULE-FIRED" not in run.text:
            failures.append(f"unexpected answer: {run.text[:80]!r}")
        if run.finished <= run.started:
            failures.append("the run has no duration")

    # the run is persisted against the schedule
    stored = next((s for s in store.list_schedules()
                   if s.title == "Scheduler smoke test"), None)
    if stored is None:
        failures.append("the schedule disappeared")
    else:
        print(f"  recorded runs: {len(stored.runs)}  last_run set: "
              f"{bool(stored.last_run)}")
        if not stored.runs:
            failures.append("the run was not persisted")
        if not stored.last_run:
            failures.append("last_run was not advanced")
        # after running, it should not be due again immediately
        if stored.due:
            failures.append("the schedule is still due right after running")
        else:
            print("  not due again right after running")

    print()
    if failures:
        for f in failures:
            print(f"  FAIL: {f}")
        return 1
    print("  the scheduler fires real agent turns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
