"""Tasks: the agent's work threads.

The desktop app keeps one unified list of chats and task threads, with filters
*All / Ready / Needs attention / In progress*.  The status words come from
`app.session` so the list and the composer agree about what state a thread is
in.
"""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from app import session as session_mod
from app import theme  # noqa: E402
from app.cards import (body, card, chip, divider, eyebrow, hspacer,
                       icon_square, pill_button, section_title, segmented,
                       spacer)

#: The filter names the desktop app uses.
FILTERS = (
    ("all", "All"),
    ("ready", "Ready"),
    ("attention", "Needs attention"),
    ("progress", "In progress"),
)

STATUS_LABEL = {
    session_mod.STATUS_IDLE: "Ready",
    session_mod.STATUS_THINKING: "In progress",
    session_mod.STATUS_COMPLETE: "Complete",
    session_mod.STATUS_NEEDS_INPUT: "Needs attention",
    session_mod.STATUS_ERROR: "Error",
}

STATUS_CHIP = {
    session_mod.STATUS_IDLE: "chip-grade",
    session_mod.STATUS_THINKING: "chip-grade",
    session_mod.STATUS_NEEDS_INPUT: "chip-grade",
    session_mod.STATUS_COMPLETE: "chip-grade",
    session_mod.STATUS_ERROR: "chip-grade",
}


class TasksPage(Gtk.Box):
    """A filtered list of the agent's task threads."""

    def __init__(self, on_new: Callable[[], None] | None = None,
                 on_open: Callable[[str], None] | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("content")
        self.set_margin_start(36)
        self.set_margin_end(36)
        self.set_margin_top(8)
        self.set_margin_bottom(28)

        self._on_new = on_new
        self._on_open = on_open or (lambda _cid: None)
        self._filter = "all"
        self._items: list[dict] = []

        # --- header --------------------------------------------------------
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="Tasks", xalign=0)
        title.add_css_class("hero-title")
        titles.append(title)
        titles.append(body("Work the agent is running, finished, or waiting on "
                           "you for."))
        head.append(titles)
        head.append(hspacer())
        if on_new:
            head.append(pill_button("New task", "add", primary=True,
                                    on_click=on_new))
        self.append(head)

        self.append(spacer(height=18))

        # --- filters -------------------------------------------------------
        self._segmented = segmented([label for _key, label in FILTERS],
                                    active=0, on_select=self._on_filter)
        self.append(self._segmented)
        self.append(spacer(height=18))

        self.append(section_title("Threads", "checklist"))
        self.append(spacer(height=12))

        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.append(self._list)
        self.refresh([])

    # -- data ---------------------------------------------------------------
    def refresh(self, conversations, status_for=None) -> None:
        """Rebuild the list.

        `conversations` are `app.store.Conversation` objects; `status_for` maps
        one to an `app.session` status word.
        """
        items = []
        for conv in conversations or []:
            status = (status_for(conv) if status_for
                      else session_mod.STATUS_IDLE)
            items.append({
                "id": conv.id,
                "title": conv.title,
                "status": status,
                "updated": conv.updated,
                "messages": len(conv.messages),
                "preview": next((m.text for m in reversed(conv.messages)
                                 if m.role == "assistant"), ""),
            })
        self._items = items
        self._render()

    def set_items(self, items: list[dict]) -> None:
        self._items = list(items)
        self._render()

    def _on_filter(self, index: int) -> None:
        self._filter = FILTERS[index][0]
        self._render()

    def _matches(self, item: dict) -> bool:
        if self._filter == "all":
            return True
        if self._filter == "ready":
            return item["status"] in (session_mod.STATUS_IDLE,
                                      session_mod.STATUS_COMPLETE)
        if self._filter == "attention":
            return item["status"] in (session_mod.STATUS_NEEDS_INPUT,
                                      session_mod.STATUS_ERROR)
        if self._filter == "progress":
            return item["status"] == session_mod.STATUS_THINKING
        return True

    # -- rendering ----------------------------------------------------------
    def _render(self) -> None:
        while (child := self._list.get_first_child()) is not None:
            self._list.remove(child)

        shown = [i for i in self._items if self._matches(i)]
        if not shown:
            self._list.append(self._empty_state())
            return
        for item in shown:
            self._list.append(self._row(item))

    def _empty_state(self) -> Gtk.Widget:
        if self._filter == "all":
            heading = "No tasks yet"
            copy = ("Ask for something in Task mode and it will appear here, "
                    "with what the agent did and what it needs from you.")
        else:
            label = dict(FILTERS)[self._filter]
            heading = f"Nothing {label.lower()}"
            copy = "Switch the filter, or start a task in Task mode."
        panel = card(inset=True)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_margin_top(28)
        inner.set_margin_bottom(28)
        inner.set_halign(Gtk.Align.CENTER)
        icon = icon_square("checklist", "", 22)
        icon.set_halign(Gtk.Align.CENTER)
        inner.append(icon)
        title = Gtk.Label(label=heading)
        title.add_css_class("card-title")
        inner.append(title)
        text = body(copy)
        text.set_justify(Gtk.Justification.CENTER)
        text.set_halign(Gtk.Align.CENTER)
        inner.append(text)
        panel.append(inner)
        return panel

    def _row(self, item: dict) -> Gtk.Widget:
        btn = Gtk.Button()
        btn.add_css_class("card")
        btn.set_child(self._row_body(item))
        btn.connect("clicked", lambda _b, i=item["id"]: self._on_open(i))
        btn.set_tooltip_text(item["title"])
        return btn

    def _row_body(self, item: dict) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        row.set_margin_start(16)
        row.set_margin_end(16)
        row.set_margin_top(14)
        row.set_margin_bottom(14)

        badge = icon_square("notes_spark", "", 18)
        badge.set_valign(Gtk.Align.START)
        row.append(badge)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        col.set_hexpand(True)
        title = Gtk.Label(label=item["title"], xalign=0)
        title.add_css_class("card-title")
        title.set_ellipsize(3)
        col.append(title)
        if item.get("preview"):
            preview = body(item["preview"].replace("\n", " "))
            preview.set_lines(2)
            preview.set_ellipsize(3)
            col.append(preview)
        meta = Gtk.Label(
            label=f"{item['messages']} message"
                  f"{'' if item['messages'] == 1 else 's'}",
            xalign=0)
        meta.add_css_class("metric-sub")
        col.append(meta)
        row.append(col)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right.set_valign(Gtk.Align.CENTER)
        status = Gtk.Label(label=STATUS_LABEL.get(item["status"], "Ready"))
        status.add_css_class(STATUS_CHIP.get(item["status"], "chip-grade"))
        right.append(status)
        import time as _time  # noqa: PLC0415

        when = Gtk.Label(label=_time.strftime(
            "%d %b %H:%M", _time.localtime(item["updated"])))
        when.add_css_class("metric-sub")
        when.set_halign(Gtk.Align.END)
        right.append(when)
        row.append(right)
        return row
