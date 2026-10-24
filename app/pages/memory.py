"""Memory: the facts the agent knows about you, with the receipts.

This page exists because a memory you cannot inspect is a memory you cannot
trust. Every fact shows where it came from, when it was last true, whether it
expires, and a way to delete it. Superseded facts are visible on request, so a
contradiction is a correction rather than a silent overwrite.
"""
from __future__ import annotations

import time
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from app import memory as store
from app import theme  # noqa: F401  (registers the bundled fonts)
from app.cards import (body, card, divider, hspacer, icon_square, pill_button,
                       section_title, segmented, spacer)

#: Filters, in rail order.
FILTERS = ("All", "Preferences", "Facts", "Commitments", "Projects")

KIND_FOR_FILTER = {
    "Preferences": "preference",
    "Facts": "fact",
    "Commitments": "commitment",
    "Projects": "project",
}


def _when(timestamp: float) -> str:
    if not timestamp:
        return ""
    return time.strftime("%d %b", time.localtime(timestamp))


def _expiry(fact: store.Fact) -> str:
    if not fact.expires:
        return ""
    if fact.expires < time.time():
        return "expired"
    days = max(1, int((fact.expires - time.time()) / 86400))
    return f"expires in {days} day{'s' if days != 1 else ''}"


class MemoryPage(Gtk.Box):
    """Inspect, add and forget what the agent remembers."""

    def __init__(self, on_changed: Callable[[], None] | None = None,
                 on_add: Callable[[str], None] | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("content")
        self.set_margin_start(36)
        self.set_margin_end(36)
        self.set_margin_top(8)
        self.set_margin_bottom(28)

        self._on_changed = on_changed
        self._on_add = on_add
        self._filter = "All"
        self._show_superseded = False

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="Memory", xalign=0)
        title.add_css_class("hero-title")
        titles.append(title)
        titles.append(body("What the agent knows about you. Local to this "
                           "machine, editable, and injected only where it "
                           "helps."))
        head.append(titles)
        head.append(hspacer())
        add = pill_button("Add a fact", "add", primary=True, on_click=self._add)
        add.set_valign(Gtk.Align.CENTER)
        head.append(add)
        self.append(head)
        self.append(spacer(height=18))

        self._segmented = segmented(list(FILTERS), active=0,
                                    on_select=self._on_filter)
        self.append(self._segmented)
        self.append(spacer(height=18))

        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.append(self._list)
        self.refresh()

    # -- data ---------------------------------------------------------------
    def refresh(self) -> None:
        while (child := self._list.get_first_child()) is not None:
            self._list.remove(child)

        live = store.facts()
        wanted = KIND_FOR_FILTER.get(self._filter)
        shown = [f for f in live if wanted is None or f.kind == wanted]

        self._list.append(self._summary(live))
        if shown:
            for fact in shown:
                self._list.append(self._row(fact))
        else:
            self._list.append(self._empty())

        dead = [f for f in store.facts(include_dead=True) if not f.live]
        if dead:
            self._list.append(spacer(height=6))
            toggle = Gtk.Button(
                label=("Hide superseded" if self._show_superseded
                       else f"Show {len(dead)} superseded or expired"))
            toggle.add_css_class("chip-grade")
            toggle.connect("clicked", lambda _b: self._toggle_superseded())
            self._list.append(toggle)
            if self._show_superseded:
                for fact in dead[:12]:
                    self._list.append(self._row(fact, muted=True))

    def _summary(self, live: list[store.Fact]) -> Gtk.Widget:
        counts = {}
        for fact in live:
            counts[fact.kind] = counts.get(fact.kind, 0) + 1
        parts = [f"{count} {kind}{'' if count == 1 else 's'}"
                 for kind, count in sorted(counts.items())]
        text = " · ".join(parts) if parts else "nothing yet"
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class("metric-sub")
        return label

    def _empty(self) -> Gtk.Widget:
        panel = card(inset=True)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_margin_top(26)
        inner.set_margin_bottom(26)
        inner.set_halign(Gtk.Align.CENTER)
        icon = icon_square("lightbulb_tips", "", 22)
        icon.set_halign(Gtk.Align.CENTER)
        inner.append(icon)
        title = Gtk.Label(label="Nothing remembered yet")
        title.add_css_class("card-title")
        inner.append(title)
        copy = body("Facts appear here as you tell them to the agent — "
                    "preferences, what you are working on, promises you made. "
                    "Or add one directly.")
        copy.set_justify(Gtk.Justification.CENTER)
        copy.set_max_width_chars(60)
        copy.set_halign(Gtk.Align.CENTER)
        inner.append(copy)
        panel.append(inner)
        return panel

    def _row(self, fact: store.Fact, muted: bool = False) -> Gtk.Widget:
        panel = card(inset=True)
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        for m in ("start", "end"):
            getattr(inner, f"set_margin_{m}")(16)
        inner.set_margin_top(12)
        inner.set_margin_bottom(12)

        badge = icon_square({"preference": "lightbulb_tips",
                             "commitment": "check_circle",
                             "project": "extension"}.get(fact.kind, "notes_spark"),
                            "", 16)
        badge.set_valign(Gtk.Align.START)
        inner.append(badge)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        col.set_hexpand(True)
        line = Gtk.Label(label=fact.text, xalign=0)
        line.add_css_class("card-title")
        line.set_wrap(True)
        if muted:
            line.set_opacity(0.55)
        col.append(line)

        meta = [f"{fact.kind} · {fact.scope} · from {fact.source}",
                _when(fact.updated)]
        expiry = _expiry(fact)
        if expiry:
            meta.append(expiry)
        if fact.superseded_by:
            meta.append("superseded")
        detail = Gtk.Label(label=" · ".join(part for part in meta if part),
                           xalign=0)
        detail.add_css_class("metric-sub")
        col.append(detail)
        inner.append(col)

        if not muted:
            forget = Gtk.Button(label="Forget")
            forget.add_css_class("chip-grade")
            forget.set_valign(Gtk.Align.CENTER)
            forget.connect("clicked", lambda _b, f=fact: self._forget(f))
            inner.append(forget)

        panel.append(inner)
        return panel

    # -- actions ------------------------------------------------------------
    def _on_filter(self, index: int) -> None:
        self._filter = FILTERS[index]
        self.refresh()

    def _toggle_superseded(self) -> None:
        self._show_superseded = not self._show_superseded
        self.refresh()

    def _forget(self, fact: store.Fact) -> None:
        if store.forget(fact.id):
            self.refresh()
            if self._on_changed:
                self._on_changed()

    def _add(self) -> None:
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(), heading="Add a fact",
            body="Something the agent should remember about you. It is stored "
                 "locally and can be deleted at any time.")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(8)

        entry = Gtk.Entry()
        entry.set_placeholder_text("e.g. I prefer mornings for deep work")
        box.append(entry)

        kinds = Gtk.DropDown.new_from_strings(list(store.KINDS))
        kinds.set_selected(1)
        box.append(kinds)

        scopes = Gtk.DropDown.new_from_strings(["all", "work", "personal"])
        box.append(scopes)

        error = Gtk.Label(label="", xalign=0)
        error.add_css_class("error-box")
        error.set_visible(False)
        box.append(error)

        dialog.set_extra_child(box)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("add", "Remember")
        dialog.set_response_appearance("add",
                                       Adw.ResponseAppearance.SUGGESTED)

        def on_response(dlg, response):
            if response != "add":
                return
            text = entry.get_text().strip()
            if not text:
                error.set_text("A fact needs some text.")
                error.set_visible(True)
                dlg.present()
                return
            kind = store.KINDS[max(0, min(kinds.get_selected(),
                                         len(store.KINDS) - 1))]
            scope = store.SCOPES[max(0, min(scopes.get_selected(),
                                            len(store.SCOPES) - 1))]
            if store.remember(text, kind=kind, scope=scope, source="you") is None:
                error.set_text("That fact could not be stored.")
                error.set_visible(True)
                dlg.present()
                return
            self.refresh()
            if self._on_add:
                self._on_add(text)
            if self._on_changed:
                self._on_changed()

        dialog.connect("response", on_response)
        dialog.present()
