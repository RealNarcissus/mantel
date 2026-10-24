"""A fake Gemini REST API for tests.

Speaks the two endpoints the adapter uses — model listing and SSE streaming —
plus a tool protocol so the tool loop can be exercised without a key or network.

`tool_mode` controls the answer: "none" streams text, "read"/"write" ask for a
function call first then answer with the tool result, "loop" keeps asking (to
prove the loop is bounded).
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
    #: "none" streams text; "read" asks for read_file then answers;
    #: "write" asks for write_file; "loop" asks forever
    tool_mode = "none"

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
        body = Fake.seen[-1]["body"]
        chunks = self._chunks_for(body)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for chunk in chunks:
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.wfile.flush()

    def _chunks_for(self, body: dict) -> list[dict]:
        if Fake.tool_mode == "none":
            return STREAM_CHUNKS
        contents = body.get("contents") or []
        answered = any(
            isinstance(part, dict) and "functionResponse" in part
            for entry in contents if isinstance(entry, dict)
            for part in (entry.get("parts") or []))
        if Fake.tool_mode == "loop" or not answered:
            name = {"read": "read_file", "write": "write_file",
                    "loop": "read_file"}.get(Fake.tool_mode, "read_file")
            args = {"path": "notes.txt"}
            if name == "write_file":
                args = {"path": "written.txt", "content": "hello from the model"}
            return [{"candidates": [{
                "content": {"role": "model", "parts": [
                    {"functionCall": {"name": name, "args": args}}]},
                "finishReason": "STOP"}]}]
        result = ""
        for entry in contents:
            for part in (entry.get("parts") or []):
                if isinstance(part, dict) and "functionResponse" in part:
                    result = json.dumps(part["functionResponse"]
                                        .get("response", {}))
        return [{"candidates": [{
            "content": {"role": "model", "parts": [
                {"text": f"Tool said: {result}"}]},
            "finishReason": "STOP"}]}]

    def _json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)



def serve() -> tuple[ThreadingHTTPServer, str]:
    """Start the fake API on a free port; returns (server, base_url)."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"
