"""Tests for the weekly review.

The review is only useful if its numbers are true, so these tests build a known
week out of the real stores — completed tasks, overdue ones, focus log entries,
memory facts and calendar events — then assert the arithmetic against a pinned
clock.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import fonts_env  # noqa: F401,E402

from app import calendar as calendar_store  # noqa: E402
from app import memory  # noqa: E402
from app import review  # noqa: E402
from app import todos  # noqa: E402


def main() -> int:
    failures: list[str] = []
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="mantel-review-")
    os.environ.pop("MANTEL_ICS", None)
    memory.clear()

    # build the week around the real clock: memory and focus records are
    # stamped with it, so a pretend future would exclude them
    now = time.time()
    start, end = review.week_bounds(now)
    print(f"  week: {datetime.fromtimestamp(start):%a %d %b} -> "
          f"{datetime.fromtimestamp(end):%a %d %b}")
    if datetime.fromtimestamp(start).weekday() != 0:
        failures.append("the week does not start on Monday")
    if round((end - start) / 86400) != 7:
        failures.append("the week is not seven days")

    # --- completed this week vs before ---------------------------------
    monday = datetime.fromtimestamp(start)
    for offset, title in ((0, "Shipped the adapter"), (1, "Wrote the tests")):
        task = todos.add(title, due=(monday + timedelta(days=offset)).timestamp())
        todos.complete(task.id,
                       now=(monday + timedelta(days=offset, hours=15)).timestamp())
    old = todos.add("Last week's task", due=(monday - timedelta(days=3)).timestamp())
    todos.complete(old.id, now=(monday - timedelta(days=2)).timestamp())

    # overdue and open
    late = todos.add("Pay the invoice", due=now - 86400)
    todos.add("Future thing", due=now + 3 * 86400)

    # --- focus sessions -------------------------------------------------
    review.record_focus(25, finished=start + 3600)
    review.record_focus(25, finished=start + 7200)
    review.record_focus(50, finished=start + 10 * 3600)   # counts
    review.record_focus(25, finished=start - 86400)       # last week

    # --- memory learned this week --------------------------------------
    memory.remember("Prefers mornings for deep work", kind="preference")

    # --- one calendar event --------------------------------------------
    ics = Path(tempfile.mkdtemp(prefix="mantel-review-ics-")) / "week.ics"
    moment = (monday + timedelta(days=1)).replace(hour=10)
    ics.write_text(
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:x\nSUMMARY:Planning\n"
        f"DTSTART:{moment:%Y%m%dT%H%M%S}\n"
        f"DTEND:{(moment + timedelta(hours=2)):%Y%m%dT%H%M%S}\n"
        "END:VEVENT\nEND:VCALENDAR\n")
    calendar_store.add_source(str(ics))

    stats = review.stats(now)
    print(f"  headline: {stats.headline()}")
    print(f"  completed={stats.completed} overdue={stats.overdue} "
          f"open={stats.open_now} focus={stats.focus_minutes}m "
          f"events={stats.events} facts={stats.facts_learned}")

    if stats.completed != 2:
        failures.append(f"completed should be 2, got {stats.completed}")
    if "Shipped the adapter" not in stats.completed_titles:
        failures.append("completed titles are wrong")
    if stats.overdue != 1:
        failures.append(f"overdue should be 1, got {stats.overdue}")
    if stats.open_now != 2:
        failures.append(f"open should be 2, got {stats.open_now}")
    if stats.focus_minutes != 100:
        failures.append(f"focus minutes should be 100, got {stats.focus_minutes}")
    if stats.focus_sessions != 3:
        failures.append(f"focus sessions should be 3, got {stats.focus_sessions}")
    if stats.facts_learned < 1:
        failures.append("a fact learned this week was not counted")
    if stats.events != 1:
        failures.append(f"events should be 1, got {stats.events}")
    if abs(stats.event_hours - 2.0) > 0.1:
        failures.append(f"event hours should be 2, got {stats.event_hours}")

    # --- the prompt is factual ------------------------------------------
    prompt = review.agent_prompt(stats)
    print(f"  prompt (first line): {prompt.splitlines()[0][:70]}…")
    for expected in ("Tasks completed: 2", "Overdue: 1",
                     "Focus: 3 sessions, 1.7 hours", "Completed: Shipped the adapter"):
        if expected not in prompt:
            failures.append(f"the prompt is missing {expected!r}")
    if "Shipped the adapter" not in prompt:
        failures.append("completed titles did not reach the agent")

    # --- previous week --------------------------------------------------
    last = review.previous_week(now)
    print(f"  previous week: completed={last.completed} "
          f"focus={last.focus_minutes}m")
    if last.completed != 1:
        failures.append(f"last week completed should be 1, got {last.completed}")
    if last.focus_minutes != 25:
        failures.append(f"last week focus should be 25m, got {last.focus_minutes}")

    # --- a broken calendar does not break the review --------------------
    calendar_store.add_source("/definitely/not/here.ics")
    safe = review.stats(now)
    if safe.events != 1:
        failures.append(f"a missing calendar changed the review: {safe.events}")

    # --- no data is a valid week ---------------------------------------
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="mantel-review-empty-")
    empty = review.stats(now)
    print(f"  empty week: {empty.headline()}")
    if empty.headline() != "0 done" or empty.focus_minutes:
        failures.append(f"an empty week should read as zero: {empty.headline()}")

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        return 1
    print("  review: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
