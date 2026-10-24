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
import time
import urllib.error
import urllib.parse
import urllib.request

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from app.engines.base import (  # noqa: E402
    CHAT, DEFAULT_TIMEOUT, EngineAdapter, Turn,
)

#: Where the key comes from. `GEMINI_API_KEY` is the name the docs use.
API_KEY_ENV = "GEMINI_API_KEY"
BASE_ENV = "MANTEL_GEMINI_BASE"
MODEL_ENV = "MANTEL_GEMINI_MODEL"

DEFAULT_BASE = "https://generativelanguage.googleapis.com"

#: Used when the model catalogue cannot be listed (offline, or no network yet).
FALLBACK_MODELS = [("", "Gemini (server default)")]

REQUEST_TIMEOUT = 120


def find_key() -> str:
    return (os.environ.get(API_KEY_ENV)
            or os.environ.get("MANTEL_GEMINI_KEY") or "").strip()


class GeminiTurn(Turn):
    """A turn against the REST streaming endpoint."""

    def __init__(self, request: urllib.request.Request | None = None) -> None:
        super().__init__("gemini")
        self._request = request
        self._started_at = time.monotonic()

    def cancel(self) -> None:
        # urllib has no cancel; the read loop checks `cancelled` between events
        self._cancelled = True


class GeminiAdapter(EngineAdapter):
    """Streams from the Gemini API. Chat only — no tool loop yet."""

    name = "gemini"
    capabilities = frozenset({CHAT})

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
        turn = GeminiTurn()
        if not self.available:
            turn.emit_soon(
                "failed",
                f"no Gemini API key — set {API_KEY_ENV} to use this engine")
            return turn

        model_id = (model or os.environ.get(MODEL_ENV)
                    or self.models()[0][0] or "gemini-2.0-flash")
        url = (f"{self.base}/v1beta/models/"
               f"{urllib.parse.quote(model_id)}:streamGenerateContent?"
               + urllib.parse.urlencode({"alt": "sse", "key": self.key}))
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        }
        if effort and effort != "medium":
            payload["generationConfig"] = {"thinkingConfig": {"level": effort}}
        request = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json"})

        import threading  # noqa: PLC0415

        threading.Thread(target=self._pump, args=(turn, request, timeout),
                         daemon=True, name="gemini-turn").start()
        return turn

    # -- the reader ---------------------------------------------------------
    def _pump(self, turn: GeminiTurn, request, timeout: int) -> None:
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
                    self._handle(turn, record)
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

        turn.duration = time.monotonic() - turn._started_at  # noqa: SLF001
        if turn.cancelled:
            turn.emit_soon("failed", "cancelled")
            return
        if turn.status:
            turn.emit_soon("finished", turn.result())
            return
        turn.status = "SUCCESS"
        turn.emit_soon("finished", turn.result())

    def _handle(self, turn: GeminiTurn, record: dict) -> None:
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

        prompt_feedback = record.get("promptFeedback") or {}
        blocked = prompt_feedback.get("blockReason")
        if blocked:
            turn.error = f"the request was blocked: {blocked}"
            turn.status = "ERROR"
