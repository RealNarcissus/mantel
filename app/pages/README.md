# Page contract

Every page is a `Gtk.Box` subclass:

```python
class XPage(Gtk.Box):
    def __init__(self, **callbacks):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
```

Rules:

- Build only from `app.cards` primitives and `app.theme` tokens. Never
  hard-code a colour or invent a CSS class.
- Pages are **scrollable**: put the content in a `Gtk.ScrolledWindow` so a
  long page never stretches the window.
- Page background is the `content` class; the page's own margins are
  36 left/right, 8 top, 28 bottom.
- Headings use `cards.section_title(text, icon_name)`.
- Every action must work without a network connection where possible, and
  must report failures in the UI (a `cards`-styled error box) rather than
  raising.
- No `import` of `app.window` — the window imports the pages, not the other
  way round. Callbacks are passed in.

Available primitives (`app/cards.py`): `card`, `section_title`, `icon_square`,
`pill_button`, `segmented`, `chip`, `divider`, `stat_tile`, `metric`,
`eyebrow`, `title`, `body`, `spacer`.
