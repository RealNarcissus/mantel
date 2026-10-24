"""Settings: the app and agent defaults.

The desktop agents put appearance, agent behaviour and the working folder in
one place; this page follows that, and keeps to the same monospaced card
language as the rest of the shell.
"""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from app import calendar as calendar_store
from app import knowledge as knowledge_store
from app import nudges as nudges_store
from app import session as session_mod
from app.cards import (
    body,
    card,
    divider,
    hspacer,
    icon_square,
    pill_button,
    section_title,
    segmented,
    spacer,
)


def _row(icon_name: str, title: str, detail: str,
         control: Gtk.Widget | None = None) -> Gtk.Widget:
    """A settings row: icon, title, explanation, control on the right."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
    row.set_margin_top(12)
    row.set_margin_bottom(12)

    badge = icon_square(icon_name, "", 18)
    badge.set_valign(Gtk.Align.CENTER)
    row.append(badge)

    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    col.set_hexpand(True)
    lbl = Gtk.Label(label=title, xalign=0)
    lbl.add_css_class("card-title")
    col.append(lbl)
    if detail:
        col.append(body(detail))
    row.append(col)

    row.append(hspacer())
    if control is not None:
        control.set_valign(Gtk.Align.CENTER)
        row.append(control)
    return row


class SettingsPage(Gtk.Box):
    """Appearance, agent defaults, workspace and diagnostics."""

    def __init__(self,
                 on_theme: Callable[[str], None] | None = None,
                 on_approval: Callable[[str], None] | None = None,
                 on_effort: Callable[[str], None] | None = None,
                 on_workspace: Callable[[], None] | None = None,
                 on_shortcuts: Callable[[], None] | None = None,
                 on_about: Callable[[], None] | None = None,
                 on_calendar: Callable[[], None] | None = None,
                 on_nudges: Callable[[], None] | None = None,
                 on_knowledge: Callable[[], None] | None = None,
                 scheme: str = "light",
                 approval: str = "ask",
                 effort: str = "medium",
                 workspace: str = "",
                 models: list[tuple[str, str]] | None = None,
                 capabilities: frozenset[str] | None = None,
                 engine_name: str = "") -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("content")
        self.set_margin_start(36)
        self.set_margin_end(36)
        self.set_margin_top(8)
        self.set_margin_bottom(28)

        self._callbacks = {
            "theme": on_theme, "approval": on_approval, "effort": on_effort,
            "workspace": on_workspace, "shortcuts": on_shortcuts,
            "about": on_about,
            "calendar": on_calendar,
            "nudges": on_nudges,
            "knowledge": on_knowledge,
        }
        self._scheme = scheme
        self._approval = approval
        self._effort = effort
        self._workspace = workspace
        self._models = models or []
        self._capabilities = frozenset(capabilities or ())
        self._engine_name = engine_name

        self._build()

    def refresh(self) -> None:
        """Re-read the stores this page summarises (settings, not layout)."""
        self._build()

    def _build(self) -> None:
        """(Re)build the page, so sources edited elsewhere show up."""
        while (child := self.get_first_child()) is not None:
            self.remove(child)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="Settings", xalign=0)
        title.add_css_class("hero-title")
        titles.append(title)
        titles.append(body("How the app looks, and what the agent may do."))
        head.append(titles)
        self.append(head)
        self.append(spacer(height=24))

        self.append(section_title("Appearance", "light_mode"))
        self.append(spacer(height=12))
        self.append(self._appearance_card())
        self.append(spacer(height=22))

        self.append(section_title("Agent", "gemini_spark"))
        self.append(spacer(height=12))
        self.append(self._agent_card())
        self.append(spacer(height=22))

        self.append(section_title("Knowledge", "notes_spark"))
        self.append(spacer(height=12))
        self.append(self._knowledge_card())
        self.append(spacer(height=22))

        self.append(section_title("Proactivity", "notifications"))
        self.append(spacer(height=12))
        self.append(self._nudges_card())
        self.append(spacer(height=22))

        self.append(section_title("Calendar", "calendar_month"))
        self.append(spacer(height=12))
        self.append(self._calendar_card())
        self.append(spacer(height=22))

        self.append(section_title("Workspace", "folder"))
        self.append(spacer(height=12))
        self.append(self._workspace_card())
        self.append(spacer(height=22))

        self.append(section_title("About", "info"))
        self.append(spacer(height=12))
        self.append(self._about_card())
    # -- cards --------------------------------------------------------------
    # -- cards --------------------------------------------------------------
    def _appearance_card(self) -> Gtk.Widget:
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for m in ("start", "end"):
            getattr(inner, f"set_margin_{m}")(18)
        inner.set_margin_top(6)
        inner.set_margin_bottom(6)

        themes = segmented(["Light", "Dark", "System"],
                           active={"light": 0, "dark": 1, "system": 2}.get(
                               self._scheme, 0),
                           on_select=self._on_theme)
        inner.append(_row("contrast", "Theme",
                          "Follow the reference design, or the desktop's "
                          "preference.", themes))
        panel.append(inner)
        return panel

    def _agent_card(self) -> Gtk.Widget:
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for m in ("start", "end"):
            getattr(inner, f"set_margin_{m}")(18)
        inner.set_margin_top(6)
        inner.set_margin_bottom(6)

        if "cli_flags" in self._capabilities:
            modes = segmented(
                [m.label for m in session_mod.APPROVAL_MODES],
                active=[m.key for m in session_mod.APPROVAL_MODES].index(
                    self._approval)
                if self._approval in [m.key for m in session_mod.APPROVAL_MODES]
                else 0,
                on_select=self._on_approval)
            inner.append(_row("lock", "Approval mode",
                              "What the agent may do without asking you.", modes))
        else:
            enforced = Gtk.Label(label="Enforced per call")
            enforced.add_css_class("chip-grade")
            inner.append(_row(
                "lock", "Approvals",
                "This engine asks before it acts; every tool call is gated by "
                "the client's approval cards.", enforced))
        inner.append(divider())

        efforts = segmented(["Low", "Medium", "High", "Max"],
                            active={"low": 0, "medium": 1, "high": 2,
                                    "xhigh": 2, "max": 3}.get(self._effort, 1),
                            on_select=self._on_effort)
        inner.append(_row("bolt", "Reasoning effort",
                          "How much thinking the model spends per turn.",
                          efforts))
        inner.append(divider())

        panel.append(inner)
        return panel

    def _agent_card(self) -> Gtk.Widget:
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for m in ("start", "end"):
            getattr(inner, f"set_margin_{m}")(18)
        inner.set_margin_top(6)
        inner.set_margin_bottom(6)

        if "cli_flags" in self._capabilities:
            modes = segmented(
                [m.label for m in session_mod.APPROVAL_MODES],
                active=[m.key for m in session_mod.APPROVAL_MODES].index(
                    self._approval)
                if self._approval in [m.key for m in session_mod.APPROVAL_MODES]
                else 0,
                on_select=self._on_approval)
            inner.append(_row("lock", "Approval mode",
                              "What the agent may do without asking you.", modes))
        else:
            enforced = Gtk.Label(label="Enforced per call")
            enforced.add_css_class("chip-grade")
            inner.append(_row(
                "lock", "Approvals",
                "This engine asks before it acts; every tool call is gated by "
                "the client's approval cards.", enforced))
        inner.append(divider())

        efforts = segmented(["Low", "Medium", "High", "Max"],
                            active={"low": 0, "medium": 1, "high": 2,
                                    "xhigh": 2, "max": 3}.get(self._effort, 1),
                            on_select=self._on_effort)
        inner.append(_row("bolt", "Reasoning effort",
                          "How much thinking the model spends per turn.",
                          efforts))
        inner.append(divider())

        panel.append(inner)
        return panel

    def _knowledge_card(self) -> Gtk.Widget:
        """Folders the agent may read: local notes, read-only, indexed."""
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for margin in ("start", "end"):
            getattr(inner, f"set_margin_{margin}")(18)
        inner.set_margin_top(6)
        inner.set_margin_bottom(6)

        stats = knowledge_store.stats()
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.append(pill_button("Add folder", "add",
                                   on_click=self._add_knowledge))
        reindex = Gtk.Button(label="Reindex")
        reindex.add_css_class("chip-grade")
        reindex.connect("clicked", lambda _b: self._reindex_knowledge())
        buttons.append(reindex)
        inner.append(_row(
            "notes_spark", "Notes folders",
            f"{stats['files']} files · {stats['chunks']} passages indexed. "
            "Read-only; stays on this machine.", buttons))

        sources = knowledge_store.sources()
        inner.append(divider())
        if not sources:
            empty = Gtk.Label(label="No folders indexed yet.", xalign=0)
            empty.add_css_class("metric-sub")
            empty.set_margin_top(6)
            empty.set_margin_bottom(6)
            inner.append(empty)
        for source in sources:
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            line.set_margin_top(6)
            line.set_margin_bottom(6)
            label = Gtk.Label(label=source, xalign=0)
            label.add_css_class("metric-sub")
            label.set_ellipsize(3)
            label.set_hexpand(True)
            line.append(label)
            remove = Gtk.Button(label="Remove")
            remove.add_css_class("chip-grade")
            remove.connect("clicked",
                           lambda _b, s=source: self._remove_knowledge(s))
            line.append(remove)
            inner.append(line)
        panel.append(inner)
        return panel

    def _add_knowledge(self) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Choose a folder of notes")
        from gi.repository import GLib  # noqa: PLC0415

        def done(file_dialog, result):
            try:
                folder = file_dialog.select_folder_finish(result)
            except GLib.Error:
                return
            path = folder.get_path() if folder is not None else None
            if path:
                knowledge_store.add_source(path)
                self._knowledge_changed()

        dialog.select_folder(self.get_root(), None, done)

    def _remove_knowledge(self, source: str) -> None:
        knowledge_store.remove_source(source)
        self._knowledge_changed()

    def _reindex_knowledge(self) -> None:
        knowledge_store.sync(force=True)
        self._knowledge_changed()

    def _knowledge_changed(self) -> None:
        callback = self._callbacks.get("knowledge")
        if callback:
            callback()

    def _nudges_card(self) -> Gtk.Widget:
        """The interruption budget: on/off, how many, and when the brief lands."""
        policy = nudges_store.Proactivity.load()
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for margin in ("start", "end"):
            getattr(inner, f"set_margin_{margin}")(18)
        inner.set_margin_top(6)
        inner.set_margin_bottom(6)

        switch = Gtk.Switch()
        switch.set_active(bool(policy.enabled))
        switch.set_valign(Gtk.Align.CENTER)
        switch.connect("notify::active",
                       lambda widget, _p: self._set_nudges(
                           enabled=widget.get_active()))
        inner.append(_row("notifications", "Nudges",
                          "Bounded interruptions: something starting soon, too "
                          "much late, and one morning brief.", switch))
        inner.append(divider())

        budgets = ["1", "2", "3", "5"]
        active = budgets.index(str(policy.budget)) if str(
            policy.budget) in budgets else 2
        budget = segmented(budgets, active=active,
                           on_select=lambda index: self._set_nudges(
                               budget=budgets[index]))
        inner.append(_row("bell", "Per day",
                          "How many the app may show, across all rules.", budget))
        inner.append(divider())

        hours = ["07:00", "08:00", "09:00", "10:00"]
        run_hours = [7, 8, 9, 10]
        hour_active = run_hours.index(policy.brief_hour) if (
            policy.brief_hour in run_hours) else 1
        brief = segmented(hours, active=hour_active,
                          on_select=lambda index: self._set_nudges(
                              brief_hour=run_hours[index]))
        inner.append(_row("light_mode", "Morning brief",
                          "Once a day, after this hour: what the day holds.",
                          brief))
        panel.append(inner)
        return panel

    def _set_nudges(self, **changes) -> None:
        policy = nudges_store.Proactivity.load()
        for key, value in changes.items():
            setattr(policy, key, value)
        policy.save()
        callback = self._callbacks.get("nudges")
        if callback:
            callback()

    def _calendar_card(self) -> Gtk.Widget:
        """Read-only .ics sources: the day without an account."""
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for margin in ("start", "end"):
            getattr(inner, f"set_margin_{margin}")(18)
        inner.set_margin_top(6)
        inner.set_margin_bottom(6)

        sources = calendar_store.sources()
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        add = pill_button("Add .ics file", "add", on_click=self._add_calendar)
        row.append(add)
        inner.append(_row(
            "calendar_month", "Calendar sources",
            "iCalendar files, read-only. Export from any provider; no account "
            "or network needed.", row))

        if sources:
            inner.append(divider())
            for source in sources:
                line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                               spacing=8)
                line.set_margin_top(6)
                line.set_margin_bottom(6)
                label = Gtk.Label(label=source, xalign=0)
                label.add_css_class("metric-sub")
                label.set_ellipsis if False else None
                label.set_ellipsize(3)
                label.set_hexpand(True)
                line.append(label)
                remove = Gtk.Button(label="Remove")
                remove.add_css_class("chip-grade")
                remove.connect("clicked",
                               lambda _b, s=source: self._remove_calendar(s))
                line.append(remove)
                inner.append(line)
        else:
            inner.append(divider())
            empty = Gtk.Label(label="No calendar connected.", xalign=0)
            empty.add_css_class("metric-sub")
            empty.set_margin_top(6)
            empty.set_margin_bottom(6)
            inner.append(empty)
        panel.append(inner)
        return panel

    def _add_calendar(self) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Choose an .ics file")
        dialog.set_filters(_ics_filters())

        def done(file_dialog, result):
            try:
                folder = file_dialog.open_finish(result)
            except GLib.Error:
                return
            path = folder.get_path() if folder is not None else None
            if not path:
                return
            calendar_store.add_source(path)
            self._calendar_changed()

        from gi.repository import GLib  # noqa: PLC0415

        dialog.open(self.get_root(), None, done)

    def _remove_calendar(self, source: str) -> None:
        calendar_store.remove_source(source)
        self._calendar_changed()

    def _calendar_changed(self) -> None:
        callback = self._callbacks.get("calendar")
        if callback:
            callback()

    def _workspace_card(self) -> Gtk.Widget:
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for m in ("start", "end"):
            getattr(inner, f"set_margin_{m}")(18)
        inner.set_margin_top(6)
        inner.set_margin_bottom(6)

        choose = pill_button("Change folder", "folder", on_click=self._on_workspace)
        inner.append(_row("folder", "Working folder",
                          self._workspace or "not set", choose))
        inner.append(divider())

        note = Gtk.Label(label="asked on change")
        note.add_css_class("chip-grade")
        inner.append(_row(
            "check_circle", "Folder trust",
            "You are asked when you choose a folder, and the engine's approval "
            "gate still checks every action.", note))
        panel.append(inner)
        return panel

    def _about_card(self) -> Gtk.Widget:
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for m in ("start", "end"):
            getattr(inner, f"set_margin_{m}")(18)
        inner.set_margin_top(6)
        inner.set_margin_bottom(6)

        shortcuts = pill_button("Shortcuts", "keyboard",
                                on_click=self._callbacks["shortcuts"])
        inner.append(_row("keyboard", "Keyboard shortcuts",
                          "Enter sends, Esc stops, Ctrl+N starts a chat.",
                          shortcuts))
        inner.append(divider())

        about = pill_button("About", "info", on_click=self._callbacks["about"])
        inner.append(_row("info", "About this app",
                          "Mantel, local-first. No account required.", about))
        inner.append(divider())

        engine = Gtk.Label(label=f"{len(self._models)} models")
        engine.add_css_class("chip-grade")
        detail = self._engine_name or "unknown"
        if self._capabilities:
            detail += " · " + ", ".join(sorted(self._capabilities))
        inner.append(_row("memory", "Agent engine", detail, engine))
        panel.append(inner)
        return panel

    # -- callbacks ----------------------------------------------------------
    def _on_theme(self, index: int) -> None:
        key = ("light", "dark", "system")[index]
        self._scheme = key
        if self._callbacks["theme"]:
            self._callbacks["theme"](key)

    def _on_approval(self, index: int) -> None:
        key = session_mod.APPROVAL_MODES[index].key
        self._approval = key
        if self._callbacks["approval"]:
            self._callbacks["approval"](key)

    def _on_effort(self, index: int) -> None:
        key = ("low", "medium", "high", "max")[index]
        self._effort = key
        if self._callbacks["effort"]:
            self._callbacks["effort"](key)

    def _on_workspace(self) -> None:
        if self._callbacks["workspace"]:
            self._callbacks["workspace"]()


def _ics_filters():
    """A filter for .ics files (and a fallback to everything)."""
    import gi as _gi  # noqa: PLC0415

    _gi.require_version("Gtk", "4.0")
    from gi.repository import Gio as _Gio  # noqa: PLC0415

    filters = _Gio.ListStore.new(Gtk.FileFilter)
    ics = Gtk.FileFilter()
    ics.set_name("Calendar files (.ics)")
    ics.add_pattern("*.ics")
    filters.append(ics)
    everything = Gtk.FileFilter()
    everything.set_name("All files")
    everything.add_pattern("*")
    filters.append(everything)
    return filters
