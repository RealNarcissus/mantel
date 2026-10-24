"""Generate the application icon.

The shell's brand mark is a rounded dark square with a light glyph, so the
desktop icon is drawn the same way: a dark rounded square carrying the
Gemini mark from the app's own icon font.

The glyph is composited from the pre-rendered PNG set rather than rasterised
here, because the pre-rendered set is the verified one (see
`tools/render_icons.py`, and the note in `docs/PORT_NOTES.md` about icon
rasterisation being unreliable at runtime).

Usage: python3 tools/make_app_icon.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "icons"
GLYPH = ROOT / "assets" / "icons_rendered" / "gem_spark.png"
SIZES = (16, 24, 32, 48, 64, 128, 256, 512)

# The gradient behind the mark, sampled from the sidebar's active pill.
TOP = (26, 26, 27)
BOTTOM = (10, 10, 11)
GLYPH_TINT = (237, 241, 252)


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1),
                                            radius=radius, fill=255)
    return mask


def render(size: int) -> Image.Image:
    bg = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(bg)
    for y in range(size):
        t = y / max(1, size - 1)
        draw.line(
            [(0, y), (size, y)],
            fill=tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM))
            + (255,),
        )
    bg.putalpha(_rounded_mask(size, int(size * 0.22)))

    glyph = Image.open(GLYPH).convert("RGBA")
    side = int(size * 0.62)
    glyph = glyph.resize((side, side), Image.LANCZOS)
    alpha = glyph.getchannel("A").point(lambda a: 255 if a > 40 else 0)
    tint = Image.new("RGBA", (side, side), GLYPH_TINT + (255,))
    tint.putalpha(alpha)
    bg.alpha_composite(tint, ((size - side) // 2, (size - side) // 2))
    return bg


def main() -> int:
    if not GLYPH.is_file():
        print(f"missing {GLYPH}", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        render(size).save(OUT / f"appicon_{size}.png")
    render(512).save(OUT / "appicon.png")
    print(f"wrote {len(SIZES) + 1} icons to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
