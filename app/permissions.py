"""Permission grants and trusted folders.

The engine decides whether an action is allowed by reading shared permission
grants from its config (``~/.gemini/config/config.json``):

    userSettings.globalPermissionGrants = {"allow": [...], "deny": [...],
                                            "ask": [...]}

Each rule is ``action(path)`` — ``read_file(*)``, ``write_file(/home/me/x)``,
``run_command(*)``.  A rule in ``allow`` is applied; anything else is refused
in non-interactive mode, which is how the engine reports it back as a
``denied_actions`` entry.

The client owns this file, so it can offer the app-level trust model the
real desktop app has: connect a folder once, and the agent may work in it.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.account import gemini_dir

#: Actions the engine knows about, and whether they need a path.
ACTIONS = {
    "read_file": True,
    "write_file": True,
    "replace_file_content": True,
    "multi_replace_file_content": True,
    "sed_file": True,
    "notebook_edit": True,
    "run_command": False,
    "list_dir": True,
    "grep_search": False,
    "search_web": False,
    "read_url_content": False,
}

#: Actions that change something on the machine.
MUTATING = {"write_file", "replace_file_content", "multi_replace_file_content",
             "sed_file", "notebook_edit", "run_command"}


def config_path() -> Path:
    return gemini_dir() / "config" / "config.json"


def cli_settings_path() -> Path:
    return gemini_dir() / "antigravity-cli" / "settings.json"


@dataclass
class Grant:
    action: str
    path: str = "*"

    @property
    def rule(self) -> str:
        return f"{self.action}({self.path})"

    @classmethod
    def parse(cls, rule: str) -> "Grant | None":
        rule = rule.strip()
        if "(" not in rule or not rule.endswith(")"):
            return None
        action, _, path = rule.partition("(")
        return cls(action.strip(), path[:-1].strip() or "*")


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


def grants() -> list[Grant]:
    """Every rule the engine currently honours."""
    cfg = _read_json(config_path())
    user = cfg.get("userSettings") or {}
    block = user.get("globalPermissionGrants") or {}
    out: list[Grant] = []
    for key in ("allow", "deny", "ask"):
        for rule in block.get(key) or []:
            parsed = Grant.parse(str(rule))
            if parsed:
                out.append(parsed)
    return out


def allowed_rules() -> list[str]:
    cfg = _read_json(config_path())
    user = cfg.get("userSettings") or {}
    block = user.get("globalPermissionGrants") or {}
    return [str(r) for r in (block.get("allow") or [])]


def _set_allow(rules: list[str]) -> None:
    cfg = _read_json(config_path())
    user = cfg.setdefault("userSettings", {})
    block = user.setdefault("globalPermissionGrants", {})
    block["allow"] = sorted(set(rules))
    block.setdefault("deny", [])
    block.setdefault("ask", [])
    _write_json(config_path(), cfg)


def allow(action: str, path: str = "*") -> str:
    """Grant an action, and clear any pending 'ask' for the same action.

    Returns the rule that was added.
    """
    rule = Grant(action, path).rule
    rules = set(allowed_rules())
    rules.add(rule)
    cfg = _read_json(config_path())
    user = cfg.setdefault("userSettings", {})
    block = user.setdefault("globalPermissionGrants", {})
    block["allow"] = sorted(rules)
    # a rule that is still listed under `ask` would keep holding the action,
    # so granting it has to remove it from there as well
    block["ask"] = [r for r in (block.get("ask") or [])
                    if not str(r).startswith(f"{action}(")]
    block.setdefault("deny", [])
    _write_json(config_path(), cfg)
    return rule


def revoke(rule: str) -> bool:
    rules = set(allowed_rules())
    if rule in rules:
        rules.discard(rule)
        _set_allow(sorted(rules))
        return True
    return False


def allow_folder(folder: str) -> list[str]:
    """Trust a folder: allow reading, writing and searching inside it."""
    folder = str(Path(folder).expanduser().resolve())
    added = []
    for action in ("read_file", "write_file", "replace_file_content",
                   "multi_replace_file_content", "sed_file", "list_dir"):
        added.append(allow(action, folder))
    return added


def trusted_folders() -> list[str]:
    """Folders the engine already treats as trusted."""
    settings = _read_json(cli_settings_path())
    return [str(p) for p in (settings.get("trustedWorkspaces") or [])]


def trust_folder(folder: str) -> bool:
    """Mark a folder as a trusted workspace in the engine's own settings."""
    settings = _read_json(cli_settings_path())
    folders = list(settings.get("trustedWorkspaces") or [])
    resolved = str(Path(folder).expanduser().resolve())
    if resolved in folders:
        return False
    folders.append(resolved)
    settings["trustedWorkspaces"] = folders
    try:
        _write_json(cli_settings_path(), settings)
    except OSError:
        return False
    return True


def is_trusted(folder: str) -> bool:
    try:
        resolved = str(Path(folder).expanduser().resolve())
    except OSError:
        return False
    return any(str(Path(f).expanduser().resolve()) == resolved
               for f in trusted_folders())


def writable() -> bool:
    """Can the client persist grants? (False on a locked-down machine.)"""
    path = config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        probe = path.parent / ".write-probe"
        probe.write_text("")
        probe.unlink()
        return True
    except OSError:
        return False


def open_in_file_manager(path: str) -> bool:
    """Reveal a path in the desktop's file manager."""
    target = Path(path).expanduser()
    if not target.exists():
        target = target.parent
    for opener in ("xdg-open", "gio", "nautilus", "dolphin", "thunar"):
        if shutil.which(opener):
            args = [opener, str(target)]
            if opener == "gio":
                args = ["gio", "open", str(target)]
            try:
                import subprocess
                subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                return True
            except OSError:
                continue
    return False
