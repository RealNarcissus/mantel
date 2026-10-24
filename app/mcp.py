"""Connectors: the MCP servers the agent can use.

The real desktop app calls these "Connectors" (custom MCP apps are added by
server URL).  The engine here manages them through its own CLI, so the
client shells out to `agy mcp` rather than editing files behind its back.

Configuration lives in ``~/.gemini/config/mcp_config.json`` and
``~/.gemini/settings.json`` (both hold an ``mcpServers`` map).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.account import gemini_dir


@dataclass
class Server:
    """One MCP server."""

    name: str
    command: str = ""
    args: list[str] = field(default_factory=list)
    url: str = ""
    env: dict = field(default_factory=dict)
    enabled: bool = True

    @property
    def kind(self) -> str:
        return "http" if self.url else "stdio"

    @property
    def target(self) -> str:
        if self.url:
            return self.url
        parts = [self.command, *self.args]
        return " ".join(parts)

    @property
    def short(self) -> str:
        if self.url:
            return self.url.replace("https://", "").replace("http://", "")
        return self.command.split("/")[-1] or self.command


def config_files() -> list[Path]:
    return [gemini_dir() / "config" / "mcp_config.json",
            gemini_dir() / "settings.json"]


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def list_servers() -> list[Server]:
    """Every configured server, merged across the config files."""
    merged: dict[str, Server] = {}
    for path in config_files():
        data = _read(path)
        for name, spec in (data.get("mcpServers") or {}).items():
            if not isinstance(spec, dict):
                continue
            server = Server(
                name=str(name),
                command=str(spec.get("command", "")),
                args=[str(a) for a in (spec.get("args") or [])],
                url=str(spec.get("url", "") or spec.get("httpUrl", "")),
                env=dict(spec.get("env") or {}),
                enabled=spec.get("enabled", True) is not False,
            )
            merged[server.name] = server
    return sorted(merged.values(), key=lambda s: s.name.lower())


def _write(path: Path, servers: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _read(path)
        data["mcpServers"] = servers
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        tmp.replace(path)
        return True
    except OSError:
        return False


def add_server(name: str, command: str = "", args: list[str] | None = None,
               url: str = "", env: dict | None = None) -> bool:
    """Add a server to the engine's own MCP config."""
    spec: dict = {}
    if url:
        spec["url"] = url
    else:
        spec["command"] = command
        spec["args"] = list(args or [])
    if env:
        spec["env"] = dict(env)
    servers: dict = {}
    path = gemini_dir() / "config" / "mcp_config.json"
    servers.update(_read(path).get("mcpServers") or {})
    servers[name] = spec
    if not _write(path, servers):
        return False
    # keep the second store in step when it exists
    other = gemini_dir() / "settings.json"
    if other.is_file():
        _write(other, servers)
    return True


def remove_server(name: str) -> bool:
    removed = False
    for path in config_files():
        data = _read(path)
        servers = dict(data.get("mcpServers") or {})
        if name in servers:
            servers.pop(name)
            removed = _write(path, servers) or removed
    return removed


def set_enabled(name: str, enabled: bool) -> bool:
    ok = False
    for path in config_files():
        data = _read(path)
        servers = dict(data.get("mcpServers") or {})
        if name in servers:
            spec = dict(servers[name])
            spec["enabled"] = enabled
            servers[name] = spec
            ok = _write(path, servers) or ok
    return ok


def engine_cli() -> str | None:
    """The engine binary, for `agy mcp`."""
    from app import engine as engine_mod  # noqa: PLC0415

    return engine_mod.find_binary()


def run_engine_mcp(*args: str) -> tuple[bool, str]:
    """Run an `agy mcp` subcommand."""
    binary = engine_cli()
    if not binary:
        return False, "engine binary not found"
    try:
        res = subprocess.run([binary, "mcp", *args], capture_output=True,
                             text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    out = (res.stdout or "") + (res.stderr or "")
    return res.returncode == 0, out.strip()


def engine_list() -> list[Server]:
    """The engine's own view of the servers, if it can be read."""
    ok, out = run_engine_mcp("list")
    if not ok or not out:
        return []
    servers: list[Server] = []
    lines = out.splitlines()
    for line in lines[1:]:            # skip the header
        parts = line.split()
        if len(parts) >= 2:
            servers.append(Server(name=parts[0], kind=parts[1],
                                  command=parts[-1] if len(parts) > 3 else ""))
    return servers
