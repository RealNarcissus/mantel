"""Create: generate images and video with the agent.

The desktop app has a Create surface (image, video, music) and a library of
what you made. This page drives the agent's own `generate_image` tool: it
composes a prompt with the chosen style, hands it to the agent in Task mode,
and shows the results from the output folder as a gallery.

Generated files are ordinary pictures on disk, so the gallery is just a
directory listing — nothing is hidden in a database.
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk  # noqa: E402

from app import theme  # noqa: F401  (registers the bundled fonts)
from app.cards import (body, card, hspacer, icon_square, pill_button,
                       section_title, spacer)

#: The styles the Create surface offers.
STYLES = ("Photo", "Illustration", "3D", "Minimal", "Watercolour")

#: What each style adds to the prompt.
STYLE_PROMPTS = {
    "Photo": "photorealistic, natural lighting, high detail",
    "Illustration": "digital illustration, clean shapes, soft colour",
    "3D": "3D render, soft studio lighting, matte materials",
    "Minimal": "minimalist, flat colour, generous negative space",
    "Watercolour": "watercolour painting, paper texture, loose brushwork",
}

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def output_dir() -> Path:
    """Where generated images are kept."""
    base = Path(os.environ.get("XDG_PICTURES_DIR") or (Path.home() / "Pictures"))
    data = Path(os.environ.get("XDG_DATA_HOME")
                or (Path.home() / ".local" / "share"))
    import tempfile  # noqa: PLC0415

    for cand in (base / "Mantel", data / "gemini-desktop" / "created",
                 Path(tempfile.gettempdir()) / "gemini-created"):
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / ".write-probe"
            probe.write_text("")
            probe.unlink()
            return cand
        except OSError:
            continue
    return Path(tempfile.mkdtemp(prefix="gemini-created-"))


def recent_images(limit: int = 12) -> list[Path]:
    """The newest pictures *this app* created.

    Only the app's own folder is scanned — never the user's whole Pictures
    directory, which would put their personal photos on the Create page.
    """
    found: list[Path] = []
    try:
        for entry in output_dir().iterdir():
            if entry.is_file() and entry.suffix.lower() in IMAGE_SUFFIXES:
                found.append(entry)
    except OSError:
        pass
    seen: set[str] = set()
    unique = []
    for path in sorted(found, key=lambda p: p.stat().st_mtime
                       if p.exists() else 0, reverse=True):
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique[:limit]


def compose_prompt(description: str, style: str, count: int = 1) -> str:
    """The instruction handed to the agent."""
    suffix = STYLE_PROMPTS.get(style, "")
    plural = "" if count == 1 else f" ({count} variations)"
    return (
        f"Create {count} image{'' if count == 1 else 's'} of: {description}"
        f"{plural}\n\n"
        f"Style: {suffix}.\n\n"
        f"Use the image generation tool. Save each result as a PNG inside "
        f"{output_dir()} with a descriptive filename, then tell me the file "
        f"paths and include each one as a markdown image so I can see it.\n"
    )


class CreatePage(Gtk.Box):
    """Generate images, and browse what has been made."""

    def __init__(self, on_generate: Callable[[str], None] | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("content")
        self.set_margin_start(36)
        self.set_margin_end(36)
        self.set_margin_top(8)
        self.set_margin_bottom(28)

        self._on_generate = on_generate
        self._style = STYLES[0]
        self._count = 1

        # --- header --------------------------------------------------------
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="Create", xalign=0)
        title.add_css_class("hero-title")
        titles.append(title)
        titles.append(body("Describe a picture. The agent generates it and "
                           "saves it to your Pictures folder."))
        head.append(titles)
        self.append(head)
        self.append(spacer(height=22))

        # --- the prompt card ----------------------------------------------
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for m in ("start", "end"):
            getattr(inner, f"set_margin_{m}")(18)
        inner.set_margin_top(16)
        inner.set_margin_bottom(16)

        self.prompt = Gtk.TextView()
        self.prompt.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.prompt.set_size_request(-1, 96)
        self.prompt.add_css_class("composer")
        frame = Gtk.Box()
        frame.add_css_class("search-field")
        frame.append(self.prompt)

        # Gtk.TextView has no placeholder in this GTK build, so one is stacked
        # over it and hidden as soon as there is text
        stack = Gtk.Overlay()
        stack.set_child(frame)
        self._hint = Gtk.Label(
            label="A quiet street corner after rain, warm window light…",
            xalign=0, yalign=0)
        self._hint.add_css_class("metric-sub")
        self._hint.set_margin_start(14)
        self._hint.set_margin_top(12)
        self._hint.set_can_target(False)
        stack.add_overlay(self._hint)
        self.prompt.get_buffer().connect("changed", self._on_prompt_changed)
        inner.append(stack)

        styles = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._style_buttons: dict[str, Gtk.Button] = {}
        for style in STYLES:
            btn = Gtk.Button(label=style)
            btn.add_css_class("chip-grade")
            if style == self._style:
                btn.add_css_class("active")
            btn.connect("clicked", lambda _b, s=style: self._pick_style(s))
            self._style_buttons[style] = btn
            styles.append(btn)
        inner.append(styles)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        count = Gtk.DropDown.new_from_strings(["1 image", "2 images",
                                               "4 images"])
        count.set_selected(0)
        count.connect("notify::selected", self._on_count)
        controls.append(count)
        controls.append(hspacer())
        controls.append(pill_button("Generate", "add_image_spark",
                                    primary=True, on_click=self._generate))
        inner.append(controls)
        panel.append(inner)
        self.append(panel)

        # --- the gallery ---------------------------------------------------
        self.append(spacer(height=26))
        gallery_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                               spacing=8)
        gallery_head.append(section_title("Recent creations", "image"))
        gallery_head.append(hspacer())
        refresh = Gtk.Button(label="Refresh")
        refresh.add_css_class("chip-grade")
        refresh.connect("clicked", lambda _b: self.refresh())
        gallery_head.append(refresh)
        self.append(gallery_head)
        self.append(spacer(height=12))

        self._gallery = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                spacing=14)
        self.append(self._gallery)
        self.refresh()

    # -- controls -----------------------------------------------------------
    def _on_prompt_changed(self, buffer) -> None:
        has_text = buffer.get_char_count() > 0
        self._hint.set_visible(not has_text)

    def _pick_style(self, style: str) -> None:
        self._style = style
        for name, button in self._style_buttons.items():
            if name == style:
                button.add_css_class("active")
            else:
                button.remove_css_class("active")

    def _on_count(self, dropdown: Gtk.DropDown, _spec) -> None:
        self._count = (1, 2, 4)[max(0, min(dropdown.get_selected(), 2))]

    def _generate(self) -> None:
        buf = self.prompt.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(),
                            False).strip()
        if not text or not self._on_generate:
            return
        self._on_generate(compose_prompt(text, self._style, self._count))

    # -- gallery ------------------------------------------------------------
    def refresh(self) -> None:
        while (child := self._gallery.get_first_child()) is not None:
            self._gallery.remove(child)
        images = recent_images()
        if not images:
            self._gallery.append(self._empty_state())
            return
        for path in images[:4]:
            self._gallery.append(self._thumb(path))

    def _empty_state(self) -> Gtk.Widget:
        panel = card(inset=True)
        panel.set_hexpand(True)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_margin_top(26)
        inner.set_margin_bottom(26)
        inner.set_halign(Gtk.Align.CENTER)
        icon = icon_square("add_image_spark", "", 22)
        icon.set_halign(Gtk.Align.CENTER)
        inner.append(icon)
        title = Gtk.Label(label="Nothing created yet")
        title.add_css_class("card-title")
        inner.append(title)
        copy = body(f"Generated pictures appear here. They are saved to "
                    f"{output_dir()}.")
        copy.set_justify(Gtk.Justification.CENTER)
        copy.set_max_width_chars(70)
        copy.set_halign(Gtk.Align.CENTER)
        inner.append(copy)
        panel.append(inner)
        return panel

    def _thumb(self, path: Path) -> Gtk.Widget:
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for m in ("start", "end"):
            getattr(inner, f"set_margin_{m}")(10)
        inner.set_margin_top(10)
        inner.set_margin_bottom(10)

        picture = Gtk.Picture.new_for_filename(str(path))
        picture.set_can_shrink(True)
        picture.set_size_request(240, 180)
        picture.add_css_class("md-image")
        inner.append(picture)

        name = Gtk.Label(label=path.name, xalign=0)
        name.add_css_class("metric-sub")
        name.set_ellipsize(3)
        inner.append(name)

        when = Gtk.Label(
            label=time.strftime("%d %b %H:%M",
                                time.localtime(path.stat().st_mtime)),
            xalign=0)
        when.add_css_class("metric-sub")
        inner.append(when)

        panel.append(inner)
        panel.set_tooltip_text(str(path))
        return panel
