"""Card and control primitives shared across the shell.

Every widget here maps to a component measured in the reference application
(see `docs/DESIGN.md`): the card outline, the rounded icon button, the
pill button, the segmented control, the section heading and the stat tile.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from app import theme  # noqa: E402


def card(inset: bool = False, spacing: int = 0) -> Gtk.Box:
    """A rounded surface panel."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    box.add_css_class("card")
    if inset:
        box.add_css_class("inset")
    return box


def section_title(text: str, icon_name: str = "", size: int = 19) -> Gtk.Box:
    """A section heading with an optional leading icon."""
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    if icon_name:
        row.append(theme.icon(icon_name, size + 1, tone=""))
    lbl = Gtk.Label(label=text, xalign=0)
    lbl.add_css_class("section-title")
    row.append(lbl)
    return row


def icon_square(name: str, tooltip: str = "", size: int = 20,
                tone: str = "", filled: bool = False) -> Gtk.Button:
    """The rounded-square icon button used throughout the reference."""
    btn = Gtk.Button()
    btn.add_css_class("icon-square")
    btn.set_child(theme.icon(name, size, tone, filled))
    if tooltip:
        btn.set_tooltip_text(tooltip)
    return btn


def pill_button(label: str, icon_name: str = "", primary: bool = False,
                on_click=None) -> Gtk.Button:
    """A rounded button: black when primary, outlined otherwise."""
    btn = Gtk.Button()
    btn.add_css_class("btn-primary" if primary else "btn-secondary")
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    if icon_name:
        tone = theme.scheme().on_accent if primary else ""
        row.append(theme.icon(icon_name, 18, tone=tone))
    lbl = Gtk.Label(label=label)
    row.append(lbl)
    btn.set_child(row)
    if on_click:
        btn.connect("clicked", lambda _b: on_click())
    return btn


def segmented(items: list[str], active: int = 0, on_select=None) -> Gtk.Box:
    """A segmented control; `items` are labels."""
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    box.add_css_class("segmented")
    for i, text in enumerate(items):
        btn = Gtk.Button(label=text)
        if i == active:
            btn.add_css_class("active")
        if on_select:
            btn.connect("clicked", lambda _b, idx=i: on_select(idx))
        box.append(btn)
    return box


def chip(label: str, on_click=None) -> Gtk.Button:
    btn = Gtk.Button(label=label)
    btn.add_css_class("chip-grade")
    if on_click:
        btn.connect("clicked", lambda _b: on_click())
    return btn


def divider() -> Gtk.Widget:
    sep = Gtk.Separator()
    sep.add_css_class("divider")
    return sep


def stat_tile(icon_name: str, number: str, label: str,
              on_click=None) -> Gtk.Box:
    """A quick-stat tile: icon, number, caption."""
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
    box.append(icon_square(icon_name, "", 20))
    col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    num = Gtk.Label(label=number, xalign=0)
    num.add_css_class("stat-num")
    col.append(num)
    cap = Gtk.Label(label=label, xalign=0)
    cap.add_css_class("stat-label")
    col.append(cap)
    box.append(col)
    if on_click:
        btn = Gtk.Button()
        btn.add_css_class("card")
        btn.set_child(box)
        btn.connect("clicked", lambda _b: on_click())
        return btn
    return box


def metric(value: str, caption: str = "") -> Gtk.Box:
    """The large number + small caption used in target cards."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    val = Gtk.Label(label=value, xalign=0)
    val.add_css_class("metric")
    box.append(val)
    if caption:
        cap = Gtk.Label(label=caption, xalign=0)
        cap.add_css_class("metric-sub")
        box.append(cap)
    return box


def eyebrow(text: str) -> Gtk.Label:
    lbl = Gtk.Label(label=text.upper(), xalign=0)
    lbl.add_css_class("card-eyebrow")
    return lbl


def title(text: str, size: int = 17) -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0)
    lbl.add_css_class("card-title")
    if size != 17:
        # GTK4 dropped the `font-size` widget property; use a CSS class.
        lbl.add_css_class(f"card-title-{size}")
    return lbl


def body(text: str, wrap: bool = True) -> Gtk.Label:
    lbl = Gtk.Label(label=text, xalign=0)
    lbl.add_css_class("card-body")
    lbl.set_wrap(wrap)
    return lbl


def hspacer() -> Gtk.Widget:
    """A spacer that expands horizontally only.

    `spacer()` expands in both directions, which is right between stacked
    sections but makes a row grow vertically when used beside a button.
    """
    box = Gtk.Box()
    box.set_hexpand(True)
    return box


def spacer(height: int = 0, width: int = 0) -> Gtk.Widget:
    box = Gtk.Box()
    if height:
        box.set_size_request(width, height)
    else:
        box.set_hexpand(True)
        box.set_vexpand(True)
    return box
