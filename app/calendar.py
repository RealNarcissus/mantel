"""Calendar: read-only, local-first, from `.ics` files.

The day is not just tasks. Meetings are where the hours actually go, and a
"Today" screen that ignores them is a list pretending to be a schedule. This
module reads iCalendar files — the one calendar format that every provider can
export and that needs no account, no OAuth and no network.

Deliberately read-only in v1: importing events is useful immediately, writing
back is a permissions problem that deserves its own design pass.

Supported: VEVENTs with SUMMARY, LOCATION, UID, DTSTART/DTEND (date or naive or
UTC datetime), and RRULE with FREQ=DAILY/WEEKLY/MONTHLY plus INTERVAL, COUNT and
UNTIL. Everything else is ignored rather than guessed at, and a malformed file
is skipped without taking the day down with it.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

#: How far forward recurrences are expanded.
RECUR_WINDOW_DAYS = 60

#: Hard cap so a bad rule cannot spin.
MAX_OCCURRENCES = 400

SOURCES_ENV = "MANTEL_ICS"


def data_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME")
                or (Path.home() / ".local" / "share"))
    for candidate in (base / "mantel", Path(__file__).resolve().parent.parent
                      / ".data"):
        try:
            (candidate / "calendar").mkdir(parents=True, exist_ok=True)
            probe = candidate / "calendar" / ".write-probe"
            probe.write_text("")
            probe.unlink()
            return candidate
        except OSError:
            continue
    import tempfile  # noqa: PLC0415

    return Path(tempfile.mkdtemp(prefix="mantel-calendar-"))


def settings_path() -> Path:
    return data_dir() / "calendar" / "sources.json"


@dataclass
class Event:
    title: str
    start: float
    end: float = 0.0
    all_day: bool = False
    location: str = ""
    uid: str = ""
    source: str = ""
    recurring: bool = False
    _rule: dict = field(default_factory=dict, repr=False)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start) or 3600.0

    @property
    def timed(self) -> bool:
        return not self.all_day


# --- sources ----------------------------------------------------------------

def _read_settings() -> list[str]:
    try:
        raw = json.loads(settings_path().read_text())
    except (OSError, ValueError):
        return []
    if isinstance(raw, dict):
        raw = raw.get("paths", [])
    if not isinstance(raw, list):
        return []
    return [str(path) for path in raw if isinstance(path, str) and path]


def _write_settings(paths: list[str]) -> bool:
    try:
        path = settings_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"paths": paths}, indent=1))
        tmp.replace(path)
        return True
    except OSError:
        return False


def sources() -> list[str]:
    """Configured `.ics` paths or URLs, environment first."""
    found: list[str] = []
    for value in (os.environ.get(SOURCES_ENV) or "").split(":"):
        value = value.strip()
        if value and value not in found:
            found.append(value)
    for value in _read_settings():
        if value not in found:
            found.append(value)
    return found


def add_source(path: str) -> bool:
    path = str(path).strip()
    if not path:
        return False
    paths = _read_settings()
    if path in paths:
        return True
    paths.append(path)
    return _write_settings(paths)


def remove_source(path: str) -> bool:
    paths = _read_settings()
    if path not in paths:
        return False
    return _write_settings([item for item in paths if item != path])


# --- parsing ----------------------------------------------------------------

def _unfold(text: str) -> list[str]:
    """Join RFC 5545 continuation lines (leading space or tab)."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


_UNESCAPE = (("\\n", "\n"), ("\\N", "\n"), ("\\,", ","), ("\\;", ";"),
             ("\\\\", "\\"))


def _text(value: str) -> str:
    for source, target in _UNESCAPE:
        value = value.replace(source, target)
    return value.strip()


def _parse_dt(value: str) -> tuple[float, bool]:
    """(timestamp, all_day) from an iCalendar date or date-time."""
    value = value.strip()
    if not value:
        return 0.0, False
    if value.endswith("Z") and "T" in value:
        try:
            moment = datetime.strptime(value[:-1], "%Y%m%dT%H%M%S")
        except ValueError:
            return 0.0, False
        # the naive time is UTC: treat it as such rather than assuming the
        # server's local zone (no stdlib timegm import needed)
        return (moment - datetime(1970, 1, 1)).total_seconds(), False
    if "T" in value:
        for pattern in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
            try:
                return datetime.strptime(value, pattern).timestamp(), False
            except ValueError:
                continue
        return 0.0, False
    try:
        moment = datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return 0.0, False
    return moment.timestamp(), True


_RRULE = re.compile(r"([A-Z]+)=([^;]+)")


def _parse_rule(value: str) -> dict:
    rule: dict = {}
    for key, raw in _RRULE.findall(value.upper()):
        if key == "FREQ":
            rule["freq"] = raw
        elif key == "INTERVAL":
            try:
                rule["interval"] = max(1, int(raw))
            except ValueError:
                pass
        elif key == "COUNT":
            try:
                rule["count"] = max(1, int(raw))
            except ValueError:
                pass
        elif key == "UNTIL":
            until, _all_day = _parse_dt(raw)
            if until:
                rule["until"] = until
    return rule


def parse_ics(text: str, *, source: str = "") -> list[Event]:
    """Every VEVENT in an iCalendar document, unsorted."""
    events: list[Event] = []
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if not current:
            return
        start = current.get("start", 0.0)
        if start:
            events.append(Event(
                title=current.get("title") or "Untitled",
                start=start,
                end=current.get("end", 0.0),
                all_day=bool(current.get("all_day")),
                location=current.get("location", ""),
                uid=current.get("uid", ""),
                source=source,
                recurring=bool(current.get("rule")),
                _rule=current.get("rule") or {},
            ))
        current = None

    for line in _unfold(text):
        upper = line.upper()
        if upper.startswith("BEGIN:VEVENT"):
            current = {}
            continue
        if upper.startswith("END:VEVENT"):
            flush()
            continue
        if current is None or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.split(";")[0].upper()
        if key == "SUMMARY":
            current["title"] = _text(value)
        elif key == "LOCATION":
            current["location"] = _text(value)
        elif key == "UID":
            current["uid"] = value.strip()
        elif key == "DTSTART":
            start, all_day = _parse_dt(value)
            if start:
                current["start"] = start
                current["all_day"] = all_day
        elif key == "DTEND":
            end, _all_day = _parse_dt(value)
            if end:
                current["end"] = end
        elif key == "RRULE":
            rule = _parse_rule(value)
            if rule.get("freq"):
                current["rule"] = rule
    flush()
    return events


def load(path: str) -> list[Event]:
    """Read one source: a local file, or an http(s) URL if you must."""
    try:
        if path.startswith(("http://", "https://")):
            with urllib.request.urlopen(path, timeout=15) as response:
                text = response.read().decode("utf-8", "replace")
        else:
            text = Path(os.path.expanduser(path)).read_text(
                errors="replace")
    except (OSError, ValueError, urllib.error.URLError):
        return []
    return parse_ics(text, source=path)


# --- expanding recurrences --------------------------------------------------

def _expand(event: Event, start: float, end: float) -> list[Event]:
    """Occurrences of an event between two timestamps."""
    if not event.recurring:
        return [event] if event.start < end and (
            event.start + event.duration) > start else []

    rule = event._rule
    freq = rule.get("freq")
    interval = int(rule.get("interval") or 1)
    count = rule.get("count")
    until = float(rule.get("until") or 0)
    length = event.duration

    out: list[Event] = []
    moment = datetime.fromtimestamp(event.start)
    index = 0
    while index < MAX_OCCURRENCES:
        stamp = moment.timestamp()
        if count and index >= int(count):
            break
        if until and stamp > until:
            break
        if stamp > end:
            break
        if stamp + length > start:
            out.append(Event(
                title=event.title, start=stamp, end=stamp + length,
                all_day=event.all_day, location=event.location,
                uid=event.uid, source=event.source, recurring=True,
                _rule={}))
        index += 1
        if freq == "DAILY":
            moment += timedelta(days=interval)
        elif freq == "WEEKLY":
            moment += timedelta(weeks=interval)
        elif freq == "MONTHLY":
            month = moment.month - 1 + interval
            year = moment.year + month // 12
            month = month % 12 + 1
            try:
                moment = moment.replace(year=year, month=month)
            except ValueError:
                moment = moment.replace(year=year, month=month, day=28)
        else:
            break
    return out


def events_between(start: float, end: float,
                   *, sources_override: list[str] | None = None) -> list[Event]:
    """Every event occurrence overlapping [start, end), sorted by start."""
    found: list[Event] = []
    for source in (sources_override if sources_override is not None
                   else sources()):
        for event in load(source):
            found.extend(_expand(event, start, end))
    found.sort(key=lambda event: event.start)
    return found


def today(*, now: float | None = None) -> list[Event]:
    now = now or time.time()
    start = datetime.fromtimestamp(now).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp()
    return events_between(start, start + 86400)


def upcoming(days: int = 7, *, now: float | None = None) -> list[Event]:
    now = now or time.time()
    start = datetime.fromtimestamp(now).replace(
        hour=0, minute=0, second=0, microsecond=0).timestamp() + 86400
    return events_between(start, start + days * 86400)


def next_event(*, now: float | None = None) -> Event | None:
    now = now or time.time()
    for event in events_between(now, now + 7 * 86400):
        if event.start >= now and (not event.all_day):
            return event
    return None


def summarise(events: list[Event]) -> str:
    """A one-line shape of a day, for cards."""
    if not events:
        return "no events"
    timed = [event for event in events if event.timed]
    if not timed:
        return f"{len(events)} all-day"
    return f"{len(timed)} timed · {len(events) - len(timed)} all-day" \
        if len(events) != len(timed) else f"{len(timed)} events"
