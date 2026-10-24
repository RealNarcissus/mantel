"""Tests for proactivity: the rules, the budget, and the silence.

A nudge system earns trust by what it does *not* show, so most of these checks
are about suppression: quiet hours, the daily budget, no repeats, nothing when
disabled. The positives — an event soon, too much late, the morning brief —
are checked against a pinned clock too.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import calendar as calendar_store  # noqa: E402
from app import (
    fonts_env,  # noqa: F401,E402
    nudges,  # noqa: E402
    todos,  # noqa: E402
)


def write_ics(path: Path, start: datetime, duration_min: int, title: str,
              uid: str) -> None:
    path.write_text(
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\n"
        f"UID:{uid}\nSUMMARY:{title}\n"
        f"DTSTART:{start:%Y%m%dT%H%M%S}\n"
        f"DTEND:{start + timedelta(minutes=duration_min):%Y%m%dT%H%M%S}\n"
        "END:VEVENT\nEND:VCALENDAR\n")


def main() -> int:
    failures: list[str] = []
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="mantel-nudges-")
    os.environ.pop("MANTEL_ICS", None)

    # a pinned Wednesday at 10:00
    now = datetime(2026, 10, 28, 10, 0).timestamp()

    # --- an event starting soon -----------------------------------------
    ics = Path(tempfile.mkdtemp(prefix="mantel-nudges-ics-")) / "day.ics"
    write_ics(ics, datetime(2026, 10, 28, 10, 10), 30, "Design review", "d1")
    calendar_store.add_source(str(ics))

    policy = nudges.Proactivity()
    found = policy.plan(now)
    print(f"  plan: {[(n.key, n.title) for n in found]}")
    if not any(n.key.startswith("event:") for n in found):
        failures.append("an event starting in 10 minutes produced no nudge")

    due = policy.due(now)
    if not due:
        failures.append("nothing was allowed to be shown")
    nudge = due[0]
    policy.mark(nudge, now)
    again = [item.key for item in policy.due(now)]
    print(f"  after marking {nudge.key}, still due: {again}")
    if nudge.key in again:
        failures.append("a marked nudge repeated")
    if policy.shown != 1:
        failures.append(f"the day counter is wrong: {policy.shown}")

    # an event two hours out is not worth a notification
    far = now + 7200
    if any(n.key.startswith("event:") for n in policy.plan(far)):
        failures.append("a far-future event produced a nudge")

    # --- the budget ------------------------------------------------------
    tight = nudges.Proactivity(budget=1)
    for index in range(4):
        task = todos.add(f"Late thing {index}", due=now - 86400)
        if task is None:
            failures.append("could not add a task fixture")
    if len(tight.due(now)) > 1:
        failures.append("the budget did not cap the nudges")
    tight.mark(tight.due(now)[0], now)
    if tight.due(now):
        failures.append("the budget was not exhausted after one nudge")
    print(f"  budget=1 shown={tight.shown} remaining={tight.remaining(now)}")

    # the budget resets on a new day
    tomorrow = now + 86400
    if tight.remaining(tomorrow) != 1:
        failures.append("the budget did not reset on a new day")

    # --- quiet hours ------------------------------------------------------
    night = datetime(2026, 10, 28, 3, 0).timestamp()
    wide = nudges.Proactivity()
    print(f"  quiet at 03:00 -> {wide.quiet(night)}")
    if not wide.quiet(night):
        failures.append("quiet hours did not cover 03:00")
    if wide.quiet(now):
        failures.append("10:00 was treated as quiet")
    if wide.due(night):
        failures.append("a nudge was allowed during quiet hours")
    daytime = nudges.Proactivity(quiet_start=9, quiet_end=17)
    if not daytime.quiet(now):
        failures.append("a custom quiet window was ignored")

    # --- overdue threshold -------------------------------------------------
    quiet_policy = nudges.Proactivity(brief_hour=23)
    # three overdue tasks now exist (four were added, one may repeat)
    late_count = len([t for t in todos.all_tasks(include_done=False)
                      if t.due and t.due < now])
    print(f"  overdue tasks: {late_count}")
    if late_count >= nudges.OVERDUE_THRESHOLD:
        keys = [nudge.key for nudge in quiet_policy.plan(now)]
        if not any(key.startswith("overdue:") for key in keys):
            failures.append("enough overdue tasks did not produce a nudge")

    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="mantel-nudges-2-")
    under = nudges.Proactivity(brief_hour=23)
    todos.add("Single late thing", due=now - 86400)
    if any(nudge.key.startswith("overdue:") for nudge in under.plan(now)):
        failures.append("one overdue task was treated as too many")

    # --- the morning brief -------------------------------------------------
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="mantel-nudges-3-")
    todos.add("Something today", due=now)
    early = nudges.Proactivity(brief_hour=9)
    morning = datetime(2026, 10, 28, 8, 0).timestamp()
    if any(nudge.key.startswith("brief:") for nudge in early.plan(morning)):
        failures.append("the brief fired before its hour")
    late_enough = datetime(2026, 10, 28, 9, 30).timestamp()
    if not any(nudge.key.startswith("brief:")
               for nudge in early.plan(late_enough)):
        failures.append("the brief did not fire after its hour")
    first = [n for n in early.due(late_enough) if n.key.startswith("brief:")][0]
    early.mark(first, late_enough)
    if any(nudge.key.startswith("brief:") for nudge in early.due(late_enough)):
        failures.append("the brief fired twice in one day")

    # --- disabled means silence -------------------------------------------
    off = nudges.Proactivity(enabled=False)
    if off.due(now):
        failures.append("a disabled policy still produced nudges")

    # --- persistence ------------------------------------------------------
    saved = nudges.Proactivity(budget=5, brief_hour=7)
    saved.save()
    loaded = nudges.Proactivity.load()
    print(f"  reloaded: budget={loaded.budget} brief_hour={loaded.brief_hour}")
    if loaded.budget != 5 or loaded.brief_hour != 7:
        failures.append("the policy did not round-trip")

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        return 1
    print("  nudges: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
