"""Instantiate static faces from the app's variable icon font.

LuminousSymbols is a variable font (FILL/opsz/wght). Driving it through
Pango/fontconfig renders wrong or missing glyphs, while a direct FreeType
render of the same codepoints is correct — so the port ships frozen
instances instead of relying on variable-axis support in the stack.

Producing two instances also gives filled icons as a family switch rather
than a variation string, which is far more robust in GTK4 CSS.

Usage: python3 tools/make_icon_fonts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "fonts" / "LuminousSymbols[FILL,opsz,wght].ttf"

# (output filename, family name, FILL value)
INSTANCES = [
    ("GeminiIcons-Regular.ttf", "Gemini Icons", 0.0),
    ("GeminiIcons-Filled.ttf", "Gemini Icons Filled", 1.0),
]


def set_names(font: TTFont, family: str, subfamily: str) -> None:
    """Rewrite the name table to a single unambiguous family."""
    full = f"{family} {subfamily}"
    ps = full.replace(" ", "")
    for rec in font["name"].names:
        try:
            cur = rec.toUnicode()
        except Exception:
            continue
        if rec.nameID == 1:
            rec.string = family
        elif rec.nameID == 2:
            rec.string = subfamily
        elif rec.nameID == 3:
            rec.string = f"{ps};{cur.split(';')[-1] if ';' in cur else '1.000'}"
        elif rec.nameID == 4:
            rec.string = full
        elif rec.nameID == 6:
            rec.string = ps
        elif rec.nameID in (16, 17):
            rec.string = family if rec.nameID == 16 else subfamily


def main() -> int:
    if not SRC.is_file():
        print(f"missing {SRC}", file=sys.stderr)
        return 1
    for out_name, family, fill in INSTANCES:
        font = TTFont(SRC)
        inst = instancer.instantiateVariableFont(
            font, {"opsz": 24.0, "wght": 400.0, "FILL": fill},
            inplace=False, updateFontNames=False,
        )
        set_names(inst, family, "Regular")
        for table in ("fvar", "STAT", "avar", "gvar", "HVAR", "MVAR", "VVAR"):
            if table in inst:
                del inst[table]
        dst = ROOT / "assets" / "fonts" / out_name
        inst.save(dst)
        print(f"wrote {dst.name}  family={family!r}  FILL={fill}  "
              f"glyphs={inst['maxp'].numGlyphs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
