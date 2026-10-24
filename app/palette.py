"""The command palette: one keystroke for everything the app can do.

The idea is borrowed from Raycast and from the terminal: instead of learning
where a feature lives, type what you mean. The palette is the front door for
capture too — "call the dentist tomorrow" becomes a dated task without leaving
the keyboard, which is the difference between a list people keep and a list
people abandon.

`interpret()` is deliberately pure: it turns a query into a list of candidate
actions, and the window decides how to run them. That keeps the interesting
part — what a phrase *means* — testable without a display.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from app import memory as memory_store
from app import todos

#: Pages the palette can jump to. Labels are what the user would type.
PAGE_WORDS = (
    ("today", "Today", "Go to Today"),
    ("chat", "Chat", "Go to the transcript"),
    ("tasks", "Tasks", "Go to the task list"),
    ("create", "Create", "Generate an image"),
    ("schedule", "Schedule", "Recurring prompts"),
    ("memory", "Memory", "What the agent knows"),
    ("connectors", "Connectors", "MCP servers"),
    ("skills", "Skills", "Installed skills"),
    ("settings", "Settings", "Preferences"),
)

#: Commands the palette can run directly.
COMMANDS = (
    ("new-thread", "New thread", "Start a conversation"),
    ("start-focus", "Start focus session", "25 minutes"),
    ("toggle-theme", "Toggle theme", "Light or dark"),
    ("review-day", "Review the day", "Ask the agent to summarise today"),
)

#: Prefixes the palette understands, with or without a colon.
TRIGGERS = ("> ", "? ", "ask ", "ask: ", "note ", "note: ", "remember ",
            "remember: ", "remind ", "remind: ", "task ", "task: ")


def _strip_prefix(query: str, *prefixes: str) -> str:
    lowered = query.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return query[len(prefix):].strip(" :")
    return query.strip()


def _strip_reminder(query: str) -> str:
    """'remind me to call mum' -> 'call mum'."""
    text = _strip_prefix(query, "remind me to ", "remind me ", "remind: ",
                         "remind ")
    return re.sub(r"^(?:me\s+to|to|that)\s+", "", text, flags=re.I)


def actions_for(query: str, *, pages: list[str] | None = None,
                extras: list[Action] | None = None,
                limit: int = 8) -> list[Action]:
    """The widget's entry point: built-in actions plus contributed ones."""
    actions = interpret(query, pages=pages, limit=limit)
    if not extras:
        return actions
    text = (query or "").strip().lower()
    matched = [action for action in extras
               if not text or text in action.label.lower()]
    if not matched:
        return actions
    # contributed commands sit after the built-ins, never instead of them
    return (actions + matched)[:max(limit, len(matched))]


@dataclass
class Action:
    """One thing the palette can do."""

    kind: str            # task | note | ask | navigate | command | remind
    label: str
    detail: str = ""
    payload: str = ""    # what to run / where to go


def _starts_with(query: str, prefix: str) -> bool:
    return query.lower().startswith(prefix) and len(query) > len(prefix)


def _strip(query: str, *prefixes: str) -> str:
    for prefix in prefixes:
        if query.lower().startswith(prefix):
            return query[len(prefix):].strip()
    return query.strip()


def _when(timestamp: float) -> str:
    if not timestamp:
        return "no date"
    moment = time.localtime(timestamp)
    if time.strftime("%Y-%m-%d", moment) == time.strftime("%Y-%m-%d"):
        return "today · " + time.strftime("%H:%M", moment)
    return time.strftime("%a %d %b · %H:%M", moment)


def interpret(query: str, *, pages: list[str] | None = None,
              limit: int = 8) -> list[Action]:
    """Candidate actions for a query, best first.

    `pages` restricts navigation to the surfaces the current engine backs.
    """
    query = (query or "").strip()
    available = set(pages) if pages is not None else {p[0] for p in PAGE_WORDS}

    def navigations() -> list[Action]:
        return [Action("navigate", label, detail, key)
                for key, label, detail in PAGE_WORDS if key in available]

    def commands() -> list[Action]:
        return [Action("command", label, detail, key)
                for key, label, detail in COMMANDS]

    if not query:
        return (navigations() + commands())[:limit]

    # explicit intents
    if query.startswith(">"):
        text = query[1:].strip().lower()
        return [action for action in commands()
                if text in action.label.lower() or text in action.payload][:limit]

    lowered_query = query.lower()
    if lowered_query.startswith(("? ", "ask ", "ask:")):
        text = _strip_prefix(query, "? ", "ask ", "ask: ")
        return [Action("ask", f"Ask the agent: {text}",
                       "Send this to the transcript", text)]

    if lowered_query.startswith(("note ", "note:", "remember ", "remember:")):
        text = _strip_prefix(query, "note ", "note: ", "remember ",
                             "remember: ")
        if not text:
            return []
        return [Action("note", f"Remember: {text}",
                       "Store as a memory fact", text)]

    if lowered_query.startswith(("remind ", "remind:")):
        text = _strip_reminder(query)
        due, cleaned = todos.parse_due(text)
        detail = _when(due) if due else "needs a time"
        return [Action("remind", f"Remind me: {cleaned}", detail, text)]

    if lowered_query.startswith(("task ", "task:")):
        text = _strip_prefix(query, "task ", "task: ")
        due, cleaned = todos.parse_due(text)
        return [Action("task", cleaned, _when(due), text)]

    # navigation by name
    lowered = query.lower()
    routes = [action for action in navigations()
              if action.label.lower().startswith(lowered)]
    if routes and len(lowered) >= 2:
        return routes[:limit]

    # commands by name
    if lowered.startswith(("new", "start", "toggle", "review")):
        matched = [action for action in commands()
                   if action.label.lower().startswith(lowered)]
        if matched:
            return matched[:limit]

    # a memory being looked up
    facts = memory_store.search(query, limit=3)
    if facts and len(query) >= 4:
        return [Action("remembered", f"“{fact.text}”",
                       f"remembered · {fact.kind}", fact.id)
                for fact in facts]

    # default: it is a task, with the date parsed out of the phrase
    due, cleaned = todos.parse_due(query)
    looks_like_task = len(cleaned) >= 3
    if looks_like_task:
        actions = [Action("task", f"Add task: {cleaned}", _when(due), query)]
    else:
        actions = []
    return (actions + navigations()[:2])[:limit]


# --- the widget -------------------------------------------------------------

class Palette(Gtk.Revealer):
    """An overlay at the top of the window: type, choose, done."""

    def __init__(self, on_run, on_close=None, pages=None,
                 extras_provider=None) -> None:
        super().__init__()
        self.set_transition_type(Gtk.RevealerTransitionType.CROSSFADE)
        self.set_transition_duration(120)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.START)
        self.set_margin_top(14)
        self.add_css_class("palette")
        self._on_run = on_run
        self._on_close = on_close or (lambda: None)
        self._pages = pages or []
        self._extras_provider = extras_provider
        self._actions: list[Action] = []
        self._selected = 0

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        panel.add_css_class("palette-body")
        panel.set_size_request(660, -1)

        entry_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        entry_row.set_margin_start(16)
        entry_row.set_margin_end(16)
        entry_row.set_margin_top(12)
        entry_row.set_margin_bottom(10)
        entry_row.append(Gtk.Image.new_from_icon_name("system-search-symbolic"))
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text(
            "Add a task, jump somewhere, or type ? to ask…")
        self.entry.set_has_frame(False)
        self.entry.set_hexpand(True)
        self.entry.connect("changed", self._on_changed)
        self.entry.connect("activate", self._run_selected)
        entry_row.append(self.entry)
        panel.append(entry_row)

        self._list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._list.set_margin_start(8)
        self._list.set_margin_end(8)
        self._list.set_margin_bottom(8)
        panel.append(self._list)

        self.set_child(panel)

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.entry.add_controller(key)

    # -- state -------------------------------------------------------------
    def open(self, seed: str = "") -> None:
        self.entry.set_text(seed)
        self.entry.set_position(-1)
        self._refresh(seed)
        self.set_reveal_child(True)
        self.entry.grab_focus()

    def close(self) -> None:
        self.set_reveal_child(False)
        self._on_close()

    @property
    def is_open(self) -> bool:
        return self.get_reveal_child()

    def _on_changed(self, entry) -> None:
        self._refresh(entry.get_text())

    def _refresh(self, query: str) -> None:
        extras = []
        if self._extras_provider:
            try:
                extras = list(self._extras_provider())
            except Exception:  # noqa: BLE001 - a bad provider must not break it
                extras = []
        self._actions = actions_for(query, pages=self._pages, extras=extras)
        self._selected = 0
        while (child := self._list.get_first_child()) is not None:
            self._list.remove(child)
        if not self._actions:
            empty = Gtk.Label(label="Nothing matches", xalign=0)
            empty.add_css_class("metric-sub")
            empty.set_margin_top(8)
            empty.set_margin_bottom(8)
            empty.set_margin_start(8)
            self._list.append(empty)
            return
        for index, action in enumerate(self._actions):
            self._list.append(self._row(index, action))

    def _row(self, index: int, action: Action) -> Gtk.Widget:
        row = Gtk.Button()
        row.add_css_class("palette-row")
        if index == self._selected:
            row.add_css_class("selected")
        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        inner.set_margin_start(6)
        inner.set_margin_end(6)
        icon = {"task": "checklist", "remind": "notifications",
                "note": "lightbulb_tips", "ask": "chat",
                "navigate": "chevron_right", "command": "bolt",
                "remembered": "notes_spark"}.get(action.kind, "add")
        from app import theme  # noqa: PLC0415

        inner.append(theme.icon(icon, 16))
        label = Gtk.Label(label=action.label, xalign=0)
        label.set_hexpand(True)
        label.set_ellipsize(3)
        inner.append(label)
        if action.detail:
            detail = Gtk.Label(label=action.detail, xalign=1)
            detail.add_css_class("metric-sub")
            inner.append(detail)
        row.set_child(inner)
        row.connect("clicked", lambda _b, i=index: self._run_index(i))
        return row

    # -- keyboard ----------------------------------------------------------
    def _on_key(self, _controller, keyval, _code, _state) -> bool:
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        if keyval == Gdk.KEY_Down:
            self._move(1)
            return True
        if keyval == Gdk.KEY_Up:
            self._move(-1)
            return True
        return False

    def _move(self, delta: int) -> None:
        if not self._actions:
            return
        self._selected = (self._selected + delta) % len(self._actions)
        index = 0
        child = self._list.get_first_child()
        while child is not None:
            if child.has_css_class("palette-row"):
                child.set_sensitive(True)
                if index == self._selected:
                    child.add_css_class("selected")
                else:
                    child.remove_css_class("selected")
                index += 1
            child = child.get_next_sibling()

    def _run_selected(self, *_args) -> None:
        if self._actions:
            self._run_index(self._selected)

    def _run_index(self, index: int) -> None:
        if not (0 <= index < len(self._actions)):
            return
        action = self._actions[index]
        self.close()
        self._on_run(action)
