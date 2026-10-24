"""Tests for the read-only calendar.

What matters is that a real `.ics` file yields the right moments: all-day
versus timed, UTC converted to local, recurrences expanded into a window rather
than into infinity, and a broken file skipped instead of crashing the day.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import (
    calendar,  # noqa: E402
    fonts_env,  # noqa: F401,E402
)

SAMPLE = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:standup@example.com
SUMMARY:Daily standup
DTSTART:20261026T093000
DTEND:20261026T094500
LOCATION:Room 3
RRULE:FREQ=DAILY;INTERVAL=1;COUNT=10
END:VEVENT
BEGIN:VEVENT
UID:review@example.com
SUMMARY:Design review\\, phase 2
DTSTART:20261027T140000Z
DTEND:20261027T150000Z
END:VEVENT
BEGIN:VEVENT
UID:holiday@example.com
SUMMARY:Public holiday
DTSTART;VALUE=DATE:20261028
END:VEVENT
END:VCALENDAR
"""


def main() -> int:
    failures: list[str] = []
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="mantel-calendar-")
    os.environ.pop("MANTEL_ICS", None)

    events = calendar.parse_ics(SAMPLE, source="sample")
    print(f"  parsed {len(events)} events")
    if len(events) != 3:
        failures.append(f"expected 3 events, got {len(events)}")

    by_title = {event.title: event for event in events}
    standup = by_title.get("Daily standup")
    if standup is None:
        failures.append("the standup was not parsed")
    else:
        when = datetime.fromtimestamp(standup.start)
        print(f"  standup: {when:%Y-%m-%d %H:%M} - "
              f"{datetime.fromtimestamp(standup.end):%H:%M}, "
              f"recurring={standup.recurring}")
        if (when.month, when.day, when.hour, when.minute) != (10, 26, 9, 30):
            failures.append(f"standup start is wrong: {when}")
        if standup.end - standup.start != 900:
            failures.append("standup duration is wrong")
        if not standup.recurring:
            failures.append("the RRULE was dropped")

    review = by_title.get("Design review, phase 2")
    if review is None:
        failures.append("the escaped SUMMARY was not unescaped")
    else:
        local = datetime.fromtimestamp(review.start)
        print(f"  review (UTC converted): {local:%Y-%m-%d %H:%M}")
        expected = (datetime(2026, 10, 27, 14, 0)
                    - datetime(1970, 1, 1)).total_seconds()
        if abs(review.start - expected) > 1:
            failures.append(f"UTC conversion is off: {local}")

    holiday = by_title.get("Public holiday")
    if holiday is None or not holiday.all_day:
        failures.append("the all-day event was not marked all-day")

    # --- recurrence expansion -------------------------------------------
    day = datetime(2026, 10, 26, 0, 0).timestamp()
    # expansion is tested directly: events_between reads from disk
    expanded = calendar._expand(standup, day, day + 5 * 86400)
    print(f"  standup occurrences in 5 days: {len(expanded)}")
    if len(expanded) != 5:
        failures.append(f"expected 5 occurrences, got {len(expanded)}")
    if [int((event.start - standup.start) / 86400) for event in expanded] != list(range(5)):
        failures.append("occurrences are not one day apart")

    capped = calendar._expand(standup, day, day + 60 * 86400)
    if len(capped) > 10:
        failures.append(f"COUNT=10 was ignored: {len(capped)} occurrences")

    weekly = calendar.Event(title="Weekly", start=day, end=day + 3600,
                            recurring=True, _rule={"freq": "WEEKLY",
                                                   "interval": 2})
    weeks = calendar._expand(weekly, day, day + 30 * 86400)
    print(f"  fortnightly occurrences in 30 days: {len(weeks)}")
    if len(weeks) != 3:
        failures.append(f"fortnightly expansion is wrong: {len(weeks)}")

    # --- a broken file is skipped, not fatal ---------------------------
    broken = Path(tempfile.mkdtemp(prefix="mantel-ics-")) / "broken.ics"
    broken.write_text("BEGIN:VCALENDAR\nBEGIN:VEVENT\nSUMMARY:No date\n")
    if calendar.load(str(broken)):
        failures.append("a file without DTSTART produced events")
    if calendar.load("/definitely/not/here.ics"):
        failures.append("a missing source produced events")

    # --- file sources and the settings store ---------------------------
    good = Path(tempfile.mkdtemp(prefix="mantel-ics-")) / "good.ics"
    good.write_text(SAMPLE)
    if not calendar.add_source(str(good)):
        failures.append("a source could not be added")
    if str(good) not in calendar.sources():
        failures.append("the added source is not listed")
    if not calendar.remove_source(str(good)):
        failures.append("a source could not be removed")
    if str(good) in calendar.sources():
        failures.append("the removed source is still listed")

    # environment sources win, and are included
    os.environ["MANTEL_ICS"] = str(good)
    try:
        found = calendar.sources()
        if str(good) not in found:
            failures.append(f"MANTEL_ICS was ignored: {found}")
        events = calendar.events_between(0, time.time() + 400 * 86400)
        if not events:
            failures.append("no events came from the .ics file")
    finally:
        os.environ.pop("MANTEL_ICS", None)

    # --- summaries ------------------------------------------------------
    if calendar.summarise([]) != "no events":
        failures.append("an empty day did not summarise as such")

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        return 1
    print("  calendar: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
