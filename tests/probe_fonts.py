"""Probe: confirm bundled fonts + Luminous Symbols icons actually resolve."""
from __future__ import annotations

import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from harness import shoot  # noqa: E402
from app import theme  # noqa: E402


def build() -> Gtk.Widget:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    for m in ("top", "bottom", "start", "end"):
        getattr(box, f"set_margin_{m}")(32)

    t = Gtk.Label(label="Gemini", xalign=0)
    t.add_css_class("hero")
    box.append(t)

    box.append(
        Gtk.Label(
            label="Google Sans Flex — the app's own UI typeface", xalign=0,
            css_classes=["hero-sub"],
        )
    )
    box.append(
        Gtk.Label(
            label="Google Sans Text — used for message bodies at 14.5px", xalign=0
        )
    )

    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
    names = [
        "chat_spark", "add", "search", "send", "settings", "mic",
        "image", "attach_file", "arrow_upward", "more_vert",
        "check_circle", "person", "edit", "content_copy", "history",
    ]
    for n in names:
        cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        cell.append(theme.icon(n, 22))
        cap = Gtk.Label(label=n)
        cap.add_css_class("status-dot")
        cell.append(cap)
        row.append(cell)
    box.append(row)

    row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
    for n in ["chat_spark", "star", "bookmark", "favorite"]:
        for filled in (False, True):
            row2.append(theme.icon(n, 26, filled=filled))
    box.append(row2)

    code = Gtk.Label(label="Google Sans Code — monospace", xalign=0)
    code.add_css_class("codeblock")
    box.append(code)
    return box


if __name__ == "__main__":
    out = ROOT / "tests" / "out" / "fonts.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    raise SystemExit(
        shoot(build, str(out), 1000, 520, app_id="dev.gemini.fontprobe", setup=theme.install)
    )
