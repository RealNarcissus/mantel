"""Tests for the cron engine and the schedule store.

Verifies the parts that decide *when* the agent runs something, and that a
schedule survives a restart. No engine and no GUI needed.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import schedules as store  # noqa: E402


def main() -> int:
    failures: list[str] = []

    # --- cron parsing ------------------------------------------------------
    print("  cron: parsing")
    for expr in ("0 9 * * *", "0 9 * * 1-5", "*/15 * * * *", "0 17 * * 1",
                 "30 8 1 * *", "0 0 * * 0"):
        try:
            store.validate_cron(expr)
        except ValueError as exc:
            failures.append(f"{expr!r} rejected: {exc}")
    for bad in ("", "0 9 * *", "60 * * * *", "* 24 * * *", "0 9 * * 8",
                "a b c d e"):
        try:
            store.validate_cron(bad)
        except ValueError:
            pass
        else:
            failures.append(f"{bad!r} should have been rejected")
    print(f"      {len(failures)} problems so far")

    # --- next run ----------------------------------------------------------
    print("  cron: next run")
    now = time.time()
    nxt = store.next_run("0 9 * * *", after=now)
    if nxt is None:
        failures.append("a daily 09:00 schedule has no next run")
    else:
        when = time.localtime(nxt)
        if when.tm_hour != 9 or when.tm_min != 0:
            failures.append(f"daily 09:00 resolved to {when.tm_hour}:"
                            f"{when.tm_min}")
        if not (0 < nxt - now <= 86400 + 60):
            failures.append("daily 09:00 is not within a day")
        print(f"      next 09:00 in {(nxt - now) / 3600:.1f} h")

    # a weekday schedule must not land on the weekend
    nxt = store.next_run("0 9 * * 1-5", after=now)
    if nxt is not None and time.localtime(nxt).tm_wday >= 5:
        failures.append("weekday schedule landed on a weekend")
    print(f"      next weekday run: {time.strftime('%a %H:%M', time.localtime(nxt))}"
          if nxt else "      none")

    # every-15-minutes advances by 15
    first = store.next_run("*/15 * * * *", after=now)
    second = store.next_run("*/15 * * * *", after=first)
    if first and second and (second - first) != 900:
        failures.append(f"*/15 stepped {second - first}s instead of 900")

    # --- descriptions ------------------------------------------------------
    print("  cron: descriptions")
    for expr, wanted in (
        ("0 9 * * 1-5", "every weekday at 09:00"),
        ("0 18 * * *", "every day at 18:00"),
        ("0 17 * * 1", "every Monday at 17:00"),
        ("0 9 * * *", "every day at 09:00"),
    ):
        got = store.describe_cron(expr)
        if got != wanted:
            failures.append(f"describe({expr!r}) = {got!r}, wanted {wanted!r}")
        else:
            print(f"      {expr:14} -> {got}")

    # --- the store ---------------------------------------------------------
    print("  store: save / load / pause / delete")
    tmp = tempfile.mkdtemp(prefix="gemini-sched-")
    os.environ["XDG_DATA_HOME"] = tmp
    os.environ["HOME"] = tmp

    if store.list_schedules():
        failures.append("a fresh store should be empty")

    schedule = store.Schedule(title="Morning briefing",
                              prompt="Summarise yesterday.",
                              cron="0 9 * * 1-5", mode="task")
    if not store.save(schedule):
        failures.append("could not save a schedule")
    loaded = store.list_schedules()
    if len(loaded) != 1:
        failures.append(f"expected 1 schedule, got {len(loaded)}")
    elif loaded[0].title != "Morning briefing":
        failures.append("the title did not survive the round trip")

    # due-ness: a schedule that has never run and is not due yet
    if loaded:
        if loaded[0].due:
            failures.append("a future schedule reported itself due")
        if loaded[0].next_run is None:
            failures.append("an active schedule has no next run")

    # pause / resume
    store.set_paused(schedule.id, True)
    paused = store.list_schedules()[0]
    if not paused.paused:
        failures.append("pause did not persist")
    if paused.next_run is not None:
        failures.append("a paused schedule still has a next run")
    if paused.due:
        failures.append("a paused schedule reported itself due")
    print("      paused schedule has no next run")

    store.set_paused(schedule.id, False)
    if store.list_schedules()[0].paused:
        failures.append("resume did not persist")

    # a run is recorded, and completes the schedule's history
    run = store.Run(started=time.time(), finished=time.time(),
                    status="SUCCESS", text="All quiet.")
    store.record_run(schedule.id, run)
    after = store.list_schedules()[0]
    if len(after.runs) != 1:
        failures.append(f"expected 1 run, got {len(after.runs)}")
    if after.last_run == 0:
        failures.append("last_run was not set")

    # a schedule whose slot has passed is due
    overdue = store.Schedule(title="Overdue", prompt="x", cron="* * * * *")
    store.save(overdue)
    overdue = next(s for s in store.list_schedules() if s.id == overdue.id)
    # never run, every minute: due whenever the current minute matches
    print(f"      every-minute schedule due={overdue.due}")

    # one-shot history cap
    for i in range(30):
        store.record_run(schedule.id, store.Run(started=time.time(),
                                                status="SUCCESS"))
    capped = next(s for s in store.list_schedules() if s.id == schedule.id)
    if len(capped.runs) > 20:
        failures.append(f"run history grew to {len(capped.runs)}, expected <=20")
    print(f"      history capped at {len(capped.runs)} runs")

    # delete
    store.delete(schedule.id)
    if any(s.id == schedule.id for s in store.list_schedules()):
        failures.append("delete did not remove the schedule")

    # a corrupted store does not crash
    store.store_path().write_text("{not json")
    if store.list_schedules() != []:
        failures.append("a corrupt store should read as empty")
    print("      corrupt store reads as empty")

    print()
    if failures:
        for f in failures:
            print(f"  FAIL: {f}")
        return 1
    print("  schedules: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
