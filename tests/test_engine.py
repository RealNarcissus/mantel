"""End-to-end check of the engine bridge (no GUI).

Runs a real turn through app.engine.Engine and prints the streamed events, so
the streaming path can be verified independently of the window.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import fonts_env  # noqa: F401,E402

import gi  # noqa: E402

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from app import engine as engine_mod  # noqa: E402


def main() -> int:
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Reply with exactly: BRIDGE-OK"
    model = sys.argv[2] if len(sys.argv) > 2 else "gemini-3.8-flash-low"

    eng = engine_mod.Engine()
    print(f"binary: {eng.binary}")
    print(f"available: {eng.available}")
    if not eng.available:
        return 2
    print(f"models: {[m for m, _ in eng.models()]}")

    loop = GLib.MainLoop()
    state = {"deltas": 0, "chars": 0, "tools": 0}

    turn = eng.run(prompt=prompt, model=model, cwd=str(ROOT))

    turn.connect("started", lambda _t, cid: print(f"[started] engine conversation {cid}"))
    turn.connect("tool", lambda _t, n, d: (state.__setitem__("tools", state["tools"] + 1),
                                           print(f"[tool] {n} {d}")))
    turn.connect("thought", lambda _t, d: print(f"[thought] {d!r}"))

    def on_delta(_t, d):
        state["deltas"] += 1
        state["chars"] += len(d)
        print(f"[delta] {d!r}")

    def on_finished(_t, result):
        print(f"[finished] status={result.get('status')} "
              f"text={result.get('text')!r} duration={result.get('duration'):.1f}s")
        print(f"[usage] {result.get('usage')}")
        print(f"[summary] deltas={state['deltas']} chars={state['chars']} "
              f"tools={state['tools']}")
        loop.quit()

    def on_failed(_t, message):
        print(f"[failed] {message}")
        loop.quit()

    turn.connect("delta", on_delta)
    turn.connect("finished", on_finished)
    turn.connect("failed", on_failed)

    GLib.timeout_add_seconds(180, lambda: (print("[timeout]"), turn.cancel(),
                                           loop.quit(), False)[3])
    loop.run()
    return 0 if state["chars"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
