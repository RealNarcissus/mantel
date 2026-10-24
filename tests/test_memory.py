"""Tests for Memory v1.

The interesting behaviour is not "it stores a string" but the judgement calls:
duplicates are reinforced rather than repeated, contradictions supersede, stale
facts expire, and the injected block stays inside its budget.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import fonts_env  # noqa: F401,E402

from app import memory  # noqa: E402


def fresh() -> None:
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="mantel-memory-")
    memory.clear()


def main() -> int:
    failures: list[str] = []
    fresh()

    # --- storing and listing ---------------------------------------------
    fact = memory.remember("Prefers deep work before noon", kind="preference")
    print(f"  stored: {fact.text if fact else None}")
    if fact is None:
        failures.append("a plain fact was rejected")
    if len(memory.facts()) != 1:
        failures.append("the fact did not round-trip")

    for bad in ("", "  ", "x" * 400):
        if memory.remember(bad) is not None:
            failures.append(f"accepted a bad fact: {bad[:20]!r}")

    # --- duplicates are reinforced, not repeated -------------------------
    memory.remember("Prefers deep work before noon", kind="preference")
    stored = memory.facts()
    print(f"  after duplicate: {len(stored)} fact(s), "
          f"reinforced={stored[0].reinforced if stored else 0}")
    if len(stored) != 1:
        failures.append(f"a duplicate created a second fact: {len(stored)}")
    elif stored[0].reinforced < 2:
        failures.append("a duplicate did not reinforce the original")

    # --- contradictions supersede ---------------------------------------
    memory.remember("I live in New York", kind="fact")
    memory.remember("I moved to San Francisco", kind="fact")
    live = [f.text for f in memory.facts()]
    dead = [f.text for f in memory.facts(include_dead=True) if not f.live]
    print(f"  contradiction -> live={live} superseded={dead}")
    if not any("San Francisco" in text for text in live):
        failures.append("the newer fact was not stored")
    if any("New York" in text for text in live):
        failures.append("the superseded fact is still injected")
    if not dead:
        failures.append("the old fact was deleted instead of superseded")

    # --- expiry ----------------------------------------------------------
    memory.clear()
    memory.remember("I have an exam tomorrow", kind="fact")
    expiring = memory.facts()[0]
    print(f"  expiry set for a temporal fact: {bool(expiring.expires)}")
    if not expiring.expires:
        failures.append("a temporal fact got no expiry")
    expiring.expires = time.time() - 10     # pretend it passed
    rows = memory._read()                    # noqa: SLF001
    for row in rows:
        if row.get("text", "").startswith("I have an exam"):
            row["expires"] = expiring.expires
    memory._write(rows)                      # noqa: SLF001
    if memory.facts():
        failures.append("an expired fact is still live")
    print(f"  expired facts pruned: {memory.prune()}")

    # --- search and profile budget --------------------------------------
    memory.clear()
    memory.remember("Prefers deep work before noon", kind="preference")
    memory.remember("Works on the Mantel project", kind="project")
    memory.remember("Uses Neovim", kind="preference")
    hits = memory.search("deep work")
    print(f"  search('deep work') -> {[f.text for f in hits]}")
    if not hits or "deep work" not in hits[0].text:
        failures.append(f"search did not rank the right fact: {hits}")
    if memory.search("astrophysics"):
        failures.append("search returned facts for an unrelated query")

    for index in range(40):
        memory.remember(f"Filler fact number {index} about nothing much",
                        kind="fact")
    block = memory.profile_block(budget=400)
    print(f"  profile block: {len(block)} chars (budget 400)")
    if len(block) > 400:
        failures.append(f"the profile block exceeded its budget: {len(block)}")
    if "What you know about the user" not in block:
        failures.append("the profile block lost its heading")

    # a scope that excludes the only facts yields no block
    memory.clear()
    memory.remember("Work secret", kind="fact", scope="work")
    if memory.profile_block(scope="personal"):
        failures.append("a personal turn saw a work-scoped fact")

    # --- forgetting ------------------------------------------------------
    memory.clear()
    kept = memory.remember("Prefers tea", kind="preference")
    doomed = memory.remember("Uses Neovim", kind="preference")
    if not memory.forget(doomed.id):
        failures.append("forget() reported failure for a real fact")
    remaining = [f.text for f in memory.facts()]
    print(f"  after forget: {remaining}")
    if any("Neovim" in text for text in remaining):
        failures.append("a forgotten fact is still there")
    if not any("tea" in text for text in remaining):
        failures.append("forget() removed the wrong fact")
    if memory.forget("does-not-exist"):
        failures.append("forget() claimed to remove a missing fact")

    # --- capture heuristics ---------------------------------------------
    memory.clear()
    found = memory.capture("I prefer oat milk and I am working on a Rust CLI")
    kinds = sorted({fact.kind for fact in found})
    print(f"  captured: {[(f.kind, f.text) for f in found]}")
    if not found:
        failures.append("no facts were captured from an obvious message")
    if "preference" not in kinds:
        failures.append("a stated preference was not captured")
    if "project" not in kinds:
        failures.append("an ongoing project was not captured")
    if memory.capture("what is the capital of France?"):
        failures.append("a question was turned into a memory")

    # --- injection into a turn ------------------------------------------
    memory.clear()
    memory.remember("Prefers deep work before noon", kind="preference")
    from app import engine as engine_mod  # noqa: PLC0415
    from app import session as session_mod  # noqa: PLC0415

    engine = engine_mod.Engine(adapter="legacy")
    sess = session_mod.Session(engine, mode=session_mod.MODE_TASK)
    prompt = sess.brief("What should I work on?")
    print(f"  injected prompt:\n{prompt}")
    if "What you know about the user" not in prompt:
        failures.append("memory was not injected into the turn")
    if "deep work before noon" not in prompt:
        failures.append("the fact itself was not injected")
    if not prompt.rstrip().endswith("What should I work on?"):
        failures.append("the user's prompt should come last")

    sess.use_memory = False
    if "What you know about the user" in sess.brief("hi"):
        failures.append("memory injection could not be turned off")

    # --- a corrupt store reads as empty ---------------------------------
    memory.store_path().write_text("{not json")
    if memory.facts():
        failures.append("a corrupt store should read as empty")
    print("  corrupt store reads as empty")

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        return 1
    print("  memory: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
