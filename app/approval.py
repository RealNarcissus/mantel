"""Approval cards.

When the engine asks for something it was not granted, the client shows a
card with the narrowest useful choices — the same ladder Codex and Claude
offer: *Allow once* / *Allow for this session* / *Always allow in this
folder* / *Deny*.

The cards are not modal and are anchored to the bottom of the transcript, so
a stack of them never slides under the pointer (a bug Claude had to fix).
Enter approves, Escape declines — the keyboard-first convention.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from app import session as session_mod
from app import theme  # noqa: E402


class ApprovalCard(Gtk.Box):
    """One request for permission."""

    def __init__(self, approval: session_mod.Approval, on_decide,
                 can_grant: bool = True):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add_css_class("approval-card")
        self.approval = approval
        self._on_decide = on_decide

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        head.append(theme.icon("lock", 18, tone=""))
        title = Gtk.Label(label=approval.title, xalign=0)
        title.add_css_class("approval-title")
        head.append(title)
        self.append(head)

        detail = approval.path or approval.command
        if detail:
            row = Gtk.Label(label=detail, xalign=0)
            row.add_css_class("approval-detail")
            row.set_ellipsize(3)
            self.append(row)

        ask = Gtk.Label(
            label=f"Gemini wants to {approval.verb}. It has not been allowed "
                  f"to do that yet.", xalign=0)
        ask.add_css_class("metric-sub")
        self.append(ask)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for key, label in session_mod.APPROVAL_SCOPES:
            btn = Gtk.Button(label=label)
            btn.add_css_class("pill")
            if not can_grant:
                btn.set_sensitive(False)
                btn.set_tooltip_text(
                    "The engine's permission file cannot be written on this machine.")
            btn.connect("clicked", lambda _b, k=key: self._decide(k))
            buttons.append(btn)
        deny = Gtk.Button(label="Deny")
        deny.add_css_class("pill")
        deny.connect("clicked", lambda _b: self._decide("deny"))
        buttons.append(deny)
        self.append(buttons)

    def _decide(self, scope: str) -> None:
        self._on_decide(self.approval, scope)


class DialogCard(Gtk.Box):
    """A question from the engine that is blocking until answered.

    With the Pi adapter this is how approvals arrive: the engine's `tool_call`
    hook asks before the tool runs, so "deny" means the call never happened.
    The card is deliberately the same shape as `ApprovalCard` — same voice,
    same place, same keyboard rules.
    """

    def __init__(self, request: dict, on_answer):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add_css_class("approval-card")
        self.request = request
        self._on_answer = on_answer

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        head.append(theme.icon("lock", 18, tone=""))
        title = Gtk.Label(label=request.get("title") or "Approve this action?",
                          xalign=0)
        title.add_css_class("approval-title")
        title.set_ellipsize(3)
        title.set_hexpand(True)
        head.append(title)
        self.append(head)

        message = request.get("message") or ""
        if message:
            detail = Gtk.Label(label=message, xalign=0)
            detail.add_css_class("approval-detail")
            detail.set_wrap(True)
            self.append(detail)

        note = Gtk.Label(
            label="The assistant is paused until you answer.  Esc denies.",
            xalign=0)
        note.add_css_class("approval-note")
        self.append(note)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.set_halign(Gtk.Align.START)
        options = request.get("options") or ["Allow", "Deny"]
        for index, option in enumerate(options):
            button = Gtk.Button(label=str(option))
            # reuse the shell's own button styles so the card matches the rest
            button.add_css_class("btn-primary" if index == 0 else "btn-secondary")
            if str(option).lower().startswith("deny"):
                button.add_css_class("approval-deny")
            button.connect("clicked", lambda _b, o=option: self._answer(str(o)))
            row.append(button)
        self.append(row)

    def _answer(self, value: str) -> None:
        self.set_visible(False)
        self._on_answer(value)

    def deny(self) -> None:
        """Escape: answer with the deny option, or cancel the dialog."""
        options = self.request.get("options") or []
        for option in options:
            if str(option).lower().startswith("deny"):
                self._answer(str(option))
                return
        self.set_visible(False)
        self._on_answer(None)


class ApprovalStack(Gtk.Box):
    """A non-modal stack of approval cards."""

    def __init__(self, on_decide):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("approval-stack")
        self._on_decide = on_decide
        self.set_visible(False)

    def show(self, approvals: list[session_mod.Approval],
             can_grant: bool = True) -> None:
        while (child := self.get_first_child()) is not None:
            self.remove(child)
        for approval in approvals:
            self.append(ApprovalCard(approval, self._on_decide, can_grant))
        self.set_visible(bool(approvals))

    def ask(self, request: dict, on_answer) -> None:
        """Show one blocking engine question. Replaces any previous card."""
        self.clear()
        self.append(DialogCard(request, on_answer))
        self.set_visible(True)

    def deny_current(self) -> bool:
        """Deny the visible question, if any. Returns True when one was shown."""
        child = self.get_first_child()
        while child is not None:
            if isinstance(child, DialogCard):
                child.deny()
                return True
            child = child.get_next_sibling()
        return False

    def clear(self) -> None:
        while (child := self.get_first_child()) is not None:
            self.remove(child)
        self.set_visible(False)
