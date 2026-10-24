"""The weekly review: what actually happened, from the app's own records.

Productivity tools tend to ask you to reflect in a journal nobody keeps. This
computes the review instead: tasks finished, things that slipped, hours on the
calendar, minutes in focus sessions, facts learned. The agent can then write the
prose around those numbers — it is better at narrative than at bookkeeping, and
the numbers are the part a user cannot argue with.

Everything is derived from local stores (tasks, calendar, memory, focus log), and
the clock is injectable so the tests can pin a week.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app import calendar as calendar_store
from app import memory as memory_store
from app import todos


def data_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME")
                or (Path.home() / ".local" / "share"))
    for candidate in (base / "mantel", Path(__file__).resolve().parent.parent
                      / ".data"):
        try:
            (candidate / "review").mkdir(parents=True, exist_ok=True)
            probe = candidate / "review" / ".write-probe"
            probe.write_text("")
            probe.unlink()
            return candidate
        except OSError:
            continue
    import tempfile  # noqa: PLC0415

    return Path(tempfile.mkdtemp(prefix="mantel-review-"))


def focus_path() -> Path:
    return data_dir() / "review" / "focus.json"


# --- focus sessions ---------------------------------------------------------

def record_focus(minutes: int, *, finished: float | None = None) -> bool:
    """Log one completed focus session. The review counts these."""
    try:
        raw = json.loads(focus_path().read_text())
    except (OSError, ValueError):
        raw = []
    if not isinstance(raw, list):
        raw = []
    raw.append({"finished": finished or time.time(),
                "minutes": max(0, int(minutes))})
    try:
        path = focus_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(raw[-500:], indent=1))
        tmp.replace(path)
        return True
    except OSError:
        return False


def focus_sessions(start: float, end: float) -> list[dict]:
    try:
        raw = json.loads(focus_path().read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(raw, list):
        return []
    out = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        moment = float(row.get("finished") or 0)
        if start <= moment < end:
            out.append({"finished": moment,
                        "minutes": int(row.get("minutes") or 0)})
    return out


# --- the week ---------------------------------------------------------------

@dataclass
class Stats:
    """One week, as the app can see it."""

    start: float
    end: float
    completed: int
    completed_titles: list[str]
    overdue: int
    overdue_titles: list[str]
    open_now: int
    focus_minutes: int
    focus_sessions: int
    events: int
    event_hours: float
    facts_learned: int
    facts: list[str]

    @property
    def focus_hours(self) -> float:
        return round(self.focus_minutes / 60.0, 1)

    def headline(self) -> str:
        bits = [f"{self.completed} done"]
        if self.overdue:
            bits.append(f"{self.overdue} late")
        if self.focus_minutes:
            bits.append(f"{self.focus_hours}h focus")
        if self.events:
            bits.append(f"{self.events} events")
        return " · ".join(bits)


def week_bounds(now: float | None = None,
                *, days: int = 7) -> tuple[float, float]:
    """Monday 00:00 of this week through the same moment next Monday."""
    moment = datetime.fromtimestamp(now if now is not None else time.time())
    monday = (moment - timedelta(days=moment.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return monday.timestamp(), (monday + timedelta(days=days)).timestamp()


def stats(now: float | None = None) -> Stats:
    """Compute the week's review from the local stores."""
    now = now if now is not None else time.time()
    start, end = week_bounds(now)

    completed: list[str] = []
    overdue: list[str] = []
    open_now = 0
    for task in todos.all_tasks(include_done=True):
        if task.done and start <= (task.completed or 0) < end:
            completed.append(task.title)
        if not task.done:
            open_now += 1
            # overdue relative to the review's own clock, so the window and the
            # judgement always agree
            if task.due and task.due < now:
                overdue.append(task.title)

    sessions = focus_sessions(start, end)
    focus_minutes = sum(session["minutes"] for session in sessions)

    try:
        events = calendar_store.events_between(start, end)
    except Exception:  # noqa: BLE001 - a bad calendar must not break the review
        events = []
    event_hours = round(sum(event.duration for event in events) / 3600.0, 1)

    learned: list[str] = []
    for fact in memory_store.facts():
        if start <= fact.created < end:
            learned.append(fact.text)

    return Stats(
        start=start, end=end,
        completed=len(completed), completed_titles=completed[:12],
        overdue=len(overdue), overdue_titles=overdue[:12],
        open_now=open_now,
        focus_minutes=focus_minutes, focus_sessions=len(sessions),
        events=len(events), event_hours=event_hours,
        facts_learned=len(learned), facts=learned[:8],
    )


def agent_prompt(stats: Stats) -> str:
    """The brief handed to the agent when the user asks it to write the review."""
    lines = [
        "Write my weekly review from these numbers. Be direct, no praise, no "
        "lists of everything — three short sections: what actually moved, what "
        "slipped and why it probably happened, and one change for next week.",
        "",
        f"Week of {datetime.fromtimestamp(stats.start):%d %b}.",
        f"Tasks completed: {stats.completed}",
        f"Still open: {stats.open_now}",
        f"Overdue: {stats.overdue}",
        f"Focus: {stats.focus_sessions} sessions, {stats.focus_hours} hours",
        f"Calendar: {stats.events} events, {stats.event_hours} hours",
        f"Facts learned: {stats.facts_learned}",
    ]
    if stats.completed_titles:
        lines.append("Completed: " + "; ".join(stats.completed_titles))
    if stats.overdue_titles:
        lines.append("Overdue: " + "; ".join(stats.overdue_titles))
    return "\n".join(lines)


def previous_week(now: float | None = None) -> Stats:
    now = now if now is not None else time.time()
    return stats(now - 7 * 86400)
