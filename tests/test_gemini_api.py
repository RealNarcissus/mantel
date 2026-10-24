"""Tests for the Gemini API engine, against a local fake API.

No key and no network: a tiny HTTP server speaks the two endpoints the adapter
uses (model listing and SSE streaming), so the interesting behaviour — streaming
deltas, usage, error mapping, and what the request actually sends — is pinned
without touching Google's servers.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import fonts_env  # noqa: F401,E402

sys.path.insert(0, str(ROOT / "tests" / "fixtures"))

import gi  # noqa: E402

gi.require_version("GLib", "2.0")
from fake_gemini import Fake, serve  # noqa: E402
from gi.repository import GLib  # noqa: E402

from app import engine as engine_mod  # noqa: E402
from app.engines import gemini_api  # noqa: E402


def collect(turn, timeout: int = 20) -> dict:
    loop = GLib.MainLoop()
    seen = {"deltas": [], "finished": None, "failed": None}
    turn.connect("delta", lambda _t, text: seen["deltas"].append(text))
    turn.connect("finished", lambda _t, result: (
        seen.update(finished=result), loop.quit()))
    turn.connect("failed", lambda _t, message: (
        seen.update(failed=message), loop.quit()))
    GLib.timeout_add_seconds(timeout, lambda: (loop.quit(), False)[1])
    loop.run()
    return seen


def main() -> int:
    failures: list[str] = []
    server, base = serve()
    print(f"  fake API on {base}")

    # --- availability ---------------------------------------------------
    no_key = engine_mod.Engine(adapter="gemini")
    if no_key.available:
        failures.append("the adapter claims to be available without a key")
    seen = collect(no_key.run("hello"), timeout=5)
    print(f"  no key -> failed={str(seen['failed'])[:60]!r}")
    if not seen["failed"] or "key" not in str(seen["failed"]).lower():
        failures.append("a missing key should fail with an explanation")

    adapter = gemini_api.GeminiAdapter(key="test-key", base=base)
    if not adapter.available:
        failures.append("a key should make the adapter available")

    # --- models ---------------------------------------------------------
    models = adapter.models()
    print(f"  models: {models}")
    if [m for m, _ in models] != ["gemini-2.0-flash"]:
        failures.append(f"model listing is wrong or unfiltered: {models}")
    if any("embedding" in label.lower() for _m, label in models):
        failures.append("a non-generateContent model was offered")

    # --- streaming turn -------------------------------------------------
    Fake.seen.clear()
    turn = adapter.run("Say hello", model="gemini-2.0-flash")
    seen = collect(turn)
    print(f"  deltas: {seen['deltas']} finished={seen['finished']}")
    if "".join(seen["deltas"]) != "Hello world":
        failures.append(f"streaming did not accumulate: {seen['deltas']}")
    result = seen["finished"] or {}
    if result.get("status") != "SUCCESS":
        failures.append(f"status was {result.get('status')!r}")
    if (result.get("usage") or {}).get("total_tokens") != 9:
        failures.append(f"usage was not normalised: {result.get('usage')}")
    if not Fake.seen:
        failures.append("the adapter sent no request")
    else:
        body = Fake.seen[-1]["body"]
        sent = (body.get("contents") or [{}])[0].get("parts") or [{}]
        print(f"  request body: {json.dumps(body)[:120]}")
        if sent[0].get("text") != "Say hello":
            failures.append(f"the prompt was not sent as a text part: {body}")
        if "key=" not in Fake.seen[-1]["path"]:
            failures.append("the API key was not passed as a query parameter")

    # --- key not sent over the wire in a body ---------------------------
    if "test-key" in json.dumps([entry["body"] for entry in Fake.seen]):
        failures.append("the API key leaked into the request body")

    # --- HTTP error mapping ---------------------------------------------
    Fake.fail_status = 401
    seen = collect(adapter.run("hello"))
    Fake.fail_status = 0
    result = seen["finished"] or {}
    print(f"  http 401 -> status={result.get('status')!r} "
          f"error={str(result.get('error'))[:50]!r}")
    if result.get("status") != "ERROR":
        failures.append("an HTTP error should finish with status ERROR")
    if "key" not in str(result.get("error", "")).lower():
        failures.append(f"the API's message was lost: {result.get('error')}")
    if seen["failed"]:
        failures.append("an HTTP error should not also emit failed")

    # --- tools: read is free, write asks --------------------------------
    workspace = Path(tempfile.mkdtemp(prefix="mantel-gem-ws-"))
    (workspace / "notes.txt").write_text("the quick brown fox")
    tool_adapter = gemini_api.GeminiAdapter(key="test-key", base=base)

    Fake.tool_mode = "read"
    turn = tool_adapter.run("read the notes", model="gemini-2.0-flash",
                            cwd=str(workspace))
    seen = collect(turn)
    result = seen["finished"] or {}
    print(f"  tool read -> status={result.get('status')!r} "
          f"text={str(result.get('text'))[:60]!r}")
    if result.get("status") != "SUCCESS":
        failures.append(f"the read tool turn failed: {result.get('error')}")
    if "quick brown fox" not in str(result.get("text")):
        failures.append("the read tool's result never reached the model")
    if len(Fake.seen) < 2:
        failures.append("the loop did not send the tool result back")
    requests = [json.loads(json.dumps(entry["body"])) for entry in Fake.seen]
    if not any(entry.get("tools") for entry in requests):
        failures.append("tool declarations were not sent to the API")

    # --- a denied write leaves no file ----------------------------------
    Fake.tool_mode = "write"
    dialogs = []

    def watch(_turn, request):
        dialogs.append(request)
        _turn.answer_dialog(request["id"], value="Deny")

    turn = tool_adapter.run("write the file", model="gemini-2.0-flash",
                            cwd=str(workspace))
    turn.connect("dialog", watch)
    seen = collect(turn)
    print(f"  denied write -> dialogs={len(dialogs)} "
          f"file={ (workspace / 'written.txt').exists() }")
    if not dialogs:
        failures.append("a write did not ask for approval")
    elif dialogs[0].get("method") != "select":
        failures.append(f"the approval card shape is wrong: {dialogs[0]}")
    if (workspace / "written.txt").exists():
        failures.append("a denied write still executed")
    if "denied" not in str((seen["finished"] or {}).get("text", "")).lower():
        failures.append("the model was not told the write was denied")

    # --- an approved write executes -------------------------------------
    Fake.tool_mode = "write"
    turn = tool_adapter.run("write the file", model="gemini-2.0-flash",
                            cwd=str(workspace))
    turn.connect("dialog",
                 lambda _t, request: _t.answer_dialog(request["id"],
                                                      value="Allow once"))
    seen = collect(turn)
    print(f"  approved write -> file exists="
          f"{(workspace / 'written.txt').exists()}")
    if not (workspace / "written.txt").exists():
        failures.append("an approved write did not execute")
    elif (workspace / "written.txt").read_text() != "hello from the model":
        failures.append("the written content is wrong")

    # --- a path outside the workspace is refused ------------------------
    outside = Path(tempfile.mkdtemp()) / "secret.txt"
    outside.write_text("nope")
    # no turn needed: check the guard directly
    outside_turn = gemini_api.GeminiTurn(cwd=str(workspace))
    tool_result = tool_adapter._run_tool(  # noqa: SLF001
        outside_turn, {"name": "read_file",
                       "args": {"path": str(outside)}})
    if "error" not in tool_result:
        failures.append(f"a path outside the workspace was not refused: "
                        f"{tool_result}")
    print(f"  outside path -> {tool_result.get('error', '')[:60]}")

    # --- the loop is bounded --------------------------------------------
    Fake.tool_mode = "loop"
    Fake.seen.clear()
    turn = tool_adapter.run("loop forever", model="gemini-2.0-flash",
                            cwd=str(workspace))
    turn.connect("dialog", lambda _t, request: _t.answer_dialog(
        request["id"], value="Allow once"))
    seen = collect(turn, timeout=30)
    print(f"  loop bound -> status={(seen['finished'] or {}).get('status')!r} "
          f"steps={len(Fake.seen)}")
    requests_after = len(Fake.seen)
    Fake.tool_mode = "none"
    if requests_after > gemini_api.MAX_STEPS + 2:
        failures.append(f"the tool loop was not bounded: {requests_after} calls")

    # --- the facade can select it ---------------------------------------
    import os  # noqa: PLC0415

    os.environ["MANTEL_ENGINE"] = "gemini"
    os.environ["GEMINI_API_KEY"] = "test-key"
    os.environ["MANTEL_GEMINI_BASE"] = base
    try:
        engine = engine_mod.Engine()
        print(f"  facade -> {engine.name} available={engine.available} "
              f"caps={sorted(engine.capabilities)}")
        if engine.adapter_name != "gemini":
            failures.append("MANTEL_ENGINE did not select the gemini adapter")
        if not engine.supports(engine_mod.CHAT):
            failures.append("the gemini adapter should support chat")
        if not engine.supports(engine_mod.TOOLS):
            failures.append("the gemini adapter should advertise its tool loop")
        if not engine.supports(engine_mod.APPROVALS):
            failures.append("the gemini adapter should advertise approvals")
        # chat surfaces must survive a chat-only engine
        from app.window import pages_for  # noqa: PLC0415

        pages = [page[0] for page in pages_for(engine)]
        print(f"  pages for a chat-only engine: {pages}")
        if "chat" not in pages or "today" not in pages:
            failures.append(f"chat surfaces disappeared without tools: {pages}")
        if "create" in pages:
            failures.append("image generation offered without an image engine")
    finally:
        os.environ.pop("MANTEL_ENGINE", None)
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("MANTEL_GEMINI_BASE", None)

    server.shutdown()
    print()
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        return 1
    print("  gemini api engine: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
