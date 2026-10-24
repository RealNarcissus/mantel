"""The navigation rail.

Reproduces the reference sidebar (see `docs/DESIGN.md`): brand row
with a collapse control, a search field with a keyboard-shortcut chip, a
`Main` section of nav rows, a `Today` section of indented rows behind a hairline
rule, a `Setting` section, a user card and a Light/Dark/System theme toggle.

Every vertical position below is measured from the reference frames, so the
rail lines up with the original at the same window size.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from app import theme  # noqa: E402

WIDTH = 304

# Measured from the reference (application space, 1744 x 1168).
BRAND_TOP = 26
BRAND_LOGO = 46
SEARCH_TOP = 99
SEARCH_HEIGHT = 46
MAIN_LABEL_TOP = 172
NAV_PITCH = 48
NAV_HEIGHT = 46
TASK_PITCH = 32


class NavItem(Gtk.Button):
    """One navigation row: icon, label, optional trailing badge."""

    def __init__(self, icon_name: str, label: str, badge: str = "",
                 on_click=None):
        super().__init__()
        self.add_css_class("nav-item")
        self.icon_name = icon_name
        self.label_text = label

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)

        self._icon = theme.icon(icon_name, 20, tone="")
        row.append(self._icon)

        lbl = Gtk.Label(label=label, xalign=0)
        lbl.set_hexpand(True)
        row.append(lbl)

        self.badge_label = None
        if badge:
            self.badge_label = Gtk.Label(label=badge)
            self.badge_label.add_css_class("badge")
            row.append(self.badge_label)

        self.set_child(row)
        if on_click:
            self.connect("clicked", lambda _b: on_click(self))

    def set_active(self, active: bool) -> None:
        if active:
            self.add_css_class("active")
        else:
            self.remove_css_class("active")


class SectionHead(Gtk.Button):
    """A collapsible section header with a chevron."""

    def __init__(self, text: str):
        super().__init__()
        self.add_css_class("section-head")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.set_hexpand(True)
        box.append(lbl)
        box.append(theme.icon("expand_more", 18, tone=""))
        self.set_child(box)


class Sidebar(Gtk.Box):
    """The full navigation rail."""

    def __init__(self, on_new=None, on_navigate=None, on_task=None,
                 on_open=None, on_collapse=None, on_theme=None, on_account=None,
                 user_name: str = "Gemini", user_mail: str = "",
                 avatar_initials: str = "G",
                 accent_icon: str = "gemini_spark"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("sidebar")
        self.set_size_request(WIDTH, -1)
        self.set_vexpand(True)

        self._on_new = on_new
        self._on_navigate = on_navigate
        self._on_task = on_task
        self._on_open = on_open or (lambda _cid: None)
        self._on_theme = on_theme
        self._on_account = on_account
        self._items: dict[str, NavItem] = {}
        self._task_rows: list[Gtk.Button] = []
        self._ready = False

        self._build_brand(accent_icon, on_collapse)
        self._build_search()
        self._build_main()
        self._build_today()
        self._build_settings()
        self._build_user(user_name, user_mail, avatar_initials)
        self._build_theme_toggle()

    # -- sections -----------------------------------------------------------
    def _build_brand(self, accent_icon: str, on_collapse) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_margin_top(BRAND_TOP)
        row.set_margin_start(20)
        row.set_margin_end(18)
        row.set_margin_bottom(0)

        mark = Gtk.Box()
        mark.add_css_class("brand-mark")
        mark.set_valign(Gtk.Align.CENTER)
        mark.append(theme.icon(accent_icon, 24, tone="white"))
        row.append(mark)

        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        names.set_valign(Gtk.Align.CENTER)
        brand = Gtk.Label(label="Gemini", xalign=0)
        brand.add_css_class("brand-name")
        names.append(brand)
        sub = Gtk.Label(label="Linux client", xalign=0)
        sub.add_css_class("brand-sub")
        names.append(sub)
        row.append(names)

        box = Gtk.Box()
        box.set_hexpand(True)
        row.append(box)

        collapse = Gtk.Button()
        collapse.add_css_class("brand-collapse")
        collapse.set_child(theme.icon("keyboard_double_arrow_left", 16, tone=""))
        collapse.set_tooltip_text("Collapse sidebar")
        collapse.set_valign(Gtk.Align.CENTER)
        if on_collapse:
            collapse.connect("clicked", lambda _b: on_collapse())
        row.append(collapse)

        self.append(row)

    def _build_search(self) -> None:
        field = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        field.add_css_class("search-field")
        field.set_margin_start(20)
        field.set_margin_end(18)
        field.set_margin_top(SEARCH_TOP - BRAND_TOP - BRAND_LOGO)

        field.append(theme.icon("search", 19, tone=""))

        entry = Gtk.Entry()
        entry.add_css_class("search-entry")
        entry.set_placeholder_text("Search …")
        entry.set_hexpand(True)
        field.append(entry)

        kbd = Gtk.Label(label="⌘K")
        kbd.add_css_class("kbd")
        field.append(kbd)

        self.append(field)

    def _build_main(self) -> None:
        label = Gtk.Label(label="Main", xalign=0)
        label.add_css_class("nav-label")
        label.set_margin_start(20)
        label.set_margin_top(MAIN_LABEL_TOP - SEARCH_TOP - SEARCH_HEIGHT)
        label.set_margin_bottom(18)
        self.append(label)

        # The surfaces the real desktop app puts in the rail: chat, the
        # agentic task mode, the schedule, and the two customisation pages.
        nav = [
            ("chat", "Chat", ""),
            ("explore", "Goals", ""),
            ("checklist", "Tasks", ""),
            ("add_image_spark", "Create", ""),
            ("schedule", "Schedule", ""),
            ("extension", "Connectors", ""),
            ("notes_spark", "Skills", ""),
        ]
        for icon_name, text, badge in nav:
            item = NavItem(icon_name, text, badge, self._navigate)
            self._items[text] = item
            self.append(item)

        sep = Gtk.Separator()
        sep.add_css_class("divider")
        sep.set_margin_start(20)
        sep.set_margin_end(20)
        sep.set_margin_top(20)
        sep.set_margin_bottom(0)
        self.append(sep)

    def _build_today(self) -> None:
        """The history list: the conversations, newest first."""
        head = SectionHead("Today")
        head.set_margin_start(20)
        head.set_margin_end(20)
        head.set_margin_top(20)
        self.append(head)

        holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        holder.add_css_class("task-list")
        holder.set_margin_start(40)
        self._history_holder = holder
        self.append(holder)
        self._set_history([])

    def _build_settings(self) -> None:
        # the reference leaves the gap between the task list and this group
        # open, so the lower group sits at the foot of the rail
        filler = Gtk.Box()
        filler.set_vexpand(True)
        self.append(filler)

        sep = Gtk.Separator()
        sep.add_css_class("divider")
        sep.set_margin_start(20)
        sep.set_margin_end(20)
        self.append(sep)

        for text in ("Setting", "Help Center"):
            head = SectionHead(text)
            head.set_margin_start(20)
            head.set_margin_end(20)
            head.set_margin_top(10)
            head.connect("clicked", lambda _b, t=text: self._on_navigate_item(t))
            self.append(head)

    def _build_user(self, name: str, mail: str,
                    avatar_initials: str = "G") -> None:
        card = Gtk.Button()
        card.add_css_class("user-card")
        card_inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        card.set_margin_start(12)
        card.set_margin_end(12)
        card.set_margin_top(16)

        self._avatar = Gtk.Box()
        self._avatar.add_css_class("icon-square")
        self._avatar_label = Gtk.Label(label=avatar_initials)
        self._avatar_label.add_css_class("user-initials")
        self._avatar.append(self._avatar_label)
        card_inner.append(self._avatar)

        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        col.set_hexpand(True)
        n = Gtk.Label(label=name, xalign=0)
        n.add_css_class("user-name")
        col.append(n)
        m = Gtk.Label(label=mail, xalign=0)
        m.add_css_class("user-mail")
        m.set_ellipsize(3)
        col.append(m)
        self._user_name, self._user_mail = n, m
        card_inner.append(col)
        card_inner.append(theme.icon("expand_more", 18, tone=""))
        card.set_child(card_inner)
        if self._on_account:
            card.set_tooltip_text("Account")
            card.connect("clicked", lambda _b: self._on_account())
        self._user_card = card
        self.append(card)

    def _build_theme_toggle(self) -> None:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        row.add_css_class("theme-toggle")
        row.set_margin_start(12)
        row.set_margin_end(12)
        row.set_margin_top(10)
        row.set_margin_bottom(16)

        self._theme_buttons: dict[str, Gtk.Button] = {}
        for key, icon_name, label in (
            ("light", "light_mode", "Light"),
            ("dark", "dark_mode", "Dark"),
            ("system", "contrast", "System"),
        ):
            btn = Gtk.Button()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            box.append(theme.icon(icon_name, 15, tone=""))
            box.append(Gtk.Label(label=label))
            btn.set_child(box)
            btn.connect("clicked", lambda _b, k=key: self._set_theme(k))
            self._theme_buttons[key] = btn
            row.append(btn)
        self.append(row)
        self.set_theme("light")
        self._ready = True

    # -- behaviour ----------------------------------------------------------
    def _set_theme(self, key: str) -> None:
        for k, btn in self._theme_buttons.items():
            if k == key:
                btn.add_css_class("active")
            else:
                btn.remove_css_class("active")
        if self._on_theme and self._ready:
            self._on_theme(key)

    def set_theme(self, key: str, notify: bool = True) -> None:
        """Highlight a scheme. `notify=False` avoids calling back."""
        for k, btn in self._theme_buttons.items():
            if k == key:
                btn.add_css_class("active")
            else:
                btn.remove_css_class("active")
        if notify and self._on_theme and self._ready:
            self._on_theme(key)

    def _on_navigate_item(self, label: str) -> None:
        """Navigate from a row that is not a NavItem."""
        if self._on_navigate:
            self._on_navigate(label)

    def _navigate(self, item: NavItem) -> None:
        for _name, other in self._items.items():
            other.set_active(other is item)
        if self._on_navigate:
            self._on_navigate(item.label_text)

    def set_active(self, name: str) -> None:
        """Highlight one rail row; an empty name clears the highlight."""
        for label, item in self._items.items():
            item.set_active(bool(name) and label == name)

    def set_account(self, name: str, mail: str, initials: str) -> None:
        """Update the account card at the foot of the rail."""
        self._user_name.set_text(name)
        self._user_mail.set_text(mail)
        self._avatar_label.set_text(initials or "?")

    def set_conversations(self, conversations, status_for=None) -> None:
        """Show the conversation history, newest first."""
        self._set_history(conversations, status_for)

    def _set_history(self, conversations, status_for=None) -> None:
        from app import session as session_mod  # noqa: PLC0415

        while (child := self._history_holder.get_first_child()) is not None:
            self._history_holder.remove(child)
        if not conversations:
            empty = Gtk.Label(label="No chats yet", xalign=0)
            empty.add_css_class("status-dot")
            empty.set_margin_top(6)
            empty.set_margin_start(12)
            self._history_holder.append(empty)
            return
        for conv in list(conversations)[:8]:
            status = status_for(conv) if status_for else session_mod.STATUS_IDLE
            btn = Gtk.Button()
            btn.add_css_class("task-row")
            btn.set_halign(Gtk.Align.FILL)
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            dot = Gtk.Box()
            dot.add_css_class("status-dot")
            dot.add_css_class(f"status-dot-{status}")
            dot.set_size_request(8, 8)
            dot.set_valign(Gtk.Align.CENTER)
            row.append(dot)
            lbl = Gtk.Label(label=conv.title, xalign=0)
            lbl.set_hexpand(True)
            lbl.set_ellipsize(3)
            row.append(lbl)
            btn.set_child(row)
            btn.set_tooltip_text(conv.title)
            btn.connect("clicked", lambda _b, c=conv: self._on_open(c.id))
            self._history_holder.append(btn)

    def set_badge(self, name: str, badge: str) -> None:
        item = self._items.get(name)
        if item and item.badge_label:
            item.badge_label.set_text(badge)
