"""The top bar.

Matches the reference: a breadcrumb chip on the left, and on the right a
notification button, a black pill action button and a filter button.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from app import theme  # noqa: E402

HEIGHT = 100


class TopBar(Gtk.Box):
    """Height-100 header row spanning the content area."""

    def __init__(self, title: str = "Chat", on_back=None, on_new=None,
                 on_filter=None, on_notify=None):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.add_css_class("topbar")
        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(36)
        self.set_margin_end(36)

        crumb = Gtk.Button()
        crumb.add_css_class("crumb")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.append(theme.icon("chevron_left", 18, tone=""))
        self._crumb_label = Gtk.Label(label=title)
        row.append(self._crumb_label)
        crumb.set_child(row)
        if on_back:
            crumb.connect("clicked", lambda _b: on_back())
        self.append(crumb)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        self.append(spacer)

        bell = theme.icon_button("notifications", "Notifications", 20)
        bell.set_valign(Gtk.Align.CENTER)
        if on_notify:
            bell.connect("clicked", lambda _b: on_notify())
        self.append(bell)

        new_btn = Gtk.Button()
        new_btn.add_css_class("btn-primary")
        new_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        new_row.append(theme.icon("edit_square", 18,
                                  tone=theme.scheme().on_accent))
        new_row.append(Gtk.Label(label="New"))
        new_btn.set_child(new_row)
        new_btn.set_valign(Gtk.Align.CENTER)
        if on_new:
            new_btn.connect("clicked", lambda _b: on_new())
        self.append(new_btn)

        filt = theme.icon_button("tune", "Options", 20)
        filt.set_valign(Gtk.Align.CENTER)
        if on_filter:
            filt.connect("clicked", lambda _b: on_filter())
        self.append(filt)

    def set_title(self, title: str) -> None:
        self._crumb_label.set_text(title)
