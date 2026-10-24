"""Connectors: the MCP servers the agent can call.

The real desktop app calls MCP servers "Connectors"; this page is where they
are added, switched on and off, and removed.  The servers themselves live in
``~/.gemini/config/mcp_config.json``, which :mod:`app.mcp` owns — this page
only talks to that layer and never writes the configuration itself.

Everything on the page is built from the shared primitives in :mod:`app.cards`
and the tokens in :mod:`app.theme`; no colours or CSS classes are hard-coded.
"""
from __future__ import annotations

from collections.abc import Callable

from app import theme  # noqa: F401  (registers the bundled fonts before Gtk)

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GObject, Gtk, Pango  # noqa: E402

from app import mcp  # noqa: E402
from app.cards import (body, card, eyebrow, icon_square, pill_button,  # noqa: E402
                       section_title, spacer, title)

#: The kinds a connector can have, as they are shown to the user.
KIND_LABELS = {"stdio": "stdio", "http": "HTTP"}


# --- helpers ----------------------------------------------------------------


def _is_dark(colour: str) -> bool:
    """True when a CSS colour is dark enough to need light glyphs on top."""
    rgba = Gdk.RGBA()
    rgba.parse(colour)
    luminance = 0.2126 * rgba.red + 0.7152 * rgba.green + 0.0722 * rgba.blue
    return luminance < 0.5


def _pill(label: str, icon_name: str = "", primary: bool = False,
          on_click: Callable[[], None] | None = None) -> Gtk.Button:
    """``cards.pill_button`` with a glyph that stays legible on the pill.

    The bundled icons are white in their base rendering and navy in the "dark"
    tone, so a black pill needs the white one and a light pill the muted one.
    """
    button = pill_button(label, icon_name, primary=primary, on_click=on_click)
    button.set_valign(Gtk.Align.CENTER)
    if icon_name:
        scheme = theme.scheme()
        row = button.get_child()
        image = row.get_first_child() if row is not None else None
        if isinstance(image, Gtk.Image):
            if primary:
                tone = "white" if _is_dark(scheme.pill_bg) else scheme.on_accent
            else:
                tone = ""
            image.set_from_paintable(theme.icon_texture(icon_name, tone))
    return button


def _field(caption: str, control: Gtk.Widget) -> Gtk.Box:
    """A labelled form control: the caption sits above the widget."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.append(eyebrow(caption))
    control.set_hexpand(True)
    box.append(control)
    return box


def _wrap_entry(entry: Gtk.Entry) -> Gtk.Box:
    """Put an entry inside the shell's field chrome.

    ``.search-field`` is the only rounded field in the stylesheet, so the
    dialog form reuses it rather than inventing a class of its own.
    """
    field = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    field.add_css_class("search-field")
    entry.add_css_class("search-entry")
    entry.set_hexpand(True)
    field.append(entry)
    return field


def _ellipsize(label: Gtk.Label) -> Gtk.Label:
    """Let a single-line label shrink instead of overflowing its card."""
    label.set_ellipsize(Pango.EllipsizeMode.END)
    return label


def _clear(box: Gtk.Box) -> None:
    """Empty a box (GTK4 has no ``get_children``)."""
    child = box.get_first_child()
    while child is not None:
        following = child.get_next_sibling()
        box.remove(child)
        child = following


# --- the page ---------------------------------------------------------------


class ConnectorsPage(Gtk.Box):
    """The Connectors page: the MCP servers the agent can use."""

    def __init__(self, on_changed: Callable[[], None] | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("content")
        self.set_vexpand(True)
        # the page's own margins, per the page contract
        self.set_margin_start(36)
        self.set_margin_end(36)
        self.set_margin_top(8)
        self.set_margin_bottom(28)

        self._on_changed = on_changed
        self._muting = False
        self._banner: Gtk.Widget | None = None

        self._cards = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._banner_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._content.append(self._banner_slot)
        self._content.append(self._build_header())
        self._content.append(spacer(height=26))
        self._content.append(section_title("Installed", "extension"))
        self._content.append(spacer(height=14))
        self._content.append(self._cards)
        self._content.append(spacer(height=22))
        self._content.append(self._build_footer())

        scroll.set_child(self._content)
        self.append(scroll)
        self.refresh()

    # -- construction -------------------------------------------------------
    def _build_header(self) -> Gtk.Widget:
        """The page heading, with the add button on the right."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        row.set_valign(Gtk.Align.CENTER)

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        labels.append(title("Connectors", 24))
        labels.append(body("MCP servers the agent can call for extra tools."))
        row.append(labels)

        gap = Gtk.Box()
        gap.set_hexpand(True)
        row.append(gap)
        row.append(_pill("Add server", "add", primary=True,
                         on_click=self._open_add_dialog))
        return row

    def _build_footer(self) -> Gtk.Widget:
        """The muted note that closes the page."""
        note = body("Connectors give the agent extra tools — reading files, "
                    "querying services, running commands. Anything that writes "
                    "or deletes still asks for your approval first.")
        note.set_margin_top(2)
        return note

    # -- the list -----------------------------------------------------------
    def refresh(self) -> None:
        """Rebuild the list of servers from the configuration."""
        _clear(self._cards)

        servers = mcp.list_servers()
        if not servers:
            self._cards.append(self._empty_state())
            return
        for server in servers:
            self._cards.append(self._server_card(server))

    def _server_card(self, server: mcp.Server) -> Gtk.Widget:
        """One installed server: its name, its target and its controls."""
        panel = card()
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        row.set_margin_start(18)
        row.set_margin_end(18)
        row.set_margin_top(16)
        row.set_margin_bottom(16)

        badge = icon_square("extension", "", 20)
        badge.set_valign(Gtk.Align.START)
        row.append(badge)

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        labels.set_hexpand(True)
        labels.set_valign(Gtk.Align.CENTER)
        labels.append(_ellipsize(title(server.name, 15)))
        kind = KIND_LABELS.get(server.kind, server.kind)
        labels.append(body(f"{kind} · {server.target}"))
        row.append(labels)

        controls = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        controls.set_valign(Gtk.Align.CENTER)

        switch = Gtk.Switch()
        switch.set_active(server.enabled)
        switch.set_halign(Gtk.Align.END)
        switch.set_valign(Gtk.Align.CENTER)
        switch.set_tooltip_text("Enable this connector")
        switch.connect("notify::active", self._on_switch, server.name)
        controls.append(switch)

        remove = icon_square("delete", "Remove")
        remove.set_halign(Gtk.Align.END)
        remove.connect("clicked", lambda _b, n=server.name: self._confirm_remove(n))
        controls.append(remove)

        row.append(controls)
        panel.append(row)
        return panel

    def _empty_state(self) -> Gtk.Widget:
        """Shown when no connector is configured yet."""
        panel = card(inset=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(26)
        box.set_margin_end(26)
        box.set_margin_top(24)
        box.set_margin_bottom(24)

        badge = icon_square("extension", "", 22)
        badge.set_halign(Gtk.Align.START)
        box.append(badge)
        box.append(title("No connectors yet", 15))
        box.append(body("A connector is an MCP server: a small program that "
                        "gives the agent extra tools, such as reading files, "
                        "querying a service or searching the web. Add one to "
                        "give the agent more to work with."))
        add = _pill("Add server", "add", on_click=self._open_add_dialog)
        add.set_halign(Gtk.Align.START)
        box.append(add)

        panel.append(box)
        return panel

    # -- mutations ----------------------------------------------------------
    def _on_switch(self, switch: Gtk.Switch, _spec: GObject.ParamSpec,
                   name: str) -> None:
        """Enable or disable a server, and put the switch back on failure."""
        if self._muting:
            return
        value = switch.get_active()
        if not mcp.set_enabled(name, value):
            self._muting = True
            switch.set_active(not value)
            self._muting = False
            self._flash(f"Could not update {name}.", False)
            return
        self._changed()

    def _confirm_remove(self, name: str) -> None:
        """Ask before a server is removed."""
        dialog = Adw.MessageDialog(
            transient_for=self._window(),
            heading=f"Remove {name}?",
            body="The agent will no longer be able to call this connector. "
                 "Its tools disappear from every conversation.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("remove", "Remove")
        dialog.set_response_appearance("remove",
                                       Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        dialog.set_default_response("cancel")
        dialog.connect("response", self._on_remove_response, name)
        dialog.present()

    def _on_remove_response(self, dialog: Adw.MessageDialog, response: str,
                            name: str) -> None:
        """Carry out a confirmed removal."""
        if response != "remove":
            return
        if not mcp.remove_server(name):
            self._flash(f"Could not remove {name}.", False)
            return
        self.refresh()
        self._changed()

    # -- the add dialog -----------------------------------------------------
    def _open_add_dialog(self) -> None:
        """Open the modal form that adds a new server."""
        dialog = Adw.MessageDialog(
            transient_for=self._window(),
            heading="Add a connector",
            body="Point the agent at an MCP server. A stdio server is run as "
                 "a command; an HTTP server is reached over the network.",
        )

        self._name_entry = Gtk.Entry()
        self._name_entry.set_placeholder_text("filesystem")
        self._name_entry.set_max_length(64)

        self._type = Gtk.DropDown.new_from_strings(["stdio", "HTTP"])
        self._type.set_hexpand(True)

        self._command_entry = Gtk.Entry()
        self._command_entry.set_placeholder_text("npx -y @modelcontextprotocol/server-filesystem")

        self._args_entry = Gtk.Entry()
        self._args_entry.set_placeholder_text("--root ~/projects")

        self._url_entry = Gtk.Entry()
        self._url_entry.set_placeholder_text("https://example.com/mcp")

        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        form.append(_field("Name", _wrap_entry(self._name_entry)))
        form.append(_field("Type", self._type))

        self._stdio_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self._stdio_rows.append(_field("Command",
                                       _wrap_entry(self._command_entry)))
        self._stdio_rows.append(_field("Arguments",
                                       _wrap_entry(self._args_entry)))
        form.append(self._stdio_rows)

        self._url_row = _field("Server URL", _wrap_entry(self._url_entry))
        form.append(self._url_row)

        self._error = Gtk.Label(label="", xalign=0)
        self._error.add_css_class("error-box")
        self._error.set_wrap(True)
        self._error.set_visible(False)
        form.append(self._error)

        dialog.set_extra_child(form)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("add", "Add")
        dialog.set_response_appearance("add", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_close_response("cancel")
        dialog.set_default_response("add")

        self._type.connect("notify::selected", self._on_type_changed)
        self._apply_type()

        dialog.connect("response", self._on_add_response)
        dialog.present()

    def _apply_type(self) -> None:
        """Show the fields that belong to the selected kind."""
        http = self._type.get_selected() == 1
        self._stdio_rows.set_visible(not http)
        self._url_row.set_visible(http)

    def _on_type_changed(self, *_args) -> None:
        """The kind of connector changed."""
        self._apply_type()

    def _on_add_response(self, dialog: Adw.MessageDialog, response: str) -> None:
        """Validate the form and save the server."""
        if response != "add":
            return
        self._error.set_visible(False)

        name = self._name_entry.get_text().strip()
        if not name:
            self._set_error("Give the connector a name.")
            return

        if self._type.get_selected() == 1:
            url = self._url_entry.get_text().strip()
            if not url:
                self._set_error("Enter the server URL.")
                return
            ok = mcp.add_server(name, url=url)
        else:
            command = self._command_entry.get_text().strip()
            if not command:
                self._set_error("Enter the command that runs the server.")
                return
            args = self._args_entry.get_text().split()
            ok = mcp.add_server(name, command=command, args=args)

        if not ok:
            self._set_error("Could not save the connector.")
            return

        dialog.close()
        self.refresh()
        self._changed()

    def _set_error(self, message: str) -> None:
        """Show a failure inside the add dialog."""
        self._error.set_text(message)
        self._error.set_visible(True)

    # -- page furniture -----------------------------------------------------
    def _flash(self, message: str, ok: bool) -> None:
        """Show a short-lived banner at the top of the page."""
        self._dismiss_banner()

        banner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        banner.add_css_class("card" if ok else "error-box")
        if ok:
            banner.add_css_class("inset")
        banner.set_margin_bottom(18)

        icon = theme.icon("check_circle" if ok else "error", 18,
                          tone="" if ok else "white")
        icon.set_valign(Gtk.Align.CENTER)
        banner.append(icon)

        label = Gtk.Label(label=message, xalign=0)
        label.set_hexpand(True)
        label.set_wrap(True)
        label.set_valign(Gtk.Align.CENTER)
        banner.append(label)

        close = icon_square("close", "Dismiss", 16)
        close.set_valign(Gtk.Align.CENTER)
        close.connect("clicked", lambda _b: self._dismiss_banner())
        banner.append(close)

        self._banner = banner
        self._banner_slot.append(banner)

    def _dismiss_banner(self) -> None:
        """Take the banner off the page."""
        if self._banner is not None:
            self._banner_slot.remove(self._banner)
            self._banner = None

    def _changed(self) -> None:
        """Tell the shell that the configuration changed."""
        if self._on_changed is not None:
            self._on_changed()

    def _window(self) -> Gtk.Window | None:
        """The window this page lives in, for parenting dialogs."""
        root = self.get_root()
        return root if isinstance(root, Gtk.Window) else None
