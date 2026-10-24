"""Schedules: recurring prompts the agent runs on its own.

The desktop app lets you schedule a prompt; Claude's desktop app runs *local*
scheduled tasks whenever the app is open. This module does the same: it owns
its own store (independent of the engine's opaque sidecars), understands a
five-field cron expression, and fires due prompts while the app runs.

The scheduler is deliberately in-process and honest about it: a schedule only
runs while Gemini is open, and a missed slot is caught up once on the next
tick rather than replayed a hundred times.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


# --- store location --------------------------------------------------------

def data_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME")
                or (Path.home() / ".local" / "share"))
    for cand in (base / "gemini-desktop", Path(__file__).resolve().parent.parent
                 / ".data"):
        try:
            (cand / "schedules").mkdir(parents=True, exist_ok=True)
            return cand
        except OSError:
            continue
    raise RuntimeError("no writable data directory")


def store_path() -> Path:
    return data_dir() / "schedules" / "schedules.json"


# --- cron ------------------------------------------------------------------

FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))
FIELD_NAMES = ("minute", "hour", "day of month", "month", "weekday")
MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep",
          "oct", "nov", "dec")
WEEKDAYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")


def parse_field(text: str, index: int) -> set[int]:
    """Parse one cron field into the set of values it matches."""
    lo, hi = FIELD_RANGES[index]
    out: set[int] = set()
    for part in text.split(","):
        part = part.strip().lower()
        if not part:
            raise ValueError(f"empty {FIELD_NAMES[index]} field")
        step = 1
        if "/" in part:
            part, _, step_text = part.partition("/")
            step = int(step_text)
            if step <= 0:
                raise ValueError("step must be positive")
        # names for months and weekdays
        if index == 3:
            for i, name in enumerate(MONTHS, start=1):
                part = part.replace(name, str(i))
        if index == 4:
            for i, name in enumerate(WEEKDAYS):
                part = part.replace(name, str(i))
            part = part.replace("7", "0") if part.strip() == "7" else part
        if part in ("*", ""):
            start, end = lo, hi
        elif "-" in part:
            start_text, _, end_text = part.partition("-")
            start, end = int(start_text), int(end_text)
        else:
            start = int(part)
            end = hi if step > 1 else start
        if start < lo or end > hi or start > end:
            raise ValueError(
                f"{FIELD_NAMES[index]} out of range: {text}")
        out.update(range(start, end + 1, step))
    return out


def validate_cron(expression: str) -> None:
    """Raise ValueError if the expression is not a valid five-field cron."""
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("a schedule needs five fields: minute hour day month "
                         "weekday")
    for index, text in enumerate(fields):
        parse_field(text, index)


def _matches(when: time.struct_time, expr) -> bool:
    fields = expr.split()
    minutes = parse_field(fields[0], 0)
    hours = parse_field(fields[1], 1)
    doms = parse_field(fields[2], 2)
    months = parse_field(fields[3], 3)
    dows = parse_field((fields[4].replace("7", "0")), 4)
    return (when.tm_min in minutes and when.tm_hour in hours
            and when.tm_mon in months
            and (when.tm_mday in doms) and (when.tm_wday in dows))


def next_run(expression: str, after: float | None = None) -> float | None:
    """The next timestamp this expression fires at, or None within a year."""
    validate_cron(expression)
    start = int(after if after is not None else time.time())
    # round up to the next whole minute
    start = start - (start % 60) + 60
    limit = start + 366 * 24 * 3600
    t = start
    while t < limit:
        if _matches(time.localtime(t), expression):
            return float(t)
        t += 60
    return None


def describe_cron(expression: str) -> str:
    """A human sentence for a cron expression."""
    try:
        fields = expression.split()
        minute, hour, dom, month, dow = fields
    except (ValueError, IndexError):
        return expression
    if minute.isdigit() and hour.isdigit():
        clock = f"{int(hour):02d}:{int(minute):02d}"
        if dow == "*" and dom == "*":
            return f"every day at {clock}"
        if dow != "*" and dom == "*":
            names = [_weekday_name(int(d)) for d in
                     parse_field(dow, 4)]
            if set(parse_field(dow, 4)) == {1, 2, 3, 4, 5}:
                return f"every weekday at {clock}"
            return f"every {', '.join(names)} at {clock}"
        if dom != "*" and dow == "*":
            return f"every month on day {dom} at {clock}"
    if minute.startswith("*/"):
        step = minute[2:]
        return f"every {step} minutes"
    if hour.startswith("*/"):
        return f"every {hour[2:]} hours"
    return expression


def _weekday_name(value: int) -> str:
    names = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
             "Saturday")
    return names[value % 7]


# --- the model -------------------------------------------------------------

@dataclass
class Run:
    """One execution of a schedule."""

    started: float
    finished: float = 0.0
    status: str = ""
    text: str = ""
    error: str = ""
    conversation_id: str = ""


@dataclass
class Schedule:
    """One recurring prompt."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    title: str = ""
    prompt: str = ""
    cron: str = "0 9 * * *"
    mode: str = "task"
    approval: str = "ask"
    workspace: str = ""
    paused: bool = False
    created: float = field(default_factory=time.time)
    last_run: float = 0.0
    runs: list[Run] = field(default_factory=list)

    @property
    def description(self) -> str:
        return describe_cron(self.cron)

    @property
    def anchor(self) -> float:
        """When to start looking for a slot: the last run, or creation."""
        return max(self.last_run, self.created)

    @property
    def next_run(self) -> float | None:
        """The next slot from now — what the UI counts down to."""
        if self.paused:
            return None
        return next_run(self.cron, after=max(self.anchor, time.time() - 1))

    @property
    def due(self) -> bool:
        """Has a slot passed since it last ran (or since it was created)?"""
        if self.paused:
            return False
        slot = next_run(self.cron, after=self.anchor)
        return slot is not None and slot <= time.time()


# --- store -----------------------------------------------------------------

def _read() -> dict:
    try:
        data = json.loads(store_path().read_text())
    except (OSError, ValueError):
        return {"schedules": []}
    return data if isinstance(data, dict) else {"schedules": []}


def _write(data: dict) -> bool:
    try:
        path = store_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        tmp.replace(path)
        return True
    except OSError:
        return False


def list_schedules() -> list[Schedule]:
    """Every stored schedule, newest first."""
    out: list[Schedule] = []
    for raw in _read().get("schedules", []):
        if not isinstance(raw, dict):
            continue
        runs = []
        for run in raw.get("runs", []) or []:
            if isinstance(run, dict):
                runs.append(Run(**{k: v for k, v in run.items()
                                   if k in Run.__dataclass_fields__}))
        fields = {k: v for k, v in raw.items()
                  if k in Schedule.__dataclass_fields__ and k != "runs"}
        try:
            schedule = Schedule(**fields)
        except TypeError:
            continue
        schedule.runs = runs
        out.append(schedule)
    out.sort(key=lambda s: s.created, reverse=True)
    return out


def save(schedule: Schedule) -> bool:
    """Insert or update a schedule."""
    data = _read()
    rows = [r for r in data.get("schedules", [])
            if isinstance(r, dict) and r.get("id") != schedule.id]
    record = asdict(schedule)
    record["runs"] = [asdict(r) for r in schedule.runs[-20:]]
    rows.append(record)
    data["schedules"] = rows
    return _write(data)


def delete(schedule_id: str) -> bool:
    data = _read()
    rows = [r for r in data.get("schedules", [])
            if isinstance(r, dict) and r.get("id") != schedule_id]
    data["schedules"] = rows
    return _write(data)


def set_paused(schedule_id: str, paused: bool) -> bool:
    for schedule in list_schedules():
        if schedule.id == schedule_id:
            schedule.paused = paused
            return save(schedule)
    return False


def record_run(schedule_id: str, run: Run) -> bool:
    for schedule in list_schedules():
        if schedule.id == schedule_id:
            schedule.runs.append(run)
            schedule.last_run = run.started
            if run.status:
                # a one-shot run that succeeded leaves nothing to repeat
                pass
            return save(schedule)
    return False


# --- suggestions -----------------------------------------------------------

@dataclass(frozen=True)
class Suggestion:
    """A starter schedule."""

    title: str
    cron: str
    prompt: str


SUGGESTIONS: tuple[Suggestion, ...] = (
    Suggestion("Morning briefing", "0 9 * * 1-5",
               "Summarise what changed since yesterday and what needs "
               "attention today."),
    Suggestion("Inbox digest", "0 18 * * *",
               "Summarise today's important mail and list anything waiting on "
               "a reply."),
    Suggestion("Weekly review", "0 17 * * 1",
               "Review the week's goals: what moved, what slipped, and what to "
               "carry into next week."),
)
