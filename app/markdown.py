"""Markdown -> GTK widgets.

The engine streams markdown, so the transcript needs real rendering rather
than a plain text blob: headings, lists, blockquotes, fenced code and inline
emphasis/code/links. Everything is emitted as selectable labels with Pango
markup, which keeps text selection and copy working the way a native app's
transcript should.
"""
from __future__ import annotations

import re

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from app import theme  # noqa: E402

_FENCE = re.compile(r"^\s*```(.*)$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_NUMBER = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_QUOTE = re.compile(r"^>\s?(.*)$")
_RULE = re.compile(r"^\s*([-*_])\1{2,}\s*$")
#: A standalone image: ![alt](path) or ![alt](file:///path)
_IMAGE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif")


def _local_path(target: str) -> str:
    """Turn a link target into a local path, or return ''."""
    target = target.strip()
    if target.startswith("file://"):
        target = target[len("file://"):]
    if target.startswith("~"):
        import os  # noqa: PLC0415

        target = os.path.expanduser(target)
    if target.startswith("/") and target.lower().endswith(IMAGE_SUFFIXES):
        return target
    return ""


def _image(target: str) -> Gtk.Widget | None:
    """An image block, if the target points at a local picture."""
    path = _local_path(target)
    if not path:
        return None
    try:
        from pathlib import Path  # noqa: PLC0415

        if not Path(path).is_file():
            return None
    except OSError:
        return None
    picture = Gtk.Picture.new_for_filename(path)
    picture.set_can_shrink(True)
    picture.set_alternative_text(path.rsplit("/", 1)[-1])
    picture.add_css_class("md-image")
    picture.set_margin_top(6)
    picture.set_margin_bottom(6)
    return picture


def _esc(text: str) -> str:
    return GLib.markup_escape_text(text, -1)


def inline(text: str) -> str:
    """Inline markdown -> Pango markup (escaped first)."""
    out = _esc(text)
    # Pango markup has no `class` attribute, so the chip colour is taken
    # from the active palette and inlined.
    out = re.sub(r"`([^`]+)`",
                 lambda m: (f'<span font_family="{theme.FONT_MONO}" '
                            f'background="{theme.scheme().surface_alt}">'
                            f'{m.group(1)}</span>'),
                 out)
    out = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", out)
    out = re.sub(r"(?<![\w_])_([^_\n]+)_(?![\w_])", r"<i>\1</i>", out)
    out = re.sub(r"~~(.+?)~~", r"<s>\1</s>", out)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)",
                 r'<a href="\2">\1</a>', out)
    return out


MAX_COLS = 92
#: Pixel width of a code block, matching the transcript measure.
CODE_WIDTH = 690


def _label(markup: str, css: str = "", wrap: bool = True,
           selectable: bool = True) -> Gtk.Label:
    lbl = Gtk.Label()
    try:
        lbl.set_markup(markup)
    except Exception:  # noqa: BLE001 - malformed markup falls back to text
        lbl.set_text(markup)
    lbl.set_wrap(wrap)
    lbl.set_wrap_mode(2)  # PANGO_WRAP_WORD_CHAR
    lbl.set_xalign(0.0)
    lbl.set_selectable(selectable)
    lbl.set_max_width_chars(MAX_COLS)
    if css:
        lbl.add_css_class(css)
    return lbl


def _code_block(lines: list[str]) -> Gtk.Widget:
    frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    frame.add_css_class("md-pre")
    lbl = Gtk.Label(label="\n".join(lines))
    lbl.set_xalign(0.0)
    lbl.set_selectable(True)
    lbl.set_wrap(True)
    lbl.set_max_width_chars(MAX_COLS - 4)
    # a pixel request keeps a long line from stretching the transcript column
    lbl.set_size_request(CODE_WIDTH, -1)
    lbl.add_css_class("md-code-block")
    frame.append(lbl)
    return frame


def render(markdown: str) -> list[Gtk.Widget]:
    """Convert markdown text into a list of widgets, in document order."""
    widgets: list[Gtk.Widget] = []
    lines = (markdown or "").split("\n")
    i = 0
    para: list[str] = []

    def flush_para() -> None:
        if para:
            widgets.append(_label(inline(" ".join(para))))
            para.clear()

    while i < len(lines):
        line = lines[i]

        fence = _FENCE.match(line)
        if fence:
            flush_para()
            body: list[str] = []
            i += 1
            while i < len(lines) and not _FENCE.match(lines[i]):
                body.append(lines[i])
                i += 1
            i += 1  # closing fence
            widgets.append(_code_block(body))
            continue

        if not line.strip():
            flush_para()
            i += 1
            continue

        image = _IMAGE.match(line)
        if image:
            widget = _image(image.group(2))
            if widget is not None:
                flush_para()
                widgets.append(widget)
                i += 1
                continue

        if _RULE.match(line):
            flush_para()
            sep = Gtk.Separator()
            sep.set_margin_top(6)
            sep.set_margin_bottom(6)
            widgets.append(sep)
            i += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_para()
            level = min(len(heading.group(1)), 3)
            widgets.append(_label(inline(heading.group(2)), f"md-h{level}"))
            i += 1
            continue

        quote = _QUOTE.match(line)
        if quote:
            flush_para()
            body = [quote.group(1)]
            i += 1
            while i < len(lines) and _QUOTE.match(lines[i]):
                body.append(_QUOTE.match(lines[i]).group(1))
                i += 1
            widgets.append(_label(inline(" ".join(body)), "md-quote"))
            continue

        bullet = _BULLET.match(line)
        number = _NUMBER.match(line)
        if bullet or number:
            flush_para()
            while i < len(lines):
                b = _BULLET.match(lines[i])
                n = _NUMBER.match(lines[i])
                if b:
                    text, marker = b.group(2), "•"
                elif n:
                    text, marker = n.group(3), f"{n.group(2)}."
                else:
                    break
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                dot = Gtk.Label(label=marker)
                dot.set_valign(Gtk.Align.START)
                dot.set_xalign(1.0)
                dot.set_size_request(18, -1)
                row.append(dot)
                row.append(_label(inline(text)))
                widgets.append(row)
                i += 1
            continue

        para.append(line.strip())
        i += 1

    flush_para()
    return widgets
