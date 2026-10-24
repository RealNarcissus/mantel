"""Skills: the agent's reusable instructions, and the plugins it can load.

A skill is a folder holding a ``SKILL.md`` — the same shape the desktop app
uses.  The real app lets you write one by hand or upload a ``.zip`` of such a
folder, and it invokes a skill by name.  Plugins are the engine's own
extensions; they live next to the skills and can be switched off.

The data itself belongs to :mod:`app.skills`, which owns ``~/.gemini``; this
page only talks to that layer.  Everything on the page is built from the
shared primitives in :mod:`app.cards` and the tokens in :mod:`app.theme`; no
colours or CSS classes are hard-coded.
"""
from __future__ import annotations

from collections.abc import Callable

import gi

from app import theme  # noqa: F401  (registers the bundled fonts before Gtk)

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, GObject, Gtk, Pango  # noqa: E402

from app import skills  # noqa: E402
from app.cards import (  # noqa: E402
    body,
    card,
    chip,
    eyebrow,
    icon_square,
    pill_button,
    section_title,
    spacer,
    title,
)

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


class SkillsPage(Gtk.Box):
    """The Skills page: the agent's skills and the plugins it can load."""

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

        self._skill_cards = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self._plugin_cards = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        self._banner_slot = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._content.append(self._banner_slot)

        self._content.append(self._build_header())
        self._content.append(spacer(height=26))

        self._content.append(section_title("Skills", "checklist"))
        self._content.append(spacer(height=14))
        self._content.append(self._skill_cards)

        self._content.append(spacer(height=26))
        self._content.append(section_title("Plugins", "extension"))
        self._content.append(spacer(height=14))
        self._content.append(self._plugin_cards)

        scroll.set_child(self._content)
        self.append(scroll)
        self.refresh()

    # -- construction -------------------------------------------------------
    def _build_header(self) -> Gtk.Widget:
        """The page heading, with the create and upload buttons on the right."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        row.set_valign(Gtk.Align.CENTER)

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        labels.append(title("Skills", 24))
        labels.append(body("Reusable instructions the agent can pull in by "
                           "name."))
        row.append(labels)

        gap = Gtk.Box()
        gap.set_hexpand(True)
        row.append(gap)
        row.append(_pill("Create skill", "add", primary=True,
                         on_click=self._open_create_dialog))
        row.append(_pill("Upload", "upload", on_click=self._open_upload))
        return row

    # -- the lists ----------------------------------------------------------
    def refresh(self) -> None:
        """Rebuild both lists from the configuration."""
        _clear(self._skill_cards)
        _clear(self._plugin_cards)

        entries = skills.list_skills()
        skill_entries = [s for s in entries if s.kind == "skill"]
        plugin_entries = [s for s in entries if s.kind == "plugin"]

        if skill_entries:
            for skill in skill_entries:
                self._skill_cards.append(self._skill_card(skill))
        else:
            self._skill_cards.append(self._skills_empty_state())

        if plugin_entries:
            for plugin in plugin_entries:
                self._plugin_cards.append(self._plugin_card(plugin))
        else:
            self._plugin_cards.append(self._plugins_empty_state())

    def _skill_card(self, skill: skills.Skill) -> Gtk.Widget:
        """One skill: its name, what it is for and how it is invoked."""
        panel = card()
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        row.set_margin_start(18)
        row.set_margin_end(18)
        row.set_margin_top(16)
        row.set_margin_bottom(16)

        badge = icon_square("checklist", "", 20)
        badge.set_valign(Gtk.Align.START)
        row.append(badge)

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        labels.set_hexpand(True)
        labels.set_valign(Gtk.Align.CENTER)
        labels.append(_ellipsize(title(skill.name, 15)))
        labels.append(body(skill.description or "No description."))
        row.append(labels)

        invoke = chip(skill.name)
        invoke.set_tooltip_text("Invoke this skill by name")
        invoke.set_valign(Gtk.Align.CENTER)
        chip_label = invoke.get_child()
        if isinstance(chip_label, Gtk.Label):
            chip_label.set_ellipsize(Pango.EllipsizeMode.END)
            chip_label.set_max_width_chars(24)
        row.append(invoke)

        remove = icon_square("delete", "Remove")
        remove.set_valign(Gtk.Align.CENTER)
        remove.connect("clicked", lambda _b, n=skill.name: self._confirm_remove(n))
        row.append(remove)

        panel.append(row)
        return panel

    def _plugin_card(self, plugin: skills.Skill) -> Gtk.Widget:
        """One plugin: its name and the switch that turns it on."""
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
        labels.append(_ellipsize(title(plugin.name, 15)))
        labels.append(body(plugin.description or "No description."))
        row.append(labels)

        switch = Gtk.Switch()
        switch.set_active(plugin.enabled)
        switch.set_valign(Gtk.Align.CENTER)
        switch.set_tooltip_text("Enable this plugin")
        switch.connect("notify::active", self._on_switch, plugin.name)
        row.append(switch)

        panel.append(row)
        return panel

    # -- empty states -------------------------------------------------------
    def _skills_empty_state(self) -> Gtk.Widget:
        """Shown when no skill has been written or uploaded yet."""
        panel = card(inset=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(26)
        box.set_margin_end(26)
        box.set_margin_top(24)
        box.set_margin_bottom(24)

        badge = icon_square("checklist", "", 22)
        badge.set_halign(Gtk.Align.START)
        box.append(badge)
        box.append(title("No skills yet", 15))
        box.append(body("A skill is a short set of instructions — a name, a "
                        "description and the steps themselves. The agent pulls "
                        "it in when it matches what you asked for, and you "
                        "can call it by name."))
        create = _pill("Create skill", "add", on_click=self._open_create_dialog)
        create.set_halign(Gtk.Align.START)
        box.append(create)

        panel.append(box)
        return panel

    def _plugins_empty_state(self) -> Gtk.Widget:
        """Shown when no plugin is installed."""
        panel = card(inset=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(26)
        box.set_margin_end(26)
        box.set_margin_top(24)
        box.set_margin_bottom(24)

        badge = icon_square("extension", "", 22)
        badge.set_halign(Gtk.Align.START)
        box.append(badge)
        box.append(title("No plugins installed", 15))
        box.append(body("Plugins are the engine's own extensions: they add "
                        "tools and commands to the agent. Switch one on to "
                        "let the agent use it."))

        panel.append(box)
        return panel

    # -- mutations ----------------------------------------------------------
    def _on_switch(self, switch: Gtk.Switch, _spec: GObject.ParamSpec,
                   name: str) -> None:
        """Enable or disable a plugin, and put the switch back on failure."""
        if self._muting:
            return
        value = switch.get_active()
        if not skills.set_plugin_enabled(name, value):
            self._muting = True
            switch.set_active(not value)
            self._muting = False
            self._flash(f"Could not update {name}.", False)
            return
        self._changed()

    def _confirm_remove(self, name: str) -> None:
        """Ask before a skill is deleted."""
        dialog = Adw.MessageDialog(
            transient_for=self._window(),
            heading=f"Delete {name}?",
            body="The skill and everything in its folder are removed. The "
                 "agent will no longer be able to use it.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete",
                                       Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        dialog.set_default_response("cancel")
        dialog.connect("response", self._on_remove_response, name)
        dialog.present()

    def _on_remove_response(self, dialog: Adw.MessageDialog, response: str,
                            name: str) -> None:
        """Carry out a confirmed deletion."""
        if response != "delete":
            return
        if not skills.delete_skill(name):
            self._flash(f"Could not delete {name}.", False)
            return
        self.refresh()
        self._changed()

    # -- creating a skill ---------------------------------------------------
    def _open_create_dialog(self) -> None:
        """Open the modal form that writes a new skill."""
        dialog = Adw.MessageDialog(
            transient_for=self._window(),
            heading="Create a skill",
            body="Write the instructions the agent should follow. The skill "
                 "is invoked by its name.",
        )

        self._name_entry = Gtk.Entry()
        self._name_entry.set_placeholder_text("release-notes")
        self._name_entry.set_max_length(64)

        self._description_entry = Gtk.Entry()
        self._description_entry.set_placeholder_text("What the skill is for")

        self._body_view = Gtk.TextView()
        self._body_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self._body_view.set_monospace(True)

        body_scroll = Gtk.ScrolledWindow()
        body_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        body_scroll.set_size_request(-1, 190)
        body_scroll.set_child(self._body_view)

        # The editor sits on the shell's own inset surface; the "composer"
        # class is what makes the text view itself transparent.
        holder = card(inset=True)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        inner.add_css_class("composer")
        inner.set_margin_start(12)
        inner.set_margin_end(12)
        inner.set_margin_top(12)
        inner.set_margin_bottom(12)
        inner.append(body_scroll)
        holder.append(inner)

        form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        form.append(_field("Name", _wrap_entry(self._name_entry)))
        form.append(_field("Description", _wrap_entry(self._description_entry)))
        form.append(_field("Instructions", holder))

        self._error = Gtk.Label(label="", xalign=0)
        self._error.add_css_class("error-box")
        self._error.set_wrap(True)
        self._error.set_visible(False)
        form.append(self._error)

        dialog.set_extra_child(form)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("create", "Create")
        dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_close_response("cancel")
        dialog.set_default_response("create")

        dialog.connect("response", self._on_create_response)
        dialog.present()

    def _on_create_response(self, dialog: Adw.MessageDialog, response: str) -> None:
        """Validate the form and write the skill."""
        if response != "create":
            return
        self._error.set_visible(False)

        name = self._name_entry.get_text().strip()
        if not name:
            self._set_error("Give the skill a name.")
            return

        description = self._description_entry.get_text().strip()
        buffer = self._body_view.get_buffer()
        body = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(),
                               False)

        ok, message = skills.install_skill(name, description, body)
        if not ok:
            self._set_error(message)
            return

        dialog.close()
        self.refresh()
        self._changed()
        self._flash(message, True)

    def _set_error(self, message: str) -> None:
        """Show a failure inside the create dialog."""
        self._error.set_text(message)
        self._error.set_visible(True)

    # -- uploading a skill --------------------------------------------------
    def _open_upload(self) -> None:
        """Ask for a ``.zip`` and install the skill it holds."""
        dialog = Gtk.FileDialog()
        dialog.set_title("Upload a skill")
        dialog.set_filters(Gtk.FileFilter.new_from_glob("*.zip"))

        def chosen(file_dialog: Gtk.FileDialog, result) -> None:
            try:
                chosen_file = file_dialog.open_finish(result)
            except GLib.Error:
                return
            if chosen_file is None:
                return
            path = chosen_file.get_path()
            if not path:
                self._flash("Could not read that file.", False)
                return
            ok, message = skills.install_skill_zip(path)
            self._flash(message, ok)
            if ok:
                self.refresh()
                self._changed()

        dialog.open(self._window(), None, chosen)

    # -- page furniture -----------------------------------------------------
    def _flash(self, message: str, ok: bool) -> None:
        """Show the result of an upload at the top of the page."""
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
