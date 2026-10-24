"""The engine adapter contract, run against the Pi adapter and the fake engine.

This is the suite that defines "an engine is supported" (docs/plan/pi-engine.md,
M0/M1). It needs no real engine and no credentials: `tests/fixtures/fake_pi.py`
speaks enough of Pi's RPC protocol to exercise every signal the shell binds to.

    python3 tests/test_engine_adapter.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import fonts_env  # noqa: F401,E402

import gi  # noqa: E402

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from app import engine as engine_mod  # noqa: E402
from app.engines import base  # noqa: E402

FAKE_PI = ROOT / "tests" / "fixtures" / "fake_pi.py"


# --- helpers ---------------------------------------------------------------

def collect(turn, timeout: int = 20) -> dict:
    """Run a turn to completion, collecting everything it emits."""
    loop = GLib.MainLoop()
    seen: dict = {"deltas": [], "thoughts": [], "tools": [], "finished": None,
                  "failed": None, "started": None}

    turn.connect("started", lambda _t, cid: seen.update(started=cid))
    turn.connect("delta", lambda _t, text: seen["deltas"].append(text))
    turn.connect("thought", lambda _t, text: seen["thoughts"].append(text))
    turn.connect("tool", lambda _t, name, payload: seen["tools"].append(
        (name, payload)))
    turn.connect("finished", lambda _t, result: (
        seen.update(finished=result), loop.quit()))
    turn.connect("failed", lambda _t, message: (
        seen.update(failed=message), loop.quit()))
    GLib.timeout_add_seconds(timeout, lambda: (loop.quit(), False)[1])
    loop.run()
    return seen


def pi_engine() -> engine_mod.Engine:
    return engine_mod.Engine(adapter="pi", binary=str(FAKE_PI))


# --- the tests -------------------------------------------------------------

def test_models(failures: list[str]) -> None:
    engine = pi_engine()
    models = engine.models()
    print(f"  models: {models}")
    ids = [m for m, _ in models]
    if "fake/fake-fast" not in ids:
        failures.append(f"model list missing fake/fake-fast: {ids}")
    if any("Fake Fast" not in label for mid, label in models
           if mid.endswith("fake-fast")):
        failures.append("model label did not come from Pi's name field")


def test_streaming_turn(failures: list[str]) -> None:
    engine = pi_engine()
    turn = engine.run("hello")
    seen = collect(turn)
    print(f"  deltas: {seen['deltas']}")
    print(f"  tools:  {[name for name, _ in seen['tools']]}")
    print(f"  result: {seen['finished']}")

    if seen["failed"]:
        failures.append(f"turn failed: {seen['failed']}")
        return
    if "".join(seen["deltas"]) != "Hello world":
        failures.append(f"deltas did not join to the reply: {seen['deltas']}")
    if seen["started"] != "fake-session-0001":
        failures.append(f"started signal carried {seen['started']!r}")
    if not seen["tools"]:
        failures.append("no tool events were emitted")
    else:
        name, payload = seen["tools"][-1]
        if name != "bash":
            failures.append(f"tool name was {name!r}")
        import json  # noqa: PLC0415

        data = json.loads(payload)
        if data.get("state") != "DONE":
            failures.append(f"tool did not finish: {data.get('state')!r}")
        if "hi" not in (data.get("output") or ""):
            failures.append(f"tool output missing: {data.get('output')!r}")

    result = seen["finished"] or {}
    if result.get("status") != "SUCCESS":
        failures.append(f"status was {result.get('status')!r}")
    if result.get("text") != "Hello world":
        failures.append(f"result text was {result.get('text')!r}")
    if result.get("conversation_id") != "fake-session-0001":
        failures.append("result did not carry the session id")
    if (result.get("usage") or {}).get("total_tokens") != 12:
        failures.append(f"usage not normalised: {result.get('usage')!r}")


def test_chat_mode_is_read_only(failures: list[str]) -> None:
    adapter = engine_mod.Engine(adapter="pi", binary=str(FAKE_PI)).adapter
    flags = adapter._mode_flags("chat")
    print(f"  chat flags: {flags}")
    if flags[:2] != ["--tools", "read,grep,find,ls"]:
        failures.append(f"chat mode did not restrict tools: {flags}")
    if adapter._mode_flags("task") != []:
        failures.append("task mode should keep the default tool set")


def test_rejected_prompt(failures: list[str]) -> None:
    engine = pi_engine()
    seen = collect(engine.run("fail"))
    print(f"  rejected -> finished={seen['finished']!r} failed={seen['failed']!r}")
    result = seen["finished"] or {}
    if result.get("status") != "ERROR":
        failures.append("a rejected prompt should finish with status ERROR")
    if "provider" not in (result.get("error") or ""):
        failures.append(f"rejection reason missing: {result.get('error')!r}")


def test_crash(failures: list[str]) -> None:
    engine = pi_engine()
    seen = collect(engine.run("crash"))
    print(f"  crash -> failed={seen['failed']!r}")
    if not seen["failed"]:
        failures.append("a process that exits mid-turn must emit failed")
    elif "exited" not in seen["failed"]:
        failures.append(f"unhelpful crash message: {seen['failed']!r}")


def test_cancel(failures: list[str]) -> None:
    engine = pi_engine()
    turn = engine.run("slow")
    state: dict = {}

    def once_a_delta(_t, _text):
        turn.cancel()

    turn.connect("delta", once_a_delta)
    seen = collect(turn, timeout=15)
    print(f"  cancel -> failed={seen['failed']!r}")
    if not seen["failed"]:
        failures.append("a cancelled turn must emit failed")
    elif "cancelled" not in seen["failed"]:
        failures.append(f"unhelpful cancel message: {seen['failed']!r}")


def test_dialog_is_declined(failures: list[str]) -> None:
    """Until M2, a blocking engine dialog must be answered, not ignored."""
    engine = pi_engine()
    seen = collect(engine.run("dialog"), timeout=15)
    text = "".join(seen["deltas"])
    print(f"  dialog -> deltas={seen['deltas']!r}")
    if seen["failed"]:
        failures.append(f"dialog turn failed: {seen['failed']}")
        return
    if "answer:False" not in text:
        failures.append(f"the dialog was not declined: {text!r}")


def test_facade(failures: list[str]) -> None:
    os.environ["MANTEL_ENGINE"] = "pi"
    os.environ["MANTEL_PI_BIN"] = str(FAKE_PI)
    try:
        engine = engine_mod.Engine()
        print(f"  selected: {engine.adapter_name} ({engine.name})")
        if engine.adapter_name != "pi":
            failures.append("MANTEL_ENGINE did not select the pi adapter")
        if not engine.supports(base.APPROVALS):
            failures.append("the pi adapter should advertise approvals")

        os.environ["MANTEL_ENGINE"] = "nonsense"
        fallback = engine_mod.Engine()
        print(f"  unknown engine -> {fallback.adapter_name}")
        if fallback.adapter_name != engine_mod.DEFAULT_ADAPTER:
            failures.append("an unknown engine did not fall back to the default")
    finally:
        os.environ.pop("MANTEL_ENGINE", None)
        os.environ.pop("MANTEL_PI_BIN", None)


def test_missing_engine(failures: list[str]) -> None:
    engine = engine_mod.Engine(adapter="pi", binary="/nonexistent/pi")
    seen = collect(engine.run("hello"), timeout=5)
    print(f"  missing binary -> failed={seen['failed']!r}")
    if not seen["failed"]:
        failures.append("a missing engine must fail fast, not hang")
    if engine.models() != [("", "Pi default")]:
        failures.append(f"unexpected model fallback: {engine.models()}")


def main() -> int:
    if not FAKE_PI.is_file():
        print(f"  missing fixture: {FAKE_PI}")
        return 1
    os.chmod(FAKE_PI, 0o755)

    failures: list[str] = []
    for test in (test_models, test_streaming_turn, test_chat_mode_is_read_only,
                 test_rejected_prompt, test_crash, test_cancel,
                 test_dialog_is_declined, test_facade, test_missing_engine):
        print(f"\n  {test.__name__}")
        test(failures)

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        return 1
    print("  engine adapter contract: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
