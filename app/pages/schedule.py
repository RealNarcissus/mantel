"""Schedules: recurring prompts the agent runs while the app is open.

The page lists schedules from `app.schedules`, lets you create, pause, run and
delete them, and shows the last few runs. A schedule only fires while Mantel
is running — the same contract Claude's desktop app uses for local tasks.
"""
from __future__ import annotations

import time
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from app import schedules as store
from app import session as session_mod
from app import theme  # noqa: F401  (registers the bundled fonts)
from app.cards import (body, card, hspacer, icon_square, pill_button,
                       section_title, segmented, spacer)

#: Filters in the segmented control.
FILTERS = ("All", "Active", "Paused", "Completed")


def _when(timestamp: float) -> str:
    if not timestamp:
        return "never"
    return time.strftime("%d %b %H:%M", time.localtime(timestamp))


def _relative(timestamp: float) -> str:
    if not timestamp:
        return ""
    delta = timestamp - time.time()
    if delta <= 0:
        return "due now"
    minutes = int(delta // 60)
    if minutes < 60:
        return f"in {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"in {hours} h"
    return f"in {hours // 24} d"


class SchedulePage(Gtk.Box):
    """Create, inspect and control recurring prompts."""

    def __init__(self, on_new: Callable[[], None] | None = None,
                 on_run_now: Callable[[object], None] | None = None,
                 on_changed: Callable[[], None] | None = None,
                 on_open_thread: Callable[[str], None] | None = None,
                 workspace: str = "") -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("content")
        self.set_margin_start(36)
        self.set_margin_end(36)
        self.set_margin_top(8)
        self.set_margin_bottom(28)

        self._on_new = on_new
        self._on_run_now = on_run_now
        self._on_changed = on_changed
        self._workspace = workspace
        self._filter = "All"

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="Scheduled", xalign=0)
        title.add_css_class("hero-title")
        titles.append(title)
        titles.append(body("Recurring prompts the agent runs while Gemini is "
                           "open."))
        head.append(titles)
        head.append(hspacer())
        new_btn = pill_button("New schedule", "add", primary=True,
                              on_click=self._create)
        new_btn.set_valign(Gtk.Align.CENTER)
        head.append(new_btn)
        self.append(head)
        self.append(spacer(height=20))

        self._segmented = segmented(list(FILTERS), active=0,
                                    on_select=self._on_filter)
        self.append(self._segmented)
        self.append(spacer(height=20))

        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.append(self._list)
        self.refresh()

    # -- data ---------------------------------------------------------------
    def refresh(self) -> None:
        while (child := self._list.get_first_child()) is not None:
            self._list.remove(child)

        schedules = store.list_schedules()
        shown = [s for s in schedules if self._matches(s)]

        if shown:
            for schedule in shown:
                self._list.append(self._schedule_card(schedule))
        else:
            self._list.append(self._empty_state())

        self._list.append(section_title("Suggested", "auto_awesome"))
        for suggestion in store.SUGGESTIONS:
            self._list.append(self._suggestion_card(suggestion))

    def _matches(self, schedule: store.Schedule) -> bool:
        if self._filter == "All":
            return True
        if self._filter == "Active":
            return not schedule.paused
        if self._filter == "Paused":
            return schedule.paused
        if self._filter == "Completed":
            return bool(schedule.runs) and schedule.paused
        return True

    def _on_filter(self, index: int) -> None:
        self._filter = FILTERS[index]
        self.refresh()

    # -- cards --------------------------------------------------------------
    def _empty_state(self) -> Gtk.Widget:
        panel = card(inset=True)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_margin_top(28)
        inner.set_margin_bottom(28)
        inner.set_halign(Gtk.Align.CENTER)
        icon = icon_square("schedule", "", 22)
        icon.set_halign(Gtk.Align.CENTER)
        inner.append(icon)
        title = Gtk.Label(label="No schedules yet")
        title.add_css_class("card-title")
        inner.append(title)
        copy = body("A schedule is a recurring prompt: every weekday at nine, "
                    "every Monday at five. Gemini starts a fresh conversation "
                    "each time and notifies you when it is done.")
        copy.set_justify(Gtk.Justification.CENTER)
        copy.set_halign(Gtk.Align.CENTER)
        copy.set_max_width_chars(64)
        inner.append(copy)
        panel.append(inner)
        return panel

    def _schedule_card(self, schedule: store.Schedule) -> Gtk.Widget:
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for m in ("start", "end"):
            getattr(inner, f"set_margin_{m}")(18)
        inner.set_margin_top(14)
        inner.set_margin_bottom(14)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        badge = icon_square("schedule", "", 18)
        badge.set_valign(Gtk.Align.START)
        head.append(badge)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        col.set_hexpand(True)
        title = Gtk.Label(label=schedule.title, xalign=0)
        title.add_css_class("card-title")
        col.append(title)
        trigger = Gtk.Label(label=schedule.description, xalign=0)
        trigger.add_css_class("metric-sub")
        col.append(trigger)
        col.append(body(schedule.prompt))
        head.append(col)

        status = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        status.set_valign(Gtk.Align.START)
        chip = Gtk.Label(label="Paused" if schedule.paused else "Active")
        chip.add_css_class("chip-grade")
        status.append(chip)
        if not schedule.paused and schedule.next_run:
            nxt = Gtk.Label(label=_relative(schedule.next_run))
            nxt.add_css_class("metric-sub")
            nxt.set_halign(Gtk.Align.END)
            status.append(nxt)
        head.append(status)
        inner.append(head)

        if schedule.runs:
            inner.append(spacer(height=10))
            last = schedule.runs[-1]
            run_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            run_box.add_css_class("work-panel")
            head_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                               spacing=8)
            line = Gtk.Label(
                label=f"Last run {_when(last.started)} · {last.status.lower()}",
                xalign=0)
            line.add_css_class("work-item")
            line.set_hexpand(True)
            head_row.append(line)
            if last.conversation_id:
                open_thread = Gtk.Button(label="Open thread")
                open_thread.add_css_class("chip-grade")
                open_thread.connect(
                    "clicked",
                    lambda _b, cid=last.conversation_id:
                    self._on_open_thread(cid))
                head_row.append(open_thread)
            run_box.append(head_row)
            if last.text:
                preview = Gtk.Label(label=last.text.replace("\n", " ")[:220],
                                    xalign=0)
                preview.add_css_class("tool-detail")
                preview.set_ellipsize(3)
                preview.set_lines(2)
                run_box.append(preview)
            inner.append(run_box)

        inner.append(spacer(height=10))
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        pause = Gtk.Button(label="Resume" if schedule.paused else "Pause")
        pause.add_css_class("chip-grade")
        pause.connect("clicked", lambda _b, s=schedule: self._toggle(s))
        controls.append(pause)

        run = Gtk.Button(label="Run now")
        run.add_css_class("chip-grade")
        run.connect("clicked", lambda _b, s=schedule: self._run(s))
        controls.append(run)

        controls.append(hspacer())

        remove = Gtk.Button(label="Delete")
        remove.add_css_class("chip-grade")
        remove.connect("clicked", lambda _b, s=schedule: self._delete(s))
        controls.append(remove)
        inner.append(controls)

        panel.append(inner)
        return panel

    def _suggestion_card(self, suggestion: store.Suggestion) -> Gtk.Widget:
        panel = card(inset=True)
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        for m in ("start", "end"):
            getattr(inner, f"set_margin_{m}")(18)
        inner.set_margin_top(12)
        inner.set_margin_bottom(12)

        badge = icon_square("auto_awesome", "", 18)
        badge.set_valign(Gtk.Align.START)
        inner.append(badge)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        col.set_hexpand(True)
        title = Gtk.Label(label=suggestion.title, xalign=0)
        title.add_css_class("card-title")
        col.append(title)
        trigger = Gtk.Label(label=store.describe_cron(suggestion.cron),
                            xalign=0)
        trigger.add_css_class("metric-sub")
        col.append(trigger)
        col.append(body(suggestion.prompt))
        inner.append(col)

        use = pill_button("Use", "add",
                          on_click=lambda: self._use_suggestion(suggestion))
        use.set_valign(Gtk.Align.CENTER)
        inner.append(use)
        panel.append(inner)
        return panel

    # -- actions ------------------------------------------------------------
    def _use_suggestion(self, suggestion: store.Suggestion) -> None:
        schedule = store.Schedule(title=suggestion.title,
                                  prompt=suggestion.prompt,
                                  cron=suggestion.cron,
                                  mode=session_mod.MODE_TASK,
                                  workspace=self._workspace)
        store.save(schedule)
        self.refresh()
        if self._on_changed:
            self._on_changed()

    def _toggle(self, schedule: store.Schedule) -> None:
        store.set_paused(schedule.id, not schedule.paused)
        self.refresh()
        if self._on_changed:
            self._on_changed()

    def _run(self, schedule: store.Schedule) -> None:
        if self._on_run_now:
            self._on_run_now(schedule)
        self.refresh()

    def _delete(self, schedule: store.Schedule) -> None:
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            heading="Delete this schedule?",
            body=f"“{schedule.title}” will stop running. Its history is "
                 f"discarded.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete",
                                       Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(dlg, response):
            if response == "delete":
                store.delete(schedule.id)
                self.refresh()
                if self._on_changed:
                    self._on_changed()

        dialog.connect("response", on_response)
        dialog.present()

    # -- creation -----------------------------------------------------------
    def _create(self) -> None:
        if self._on_new:
            self._on_new()
        else:
            self.show_create_dialog()

    def show_create_dialog(self) -> None:
        """The new-schedule form."""
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(), heading="New schedule",
            body="Choose a name, what to ask, and when to run it.")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(8)

        name = Gtk.Entry()
        name.set_placeholder_text("Name, e.g. Morning briefing")
        box.append(name)

        prompt = Gtk.TextView()
        prompt.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        prompt.set_size_request(-1, 92)
        prompt.add_css_class("composer")
        frame = Gtk.Box()
        frame.add_css_class("search-field")
        frame.append(prompt)
        box.append(frame)

        timing = Gtk.DropDown.new_from_strings([
            "Every day at 09:00",
            "Every weekday at 09:00",
            "Every day at 18:00",
            "Every Monday at 17:00",
            "Every hour",
        ])
        timing.set_selected(1)
        box.append(timing)

        error = Gtk.Label(label="", xalign=0)
        error.add_css_class("error-box")
        error.set_visible(False)
        box.append(error)

        dialog.set_extra_child(box)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("create", "Create")
        dialog.set_response_appearance("create",
                                       Adw.ResponseAppearance.SUGGESTED)

        crons = ("0 9 * * *", "0 9 * * 1-5", "0 18 * * *", "0 17 * * 1",
                 "0 * * * *")

        def on_response(dlg, response):
            if response != "create":
                return
            title_text = name.get_text().strip()
            buf = prompt.get_buffer()
            text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(),
                                False).strip()
            if not title_text or not text:
                error.set_text("A schedule needs a name and a prompt.")
                error.set_visible(True)
                dlg.present()
                return
            cron = crons[max(0, min(timing.get_selected(), len(crons) - 1))]
            try:
                store.validate_cron(cron)
            except ValueError as exc:
                error.set_text(str(exc))
                error.set_visible(True)
                dlg.present()
                return
            schedule = store.Schedule(
                title=title_text, prompt=text, cron=cron,
                mode=session_mod.MODE_TASK, workspace=self._workspace)
            if not store.save(schedule):
                error.set_text("Could not save the schedule.")
                error.set_visible(True)
                dlg.present()
                return
            self.refresh()
            if self._on_changed:
                self._on_changed()

        dialog.connect("response", on_response)
        dialog.present()
