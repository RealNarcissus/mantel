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
                  "failed": None, "started": None, "dialogs": []}

    turn.connect("started", lambda _t, cid: seen.update(started=cid))
    turn.connect("delta", lambda _t, text: seen["deltas"].append(text))
    turn.connect("thought", lambda _t, text: seen["thoughts"].append(text))
    turn.connect("tool", lambda _t, name, payload: seen["tools"].append(
        (name, payload)))
    turn.connect("finished", lambda _t, result: (
        seen.update(finished=result), loop.quit()))
    turn.connect("dialog", lambda _t, request: seen["dialogs"].append(request))
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


def _answer_first_dialog(turn, choice, timeout: int = 15) -> dict:
    """Run a turn, answer its first dialog with `choice`, return what happened."""
    state = {"seen": None, "text": []}

    def on_dialog(_turn, request):
        turn.answer_dialog(request["id"], value=choice)
        if request["method"] == "select" and choice is None:
            pass

    def on_deny(_turn, request):
        turn.answer_dialog(request["id"], cancelled=True)

    turn.connect("dialog", on_deny if choice is None else on_dialog)
    return collect(turn, timeout=timeout)


def test_approval_allow(failures: list[str]) -> None:
    """Allow once lets the tool run; the call is visible in the work panel."""
    engine = pi_engine()
    turn = engine.run("approve")
    seen = _answer_first_dialog(turn, "Allow once")
    text = "".join(seen["deltas"])
    print(f"  allow -> dialogs={len(seen['dialogs'])} deltas={text!r} "
          f"tools={[n for n, _ in seen['tools']]}")
    if not seen["dialogs"]:
        failures.append("no dialog reached the client")
    else:
        request = seen["dialogs"][0]
        if request.get("method") != "select":
            failures.append(f"dialog method was {request.get('method')!r}")
        options = request.get("options") or []
        if options[:2] != ["Allow once", "Allow for this session"]:
            failures.append(f"ladder not forwarded: {options}")
    if "decision:Allow once" not in text:
        failures.append(f"engine did not receive the answer: {text!r}")
    if not any(name == "bash" for name, _ in seen["tools"]):
        failures.append("an allowed tool should still run")
    if (seen["finished"] or {}).get("status") != "SUCCESS":
        failures.append("an allowed turn should settle successfully")


def test_approval_deny(failures: list[str]) -> None:
    """Deny blocks the call: the engine must never execute it."""
    engine = pi_engine()
    turn = engine.run("approve")
    seen = _answer_first_dialog(turn, None)
    text = "".join(seen["deltas"])
    print(f"  deny -> deltas={text!r} tools={[n for n, _ in seen['tools']]}")
    if "decision:cancelled" not in text:
        failures.append(f"engine did not see a refusal: {text!r}")
    if seen["tools"]:
        failures.append(f"a denied tool ran anyway: {seen['tools']}")


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


def test_shipped_extension_loads(failures: list[str]) -> None:
    """The approval gate is TypeScript; Pi transpiles it on load.

    This does not need credentials: loading the extension and answering a
    state request proves the file parses and registers.
    """
    import subprocess  # noqa: PLC0415

    extension = ROOT / "pi-extensions" / "approvals.ts"
    binary = os.environ.get("MANTEL_PI_BIN") or str(
        ROOT / ".pi-test" / "node_modules" / ".bin" / "pi")
    if not (Path(binary).is_file() and extension.is_file()):
        print("  skip: no pi binary or extension")
        return
    argv = [binary, "--mode", "rpc", "--no-session", "--extension", str(extension)]
    try:
        proc = subprocess.run(argv, input='{"id":"1","type":"get_state"}\n',
                              capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.SubprocessError) as exc:
        failures.append(f"could not run pi with the extension: {exc}")
        return
    out = proc.stdout
    errors = [line for line in proc.stderr.splitlines()
              if "extension" in line.lower() and "error" in line.lower()]
    print(f"  loaded with exit {proc.returncode}; "
          f"responses={out.count('\"type\":\"response\"')}")
    if '"command":"get_state"' not in out.replace(" ", ""):
        failures.append("pi did not answer get_state with the extension loaded")
    if errors:
        failures.append(f"extension reported errors: {errors[:2]}")


def test_capability_gating(failures: list[str]) -> None:
    """Switching engines changes what the app offers, not just who answers."""
    from app import session as session_mod  # noqa: PLC0415
    from app.window import pages_for  # noqa: PLC0415

    legacy = engine_mod.Engine(adapter="legacy")
    pi = pi_engine()

    for capability in ("account", "connectors", "skills", "permission_file",
                       "cli_flags"):
        if not legacy.supports(capability):
            failures.append(f"the legacy engine should advertise {capability}")
        if pi.supports(capability):
            failures.append(f"pi should not advertise {capability}")
    for capability in ("approvals", "sessions", "steering", "compaction"):
        if not pi.supports(capability):
            failures.append(f"pi should advertise {capability}")

    # approval modes are CLI flags: they must never reach an engine that would
    # reject them
    pi_flags = session_mod.Session(pi, mode=session_mod.MODE_TASK,
                                   approval="full").flags()
    legacy_flags = session_mod.Session(legacy, mode=session_mod.MODE_TASK,
                                       approval="full").flags()
    print(f"  flags: pi={pi_flags} legacy={legacy_flags}")
    if pi_flags:
        failures.append(f"vendor approval flags leaked to pi: {pi_flags}")
    if not legacy_flags:
        failures.append("legacy full access should pass its own flags")

    pi_pages = [page[0] for page in pages_for(pi)]
    legacy_pages = [page[0] for page in pages_for(legacy)]
    print(f"  pages: pi={pi_pages} legacy={legacy_pages}")
    for vendor_page in ("connectors", "skills"):
        if vendor_page in pi_pages:
            failures.append(f"{vendor_page} shown for an engine without it")
        if vendor_page not in legacy_pages:
            failures.append(f"{vendor_page} missing for the legacy engine")
    for shared in ("chat", "tasks", "create", "schedule"):
        if shared not in pi_pages:
            failures.append(f"{shared} missing for pi")


def main() -> int:
    if not FAKE_PI.is_file():
        print(f"  missing fixture: {FAKE_PI}")
        return 1
    os.chmod(FAKE_PI, 0o755)

    failures: list[str] = []
    for test in (test_models, test_streaming_turn, test_chat_mode_is_read_only,
                 test_rejected_prompt, test_crash, test_cancel,
                 test_approval_allow, test_approval_deny,
                 test_facade, test_missing_engine,
                 test_capability_gating, test_shipped_extension_loads):
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
