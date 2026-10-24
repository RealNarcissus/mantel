"""Checks for the Changes panel's git reader.

Builds a throwaway repository, edits files, and verifies the panel's data is
what git actually reports.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import (
    changes,  # noqa: E402
    fonts_env,  # noqa: F401
)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t",
                    "-c", "user.name=t", *args],
                   capture_output=True, check=False)


def main() -> int:
    failures: list[str] = []
    repo = Path(tempfile.mkdtemp(prefix="gemini-changes-"))
    git(repo, "init", "-q")

    print(f"  repo: {repo}")

    # a folder that is not a repo reads as "not available"
    plain = Path(tempfile.mkdtemp(prefix="gemini-plain-"))
    if changes.available(str(plain)):
        failures.append("a plain folder reported itself as a git repo")
    if changes.collect(str(plain)):
        failures.append("a plain folder produced changes")
    print("  non-repo folder -> no changes")

    (repo / "notes.md").write_text("one\ntwo\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")

    if not changes.available(str(repo)):
        failures.append("a real repo was not detected")

    # a clean tree has no changes
    if changes.collect(str(repo)):
        failures.append("a clean tree reported changes")
    print("  clean tree -> no changes")

    # commit a file first, then delete it, so the deletion shows up
    (repo / "gone.md").write_text("bye\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "add gone")

    # now make the working tree dirty
    (repo / "notes.md").write_text("one\ntwo changed\nthree\n")
    (repo / "fresh.md").write_text("hello\n")
    (repo / "gone.md").unlink()

    files = {f.path: f for f in changes.collect(str(repo))}
    print("  changes:", {p: (f.status, f.summary) for p, f in files.items()})

    if "notes.md" not in files:
        failures.append("a modified file was missed")
    else:
        notes = files["notes.md"]
        if notes.status != "modified":
            failures.append(f"notes.md status = {notes.status!r}")
        if notes.added != 2 or notes.removed != 1:
            failures.append(f"notes.md counts = +{notes.added} -{notes.removed},"
                            f" expected +2 -1")
        if notes.name != "notes.md":
            failures.append("the display name is wrong")

    if "fresh.md" not in files:
        failures.append("an untracked file was missed")
    elif files["fresh.md"].status != "untracked":
        failures.append(f"fresh.md status = {files['fresh.md'].status!r}")

    if "gone.md" not in files:
        failures.append("a deleted file was missed")
    elif files["gone.md"].status != "deleted":
        failures.append(f"gone.md status = {files['gone.md'].status!r}")

    # a diff exists for a tracked file and quotes the change
    text = changes.diff(str(repo), "notes.md")
    if "two changed" not in text:
        failures.append("the diff does not contain the edit")
    if not text.startswith("diff --git") and "@@" not in text:
        failures.append("the diff does not look like a unified diff")
    print(f"  diff for notes.md: {len(text.splitlines())} lines")

    # an untracked file has no diff, so its contents are shown instead
    untracked = changes.diff(str(repo), "fresh.md")
    if "hello" not in untracked:
        failures.append("an untracked file's contents were not shown")
    print("  untracked file shows its contents")

    # a missing path does not raise
    if not isinstance(changes.diff(str(repo), "nope.md"), str):
        failures.append("diff() did not return text for a missing path")

    print()
    if failures:
        for f in failures:
            print(f"  FAIL: {f}")
        return 1
    print("  changes: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
