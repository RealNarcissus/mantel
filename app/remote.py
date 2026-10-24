"""Remote control: use this machine's agent from a phone.

This module drives a vendor-engine surface. It is gated on the legacy
adapter's capabilities and is removed when that adapter goes away
(docs/plan/pi-engine.md, M6).

The desktop app can be driven from the Gemini mobile app ("Add Computer"):
the machine runs a background daemon, and the phone talks to it. The engine
ships exactly that daemon, so the client exposes it rather than reimplementing
anything:

    agy remote-control start | status | stop

`status` reports whether the daemon is registered and what instance name it
was given, which is what the user pairs with on the phone.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from app import engine as engine_mod


@dataclass
class RemoteStatus:
    """What the engine reports about the remote-control daemon."""

    running: bool = False
    reachable: bool = False
    instance: str = ""
    detail: str = ""
    log_hint: str = ""

    @property
    def label(self) -> str:
        if self.running and self.reachable:
            return "Available to your phone"
        if self.running:
            return "Starting…"
        return "Off"


def _run(*args: str, timeout: int = 30) -> tuple[bool, str]:
    binary = engine_mod.find_binary()
    if not binary:
        return False, "the engine binary was not found"
    try:
        result = subprocess.run([binary, "remote-control", *args],
                                capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    return result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def status() -> RemoteStatus:
    """Read the daemon's state from the engine."""
    ok, out = _run("status")
    state = RemoteStatus(detail=out.strip()[:400])
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Daemon status:"):
            text = line.split(":", 1)[1].strip().lower()
            state.running = ("active" in text or "running" in text
                             or "registered" in text)
            state.reachable = state.running and "failed" not in text
        elif line.startswith("Instance name:"):
            name = line.split(":", 1)[1].strip()
            match = re.search(r"[A-Za-z0-9][A-Za-z0-9._-]{2,}", name)
            if match and "not assigned" not in name.lower():
                state.instance = match.group()
            elif "not assigned" in name.lower():
                state.instance = ""
        elif "journalctl" in line:
            state.log_hint = line.strip()
    if not ok and not state.running:
        state.reachable = False
    return state


def start() -> tuple[bool, str]:
    """Register and start the daemon."""
    return _run("start", timeout=60)


def stop() -> tuple[bool, str]:
    """Stop the daemon and unregister it."""
    return _run("stop", timeout=60)


def available() -> bool:
    return engine_mod.find_binary() is not None
