"""The home dashboard.

The layout is a 1:1 restyle of the reference application measured in
``docs/DESIGN.md`` ("Hearth"), with sample content:

* a hero card whose right side carries the landscape artwork,
* a tab row (segmented control + period button),
* a two-column body — target cards and a chat strip on the left, model status
  and quick statistics on the right.

Every visual element is built from the shared primitives in :mod:`app.cards`
and the tokens in :mod:`app.theme`; no colours or CSS classes are hard-coded
here.
"""
from __future__ import annotations

from collections.abc import Callable

import gi

from app import theme  # noqa: F401  (registers the bundled fonts before Gtk)

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from app.cards import (  # noqa: E402
    body,
    card,
    chip,
    divider,
    eyebrow,
    icon_square,
    metric,
    pill_button,
    section_title,
    segmented,
    spacer,
    stat_tile,
    title,
)
from app.charts import BarChart, Sparkline  # noqa: E402
from app.hero_art import HeroArt  # noqa: E402

# --- content ----------------------------------------------------------------

#: Weekly activity behind the "Gemini 3.8 Flash" target card.
SPARK_VALUES: tuple[float, ...] = (
    18, 25, 21, 32, 40, 34, 46, 41, 55, 49, 60, 68, 62, 74, 69, 81,
)

#: Daily token spend behind the "Claude Sonnet 4.6" target card.
BAR_VALUES: tuple[float, ...] = (
    22, 25, 19, 28, 31, 26, 33, 29, 36, 42, 38, 45, 41, 48, 52, 47,
    55, 51, 58, 62, 57, 66, 71, 64, 73, 78, 69, 82, 76, 88, 81, 92,
    85, 79, 90, 84, 76, 72, 68, 74, 63, 59, 66, 57, 61, 54, 58, 49,
    52, 45, 48, 41, 44, 38, 40, 34,
)

#: The rows of the "Model Status" panel.
MODELS: tuple[dict[str, str], ...] = (
    {
        "icon": "gemini_spark",
        "name": "Gemini 3.8 Pro",
        "sub": "Pro subscription",
        "grade": "A+",
    },
    {
        "icon": "bolt",
        "name": "Gemini 3.8 Flash",
        "sub": "Low latency",
        "grade": "A+",
    },
    {
        "icon": "psychology_alt",
        "name": "Claude Sonnet 4.6",
        "sub": "Available",
        "grade": "B+",
    },
    {
        "icon": "mic",
        "name": "Gemini Live",
        "sub": "Voice mode ready",
        "grade": "A-",
    },
)

#: The "Recent Chats" strip.
CHATS: tuple[dict[str, str], ...] = (
    {
        "id": "summarise-repo",
        "icon": "code",
        "title": "Summarise this repo",
        "body": "Walk the tree, map the entry points and write a short "
                "summary of how the pieces fit together.",
        "status": "In progress",
        "date": "Q4 2026",
    },
    {
        "id": "release-notes",
        "icon": "edit_note",
        "title": "Draft release notes",
        "body": "Turn the last two weeks of commits into customer facing "
                "notes, with a short migration note at the end.",
        "status": "Planned",
        "date": "Q4 2026",
    },
    {
        "id": "model-costs",
        "icon": "bar_chart",
        "title": "Compare model costs",
        "body": "Chart token spend per model across the workspace and flag "
                "anything that drifted above the monthly budget.",
        "status": "In progress",
        "date": "Today",
    },
)

#: The 2 × 2 quick-stat grid.
STATS: tuple[tuple[str, str, str], ...] = (
    ("chat", "12", "Chats"),
    ("thinking_model", "6", "Models"),
    ("extension", "27", "Tools"),
    ("trending_up", "78%", "Avg. progress"),
)


# --- helpers ----------------------------------------------------------------


def _vdivider() -> Gtk.Widget:
    """A one pixel vertical rule, using the shared ``divider`` styling."""
    sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
    sep.add_css_class("divider")
    sep.set_size_request(1, -1)
    return sep


def _is_dark(colour: str) -> bool:
    """True when a CSS colour is dark enough to need light glyphs on top."""
    rgba = Gdk.RGBA()
    rgba.parse(colour)
    luminance = 0.2126 * rgba.red + 0.7152 * rgba.green + 0.0722 * rgba.blue
    return luminance < 0.5


def _pill_button(label: str, icon_name: str = "", primary: bool = False,
                 on_click: Callable[[], None] | None = None) -> Gtk.Button:
    """``cards.pill_button`` with a glyph that stays legible on the pill.

    The bundled icons are white in their base rendering and navy in the
    "dark" tone, so a black pill needs the white one and a light pill the
    navy one.
    """
    button = pill_button(label, icon_name, primary=primary, on_click=on_click)
    if icon_name:
        scheme = theme.scheme()
        row = button.get_child()
        image = row.get_first_child() if row is not None else None
        if isinstance(image, Gtk.Image):
            tone = "white" if _is_dark(scheme.pill_bg) else scheme.on_accent
            image.set_from_paintable(theme.icon_texture(icon_name, tone))
    return button


def _hex_rgb(value: str) -> tuple[float, float, float]:
    """#rrggbb -> (r, g, b) in 0..1."""
    v = value.lstrip("#")
    return tuple(int(v[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


#: Geometry of the greeting card, measured from the reference.
ART_WIDTH = 560
HERO_HEIGHT = 271

# --- the page ---------------------------------------------------------------


class HomePage(Gtk.Box):
    """The dashboard shown when no conversation is open."""

    def __init__(self,
                 on_new_chat: Callable[[], None] | None = None,
                 on_open_chat: Callable[[str], None] | None = None,
                 on_select_model: Callable[[], None] | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("content")
        self.set_margin_start(36)
        self.set_margin_end(36)
        self.set_margin_top(8)
        self.set_margin_bottom(28)

        self._on_new_chat = on_new_chat
        self._on_open_chat = on_open_chat
        self._on_select_model = on_select_model
        self._segment: Gtk.Box | None = None

        self._live = {"models": None, "stats": None, "chats": None}

        self.append(self._build_hero())
        self.append(spacer(height=24))
        self.append(self._build_tab_row())
        self.append(spacer(height=24))
        self._body = self._build_body()
        self.append(self._body)

    # -- hero ----------------------------------------------------------------
    def _build_hero(self) -> Gtk.Widget:
        """The hero card: greeting on the left, the landscape on the right.

        The reference bleeds a full-height illustration across the right of
        the card, clipped by the card's rounded corner, with the greeting
        sitting to its left.  The overlay reproduces that: the landscape is
        the main child (so it fills the card) and the greeting is laid over
        the left half.
        """
        hero = card(inset=True)
        hero.add_css_class("hero")

        overlay = Gtk.Overlay()
        art = HeroArt(fade_colour=_hex_rgb(theme.scheme().hero),
                      dim=0.45 if theme.scheme().name == 'dark' else 0.0)
        art.set_size_request(ART_WIDTH, HERO_HEIGHT)
        art.set_halign(Gtk.Align.END)
        art.set_valign(Gtk.Align.FILL)
        overlay.set_child(art)

        text = self._hero_text()
        text.set_halign(Gtk.Align.START)
        text.set_valign(Gtk.Align.CENTER)
        text.set_margin_start(36)
        text.set_margin_end(36)
        overlay.add_overlay(text)

        hero.append(overlay)
        return hero

    def _hero_text(self) -> Gtk.Box:
        """The greeting column of the hero card."""
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        column.set_size_request(520, -1)
        column.set_margin_start(28)
        column.set_margin_end(24)
        column.set_margin_top(26)
        column.set_margin_bottom(26)

        hello = eyebrow("WELCOME BACK")
        hello.remove_css_class("card-eyebrow")
        hello.add_css_class("hero-eyebrow")
        column.append(hello)

        heading = Gtk.Label(label="Mantel", xalign=0)
        heading.add_css_class("hero-title")
        heading.set_margin_top(6)
        column.append(heading)

        subtitle = Gtk.Label(
            label="Ask anything, pick a model and keep every thread in one "
                  "place.",
            xalign=0,
        )
        subtitle.add_css_class("hero-sub")
        subtitle.set_margin_top(4)
        column.append(subtitle)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        buttons.set_margin_top(20)
        buttons.append(_pill_button("New chat", "add", primary=True,
                                    on_click=self._new_chat))
        buttons.append(_pill_button("Vision", "image", on_click=self._new_chat))
        column.append(buttons)
        return column

    # -- tab row -------------------------------------------------------------
    def _build_tab_row(self) -> Gtk.Widget:
        """Segmented control on the left, period button on the right."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)

        self._segment = segmented(["Overview", "Models", "Chats", "Skills"], 0,
                                  self._on_tab_selected)
        row.append(self._segment)
        row.append(spacer())

        period = Gtk.Button()
        period.add_css_class("btn-secondary")
        period.set_valign(Gtk.Align.CENTER)
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        inner.append(theme.icon("calendar_month", 18))
        inner.append(Gtk.Label(label="Q4 2026"))
        inner.append(theme.icon("chevron_right", 16))
        period.set_child(inner)
        row.append(period)
        return row

    def _on_tab_selected(self, index: int) -> None:
        """Move the active pill and, on the model tab, ask for a model."""
        child = self._segment.get_first_child() if self._segment else None
        position = 0
        while child is not None:
            if position == index:
                child.add_css_class("active")
            else:
                child.remove_css_class("active")
            child = child.get_next_sibling()
            position += 1
        if index == 1 and self._on_select_model is not None:
            self._on_select_model()

    # -- body ----------------------------------------------------------------
    def _build_body(self) -> Gtk.Widget:
        """The two column body: content on the left, status on the right."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=35)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
        left.set_hexpand(True)
        row.append(left)

        left.append(section_title("Active Targets", "schedule"))
        targets = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        targets.append(self._spark_target())
        targets.append(self._bar_target())
        left.append(targets)

        recent = section_title("Recent Chats", "forum")
        recent.set_margin_top(10)
        left.append(recent)
        self._chat_holder = self._chat_strip(self._live["chats"] or CHATS)
        left.append(self._chat_holder)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        right.set_size_request(435, -1)
        row.append(right)

        right.append(section_title("Model Status", "monitor_heart"))
        self._model_holder = self._model_panel()
        right.append(self._model_holder)

        stats_title = section_title("Quick Stats", "bolt")
        stats_title.set_margin_top(14)
        right.append(stats_title)
        self._stats_holder = self._stats_panel()
        right.append(self._stats_holder)
        return row

    def _chat_strip(self, chats) -> Gtk.Widget:
        """The row of recent-chat cards."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        self._chat_row = row
        self._fill_chats(chats)
        return row

    def _fill_chats(self, chats) -> None:
        """Refill the recent-chat strip in place."""
        row = getattr(self, "_chat_row", None)
        if row is None:
            return
        while (child := row.get_first_child()) is not None:
            row.remove(child)
        for chat in chats:
            row.append(self._chat_card(chat))

    # -- target cards --------------------------------------------------------
    def _target_card(self, name: str, caption: str, icon_name: str,
                     value: str, sub: str, weeks: tuple[str, ...] = (),
                     chart: Gtk.Widget | None = None) -> Gtk.Widget:
        """An inset target card: heading, metric and a chart."""
        panel = card(inset=True)
        body_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        body_box.set_margin_start(20)
        body_box.set_margin_end(20)
        body_box.set_margin_top(18)
        body_box.set_margin_bottom(16)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        labels.append(title(name))
        labels.append(eyebrow(caption))
        head.append(labels)
        badge = icon_square(icon_name, "", 18)
        badge.set_valign(Gtk.Align.START)
        head.append(badge)
        body_box.append(head)

        figures = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        figures.set_margin_top(16)
        figures.append(metric(value, sub))
        if weeks:
            figures.append(spacer())
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            row.set_valign(Gtk.Align.CENTER)
            for week in weeks:
                row.append(chip(week))
            figures.append(row)
        body_box.append(figures)

        if chart is not None:
            chart.set_margin_top(12)
            body_box.append(chart)

        panel.append(body_box)
        return panel

    def _spark_target(self) -> Gtk.Widget:
        """The Gemini target card, charted with a sparkline."""
        return self._target_card(
            "Gemini 3.8 Flash",
            "Gemini model",
            "gemini_spark",
            "78%",
            "Weekly goal progress",
            weeks=("W1", "W2", "W3"),
            chart=Sparkline(SPARK_VALUES, marker=8, height=84),
        )

    def _bar_target(self) -> Gtk.Widget:
        """The Claude target card, charted with a bar chart."""
        return self._target_card(
            "Claude Sonnet 4.6",
            "Claude model",
            "psychology_alt",
            "45%",
            "Beta access progress",
            chart=BarChart(BAR_VALUES, highlight=(28, 40), height=84),
        )

    # -- chat cards ----------------------------------------------------------
    def _chat_card(self, chat: dict[str, str]) -> Gtk.Widget:
        """A vision-style chat card: image placeholder, title, body, footer."""
        panel = card()
        body_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        body_box.set_margin_start(16)
        body_box.set_margin_end(16)
        body_box.set_margin_top(16)
        body_box.set_margin_bottom(14)

        overlay = Gtk.Overlay()
        placeholder = card(inset=True)
        placeholder.set_size_request(-1, 120)
        overlay.set_child(placeholder)

        badge = icon_square(chat["icon"], "Open chat", 14)
        badge.add_css_class("on-dark")
        badge.set_halign(Gtk.Align.START)
        badge.set_valign(Gtk.Align.START)
        badge.set_margin_start(10)
        badge.set_margin_top(10)
        if self._on_open_chat is not None:
            badge.connect("clicked",
                          lambda _b, cid=chat.get("id", ""): self._on_open_chat(cid))
        overlay.add_overlay(badge)
        body_box.append(overlay)

        heading = title(chat["title"])
        heading.set_margin_top(14)
        body_box.append(heading)

        description = body(chat["body"])
        description.set_margin_top(8)
        body_box.append(description)

        rule = divider()
        rule.set_margin_top(14)
        body_box.append(rule)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        footer.set_margin_top(10)
        status_icon = icon_square("schedule", "", 12)
        status_icon.set_focusable(False)
        status_icon.set_valign(Gtk.Align.CENTER)
        footer.append(status_icon)
        status = Gtk.Label(label=chat["status"])
        status.add_css_class("card-body")
        footer.append(status)
        footer.append(spacer())
        date = Gtk.Label(label=chat["date"])
        date.add_css_class("card-body")
        footer.append(date)
        body_box.append(footer)

        panel.append(body_box)
        return panel

    # -- right column --------------------------------------------------------
    def _model_panel(self) -> Gtk.Widget:
        """The model status panel: one row per model, split by hairlines."""
        panel = card()
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        column.set_margin_start(18)
        column.set_margin_end(18)
        column.set_margin_top(14)
        column.set_margin_bottom(14)
        panel.append(column)
        self._model_column = column
        for index, model in enumerate(self._live["models"] or MODELS):
            if index:
                column.append(divider())
            column.append(self._model_row(model))
        return panel

    def _model_row(self, model: dict[str, str]) -> Gtk.Widget:
        """A single model row: icon, name, sub-label and a grade chip."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        row.set_margin_top(10)
        row.set_margin_bottom(10)

        badge = icon_square(model["icon"], "", 18)
        badge.set_valign(Gtk.Align.START)
        row.append(badge)

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        labels.set_valign(Gtk.Align.CENTER)
        labels.append(title(model["name"]))
        labels.append(body(model["sub"], wrap=False))
        row.append(labels)

        row.append(spacer())

        grade = Gtk.Box()
        grade.set_halign(Gtk.Align.END)
        grade.set_valign(Gtk.Align.CENTER)
        grade.append(chip(model["grade"]))
        row.append(grade)
        return row

    def _stats_panel(self) -> Gtk.Widget:
        """The quick-stat panel: one card holding a 2 × 2 grid of tiles."""
        panel = card()
        grid = Gtk.Grid(column_spacing=0, row_spacing=0)
        self._stats_grid = grid
        panel.append(grid)
        self._fill_stats(self._live["stats"] or STATS, grid)
        return panel

    def _fill_stats(self, stats, grid=None) -> None:
        """Fill a quick-stat grid with the given tiles."""
        grid = grid or getattr(self, "_stats_grid", None)
        if grid is None:
            return
        while (child := grid.get_first_child()) is not None:
            grid.remove(child)

        for index, (icon_name, number, label) in enumerate(stats):
            column, row = index % 2, index // 2
            tile = stat_tile(icon_name, number, label)
            tile.set_margin_start(18)
            tile.set_margin_end(18)
            tile.set_margin_top(14)
            tile.set_margin_bottom(14)
            grid.attach(tile, column * 2, row * 2, 1, 1)
            if column == 0:
                grid.attach(_vdivider(), 1, row * 2, 1, 1)
            if row == 0:
                rule = Gtk.Separator()
                rule.add_css_class("divider")
                grid.attach(rule, 0, 1, 3, 1)

    # -- live data -----------------------------------------------------------
    def set_live_data(self, models=None, stats=None, chats=None) -> None:
        """Replace the placeholder panels with what the machine reports.

        `models` is a list of ``{"icon", "name", "sub", "grade"}`` dicts,
        `stats` a list of ``(icon, number, label)`` triples and `chats` a list
        of the same dicts the chat cards use.

        The body is rebuilt rather than patched in place: GTK caches a render
        node per widget, and swapping children of an already-laid-out panel
        does not reliably repaint.
        """
        if models is not None:
            self._live["models"] = list(models)
        if stats is not None:
            self._live["stats"] = list(stats)
        if chats is not None:
            self._live["chats"] = list(chats)
        self._rebuild_body()

    def _rebuild_body(self) -> None:
        old = getattr(self, "_body", None)
        if old is not None:
            self.remove(old)
        self._body = self._build_body()
        self.append(self._body)
        # keep the page anchored at the top when the body changes height
        import gi as _gi  # noqa: PLC0415

        _gi.require_version("GLib", "2.0")
        from gi.repository import GLib as _GLib  # noqa: PLC0415

        def _reset():
            scroller = self.get_ancestor(Gtk.ScrolledWindow)
            if scroller is not None:
                scroller.get_vadjustment().set_value(0)
            return False

        _GLib.idle_add(_reset)

    # -- callbacks -----------------------------------------------------------
    def _new_chat(self) -> None:
        """Start a new chat, if the shell wants one."""
        if self._on_new_chat is not None:
            self._on_new_chat()
