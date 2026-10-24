"""Today: the day in one glance.

This is the home screen the product is built around. It answers "what now?" in
one view — what is due, what is next, what the agent remembers and what it is
doing — and it owns the focus timer, because a timer that lives on its own page
is a timer people forget to start.

Everything here reads the same local stores as the other pages (`app.todos`,
`app.memory`, `app.schedules`), so nothing on this screen can disagree with the
page it links to.
"""
from __future__ import annotations

import time
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from app import calendar as calendar_store
from app import memory as memory_store
from app import plan as plan_store
from app import schedules as schedule_store
from app import theme  # noqa: F401  (registers the bundled fonts)
from app import todos
from app.cards import (body, card, divider, eyebrow, hspacer, icon_square,
                       metric, pill_button, section_title, spacer)
from app.focus import FocusTimer


def _greeting() -> str:
    hour = time.localtime().tm_hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def _clock(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _relative(timestamp: float) -> str:
    delta = timestamp - time.time()
    if delta <= 0:
        return "now"
    minutes = int(delta // 60)
    if minutes < 60:
        return f"in {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"in {hours} h"
    return f"in {hours // 24} d"


class TodayPage(Gtk.Box):
    """The day: agenda, next up, memory, focus and agent activity."""

    def __init__(self,
                 on_toggle_task: Callable[[str], None] | None = None,
                 on_add_task: Callable[[str], None] | None = None,
                 on_open_tasks: Callable[[], None] | None = None,
                 on_open_chat: Callable[[], None] | None = None,
                 on_focus_done: Callable[[], None] | None = None,
                 on_open_settings: Callable[[], None] | None = None,
                 on_plan_export: Callable[[str], None] | None = None,
                 engine_name: str = "",
                 model_label: str = "") -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("content")
        self.set_margin_start(36)
        self.set_margin_end(36)
        self.set_margin_top(8)
        self.set_margin_bottom(28)

        self._on_toggle_task = on_toggle_task or (lambda _id: None)
        self._on_add_task = on_add_task
        self._on_open_tasks = on_open_tasks or (lambda: None)
        self._on_open_chat = on_open_chat or (lambda: None)
        self._on_focus_done = on_focus_done
        self._on_open_settings = on_open_settings or (lambda: None)
        self._on_plan_export = on_plan_export or (lambda _path: None)
        self._engine_name = engine_name or "engine"
        self._model_label = model_label

        self.focus = FocusTimer(minutes=25)
        self.focus.connect("tick", self._on_focus_tick)

        # --- header --------------------------------------------------------
        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        titles.append(eyebrow(time.strftime("%A · %d %B").upper()))
        greeting = _greeting()
        title = Gtk.Label(label=greeting, xalign=0)
        title.add_css_class("hero-title")
        titles.append(title)
        titles.append(body("Here is what is due, what is next, and what the "
                           "agent has been doing."))
        head.append(titles)
        head.append(hspacer())
        plan_button = pill_button("Plan the day", "schedule",
                                  on_click=self._show_plan)
        plan_button.set_valign(Gtk.Align.CENTER)
        head.append(plan_button)
        new_chat = pill_button("New thread", "chat", on_click=self._on_open_chat)
        new_chat.set_valign(Gtk.Align.CENTER)
        head.append(new_chat)
        self.append(head)
        self.append(spacer(height=20))

        # --- quick add -----------------------------------------------------
        add_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text("Add a task for today…")
        self._entry.set_hexpand(True)
        self._entry.add_css_class("task-entry")
        self._entry.connect("activate", self._add_task)
        add_row.append(self._entry)
        add_row.append(pill_button("Add", "add", primary=True,
                                   on_click=self._add_task))
        self.append(add_row)
        self.append(spacer(height=22))

        # --- columns -------------------------------------------------------
        columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=22)
        columns.set_hexpand(True)
        self.append(columns)

        self._left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self._left.set_hexpand(True)
        columns.append(self._left)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        right.set_size_request(430, -1)
        columns.append(right)

        self._focus_card = self._build_focus_card()
        right.append(self._focus_card)
        self._agent_card = self._build_agent_card()
        right.append(self._agent_card)
        self._memory_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                      spacing=0)
        right.append(self._memory_holder)

        self.refresh()

    # -- planning -----------------------------------------------------------
    def _show_plan(self) -> None:
        """Propose time blocks for the day, and offer them as an .ics file."""
        import gi as _gi  # noqa: PLC0415

        _gi.require_version("Adw", "1")
        from gi.repository import Adw as _Adw  # noqa: PLC0415

        proposal = plan_store.plan_day()
        dialog = _Adw.MessageDialog(transient_for=self.get_root(),
                                    heading="Plan the day",
                                    body="Proposed around what is already on "
                                         "your calendar.")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(6)
        if proposal.busy:
            busy = Gtk.Label(
                label="Meetings: " + ", ".join(
                    f"{time.strftime('%H:%M', time.localtime(block['start']))} "
                    f"{block['title']}" for block in proposal.busy[:4]),
                xalign=0)
            busy.add_css_class("metric-sub")
            box.append(busy)
        for block in proposal.blocks:
            row = Gtk.Label(
                label=f"{time.strftime('%H:%M', time.localtime(block.start))}"
                      f"–{time.strftime('%H:%M', time.localtime(block.end))}  "
                      f"{block.title}", xalign=0)
            row.set_wrap(True)
            box.append(row)
        if not proposal.blocks:
            empty = Gtk.Label(label="No free time left in the working day. "
                                   "Nothing scheduled.", xalign=0)
            empty.set_wrap(True)
            box.append(empty)
        if proposal.unscheduled:
            more = Gtk.Label(label="Did not fit: " + ", ".join(
                proposal.unscheduled[:4]), xalign=0)
            more.add_css_class("metric-sub")
            more.set_wrap(True)
            more.set_margin_top(6)
            box.append(more)
        dialog.set_extra_child(box)
        dialog.add_response("close", "Close")
        if proposal.blocks:
            dialog.add_response("export", "Export .ics")
            dialog.set_response_appearance("export",
                                           _Adw.ResponseAppearance.SUGGESTED)

        def on_response(dlg, response):
            if response == "export" and proposal.blocks:
                path = plan_store.save_plan(proposal)
                self._on_plan_export(path)

        dialog.connect("response", on_response)
        dialog.present()

    # -- focus --------------------------------------------------------------
    def _build_focus_card(self) -> Gtk.Widget:
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for margin in ("start", "end"):
            getattr(inner, f"set_margin_{margin}")(18)
        inner.set_margin_top(14)
        inner.set_margin_bottom(14)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.append(theme.icon("bolt", 16))
        label = Gtk.Label(label="Focus", xalign=0)
        label.add_css_class("card-title")
        head.append(label)
        head.append(hspacer())
        self._focus_state = Gtk.Label(label="ready")
        self._focus_state.add_css_class("metric-sub")
        head.append(self._focus_state)
        inner.append(head)

        self._focus_metric = metric("25:00", "focus session")
        inner.append(self._focus_metric)

        self._focus_bar = Gtk.Box()
        self._focus_bar.set_size_request(-1, 5)
        self._focus_bar.add_css_class("focus-track")
        self._focus_fill = Gtk.Box()
        self._focus_fill.add_css_class("focus-fill")
        self._focus_fill.set_size_request(0, -1)
        self._focus_bar.append(self._focus_fill)
        inner.append(spacer(height=8))
        inner.append(self._focus_bar)
        inner.append(spacer(height=10))

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._focus_toggle = pill_button("Start", "bolt",
                                         primary=True,
                                         on_click=self._toggle_focus)
        controls.append(self._focus_toggle)
        reset = Gtk.Button(label="Reset")
        reset.add_css_class("chip-grade")
        reset.connect("clicked", lambda _b: self._reset_focus())
        controls.append(reset)
        inner.append(controls)
        panel.append(inner)
        return panel

    def _toggle_focus(self) -> None:
        self.focus.toggle()
        self._on_focus_tick(self.focus, self.focus.remaining, self.focus.total)

    def _reset_focus(self) -> None:
        self.focus.reset()
        self._on_focus_tick(self.focus, self.focus.remaining, self.focus.total)

    def _on_focus_tick(self, _timer, remaining: int, total: int) -> None:
        value = _clock(remaining)
        # the metric widget is a box of labels; replace the first child's text
        for child in self._focus_metric.get_children() if hasattr(
                self._focus_metric, "get_children") else []:
            if isinstance(child, Gtk.Label):
                child.set_text(value)
                break
        else:
            label = self._focus_metric.get_first_child()
            if isinstance(label, Gtk.Label):
                label.set_text(value)
        running = self.focus.running
        self._focus_toggle.set_label("Pause" if running else "Start")
        if self.focus.finished:
            self._focus_state.set_text("done")
        elif running:
            self._focus_state.set_text("in progress")
        else:
            self._focus_state.set_text("paused" if self.focus.elapsed else "ready")
        width = int(232 * (1 - remaining / max(1, total)))
        self._focus_fill.set_size_request(max(0, width), -1)
        if self.focus.finished and self._on_focus_done:
            self._on_focus_done()

    # -- agent --------------------------------------------------------------
    def _build_agent_card(self) -> Gtk.Widget:
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for margin in ("start", "end"):
            getattr(inner, f"set_margin_{margin}")(18)
        inner.set_margin_top(14)
        inner.set_margin_bottom(14)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.append(theme.icon("gemini_spark", 16))
        label = Gtk.Label(label="Agent", xalign=0)
        label.add_css_class("card-title")
        head.append(label)
        inner.append(head)

        engine = Gtk.Label(label=self._engine_name, xalign=0)
        engine.add_css_class("metric-sub")
        inner.append(engine)
        if self._model_label:
            model = Gtk.Label(label=self._model_label, xalign=0)
            model.add_css_class("metric-sub")
            inner.append(model)

        open_button = pill_button("Open a thread", "chat",
                                  on_click=self._on_open_chat)
        open_button.set_halign(Gtk.Align.START)
        open_button.set_margin_top(10)
        inner.append(open_button)
        panel.append(inner)
        return panel

    # -- data ---------------------------------------------------------------
    def refresh(self) -> None:
        while (child := self._left.get_first_child()) is not None:
            self._left.remove(child)
        while (child := self._memory_holder.get_first_child()) is not None:
            self._memory_holder.remove(child)

        due_today = todos.today()
        upcoming = todos.upcoming()
        later = todos.someday()

        self._left.append(self._schedule_card())
        self._left.append(self._today_card(due_today))
        self._left.append(self._upcoming_card(upcoming))
        if later:
            self._left.append(self._later_card(later))

        self._memory_holder.append(self._memory_card())
        self._refresh_schedule_line()

    def _schedule_card(self) -> Gtk.Widget:
        """Today's events, or an honest hint when no calendar is connected."""
        sources = calendar_store.sources()
        events = calendar_store.today() if sources else []

        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for margin in ("start", "end"):
            getattr(inner, f"set_margin_{margin}")(18)
        inner.set_margin_top(14)
        inner.set_margin_bottom(14)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.append(theme.icon("calendar_month", 16))
        label = Gtk.Label(label="On the calendar", xalign=0)
        label.add_css_class("card-title")
        head.append(label)
        head.append(hspacer())
        count = Gtk.Label(label=calendar_store.summarise(events))
        count.add_css_class("metric-sub")
        head.append(count)
        inner.append(head)

        if not sources:
            copy = body("No calendar connected. Add an .ics file in Settings "
                        "and your day appears here — read-only, no account "
                        "needed.")
            copy.set_margin_top(8)
            inner.append(copy)
            open_settings = Gtk.Button(label="Add a calendar")
            open_settings.add_css_class("chip-grade")
            open_settings.set_halign(Gtk.Align.START)
            open_settings.set_margin_top(10)
            open_settings.connect("clicked",
                                  lambda _b: self._on_open_settings())
            inner.append(open_settings)
            panel.append(inner)
            return panel

        if not events:
            copy = body("Nothing on the calendar today.")
            copy.set_margin_top(8)
            inner.append(copy)
            panel.append(inner)
            return panel

        for index, event in enumerate(events[:8]):
            if index:
                inner.append(divider())
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            row.set_margin_top(8)
            row.set_margin_bottom(8)
            when = Gtk.Label(
                label="all day" if event.all_day
                else time.strftime("%H:%M", time.localtime(event.start)),
                xalign=0)
            when.add_css_class("metric-sub")
            when.set_size_request(58, -1)
            row.append(when)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
            col.set_hexpand(True)
            title = Gtk.Label(label=event.title, xalign=0)
            title.add_css_class("card-title")
            title.set_ellipsize(3)
            col.append(title)
            if event.location:
                place = Gtk.Label(label=event.location, xalign=0)
                place.add_css_class("metric-sub")
                place.set_ellipsize(3)
                col.append(place)
            row.append(col)
            inner.append(row)
        panel.append(inner)
        return panel

    def _today_card(self, tasks: list[todos.Task]) -> Gtk.Widget:
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for margin in ("start", "end"):
            getattr(inner, f"set_margin_{margin}")(18)
        inner.set_margin_top(14)
        inner.set_margin_bottom(14)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.append(theme.icon("check_circle", 16))
        label = Gtk.Label(label="Today", xalign=0)
        label.add_css_class("card-title")
        head.append(label)
        head.append(hspacer())
        count = Gtk.Label(label=f"{len(tasks)} open"
                             if tasks else "nothing due")
        count.add_css_class("metric-sub")
        head.append(count)
        inner.append(head)

        if not tasks:
            copy = body("Nothing due today. Add something above, or enjoy it.")
            copy.set_margin_top(8)
            inner.append(copy)
        for index, task in enumerate(tasks[:8]):
            if index:
                inner.append(divider())
            inner.append(self._task_row(task))
        panel.append(inner)
        return panel

    def _task_row(self, task: todos.Task) -> Gtk.Widget:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_margin_top(9)
        row.set_margin_bottom(9)

        tick = Gtk.Button()
        tick.add_css_class("task-tick")
        tick.set_valign(Gtk.Align.CENTER)
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
        meta = []
        if task.overdue:
            meta.append("overdue")
        elif task.due:
            meta.append(time.strftime("%H:%M", time.localtime(task.due)))
        if task.repeat:
            meta.append(f"repeats {task.repeat}")
        if meta:
            detail = Gtk.Label(label=" · ".join(meta), xalign=0)
            detail.add_css_class("metric-sub")
            col.append(detail)
        row.append(col)
        return row

    def _upcoming_card(self, tasks: list[todos.Task]) -> Gtk.Widget:
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for margin in ("start", "end"):
            getattr(inner, f"set_margin_{margin}")(18)
        inner.set_margin_top(14)
        inner.set_margin_bottom(14)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.append(theme.icon("schedule", 16))
        label = Gtk.Label(label="Next up", xalign=0)
        label.add_css_class("card-title")
        head.append(label)
        head.append(hspacer())
        open_all = Gtk.Button(label="All tasks")
        open_all.add_css_class("chip-grade")
        open_all.connect("clicked", lambda _b: self._on_open_tasks())
        head.append(open_all)
        inner.append(head)

        if not tasks:
            copy = body("Nothing scheduled this week.")
            copy.set_margin_top(8)
            inner.append(copy)
        for index, task in enumerate(tasks[:5]):
            if index:
                inner.append(divider())
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.set_margin_top(8)
            row.set_margin_bottom(8)
            when = Gtk.Label(label=time.strftime("%a", time.localtime(task.due)),
                             xalign=0)
            when.add_css_class("metric-sub")
            when.set_size_request(42, -1)
            row.append(when)
            title = Gtk.Label(label=task.title, xalign=0)
            title.set_hexpand(True)
            title.set_ellipsize(3)
            row.append(title)
            inner.append(row)
        panel.append(inner)
        return panel

    def _later_card(self, tasks: list[todos.Task]) -> Gtk.Widget:
        panel = card(inset=True)
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        for margin in ("start", "end"):
            getattr(inner, f"set_margin_{margin}")(18)
        inner.set_margin_top(12)
        inner.set_margin_bottom(12)
        label = Gtk.Label(label=f"{len(tasks)} undated "
                                f"task{'' if len(tasks) == 1 else 's'} in Later",
                          xalign=0)
        label.add_css_class("metric-sub")
        label.set_hexpand(True)
        inner.append(label)
        open_all = Gtk.Button(label="Open")
        open_all.add_css_class("chip-grade")
        open_all.connect("clicked", lambda _b: self._on_open_tasks())
        inner.append(open_all)
        panel.append(inner)
        return panel

    def _memory_card(self) -> Gtk.Widget:
        facts = memory_store.facts()[:4]
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for margin in ("start", "end"):
            getattr(inner, f"set_margin_{margin}")(18)
        inner.set_margin_top(14)
        inner.set_margin_bottom(14)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        head.append(theme.icon("lightbulb_tips", 16))
        label = Gtk.Label(label="Remembered", xalign=0)
        label.add_css_class("card-title")
        head.append(label)
        head.append(hspacer())
        count = Gtk.Label(label=f"{len(memory_store.facts())} facts")
        count.add_css_class("metric-sub")
        head.append(count)
        inner.append(head)

        if not facts:
            copy = body("Nothing yet — tell the agent how you like to work.")
            copy.set_margin_top(8)
            inner.append(copy)
        for fact in facts:
            row = Gtk.Label(label=f"· {fact.text}", xalign=0)
            row.set_wrap(True)
            row.add_css_class("metric-sub")
            row.set_margin_top(5)
            inner.append(row)
        panel.append(inner)
        return panel

    def _refresh_schedule_line(self) -> None:
        try:
            pending = [s.next_run for s in schedule_store.list_schedules()
                       if not s.paused and s.next_run]
            if not pending:
                return
            soonest = min(pending)
            label = Gtk.Label(
                label=f"Next scheduled run {_relative(soonest)}",
                xalign=0)
            label.add_css_class("metric-sub")
            label.set_margin_top(4)
            self._memory_holder.append(label)
        except Exception:  # noqa: BLE001 - a schedule line is optional
            pass

    # -- actions ------------------------------------------------------------
    def _add_task(self, *_args) -> None:
        text = self._entry.get_text().strip()
        if not text:
            return
        if self._on_add_task is not None:
            self._on_add_task(text)
        else:
            todos.add(text)
        self._entry.set_text("")
        self.refresh()

    def _complete(self, task: todos.Task) -> None:
        todos.complete(task.id)
        self.refresh()
        if self._on_toggle_task:
            self._on_toggle_task(task.id)

    def stop(self) -> None:
        self.focus.stop()
