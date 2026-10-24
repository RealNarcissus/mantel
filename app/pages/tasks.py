"""Tasks: the user's own list — today, upcoming, later, done.

This page is the "to do list" half of the product, and the reminder surface:
add a line the way you would say it ("call the dentist tomorrow"), and the
parser turns the phrase into a date. Everything here is the user's, not the
agent's; the agent reads and writes the same store through `app.todos`.
"""
from __future__ import annotations

import time
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from app import theme  # noqa: F401  (registers the bundled fonts)
from app import todos as store
from app.cards import (body, card, hspacer, icon_square, pill_button,
                       section_title, spacer)


def _due_label(task: store.Task) -> str:
    if not task.due:
        return ""
    moment = time.localtime(task.due)
    if task.overdue:
        return "overdue · " + time.strftime("%d %b", moment)
    if task.due_today:
        clock = time.strftime("%H:%M", moment)
        return "today" + (f" · {clock}" if clock != "00:00" else "")
    return time.strftime("%a %d %b", moment)


class TasksPage(Gtk.Box):
    """The user's task list."""

    def __init__(self, on_changed: Callable[[], None] | None = None,
                 on_all_done: Callable[[], None] | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("content")
        self.set_margin_start(36)
        self.set_margin_end(36)
        self.set_margin_top(8)
        self.set_margin_bottom(28)

        self._on_changed = on_changed
        self._on_all_done = on_all_done

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="Tasks", xalign=0)
        title.add_css_class("hero-title")
        titles.append(title)
        titles.append(body("Write it the way you'd say it — “pay the invoice "
                           "tomorrow at 5pm” becomes a dated task."))
        head.append(titles)
        self.append(head)
        self.append(spacer(height=18))

        # --- quick add -----------------------------------------------------
        add_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text(
            "Add a task…  (tomorrow, Monday, in 3 days)")
        self._entry.set_hexpand(True)
        self._entry.add_css_class("task-entry")
        self._entry.connect("activate", self._add)
        add_row.append(self._entry)
        add_row.append(pill_button("Add", "add", primary=True,
                                   on_click=self._add))
        self.append(add_row)
        self.append(spacer(height=20))

        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.append(self._list)
        self.refresh()

    # -- data ---------------------------------------------------------------
    def refresh(self) -> None:
        while (child := self._list.get_first_child()) is not None:
            self._list.remove(child)

        groups = (
            ("Today", store.today()),
            ("Upcoming", store.upcoming()),
            ("Later", store.someday()),
        )
        shown = 0
        for name, tasks in groups:
            if not tasks:
                continue
            shown += len(tasks)
            self._list.append(section_title(name, "schedule"))
            for task in tasks:
                self._list.append(self._row(task))

        if not shown:
            self._list.append(self._empty())

        done = [task for task in store.all_tasks() if task.done]
        if done:
            self._list.append(spacer(height=4))
            self._list.append(self._done_section(done))

    def _empty(self) -> Gtk.Widget:
        panel = card(inset=True)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_margin_top(28)
        inner.set_margin_bottom(28)
        inner.set_halign(Gtk.Align.CENTER)
        icon = icon_square("checklist", "", 22)
        icon.set_halign(Gtk.Align.CENTER)
        inner.append(icon)
        title = Gtk.Label(label="Nothing to do")
        title.add_css_class("card-title")
        inner.append(title)
        copy = body("Add a task above, or ask the agent to add one for you.")
        copy.set_justify(Gtk.Justification.CENTER)
        inner.append(copy)
        panel.append(inner)
        return panel

    def _row(self, task: store.Task) -> Gtk.Widget:
        panel = card(inset=True)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        for margin in ("start", "end"):
            getattr(row, f"set_margin_{margin}")(16)
        row.set_margin_top(10)
        row.set_margin_bottom(10)

        tick = Gtk.Button()
        tick.add_css_class("task-tick")
        tick.set_valign(Gtk.Align.CENTER)
        tick.set_tooltip_text("Complete")
        tick.connect("clicked", lambda _b, t=task: self._complete(t))
        row.append(tick)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        col.set_hexpand(True)
        title = Gtk.Label(label=task.title, xalign=0)
        title.add_css_class("card-title")
        title.set_wrap(True)
        if task.overdue:
            title.add_css_class("task-overdue")
        col.append(title)

        meta = [part for part in (task.project, _due_label(task)) if part]
        if task.repeat:
            meta.append(f"repeats {task.repeat}")
        if not task.remind and task.due:
            meta.append("no reminder")
        if meta:
            detail = Gtk.Label(label=" · ".join(meta), xalign=0)
            detail.add_css_class("metric-sub")
            col.append(detail)
        row.append(col)

        if task.due and not task.remind:
            remind = Gtk.Button(label="Remind me")
            remind.add_css_class("chip-grade")
            remind.set_valign(Gtk.Align.CENTER)
            remind.connect("clicked", lambda _b, t=task: self._remind(t))
            row.append(remind)

        delete = Gtk.Button(label="Delete")
        delete.add_css_class("chip-grade")
        delete.set_valign(Gtk.Align.CENTER)
        delete.connect("clicked", lambda _b, t=task: self._remove(t))
        row.append(delete)

        panel.append(row)
        return panel

    def _done_section(self, done: list[store.Task]) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        head = Gtk.Label(label=f"Done · {len(done)}", xalign=0)
        head.add_css_class("metric-sub")
        box.append(head)
        for task in done[:6]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.set_margin_top(3)
            row.set_margin_bottom(3)
            label = Gtk.Label(label=task.title, xalign=0)
            label.set_opacity(0.55)
            row.append(label)
            row.append(hspacer())
            undo = Gtk.Button(label="Undo")
            undo.add_css_class("chip-grade")
            undo.connect("clicked", lambda _b, t=task: self._reopen(t))
            row.append(undo)
            box.append(row)
        return box

    # -- actions ------------------------------------------------------------
    def _add(self, *_args) -> None:
        text = self._entry.get_text().strip()
        if not text:
            return
        if store.add(text) is None:
            return
        self._entry.set_text("")
        self.refresh()
        if self._on_changed:
            self._on_changed()

    def _complete(self, task: store.Task) -> None:
        store.complete(task.id)
        self.refresh()
        if self._on_changed:
            self._on_changed()
        if self._on_all_done and not store.today():
            self._on_all_done()

    def _reopen(self, task: store.Task) -> None:
        store.reopen(task.id)
        self.refresh()
        if self._on_changed:
            self._on_changed()

    def _remove(self, task: store.Task) -> None:
        store.remove(task.id)
        self.refresh()
        if self._on_changed:
            self._on_changed()

    def _remind(self, task: store.Task) -> None:
        if not task.due:
            return
        store.update(task.id, remind=task.due)
        self.refresh()
        if self._on_changed:
            self._on_changed()
