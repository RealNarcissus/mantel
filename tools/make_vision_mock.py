#!/usr/bin/env python3
"""Render the proposed "Today" surface as a design mock.

This is a picture, not a feature: the widgets are built here with sample data to
show where the product is going (docs/VISION.md §5 and §9) and to test the
design language against a real screen before committing to it.

    python3 tools/make_vision_mock.py [--out docs/vision/today.png]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import fonts_env  # noqa: F401,E402

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from app import theme  # noqa: E402
from app.cards import (body, card, divider, eyebrow, hspacer, icon_square,  # noqa: E402
                       metric, pill_button, section_title, segmented, spacer)
from tests.harness import render_to_png  # noqa: E402

WIDTH, HEIGHT = 1744, 1168

#: Styles used only by this mock. The product theme is not modified.
MOCK_CSS = """
.nav-row { border-radius: 12px; }
.nav-label { font-size: 15px; }
.nav-label-active { font-size: 15px; font-weight: 600; }
.rail-fact { font-size: 13px; }
.tick {
  border-radius: 999px; border: 1.5px solid rgba(0,0,0,0.28);
  background: transparent;
}
.tick-done { border-radius: 999px; background: #0B0B0B; }
.block-focus { background: #F3F5F5; border-radius: 12px; }
.block-event { background: #EDF0F6; border-radius: 12px; }
.block-break { background: #F6F4EF; border-radius: 12px; }
.block-agent { background: #F1EEF6; border-radius: 12px; }
.block-free {
  background: transparent; border-radius: 12px;
  border: 1px dashed rgba(0,0,0,0.18);
}
.block-title { font-weight: 600; font-size: 14px; }
.page, .metric-sub, .block-title, .rail-fact, .card-title, .search-field {
  font-family: "__MONO__";
}
.hero-title, .brand-name { font-family: "__BRAND__"; }
.progress-track { background: rgba(0,0,0,0.10); border-radius: 999px; }
.progress-fill { background: #0B0B0B; border-radius: 999px; }
"""

NAV = ("Today", "Inbox", "Threads", "Tasks", "Focus", "Scheduled", "Memory",
       "Plugins")

THREE_THINGS = (
    ("Ship the Pi adapter seam", "Mantel · 90 min", True, "09:30"),
    ("Review the memory proposal", "Mantel · 45 min", False, "11:00"),
    ("Draft the weekly note", "Work · 30 min", False, "16:30"),
)

TIMELINE = (
    ("09:00", "Focus block", "Py adapter seam", "focus", 90),
    ("10:30", "Standup", "15 min · recurring", "event", 15),
    ("11:00", "Review", "Memory proposal", "focus", 45),
    ("12:00", "Lunch", "", "break", 60),
    ("13:30", "Agent run", "Weekly digest, 3 sources", "agent", 40),
    ("14:30", "Open block", "2½ h — could hold the draft", "free", 150),
)

WAITING = (
    ("Alex", "Pi RPC docs for steering", "since Tuesday"),
    ("CI", "Nightly run on main", "20 min ago"),
)

MEMORY = (
    ("Prefers deep work before noon", "stated 4× · Mar–Oct"),
    ("Dentist Thursday 18:00", "expires tomorrow"),
    ("Working on Mantel v0.2", "this week"),
)

INBOX = (
    ("Forward the RPC notes to Alex", "task · today", True),
    ("Idea: plugin triggers from git hooks", "note · Mantel", False),
    ("Dentist moved to Friday?", "reminder · needs a date", False),
)


# --- small pieces ----------------------------------------------------------

def _muted(text: str) -> Gtk.Label:
    label = Gtk.Label(label=text, xalign=0)
    label.add_css_class("metric-sub")
    return label


def _rail() -> Gtk.Widget:
    rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    rail.set_size_request(304, -1)
    rail.add_css_class("sidebar")

    brand = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    brand.set_margin_start(20)
    brand.set_margin_end(20)
    brand.set_margin_top(14)
    brand.set_margin_bottom(14)
    mark = Gtk.Box()
    mark.set_size_request(44, 44)
    mark.add_css_class("brand-mark")
    brand.append(mark)
    words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    name = Gtk.Label(label="Mantel", xalign=0)
    name.add_css_class("brand-name")
    words.append(name)
    words.append(_muted("Thursday, 24 October"))
    brand.append(words)
    rail.append(brand)

    search = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    search.add_css_class("search-field")
    search.set_margin_start(20)
    search.set_margin_end(20)
    search.set_margin_top(6)
    search.set_margin_bottom(14)
    search.append(theme.icon("search", 16))
    search.append(_muted("Capture or search…"))
    search.append(hspacer())
    search.append(_muted("⌘K"))
    rail.append(search)

    for index, item in enumerate(NAV):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.set_margin_start(12)
        row.set_margin_end(12)
        row.set_margin_bottom(2)
        row.set_size_request(-1, 46)
        if index == 0:
            row.add_css_class("nav-active")
        else:
            row.add_css_class("nav-row")
        pad = Gtk.Box()
        pad.set_size_request(8, -1)
        row.append(pad)
        row.append(theme.icon(
            {"Today": "check_circle", "Inbox": "notifications",
             "Threads": "chat", "Tasks": "checklist", "Focus": "bolt",
             "Scheduled": "schedule", "Memory": "notes_spark",
             "Plugins": "extension"}.get(item, "add"), 18))
        label = Gtk.Label(label=item, xalign=0)
        if index == 0:
            label.add_css_class("nav-label-active")
        else:
            label.add_css_class("nav-label")
        row.append(label)
        row.append(hspacer())
        if item == "Inbox":
            badge = Gtk.Label(label="3")
            badge.add_css_class("chip-grade")
            row.append(badge)
        rail.append(row)

    rail.append(spacer(height=14))
    head = eyebrow("MEMORY IN USE")
    head.set_margin_start(20)
    rail.append(head)
    rail.append(spacer(height=6))
    for fact, when in MEMORY:
        line = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        line.set_margin_start(20)
        line.set_margin_end(20)
        line.set_margin_bottom(8)
        text = Gtk.Label(label=fact, xalign=0)
        text.add_css_class("rail-fact")
        text.set_ellipsize(3)
        line.append(text)
        line.append(_muted(when))
        rail.append(line)

    rail.append(hspacer())
    foot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    foot.set_margin_start(20)
    foot.set_margin_end(20)
    foot.set_margin_bottom(18)
    avatar = Gtk.Label(label="AR")
    avatar.add_css_class("user-initials")
    foot.append(avatar)
    who = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    who.append(Gtk.Label(label="Alex Rivera", xalign=0))
    who.append(_muted("alex@example.com"))
    foot.append(who)
    rail.append(foot)
    return rail


def _thing(title: str, meta: str, done: bool, when: str) -> Gtk.Widget:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    row.set_margin_top(10)
    row.set_margin_bottom(10)
    tick = Gtk.Box()
    tick.set_size_request(22, 22)
    tick.set_valign(Gtk.Align.CENTER)
    tick.add_css_class("tick-done" if done else "tick")
    row.append(tick)
    words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    words.set_hexpand(True)
    name = Gtk.Label(label=title, xalign=0)
    name.add_css_class("card-title")
    words.append(name)
    words.append(_muted(meta))
    row.append(words)
    time = Gtk.Label(label=when, xalign=1)
    time.add_css_class("metric-sub")
    row.append(time)
    return row


def _timeline_row(when: str, what: str, detail: str, kind: str,
                  minutes: int) -> Gtk.Widget:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    row.set_margin_top(6)
    row.set_margin_bottom(6)
    clock = Gtk.Label(label=when, xalign=0)
    clock.add_css_class("metric-sub")
    clock.set_size_request(48, -1)
    row.append(clock)
    block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    block.set_hexpand(True)
    block.add_css_class(f"block-{kind}")
    height = max(34, min(78, 22 + minutes // 3))
    block.set_size_request(-1, height)
    pad = Gtk.Box()
    pad.set_size_request(0, 6)
    block.append(pad)
    pad2 = Gtk.Box()
    pad2.set_size_request(12, -1)
    line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    line.append(pad2)
    words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    words.set_hexpand(True)
    name = Gtk.Label(label=what, xalign=0)
    name.add_css_class("block-title")
    words.append(name)
    if detail:
        words.append(_muted(detail))
    line.append(words)
    block.append(line)
    row.append(block)
    return row


def _panel(title: str, icon_name: str, content: Gtk.Widget,
           action: str = "") -> Gtk.Widget:
    panel = card()
    inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    for m in ("start", "end"):
        getattr(inner, f"set_margin_{m}")(18)
    inner.set_margin_top(14)
    inner.set_margin_bottom(14)
    head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    head.append(theme.icon(icon_name, 16))
    heading = Gtk.Label(label=title, xalign=0)
    heading.add_css_class("card-title")
    head.append(heading)
    head.append(hspacer())
    if action:
        head.append(_muted(action))
    inner.append(head)
    inner.append(content)
    panel.append(inner)
    return panel


# --- the page --------------------------------------------------------------

def build() -> Gtk.Widget:
    # A static composition, so geometry is explicit rather than negotiated:
    # the mock is a picture of a layout, not the layout itself.
    root = Gtk.Fixed()
    root.add_css_class("page")
    root.set_size_request(WIDTH, HEIGHT)

    rail = _rail()
    rail.set_size_request(304, HEIGHT)
    root.put(rail, 0, 0)

    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    content.set_size_request(WIDTH - 304, HEIGHT)
    for m in ("start", "end"):
        getattr(content, f"set_margin_{m}")(36)
    content.set_margin_top(26)

    head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    titles.append(eyebrow("THURSDAY · WEEK 43"))
    day = Gtk.Label(label="Today", xalign=0)
    day.add_css_class("hero-title")
    titles.append(day)
    titles.append(body("Three things that matter, and the day shaped around them."))
    head.append(titles)
    head.append(hspacer())
    capture = pill_button("Capture", "add", primary=True)
    capture.set_valign(Gtk.Align.CENTER)
    head.append(capture)
    content.append(head)
    content.append(spacer(height=22))

    columns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=22)
    columns.set_hexpand(True)
    content.append(columns)

    left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    left.set_hexpand(True)
    columns.append(left)

    # three things
    things = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    for index, (title, meta, done, when) in enumerate(THREE_THINGS):
        if index:
            things.append(divider())
        things.append(_thing(title, meta, done, when))
    left.append(_panel("The three things", "check_circle", things, "2 of 3"))

    # timeline
    day_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    for when, what, detail, kind, minutes in TIMELINE:
        day_rows.append(_timeline_row(when, what, detail, kind, minutes))
    left.append(_panel("The day", "schedule", day_rows, "Thu 24 Oct"))

    # waiting on
    waiting = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    for index, (who, what, age) in enumerate(WAITING):
        if index:
            waiting.append(divider())
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_margin_top(9)
        row.set_margin_bottom(9)
        words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        words.set_hexpand(True)
        line = Gtk.Label(label=what, xalign=0)
        line.add_css_class("card-title")
        words.append(line)
        words.append(_muted(f"{who} · {age}"))
        row.append(words)
        row.append(pill_button("Nudge", "notifications"))
        waiting.append(row)
    left.append(_panel("Waiting on", "notifications", waiting, "2 open"))

    # right column
    right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    right.set_size_request(430, -1)
    columns.append(right)

    focus = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    focus.append(metric("24:51", "focus session · Pi adapter seam"))
    focus.append(spacer(height=10))
    track = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    track.add_css_class("progress-track")
    track.set_size_request(-1, 6)
    fill = Gtk.Box()
    fill.add_css_class("progress-fill")
    fill.set_size_request(232, -1)
    track.append(fill)
    focus.append(track)
    focus.append(spacer(height=8))
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    row.append(pill_button("Pause", "stop"))
    row.append(pill_button("Open thread", "chat"))
    focus.append(row)
    right.append(_panel("Focus", "bolt", focus, "hold notifications"))

    agent = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    for line, detail in (
        ("Reading 3 sources for the weekly digest", "running · 12 s"),
        ("Wants to write ~/work/notes/week-43.md", "needs approval"),
        ("Finished: triaged 3 inbox items", "4 min ago"),
    ):
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        row.set_margin_top(7)
        row.set_margin_bottom(7)
        text = Gtk.Label(label=line, xalign=0)
        text.set_ellipsize(3)
        text.add_css_class("work-item")
        row.append(text)
        row.append(_muted(detail))
        agent.append(row)
    right.append(_panel("Agent", "gemini_spark", agent, "1 approval"))

    inbox_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    for index, (text, meta, suggest) in enumerate(INBOX):
        if index:
            inbox_rows.append(divider())
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        row.set_margin_top(8)
        row.set_margin_bottom(8)
        line = Gtk.Label(label=text, xalign=0)
        line.set_ellipsize(3)
        line.add_css_class("work-item")
        row.append(line)
        tail = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tail.append(_muted(("✓ " if suggest else "→ ") + meta))
        row.append(tail)
        inbox_rows.append(row)
    right.append(_panel("Captured just now", "notifications", inbox_rows,
                        "accept with ↵"))

    content.append(spacer(height=20))
    content.append(_muted("Mantel · local-first · engine: pi (rpc) · memory: local"))
    root.put(content, 304, 0)
    return root


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "docs" / "vision" / "today.png"))
    args = ap.parse_args()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    application = Adw.Application(application_id="dev.mantel.VisionMock")

    def activate(app):
        theme.install()
        import gi as _gi  # noqa: PLC0415

        _gi.require_version("Gdk", "4.0")
        from gi.repository import Gdk as _Gdk  # noqa: PLC0415

        css = (MOCK_CSS.replace("__MONO__", theme.FONT_MONO)
               .replace("__BRAND__", theme.FONT_BRAND))
        provider = Gtk.CssProvider()
        provider.load_from_string(css)
        Gtk.StyleContext.add_provider_for_display(
            _Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_USER)
        window = Gtk.Window()
        app.add_window(window)   # keeps the application alive while it draws
        window.set_default_size(WIDTH, HEIGHT)
        window.set_size_request(WIDTH, HEIGHT)
        window.set_decorated(False)
        window.set_child(build())
        window.set_resizable(False)
        window.present()

        def shot():
            ok, detail = render_to_png(window, args.out, WIDTH, HEIGHT)
            print(f"  {'ok' if ok else detail} -> {args.out}")
            app.quit()
            return False

        from gi.repository import GLib  # noqa: PLC0415

        GLib.timeout_add(600, shot)
        return False

    application.connect("activate", activate)
    application.run(["make_vision_mock"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
