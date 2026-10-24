"""The engine-neutral contract: a Turn and the adapter interface.

Everything the UI needs from an engine fits in this module. Keeping it small is
the point: if a feature cannot be expressed here, it does not belong in the
shell.
"""
from __future__ import annotations

import os
import signal
from typing import Protocol, runtime_checkable

import gi

gi.require_version("GLib", "2.0")
from gi.repository import GLib, GObject  # noqa: E402

#: 0 = wait for the turn to finish, whatever the engine's own default is.
DEFAULT_TIMEOUT = 0

#: Capabilities an adapter may declare. The UI gates vendor-specific surfaces on
#: these instead of assuming every engine has them.
CHAT = "chat"                 # can hold a conversation at all
TOOLS = "tools"               # can call tools (an agent, not just a model)
APPROVALS = "approvals"       # the engine can ask before acting
SESSIONS = "sessions"         # conversations can be resumed by id
STEERING = "steering"         # a message can join a turn that is already running
COMPACTION = "compaction"     # long conversations can be summarised
IMAGES = "images"
REMOTE = "remote"             # a remote-control daemon exists
ACCOUNT = "account"           # the engine has a vendor account to sign in to
CONNECTORS = "connectors"     # the engine owns an MCP/connector store
SKILLS = "skills"             # the engine owns a skills store
PERMISSION_FILE = "permission_file"   # grants live in the engine's own config
CLI_FLAGS = "cli_flags"               # approval modes are CLI flags


class Turn(GObject.Object):
    """One request/response exchange, streamed.

    Signals (all emitted on the GTK main thread):

        started(str)          the engine's conversation id, when it has one
        delta(str)            response text
        thought(str)          reasoning text
        tool(str, str)        tool name and a JSON payload
                              {"parameters", "state", "output", "error", "duration"}
        dialog(dict)          the engine is blocked waiting for an answer:
                              {"id", "method", "title", "message", "options",
                               "timeout_ms"} — answer with `answer_dialog()`
        finished(dict)        {"status", "text", "conversation_id", "usage",
                              "duration", "error", "denied"}
        failed(str)           a human-readable reason

    Adapters must emit exactly one of `finished` or `failed`.
    """

    __gsignals__ = {
        "started": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "delta": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "thought": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "tool": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
        "dialog": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "finished": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "failed": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self, engine: str = ""):
        super().__init__()
        self.engine = engine
        self.conversation_id = ""
        self.tools: list[str] = []
        self.permission_mode = ""
        self.text = ""
        self.thinking = ""
        self.usage: dict = {}
        self.status = ""
        self.error = ""
        self.duration = 0.0
        self.denied: list[dict] = []
        self._proc = None
        self._cancelled = False

    # -- cancellation -------------------------------------------------------
    def cancel(self) -> None:
        """Stop the turn. Safe to call more than once."""
        self._cancelled = True
        self._stop_process()

    def _stop_process(self) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.terminate()
            except OSError:
                pass

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def history(self, conversation_id: str) -> list[dict]:
        """[{"role": "user"|"assistant", "text": …}] for a stored session.

        Engines that cannot enumerate a session inherit this and return an
        empty list; the UI then relies on its own store.
        """
        return []

    def steer(self, text: str) -> bool:
        """Add a message to a turn that is already running.

        Engines without steering inherit this and return False, so the UI can
        offer the affordance only where it works.
        """
        return False

    # -- answering the engine ---------------------------------------------
    def answer_dialog(self, request_id: str, *, value: str | None = None,
                      confirmed: bool | None = None,
                      cancelled: bool = False) -> bool:
        """Answer a `dialog` request. Returns True when the engine accepted it.

        Engines that cannot ask mid-turn simply inherit this and return False.
        """
        return False

    # -- helpers for adapters ----------------------------------------------
    def emit_soon(self, signal: str, *args) -> None:
        """Emit from a worker thread, on the main loop."""
        GLib.idle_add(self.emit, signal, *args)

    def result(self) -> dict:
        """The dict handed to `finished`."""
        return {
            "status": self.status or "SUCCESS",
            "text": self.text,
            "conversation_id": self.conversation_id,
            "usage": self.usage,
            "duration": self.duration,
            "error": self.error,
            "denied": self.denied,
        }


@runtime_checkable
class EngineAdapter(Protocol):
    """What the shell requires of an engine."""

    name: str
    capabilities: frozenset[str]

    @property
    def available(self) -> bool:
        """Is the engine installed and usable right now?"""

    def models(self) -> list[tuple[str, str]]:
        """[(id, label)] for the model picker."""

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
        """Start one turn; the returned Turn streams it."""
