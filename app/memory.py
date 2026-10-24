"""Memory: what the agent knows about you, and how you check it.

This is the local-first half of the "the agent should know me" requirement. It
is deliberately not a vector database: it is an inspectable list of facts, a
few honest heuristics for filling it, and a small block of text injected into
the prompt before each turn.

Three rules shape the design:

1. **Every fact is visible and deletable.** A memory you cannot audit is a
   memory you cannot trust, and an untrusted assistant stops being useful the
   first time it is wrong about you.
2. **Facts expire.** "I have an exam tomorrow" is not true next week. Temporal
   facts carry an expiry and are dropped when it passes.
3. **Contradictions replace, they do not accumulate.** "I moved to SF" must
   supersede "I live in NYC", not sit next to it. The old fact is kept as
   superseded so the history is auditable, but it is never injected.

Storage is one JSON file next to the client's other state. A future version can
put a provider interface (local store, Supermemory, …) behind this module
without the rest of the app noticing; see docs/VISION.md §7.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

#: How many characters of memory may be injected into one prompt.
PROFILE_BUDGET = 900

#: Facts older than this without reinforcement are dropped from injection.
SOFT_TTL_DAYS = 180

KINDS = ("preference", "fact", "commitment", "project")
SCOPES = ("all", "work", "personal")


def data_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME")
                or (Path.home() / ".local" / "share"))
    for candidate in (base / "mantel", Path(__file__).resolve().parent.parent
                      / ".data"):
        try:
            (candidate / "memory").mkdir(parents=True, exist_ok=True)
            probe = candidate / "memory" / ".write-probe"
            probe.write_text("")
            probe.unlink()
            return candidate
        except OSError:
            continue
    import tempfile  # noqa: PLC0415

    return Path(tempfile.mkdtemp(prefix="mantel-memory-"))


def store_path() -> Path:
    return data_dir() / "memory" / "memory.json"


@dataclass
class Fact:
    """One thing the agent believes about the user."""

    text: str
    kind: str = "fact"            # one of KINDS
    scope: str = "all"            # all | work | personal
    source: str = "you"           # "you", "conversation", "file:…"
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    reinforced: int = 1           # times seen; used for ranking
    expires: float = 0.0          # 0 = no expiry
    superseded_by: str = ""       # set when replaced by a newer fact

    @property
    def expired(self) -> bool:
        return bool(self.expires) and self.expires < time.time()

    @property
    def live(self) -> bool:
        return not self.expired and not self.superseded_by

    def to_json(self) -> dict:
        return asdict(self)


# --- reading and writing ----------------------------------------------------

def _read() -> list[dict]:
    try:
        raw = json.loads(store_path().read_text())
    except (OSError, ValueError):
        return []
    if isinstance(raw, dict):
        raw = raw.get("facts", [])
    return [item for item in raw if isinstance(item, dict)]


def _write(rows: list[dict]) -> bool:
    try:
        path = store_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, indent=1))
        tmp.replace(path)
        return True
    except OSError:
        return False


def facts(*, include_dead: bool = False) -> list[Fact]:
    """Every fact, newest first. Dead facts only when asked for."""
    out: list[Fact] = []
    for row in _read():
        known = {k: v for k, v in row.items() if k in Fact.__dataclass_fields__}
        try:
            fact = Fact(**known)
        except TypeError:
            continue
        if include_dead or fact.live:
            out.append(fact)
    out.sort(key=lambda item: item.updated, reverse=True)
    return out


# --- tokenising and similarity ---------------------------------------------

_STOP = frozenset("""
a an and are as at be but by for from has have i if in into is it its me my
of on or our so that the their them then there these they this to was we were
what when where which who will with you your
""".split())

_WORD = re.compile(r"[a-z0-9']+")

#: Facts that can only have one value at a time. Two statements in the same
#: slot contradict by definition, whatever their wording — "I live in NYC"
#: says nothing lexically shared with "I moved to SF".
_SLOTS = (
    ("residence", re.compile(
        r"\b(?:i live in|i'?m living in|i moved to|i'?m moving to|"
        r"i am moving to)\s+(.{2,60})", re.I)),
    ("employer", re.compile(r"\bi work (?:at|for)\s+(.{2,60})", re.I)),
    ("role", re.compile(r"\bi(?:'m| am) (?:a|an) (.{2,60}?) "
                        r"(?:at|who|and|$)", re.I)),
)


def slot_of(text: str) -> tuple[str, str] | None:
    """(slot, value) when a fact occupies a single-valued slot."""
    for name, pattern in _SLOTS:
        match = pattern.search(text)
        if match:
            return name, " ".join(match.group(1).split()).lower()
    return None


def tokens(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.lower()) if word not in _STOP}


def similar(left: str, right: str) -> float:
    """Jaccard overlap, used to spot a contradiction or a duplicate."""
    a, b = tokens(left), tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _temporal_expiry(text: str) -> float:
    """A crude expiry for facts that are only true for a moment."""
    lowered = text.lower()
    now = time.time()
    if "tomorrow" in lowered:
        return now + 2 * 86400
    if "today" in lowered or "tonight" in lowered:
        return now + 86400
    match = re.search(r"next (week|month)", lowered)
    if match:
        return now + (14 if match.group(1) == "week" else 45) * 86400
    return 0.0


# --- writing ----------------------------------------------------------------

def remember(text: str, *, kind: str = "fact", scope: str = "all",
             source: str = "you") -> Fact | None:
    """Store a fact, replacing near-duplicates and contradictions.

    Returns the new fact, or None when there was nothing worth keeping.
    """
    text = " ".join(str(text).split()).strip()
    if len(text) < 3 or len(text) > 280:
        return None
    if kind not in KINDS:
        kind = "fact"
    if scope not in SCOPES:
        scope = "all"

    rows = _read()
    new = Fact(text=text, kind=kind, scope=scope, source=source,
               expires=_temporal_expiry(text))

    new_slot = slot_of(text)

    for row in rows:
        if row.get("superseded_by") or row.get("id") in ("", None):
            continue
        other = str(row.get("text", ""))
        if row.get("kind") != kind or row.get("scope") != scope:
            continue

        # a single-valued slot contradicts by definition
        other_slot = slot_of(other)
        if (new_slot and other_slot and new_slot[0] == other_slot[0]
                and new_slot[1] != other_slot[1]):
            row["superseded_by"] = new.id
            row["updated"] = time.time()
            continue

        score = similar(text, other)
        if score >= 0.82:
            # the same thing said again: reinforce rather than duplicate
            row["reinforced"] = int(row.get("reinforced", 1)) + 1
            row["updated"] = time.time()
            row["text"] = text if len(text) > len(other) else other
            _write(rows)
            return Fact(**{k: v for k, v in row.items()
                           if k in Fact.__dataclass_fields__})
        if score >= 0.45 and _contradicts(text, other):
            # a newer statement about the same subject: supersede the old one
            row["superseded_by"] = new.id
            row["updated"] = time.time()

    rows.append(new.to_json())
    _write(rows)
    return new


def _contradicts(newer: str, older: str) -> bool:
    """Do these read as two statements about the same thing?

    Heuristic: they share a subject token but differ in the predicate. "I live
    in NYC" vs "I moved to SF" share nothing lexically, so the caller also
    passes `similar`; this guard keeps unrelated pairs apart.
    """
    shared = tokens(newer) & tokens(older)
    if not shared:
        return False
    return bool(shared - {"love", "like", "prefer", "use", "work"})


def forget(fact_id: str) -> bool:
    rows = _read()
    kept = [row for row in rows if row.get("id") != fact_id]
    if len(kept) == len(rows):
        return False
    return _write(kept)


def prune() -> int:
    """Drop expired facts and old unreinforced ones. Returns how many went."""
    rows = _read()
    cutoff = time.time() - SOFT_TTL_DAYS * 86400
    kept = []
    for row in rows:
        expires = float(row.get("expires") or 0)
        updated = float(row.get("updated") or row.get("created") or 0)
        if expires and expires < time.time():
            continue
        if not expires and updated < cutoff and int(row.get("reinforced", 1)) <= 1:
            continue
        kept.append(row)
    if len(kept) != len(rows):
        _write(kept)
    return len(rows) - len(kept)


def clear() -> bool:
    return _write([])


# --- reading back -----------------------------------------------------------

def search(query: str, *, scope: str = "all", limit: int = 8) -> list[Fact]:
    """Facts relevant to a query, best first (relevance × recency × weight)."""
    wanted = tokens(query)
    now = time.time()
    scored: list[tuple[float, Fact]] = []
    for fact in facts():
        if scope != "all" and fact.scope not in ("all", scope):
            continue
        overlap = len(wanted & tokens(fact.text)) if wanted else 0
        if wanted and not overlap:
            continue
        age_days = max(0.0, now - fact.updated) / 86400
        recency = 1.0 / (1.0 + age_days / 30.0)
        score = (overlap or 1) * recency * (1 + 0.15 * fact.reinforced)
        scored.append((score, fact))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [fact for _score, fact in scored[:limit]]


def profile_block(*, scope: str = "all", budget: int = PROFILE_BUDGET) -> str:
    """The text injected before a turn so the agent knows who it is talking to."""
    live = [fact for fact in facts()
            if scope == "all" or fact.scope in ("all", scope)]
    if not live:
        return ""
    live.sort(key=lambda fact: (fact.reinforced, fact.updated), reverse=True)
    lines = ["What you know about the user, from earlier sessions:", ""]
    for fact in live:
        line = f"- {fact.text}"
        if fact.kind != "fact":
            line += f"  ({fact.kind})"
        if len("\n".join(lines + [line])) > budget:
            break
        lines.append(line)
    if len(lines) <= 2:
        return ""
    lines += ["", "Use this only where it helps; do not recite it back."]
    return "\n".join(lines) + "\n\n"


# --- filling it without asking the user ------------------------------------

_CLAUSE = r"(.*?)(?=\s+(?:and|but|so|because)\b|[.;!?]|$)"

_PATTERNS = (
    (re.compile(r"\b(?:remember|note) that\s+(.+?)(?:[.;!?]|$)", re.I), "fact"),
    (re.compile(r"\bi (?:prefer|like|love|hate|avoid)\b" + _CLAUSE, re.I),
     "preference"),
    (re.compile(r"\bi(?:'m| am) (?:working on|building)\s+" + _CLAUSE, re.I),
     "project"),
    (re.compile(r"\bi(?:'ll| will) (?:send|finish|do|review|reply|write)\b"
                + _CLAUSE, re.I), "commitment"),
)


def candidates_from(text: str) -> list[tuple[str, str]]:
    """(kind, fact) pairs worth remembering from a user message.

    Deliberately conservative: an assistant that remembers everything remembers
    nothing useful, and a wrong memory is worse than a missing one.
    """
    found: list[tuple[str, str]] = []
    for pattern, kind in _PATTERNS:
        for match in pattern.finditer(text):
            phrase = match.group(0).strip().rstrip(".,;!")
            if 6 <= len(phrase) <= 200:
                found.append((kind, phrase))
    return found


def capture(text: str, *, scope: str = "all") -> list[Fact]:
    """Remember what is worth remembering from one user message."""
    saved = []
    for kind, phrase in candidates_from(text):
        fact = remember(phrase, kind=kind, scope=scope, source="conversation")
        if fact is not None:
            saved.append(fact)
    return saved
