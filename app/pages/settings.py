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

from app import account as account_mod
from app import engine as engine_mod
from app import calendar as calendar_store
from app import permissions
from app import remote
from app import session as session_mod
from app import theme  # noqa: E402
from app.cards import (body, card, divider, eyebrow, hspacer, icon_square,
                       pill_button, section_title, segmented, spacer)


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
        }
        self._scheme = scheme
        self._approval = approval
        self._effort = effort
        self._workspace = workspace
        self._models = models or []
        self._capabilities = frozenset(capabilities or ())
        self._engine_name = engine_name

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

        if "remote" in self._capabilities:
            self.append(section_title("Connectivity", "devices"))
            self.append(spacer(height=12))
            self.append(self._remote_card())
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

        if "permission_file" in self._capabilities:
            writable = permissions.writable()
            state = Gtk.Label(label="Writable" if writable else "Read-only")
            state.add_css_class("chip-grade")
            inner.append(_row(
                "save", "Permission file",
                f"{permissions.config_path()} — "
                + ("grants are saved here." if writable
                   else "this machine blocks writes, so approvals cannot persist."),
                state))
        panel.append(inner)
        return panel

    def _remote_card(self) -> Gtk.Widget:
        """Remote control: drive this machine's agent from a phone."""
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for m in ("start", "end"):
            getattr(inner, f"set_margin_{m}")(18)
        inner.set_margin_top(6)
        inner.set_margin_bottom(6)

        status = remote.status() if remote.available() else None
        self._remote_status = status

        control = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        state_chip = Gtk.Label(label=status.label if status else "Unavailable")
        state_chip.add_css_class("chip-grade")
        control.append(state_chip)

        button = pill_button(
            "Stop" if (status and status.running) else "Start",
            "stop" if (status and status.running) else "play_arrow",
            on_click=self._toggle_remote)
        control.append(button)

        detail = ("Let the Gemini app on your phone reach this machine. "
                  "Pairing uses the same Google account.")
        if status and status.instance:
            detail += f" Instance: {status.instance}."
        inner.append(_row("devices", "Remote control", detail, control))
        panel.append(inner)
        return panel

    def _toggle_remote(self) -> None:
        status = self._remote_status
        if status and status.running:
            ok, output = remote.stop()
        else:
            ok, output = remote.start()
        if not ok:
            # the daemon needs to write its token into the engine's config, so
            # a locked-down home is the usual cause
            dialog = Adw.MessageDialog(
                transient_for=self.get_root(),
                heading="Remote control could not start",
                body=(output or "The engine did not report why.").strip()[:400])
            dialog.add_response("close", "Close")
            dialog.present()
            return
        root = self.get_root()
        if root is not None and hasattr(root, "_refresh_settings"):
            root._refresh_settings()

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

        trusted = permissions.trusted_folders()
        count = Gtk.Label(label=f"{len(trusted)} trusted")
        count.add_css_class("chip-grade")
        detail = (", ".join(trusted[:2]) + ("…" if len(trusted) > 2 else "")
                  if trusted else "No folders trusted yet.")
        inner.append(_row("check_circle", "Trusted folders", detail, count))
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
        acc = account_mod.load_account()
        inner.append(_row("info", "About this app",
                          f"Signed in as {acc.email or 'nobody'}.", about))
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
