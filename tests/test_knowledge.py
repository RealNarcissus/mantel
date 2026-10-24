"""Tests for the knowledge index.

The property that matters is that the index is *honest*: it indexes only what it
claims to, re-reads only what changed, forgets files that disappear, and returns
passages that actually contain the question. Plus the caps, because a notes
folder is not always small.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import (
    fonts_env,  # noqa: F401,E402
    knowledge,  # noqa: E402
)

NOTES = {
    "deploy.md": """# Deploying Mantel

The app is packaged as a Flatpak for the GNOME runtime. Deploys go through CI on
tag pushes, and the manifest lives in `packaging/flatpak/`.

Rollback is one command, and it must be run by a maintainer.
""",
    "focus.md": """# Focus rules

Deep work happens before noon. Meetings are clustered after lunch so the morning
stays free for code. The timer on the Today screen defaults to 25 minutes.
""",
    "binary.bin": "\x00\x01\x02 not text",
}


def fresh_notes() -> Path:
    folder = Path(tempfile.mkdtemp(prefix="mantel-notes-"))
    for name, text in NOTES.items():
        (folder / name).write_text(text)
    (folder / "sub").mkdir()
    (folder / "sub" / "nested.txt").write_text(
        "The nested note mentions the flatpak runtime too.")
    return folder


def main() -> int:
    failures: list[str] = []
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="mantel-knowledge-")
    folder = fresh_notes()

    # --- chunking --------------------------------------------------------
    chunks = knowledge.chunk_text("x" * 2500)
    print(f"  2500 chars -> {len(chunks)} chunks "
          f"(first={len(chunks[0])}, second={len(chunks[1])})")
    if len(chunks) < 3:
        failures.append(f"long text produced {len(chunks)} chunks")
    if len(chunks[0]) > knowledge.CHUNK_CHARS:
        failures.append("a chunk exceeded the window")
    if not chunks[0][-knowledge.CHUNK_OVERLAP:].strip():
        failures.append("chunks do not overlap")

    # --- adding a source indexes it -------------------------------------
    if not knowledge.add_source(str(folder)):
        failures.append("a real folder was rejected")
    stats = knowledge.stats()
    print(f"  indexed: files={stats['files']} chunks={stats['chunks']}")
    if stats["files"] != 3:      # 2 notes + 1 nested; the binary is skipped
        failures.append(f"expected 3 files indexed, got {stats['files']}")

    # --- retrieval -------------------------------------------------------
    hits = knowledge.search("how do we deploy and roll back")
    print(f"  search 'deploy/rollback' -> "
          f"{[Path(hit.path).name for hit in hits]}")
    if not hits or Path(hits[0].path).name != "deploy.md":
        failures.append(f"the deploy note did not rank first: "
                        f"{[hit.path for hit in hits]}")

    hits = knowledge.search("when is deep work")
    if not hits or Path(hits[0].path).name != "focus.md":
        failures.append("the focus note did not surface for its own topic")

    if knowledge.search("quantum chromodynamics lattice"):
        failures.append("an unrelated query returned notes")

    # --- the injected block is bounded and labelled ---------------------
    block = knowledge.context_block("how do we deploy")
    print(f"  injected block: {len(block)} chars")
    if "deploy.md" not in block:
        failures.append(f"the block does not name its source: {block!r}")
    if len(block) > knowledge.CONTEXT_BUDGET + 200:
        failures.append(f"the block ignored its budget: {len(block)} chars")
    if knowledge.context_block("kangaroo boxing"):
        failures.append("an unrelated prompt produced context")

    # --- a turn receives the relevant notes ------------------------------
    from app import engine as engine_mod  # noqa: PLC0415
    from app import session as session_mod  # noqa: PLC0415

    sess = session_mod.Session(engine_mod.Engine(adapter="pi"),
                               mode=session_mod.MODE_TASK)
    brief = sess.brief("how do we deploy this")
    print(f"  turn prefix mentions deploy.md: {'deploy.md' in brief}")
    if "Relevant notes" not in brief or "deploy.md" not in brief:
        failures.append("the prompt did not receive the relevant note")
    sess.use_knowledge = False
    if "Relevant notes" in sess.brief("how do we deploy this"):
        failures.append("knowledge injection could not be turned off")

    # --- incremental rescans --------------------------------------------
    (folder / "focus.md").write_text("# Focus rules\n\nChanged: deep work is "
                                     "now after lunch on Fridays.\n")
    before = knowledge.stats()["files"]
    result = knowledge.sync()
    print(f"  after edit: added={result['added']} removed={result['removed']}")
    if result["added"] != 1:
        failures.append(f"an edited file was not reindexed: {result}")
    if knowledge.stats()["files"] != before:
        failures.append("an edit changed the file count")
    if "after lunch" not in (knowledge.search("deep work fridays")[0].text
                             if knowledge.search("deep work fridays") else ""):
        failures.append("the edited text did not replace the old one")

    unchanged = knowledge.sync()
    if unchanged["added"]:
        failures.append("a second sync without changes reindexed files")

    # --- deleted files leave the index ----------------------------------
    (folder / "deploy.md").unlink()
    gone = knowledge.sync()
    print(f"  after delete: removed={gone['removed']}")
    if not gone["removed"]:
        failures.append("a deleted file stayed in the index")
    if any(Path(hit.path).name == "deploy.md"
           for hit in knowledge.search("deploy")):
        failures.append("a deleted file still matches")

    # --- a missing source is skipped, not fatal -------------------------
    knowledge._write_sources([str(folder), "/definitely/not/here"])
    knowledge.sync()
    if knowledge.stats()["files"] < 1:
        failures.append("a missing source broke the index")

    # --- removing a source ----------------------------------------------
    if not knowledge.remove_source(str(folder)):
        failures.append("removing a configured source failed")
    if knowledge.stats()["files"]:
        failures.append("removing the source left files indexed")

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        return 1
    print("  knowledge: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
