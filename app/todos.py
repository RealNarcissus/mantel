"""Tasks and reminders: the user's own list, not the agent's.

Everything here is local and boring on purpose. A task is a line with a date, a
project and a repeat rule; a reminder is a task that can also poke you at a
specific time. The agent reads and writes the same store, so "add a task to
call the dentist on Friday" from the chat and the checkbox on the page are the
same object.

Design decisions worth knowing:

* **One store, JSON, human-readable.** Same directory as memory and schedules.
  It can be inspected, backed up and edited by hand.
* **Dates are optional.** A task without a date is not a failure state; it
  lives in "Later" instead of pretending to be due today.
* **Recurrence is a rule, not a cron.** `daily`, `weekdays`, `weekly`,
  `monthly` — completing a repeating task rolls it forward from the due date,
  not from "now", so a missed day does not shift the series.
* **Reminders are times, not daemons.** A minute-level check turns due
  reminders into notifications while the app is open; the honest contract is
  the same one Claude desktop uses for local tasks.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

REPEATS = ("", "daily", "weekdays", "weekly", "monthly")


def data_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME")
                or (Path.home() / ".local" / "share"))
    for candidate in (base / "mantel", Path(__file__).resolve().parent.parent
                      / ".data"):
        try:
            (candidate / "tasks").mkdir(parents=True, exist_ok=True)
            probe = candidate / "tasks" / ".write-probe"
            probe.write_text("")
            probe.unlink()
            return candidate
        except OSError:
            continue
    import tempfile  # noqa: PLC0415

    return Path(tempfile.mkdtemp(prefix="mantel-tasks-"))


def store_path() -> Path:
    return data_dir() / "tasks" / "tasks.json"


@dataclass
class Task:
    title: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    notes: str = ""
    project: str = ""
    due: float = 0.0            # unix ts of the due moment; 0 = someday
    remind: float = 0.0         # unix ts to notify at; 0 = no reminder
    repeat: str = ""            # one of REPEATS
    done: bool = False
    created: float = field(default_factory=time.time)
    completed: float = 0.0
    reminded: float = 0.0       # when the reminder last fired

    # -- derived ----------------------------------------------------------
    @property
    def overdue(self) -> bool:
        return bool(self.due) and not self.done and self.due < time.time()

    @property
    def due_today(self) -> bool:
        if not self.due or self.done:
            return False
        return _day(self.due) == _day(time.time())

    def to_json(self) -> dict:
        return asdict(self)


def _day(timestamp: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(timestamp))


# --- reading and writing ----------------------------------------------------

def _read() -> list[dict]:
    try:
        raw = json.loads(store_path().read_text())
    except (OSError, ValueError):
        return []
    if isinstance(raw, dict):
        raw = raw.get("tasks", [])
    return [row for row in raw if isinstance(row, dict)]


def _write(rows: list[dict]) -> bool:
    try:
        path = store_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, indent=1))
        tmp.replace(path)
        return True
    except OSError:
        return False


def all_tasks(*, include_done: bool = True) -> list[Task]:
    out: list[Task] = []
    for row in _read():
        known = {k: v for k, v in row.items() if k in Task.__dataclass_fields__}
        try:
            task = Task(**known)
        except TypeError:
            continue
        if include_done or not task.done:
            out.append(task)
    out.sort(key=lambda task: (task.done, task.due or float("inf"),
                               task.created))
    return out


# --- natural language -------------------------------------------------------

_WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}
_MONTHS = {name: index for index, name in enumerate(
    ("january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"), start=1)}

_TIME = re.compile(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
_TIME24 = re.compile(r"\bat\s+(\d{1,2}):(\d{2})\b", re.I)


def parse_due(text: str, now: float | None = None) -> tuple[float, str]:
    """Pull a due moment out of a phrase. Returns (timestamp, cleaned text).

    Deliberately modest: today/tomorrow/tonight/next week, weekday names, "in N
    days", month-day, and a time. Anything else is left in the title, because
    silently guessing is worse than leaving a task undated.
    """
    from datetime import datetime as _dt  # noqa: PLC0415

    now = now if now is not None else time.time()
    base = _dt.fromtimestamp(now).replace(second=0, microsecond=0)
    cleaned = text
    due: _dt | None = None
    hour, minute = 0, 0
    has_time = False

    time_match = _TIME.search(cleaned)
    if time_match:
        hour = int(time_match.group(1)) % 12
        minute = int(time_match.group(2) or 0)
        if (time_match.group(3) or "").lower() == "pm":
            hour += 12
        has_time = True
        cleaned = _TIME.sub("", cleaned)
    else:
        time_match = _TIME24.search(cleaned)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            has_time = True
            cleaned = _TIME24.sub("", cleaned)

    lowered = cleaned.lower()
    if re.search(r"\b(today|tonight)\b", lowered):
        due = base
        cleaned = re.sub(r"\b(today|tonight)\b", "", cleaned, flags=re.I)
        if "tonight" in lowered and not has_time:
            hour, has_time = 20, True
    elif re.search(r"\btomorrow\b", lowered):
        due = base + timedelta(days=1)
        cleaned = re.sub(r"\btomorrow\b", "", cleaned, flags=re.I)
    elif re.search(r"\bnext week\b", lowered):
        due = base + timedelta(days=7)
        cleaned = re.sub(r"\bnext week\b", "", cleaned, flags=re.I)
    else:
        in_days = re.search(r"\bin (\d{1,2}) days?\b", lowered)
        if in_days:
            due = base + timedelta(days=int(in_days.group(1)))
            cleaned = re.sub(r"\bin (\d{1,2}) days?\b", "", cleaned, flags=re.I)
        else:
            for name, index in _WEEKDAYS.items():
                if re.search(rf"\b(?:on |by )?{name}\b", lowered):
                    ahead = (index - base.weekday()) % 7 or 7
                    due = base + timedelta(days=ahead)
                    cleaned = re.sub(rf"\b(?:on |by )?{name}\b", "", cleaned,
                                     flags=re.I)
                    break
            if due is None:
                month_day = re.search(
                    r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2})\b", lowered)
                if month_day:
                    month = _MONTHS[month_day.group(1)]
                    day = int(month_day.group(2))
                    year = base.year
                    try:
                        candidate = _dt(year, month, day)
                    except ValueError:
                        candidate = None
                    if candidate is not None:
                        if candidate < base:
                            candidate = candidate.replace(year=year + 1)
                        due = candidate
                        cleaned = re.sub(month_day.group(0), "", cleaned,
                                         flags=re.I)

    if due is None and not has_time:
        return 0.0, " ".join(text.split())

    target = due or base
    if has_time:
        target = target.replace(hour=hour, minute=minute)
        if due is None and target < base:
            target += timedelta(days=1)
    cleaned = " ".join(cleaned.split()).strip(" ,;:-")
    cleaned = re.sub(r"\b(in|on|at|by|next)\s*$", "", cleaned,
                     flags=re.I).strip(" ,;:-")
    return target.timestamp(), cleaned or " ".join(text.split())


# --- writes ----------------------------------------------------------------

def add(title: str, *, project: str = "", due: float | None = None,
        remind: bool = False, repeat: str = "", notes: str = "") -> Task | None:
    """Create a task. `due` defaults to whatever the title says."""
    title = " ".join(str(title).split())
    if not title:
        return None
    if due is None:
        due, cleaned = parse_due(title)
        if due:
            title = cleaned
    task = Task(title=title, project=project, due=due or 0.0,
                repeat=repeat if repeat in REPEATS else "",
                notes=notes)
    if remind and task.due:
        task.remind = task.due
    rows = _read()
    rows.append(task.to_json())
    _write(rows)
    return task


def update(task_id: str, **changes) -> bool:
    rows = _read()
    allowed = set(Task.__dataclass_fields__) - {"id"}
    for row in rows:
        if row.get("id") != task_id:
            continue
        for key, value in changes.items():
            if key in allowed:
                row[key] = value
        _write(rows)
        return True
    return False


def complete(task_id: str, *, now: float | None = None) -> Task | None:
    """Mark done; a repeating task rolls forward instead of finishing."""
    now = now or time.time()
    rows = _read()
    for row in rows:
        if row.get("id") != task_id:
            continue
        repeat = row.get("repeat") or ""
        if repeat:
            row["due"] = _next_occurrence(float(row.get("due") or now), repeat)
            row["remind"] = row["due"]
            row["reminded"] = 0.0
            row["completed"] = now
        else:
            row["done"] = True
            row["completed"] = now
        _write(rows)
        return Task(**{k: v for k, v in row.items()
                       if k in Task.__dataclass_fields__})
    return None


def reopen(task_id: str) -> bool:
    return update(task_id, done=False, completed=0.0)


def remove(task_id: str) -> bool:
    rows = _read()
    kept = [row for row in rows if row.get("id") != task_id]
    if len(kept) == len(rows):
        return False
    return _write(kept)


def _next_occurrence(due: float, repeat: str) -> float:
    """Roll a repeating task forward from its due date, not from now."""
    moment = datetime.fromtimestamp(due or time.time())
    if repeat == "daily":
        moment += timedelta(days=1)
    elif repeat == "weekdays":
        moment += timedelta(days=1)
        while moment.weekday() >= 5:
            moment += timedelta(days=1)
    elif repeat == "weekly":
        moment += timedelta(days=7)
    elif repeat == "monthly":
        month = moment.month % 12 + 1
        year = moment.year + (1 if month == 1 else 0)
        try:
            moment = moment.replace(year=year, month=month)
        except ValueError:      # 31st of a shorter month
            moment = moment.replace(year=year, month=month, day=28)
    return moment.timestamp()


# --- reading back -----------------------------------------------------------

def today(*, now: float | None = None) -> list[Task]:
    """Anything due today or already overdue, soonest first."""
    now = now or time.time()
    stamp = _day(now)
    picked = [task for task in all_tasks(include_done=False)
              if task.due and _day(task.due) <= stamp]
    picked.sort(key=lambda task: task.due)
    return picked


def upcoming(days: int = 7, *, now: float | None = None) -> list[Task]:
    now = now or time.time()
    end = now + days * 86400
    return [task for task in all_tasks(include_done=False)
            if task.due and _day(now) < _day(task.due)
            and task.due <= end]


def someday() -> list[Task]:
    return [task for task in all_tasks(include_done=False) if not task.due]


def due_reminders(*, now: float | None = None) -> list[Task]:
    """Tasks whose reminder time has arrived and has not fired yet."""
    now = now or time.time()
    return [task for task in all_tasks(include_done=False)
            if task.remind and task.remind <= now
            and (not task.reminded or task.reminded < task.remind)]


def mark_reminded(task_id: str, *, now: float | None = None) -> None:
    update(task_id, reminded=now or time.time())


def counts() -> dict:
    open_tasks = all_tasks(include_done=False)
    return {
        "open": len(open_tasks),
        "today": len(today()),
        "overdue": sum(1 for task in open_tasks if task.overdue),
        "someday": len(someday()),
    }
