"""Plugins: let people make the app theirs, without letting them break it.

The design follows the vision's three tiers (`docs/VISION.md` §8), and this
module implements the one with teeth — **extensions**: a program that
contributes commands (and later panels and triggers) and runs *out of process*,
talking JSON-RPC over stdin/stdout.

Two decisions are load-bearing:

1. **The manifest is data, not code.** Installing a plugin never executes it.
   The manifest is read, validated and shown as a capability sheet; only an
   explicit user action runs the program.
2. **Every call is a request with a deadline.** The host spawns the program,
   sends one JSON line, reads one JSON line, and kills the process if it takes
   too long. A plugin cannot take the app down with it, and a hung plugin is a
   failed command, not a hung client.

Skills and connectors already exist elsewhere (markdown instructions, MCP
servers); this is the tier that needs a host.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

#: Manifest version this client understands.
API_VERSION = 1

#: How long one plugin command may take before the process is killed.
CALL_TIMEOUT = 8

#: Permission keys and the values they accept.
PERMISSION_KEYS = {
    "fs": {"none", "workspace"},
    "net": list,          # list of host names, or [] for none
    "memory": {"none", "read", "write"},
    "exec": bool,
    "ui": list,           # "panel", "page" — declarative contributions only
}
KNOWN_PERMISSIONS = frozenset(PERMISSION_KEYS)

#: Safe mode: no plugin code runs at all.
SAFE_MODE_ENV = "MANTEL_SAFE_MODE"

#: Where a declarative panel may appear, and its limits. Panels are *data*:
#: the host renders rows and buttons, the plugin never supplies markup.
PANEL_SLOTS = ("today", "plugins")
MAX_PANELS = 3
MAX_PANEL_ROWS = 6
MAX_ROW_LABEL = 80

_ID = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)+$")


def data_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME")
                or (Path.home() / ".local" / "share"))
    for candidate in (base / "mantel", Path(__file__).resolve().parent.parent
                      / ".data"):
        try:
            (candidate / "plugins").mkdir(parents=True, exist_ok=True)
            probe = candidate / "plugins" / ".write-probe"
            probe.write_text("")
            probe.unlink()
            return candidate
        except OSError:
            continue
    import tempfile  # noqa: PLC0415

    return Path(tempfile.mkdtemp(prefix="mantel-plugins-"))


def plugins_dir() -> Path:
    return data_dir() / "plugins"


def state_path() -> Path:
    return data_dir() / "plugins" / "installed.json"


def audit_path() -> Path:
    return data_dir() / "plugins" / "audit.jsonl"


def safe_mode() -> bool:
    return bool(os.environ.get(SAFE_MODE_ENV))


# --- the manifest -----------------------------------------------------------

@dataclass
class Manifest:
    id: str
    name: str
    version: str
    entry: list[str]
    description: str = ""
    author: str = ""
    api_version: int = API_VERSION
    permissions: dict = field(default_factory=dict)
    commands: list[dict] = field(default_factory=list)
    panels: list[dict] = field(default_factory=list)

    @property
    def capabilities(self) -> list[str]:
        """Human-readable capability sheet for the install dialog."""
        out = []
        fs = self.permissions.get("fs", "none")
        if fs != "none":
            out.append(f"read/write files ({fs})")
        net = self.permissions.get("net") or []
        if net:
            out.append("network: " + ", ".join(str(host) for host in net))
        memory = self.permissions.get("memory", "none")
        if memory != "none":
            out.append(f"memory ({memory})")
        if self.permissions.get("exec"):
            out.append("run commands")
        ui = self.permissions.get("ui") or []
        if ui:
            rendered = ", ".join(str(panel.get("title") or "panel")
                                 for panel in self.panels) or "none"
            out.append("add UI: " + ", ".join(str(slot) for slot in ui)
                       + f" ({rendered})")
        return out or ["no special access"]


def parse_manifest(raw: dict, *, source: str = "") -> tuple[Manifest | None, list[str]]:
    """Validate a manifest. Returns (manifest, problems)."""
    problems: list[str] = []
    if not isinstance(raw, dict):
        return None, ["manifest is not an object"]

    plugin_id = str(raw.get("id") or "").strip()
    if not _ID.match(plugin_id):
        problems.append("id must be reverse-DNS style, e.g. com.example.hello")
    name = str(raw.get("name") or "").strip()
    if not name:
        problems.append("name is required")
    version = str(raw.get("version") or "0.0.0").strip()
    try:
        api = int(raw.get("apiVersion") or 0)
    except (TypeError, ValueError):
        api = 0
    if api != API_VERSION:
        problems.append(f"apiVersion must be {API_VERSION}")

    entry = raw.get("entry")
    if not isinstance(entry, list) or not entry or not all(
            isinstance(part, str) and part for part in entry):
        problems.append("entry must be a list of strings (argv, no shell)")

    permissions = raw.get("permissions") or {}
    if not isinstance(permissions, dict):
        problems.append("permissions must be an object")
        permissions = {}
    for key, value in permissions.items():
        if key not in KNOWN_PERMISSIONS:
            problems.append(f"unknown permission {key!r}")
            continue
        expected = PERMISSION_KEYS[key]
        if isinstance(expected, set):
            if value not in expected:
                problems.append(f"permission {key} must be one of "
                                f"{sorted(expected)}")
        elif expected is list:
            if not isinstance(value, list):
                problems.append(f"permission {key} must be a list")
        elif expected is bool and not isinstance(value, bool):
            problems.append(f"permission {key} must be true or false")

    commands = raw.get("commands") or []
    if not isinstance(commands, list):
        problems.append("commands must be a list")
        commands = []
    cleaned_commands = []
    for command in commands:
        if not isinstance(command, dict):
            problems.append("each command must be an object")
            continue
        command_id = str(command.get("id") or "").strip()
        title = str(command.get("title") or "").strip()
        if not command_id or not title:
            problems.append("commands need an id and a title")
            continue
        cleaned_commands.append({
            "id": command_id, "title": title,
            "description": str(command.get("description") or ""),
        })

    panels_raw = raw.get("panels") or []
    if not isinstance(panels_raw, list):
        problems.append("panels must be a list")
        panels_raw = []
    if len(panels_raw) > MAX_PANELS:
        problems.append(f"at most {MAX_PANELS} panels per plugin")
        panels_raw = panels_raw[:MAX_PANELS]
    declared_commands = {command["id"] for command in cleaned_commands}
    cleaned_panels = []
    for panel in panels_raw:
        if not isinstance(panel, dict):
            problems.append("each panel must be an object")
            continue
        panel_id = str(panel.get("id") or "").strip()
        title = str(panel.get("title") or "").strip()
        slot = str(panel.get("slot") or "").strip()
        if not panel_id or not title:
            problems.append("panels need an id and a title")
            continue
        if slot not in PANEL_SLOTS:
            problems.append(f"panel slot must be one of {list(PANEL_SLOTS)}")
            continue
        rows_raw = panel.get("rows") or []
        if not isinstance(rows_raw, list) or not rows_raw:
            problems.append(f"panel {panel_id!r} needs at least one row")
            continue
        if len(rows_raw) > MAX_PANEL_ROWS:
            problems.append(f"panel {panel_id!r} has more than "
                            f"{MAX_PANEL_ROWS} rows")
            rows_raw = rows_raw[:MAX_PANEL_ROWS]
        rows = []
        for row in rows_raw:
            if not isinstance(row, dict):
                problems.append(f"panel {panel_id!r} rows must be objects")
                continue
            label = str(row.get("label") or "").strip()
            command_id = str(row.get("command") or "").strip()
            if not label or len(label) > MAX_ROW_LABEL:
                problems.append(f"panel {panel_id!r} rows need a label under "
                                f"{MAX_ROW_LABEL} chars")
                continue
            if command_id not in declared_commands:
                problems.append(f"panel {panel_id!r} row {label!r} refers to "
                                f"an undeclared command {command_id!r}")
                continue
            rows.append({"label": label, "command": command_id})
        if rows:
            cleaned_panels.append({"id": panel_id, "title": title,
                                   "slot": slot, "rows": rows})

    if problems:
        return None, problems
    return Manifest(id=plugin_id, name=name, version=version, entry=list(entry),
                    description=str(raw.get("description") or ""),
                    author=str(raw.get("author") or ""),
                    api_version=api, permissions=permissions,
                    commands=cleaned_commands, panels=cleaned_panels), []


# --- installed plugins ------------------------------------------------------

def _read_state() -> dict:
    try:
        raw = json.loads(state_path().read_text())
    except (OSError, ValueError):
        return {"plugins": []}
    if isinstance(raw, dict) and isinstance(raw.get("plugins"), list):
        return raw
    return {"plugins": []}


def _write_state(state: dict) -> bool:
    try:
        path = state_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1))
        tmp.replace(path)
        return True
    except OSError:
        return False


@dataclass
class Plugin:
    manifest: Manifest
    path: Path
    enabled: bool = True
    installed: float = field(default_factory=time.time)
    source: str = "local"

    @property
    def argv(self) -> list[str]:
        """The entry command, with the plugin directory as the working dir."""
        return list(self.manifest.entry)


def installed(*, include_disabled: bool = True) -> list[Plugin]:
    """Plugins on disk, newest first. Safe mode returns nothing."""
    if safe_mode():
        return []
    out: list[Plugin] = []
    state = _read_state()
    for row in state.get("plugins", []):
        if not isinstance(row, dict):
            continue
        folder = plugins_dir() / str(row.get("id") or "")
        manifest_file = folder / "mantel.json"
        try:
            raw = json.loads(manifest_file.read_text())
        except (OSError, ValueError):
            continue
        manifest, _problems = parse_manifest(raw)
        if manifest is None:
            continue
        enabled = bool(row.get("enabled", True))
        if not enabled and not include_disabled:
            continue
        out.append(Plugin(manifest=manifest, path=folder, enabled=enabled,
                          installed=float(row.get("installed") or 0),
                          source=str(row.get("source") or "local")))
    out.sort(key=lambda plugin: plugin.installed, reverse=True)
    return out


def install(source: Path, *, enable: bool = True) -> tuple[Plugin | None, list[str]]:
    """Copy a plugin directory into the store. Never runs the code."""
    source = Path(source)
    manifest_file = source / "mantel.json"
    try:
        raw = json.loads(manifest_file.read_text())
    except (OSError, ValueError) as error:
        return None, [f"cannot read mantel.json: {error}"]
    manifest, problems = parse_manifest(raw)
    if manifest is None:
        return None, problems

    target = plugins_dir() / manifest.id
    try:
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
    except OSError as error:
        return None, [f"cannot copy the plugin: {error}"]

    state = _read_state()
    rows = [row for row in state.get("plugins", [])
            if isinstance(row, dict) and row.get("id") != manifest.id]
    rows.append({"id": manifest.id, "enabled": enable,
                 "installed": time.time(), "source": str(source)})
    state["plugins"] = rows
    _write_state(state)
    _audit(manifest.id, "install", f"from {source}")
    return Plugin(manifest=manifest, path=target, enabled=enable), []


def remove(plugin_id: str) -> bool:
    state = _read_state()
    rows = [row for row in state.get("plugins", [])
            if isinstance(row, dict) and row.get("id") != plugin_id]
    if len(rows) == len(state.get("plugins", [])):
        return False
    state["plugins"] = rows
    _write_state(state)
    try:
        shutil.rmtree(plugins_dir() / plugin_id)
    except OSError:
        pass
    _audit(plugin_id, "remove", "")
    return True


def set_enabled(plugin_id: str, enabled: bool) -> bool:
    state = _read_state()
    for row in state.get("plugins", []):
        if isinstance(row, dict) and row.get("id") == plugin_id:
            row["enabled"] = bool(enabled)
            _write_state(state)
            _audit(plugin_id, "enable" if enabled else "disable", "")
            return True
    return False


def find(plugin_id: str) -> Plugin | None:
    return next((plugin for plugin in installed()
                 if plugin.manifest.id == plugin_id), None)


def commands() -> list[tuple[Plugin, dict]]:
    """(plugin, command) pairs for the palette, from enabled plugins."""
    out: list[tuple[Plugin, dict]] = []
    for plugin in installed(include_disabled=False):
        for command in plugin.manifest.commands:
            out.append((plugin, command))
    return out


# --- running one ------------------------------------------------------------

def _audit(plugin_id: str, action: str, detail: str) -> None:
    try:
        with audit_path().open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "ts": time.time(), "plugin": plugin_id, "action": action,
                "detail": detail[:300],
            }) + "\n")
    except OSError:
        pass


def audit_log(limit: int = 50) -> list[dict]:
    try:
        lines = audit_path().read_text().splitlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def call(plugin: Plugin, method: str, params: dict | None = None,
         *, timeout: int = CALL_TIMEOUT) -> tuple[bool, object]:
    """Run one request against a plugin process.

    Returns (ok, result-or-error). The process is spawned per call: isolation
    matters more than start-up cost for the commands a plugin exposes.
    """
    if not plugin.enabled:
        return False, "plugin is disabled"
    if safe_mode():
        return False, f"safe mode ({SAFE_MODE_ENV}) is on"

    argv = plugin.argv
    if not argv:
        return False, "the plugin has no entry command"
    request = {"id": uuid.uuid4().hex[:8], "method": method,
               "params": params or {}}
    try:
        proc = subprocess.run(
            argv,
            cwd=str(plugin.path),
            input=json.dumps(request) + "\n",
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "MANTEL_PLUGIN_ID": plugin.manifest.id},
            start_new_session=True,
        )
    except subprocess.TimeoutExpired:
        _audit(plugin.manifest.id, method, "timeout")
        return False, f"{plugin.manifest.name} did not answer within {timeout}s"
    except OSError as error:
        _audit(plugin.manifest.id, method, f"spawn failed: {error}")
        return False, f"could not start {plugin.manifest.name}: {error}"

    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        if record.get("id") not in (None, request["id"]):
            continue
        _audit(plugin.manifest.id, method, "ok" if record.get("ok") else "error")
        if record.get("ok"):
            return True, record.get("result")
        return False, str(record.get("error") or "the plugin reported an error")

    detail = (proc.stderr or "").strip().splitlines()
    _audit(plugin.manifest.id, method, "no answer")
    return False, (f"{plugin.manifest.name} returned no answer"
                   + (f": {detail[-1][:160]}" if detail else ""))


def run_command(plugin: Plugin, command_id: str,
                params: dict | None = None) -> tuple[bool, object]:
    """Run one contributed command."""
    return call(plugin, "command", {"command": command_id,
                                    **(params or {})})


def context(plugin: Plugin) -> dict:
    """The data a plugin may see for a command call, per its declarations."""
    import time  # noqa: PLC0415

    from app import memory as memory_mod  # noqa: PLC0415
    from app import todos  # noqa: PLC0415

    permissions = plugin.manifest.permissions
    payload: dict = {"date": time.strftime("%A %d %B")}
    if permissions.get("memory") in ("read", "write"):
        payload["memory"] = [fact.text for fact in memory_mod.facts()[:10]]
    open_tasks = todos.all_tasks(include_done=False)
    payload["tasks"] = [task.title for task in open_tasks[:20]]
    payload["overdue"] = sum(1 for task in open_tasks if task.overdue)
    return payload


def panels(slot: str) -> list[tuple[Plugin, dict]]:
    """Panels contributed for a slot, from enabled plugins that asked for UI.

    Declarative only: a panel is a titled list of (label, command) rows. The
    host decides how it looks, so a plugin cannot inject markup or run code at
    render time.
    """
    out: list[tuple[Plugin, dict]] = []
    for plugin in installed(include_disabled=False):
        if "panel" not in (plugin.manifest.permissions.get("ui") or []):
            continue
        for panel in plugin.manifest.panels:
            if panel.get("slot") == slot:
                out.append((plugin, panel))
    return out
