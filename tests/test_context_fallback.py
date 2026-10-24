"""The conversation context fallback.

The engine keeps a thread itself via `--conversation <id>`. When it cannot —
a read-only home, a pruned store — it silently starts a *new* conversation
and returns a different id. `Window` notices that and replays the recent
turns inline on the next request. This checks that replay is built correctly
and bounded.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import fonts_env  # noqa: F401

from app.store import Conversation, Message  # noqa: E402


def history_prefix(conv, turns=8) -> str:
    """Mirror of Window._history_prefix, without needing a GUI."""
    selected = [m for m in conv.messages if m.role in ("user", "assistant")
                and (m.text or "").strip()][-turns:]
    if not selected:
        return ""
    lines = ["Conversation so far, for context:"]
    for message in selected:
        speaker = "User" if message.role == "user" else "Assistant"
        body = " ".join(message.text.split())
        if len(body) > 600:
            body = body[:600] + "…"
        lines.append(f"{speaker}: {body}")
    lines.append("")
    lines.append("Now answer the next message, using the context above.")
    lines.append("")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    failures: list[str] = []

    empty = Conversation()
    if history_prefix(empty) != "":
        failures.append("an empty conversation should produce no prefix")
    print("  empty conversation -> no prefix")

    conv = Conversation()
    conv.add("user", "Remember the number 417.")
    conv.add("assistant", "Understood.")
    conv.add("user", "What number?")
    conv.add("assistant", "417.")
    prefix = history_prefix(conv)
    print(f"  prefix:\n{prefix}")
    if "User: Remember the number 417." not in prefix:
        failures.append("the first user turn is missing")
    if "Assistant: 417." not in prefix:
        failures.append("the last assistant turn is missing")
    if not prefix.endswith("\n\n"):
        failures.append("the prefix should end with a blank line")

    # only the most recent turns are resent
    long_conv = Conversation()
    for i in range(20):
        long_conv.add("user", f"question {i}")
        long_conv.add("assistant", f"answer {i}")
    bounded = history_prefix(long_conv)
    if "question 0" in bounded:
        failures.append("old turns were not trimmed")
    if "answer 19" not in bounded:
        failures.append("the newest turn is missing")
    resent = bounded.count("User: ")
    print(f"  bounded to {resent} user turns out of 20")
    if resent > 8:
        failures.append(f"{resent} turns resent, expected at most 8")

    # a huge message is truncated rather than blowing the window
    huge = Conversation()
    huge.add("user", "x" * 5000)
    if len(history_prefix(huge)) > 1200:
        failures.append("a huge turn was not truncated")
    print(f"  huge turn truncated to {len(history_prefix(huge))} chars")

    # whitespace-only turns are skipped
    sparse = Conversation()
    sparse.add("user", "   ")
    sparse.add("assistant", "")
    sparse.add("user", "real question")
    if history_prefix(sparse).count("User:") != 1:
        failures.append("blank turns were included")
    print("  blank turns skipped")

    print()
    if failures:
        for f in failures:
            print(f"  FAIL: {f}")
        return 1
    print("  context fallback: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
