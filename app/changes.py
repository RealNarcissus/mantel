"""Changes: what the agent actually touched in the workspace.

Codex and Claude both make the working tree, not the agent's claims, the
source of truth. This asks git directly, so the panel shows real edits —
including ones the agent made silently.

Nothing here writes: it only reads `git status` and `git diff`.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ChangedFile:
    """One file in the working tree."""

    path: str
    status: str        # "modified" | "added" | "deleted" | "renamed" | "untracked"
    added: int = 0
    removed: int = 0

    @property
    def summary(self) -> str:
        parts = []
        if self.added:
            parts.append(f"+{self.added}")
        if self.removed:
            parts.append(f"-{self.removed}")
        return " ".join(parts)

    @property
    def name(self) -> str:
        return Path(self.path).name or self.path


_STATUS_WORDS = {
    "M": "modified", "A": "added", "D": "deleted", "R": "renamed",
    "C": "copied", "U": "conflicted", "?": "untracked",
}


def _git(workspace: str, *args: str, timeout: int = 20) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", workspace, *args],
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def available(workspace: str) -> bool:
    """Is the working folder inside a git repository?"""
    if not workspace or not Path(workspace).is_dir():
        return False
    return bool(_git(workspace, "rev-parse", "--is-inside-work-tree").strip())


def collect(workspace: str) -> list[ChangedFile]:
    """Every changed file, with line counts where git reports them."""
    if not available(workspace):
        return []

    counts: dict[str, tuple[int, int]] = {}
    for line in _git(workspace, "diff", "--numstat", "HEAD").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added, removed, path = parts[0], parts[1], parts[2]
        try:
            counts[path] = (int(added), int(removed))
        except ValueError:
            counts[path] = (0, 0)      # binary files report "-"

    files: list[ChangedFile] = []
    seen: set[str] = set()
    for line in _git(workspace, "status", "--porcelain").splitlines():
        if len(line) < 4:
            continue
        xy = line[:2]
        path = line[3:].strip()
        if " -> " in path:             # renames read "old -> new"
            path = path.split(" -> ", 1)[1]
        if path in seen:
            continue
        seen.add(path)
        # porcelain v1 is XY: index status then worktree status. A deletion in
        # the working tree is " D", so the first column alone is misleading.
        if xy == "??":
            status = "untracked"
        else:
            code = xy[0] if xy[0] not in " ?" else xy[1]
            status = _STATUS_WORDS.get(code, "modified")
        added, removed = counts.get(path, (0, 0))
        files.append(ChangedFile(path=path, status=status,
                                 added=added, removed=removed))

    files.sort(key=lambda f: f.path)
    return files


def diff(workspace: str, path: str = "", limit: int = 4000) -> str:
    """The unified diff, optionally for one file, truncated for display."""
    args = ["diff", "HEAD"]
    if path:
        args += ["--", path]
    text = _git(workspace, *args, timeout=30)
    if not text and path:
        # an untracked file has no diff; show its contents instead
        try:
            target = Path(workspace) / path
            if target.is_file():
                body = target.read_text(errors="replace")
                return f"# {path} (untracked)\n\n{body[:limit]}"
        except OSError:
            pass
    return text[:limit]
