"""Tests for the command palette's interpretation and its capture CLI.

The palette's promise is that a phrase does the obvious thing. These checks
pin the obvious thing down: prefixes win over guessing, navigation is
restricted to the surfaces the engine backs, and a bare phrase becomes a task
with the date parsed out of it.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import fonts_env  # noqa: F401,E402

from app import memory, palette, todos  # noqa: E402


def kinds(actions: list[palette.Action]) -> list[str]:
    return [action.kind for action in actions]


def main() -> int:
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="mantel-palette-")
    failures: list[str] = []

    # --- an empty query offers navigation and commands -------------------
    idle = palette.interpret("")
    print(f"  empty: {[(a.kind, a.label) for a in idle[:3]]}…")
    if not idle:
        failures.append("an empty palette offered nothing")
    if not any(action.kind == "navigate" for action in idle):
        failures.append("an empty palette offered no navigation")

    # --- a bare phrase becomes a task with a parsed date ----------------
    task = palette.interpret("call the dentist tomorrow")[0]
    print(f"  bare phrase -> {task.kind}: {task.label!r} ({task.detail})")
    if task.kind != "task":
        failures.append(f"a bare phrase resolved to {task.kind}, not a task")
    if "dentist" not in task.label:
        failures.append(f"the task label lost its text: {task.label!r}")
    from datetime import datetime, timedelta  # noqa: PLC0415

    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%d %b")
    if tomorrow not in task.detail:
        failures.append(f"the task lost its date: {task.detail!r}")

    # --- explicit intents beat the default ------------------------------
    asked = palette.interpret("ask what did I do yesterday")[0]
    if asked.kind != "ask" or asked.payload != "what did I do yesterday":
        failures.append(f"'ask' was not parsed: {asked}")

    note = palette.interpret("note prefers deep work before noon")[0]
    if note.kind != "note" or "deep work" not in note.payload:
        failures.append(f"'note' was not parsed: {note}")

    remind = palette.interpret("remind me to call mum at 18:00")[0]
    print(f"  remind -> {remind.kind}: {remind.label!r} ({remind.detail})")
    if remind.kind != "remind":
        failures.append(f"'remind' was not parsed: {remind}")
    if "18:00" not in remind.detail:
        failures.append(f"the reminder time was not parsed: {remind.detail!r}")

    # --- navigation, limited to what the engine backs -------------------
    chat = palette.interpret("cha")
    if not chat or chat[0].kind != "navigate" or chat[0].payload != "chat":
        failures.append(f"navigation by prefix failed: {chat[:2]}")
    limited = palette.interpret("cre", pages=["chat", "tasks"])
    offered = {action.payload for action in limited if action.kind == "navigate"}
    print(f"  restricted navigation: {sorted(offered)}")
    if not offered <= {"chat", "tasks"}:
        failures.append(f"navigation offered a surface the engine lacks: {offered}")

    # --- commands -------------------------------------------------------
    commands = palette.interpret(">focus")
    if not commands or commands[0].payload != "start-focus":
        failures.append(f"command search failed: {commands}")
    if not any(action.payload == "new-thread"
               for action in palette.interpret("new")):
        failures.append("the New thread command was not found")

    # --- a known fact surfaces instead of becoming a task ---------------
    memory.remember("Prefers deep work before noon", kind="preference")
    found = palette.interpret("deep work")
    print(f"  memory lookup -> {[(a.kind, a.payload) for a in found[:2]]}")
    if not found or found[0].kind != "remembered":
        failures.append(f"a known fact was not surfaced: {kinds(found)}")

    # --- capture without a window ---------------------------------------
    before = len(todos.all_tasks())
    result = subprocess.run(
        [sys.executable, "-m", "app.main", "--capture", "pay the invoice tomorrow"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
        env={**os.environ, "XDG_DATA_HOME": os.environ["XDG_DATA_HOME"]})
    after = len(todos.all_tasks())
    print(f"  cli capture: rc={result.returncode} tasks {before}->{after} "
          f"out={result.stdout.strip()!r}")
    if result.returncode != 0:
        failures.append(f"--capture failed: {result.stderr[-300:]}")
    if after != before + 1:
        failures.append("--capture did not add a task")
    if not result.stdout.strip():
        failures.append("--capture printed nothing back")

    # a capture that is a note goes to memory instead
    mem_before = len(memory.facts())
    subprocess.run(
        [sys.executable, "-m", "app.main", "--capture",
         "note: prefers early meetings"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
        env={**os.environ, "XDG_DATA_HOME": os.environ["XDG_DATA_HOME"]})
    print(f"  cli capture note: facts {mem_before}->{len(memory.facts())}")
    if len(memory.facts()) <= mem_before:
        failures.append("a note capture did not reach memory")

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        return 1
    print("  palette: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
