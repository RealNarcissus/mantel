"""Review: the week, from the app's own records.

The numbers are computed (`app/review.py`); the prose is the agent's job, behind
one button. That split is deliberate — a model is good at saying what a week
felt like, and bad at being trusted with arithmetic.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from app import review as store
from app import theme  # noqa: F401  (registers the bundled fonts)
from app.cards import (
    body,
    card,
    divider,
    eyebrow,
    hspacer,
    metric,
    pill_button,
    spacer,
)


def _hours(minutes: int) -> str:
    return f"{round(minutes / 60.0, 1)}h" if minutes else "0h"


class ReviewPage(Gtk.Box):
    """The week in numbers, with a button to have it written up."""

    def __init__(self, on_write: Callable[[str], None] | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("content")
        self.set_margin_start(36)
        self.set_margin_end(36)
        self.set_margin_top(8)
        self.set_margin_bottom(28)
        self._on_write = on_write or (lambda _prompt: None)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        titles.append(eyebrow(time.strftime("%A · %d %B").upper()))
        title = Gtk.Label(label="Review", xalign=0)
        title.add_css_class("hero-title")
        titles.append(title)
        titles.append(body("What actually happened this week — counted locally, "
                           "not remembered generously."))
        head.append(titles)
        head.append(hspacer())
        write = pill_button("Write it with the agent", "chat", primary=True,
                            on_click=self._write)
        write.set_valign(Gtk.Align.CENTER)
        head.append(write)
        self.append(head)
        self.append(spacer(height=20))

        self._body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.append(self._body)
        self.refresh()

    # -- data ---------------------------------------------------------------
    def refresh(self) -> None:
        while (child := self._body.get_first_child()) is not None:
            self._body.remove(child)

        stats = store.stats()
        previous = store.previous_week()

        self._body.append(self._numbers(stats, previous))

        columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        columns.set_hexpand(True)
        self._body.append(columns)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        left.set_hexpand(True)
        columns.append(left)
        left.append(self._list_card("What moved", stats.completed,
                                    stats.completed_titles,
                                    empty="Nothing finished this week."))
        left.append(self._list_card("What slipped", stats.overdue,
                                    stats.overdue_titles,
                                    empty="Nothing overdue. Rare and good."))

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        right.set_size_request(430, -1)
        columns.append(right)
        right.append(self._learned_card(stats))
        right.append(self._next_card(stats))

    def _numbers(self, stats: store.Stats, previous: store.Stats) -> Gtk.Widget:
        panel = card()
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        for margin in ("start", "end"):
            getattr(row, f"set_margin_{margin}")(8)

        delta_done = stats.completed - previous.completed
        tiles = (
            ("check_circle", str(stats.completed),
             f"done · {delta_done:+d} vs last week" if previous.completed
             else "done"),
            ("notifications", str(stats.overdue), "overdue"),
            ("bolt", _hours(stats.focus_minutes),
             f"focus · {stats.focus_sessions} sessions"),
            ("calendar_month", f"{stats.event_hours:g}h",
             f"{stats.events} events"),
        )
        for index, (icon, value, caption) in enumerate(tiles):
            if index:
                row.append(divider())
            tile = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            tile.set_hexpand(True)
            for margin in ("start", "end", "top", "bottom"):
                getattr(tile, f"set_margin_{margin}")(16)
            tile.append(metric(value, caption))
            row.append(tile)

        panel.append(row)
        week = (f"{datetime.fromtimestamp(stats.start):%d %b} – "
                f"{datetime.fromtimestamp(stats.end - 1):%d %b}")
        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        label = Gtk.Label(label=f"Week of {week}", xalign=0)
        label.add_css_class("metric-sub")
        label.set_margin_start(18)
        label.set_margin_bottom(4)
        wrapper.append(label)
        wrapper.append(panel)
        return wrapper

    def _list_card(self, title: str, count: int, items: list[str],
                   *, empty: str) -> Gtk.Widget:
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for margin in ("start", "end"):
            getattr(inner, f"set_margin_{margin}")(18)
        inner.set_margin_top(14)
        inner.set_margin_bottom(14)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label(label=title, xalign=0)
        label.add_css_class("card-title")
        head.append(label)
        head.append(hspacer())
        chip = Gtk.Label(label=str(count))
        chip.add_css_class("chip-grade")
        head.append(chip)
        inner.append(head)

        if not items:
            copy = body(empty)
            copy.set_margin_top(8)
            inner.append(copy)
        else:
            for item in items:
                line = Gtk.Label(label=f"· {item}", xalign=0)
                line.set_wrap(True)
                line.add_css_class("metric-sub")
                line.set_margin_top(5)
                inner.append(line)
        panel.append(inner)
        return panel

    def _learned_card(self, stats: store.Stats) -> Gtk.Widget:
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for margin in ("start", "end"):
            getattr(inner, f"set_margin_{margin}")(18)
        inner.set_margin_top(14)
        inner.set_margin_bottom(14)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.append(theme.icon("lightbulb_tips", 16))
        label = Gtk.Label(label="Learned about you", xalign=0)
        label.add_css_class("card-title")
        head.append(label)
        inner.append(head)

        if not stats.facts:
            copy = body("Nothing new recorded this week.")
            copy.set_margin_top(8)
            inner.append(copy)
        for fact in stats.facts:
            line = Gtk.Label(label=f"· {fact}", xalign=0)
            line.set_wrap(True)
            line.add_css_class("metric-sub")
            line.set_margin_top(5)
            inner.append(line)
        panel.append(inner)
        return panel

    def _next_card(self, stats: store.Stats) -> Gtk.Widget:
        panel = card(inset=True)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for margin in ("start", "end"):
            getattr(inner, f"set_margin_{margin}")(18)
        inner.set_margin_top(12)
        inner.set_margin_bottom(12)

        if stats.open_now:
            line = f"{stats.open_now} task{'s' if stats.open_now != 1 else ''} " \
                   f"still open going into next week."
        else:
            line = "Nothing open. The week is genuinely closed."
        copy = body(line)
        inner.append(copy)
        note = Gtk.Label(
            label="The agent writes the narrative; these numbers are the input.",
            xalign=0)
        note.add_css_class("metric-sub")
        inner.append(note)
        panel.append(inner)
        return panel

    # -- actions ------------------------------------------------------------
    def _write(self) -> None:
        self._on_write(store.agent_prompt(store.stats()))
