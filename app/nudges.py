"""Proactivity with a budget: the app may interrupt you a little, on purpose.

The failure mode of "smart" assistants is noise. This module is the opposite
kind of design: every possible nudge is computed from local data, then filtered
through a daily budget, quiet hours, and a record of what already fired. The
default budget is three a day and the default quiet window is the night — the
app should feel like a good assistant, which mostly means knowing when not to
speak.

The rules are deliberately few and boring:

    next event       something starts within 15 minutes
    overdue          three or more things are late
    brief            once a day, at the configured hour, what the day holds

Everything is local and testable: `plan()` gives the candidates, `due()` gives
what may actually be shown right now, and `mark()` records it.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app import calendar as calendar_store
from app import todos

#: Minutes before an event starts that it is worth mentioning.
EVENT_LEAD_MINUTES = 15

#: How many things must be late before it is worth saying so.
OVERDUE_THRESHOLD = 3

DEFAULT_BUDGET = 3
DEFAULT_BRIEF_HOUR = 8
DEFAULT_QUIET_START = 22
DEFAULT_QUIET_END = 8


def data_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME")
                or (Path.home() / ".local" / "share"))
    for candidate in (base / "mantel", Path(__file__).resolve().parent.parent
                      / ".data"):
        try:
            (candidate / "nudges").mkdir(parents=True, exist_ok=True)
            probe = candidate / "nudges" / ".write-probe"
            probe.write_text("")
            probe.unlink()
            return candidate
        except OSError:
            continue
    import tempfile  # noqa: PLC0415

    return Path(tempfile.mkdtemp(prefix="mantel-nudges-"))


def state_path() -> Path:
    return data_dir() / "nudges" / "nudges.json"


@dataclass
class Nudge:
    """One thing worth saying, if the budget allows."""

    key: str
    title: str
    body: str
    priority: int = 5          # lower fires first when the budget is tight


@dataclass
class Proactivity:
    """The policy: what may be shown, and what already was."""

    enabled: bool = True
    budget: int = DEFAULT_BUDGET
    brief_hour: int = DEFAULT_BRIEF_HOUR
    quiet_start: int = DEFAULT_QUIET_START
    quiet_end: int = DEFAULT_QUIET_END
    fired: dict = field(default_factory=dict)   # key -> timestamp
    day: str = ""
    shown: int = 0

    # -- persistence -------------------------------------------------------
    @classmethod
    def load(cls) -> "Proactivity":
        try:
            raw = json.loads(state_path().read_text())
        except (OSError, ValueError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        policy = cls()
        config = raw.get("config") if isinstance(raw.get("config"), dict) else {}
        state = raw.get("state") if isinstance(raw.get("state"), dict) else {}
        for key in ("enabled", "budget", "brief_hour", "quiet_start",
                    "quiet_end"):
            if key in config:
                setattr(policy, key, config[key])
        policy.fired = dict(state.get("fired") or {})
        policy.day = str(state.get("day") or "")
        policy.shown = int(state.get("shown") or 0)
        return policy

    def save(self) -> bool:
        payload = {
            "config": {"enabled": self.enabled, "budget": self.budget,
                       "brief_hour": self.brief_hour,
                       "quiet_start": self.quiet_start,
                       "quiet_end": self.quiet_end},
            "state": {"fired": self.fired, "day": self.day,
                      "shown": self.shown},
        }
        try:
            path = state_path()
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=1))
            tmp.replace(path)
            return True
        except OSError:
            return False

    # -- policy ------------------------------------------------------------
    def _roll_day(self, now: float) -> None:
        today = datetime.fromtimestamp(now).strftime("%Y-%m-%d")
        if self.day != today:
            self.day = today
            self.shown = 0
            # keep per-day keys out of the map so it cannot grow forever
            self.fired = {key: stamp for key, stamp in self.fired.items()
                          if not key.startswith("brief:")}

    def quiet(self, now: float) -> bool:
        hour = datetime.fromtimestamp(now).hour
        if self.quiet_start == self.quiet_end:
            return False
        if self.quiet_start < self.quiet_end:
            return self.quiet_start <= hour < self.quiet_end
        return hour >= self.quiet_start or hour < self.quiet_end

    def remaining(self, now: float) -> int:
        self._roll_day(now)
        return max(0, int(self.budget) - self.shown)

    # -- the rules ---------------------------------------------------------
    def plan(self, now: float | None = None) -> list[Nudge]:
        """Every candidate worth mentioning right now, best first."""
        now = now if now is not None else time.time()
        found: list[Nudge] = []
        day = datetime.fromtimestamp(now).strftime("%Y-%m-%d")

        # 1. something is about to start
        try:
            horizon = now + EVENT_LEAD_MINUTES * 60
            for event in calendar_store.events_between(now, horizon):
                if event.all_day or event.start < now:
                    continue
                key = f"event:{event.uid or event.title}:{int(event.start)}"
                if key in self.fired:
                    continue
                minutes = max(1, int((event.start - now) // 60))
                found.append(Nudge(
                    key=key,
                    title=event.title,
                    body=f"starts in {minutes} min"
                         + (f" · {event.location}" if event.location else ""),
                    priority=1))
        except Exception:  # noqa: BLE001 - a calendar must not break nudges
            pass

        # 2. too much is late
        try:
            open_tasks = todos.all_tasks(include_done=False)
            late = [task for task in open_tasks
                    if task.due and task.due < now]
            key = f"overdue:{day}"
            if len(late) >= OVERDUE_THRESHOLD and key not in self.fired:
                found.append(Nudge(
                    key=key, title=f"{len(late)} things are late",
                    body=", ".join(task.title for task in late[:3])
                         + ("…" if len(late) > 3 else ""),
                    priority=4))
        except Exception:  # noqa: BLE001
            pass

        # 3. the morning brief
        key = f"brief:{day}"
        if datetime.fromtimestamp(now).hour >= int(self.brief_hour) \
                and key not in self.fired:
            try:
                due_today = todos.today(now=now)
                events = calendar_store.today(now=now)
                if due_today or events:
                    parts = []
                    if due_today:
                        parts.append(f"{len(due_today)} due")
                    if events:
                        parts.append(f"{len(events)} event"
                                     f"{'' if len(events) == 1 else 's'}")
                    found.append(Nudge(
                        key=key,
                        title="Today",
                        body=" · ".join(parts) + " — open the day to plan.",
                        priority=6))
            except Exception:  # noqa: BLE001
                pass

        found.sort(key=lambda nudge: nudge.priority)
        return found

    def due(self, now: float | None = None) -> list[Nudge]:
        """What may actually be shown now: allowed, budgeted, not repeated."""
        now = now if now is not None else time.time()
        if not self.enabled or self.quiet(now):
            return []
        left = self.remaining(now)
        if left <= 0:
            return []
        return [nudge for nudge in self.plan(now) if nudge.key not in self.fired][:left]

    def mark(self, nudge: Nudge, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        self._roll_day(now)
        self.fired[nudge.key] = now
        self.shown += 1
        # yesterday's event/overdue keys are useless; drop the old ones
        cutoff = now - 2 * 86400
        self.fired = {key: stamp for key, stamp in self.fired.items()
                      if float(stamp) >= cutoff}
        self.save()


# --- the runner -------------------------------------------------------------

import gi  # noqa: E402

gi.require_version("GLib", "2.0")
from gi.repository import GLib, GObject  # noqa: E402

#: Checks are cheap and local; a minute is the right granularity.
TICK_SECONDS = 60


class NudgeRunner(GObject.Object):
    """Watches the policy and reports what may be shown."""

    __gsignals__ = {
        # nudge
        "nudge": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self, policy: Proactivity | None = None) -> None:
        super().__init__()
        self.policy = policy or Proactivity.load()
        self._timer_id = 0

    def start(self) -> None:
        if self._timer_id:
            return
        self._timer_id = GLib.timeout_add_seconds(TICK_SECONDS, self._tick)
        GLib.timeout_add_seconds(20, self._tick)

    def stop(self) -> None:
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = 0

    def reload(self) -> None:
        """Pick up settings changed in the UI."""
        enabled, budget = self.policy.enabled, self.policy.budget
        fresh = Proactivity.load()
        fresh.enabled, fresh.budget = enabled, budget
        self.policy = fresh

    def _tick(self) -> bool:
        try:
            due = self.policy.due()
        except Exception:  # noqa: BLE001 - a bad rule must not kill the timer
            due = []
        for nudge in due:
            try:
                self.policy.mark(nudge)
            except Exception:  # noqa: BLE001
                pass
            self.emit("nudge", nudge)
        return True
