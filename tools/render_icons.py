"""Pre-render every icon glyph to a PNG.

Runtime glyph rasterisation through GTK/Pango proved non-deterministic across
processes: the same family, codepoint and size produced correct icons in one
run and notdef boxes in another (font resolution order/cache state). Rendering
once, here, and shipping the resulting PNGs removes font resolution from the
app's runtime path entirely — and the output can be inspected directly.

Runs without GTK so nothing reconfigures the font map.

Usage: python3 tools/render_icons.py [--size 96]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import fonts_env  # noqa: E402  (must precede Pango)

import gi  # noqa: E402

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

import cairo  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "icons_rendered"
GLYPHS = ROOT / "assets" / "icon_glyphs.json"

FAMILIES = {"": "Gemini Icons", "~filled": "Gemini Icons Filled"}
# Icon tones. Suffix follows the fill marker, e.g. "search~filled~gray.png".
COLORS = {
    "": (1.0, 1.0, 1.0),                # white — on dark surfaces / active pills
    "~gray": (0.541, 0.541, 0.541),     # #8A8A8A — muted icons on light surfaces
    "~graydark": (0.604, 0.604, 0.604),  # #9A9A9A — muted icons on dark surfaces
    "~dark": (0.024, 0.180, 0.435),    # #062E6F — on an accent/light pill
}


def render(ch: str, family: str, px: int, color, path: Path) -> None:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, px, px)
    cr = cairo.Context(surface)
    layout = Pango.Layout(PangoCairo.FontMap.new().create_context())
    desc = Pango.FontDescription()
    desc.set_family(family)
    desc.set_absolute_size(int(px * Pango.SCALE * 0.80))
    layout.set_font_description(desc)
    layout.set_text(ch, -1)
    w, h = layout.get_pixel_size()
    cr.move_to((px - w) / 2.0, (px - h) / 2.0)
    cr.set_source_rgba(color[0], color[1], color[2], 1.0)
    PangoCairo.show_layout(cr, layout)
    surface.flush()
    surface.write_to_png(str(path))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=96)
    args = ap.parse_args()

    data = json.loads(GLYPHS.read_text())["glyphs"]
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for name, cp in sorted(data.items()):
        ch = chr(int(cp))
        for fsuffix, family in FAMILIES.items():
            for csuffix, color in COLORS.items():
                render(ch, family, args.size, color, OUT / f"{name}{fsuffix}{csuffix}.png")
                n += 1
    print(f"rendered {n} icons ({len(data)} glyphs x {len(FAMILIES)} fills x "
          f"{len(COLORS)} tones) at {args.size}px -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
