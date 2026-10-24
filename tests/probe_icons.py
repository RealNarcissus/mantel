"""Probe: verify the app's real icon font renders through theme.icon()."""
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

GROUPS = {
    "brand / agent": ["gemini_spark", "chat_spark", "search_spark", "pen_spark",
                      "audio_spark", "add_image_spark", "notes_spark", "gem_spark"],
    "composer": ["add", "image", "attach_file", "mic", "send_spark", "arrow_upward",
                 "stop", "more_vert"],
    "nav / ui": ["search", "settings", "person", "edit", "history", "home",
                 "check_circle", "close", "refresh", "delete", "share_2",
                 "content_copy", "download", "folder", "code"],
    "feedback": ["thumb_up", "thumb_down", "star", "bookmark", "translate",
                 "lightbulb", "summarize", "auto_awesome"],
}


def build() -> Gtk.Widget:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
    for m in ("top", "bottom", "start", "end"):
        getattr(root, f"set_margin_{m}")(24)

    for group, names in GROUPS.items():
        root.append(Gtk.Label(label=group.upper(), xalign=0, css_classes=["section-label"]))
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        for n in names:
            cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            pair = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            pair.append(theme.icon(n, 24, filled=False))
            pair.append(theme.icon(n, 24, filled=True))
            cell.append(pair)
            cell.append(Gtk.Label(label=n, css_classes=["status-dot"]))
            row.append(cell)
        root.append(row)

    # type ramp
    ramp = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    for txt, cls in (("Gemini", "hero"), ("Section heading", "md-h1"),
                     ("Body text in Google Sans Text", None),
                     ("code_sample(x)", "md-code")):
        lbl = Gtk.Label(label=txt, xalign=0)
        if cls:
            lbl.add_css_class(cls)
        ramp.append(lbl)
    root.append(ramp)
    # DUMPSHEET: dump the same textures this build() puts on screen
    import gi as _gi
    _gi.require_version('GLib','2.0')
    from gi.repository import GLib as _G
    def _d():
        for _n in ['add','image','mic','attach_file','search']:
            theme.icon_texture(_n, 24).save_to_png(str(ROOT/'tests'/'out'/f'sheet_{_n}.png'))
        print('DUMPSHEET done')
        return False
    _G.timeout_add(200, _d)
    return root


if __name__ == "__main__":
    out = ROOT / "tests" / "out" / "icons_v2.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    raise SystemExit(
        shoot(build, str(out), 1180, 560, app_id="dev.gemini.iconprobe", setup=theme.install)
    )
