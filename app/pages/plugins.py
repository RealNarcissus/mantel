"""Plugins: install, inspect, enable, and see what they touched.

The page is deliberately suspicious. Installing shows a capability sheet before
anything runs, every plugin states what it may touch, the audit log is one
click away, and safe mode is a single switch that stops all plugin code — a
plugin system earns trust by making its blast radius legible.
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from app import plugins as store
from app import theme  # noqa: F401  (registers the bundled fonts)
from app.cards import (
    body,
    card,
    divider,
    hspacer,
    icon_square,
    pill_button,
    section_title,
    spacer,
)


def _when(timestamp: float) -> str:
    if not timestamp:
        return ""
    return time.strftime("%d %b %H:%M", time.localtime(timestamp))


class PluginsPage(Gtk.Box):
    """The plugin store: installed plugins and what they may do."""

    def __init__(self, on_changed: Callable[[], None] | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("content")
        self.set_margin_start(36)
        self.set_margin_end(36)
        self.set_margin_top(8)
        self.set_margin_bottom(28)
        self._on_changed = on_changed

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="Plugins", xalign=0)
        title.add_css_class("hero-title")
        titles.append(title)
        titles.append(body("Programs you add to Mantel. They run out of process, "
                           "state what they may touch, and never run on install."))
        head.append(titles)
        head.append(hspacer())
        install = pill_button("Install from folder…", "add", primary=True,
                              on_click=self._install)
        install.set_valign(Gtk.Align.CENTER)
        head.append(install)
        self.append(head)
        self.append(spacer(height=18))

        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.append(self._list)
        self.refresh()

    # -- data ---------------------------------------------------------------
    def refresh(self) -> None:
        while (child := self._list.get_first_child()) is not None:
            self._list.remove(child)

        if store.safe_mode():
            banner = card(inset=True)
            inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            for margin in ("start", "end"):
                getattr(inner, f"set_margin_{margin}")(16)
            inner.set_margin_top(12)
            inner.set_margin_bottom(12)
            label = Gtk.Label(
                label=f"Safe mode is on ({store.SAFE_MODE_ENV}) — no plugin runs.",
                xalign=0)
            label.add_css_class("card-title")
            inner.append(label)
            banner.append(inner)
            self._list.append(banner)

        plugins = store.installed()
        if not plugins:
            self._list.append(self._empty())
        for plugin in plugins:
            self._list.append(self._card(plugin))

        contributed = store.panels("plugins")
        if contributed:
            self._list.append(spacer(height=6))
            self._list.append(section_title("Panels", "tune"))
            for plugin, panel in contributed:
                self._list.append(panel_card(
                    plugin, panel,
                    on_run=lambda p, command: self._run_panel(p, command)))

        audit = store.audit_log(12)
        if audit:
            self._list.append(spacer(height=6))
            self._list.append(section_title("Recent plugin activity", "schedule"))
            panel = card(inset=True)
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            for margin in ("start", "end"):
                getattr(inner, f"set_margin_{margin}")(16)
            inner.set_margin_top(12)
            inner.set_margin_bottom(12)
            for index, entry in enumerate(audit):
                if index:
                    inner.append(divider())
                raw_detail = str(entry.get("detail") or "")
                # never print a home directory or a project path into a
                # screenshot or a shared window: show the folder name, keep the
                # full path in the tooltip
                detail = raw_detail
                if raw_detail.startswith("from "):
                    source = raw_detail[5:].strip().rstrip("/")
                    detail = "from " + (os.path.basename(source) or source)
                else:
                    home = os.path.expanduser("~")
                    if home and home != "/":
                        detail = raw_detail.replace(home, "~")
                row = Gtk.Label(
                    label=f"{_when(float(entry.get('ts') or 0))} · "
                          f"{entry.get('plugin')} · {entry.get('action')} "
                          f"{detail}".strip(),
                    xalign=0)
                row.add_css_class("metric-sub")
                row.set_ellipsize(3)
                if raw_detail != detail:
                    row.set_tooltip_text(raw_detail)
                row.set_margin_top(5)
                row.set_margin_bottom(5)
                inner.append(row)
            panel.append(inner)
            self._list.append(panel)

    def _empty(self) -> Gtk.Widget:
        panel = card(inset=True)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_margin_top(28)
        inner.set_margin_bottom(28)
        inner.set_halign(Gtk.Align.CENTER)
        icon = icon_square("tune", "", 22)
        icon.set_halign(Gtk.Align.CENTER)
        inner.append(icon)
        title = Gtk.Label(label="No plugins installed")
        title.add_css_class("card-title")
        inner.append(title)
        copy = body("A plugin is a folder with a mantel.json and the program it "
                    "runs. Install one from a folder to see what it asks for "
                    "before anything runs.")
        copy.set_justify(Gtk.Justification.CENTER)
        copy.set_max_width_chars(62)
        copy.set_halign(Gtk.Align.CENTER)
        inner.append(copy)
        panel.append(inner)
        return panel

    def _card(self, plugin: store.Plugin) -> Gtk.Widget:
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for margin in ("start", "end"):
            getattr(inner, f"set_margin_{margin}")(18)
        inner.set_margin_top(14)
        inner.set_margin_bottom(14)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        badge = icon_square("extension", "", 18)
        badge.set_valign(Gtk.Align.START)
        head.append(badge)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        col.set_hexpand(True)
        title = Gtk.Label(label=f"{plugin.manifest.name} "
                               f"{plugin.manifest.version}", xalign=0)
        title.add_css_class("card-title")
        col.append(title)
        meta = [plugin.manifest.id, f"installed {_when(plugin.installed)}"]
        if plugin.manifest.author:
            meta.insert(1, plugin.manifest.author)
        detail = Gtk.Label(label=" · ".join(meta), xalign=0)
        detail.add_css_class("metric-sub")
        col.append(detail)
        if plugin.manifest.description:
            col.append(body(plugin.manifest.description))
        head.append(col)

        toggle = Gtk.Switch()
        toggle.set_active(plugin.enabled)
        toggle.set_valign(Gtk.Align.CENTER)
        toggle.connect("notify::active", lambda widget, _p: self._set_enabled(
            plugin, widget.get_active()))
        head.append(toggle)
        inner.append(head)

        # --- capability sheet ----------------------------------------------
        inner.append(spacer(height=8))
        caps = plugin.manifest.capabilities
        cap_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        cap_row.set_halign(Gtk.Align.START)
        for capability in caps:
            chip = Gtk.Label(label=capability)
            chip.add_css_class("chip-grade")
            cap_row.append(chip)
        inner.append(cap_row)

        # --- commands -------------------------------------------------------
        if plugin.manifest.commands:
            inner.append(spacer(height=8))
            commands = Gtk.Label(
                label="commands: " + ", ".join(
                    command["title"] for command in plugin.manifest.commands)
                      + "  (available in Ctrl+K)",
                xalign=0)
            commands.add_css_class("metric-sub")
            inner.append(commands)

        inner.append(spacer(height=10))
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        run = Gtk.Button(label="Run a command")
        run.add_css_class("chip-grade")
        run.set_sensitive(plugin.enabled and bool(plugin.manifest.commands))
        run.connect("clicked", lambda _b: self._run(plugin))
        controls.append(run)
        controls.append(hspacer())
        remove = Gtk.Button(label="Uninstall")
        remove.add_css_class("chip-grade")
        remove.connect("clicked", lambda _b: self._remove(plugin))
        controls.append(remove)
        inner.append(controls)

        panel.append(inner)
        return panel

    def _run_panel(self, plugin: store.Plugin, command_id: str) -> None:
        ok, result = store.run_command(plugin, command_id,
                                       store.context(plugin))
        if not ok:
            self._error(f"{plugin.manifest.name} failed", str(result))
            return
        message = ""
        if isinstance(result, dict):
            message = str(result.get("message") or result.get("text") or "")
        elif result is not None:
            message = str(result)
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(), heading=plugin.manifest.name,
            body=message[:800] or "Done.")
        dialog.add_response("close", "Close")
        dialog.present()

    # -- actions ------------------------------------------------------------
    def _install(self) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Choose a plugin folder")

        def done(file_dialog, result):
            try:
                folder = file_dialog.select_folder_finish(result)
            except GLib.Error:
                return
            if folder is None:
                return
            path = folder.get_path()
            if not path:
                return
            self._confirm_install(path)

        from gi.repository import GLib  # noqa: PLC0415

        dialog.select_folder(self.get_root(), None, done)

    def _confirm_install(self, path: str) -> None:
        """Show what the plugin asks for *before* copying it in."""
        from pathlib import Path  # noqa: PLC0415

        manifest_path = Path(path) / "mantel.json"
        try:
            import json  # noqa: PLC0415

            raw = json.loads(manifest_path.read_text())
        except (OSError, ValueError) as error:
            self._error("This folder has no readable mantel.json.",
                        str(error))
            return
        manifest, problems = store.parse_manifest(raw)
        if manifest is None:
            self._error("That manifest is not valid.", "\n".join(problems))
            return

        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            heading=f"Install {manifest.name}?",
            body="Review what it may touch. Nothing runs until you use it.")
        caps = Gtk.Label(label="\n".join(f"• {item}"
                                         for item in manifest.capabilities),
                         xalign=0)
        caps.add_css_class("metric-sub")
        caps.set_margin_top(8)
        dialog.set_extra_child(caps)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("install", "Install")
        dialog.set_response_appearance("install",
                                       Adw.ResponseAppearance.SUGGESTED)

        def on_response(dlg, response):
            if response != "install":
                return
            plugin, errors = store.install(Path(path))
            if plugin is None:
                self._error("The plugin could not be installed.",
                            "\n".join(errors))
                return
            self.refresh()
            if self._on_changed:
                self._on_changed()

        dialog.connect("response", on_response)
        dialog.present()

    def _error(self, heading: str, detail: str) -> None:
        dialog = Adw.MessageDialog(transient_for=self.get_root(),
                                   heading=heading, body=detail[:600])
        dialog.add_response("close", "Close")
        dialog.present()

    def _set_enabled(self, plugin: store.Plugin, enabled: bool) -> None:
        store.set_enabled(plugin.manifest.id, enabled)
        if self._on_changed:
            self._on_changed()

    def _remove(self, plugin: store.Plugin) -> None:
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            heading=f"Uninstall {plugin.manifest.name}?",
            body="Its folder is deleted. Your tasks, memory and conversations "
                 "are untouched.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("remove", "Uninstall")
        dialog.set_response_appearance("remove",
                                       Adw.ResponseAppearance.DESTRUCTIVE)

        def on_response(dlg, response):
            if response == "remove":
                store.remove(plugin.manifest.id)
                self.refresh()
                if self._on_changed:
                    self._on_changed()

        dialog.connect("response", on_response)
        dialog.present()

    def _run(self, plugin: store.Plugin) -> None:
        """Run the plugin's first command with the pieces it is allowed to see."""
        if not plugin.manifest.commands:
            return
        command = plugin.manifest.commands[0]
        context = self._context(plugin)
        ok, result = store.run_command(plugin, command["id"], context)
        if not ok:
            self._error(f"{plugin.manifest.name} failed", str(result))
            return
        message = ""
        if isinstance(result, dict):
            message = str(result.get("message") or result.get("text") or "")
        elif result is not None:
            message = str(result)
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            heading=plugin.manifest.name,
            body=message[:800] or "Done.")
        dialog.add_response("close", "Close")
        dialog.present()

    def _context(self, plugin: store.Plugin) -> dict:
        """Only what this plugin declared it may see."""
        return store.context(plugin)


def panel_card(plugin, panel: dict, on_run) -> Gtk.Widget:
    """Render one declarative panel: a titled card of command rows."""
    panel_widget = card()
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    for margin in ("start", "end"):
        getattr(inner, f"set_margin_{margin}")(18)
    inner.set_margin_top(14)
    inner.set_margin_bottom(14)

    head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    badge = icon_square("extension", "", 16)
    head.append(badge)
    title = Gtk.Label(label=str(panel.get("title") or plugin.manifest.name),
                      xalign=0)
    title.add_css_class("card-title")
    head.append(title)
    head.append(hspacer())
    source = Gtk.Label(label=plugin.manifest.name)
    source.add_css_class("metric-sub")
    head.append(source)
    inner.append(head)

    for index, row in enumerate(panel.get("rows") or []):
        if index:
            inner.append(divider())
        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        line.set_margin_top(6)
        line.set_margin_bottom(6)
        label = Gtk.Label(label=str(row.get("label") or ""), xalign=0)
        label.set_hexpand(True)
        line.append(label)
        button = Gtk.Button(label="Run")
        button.add_css_class("chip-grade")
        command = str(row.get("command") or "")
        button.connect("clicked", lambda _b, c=command: on_run(plugin, c))
        line.append(button)
        inner.append(line)

    panel_widget.append(inner)
    return panel_widget
