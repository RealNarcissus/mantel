"""Tests for interrupted turns: the store fields, the UI guard, and a real kill.

Three layers:

1. the store remembers a turn that was running, and reloading it knows that it
   never finished;
2. the *window's* `submit()` is checked to contain no demo seeding — a real
   regression where a patch to `load_demo` also applied to `submit`, silently
   writing sample tasks and installing a plugin on every message;
3. a real `kill -9` of the app mid-turn, then a restart: the conversation must
   come back marked interrupted rather than stuck "running" or lost.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import fonts_env  # noqa: F401,E402

from app.store import Conversation, Store  # noqa: E402


def wait_for_pending(data_home: str, timeout: float = 40.0) -> Path | None:
    """Poll the store until a conversation records a pending turn."""
    deadline = time.time() + timeout
    root = Path(data_home) / "gemini-desktop" / "conversations"
    while time.time() < deadline:
        for path in root.glob("*.json"):
            try:
                raw = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if raw.get("pending_prompt"):
                return path
        time.sleep(0.25)
    return None


def main() -> int:
    failures: list[str] = []
    data_home = tempfile.mkdtemp(prefix="mantel-resume-")
    os.environ["XDG_DATA_HOME"] = data_home

    # --- 1. store round trip -------------------------------------------
    store = Store()
    conv = store.new(cwd=ROOT.as_posix())
    conv.add("user", "do the thing")
    conv.begin_turn("do the thing")
    store.save(conv)

    reloaded = Store().load(conv.id)
    if reloaded is None or reloaded.pending_prompt != "do the thing":
        failures.append("the pending turn did not survive a reload")
    if not reloaded.recover():
        failures.append("recover() did not notice the pending turn")
    if not reloaded.interrupted or reloaded.pending_prompt:
        failures.append("recover() left the conversation in a bad state")
    print(f"  store: interrupted={reloaded.interrupted} "
          f"pending={reloaded.pending_prompt!r}")

    reloaded.end_turn()
    if reloaded.interrupted:
        failures.append("end_turn() did not clear the interrupted flag")

    # a clean conversation is not marked
    clean = Store().new(cwd=ROOT.as_posix())
    clean.add("user", "hello")
    Store().save(clean)
    if Store().load(clean.id).recover():
        failures.append("a clean conversation was marked interrupted")

    # --- 2. submit() must not seed demo data --------------------------
    source = (ROOT / "app" / "window.py").read_text()
    start = source.index("    def submit(self, text: str) -> None:")
    end = source.index("\n    def steer(", start)
    body = source[start:end]
    for marker in ("mantel-demo", "day-summary", "Pay the invoice today",
                   "record_focus"):
        if marker in body:
            failures.append(f"submit() still contains demo seeding: {marker}")
    if "memory_mod.capture(text)" not in body:
        failures.append("submit() lost the memory capture")
    print(f"  submit(): {len(body.splitlines())} lines, no demo seeding")

    # --- 3. kill -9 the app mid-turn, then restart --------------------
    env = {
        **os.environ,
        "XDG_DATA_HOME": data_home,
        "MANTEL_ENGINE": "pi",
        "MANTEL_PI_BIN": str(ROOT / "tests" / "fixtures" / "fake_pi.py"),
        "GSK_RENDERER": "cairo",
    }
    out = Path(tempfile.mkdtemp()) / "turn.png"
    first = subprocess.Popen(
        [sys.executable, "-m", "app.main", "--smoke-prompt", "slow",
         "--smoke", str(out)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    pending = wait_for_pending(data_home)
    print(f"  killed mid-turn: pending recorded={pending is not None}")
    if pending is None:
        first.kill()
        failures.append("the app never recorded a pending turn")
    else:
        first.send_signal(signal.SIGKILL)
        first.wait(timeout=20)

    # restart: the window marks the conversation and saves it
    second = subprocess.run(
        [sys.executable, "-m", "app.main", "--smoke", str(out)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    if "SMOKE ok=True" not in (second.stdout + second.stderr):
        failures.append(f"the restart did not render: {second.stderr[-300:]}")

    recovered = [c for c in Store().list() if c.messages]
    marked = [c for c in recovered if c.interrupted]
    print(f"  after restart: {len(recovered)} conversation(s), "
          f"{len(marked)} marked interrupted")
    if not recovered:
        failures.append("the conversation was lost across the kill")
    if not marked:
        failures.append("the interrupted conversation was not marked on restart")
    for conversation in marked:
        if conversation.pending_prompt:
            failures.append("a recovered conversation still has a pending turn")

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        return 1
    print("  resume: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
