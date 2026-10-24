"""Transcript view: message list with live streaming and tool activity."""
from __future__ import annotations

import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from app import markdown, theme

#: Width of the transcript column, in pixels.
CHAT_WIDTH = 720


def clear(box: Gtk.Box) -> None:
    while (child := box.get_first_child()) is not None:
        box.remove(child)


def _meta_line(model: str, duration: float, usage: dict) -> str:
    bits = []
    if model:
        bits.append(model)
    if duration:
        bits.append(f"{duration:.1f}s")
    total = (usage or {}).get("total_tokens")
    if total:
        bits.append(f"{total:,} tok")
    return "  ·  ".join(bits)


class AssistantMessage(Gtk.Box):
    """A streamed assistant reply: thinking, tool calls, markdown body."""

    def __init__(self, model: str = ""):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("msg-ai")
        self.model = model
        self._raw = ""
        self._thinking = ""
        self._render_scheduled = False
        self._finished = False

        self._tools = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.append(self._tools)

        self._think_expander = Gtk.Expander(label="Thinking")
        self._think_expander.add_css_class("thought")
        self._think_label = Gtk.Label(xalign=0)
        self._think_label.set_wrap(True)
        self._think_label.set_selectable(True)
        self._think_expander.set_child(self._think_label)
        self._think_expander.set_visible(False)
        self.append(self._think_expander)

        self._body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.append(self._body)

        self._footer = Gtk.Label(xalign=0)
        self._footer.add_css_class("metric-sub")
        self._footer.set_visible(False)
        self.append(self._footer)

    # -- streaming ----------------------------------------------------------
    def append_delta(self, delta: str) -> None:
        self._raw += delta
        self._schedule()

    def set_text(self, text: str) -> None:
        self._raw = text
        self._schedule(immediate=True)

    def append_thought(self, delta: str) -> None:
        self._thinking += delta
        self._think_expander.set_visible(True)
        self._think_label.set_text(self._thinking)

    def add_tool(self, name: str, detail: str = "") -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        row.add_css_class("tool-block")
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.append(theme.icon("build", 16, tone=""))
        title = Gtk.Label(label=name, xalign=0)
        title.add_css_class("tool-name")
        head.append(title)
        row.append(head)
        if detail:
            d = Gtk.Label(label=detail, xalign=0)
            d.add_css_class("tool-detail")
            d.set_wrap(True)
            d.set_lines(3)
            d.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
            row.append(d)
        self._tools.append(row)

    def _schedule(self, immediate: bool = False) -> None:
        if immediate:
            self._rerender()
            return
        if self._render_scheduled or self._finished:
            return
        self._render_scheduled = True
        GLib.timeout_add(80, self._do_render)

    def _do_render(self) -> bool:
        self._render_scheduled = False
        self._rerender()
        return False

    def _rerender(self) -> None:
        clear(self._body)
        for widget in markdown.render(self._raw):
            self._body.append(widget)
        self._scroll_into_view()

    def _scroll_into_view(self) -> None:
        view = self.get_ancestor(Gtk.ScrolledWindow)
        if view is None:
            return
        adj = view.get_vadjustment()
        # only auto-follow when the user is already at the bottom
        if adj.get_value() + adj.get_page_size() >= adj.get_upper() - 80:
            GLib.idle_add(lambda: (adj.set_value(adj.get_upper() - adj.get_page_size()),
                                   False)[1])

    def finish(self, duration: float = 0.0, usage: dict | None = None,
               model: str = "") -> None:
        self._finished = True
        self._rerender()
        text = _meta_line(model or self.model, duration, usage or {})
        if text:
            self._footer.set_text(text)
            self._footer.set_visible(True)

    def fail(self, message: str) -> None:
        self._finished = True
        box = Gtk.Label(label=message, xalign=0)
        box.add_css_class("error-box")
        box.set_wrap(True)
        self._body.append(box)


class WorkPanel(Gtk.Box):
    """The work panel: what the agent has done, is doing, and plans to do.

    The desktop app shows the same three groups — completed, current and
    planned steps, plus the files it touched.
    """

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.add_css_class("work-panel")
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.append(self._box)

    def set_items(self, items) -> None:
        from app import theme  # noqa: PLC0415

        while (child := self._box.get_first_child()) is not None:
            self._box.remove(child)
        if not items:
            self.set_visible(False)
            return
        group = None
        for item in items:
            if item.kind != group:
                group = item.kind
                heading = {"done": "Completed", "current": "Current",
                           "planned": "Planned", "file": "Files"}.get(group, "")
                if heading:
                    lbl = Gtk.Label(label=heading.upper(), xalign=0)
                    lbl.add_css_class("work-heading")
                    self._box.append(lbl)
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            mark = theme.icon(
                {"done": "check_circle", "current": "schedule",
                 "planned": "radio_button_unchecked",
                 "file": "description"}.get(item.kind, "circle"),
                15, tone="")
            row.append(mark)
            name = Gtk.Label(label=item.label, xalign=0)
            name.add_css_class("work-item")
            if item.kind == "current":
                name.add_css_class("current")
            row.append(name)
            if item.detail:
                detail = Gtk.Label(label=item.detail, xalign=0)
                detail.add_css_class("tool-detail")
                detail.set_ellipsize(3)
                row.append(detail)
            self._box.append(row)
        self.set_visible(True)


class ChangesPanel(Gtk.Box):
    """The files the agent changed, read from git."""

    def __init__(self, on_open=None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("work-panel")
        self._on_open = on_open
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.append(self._box)
        self.set_visible(False)

    def set_changes(self, files) -> None:
        from app import theme  # noqa: PLC0415

        while (child := self._box.get_first_child()) is not None:
            self._box.remove(child)
        if not files:
            self.set_visible(False)
            return

        heading = Gtk.Label(label="CHANGES", xalign=0)
        heading.add_css_class("work-heading")
        self._box.append(heading)

        for changed in files[:8]:
            row = Gtk.Button()
            row.add_css_class("task-row")
            row.set_halign(Gtk.Align.FILL)
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            mark = theme.icon(
                {"added": "add", "deleted": "delete",
                 "untracked": "description"}.get(changed.status, "edit"),
                15, tone="")
            inner.append(mark)
            name = Gtk.Label(label=changed.name, xalign=0)
            name.add_css_class("work-item")
            name.set_hexpand(True)
            name.set_ellipsize(3)
            inner.append(name)

            status = Gtk.Label(label=changed.status)
            status.add_css_class("tool-detail")
            inner.append(status)

            if changed.summary:
                counts = Gtk.Label(label=changed.summary)
                counts.add_css_class("tool-detail")
                inner.append(counts)

            row.set_child(inner)
            row.set_tooltip_text(changed.path)
            if self._on_open:
                row.connect("clicked",
                            lambda _b, f=changed: self._on_open(f.path))
            self._box.append(row)
        self.set_visible(True)


class ChatView(Gtk.ScrolledWindow):
    """Scrollable transcript."""

    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.add_css_class("transcript")
        self.set_vexpand(True)

        self._column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self._column.set_halign(Gtk.Align.CENTER)
        # a fixed measure: the column is wider than its content so the
        # transcript and the composer share one alignment
        self._column.set_size_request(CHAT_WIDTH, -1)
        self._column.set_margin_top(18)
        self._column.set_margin_bottom(18)
        for m in ("start", "end"):
            getattr(self._column, f"set_margin_{m}")(20)
        self.set_child(self._column)

        self._current: AssistantMessage | None = None
        self._welcome: Gtk.Widget | None = None

    @property
    def column(self) -> Gtk.Box:
        return self._column

    def _dismiss_welcome(self) -> None:
        if self._welcome is not None:
            self._column.remove(self._welcome)
            self._welcome = None

    def _scroll_bottom(self) -> None:
        GLib.idle_add(lambda: (self.get_vadjustment().set_value(
            self.get_vadjustment().get_upper()), False)[1])

    def reset(self) -> None:
        clear(self._column)
        self._current = None
        self._welcome = None

    def add_user(self, text: str) -> None:
        self._dismiss_welcome()
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        row.set_halign(Gtk.Align.END)
        bubble = Gtk.Label(label=text, xalign=1.0)
        bubble.set_wrap(True)
        bubble.set_wrap_mode(2)
        bubble.set_selectable(True)
        bubble.set_max_width_chars(60)
        bubble.add_css_class("msg-user")
        row.append(bubble)
        self._column.append(row)
        self._scroll_bottom()

    def add_steer(self, text: str) -> None:
        """A mid-turn instruction: shown as a note, not a new user bubble."""
        self._dismiss_welcome()
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        row.set_halign(Gtk.Align.END)
        chip = Gtk.Label(label=f"↳ steered: {text}", xalign=1.0)
        chip.set_wrap(True)
        chip.set_wrap_mode(2)
        chip.set_max_width_chars(60)
        chip.add_css_class("msg-steer")
        row.append(chip)
        self._column.append(row)
        self._scroll_bottom()

    def add_error(self, message: str) -> None:
        lbl = Gtk.Label(label=message, xalign=0)
        lbl.add_css_class("error-box")
        lbl.set_wrap(True)
        self._column.append(lbl)
        self._scroll_bottom()

    def begin_assistant(self, model: str = "") -> AssistantMessage:
        msg = AssistantMessage(model=model)
        self._column.append(msg)
        self._current = msg
        self._scroll_bottom()
        return msg

    def add_assistant_text(self, text: str, model: str = "") -> AssistantMessage:
        """Static (already complete) assistant message, e.g. from history."""
        msg = self.begin_assistant(model)
        msg.set_text(text)
        msg._finished = True  # noqa: SLF001
        return msg

    def show_welcome(self, on_suggestion) -> None:
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        wrap.set_valign(Gtk.Align.CENTER)
        wrap.set_vexpand(True)

        title = Gtk.Label(label="Hello")
        title.add_css_class("hero-title")
        wrap.append(title)

        sub = Gtk.Label(label="Ask anything, or pick a starting point.")
        sub.add_css_class("hero-sub")
        wrap.append(sub)

        grid = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        grid.set_halign(Gtk.Align.CENTER)
        for icon_name, label, prompt in (
            ("search_spark", "Research a topic", "Research the latest developments in "),
            ("code", "Write some code", "Write a Python script that "),
            ("notes_spark", "Summarise a file", "Summarise the file "),
            ("add_image_spark", "Work with images", "Describe this image: "),
        ):
            btn = Gtk.Button()
            btn.add_css_class("card")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            inner.append(theme.icon(icon_name, 24, tone=""))
            lbl = Gtk.Label(label=label)
            lbl.set_wrap(True)
            inner.append(lbl)
            btn.set_child(inner)
            btn.connect("clicked", lambda _b, p=prompt: on_suggestion(p))
            grid.append(btn)
        wrap.append(grid)
        self._column.append(wrap)
        self._welcome = wrap
