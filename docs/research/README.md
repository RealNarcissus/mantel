# Research notes

This folder holds the research that shaped Mantel's product decisions: the
feature inventories, the interaction studies, and captured public documentation
from tools whose desktop clients were worth learning from (Claude Desktop,
Codex, the Gemini desktop app).

It is **input to the design, not shipped documentation.** Nothing here is
loaded by the application, and nothing here is copied into the app's own code or
assets.

## Provenance and licensing

- The `claude/`, `claudeai/` and `codex/` folders are captured, publicly
  available documentation, used for comparison and feature research. Their
  original authors own that text; it is included for reference only.
- `GEMINI_DESKTOP_FEATURE_INVENTORY.md` and `DESKTOP-APP-RESEARCH.md` are
  original notes written for this project.
- **No vendor assets are included** — no fonts, glyphs, icons, binaries or
  protocol dumps. See [`../../assets/README.md`](../../assets/README.md) for how
  to supply your own typography and icon assets.
- If you are republishing this repository and would rather not ship someone
  else's documentation, deleting this folder changes nothing about how the app
  runs.

The design that came out of this research is written up in
[`../VISION.md`](../VISION.md); the visual debt to the original concepts is
credited in the README.
