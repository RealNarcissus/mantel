"""Gemini for Linux — native GTK4 client.

Entry point. `--smoke` builds the real window and renders it offscreen to a
PNG, which is how the UI is verified on hosts with no capturable compositor.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from app import fonts_env  # noqa: F401,E402  (must precede Pango init)

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from app import engine as engine_mod, theme  # noqa: E402
from app.quickchat import QuickChat  # noqa: E402
from app.store import Store  # noqa: E402
from app.window import Window  # noqa: E402

APP_ID = "dev.mantel.MantelDesktop"


def _set_app_icon() -> None:
    icon = theme.ASSETS / "icons" / "appicon.png"
    if icon.is_file():
        try:
            Gtk.Window.set_default_icon_name(str(icon))
        except Exception:  # noqa: BLE001
            pass


def _parse_size(text: str) -> tuple[int, int]:
    try:
        w, h = text.lower().replace("x", " ").split()
        return int(w), int(h)
    except Exception:  # noqa: BLE001
        return 1440, 940


class Application(Adw.Application):
    def __init__(self, workspace: str = "", smoke: str = "", demo: bool = False,
                 smoke_prompt: str = "", quick: bool = False, page: str = "home",
                 scheme: str = "light", size: tuple[int, int] = (1440, 940)):
        super().__init__(application_id=APP_ID, flags=0)
        self.workspace = workspace
        self.smoke = smoke
        self.demo = demo
        self.smoke_prompt = smoke_prompt
        self.quick = quick
        self.page = page
        self.scheme = scheme
        self.size = size
        self.engine = engine_mod.Engine()
        self.store = Store()

    def do_activate(self) -> None:
        theme.install()
        _set_app_icon()
        if self.quick:
            overlay = QuickChat(self, self.engine, workspace=self.workspace)
            overlay.summon()
            if self.smoke:
                # the overlay is its own size; render it at that size
                GLib.timeout_add(1200, lambda: self._smoke(overlay, own_size=True))
            return
        window = Window(self, self.engine, self.store, workspace=self.workspace,
                        page=self.page, scheme=self.scheme, size=self.size,
                        animate=not self.smoke, demo=self.demo)
        # With no compositor the window takes the virtual screen's size, so
        # the requested geometry has to be forced for an exact comparison.
        window.set_size_request(*self.size)
        window.present()
        if self.demo:
            window.load_demo()
        if self.smoke and self.smoke_prompt:
            window.composer.view.get_buffer().set_text(self.smoke_prompt)
            window.composer.view.set_opacity(1.0)
            GLib.timeout_add(400, lambda: self._run_smoke_prompt(window))
        elif self.smoke:
            GLib.timeout_add(1500, lambda: self._smoke(window))

    def _run_smoke_prompt(self, window) -> bool:
        window.submit(self.smoke_prompt)
        self._wait_turn(window, 0)
        return False

    def _wait_turn(self, window, elapsed_ms: int) -> bool:
        if window.turn is not None and elapsed_ms < 240_000:
            GLib.timeout_add(500, lambda: self._wait_turn(window, elapsed_ms + 500))
            return False
        GLib.timeout_add(1200, lambda: self._smoke(window))
        return False

    def _smoke(self, window, own_size: bool = False) -> bool:
        from tests.harness import render_to_png
        from gi.repository import GLib as _GLib

        # one more frame so the forced resize has been laid out
        _GLib.timeout_add(250, lambda: (self._smoke_now(window, own_size), False)[1])
        return False

    def _smoke_now(self, window, own_size: bool = False) -> None:
        from tests.harness import render_to_png

        # Force the window to the requested size: with no compositor the
        # window otherwise takes the virtual screen's size, which would not
        # match the reference geometry.  The overlay sizes itself.
        if own_size:
            width, height = window.get_width(), window.get_height()
        else:
            width, height = self.size
        ok, how = render_to_png(window, self.smoke, width, height)
        print(f"SMOKE ok={ok} {width}x{height} how={how} -> {self.smoke}")
        self.quit()
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gemini-desktop", description=__doc__)
    ap.add_argument("--workspace", "-w", default="",
                    help="folder the agent works in (default: $HOME)")
    ap.add_argument("--smoke", default="",
                    help="render the window offscreen to this PNG and exit")
    ap.add_argument("--version", action="store_true")
    ap.add_argument("--quick", action="store_true",
                    help="show only the quick-chat overlay (for a global keybind)")
    ap.add_argument("--smoke-prompt", default="",
                    help="submit this prompt, wait for the turn, then render")
    ap.add_argument("--demo", action="store_true",
                    help="fill the transcript with sample content (UI check)")
    ap.add_argument("--page", default="home",
                    choices=("home", "chat", "tasks", "schedule",
                             "connectors", "skills", "account",
                             "settings", "create"),
                    help="which page to open on start")
    ap.add_argument("--scheme", default="light",
                    choices=("light", "dark", "system"),
                    help="colour scheme")
    ap.add_argument("--size", default="1440x940",
                    help="window size, e.g. 1744x1168")
    args = ap.parse_args(argv)

    if args.version:
        print("mantel 1.0")
        return 0

    app = Application(workspace=args.workspace, smoke=args.smoke, demo=args.demo,
                      smoke_prompt=args.smoke_prompt, quick=args.quick,
                      page=args.page, scheme=args.scheme,
                      size=_parse_size(args.size))
    return app.run([])


if __name__ == "__main__":
    raise SystemExit(main())
