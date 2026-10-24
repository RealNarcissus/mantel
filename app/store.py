"""Conversation store.

Conversations are owned by the app rather than by the engine, so the sidebar,
titles, search and deletion work regardless of what the engine persists. Each
conversation keeps the engine-side id too, so a turn can be continued with
the engine's own session store when it has one.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


def data_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    for cand in (base / "gemini-desktop", Path(__file__).resolve().parent.parent / ".data"):
        try:
            (cand / "conversations").mkdir(parents=True, exist_ok=True)
            probe = cand / ".write-probe"
            probe.write_text("")
            probe.unlink()
            return cand
        except OSError:
            continue
    raise RuntimeError("no writable data directory")


@dataclass
class Message:
    role: str                    # "user" | "assistant"
    text: str
    ts: float = field(default_factory=time.time)
    model: str = ""
    thinking: str = ""
    error: str = ""
    tools: list[str] = field(default_factory=list)
    duration: float = 0.0
    usage: dict = field(default_factory=dict)


@dataclass
class Conversation:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = "New chat"
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    engine_id: str = ""          # the engine's conversation id, for resume
    context_lost: bool = False   # the engine could not resume; resend history
    pending_prompt: str = ""     # a turn that was running when the app stopped
    pending_since: float = 0.0
    interrupted: bool = False    # that turn never finished; offer a retry
    cwd: str = ""
    model: str = ""
    messages: list[Message] = field(default_factory=list)

    def begin_turn(self, prompt: str) -> None:
        """Remember what is about to run, so a crash can offer a retry."""
        self.pending_prompt = prompt
        self.pending_since = time.time()
        self.interrupted = False
        self._dirty = True

    def end_turn(self) -> None:
        self.pending_prompt = ""
        self.pending_since = 0.0
        self.interrupted = False
        self._dirty = True

    def recover(self) -> bool:
        """Called on load: a pending turn means the app died mid-turn."""
        if self.pending_prompt:
            self.interrupted = True
            self.pending_prompt = ""
            self._dirty = True
            return True
        return False

    def add(self, role: str, text: str = "", **kw) -> Message:
        msg = Message(role=role, text=text, **kw)
        self.messages.append(msg)
        self._dirty = True
        self.updated = time.time()
        if role == "user" and self.title == "New chat":
            self.title = _title_from(text)
        return msg


def _title_from(text: str, limit: int = 48) -> str:
    line = " ".join(text.strip().split())
    if not line:
        return "New chat"
    return line[:limit] + ("…" if len(line) > limit else "")


class Store:
    def __init__(self, root: Path | None = None):
        self.root = (root or data_dir()) / "conversations"
        self.root.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Conversation] = {}

    def path(self, cid: str) -> Path:
        return self.root / f"{cid}.json"

    def load(self, cid: str) -> Conversation | None:
        if cid in self._cache:
            return self._cache[cid]
        p = self.path(cid)
        if not p.is_file():
            return None
        try:
            raw = json.loads(p.read_text())
        except (OSError, ValueError):
            return None
        conv = Conversation(
            id=raw.get("id", cid),
            title=raw.get("title", "New chat"),
            created=raw.get("created", 0.0),
            updated=raw.get("updated", 0.0),
            engine_id=raw.get("engine_id", ""),
            context_lost=bool(raw.get("context_lost", False)),
            pending_prompt=str(raw.get("pending_prompt") or ""),
            pending_since=float(raw.get("pending_since") or 0.0),
            interrupted=bool(raw.get("interrupted", False)),
            cwd=raw.get("cwd", ""),
            model=raw.get("model", ""),
        )
        conv.messages = [Message(**m) for m in raw.get("messages", [])
                         if isinstance(m, dict) and "role" in m]
        self._cache[cid] = conv
        return conv

    def save(self, conv: Conversation) -> None:
        conv.updated = time.time()
        self._cache[conv.id] = conv
        payload = asdict(conv)
        tmp = self.path(conv.id).with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=1))
        tmp.replace(self.path(conv.id))

    def list(self) -> list[Conversation]:
        out: list[Conversation] = []
        for f in self.root.glob("*.json"):
            conv = self.load(f.stem)
            if conv is not None:
                out.append(conv)
        out.sort(key=lambda c: c.updated, reverse=True)
        return out

    def delete(self, cid: str) -> None:
        self._cache.pop(cid, None)
        try:
            self.path(cid).unlink()
        except OSError:
            pass

    def new(self, cwd: str = "", model: str = "") -> Conversation:
        """A new conversation.

        It is *not* written to disk until it has a message, so an abandoned
        chat never shows up in the history.
        """
        conv = Conversation(cwd=cwd, model=model)
        self._cache[conv.id] = conv
        return conv
