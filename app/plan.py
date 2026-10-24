"""Time-blocking: turn the day's tasks into a plan that respects the calendar.

The hard part of time-blocking is not drawing blocks, it is being honest:
you cannot fit six hours of work into the forty minutes between two meetings,
and a plan that ignores that is worse than no plan. This module finds real gaps
between calendar events inside a working window and places the most pressing
tasks into them, leaving a buffer around meetings, and says plainly what did
not fit.

It proposes rather than commits: the plan is shown in the app and can be
exported as an `.ics` file if the user wants it in their calendar. Writing
directly into someone's calendar is a permissions decision this app is not
ready to make.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app import calendar as calendar_store
from app import todos

#: The default working window, in local hours.
WORK_START = 9
WORK_END = 18

#: Minutes kept free on either side of a meeting.
BUFFER_MINUTES = 10

#: How long to assume a task needs when it has no estimate.
DEFAULT_BLOCK_MINUTES = 45

#: Shortest block worth placing; smaller gaps are left alone.
MIN_BLOCK_MINUTES = 20

#: Breathing room between two placed blocks.
GAP_MINUTES = 10

#: How many tasks a plan will try to place.
MAX_BLOCKS = 6

BREAK_AFTER_MINUTES = 90


@dataclass
class Block:
    """One proposed slice of the day."""

    title: str
    start: float
    end: float
    task_id: str = ""
    kind: str = "task"          # task | break | event

    @property
    def minutes(self) -> int:
        return max(0, int((self.end - self.start) // 60))

    def to_json(self) -> dict:
        return {"title": self.title, "start": self.start, "end": self.end,
                "task_id": self.task_id, "kind": self.kind}


@dataclass
class Plan:
    """A proposal, plus what could not be honoured."""

    day: str
    blocks: list[Block] = field(default_factory=list)
    unscheduled: list[str] = field(default_factory=list)
    busy: list[dict] = field(default_factory=list)

    @property
    def planned_minutes(self) -> int:
        return sum(block.minutes for block in self.blocks
                   if block.kind == "task")

    def headline(self) -> str:
        if not self.blocks:
            return "no room to plan"
        return (f"{sum(1 for b in self.blocks if b.kind == 'task')} blocks · "
                f"{self.planned_minutes} min")


def _day_start(now: float) -> datetime:
    return datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0,
                                               microsecond=0)


def _busy_intervals(now: float) -> list[tuple[float, float]]:
    """Today's timed events as (start, end), padded by the buffer."""
    try:
        events = calendar_store.today(now=now)
    except Exception:  # noqa: BLE001 - a broken calendar means an empty day
        return []
    out: list[tuple[float, float]] = []
    for event in events:
        if event.all_day:
            continue
        start = event.start - BUFFER_MINUTES * 60
        end = (event.start + event.duration) + BUFFER_MINUTES * 60
        out.append((start, end))
    return sorted(out)


def _free_windows(now: float, *, work_start: int = WORK_START,
                  work_end: int = WORK_END) -> list[tuple[float, float]]:
    """Gaps between now and the end of the working day, minus meetings."""
    moment = datetime.fromtimestamp(now)
    day = _day_start(now)
    open_at = day.replace(hour=work_start)
    close_at = day.replace(hour=work_end)
    begin = max(open_at, moment)
    if begin >= close_at:
        return []
    windows = [(begin.timestamp(), close_at.timestamp())]
    for busy_start, busy_end in _busy_intervals(now):
        narrowed: list[tuple[float, float]] = []
        for start, end in windows:
            if busy_end <= start or busy_start >= end:
                narrowed.append((start, end))
                continue
            if busy_start > start:
                narrowed.append((start, busy_start))
            if busy_end < end:
                narrowed.append((busy_end, end))
        windows = narrowed
    return [(start, end) for start, end in windows
            if end - start >= MIN_BLOCK_MINUTES * 60]


def _priorities(now: float) -> list[todos.Task]:
    """Open tasks worth scheduling: overdue first, then due today."""
    stamp = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
    candidates = []
    for task in todos.all_tasks(include_done=False):
        if not task.due:
            continue
        if task.due < now - 86400:          # hopeless late: still worth a block
            candidates.append((0, task))
            continue
        if time.strftime("%Y-%m-%d", time.localtime(task.due)) == stamp:
            candidates.append((1, task))
    candidates.sort(key=lambda pair: (pair[0], pair[1].due))
    return [task for _rank, task in candidates]


def plan_day(now: float | None = None, *,
             work_start: int = WORK_START, work_end: int = WORK_END,
             max_blocks: int = MAX_BLOCKS,
             default_minutes: int = DEFAULT_BLOCK_MINUTES) -> Plan:
    """Propose where the day's tasks could go."""
    now = now if now is not None else time.time()
    plan = Plan(day=datetime.fromtimestamp(now).strftime("%Y-%m-%d"))
    windows = _free_windows(now, work_start=work_start, work_end=work_end)
    try:
        plan.busy = [
            {"title": block.title, "start": block.start, "end": block.end}
            for block in calendar_store.today(now=now) if not block.all_day
        ]
    except Exception:  # noqa: BLE001
        plan.busy = []

    tasks = _priorities(now)
    cursor = list(windows)          # mutable copy of remaining gaps
    for task in tasks:
        if len([b for b in plan.blocks if b.kind == "task"]) >= max_blocks:
            remaining = tasks[tasks.index(task):]
            plan.unscheduled.extend(item.title for item in remaining)
            break
        need = default_minutes * 60
        placed = False
        for index, (start, end) in enumerate(cursor):
            if end - start < MIN_BLOCK_MINUTES * 60:
                continue
            length = min(need, end - start)
            if length < MIN_BLOCK_MINUTES * 60:
                continue
            block_start = start
            plan.blocks.append(Block(title=task.title, start=block_start,
                                     end=block_start + length,
                                     task_id=task.id))
            placed = True
            next_free = block_start + length + GAP_MINUTES * 60
            if end - next_free >= MIN_BLOCK_MINUTES * 60:
                cursor[index] = (next_free, end)
            else:
                cursor[index] = (end, end)
            break
        if not placed:
            plan.unscheduled.append(task.title)

    plan.blocks.sort(key=lambda block: block.start)
    return plan


def export_ics(plan: Plan) -> str:
    """A calendar file for the proposed plan, so it can be imported."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Mantel//Plan//EN"]
    for block in plan.blocks:
        start = datetime.fromtimestamp(block.start)
        end = datetime.fromtimestamp(block.end)
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uuid.uuid4().hex}@mantel",
            f"SUMMARY:{block.title}",
            f"DTSTART:{start:%Y%m%dT%H%M%S}",
            f"DTEND:{end:%Y%m%dT%H%M%S}",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return "\n".join(lines) + "\n"


def save_plan(plan: Plan) -> str:
    """Write the plan next to the other local state; return the path."""
    from app import knowledge  # noqa: PLC0415 - reuse the data-dir helper

    folder = knowledge.data_dir() / "plans"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"plan-{plan.day}.ics"
    path.write_text(export_ics(plan))
    return str(path)
