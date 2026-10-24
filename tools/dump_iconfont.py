"""Dump glyph names + codepoints from the app's icon font (LuminousSymbols)."""
import json, sys
from fontTools.ttLib import TTFont
f = TTFont(sys.argv[1])
cmap = f.getBestCmap()
order = f.getGlyphOrder()
axes = [(a.axisTag, a.minValue, a.defaultValue, a.maxValue) for a in f['fvar'].axes] if 'fvar' in f else []
out = {"axes": axes, "glyphs": {n: cp for cp, n in sorted(cmap.items())}}
json.dump(out, open(sys.argv[2], "w"), indent=1)
print("axes:", axes)
print("glyphs:", len(cmap))
for cp, n in sorted(cmap.items())[:15]:
    print(f"  U+{cp:04X} {n}")
