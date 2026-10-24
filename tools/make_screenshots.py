#!/usr/bin/env python3
"""Regenerate the screenshots in `docs/screenshots/` from the real widget tree.

The development loop has no capturable compositor, so every screenshot in this
repo is an offscreen render of the actual GTK4 tree through GSK's cairo
renderer — the same thing a compositor would be handed. Running this script is
how those images were produced; nothing is mocked up by hand.

    python3 tools/make_screenshots.py [--out docs/screenshots]

Every frame uses `--demo` data (a neutral identity, sample conversations, no
engine calls), so the images never contain a real account, e-mail or path.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import fonts_env  # noqa: F401,E402  (must precede Pango init)

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from app import engine as engine_mod  # noqa: E402
from app import store as store_mod  # noqa: E402
from app import theme  # noqa: E402
from tests.harness import render_to_png  # noqa: E402

#: The application is measured in this space (see docs/DESIGN.md).
WIDTH, HEIGHT = 1744, 1168

#: Pages to capture, in the order they should appear in the docs.
PAGES = ("home", "chat", "tasks", "create", "schedule", "connectors",
         "skills", "settings")


def _make_window(application, *, page: str, scheme: str = "light"):
    """A window in demo mode, with the engine stubbed out."""
    from app.window import Window  # noqa: PLC0415

    window = Window(application, engine_mod.Engine(), store_mod.Store(),
                    page=page, scheme=scheme, size=(WIDTH, HEIGHT),
                    animate=False, demo=True)
    window.set_size_request(WIDTH, HEIGHT)
    window.present()
    window.load_demo()
    return window


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "docs" / "screenshots"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    application = Adw.Application(application_id="dev.gemini.Screenshots")
    failures: list[str] = []

    def activate(app):
        theme.install()
        # hold the application open: without a window at the start of the
        # sequence the main loop would exit before the timers fire
        app.hold()
        jobs = [(page, "light") for page in PAGES]
        jobs.append(("home", "dark"))
        jobs.append(("quick", "light"))
        queue = list(jobs)

        def step():
            """Build one window, let it draw, capture, then move on."""
            if not queue:
                app.release()
                app.quit()
                return False
            page, scheme = queue.pop(0)
            name = "quickchat" if page == "quick" else (
                page if scheme == "light" else "dark")

            if page == "quick":
                from app.quickchat import QuickChat  # noqa: PLC0415

                target = QuickChat(app, engine_mod.Engine())
                target.set_default_size(720, 420)
                target.present()
            else:
                target = _make_window(app, page=page, scheme=scheme)

            def capture():
                ok, detail = render_to_png(target, str(out / f"{name}.png"),
                                           WIDTH, HEIGHT)
                print(f"  {name:14} {'ok' if ok else detail}")
                if not ok:
                    failures.append(f"{name}: {detail}")
                target.destroy()
                step()          # next
                return False

            GLib.timeout_add(600, capture)
            return False

        GLib.timeout_add(400, step)

    application.connect("activate", activate)
    argv = ["make_screenshots"] + sys.argv[1:]
    application.run(argv)

    if failures:
        print("\n  failed:", ", ".join(failures))
        return 1
    print(f"\n  wrote {len(PAGES) + 2} screenshots to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
