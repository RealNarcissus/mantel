"""The legacy vendor engine adapter (Antigravity-lineage `agy`).

This is the bridge this project started with: it spawns the bundled CLI and
parses its JSON stream. It is kept, unchanged in behaviour, so the rest of the
app can be migrated to the adapter interface first and to another engine
second. See docs/plan/pi-engine.md.


The desktop app's own engine ships as a native Linux binary and already speaks
a GUI-shaped protocol, so the port drives it instead of reimplementing model
access:

    agy --print <prompt> --output-format stream-json [--model M]
        [--conversation <id>] [--effort E] [--mode M]

which emits one JSON object per line:

    {"event":"init",        "conversation_id":…, "init":{"tools":[…], …}}
    {"event":"step_update", "step_update":{"step_type":"agent_response",
                                           "text_delta":"…", "state":"ACTIVE"}}
    {"event":"result",      "result":{"status":"SUCCESS","response":…}}

`run()` returns a Turn whose signals are emitted on the GTK main thread, so
the UI can bind straight to them. Work happens on a worker thread; Gio's own
async plumbing would work too, but a thread keeps cancellation simple.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from app.engines.base import DEFAULT_TIMEOUT, EngineAdapter, Turn  # noqa: E402


def _is_linux_executable(path: str) -> bool:
    """True only for a native Linux ELF.

    The macOS bundle also contains an `agy`, but it is an arm64 Mach-O and
    cannot be executed here — falling through to it would fail in a confusing
    way, so it is rejected up front.
    """
    try:
        with open(path, "rb") as fh:
            return fh.read(4) == b"\x7fELF"
    except OSError:
        return False


def find_binary() -> str | None:
    """Locate a runnable engine: PATH first, then the app bundle from the DMG."""
    override = (os.environ.get("MANTEL_ENGINE")
                or os.environ.get("GEMINI_ENGINE"))
    if override and _is_linux_executable(override):
        return override
    found = shutil.which("agy")
    if found and _is_linux_executable(found):
        return found
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in (
        "../Gemini 1.128.14.1166/Gemini.app/Contents/Helpers/agy",
        "../../Gemini 1.128.14.1166/Gemini.app/Contents/Helpers/agy",
    ):
        cand = os.path.normpath(os.path.join(here, rel))
        if os.path.isfile(cand) and os.access(cand, os.X_OK) and _is_linux_executable(cand):
            return cand
    return None


class AgyAdapter(EngineAdapter):
    """Drives `agy --print --output-format stream-json`."""

    name = "legacy-agy"
    capabilities = frozenset({"tools", "permissions", "remote", "images"})

    def __init__(self, binary: str | None = None) -> None:
        self.binary = binary or find_binary()
        self._models: list[tuple[str, str]] | None = None

    @property
    def available(self) -> bool:
        return bool(self.binary and os.path.isfile(self.binary))

    # -- model catalogue ----------------------------------------------------
    def models(self) -> list[tuple[str, str]]:
        """[(id, label)] from `agy models`; falls back to a small default."""
        if self._models is not None:
            return self._models
        out: list[tuple[str, str]] = []
        if self.available:
            try:
                res = subprocess.run(
                    [self.binary, "models"], capture_output=True, text=True, timeout=60
                )
                for line in res.stdout.splitlines():
                    if "\t" in line:
                        mid, label = line.split("\t", 1)
                        if mid.strip():
                            out.append((mid.strip(), label.strip()))
            except (OSError, subprocess.SubprocessError):
                pass
        if not out:
            out = [("gemini-3.8-flash-high", "Gemini 3.8 Flash (High)")]
        self._models = out
        return out

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
        turn = Turn(self.name)
        if not self.available:
            GLib.idle_add(turn.emit, "failed",
                          "agent engine not found — install the `agy` engine or point "
                          "MANTEL_ENGINE at it")
            return turn

        argv = [self.binary, "--print", prompt, "--output-format", "stream-json"]
        if model:
            argv += ["--model", model]
        if conversation_id:
            argv += ["--conversation", conversation_id]
        if effort:
            argv += ["--effort", effort]
        if mode:
            argv += ["--mode", mode]
        if timeout:
            argv += ["--print-timeout", f"{timeout}s"]
        argv += list(extra_flags)

        env = dict(os.environ)
        env.setdefault("GIT_TERMINAL_PROMPT", "0")

        def worker() -> None:
            try:
                turn._proc = subprocess.Popen(  # noqa: SLF001
                    argv,
                    cwd=cwd or None,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                    env=env,
                    start_new_session=True,
                )
            except OSError as exc:
                GLib.idle_add(turn.emit, "failed", f"cannot start engine: {exc}")
                return

            proc = turn._proc  # noqa: SLF001
            assert proc.stdout is not None
            try:
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    self._dispatch(turn, event)
            except (OSError, ValueError):
                pass
            finally:
                code = proc.wait()
            if turn.cancelled:
                GLib.idle_add(turn.emit, "failed", "cancelled")
            elif turn.status or code == 0:
                GLib.idle_add(turn.emit, "finished", {
                    "status": turn.status or "SUCCESS",
                    "text": turn.text,
                    "conversation_id": turn.conversation_id,
                    "usage": turn.usage,
                    "duration": turn.duration,
                    "error": turn.error,
                    "denied": turn.denied,
                })
            else:
                GLib.idle_add(turn.emit, "failed", f"engine exited with code {code}")

        threading.Thread(target=worker, daemon=True, name="gemini-turn").start()
        return turn

    # -- event decoding -----------------------------------------------------
    @staticmethod
    def _dispatch(turn: Turn, event: dict) -> None:
        kind = event.get("event")
        if kind == "init":
            data = event.get("init", {}) or {}
            turn.conversation_id = event.get("conversation_id", "")
            turn.tools = list(data.get("tools", []) or [])
            turn.permission_mode = data.get("permission_mode", "")
            if turn.conversation_id:
                GLib.idle_add(turn.emit, "started", turn.conversation_id)
        elif kind == "step_update":
            step = event.get("step_update", {}) or {}
            delta = step.get("text_delta") or ""
            stype = (step.get("step_type") or "").lower()
            if delta:
                if "think" in stype or "reason" in stype or "thought" in stype:
                    turn.thinking += delta
                    GLib.idle_add(turn.emit, "thought", delta)
                else:
                    turn.text += delta
                    GLib.idle_add(turn.emit, "delta", delta)
            name = step.get("tool_name") or step.get("name") or ""
            if name and ("tool" in stype or step.get("tool_call")
                         or step.get("tool_info")):
                info = step.get("tool_info") or {}
                payload = {
                    "parameters": info.get("parameters") or {},
                    "state": step.get("state", ""),
                    "output": str(info.get("output") or "")[:400],
                    "error": str(info.get("error") or "")[:400],
                    "duration": step.get("duration_seconds") or 0,
                }
                GLib.idle_add(turn.emit, "tool", name, json.dumps(payload))
        elif kind == "result":
            data = event.get("result", {}) or {}
            turn.status = data.get("status", "")
            turn.error = data.get("error", "") or ""
            turn.usage = data.get("usage", {}) or {}
            turn.duration = float(data.get("duration_seconds") or 0.0)
            turn.denied = list(data.get("denied_actions") or [])
            if not turn.text and data.get("response"):
                turn.text = data["response"]
