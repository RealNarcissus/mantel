"""Knowledge connectors: let the agent read your own notes.

Memory (`app/memory.py`) is what the agent learns *about you* from
conversation. This is the other half: a folder of your writing — notes, a vault,
a `~/docs` directory — indexed locally so the agent can answer with your
context instead of generic advice.

Design constraints that come from the same principles as the rest of the app:

* **Local and read-only.** You point it at a folder; it reads text files, and
  nothing leaves the machine. It never writes into your notes.
* **Incremental.** A file is re-chunked only when its mtime or size changed, so
  pointing it at a large vault stays cheap.
* **Bounded.** File size, file count and chunk count are capped; a stray 2 GB
  log cannot wedge the index.
* **Retrieval is lexical, and says so.** Token overlap with a small stop list —
  no embedding model, no network. It is honest about being a first version;
  `VISION.md` names embeddings as the upgrade path.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

#: Text files worth indexing. Anything else is skipped rather than sniffed.
TEXT_SUFFIXES = frozenset({
    ".md", ".markdown", ".txt", ".org", ".rst", ".textile",
    ".py", ".js", ".ts", ".rs", ".go", ".sh", ".sql", ".toml", ".yaml", ".yml",
    ".json", ".csv",
})

#: Caps, so a repository cannot turn into a 10-minute index.
MAX_FILE_BYTES = 256 * 1024
MAX_FILES = 800
MAX_CHUNKS = 6000

CHUNK_CHARS = 900
CHUNK_OVERLAP = 120

#: How much retrieved text may be injected into one turn.
CONTEXT_BUDGET = 1200

#: Chunks injected per turn.
CONTEXT_CHUNKS = 3

_STOP = frozenset("""
a an and are as at be but by can do does for from has have how i if in into is
it its me my of on or our so than that the their them then there these they
this to was we were what when where which who why will with you your
""".split())

_WORD = re.compile(r"[A-Za-z0-9_'-]{2,}")


def data_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME")
                or (Path.home() / ".local" / "share"))
    for candidate in (base / "mantel", Path(__file__).resolve().parent.parent
                      / ".data"):
        try:
            (candidate / "knowledge").mkdir(parents=True, exist_ok=True)
            probe = candidate / "knowledge" / ".write-probe"
            probe.write_text("")
            probe.unlink()
            return candidate
        except OSError:
            continue
    import tempfile  # noqa: PLC0415

    return Path(tempfile.mkdtemp(prefix="mantel-knowledge-"))


def index_path() -> Path:
    return data_dir() / "knowledge" / "index.json"


def sources_path() -> Path:
    return data_dir() / "knowledge" / "sources.json"


@dataclass
class Chunk:
    path: str
    text: str
    ordinal: int = 0

    def to_json(self) -> dict:
        return {"path": self.path, "text": self.text, "ordinal": self.ordinal}


# --- sources ----------------------------------------------------------------

def sources() -> list[str]:
    try:
        raw = json.loads(sources_path().read_text())
    except (OSError, ValueError):
        return []
    if isinstance(raw, dict):
        raw = raw.get("paths", [])
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if isinstance(item, str) and item]


def _write_sources(paths: list[str]) -> bool:
    try:
        path = sources_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"paths": paths}, indent=1))
        tmp.replace(path)
        return True
    except OSError:
        return False


def add_source(path: str) -> bool:
    path = str(path).strip()
    if not path:
        return False
    expanded = str(Path(os.path.expanduser(path)))
    if not Path(expanded).exists():
        return False
    paths = sources()
    if expanded in paths:
        return True
    paths.append(expanded)
    return _write_sources(paths) and sync()


def remove_source(path: str) -> bool:
    expanded = str(Path(os.path.expanduser(str(path))))
    paths = sources()
    if expanded not in paths:
        return False
    changed = _write_sources([item for item in paths if item != expanded])
    if changed:
        sync()
    return changed


# --- the index --------------------------------------------------------------

def _read_index() -> dict:
    try:
        raw = json.loads(index_path().read_text())
    except (OSError, ValueError):
        return {"files": {}}
    if not isinstance(raw, dict) or not isinstance(raw.get("files"), dict):
        return {"files": {}}
    return raw


def _write_index(index: dict) -> bool:
    try:
        path = index_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(index))
        tmp.replace(path)
        return True
    except OSError:
        return False


def _candidate_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    found: list[Path] = []
    for folder, dirnames, filenames in os.walk(root):
        # skip the usual noise instead of indexing it
        dirnames[:] = [name for name in dirnames
                       if name not in (".git", "node_modules", ".venv",
                                       "__pycache__", "dist", "build",
                                       ".cache", ".obsidian")]
        for name in filenames:
            path = Path(folder) / name
            if path.suffix.lower() in TEXT_SUFFIXES:
                found.append(path)
            if len(found) >= MAX_FILES:
                return found
    return found


def chunk_text(text: str) -> list[str]:
    """Split a document into overlapping windows on paragraph boundaries."""
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text) and len(chunks) < 400:
        end = min(len(text), start + CHUNK_CHARS)
        if end < len(text):
            # prefer a paragraph break near the end of the window
            window = text[start:end]
            cut = window.rfind("\n\n")
            if cut > CHUNK_CHARS // 2:
                end = start + cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def sync(*, force: bool = False) -> dict:
    """Bring the index up to date with the configured sources.

    Returns {"files": n, "chunks": n, "added": n, "removed": n, "ms": n}.
    """
    started = time.monotonic()
    index = _read_index()
    known: dict = index.get("files", {})
    seen: set[str] = set()
    added = removed = 0

    for source in sources():
        root = Path(source)
        if not root.exists():
            continue
        for path in _candidate_files(root):
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size > MAX_FILE_BYTES:
                continue
            key = str(path)
            seen.add(key)
            stamp = f"{stat.st_mtime_ns}:{stat.st_size}"
            previous = known.get(key) or {}
            if not force and previous.get("stamp") == stamp:
                continue
            try:
                text = path.read_text(errors="replace")
            except OSError:
                continue
            chunks = chunk_text(text)
            if not chunks:
                known.pop(key, None)
                continue
            known[key] = {
                "stamp": stamp,
                "chunks": [Chunk(key, piece, ordinal).to_json()
                           for ordinal, piece in enumerate(chunks)],
            }
            added += 1

    for key in list(known):
        if key not in seen:
            known.pop(key)
            removed += 1

    # trim to the chunk cap, newest files kept
    total = sum(len(entry.get("chunks", [])) for entry in known.values())
    if total > MAX_CHUNKS and known:
        for key in sorted(known, key=lambda name: known[name].get("stamp", "")):
            if total <= MAX_CHUNKS:
                break
            total -= len(known[key].get("chunks", []))
            known.pop(key)
            removed += 1

    index["files"] = known
    index["synced"] = time.time()
    _write_index(index)

    return {
        "files": len(known),
        "chunks": sum(len(entry.get("chunks", [])) for entry in known.values()),
        "added": added, "removed": removed,
        "ms": int((time.monotonic() - started) * 1000),
    }


def stats() -> dict:
    index = _read_index()
    files = index.get("files", {})
    return {
        "files": len(files),
        "chunks": sum(len(entry.get("chunks", [])) for entry in files.values()),
        "synced": float(index.get("synced") or 0),
    }


# --- retrieval --------------------------------------------------------------

def tokens(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.lower()) if word not in _STOP}


#: Shortest prefix worth matching, so "de" does not match "deploy".
MIN_STEM = 4


def _covered(wanted: str, present: set[str]) -> bool:
    """True when a query word appears, allowing simple suffixes and compounds.

    "deploy" covers "deploys"/"deployment"; "roll" covers "rollback". There is
    no real stemmer here — this is the smallest rule that keeps a lexical index
    from failing on plurals, and the vision names embeddings as the upgrade.
    """
    if wanted in present:
        return True
    if len(wanted) < MIN_STEM:
        return False
    return any(word.startswith(wanted) or wanted.startswith(word)
               for word in present if len(word) >= MIN_STEM)


def search(query: str, *, limit: int = CONTEXT_CHUNKS) -> list[Chunk]:
    """The most relevant chunks for a query, best first."""
    wanted = tokens(query)
    if not wanted:
        return []
    index = _read_index()
    scored: list[tuple[float, Chunk]] = []
    seen: dict[str, int] = {}

    for path, entry in index.get("files", {}).items():
        for row in entry.get("chunks", []):
            if not isinstance(row, dict):
                continue
            text = str(row.get("text") or "")
            if not text:
                continue
            present = tokens(text)
            overlap = sum(1 for word in wanted if _covered(word, present))
            if not overlap:
                continue
            # reward covering the query, not just repeating one rare word
            score = overlap / len(wanted)
            scored.append((score, Chunk(path, text,
                                        int(row.get("ordinal") or 0))))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    out: list[Chunk] = []
    for _score, chunk in scored:
        if seen.get(chunk.path, 0) >= 2:      # at most two chunks per document
            continue
        seen[chunk.path] = seen.get(chunk.path, 0) + 1
        out.append(chunk)
        if len(out) >= limit:
            break
    return out


def context_block(query: str, *, budget: int = CONTEXT_BUDGET) -> str:
    """Text injected before a turn: relevant passages from the user's notes."""
    chunks = search(query)
    if not chunks:
        return ""
    lines = ["Relevant notes from the user's own files (cite the path when you "
             "use them):", ""]
    used = len("\n".join(lines))
    for chunk in chunks:
        name = Path(chunk.path).name
        snippet = " ".join(chunk.text.split())
        if len(snippet) > 400:
            snippet = snippet[:400] + "…"
        entry = f"- {name}: {snippet}"
        if used + len(entry) > budget:
            break
        lines.append(entry)
        used += len(entry) + 1
    if len(lines) <= 2:
        return ""
    return "\n".join(lines) + "\n\n"


def clear() -> bool:
    return _write_index({"files": {}}) and _write_sources([])
