# Assets

This directory holds **only what the repository can legally ship**: the glyph
name table the icon pipeline needs. Everything extracted from the original
application — its typefaces, icon font, app icon and Lottie animations — is
deliberately **not** tracked. Those files are Google's, and a portfolio
repository is the wrong place to redistribute them.

The client is written to run without them: it falls back to stock symbolic
icons and the system `sans-serif` / `monospace` families. `docs/screenshots/`
was produced *with* the real assets supplied locally, so it shows the intended
look rather than the fallback.

## What is here

| Path | What it is |
|---|---|
| `icon_glyphs.json` | glyph name → codepoint, one entry per icon in the reference set. A factual mapping table, not font data. |

## Supplying the real assets

If you own a copy of the desktop application and want the exact look, extract
it yourself and drop the results in the paths below. Nothing here is
downloaded at build time.

```
assets/
  fonts/                 # the faces the stylesheet asks for
    GoogleSansFlex[…].ttf
    GoogleSansText-*.ttf
    GoogleSansCode-*.ttf
    LuminousSymbols[FILL,opsz,wght].ttf
  icons/
    appicon_{16,24,32,48,64,128,256,512}.png
  lottie/                # optional, currently unused by the client
  icons_rendered/        # generated
```

Then rebuild the two derived artifacts:

```bash
python3 tools/make_icon_fonts.py   # variable icon font -> static outlined + filled
python3 tools/render_icons.py      # every glyph -> assets/icons_rendered/*.png
```

`render_icons.py` writes one PNG per glyph per tone, which is what
`app/theme.py` loads. GTK's text pipeline draws notdef boxes for these
private-use codepoints, non-deterministically across processes, so the glyphs
are baked to bitmaps once rather than rendered as text at runtime.

Finally, install the fonts for the stylesheet by leaving them in
`assets/fonts/` — `app/fonts_env.py` points fontconfig at that directory
before GTK initialises. Set `GEMINI_LINUX_NO_BUNDLED_FONTS=1` to opt out and
use system fonts even when the directory exists.

## Licences

- **JetBrains Mono** — SIL Open Font License 1.1. Safe to redistribute; add it
  to `assets/fonts/` if you want the intended body face.
- **Google Sans / Google Sans Text / Google Sans Code / Luminous Symbols** —
  proprietary Google typefaces. Not licensed for redistribution; keep them to
  yourself.
- **The Gemini name and marks** belong to Google. This is an unofficial client
  and is not affiliated with or endorsed by Google.
