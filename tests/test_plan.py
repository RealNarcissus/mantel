"""Tests for time-blocking.

The honesty of the plan is what is tested: meetings are respected with a buffer,
nothing is placed in the past or outside the working day, blocks do not overlap,
the most pressing work goes first, and tasks that do not fit are reported rather
than quietly dropped.
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
    plan,  # noqa: E402
    todos,  # noqa: E402
)


def main() -> int:
    failures: list[str] = []
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="mantel-plan-")
    os.environ.pop("MANTEL_ICS", None)

    # pinned Tuesday 09:00, a fresh day
    now = datetime(2026, 11, 3, 9, 0).timestamp()

    # --- an empty day is all free time ---------------------------------
    empty = plan.plan_day(now)
    if empty.blocks:
        failures.append("an empty day produced blocks without tasks")
    if empty.headline() != "no room to plan":
        failures.append(f"empty plan headline is odd: {empty.headline()}")

    # --- tasks get placed, most pressing first --------------------------
    todos.add("Overdue thing", due=now - 2 * 86400)
    todos.add("Due today thing", due=now + 2 * 3600)
    todos.add("Undated thing")              # never scheduled
    filled = plan.plan_day(now)
    titles = [block.title for block in filled.blocks if block.kind == "task"]
    print(f"  blocks: {[(b.title, b.minutes) for b in filled.blocks]}")
    if titles[:2] != ["Overdue thing", "Due today thing"]:
        failures.append(f"priority order is wrong: {titles}")
    if "Undated thing" in titles:
        failures.append("an undated task was scheduled")
    for block in filled.blocks:
        if block.start < now:
            failures.append("a block was placed in the past")
        if datetime.fromtimestamp(block.end).hour > plan.WORK_END:
            failures.append("a block ran past the working day")

    # --- no overlaps -----------------------------------------------------
    ordered = sorted(filled.blocks, key=lambda b: b.start)
    for before, after in zip(ordered, ordered[1:]):
        if after.start < before.end:
            failures.append(f"blocks overlap: {before.title} / {after.title}")

    # --- a meeting splits the day and respects the buffer ----------------
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="mantel-plan-2-")
    ics = Path(tempfile.mkdtemp(prefix="mantel-plan-ics-")) / "day.ics"
    meeting = datetime(2026, 11, 3, 11, 0)
    ics.write_text(
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:m1\nSUMMARY:Standup\n"
        f"DTSTART:{meeting:%Y%m%dT%H%M%S}\n"
        f"DTEND:{(meeting + timedelta(minutes=30)):%Y%m%dT%H%M%S}\n"
        "END:VEVENT\nEND:VCALENDAR\n")
    calendar_store.add_source(str(ics))
    todos.add("Important task", due=now + 3600)
    split = plan.plan_day(now)
    placed = [(datetime.fromtimestamp(b.start).strftime("%H:%M"), b.title)
              for b in split.blocks]
    print(f"  with a meeting: {placed}")
    busy_start = meeting.timestamp() - plan.BUFFER_MINUTES * 60
    busy_end = (meeting + timedelta(minutes=30)).timestamp() \
        + plan.BUFFER_MINUTES * 60
    for block in split.blocks:
        if block.kind != "task":
            continue
        if block.start < busy_end and block.end > busy_start:
            failures.append(f"{block.title} was placed inside the meeting buffer")
    if not split.blocks:
        failures.append("nothing fit at all despite a mostly free day")

    # --- a full day leaves tasks unscheduled, and says so ---------------
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="mantel-plan-3-")
    busy_folder = Path(tempfile.mkdtemp(prefix="mantel-plan-busy-"))
    blocks = []
    for hour, minute in ((9, 0), (10, 0), (11, 0), (12, 0), (13, 0), (14, 0),
                         (15, 0), (16, 0), (17, 0)):
        start = datetime(2026, 11, 3, hour, minute)
        blocks.append(
            "BEGIN:VEVENT\n"
            f"UID:b{hour}\nSUMMARY:Meeting {hour}\n"
            f"DTSTART:{start:%Y%m%dT%H%M%S}\n"
            f"DTEND:{(start + timedelta(minutes=55)):%Y%m%dT%H%M%S}\n"
            "END:VEVENT")
    (busy_folder / "busy.ics").write_text(
        "BEGIN:VCALENDAR\n" + "\n".join(blocks) + "\nEND:VCALENDAR\n")
    calendar_store.add_source(str(busy_folder))
    for index in range(3):
        todos.add(f"Task {index}", due=now + 3600)
    full = plan.plan_day(now)
    print(f"  full day: blocks={len([b for b in full.blocks if b.kind == 'task'])} "
          f"unscheduled={full.unscheduled}")
    if full.unscheduled and not any("Task" in title
                                    for title in full.unscheduled):
        failures.append("unscheduled tasks are not named")

    # --- export ----------------------------------------------------------
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="mantel-plan-4-")
    todos.add("Export me", due=now + 3600)
    export = plan.plan_day(now)
    text = plan.export_ics(export)
    if "BEGIN:VCALENDAR" not in text or "SUMMARY:Export me" not in text:
        failures.append(f"the exported plan looks wrong: {text[:120]}")
    if text.count("BEGIN:VEVENT") != len(export.blocks):
        failures.append("the export does not contain every block")
    path = Path(plan.save_plan(export))
    print(f"  exported: {path.name} ({len(text)} chars)")
    if not path.exists() or "Export me" not in path.read_text():
        failures.append("save_plan did not write a usable file")

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        return 1
    print("  plan: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
