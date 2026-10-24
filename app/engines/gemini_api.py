"""Gemini API engine: the official API, with your own key.

This is the other half of the repositioning. The vendor CLI remains supported,
but the client must not *need* it: with a Gemini API key the same shell holds
the same conversation, streams the same deltas and needs no vendor account.

It speaks the public REST streaming endpoint directly rather than importing
`google-genai`:

    POST {base}/v1beta/models/{model}:streamGenerateContent?alt=sse&key=…
    ← server-sent events, each a JSON chunk with candidates[].content.parts[].text

Two reasons for hand-rolling ~150 lines here instead of adding the SDK as a
dependency: the app has no third-party Python dependencies today, and a REST
call is trivially testable against a local server — which is how this adapter is
verified without an API key. Switching to the official SDK later is a contained
change behind this interface.

What it does *not* do yet: tool calling. So the adapter advertises `chat` but
not `tools`; the shell shows the conversation and hides the agent-only surfaces
that need a tool loop. That is the capability system doing its job.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from app.engines.base import (  # noqa: E402
    APPROVALS, CHAT, DEFAULT_TIMEOUT, TOOLS, EngineAdapter, Turn,
)

#: Where the key comes from. `GEMINI_API_KEY` is the name the docs use.
API_KEY_ENV = "GEMINI_API_KEY"
BASE_ENV = "MANTEL_GEMINI_BASE"
MODEL_ENV = "MANTEL_GEMINI_MODEL"

DEFAULT_BASE = "https://generativelanguage.googleapis.com"

#: Used when the model catalogue cannot be listed (offline, or no network yet).
FALLBACK_MODELS = [("", "Gemini (server default)")]

REQUEST_TIMEOUT = 120

#: How many model turns one request may take (each may call tools).
MAX_STEPS = 8

#: File and command output caps, so a tool result cannot blow the context.
MAX_TOOL_BYTES = 64 * 1024
MAX_COMMAND_BYTES = 16 * 1024
COMMAND_TIMEOUT = 120

#: The tool surface. Read-only is free; writing and running need an approval.
TOOL_SPECS = [
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file inside the workspace.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write a UTF-8 text file inside the workspace. Asks "
                       "the user first.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"},
                           "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_command",
        "description": "Run a shell command in the workspace, returning its "
                       "output. Asks the user first.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
]

#: Read-only tools never trigger a permission card.
SAFE_TOOLS = frozenset({"read_file"})

APPROVAL_OPTIONS = ("Allow once", "Allow this session", "Deny")


def find_key() -> str:
    return (os.environ.get(API_KEY_ENV)
            or os.environ.get("MANTEL_GEMINI_KEY") or "").strip()


class GeminiTurn(Turn):
    """A turn against the REST streaming endpoint, including its tool loop."""

    def __init__(self, cwd: str = "") -> None:
        super().__init__("gemini")
        self.cwd = cwd or os.getcwd()
        self._started_at = time.monotonic()
        self._dialog_event = threading.Event()
        self._dialog_reply: tuple | None = None
        self._pending_dialog: dict | None = None
        self._session_grants: set[str] = set()

    # -- cancellation ------------------------------------------------------
    def cancel(self) -> None:
        # urllib has no cancel; the read loop checks `cancelled` between events
        self._cancelled = True

    # -- approvals ---------------------------------------------------------
    def _ask(self, request: dict, timeout: int = 600) -> str | None:
        """Block the pump thread on a UI answer. None means deny."""
        request = dict(request)
        request["id"] = request.get("id") or uuid.uuid4().hex[:8]
        self._pending_dialog = request
        self._dialog_reply = None
        self._dialog_event.clear()
        self.emit_soon("dialog", request)
        if not self._dialog_event.wait(timeout):
            self._pending_dialog = None
            return None
        self._pending_dialog = None
        value, confirmed, cancelled = self._dialog_reply or (None, None, True)
        if cancelled:
            return None
        if confirmed is not None:
            return "Allow once" if confirmed else None
        return None if value is None else str(value)

    def answer_dialog(self, request_id: str, *, value: str | None = None,
                      confirmed: bool | None = None,
                      cancelled: bool = False) -> bool:
        request = self._pending_dialog
        if not request or request.get("id") != request_id:
            return False
        self._dialog_reply = (value, confirmed, cancelled)
        self._dialog_event.set()
        return True

    def _approved(self, capability: str, title: str, body: str) -> bool:
        if capability in self._session_grants:
            return True
        answer = self._ask({
            "method": "select", "title": title, "body": body,
            "options": list(APPROVAL_OPTIONS), "capability": capability,
        })
        if answer is None:
            return False
        if answer.startswith("Deny"):
            return False
        if answer.startswith("Allow this session"):
            self._session_grants.add(capability)
        return True


class GeminiAdapter(EngineAdapter):
    """Streams from the Gemini API. Chat only — no tool loop yet."""

    name = "gemini"
    capabilities = frozenset({CHAT, TOOLS, APPROVALS})

    def __init__(self, key: str | None = None, base: str | None = None) -> None:
        self.key = (key if key is not None else find_key()).strip()
        self.base = (base or os.environ.get(BASE_ENV)
                     or DEFAULT_BASE).rstrip("/")
        self._models: list[tuple[str, str]] | None = None

    # -- availability -------------------------------------------------------
    @property
    def available(self) -> bool:
        return bool(self.key)

    @property
    def binary(self) -> None:
        return None

    # -- models -------------------------------------------------------------
    def models(self) -> list[tuple[str, str]]:
        """Ask the API which models this key can use.

        Falls back to the server default: a picker with one honest entry beats
        a hard-coded list of model names that may not exist for this key.
        """
        if self._models is not None:
            return self._models
        if not self.available:
            self._models = list(FALLBACK_MODELS)
            return self._models
        out: list[tuple[str, str]] = []
        try:
            url = f"{self.base}/v1beta/models?{urllib.parse.urlencode({'key': self.key})}"
            with urllib.request.urlopen(url, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8", "replace"))
            for model in data.get("models", []):
                if not isinstance(model, dict):
                    continue
                name = str(model.get("name") or "")
                methods = model.get("supportedGenerationMethods") or []
                if name and "generateContent" not in methods:
                    continue
                model_id = name.split("/")[-1] if name else ""
                if not model_id:
                    continue
                label = str(model.get("displayName") or model_id)
                out.append((model_id, label))
        except (OSError, ValueError, urllib.error.URLError):
            out = []
        self._models = out or list(FALLBACK_MODELS)
        return self._models

    def invalidate_models(self) -> None:
        self._models = None

    # -- running a turn -----------------------------------------------------
    def run(
        self,
        prompt: str,
        model: str = "",
        conversation_id: str = "",
        cwd: str = "",
        effort: str = "",
        mode: str = "",
        timeout: int = DEFAULT_TIMEOUT,
        extra_flags: tuple[str, ...] = (),
    ) -> Turn:
        turn = GeminiTurn(cwd=cwd)
        if not self.available:
            turn.emit_soon(
                "failed",
                f"no Gemini API key — set {API_KEY_ENV} to use this engine")
            return turn

        model_id = (model or os.environ.get(MODEL_ENV)
                    or self.models()[0][0] or "gemini-2.0-flash")
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "tools": [{"functionDeclarations": TOOL_SPECS}],
        }
        if effort and effort != "medium":
            payload["generationConfig"] = {"thinkingConfig": {"level": effort}}

        threading.Thread(
            target=self._pump, args=(turn, model_id, payload, timeout),
            daemon=True, name="gemini-turn").start()
        return turn

    # -- one request to the API --------------------------------------------
    def _post(self, turn: GeminiTurn, model_id: str, payload: dict,
              timeout: int) -> tuple[list[dict], str]:
        """Stream one response. Returns (function calls, finish reason)."""
        url = (f"{self.base}/v1beta/models/"
               f"{urllib.parse.quote(model_id)}:streamGenerateContent?"
               + urllib.parse.urlencode({"alt": "sse", "key": self.key}))
        request = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json"})
        calls: list[dict] = []
        reason = ""
        try:
            with urllib.request.urlopen(
                    request, timeout=timeout or REQUEST_TIMEOUT) as response:
                for raw in response:
                    if turn.cancelled:
                        break
                    line = raw.decode("utf-8", "replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk in ("", "[DONE]"):
                        continue
                    try:
                        record = json.loads(chunk)
                    except ValueError:
                        continue
                    reason = self._handle(turn, record) or reason
                    calls.extend(self._calls(record))
        except urllib.error.HTTPError as error:
            detail = ""
            try:
                body = error.read().decode("utf-8", "replace")
                detail = json.loads(body).get("error", {}).get("message", "")
            except (OSError, ValueError):
                detail = ""
            turn.error = detail or f"HTTP {error.code}"
            turn.status = "ERROR"
        except (OSError, urllib.error.URLError) as error:
            turn.error = f"cannot reach the Gemini API: {error}"
            turn.status = "ERROR"
        return calls, reason

    @staticmethod
    def _calls(record: dict) -> list[dict]:
        out: list[dict] = []
        finish = ""
        for candidate in record.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content") or {}
            for part in content.get("parts") or []:
                if isinstance(part, dict) and isinstance(
                        part.get("functionCall"), dict):
                    out.append(part["functionCall"])
        return out

    # -- tools --------------------------------------------------------------
    def _resolve(self, turn: GeminiTurn, raw: str) -> Path:
        """Resolve a path and refuse anything outside the workspace."""
        candidate = Path(str(raw or "")).expanduser()
        if not candidate.is_absolute():
            candidate = Path(turn.cwd) / candidate
        resolved = candidate.resolve()
        root = Path(turn.cwd).resolve()
        if resolved != root and root not in resolved.parents:
            raise PermissionError(
                f"{raw} is outside the workspace ({turn.cwd})")
        return resolved

    def _run_tool(self, turn: GeminiTurn, call: dict) -> dict:
        """Execute one function call, returning what the model sees."""
        name = str(call.get("name") or "")
        args = call.get("args") or {}
        try:
            if name == "read_file":
                path = self._resolve(turn, args.get("path", ""))
                text = path.read_text(errors="replace")
                return {"path": str(path),
                        "content": text[:MAX_TOOL_BYTES]}
            if name == "write_file":
                path = self._resolve(turn, args.get("path", ""))
                content = str(args.get("content") or "")
                if not turn._approved("write_file", "Write a file?",  # noqa: SLF001
                                      str(path)):
                    return {"error": "the user denied this write"}
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
                return {"path": str(path), "bytes": len(content)}
            if name == "run_command":
                command = str(args.get("command") or "")
                if not turn._approved("run_command", "Run a command?",  # noqa: SLF001
                                      command):
                    return {"error": "the user denied this command"}
                completed = subprocess.run(
                    ["bash", "-lc", command], cwd=turn.cwd,
                    capture_output=True, text=True, timeout=COMMAND_TIMEOUT)
                output = (completed.stdout or "") + (completed.stderr or "")
                return {"exit": completed.returncode,
                        "output": output[-MAX_COMMAND_BYTES:]}
            return {"error": f"unknown tool {name!r}"}
        except subprocess.TimeoutExpired:
            return {"error": f"the command took longer than {COMMAND_TIMEOUT}s"}
        except (OSError, PermissionError, ValueError) as error:
            return {"error": str(error)}

    # -- the reader ---------------------------------------------------------
    def _pump(self, turn: GeminiTurn, model_id: str, payload: dict,
              timeout: int) -> None:
        contents = payload["contents"]
        for _step in range(MAX_STEPS):
            if turn.cancelled:
                break
            payload["contents"] = contents
            calls, reason = self._post(turn, model_id, payload, timeout)
            if turn.status == "ERROR" or turn.cancelled:
                break
            if not calls:
                break
            # the model asked for tools: answer them, then continue the turn
            contents.append({"role": "model",
                             "parts": [{"functionCall": call}
                                       for call in calls]})
            responses = []
            for call in calls:
                result = self._run_tool(turn, call)
                responses.append({"functionResponse": {
                    "name": str(call.get("name") or ""),
                    "response": {"result": result}}})
            contents.append({"role": "user", "parts": responses})
            if reason == "MAX_TOKENS":
                break
        else:
            turn.error = (turn.error or
                          f"stopped after {MAX_STEPS} tool rounds")

        turn.duration = time.monotonic() - turn._started_at  # noqa: SLF001
        if turn.cancelled:
            turn.emit_soon("failed", "cancelled")
            return
        if turn.status:
            turn.emit_soon("finished", turn.result())
            return
        turn.status = "SUCCESS"
        turn.emit_soon("finished", turn.result())

    def _handle(self, turn: GeminiTurn, record: dict) -> str:
        usage = record.get("usageMetadata")
        if isinstance(usage, dict):
            total = usage.get("totalTokenCount") or (
                int(usage.get("promptTokenCount") or 0)
                + int(usage.get("candidatesTokenCount") or 0))
            turn.usage = {
                "input_tokens": int(usage.get("promptTokenCount") or 0),
                "output_tokens": int(usage.get("candidatesTokenCount") or 0),
                "total_tokens": int(total or 0),
            }

        finish = ""
        for candidate in record.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content") or {}
            for part in content.get("parts") or []:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text:
                    turn.text += text
                    turn.emit_soon("delta", text)
            reason = candidate.get("finishReason")
            if reason and reason not in ("STOP", "MAX_TOKENS", ""):
                turn.error = f"the model stopped: {reason}"
                turn.status = "ERROR"
            if reason:
                finish = str(reason)

        prompt_feedback = record.get("promptFeedback") or {}
        blocked = prompt_feedback.get("blockReason")
        if blocked:
            turn.error = f"the request was blocked: {blocked}"
            turn.status = "ERROR"
        return finish
