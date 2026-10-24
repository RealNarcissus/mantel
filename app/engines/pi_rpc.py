"""Pi engine adapter: drives `pi --mode rpc`.

Pi speaks JSONL on stdin/stdout: commands in, responses plus session events out,
and — the reason it matters for this app — *extension UI requests* that block
until the client answers. That last part is what makes real pre-execution
approvals possible (`docs/plan/pi-engine.md`, M2); for now dialogs are answered
with a refusal so a stray extension can never hang a turn.

Wire facts this module depends on (Pi 1.0, `docs/rpc.md` and `docs/json.md`):

    stdin   {"id": "1", "type": "prompt", "message": "…"}
    stdout  {"type": "response", "command": "prompt", "success": true,
             "data": {"disposition": "started"}}
            {"type": "message_update",
             "assistantMessageEvent": {"type": "text_delta", "delta": "…"},
             "usage": {"totalTokens": 12}}
            {"type": "tool_execution_start", "toolName": "bash", "args": {…}}
            {"type": "tool_execution_end", "toolName": "bash", "result": {…},
             "isError": false, "durationMs": 42}
            {"type": "agent_settled", "aborted": false}

    stdout  {"type": "extension_ui_request", "id": "…", "method": "select", …}
    stdin   {"type": "extension_ui_response", "id": "…", "cancelled": true}

Records are separated by LF only; a turn ends when `agent_settled` arrives,
not when the prompt is accepted.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from app.engines.base import (  # noqa: E402
    APPROVALS, COMPACTION, DEFAULT_TIMEOUT, IMAGES, SESSIONS, STEERING, TOOLS,
    EngineAdapter, Turn,
)

#: Set this to point at a specific `pi` binary (tests use a fake one).
BINARY_ENV = "MANTEL_PI_BIN"

#: Dialog methods that block the engine until the client answers.
_DIALOG_METHODS = frozenset({"select", "confirm", "input", "editor"})

#: How long an abort may take before the process is killed.
_ABORT_GRACE_MS = 4000

#: Default window for a dialog when the extension did not set one. Without it a
#: client that never answers would wedge the engine forever.
_DEFAULT_DIALOG_MS = 600_000

#: The approval gate shipped with the client.
APPROVALS_EXTENSION = (Path(__file__).resolve().parents[2]
                       / "pi-extensions" / "approvals.ts")


def find_binary() -> str | None:
    """The `pi` executable, if there is one."""
    override = os.environ.get(BINARY_ENV)
    if override and os.path.isfile(override) and os.access(override, os.X_OK):
        return override
    return shutil.which("pi")


def _text_of(result: object) -> str:
    """Flatten a Pi tool result ({"content": [{"text": …}]}) to text."""
    if isinstance(result, str):
        return result
    if not isinstance(result, dict):
        return ""
    content = result.get("content")
    if isinstance(content, list):
        parts = [block.get("text", "") for block in content
                 if isinstance(block, dict)]
        return "".join(part for part in parts if part)
    return str(result.get("text") or "")


def _usage(raw, turn: Turn) -> None:
    """Normalise Pi's usage into the shape the transcript footer reads."""
    if not isinstance(raw, dict):
        return
    total = raw.get("totalTokens") or raw.get("total_tokens")
    turn.usage = {
        "input_tokens": raw.get("input", raw.get("input_tokens", 0)),
        "output_tokens": raw.get("output", raw.get("output_tokens", 0)),
        "cache_read_tokens": raw.get("cacheRead", 0),
        "total_tokens": total or 0,
        "cost": raw.get("cost", {}),
    }


class PiTurn(Turn):
    """A turn against a live `pi --mode rpc` process."""

    def __init__(self) -> None:
        super().__init__("pi")
        self._stdin = None
        self._settled = False
        self._aborted = False
        self._prompt_id = ""
        self._started_at = time.monotonic()

    # -- cancellation -------------------------------------------------------
    def cancel(self) -> None:
        """Ask Pi to abort, then make sure the process actually goes away."""
        self._cancelled = True
        self._send({"type": "abort"})
        GLib.timeout_add(_ABORT_GRACE_MS, self._force_stop)

    def _force_stop(self) -> bool:
        self._stop_process()
        return False

    # -- answering a blocked engine ----------------------------------------
    def answer_dialog(self, request_id: str, *, value: str | None = None,
                      confirmed: bool | None = None,
                      cancelled: bool = False) -> bool:
        request = getattr(self, "_pending_dialog", None)
        if not request or request.get("id") != request_id:
            return False
        self._pending_dialog = None
        reply: dict = {"type": "extension_ui_response", "id": request_id}
        if cancelled:
            reply["cancelled"] = True
        elif confirmed is not None:
            reply["confirmed"] = bool(confirmed)
        else:
            reply["value"] = "" if value is None else str(value)
        self._send(reply)
        return True

    # -- writing to the engine ---------------------------------------------
    def _send(self, payload: dict) -> None:
        stream = self._stdin
        if stream is None or stream.closed:
            return
        try:
            stream.write(json.dumps(payload) + "\n")
            stream.flush()
        except (OSError, ValueError):
            pass


class PiAdapter(EngineAdapter):
    """Drives the `pi` coding agent over its RPC protocol."""

    name = "pi"
    capabilities = frozenset({TOOLS, APPROVALS, SESSIONS, STEERING,
                              COMPACTION, IMAGES})

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or find_binary()
        self._models: list[tuple[str, str]] | None = None
        self._model_lock = threading.Lock()
        self._next_id = 0

    # -- availability -------------------------------------------------------
    @property
    def available(self) -> bool:
        return bool(self.binary and os.path.isfile(self.binary))

    def _id(self) -> str:
        self._next_id += 1
        return f"mantel-{self._next_id}"

    # -- models -------------------------------------------------------------
    def models(self) -> list[tuple[str, str]]:
        """[(provider/id, name)] from `get_available_models`.

        Asked over a throwaway RPC process rather than parsed from CLI output,
        so it reflects the models the user's credentials actually unlock.
        """
        with self._model_lock:
            if self._models is not None:
                return self._models
            out: list[tuple[str, str]] = []
            for entry in self._one_shot("get_available_models").get("models", []):
                if not isinstance(entry, dict):
                    continue
                model_id = str(entry.get("id") or "")
                if not model_id:
                    continue
                provider = str(entry.get("provider") or "")
                label = str(entry.get("name") or model_id)
                if provider:
                    label = f"{label} · {provider}"
                out.append((f"{provider}/{model_id}" if provider else model_id,
                            label))
            if not out:
                # no providers configured yet: keep the picker usable
                out = [("", "Pi default")]
            self._models = out
            return out

    def invalidate_models(self) -> None:
        with self._model_lock:
            self._models = None

    def _one_shot(self, command: str, timeout: int = 60) -> dict:
        """Send one command to a fresh RPC process and read its response."""
        if not self.available:
            return {}
        request_id = self._id()
        argv = [self.binary, "--mode", "rpc", "--no-session"]
        try:
            proc = subprocess.Popen(argv, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True,
                                    bufsize=1, start_new_session=True)
        except OSError:
            return {}
        try:
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(json.dumps({"id": request_id, "type": command})
                             + "\n")
            proc.stdin.flush()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                line = proc.stdout.readline()
                if not line:
                    break
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if (record.get("type") == "response"
                        and record.get("id") == request_id):
                    if record.get("success"):
                        data = record.get("data")
                        return data if isinstance(data, dict) else {}
                    return {}
        except (OSError, ValueError):
            return {}
        finally:
            try:
                proc.kill()
            except OSError:
                pass
        return {}

    # -- running a turn -----------------------------------------------------
    def _mode_flags(self, mode: str) -> list[str]:
        """Our three modes onto Pi's tool selection.

        Chat is a conversation, so it must not be able to write or run
        anything. Task and Research get the default tool set.
        """
        if mode == "chat":
            return ["--tools", "read,grep,find,ls"]
        return []

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
        turn = PiTurn()
        if not self.available:
            turn.emit_soon("failed",
                           "Pi was not found — install it or point "
                           f"{BINARY_ENV} at the binary")
            return turn

        argv = [self.binary, "--mode", "rpc"]
        if conversation_id:
            argv += ["--session-id", conversation_id]
        else:
            argv += ["--no-session"]
        if model:
            argv += ["--model", model]
        if effort:
            argv += ["--thinking", effort]
        argv += self._mode_flags(mode)
        argv += self._extension_flags()
        argv += list(extra_flags)

        env = dict(os.environ)
        env.setdefault("GIT_TERMINAL_PROMPT", "0")

        threading.Thread(
            target=self._pump,
            args=(turn, argv, prompt, cwd, env, timeout),
            daemon=True,
            name="pi-turn",
        ).start()
        return turn

    # -- the reader ---------------------------------------------------------
    def _pump(self, turn: PiTurn, argv: list[str], prompt: str, cwd: str,
              env: dict, timeout: int) -> None:
        try:
            proc = subprocess.Popen(
                argv, cwd=cwd or None, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                bufsize=1, env=env, start_new_session=True)
        except OSError as exc:
            turn.emit_soon("failed", f"cannot start Pi: {exc}")
            return

        turn._proc = proc
        turn._stdin = proc.stdin
        if timeout:
            threading.Timer(timeout, turn.cancel).start()

        # Subscribe before prompting: a fast turn can settle before a late
        # client would be listening.
        turn._prompt_id = self._id()
        turn._send({"id": f"{turn._prompt_id}-state", "type": "get_state"})
        turn._send({"id": turn._prompt_id, "type": "prompt", "message": prompt})

        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if self._handle(turn, record):
                    break
        except (OSError, ValueError):
            pass
        finally:
            # RPC is long-lived: once the turn is over, ask it to stop (closing
            # stdin is Pi's orderly shutdown) and make sure it does.
            try:
                if proc.stdin is not None and not proc.stdin.closed:
                    proc.stdin.close()
            except OSError:
                pass
            try:
                code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                turn._stop_process()
                try:
                    code = proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    code = -1

        if turn._settled:
            turn.emit_soon("finished", turn.result())
            return
        if turn.cancelled:
            turn.emit_soon("failed", "cancelled")
            return
        detail = ""
        if proc.stderr is not None:
            try:
                detail = proc.stderr.read().strip().splitlines()[-1][:200]
            except (OSError, IndexError):
                detail = ""
        turn.emit_soon("failed",
                       f"Pi exited (code {code}){': ' + detail if detail else ''}")

    # -- event decoding -----------------------------------------------------
    def _handle(self, turn: PiTurn, record: dict) -> bool:
        """Apply one record. Returns True when the turn is over."""
        kind = record.get("type")

        if kind == "response":
            return self._handle_response(turn, record)

        if kind == "message_update":
            _usage(record.get("usage"), turn)
            event = record.get("assistantMessageEvent") or {}
            etype = event.get("type")
            if etype == "text_delta":
                delta = str(event.get("delta") or "")
                if delta:
                    turn.text += delta
                    turn.emit_soon("delta", delta)
            elif etype == "thinking_delta":
                delta = str(event.get("delta") or "")
                if delta:
                    turn.thinking += delta
                    turn.emit_soon("thought", delta)
            elif etype == "error":
                turn.error = str(event.get("error") or "provider error")
            return False

        if kind == "tool_execution_start":
            turn.emit_soon("tool", str(record.get("toolName") or ""),
                           json.dumps({
                               "parameters": record.get("args") or {},
                               "state": "ACTIVE",
                           }))
            return False

        if kind == "tool_execution_end":
            is_error = bool(record.get("isError"))
            turn.emit_soon("tool", str(record.get("toolName") or ""),
                           json.dumps({
                               "parameters": record.get("args") or {},
                               "state": "ERROR" if is_error else "DONE",
                               "output": _text_of(record.get("result"))[:400],
                               "error": _text_of(record.get("result"))[:400]
                                       if is_error else "",
                               "duration": (record.get("durationMs") or 0) / 1000,
                           }))
            return False

        if kind == "extension_ui_request":
            self._ask_client(turn, record)
            return False

        if kind == "compaction_start":
            turn.emit_soon("tool", "compact", json.dumps({
                "parameters": {"reason": record.get("reason", "")},
                "state": "ACTIVE",
            }))
            return False

        if kind == "compaction_end":
            turn.emit_soon("tool", "compact", json.dumps({
                "parameters": {"reason": record.get("reason", "")},
                "state": "ERROR" if record.get("errorMessage") else "DONE",
                "error": record.get("errorMessage") or "",
            }))
            return False

        if kind == "auto_retry_end" and record.get("success") is False:
            turn.error = str(record.get("finalError") or "retries exhausted")
            turn.status = "ERROR"
            return False

        if kind == "agent_settled":
            turn._settled = True
            turn._aborted = bool(record.get("aborted"))
            turn.duration = time.monotonic() - turn._started_at
            if turn._aborted or turn.cancelled:
                turn.status = "ABORTED"
            elif turn.error:
                turn.status = "ERROR"
            else:
                turn.status = "SUCCESS"
            return True

        return False

    def _handle_response(self, turn: PiTurn, record: dict) -> bool:
        """Apply a command response. Returns True when the turn is over."""
        command = record.get("command")
        data = record.get("data") if isinstance(record.get("data"), dict) else {}
        if command == "prompt" and not record.get("success"):
            turn.error = str(record.get("error") or "Pi rejected the prompt")
            turn.status = "ERROR"
            turn._settled = True
            return True
        if command == "get_state":
            session_id = str(data.get("sessionId") or "")
            if session_id:
                turn.conversation_id = session_id
                turn.emit_soon("started", session_id)
        return False

    def _extension_flags(self) -> list[str]:
        """Load the approval gate when the client is running from a checkout.

        The gate is what turns Pi's `tool_call` hook into Mantel's approval
        ladder. Without it, Pi runs with its own defaults; the UI says so.
        """
        if os.environ.get("MANTEL_NO_APPROVALS_EXT"):
            return []
        path = Path(os.environ.get("MANTEL_APPROVALS_EXT") or APPROVALS_EXTENSION)
        if path.is_file():
            return ["--extension", str(path)]
        return []

    def _ask_client(self, turn: PiTurn, record: dict) -> None:
        """Forward a blocking engine question to the UI.

        The engine is waiting on stdin, so every path must end in an answer:
        the card answers it, or the fallback timer declines on the user's
        behalf. Editors and free-text dialogs are not used by the shipped gate,
        but they are forwarded too rather than silently ignored.
        """
        method = str(record.get("method") or "")
        request_id = record.get("id")
        if method not in _DIALOG_METHODS or not request_id:
            return

        options = record.get("options")
        timeout = int(record.get("timeout") or _DEFAULT_DIALOG_MS)
        request = {
            "id": request_id,
            "method": method,
            "title": str(record.get("title") or ""),
            "message": str(record.get("message") or ""),
            "options": [str(o) for o in options] if isinstance(options, list)
                       else [],
            "timeout_ms": timeout,
        }
        turn._pending_dialog = request
        turn.emit_soon("dialog", request)

        def decline_if_unanswered() -> bool:
            if getattr(turn, "_pending_dialog", None) is request:
                turn.answer_dialog(request_id, cancelled=True)
            return False

        GLib.timeout_add(timeout, decline_if_unanswered)
