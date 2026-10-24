"""Tests for scheduled runs becoming readable threads (M5).

A schedule that only stores its last output is a notification. A schedule whose
run creates a conversation is a *task with its own transcript* — that is the
milestone. These tests drive the real `Scheduler` with a fake engine and assert
on the store: the thread exists, has both turns, is titled after the schedule,
and the run points at it.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import fonts_env  # noqa: F401,E402

import gi  # noqa: E402

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from app import schedules as store  # noqa: E402
from app.scheduler import Scheduler  # noqa: E402
from app.store import Store  # noqa: E402


class FakeTurn:
    """A turn that answers immediately on the main loop."""

    def __init__(self, text: str = "", status: str = "SUCCESS") -> None:
        self.text = text
        self.status = status
        self._listeners: dict[str, list] = {"finished": [], "failed": []}

    def connect(self, signal: str, callback) -> None:
        self._listeners.setdefault(signal, []).append(callback)
        if signal == "finished":
            GLib.idle_add(self._emit)

    def cancel(self) -> None:
        pass

    def _emit(self) -> bool:
        for callback in self._listeners.get("finished", []):
            callback(self, {
                "status": self.status, "text": self.text,
                "error": "" if self.status == "SUCCESS" else "engine said no",
                "conversation_id": "engine-side-id",
            })
        return False


class FakeEngine:
    """The slice of the facade the scheduler uses."""

    def __init__(self, text: str = "The briefing is ready.",
                 status: str = "SUCCESS") -> None:
        self.available = True
        self.name = "fake"
        self.text = text
        self.status = status
        self.prompts: list[str] = []
        self.capabilities = frozenset()

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def run(self, **kwargs):
        self.prompts.append(str(kwargs.get("prompt") or ""))
        return FakeTurn(self.text, self.status)


def wait(signal_target, timeout: float = 15.0) -> None:
    loop = GLib.MainLoop()
    held = {}

    def on_signal(_target, *_args):
        held["fired"] = True
        loop.quit()

    signal_target.connect("ran", on_signal)
    signal_target.connect("failed", on_signal)
    GLib.timeout_add_seconds(int(timeout), lambda: (loop.quit(), False)[1])
    loop.run()
    if not held.get("fired"):
        raise AssertionError("the scheduler did not report a result")


def main() -> int:
    failures: list[str] = []
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="mantel-sched-")

    # --- a successful run creates a thread -------------------------------
    schedule = store.Schedule(title="Morning brief",
                              prompt="Summarise my day.", cron="0 9 * * *")
    if not store.save(schedule):
        failures.append("the schedule fixture could not be saved")
    engine = FakeEngine("Three things today: A, B, C.")
    conversations = Store()
    scheduler = Scheduler(engine, store=conversations)
    scheduler.run(schedule)
    wait(scheduler)

    runs = [s for s in store.list_schedules() if s.id == schedule.id][0].runs
    run = runs[-1]
    print(f"  run: status={run.status!r} thread={run.conversation_id!r}")
    if not run.conversation_id:
        failures.append("the run does not point at a conversation")

    conv = conversations.load(run.conversation_id) if run.conversation_id else None
    if conv is None:
        failures.append("the run's conversation was not saved")
    else:
        roles = [message.role for message in conv.messages]
        print(f"  thread: {conv.title!r} roles={roles}")
        if roles != ["user", "assistant"]:
            failures.append(f"the thread does not have both turns: {roles}")
        elif conv.messages[0].text != "Summarise my day.":
            failures.append("the thread's user turn is not the schedule prompt")
        elif conv.messages[1].text != "Three things today: A, B, C.":
            failures.append("the thread's assistant turn is not the result")
        if "Morning brief" not in conv.title:
            failures.append(f"the thread is not titled after the schedule: {conv.title!r}")
        if conv.pending_prompt or conv.interrupted:
            failures.append("the thread was left looking interrupted")
    if not engine.prompts or "Morning brief" not in engine.prompts[0] \
            and "Summarise my day." not in engine.prompts[0]:
        failures.append(f"the schedule prompt was not sent: {engine.prompts[:1]}")

    # opening the thread through the store is what the UI does
    if conv is not None:
        opened = Store().load(conv.id)
        if opened is None or not opened.messages:
            failures.append("the run thread cannot be reopened")

    # --- a failed run still leaves a readable thread --------------------
    schedule2 = store.Schedule(title="Broken job", prompt="Do the impossible.",
                               cron="0 10 * * *")
    store.save(schedule2)
    broken = Store()
    failing = Scheduler(FakeEngine(status="ERROR"), store=broken)
    failing.run(schedule2)
    wait(failing)
    runs2 = [s for s in store.list_schedules() if s.id == schedule2.id][0].runs
    run2 = runs2[-1]
    print(f"  failed run: status={run2.status!r} thread={run2.conversation_id!r}")
    if run2.status != "ERROR":
        failures.append(f"a failing engine produced status {run2.status!r}")
    conv2 = broken.load(run2.conversation_id) if run2.conversation_id else None
    if conv2 is None:
        failures.append("a failed run left no thread to read")
    else:
        if conv2.messages[-1].role != "assistant":
            failures.append("the failed thread has no closing message")
        if not conv2.messages[-1].error:
            failures.append("the failed thread does not record the error")

    # --- a scheduler without a store still runs -------------------------
    stateless = Scheduler(FakeEngine("fine"))
    schedule3 = store.Schedule(title="Headless", prompt="Ping.",
                               cron="0 11 * * *")
    store.save(schedule3)
    stateless.run(schedule3)
    wait(stateless)
    if not [s for s in store.list_schedules() if s.id == schedule3.id][0].runs:
        failures.append("a scheduler without a store recorded no run")

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        return 1
    print("  schedule threads: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
