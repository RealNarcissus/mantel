"""The engine facade.

Everything above this module talks to `Engine` and never to a specific engine.
The concrete adapter is chosen here, by name, from `MANTEL_ENGINE`:

    MANTEL_ENGINE=pi       drive Pi over its RPC protocol
    MANTEL_ENGINE=legacy   the vendor CLI this project started with (default)

Adding an engine means adding a module under `app/engines/` and one line to the
registry there; the shell does not change.
"""
from __future__ import annotations

import os

from app.engines import DEFAULT_TIMEOUT, Turn, create, known, registry
from app.engines.base import (ACCOUNT, APPROVALS, CLI_FLAGS, COMPACTION,
                              CONNECTORS, IMAGES, PERMISSION_FILE, REMOTE,
                              SESSIONS, SKILLS, STEERING, TOOLS)
from app.engines.legacy_agy import find_binary  # noqa: F401  (re-exported)

__all__ = [
    "Engine", "Turn", "find_binary", "DEFAULT_TIMEOUT", "known",
    "TOOLS", "APPROVALS", "SESSIONS", "STEERING", "IMAGES", "REMOTE",
    "ACCOUNT", "CONNECTORS", "SKILLS", "COMPACTION", "PERMISSION_FILE",
    "CLI_FLAGS",
]

#: Used until Pi reaches parity (docs/plan/pi-engine.md, milestone M3).
DEFAULT_ADAPTER = "legacy"


class Engine:
    """A thin, engine-neutral handle used by the window and the scheduler."""

    def __init__(self, binary: str | None = None, adapter: str | None = None):
        name = (adapter or os.environ.get("MANTEL_ENGINE") or DEFAULT_ADAPTER).strip()
        if name not in registry():
            name = DEFAULT_ADAPTER
        self.adapter_name = name
        try:
            self.adapter = create(name, binary=binary) if binary else create(name)
        except Exception:  # noqa: BLE001 - a broken adapter must not kill the app
            self.adapter_name = DEFAULT_ADAPTER
            self.adapter = create(DEFAULT_ADAPTER, binary=binary) if binary \
                else create(DEFAULT_ADAPTER)

    # -- identity -----------------------------------------------------------
    @property
    def name(self) -> str:
        return getattr(self.adapter, "name", self.adapter_name)

    @property
    def binary(self) -> str | None:
        """The executable behind the engine, when it has one."""
        return getattr(self.adapter, "binary", None)

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset(getattr(self.adapter, "capabilities", frozenset()))

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    # -- behaviour ----------------------------------------------------------
    @property
    def available(self) -> bool:
        return bool(getattr(self.adapter, "available", False))

    def models(self) -> list[tuple[str, str]]:
        try:
            return list(self.adapter.models())
        except Exception:  # noqa: BLE001
            return []

    def run(self, prompt: str, *args, **kwargs) -> Turn:
        return self.adapter.run(prompt, *args, **kwargs)

    def history(self, conversation_id: str) -> list[dict]:
        """A stored session's messages, when the engine keeps them."""
        try:
            return list(self.adapter.history(conversation_id))
        except Exception:  # noqa: BLE001 - history is best-effort
            return []
