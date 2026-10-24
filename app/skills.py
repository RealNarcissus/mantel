"""Skills: the agent's reusable instructions.

A skill is a directory containing a ``SKILL.md`` — the same shape the
desktop app uses (create by hand, or upload a ``.zip`` of a folder holding
``SKILL.md``).  The engine keeps them in ``~/.gemini/skills`` and ships
plugins in the engine's local config directory, each with a ``plugin.json``.
"""
from __future__ import annotations

import json
import os  # noqa: E402
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path


def gemini_dir() -> Path:
    """Where the engine keeps skills. Local config, not a vendor account."""
    override = os.environ.get("MANTEL_ENGINE_HOME")
    if override:
        return Path(override).expanduser()
    return Path(os.environ.get("XDG_CONFIG_HOME")
                or (Path.home() / ".config")) / "mantel"

SKILL_FILE = "SKILL.md"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # the desktop app's limit


@dataclass
class Skill:
    """A skill or plugin the agent can draw on."""

    name: str
    description: str = ""
    path: str = ""
    kind: str = "skill"          # "skill" | "plugin"
    enabled: bool = True
    source: str = ""             # e.g. "uploaded", "bundled", "plugin"

    @property
    def invocable(self) -> bool:
        """Can it be invoked by name (i.e. does it look like a skill)?"""
        return self.kind == "skill"


def skills_dir() -> Path:
    return gemini_dir() / "skills"


def plugins_dir() -> Path:
    return gemini_dir() / "config" / "plugins"


def _front_matter(text: str) -> dict:
    """Read the YAML-ish front matter of a SKILL.md."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    out: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip().lower()] = value.strip().strip("\"'")
    return out


def _read_skill_file(path: Path) -> tuple[str, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "", ""
    meta = _front_matter(text)
    name = meta.get("name", path.parent.name)
    description = meta.get("description", "")
    if not description:
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("---"):
                description = line
                break
    return name, description[:200]


def list_skills() -> list[Skill]:
    """Every skill and plugin available to the agent."""
    out: list[Skill] = []

    root = skills_dir()
    if root.is_dir():
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            skill_file = entry / SKILL_FILE
            if skill_file.is_file():
                name, description = _read_skill_file(skill_file)
                out.append(Skill(name=name, description=description,
                                 path=str(entry), kind="skill",
                                 source="uploaded"))
            else:
                # a directory of sub-skills
                for sub in sorted(entry.iterdir()):
                    sub_file = sub / SKILL_FILE
                    if sub.is_dir() and sub_file.is_file():
                        name, description = _read_skill_file(sub_file)
                        out.append(Skill(name=name, description=description,
                                         path=str(sub), kind="skill",
                                         source="uploaded"))

    plugins = plugins_dir()
    if plugins.is_dir():
        for entry in sorted(plugins.iterdir()):
            manifest = entry / "plugin.json"
            if not manifest.is_file():
                continue
            try:
                data = json.loads(manifest.read_text())
            except (OSError, ValueError):
                continue
            out.append(Skill(
                name=str(data.get("name") or entry.name),
                description=str(data.get("description", ""))[:200],
                path=str(entry), kind="plugin",
                enabled=data.get("enabled", True) is not False,
                source="plugin",
            ))
    return out


def set_plugin_enabled(name: str, enabled: bool) -> bool:
    """Toggle a plugin in the engine's shared config."""
    path = gemini_dir() / "config" / "config.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    plugins = data.setdefault("plugins", {})
    entry = plugins.get(name)
    if not isinstance(entry, dict):
        entry = {}
    entry["enabled"] = enabled
    plugins[name] = entry
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        tmp.replace(path)
    except OSError:
        return False
    return True


def install_skill(name: str, description: str, body: str) -> tuple[bool, str]:
    """Create a skill from a template."""
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        return False, "A skill name must be lowercase words separated by dashes."
    root = skills_dir()
    target = root / name
    if target.exists():
        return False, f"A skill called {name} already exists."
    try:
        target.mkdir(parents=True)
        (target / SKILL_FILE).write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n")
    except OSError as exc:
        return False, f"Could not create the skill: {exc}"
    return True, f"Created the skill {name}."


def install_skill_zip(path: str) -> tuple[bool, str]:
    """Install a skill from a ``.zip`` holding a folder with ``SKILL.md``."""
    archive = Path(path)
    if not archive.is_file():
        return False, "That file does not exist."
    try:
        if archive.stat().st_size > MAX_UPLOAD_BYTES:
            return False, "That archive is larger than 100 MB."
    except OSError as exc:
        return False, f"Could not read the archive: {exc}"
    try:
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            skill_members = [n for n in names if n.endswith(SKILL_FILE)]
            if not skill_members:
                return False, "The archive must contain a SKILL.md file."
            member = skill_members[0]
            folder = member.split("/")[0] if "/" in member else ""
            if not folder:
                return False, "The SKILL.md must be inside a folder."
            name, description = _read_skill_file_text(zf.read(member))
            target = skills_dir() / folder
            if target.exists():
                return False, f"A skill called {folder} already exists."
            target.mkdir(parents=True)
            for n in names:
                if not n.startswith(folder + "/"):
                    continue
                dest = target / n[len(folder) + 1:]
                if ".." in n or n.endswith("/"):
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(n))
    except (OSError, zipfile.BadZipFile) as exc:
        return False, f"Could not read the archive: {exc}"
    return True, f"Installed the skill {name or folder}."


def _read_skill_file_text(raw: bytes) -> tuple[str, str]:
    import tempfile
    with tempfile.NamedTemporaryFile("wb", suffix=".md", delete=False) as tmp:
        tmp.write(raw)
        path = Path(tmp.name)
    try:
        return _read_skill_file(path)
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def delete_skill(name: str) -> bool:
    for skill in list_skills():
        if skill.name == name and skill.kind == "skill":
            import shutil
            try:
                shutil.rmtree(skill.path)
            except OSError:
                return False
            return True
    return False
