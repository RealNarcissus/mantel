"""Tests for the Gemini API engine, against a local fake API.

No key and no network: a tiny HTTP server speaks the two endpoints the adapter
uses (model listing and SSE streaming), so the interesting behaviour — streaming
deltas, usage, error mapping, and what the request actually sends — is pinned
without touching Google's servers.
"""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import fonts_env  # noqa: F401,E402

import gi  # noqa: E402

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from app import engine as engine_mod  # noqa: E402
from app.engines import gemini_api  # noqa: E402

MODELS = {
    "models": [
        {"name": "models/gemini-2.0-flash", "displayName": "Gemini 2.0 Flash",
         "supportedGenerationMethods": ["generateContent", "countTokens"]},
        {"name": "models/text-embedding-004", "displayName": "Embedding",
         "supportedGenerationMethods": ["embedContent"]},
    ]
}

STREAM_CHUNKS = [
    {"candidates": [{"content": {"parts": [{"text": "Hel"}]}}]},
    {"candidates": [{"content": {"parts": [{"text": "lo"}]}}],
     "usageMetadata": {"promptTokenCount": 7, "candidatesTokenCount": 2,
                       "totalTokenCount": 9}},
    {"candidates": [{"content": {"parts": [{"text": " world"}]},
                     "finishReason": "STOP"}]},
]


class Fake(BaseHTTPRequestHandler):
    """Serves the two endpoints; records what it was asked for."""

    seen: list[dict] = []
    fail_status = 0

    def log_message(self, *_args):
        pass

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/v1beta/models"):
            self._json(200, MODELS)
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            Fake.seen.append({"path": self.path, "body": json.loads(body or "{}")})
        except ValueError:
            Fake.seen.append({"path": self.path, "body": {}})
        if Fake.fail_status:
            self._json(Fake.fail_status,
                       {"error": {"message": "API key not valid"}})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for chunk in STREAM_CHUNKS:
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.wfile.flush()

    def _json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


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
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
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
        if engine.supports(engine_mod.TOOLS):
            failures.append("the gemini adapter has no tool loop yet")
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
