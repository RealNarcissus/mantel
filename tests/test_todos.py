"""Tests for the task and reminder store.

What matters here is judgement, not storage: a phrase becomes the right date
(or none at all), overdue does not mean today, and completing a repeating task
rolls it forward from its own due date rather than from now.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import datetime

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import (
    fonts_env,  # noqa: F401,E402
    todos,  # noqa: E402
)


def fresh() -> None:
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="mantel-todos-")


def main() -> int:
    failures: list[str] = []
    fresh()
    # a fixed "now": Friday 24 October 2026, 09:00 local
    now = datetime(2026, 10, 24, 9, 0).timestamp()

    # --- natural language dates -----------------------------------------
    cases = {
        "Call the dentist tomorrow": "2026-10-25",
        "Submit report today at 5pm": "2026-10-24",
        "Review slides on Monday": "2026-10-26",
        "Ship the release next week": "2026-10-31",
        "Draft the memo in 3 days": "2026-10-27",
        "Book flights in November 2": "2026-11-02",
    }
    for title, expected in cases.items():
        due, cleaned = todos.parse_due(title, now)
        got = time.strftime("%Y-%m-%d", time.localtime(due)) if due else "none"
        print(f"  {title!r:42} -> {got}  ({cleaned!r})")
        if got != expected:
            failures.append(f"{title!r} parsed to {got}, wanted {expected}")

    due, _ = todos.parse_due("Submit report today at 5pm", now)
    if time.strftime("%H:%M", time.localtime(due)) != "17:00":
        failures.append("an explicit time was not applied")

    # words that are not dates must stay in the title
    due, cleaned = todos.parse_due("Email the team about metrics", now)
    if due:
        failures.append("a plain task was given a due date")
    if cleaned != "Email the team about metrics":
        failures.append(f"a plain title was mangled: {cleaned!r}")

    # --- add / list / buckets -------------------------------------------
    todos.add("Call the dentist tomorrow")
    todos.add("Write the launch note on Monday")
    todos.add("Someday: read the Pi source", due=0)
    overdue = todos.add("Pay the invoice yesterday")
    if overdue:
        todos.update(overdue.id, due=now - 86400)
    print(f"  counts: {todos.counts()}")
    if todos.counts()["open"] != 4:
        failures.append(f"unexpected open count: {todos.counts()}")
    if not any(task.overdue for task in todos.all_tasks(include_done=False)
               if task.id == overdue.id):
        failures.append("a past-due task is not overdue")
    if len(todos.someday()) != 1:
        failures.append("the undated task is not in someday")
    today_titles = [task.title for task in todos.today()]
    if not any("invoice" in title for title in today_titles):
        failures.append(f"the overdue task is not in today: {today_titles}")
    soon = [task.title for task in todos.upcoming(now=now)]
    if not any("dentist" in title for title in soon):
        failures.append(f"tomorrow's task is missing from upcoming: {soon}")
    if any("dentist" in title for title in today_titles):
        failures.append("tomorrow's task leaked into today")

    # --- completing and undoing -----------------------------------------
    task = todos.add("One-off thing", due=now)
    done = todos.complete(task.id)
    if done is None or not done.done:
        failures.append("a one-off task did not complete")
    if any(t.id == task.id for t in todos.all_tasks(include_done=False)):
        failures.append("a completed task is still open")
    if not todos.reopen(task.id):
        failures.append("reopen failed")
    if not any(t.id == task.id for t in todos.all_tasks(include_done=False)):
        failures.append("a reopened task did not return")

    # --- recurrence rolls from the due date -----------------------------
    weekly = todos.add("Team sync", due=now, repeat="weekly")
    rolled = todos.complete(weekly.id, now=now + 30 * 86400)  # very late
    if rolled is None or rolled.done:
        failures.append("a repeating task was closed instead of rolled")
        delta = 0
    else:
        delta = (rolled.due - weekly.due) / 86400
    print(f"  weekly task rolled {delta:.0f} days from its due date")
    if round(delta) != 7:
        failures.append(f"a late completion shifted the series ({delta} days)")

    weekdays = todos.add("Standup", due=now, repeat="weekdays")
    # Friday + 1 lands on the weekend, so it must skip to Monday
    advanced = todos.complete(weekdays.id, now=now)
    if advanced is None:
        failures.append("weekday recurrence did not advance")
    else:
        print(f"  weekday task -> {time.strftime('%a %d %b', time.localtime(advanced.due))}")
        if datetime.fromtimestamp(advanced.due).weekday() >= 5:
            failures.append("weekday recurrence landed on a weekend")

    # --- reminders ------------------------------------------------------
    rundown = todos.add("Take the pills", due=now + 60, remind=True)
    if not rundown.remind:
        failures.append("a reminder was not set from the due time")
    if todos.due_reminders(now=now):
        failures.append("a future reminder fired early")
    firing = todos.due_reminders(now=now + 120)
    print(f"  reminders due: {[t.title for t in firing]}")
    if not any(task.id == rundown.id for task in firing):
        failures.append("a due reminder did not fire")
    todos.mark_reminded(rundown.id, now=now + 120)
    if todos.due_reminders(now=now + 130):
        failures.append("a fired reminder fired again")

    # --- removal and persistence ----------------------------------------
    doomed = todos.add("Delete me", due=now)
    if not todos.remove(doomed.id):
        failures.append("remove() failed for a real task")
    if any(task.id == doomed.id for task in todos.all_tasks()):
        failures.append("a removed task is still there")

    stored = todos.store_path()
    if not stored.is_file():
        failures.append("the store was not written")
    before = len(todos.all_tasks())
    todos._write(todos._read())      # simulate a reload
    if len(todos.all_tasks()) != before:
        failures.append("tasks did not survive a reload")

    # --- a corrupt store reads as empty ---------------------------------
    stored.write_text("{not json")
    if todos.all_tasks():
        failures.append("a corrupt store should read as empty")
    print("  corrupt store reads as empty")

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        return 1
    print("  tasks: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
