"""The Google Account page.

The desktop app signs in with a Google Account, shows it in a menu at the
bottom of the sidebar, and keeps the credentials in
``~/.gemini/oauth_creds.json`` — the same file the engine reads, so signing
in here signs the engine in too.

The page has three states, switched by :func:`app.account.load_account`:

* **signed out** — a card in the middle of the page with a sign-in button,
* **signing in** — the same card, waiting on the browser round-trip,
* **signed in** — the account, its scopes, and where its credentials live.

The sign-in itself is the loopback OAuth exchange implemented in
:mod:`app.account`.  ``SignIn.result()`` blocks until the browser comes back
to the local callback server, so it is polled on a worker thread and the
result is marshalled onto the GTK thread with ``GLib.idle_add``: the main
loop is never blocked.
"""
from __future__ import annotations

import datetime
import threading
from collections.abc import Callable

from app import theme  # noqa: F401  (registers the bundled fonts before Gtk)

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from app import account as account_mod  # noqa: E402
from app.cards import (hspacer, body, card, chip, divider, icon_square,  # noqa: E402
                       pill_button, spacer, title)

#: The three states the page can be in.
STATE_SIGNED_OUT = "signed-out"
STATE_SIGNING_IN = "signing-in"
STATE_SIGNED_IN = "signed-in"

#: How long the worker waits for the browser to come back.
SIGNIN_TIMEOUT = 300.0

#: Where the engine keeps the credentials, as the user sees it.
CREDS_DISPLAY = "~/.gemini/oauth_creds.json"


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

    The bundled icons are white in their base rendering and navy in the
    "dark" tone, so a black pill needs the white one and a light pill the
    navy one.
    """
    button = pill_button(label, icon_name, primary=primary, on_click=on_click)
    if primary and icon_name:
        scheme = theme.scheme()
        tone = "white" if _is_dark(scheme.pill_bg) else scheme.on_accent
        row = button.get_child()
        image = row.get_first_child() if row is not None else None
        if isinstance(image, Gtk.Image):
            image.set_from_paintable(theme.icon_texture(icon_name, tone))
    return button


def _centred(label: Gtk.Label) -> Gtk.Label:
    """Centre a label inside a card."""
    label.set_xalign(0.5)
    label.set_halign(Gtk.Align.CENTER)
    return label


# --- the page ---------------------------------------------------------------


class AccountPage(Gtk.Box):
    """Sign in, sign out, and show what the signed-in account can reach.

    Public API
        ``AccountPage(on_signed_in=None, on_signed_out=None)``
            ``on_signed_in(account)`` is called once the OAuth exchange
            succeeds; ``on_signed_out()`` is called after the credentials
            have been removed.
        ``refresh()``
            Re-read the stored credentials and swap to the matching state.
        ``start_signin()`` / ``cancel_signin()`` / ``sign_out()``
            Drive the flow from the shell (the sidebar account menu).
        ``state`` / ``account`` / ``signed_in``
            What the page is currently showing.
    """

    def __init__(self, on_signed_in: Callable[[object], None] | None = None,
                 on_signed_out: Callable[[], None] | None = None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("content")
        self.set_margin_start(36)
        self.set_margin_end(36)
        self.set_margin_top(8)
        self.set_margin_bottom(28)

        self._on_signed_in = on_signed_in
        self._on_signed_out = on_signed_out

        self._account = account_mod.Account()
        self._state = STATE_SIGNED_OUT
        self._flow: account_mod.SignIn | None = None
        self._cancelled = False
        self._copy_label: Gtk.Label | None = None
        self._copy_reset: int = 0

        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._scroll.set_vexpand(True)
        self.append(self._scroll)

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._content.set_vexpand(True)
        self._scroll.set_child(self._content)

        self.refresh()

    # -- public API ----------------------------------------------------------
    @property
    def state(self) -> str:
        """One of ``STATE_SIGNED_OUT``, ``STATE_SIGNING_IN``, ``STATE_SIGNED_IN``."""
        return self._state

    @property
    def account(self) -> account_mod.Account:
        """The account the page is currently showing."""
        return self._account

    @property
    def signed_in(self) -> bool:
        """True when a Google Account is signed in."""
        return self._state == STATE_SIGNED_IN

    def refresh(self) -> None:
        """Re-read the stored credentials and show the matching state.

        Does nothing while a sign-in is in flight — the browser owns the
        card until the flow finishes or is cancelled.
        """
        if self._flow is not None:
            return
        account = account_mod.load_account()
        self._account = account
        if account.email:
            self._set_state(STATE_SIGNED_IN, self._build_signed_in(account))
        else:
            self._set_state(STATE_SIGNED_OUT, self._build_signed_out())

    def start_signin(self) -> None:
        """Begin the OAuth round-trip; the browser opens in the background."""
        if self._flow is not None:
            return
        self._cancelled = False
        flow = account_mod.SignIn(open_browser=True)
        if not flow.start():
            self._set_state(
                STATE_SIGNED_OUT,
                self._build_signed_out(
                    getattr(flow, "error", "") or "Could not start sign-in."),
            )
            return
        self._flow = flow
        self._set_state(STATE_SIGNING_IN, self._build_signing_in(flow.url))
        worker = threading.Thread(target=self._await_signin, args=(flow,),
                                  name="gemini-signin", daemon=True)
        worker.start()

    def cancel_signin(self) -> None:
        """Stop the sign-in and go back to the signed-out card."""
        flow = self._flow
        self._cancelled = True
        self._flow = None
        if flow is not None:
            # `app.account.SignIn` has no public cancel, so the loopback
            # callback server is closed and the worker's wait released by
            # hand.  Both are guarded, so a future version of the data layer
            # cannot turn this into an exception.
            done = getattr(flow, "_done", None)
            if done is not None:
                try:
                    done.set()
                except Exception:  # noqa: BLE001
                    pass
            cleanup = getattr(flow, "_cleanup", None)
            if callable(cleanup):
                try:
                    cleanup()
                except Exception:  # noqa: BLE001
                    pass
        self._set_state(STATE_SIGNED_OUT, self._build_signed_out())

    def sign_out(self) -> bool:
        """Remove the stored credentials and show the signed-out card."""
        removed = account_mod.sign_out()
        self._account = account_mod.Account()
        self._set_state(STATE_SIGNED_OUT, self._build_signed_out())
        if self._on_signed_out is not None:
            self._on_signed_out()
        return removed

    # -- the sign-in flow -----------------------------------------------------
    def _await_signin(self, flow: account_mod.SignIn) -> None:
        """Poll the flow on a worker thread; never on the GTK thread."""
        try:
            account = flow.result(timeout=SIGNIN_TIMEOUT)
        except Exception as exc:  # noqa: BLE001 - report, never raise
            GLib.idle_add(self._signin_failed, str(exc))
            return
        GLib.idle_add(self._signin_done, flow, account)

    def _signin_done(self, flow: account_mod.SignIn,
                     account: account_mod.Account | None) -> bool:
        """The flow finished: either signed in, or it failed."""
        self._flow = None
        if self._cancelled:
            return False
        if account is not None and getattr(account, "email", ""):
            self.refresh()
            if self._on_signed_in is not None:
                self._on_signed_in(account)
            return False
        message = (getattr(flow, "error", "")
                   or "Sign-in did not complete. Please try again.")
        self._set_state(STATE_SIGNED_OUT, self._build_signed_out(message))
        return False

    def _signin_failed(self, message: str) -> bool:
        """The flow blew up; show the reason on the signed-out card."""
        self._flow = None
        if self._cancelled:
            return False
        self._set_state(STATE_SIGNED_OUT, self._build_signed_out(message))
        return False

    def _copy_link(self) -> None:
        """Copy the authorisation URL so it can be opened by hand."""
        flow = self._flow
        url = getattr(flow, "url", "") if flow is not None else ""
        if not url:
            return
        display = Gdk.Display.get_default()
        if display is None:
            return
        display.get_clipboard().set(url)
        self._flash_copied()

    def _flash_copied(self) -> None:
        """Acknowledge the copy on the button itself."""
        if self._copy_label is None:
            return
        self._copy_label.set_text("Copied")
        if self._copy_reset:
            GLib.source_remove(self._copy_reset)
        self._copy_reset = GLib.timeout_add(1800, self._restore_copy_label)

    def _restore_copy_label(self) -> bool:
        self._copy_reset = 0
        if self._copy_label is not None:
            self._copy_label.set_text("Copy link")
        return False

    # -- state plumbing ------------------------------------------------------
    def _set_state(self, state: str, widget: Gtk.Widget) -> None:
        """Swap the page to `state` and show `widget`."""
        self._state = state
        child = self._content.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self._content.remove(child)
            child = following
        # Two expanding spacers put the card in the middle of the page.
        self._content.append(hspacer())
        self._content.append(widget)
        self._content.append(hspacer())

    def _column(self, *widgets: Gtk.Widget) -> Gtk.Box:
        """A centred column of widgets."""
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        column.set_halign(Gtk.Align.CENTER)
        for widget in widgets:
            column.append(widget)
        return column

    def _error_box(self, message: str) -> Gtk.Widget:
        """The shared error style, used for every failure on this page."""
        label = Gtk.Label(label=message, xalign=0)
        label.add_css_class("error-box")
        label.set_wrap(True)
        label.set_max_width_chars(52)
        label.set_halign(Gtk.Align.CENTER)
        return label

    def _note(self, text: str) -> Gtk.Label:
        """The muted note that sits below a card."""
        note = body(text)
        _centred(note)
        note.set_max_width_chars(64)
        return note

    # -- state (a): signed out ------------------------------------------------
    def _build_signed_out(self, error: str = "") -> Gtk.Widget:
        """The card that invites the user to sign in."""
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        inner.set_margin_start(34)
        inner.set_margin_end(34)
        inner.set_margin_top(32)
        inner.set_margin_bottom(30)
        panel.append(inner)

        mark = Gtk.Box()
        mark.set_halign(Gtk.Align.CENTER)
        mark.append(theme.icon("gemini_spark", 48, tone=""))
        inner.append(mark)

        heading = title("Sign in with your Google Account", 24)
        _centred(heading)
        heading.set_margin_top(18)
        inner.append(heading)

        paragraph = body(
            "Signing in gives the app access to your Gemini subscription: "
            "the models your plan includes and — in Task mode — the agent "
            "features that run them. Scheduled prompts need it too.")
        _centred(paragraph)
        paragraph.set_max_width_chars(56)
        paragraph.set_margin_top(10)
        inner.append(paragraph)

        if error:
            box = self._error_box(error)
            box.set_margin_top(18)
            inner.append(box)

        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        button_row.set_halign(Gtk.Align.CENTER)
        button_row.set_margin_top(22)
        button_row.append(_pill("Sign in with Google", "gemini_spark",
                                primary=True, on_click=self.start_signin))
        inner.append(button_row)

        note = self._note(
            "Signing in opens a browser window and asks Google for "
            "permission. The credentials it returns are stored on this "
            f"machine only, in {CREDS_DISPLAY}.")
        note.set_margin_top(16)

        column = self._column(panel, note)
        column.set_valign(Gtk.Align.CENTER)
        return column

    # -- state (b): signing in -----------------------------------------------
    def _build_signing_in(self, url: str) -> Gtk.Widget:
        """The card that waits for the browser to come back."""
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        inner.set_margin_start(34)
        inner.set_margin_end(34)
        inner.set_margin_top(32)
        inner.set_margin_bottom(30)
        panel.append(inner)

        spinner = Gtk.Spinner()
        spinner.set_size_request(28, 28)
        spinner.set_halign(Gtk.Align.CENTER)
        spinner.start()
        inner.append(spinner)

        heading = title("Waiting for you to finish signing in…", 19)
        _centred(heading)
        heading.set_margin_top(16)
        inner.append(heading)

        paragraph = body(
            "Your browser should have opened the Google sign-in page. "
            "Finish there and this window will continue on its own; if it "
            "did not open, use the link below.")
        _centred(paragraph)
        paragraph.set_max_width_chars(56)
        paragraph.set_margin_top(10)
        inner.append(paragraph)

        link = Gtk.Label(label=url, selectable=True)
        link.set_wrap(True)
        link.set_max_width_chars(56)
        link.set_xalign(0.5)
        link.add_css_class("md-code")
        link.set_margin_top(18)
        inner.append(link)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        buttons.set_halign(Gtk.Align.CENTER)
        buttons.set_margin_top(20)
        copy = _pill("Copy link", "copy", on_click=self._copy_link)
        label = copy.get_child()
        self._copy_label = (label.get_last_child()
                            if isinstance(label, Gtk.Box) else None)
        buttons.append(copy)
        buttons.append(_pill("Cancel", "close", on_click=self.cancel_signin))
        inner.append(buttons)

        note = self._note(
            "Nothing is sent anywhere else: the credentials stay in "
            f"{CREDS_DISPLAY} on this machine.")
        note.set_margin_top(16)

        column = self._column(panel, note)
        column.set_valign(Gtk.Align.CENTER)
        return column

    # -- state (c): signed in -------------------------------------------------
    def _build_signed_in(self, account: account_mod.Account) -> Gtk.Widget:
        """The card that shows who is signed in."""
        panel = card()
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        inner.set_margin_start(32)
        inner.set_margin_end(32)
        inner.set_margin_top(28)
        inner.set_margin_bottom(26)
        panel.append(inner)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        avatar = icon_square("person", "", 64)
        avatar.set_valign(Gtk.Align.CENTER)
        head.append(avatar)

        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        name = title(account.display_name, 24)
        names.append(name)
        mail = body(account.email, wrap=False)
        names.append(mail)
        names.set_valign(Gtk.Align.CENTER)
        head.append(names)

        head.append(hspacer())

        badge = Gtk.Box()
        badge.set_valign(Gtk.Align.CENTER)
        badge.append(chip(account.initials))
        head.append(badge)
        inner.append(head)

        rule = divider()
        rule.set_margin_top(22)
        inner.append(rule)

        inner.append(self._detail_row("lock", "Scopes",
                                       self._scopes_value(account)))
        inner.append(divider())
        inner.append(self._detail_row("schedule", "Session",
                                       self._expiry_value(account)))
        inner.append(divider())
        inner.append(self._detail_row("folder_open", "Stored at",
                                       self._path_value()))

        rule = divider()
        rule.set_margin_top(6)
        inner.append(rule)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        buttons.set_margin_top(18)
        buttons.append(_pill("Sign out", "logout", on_click=self.sign_out))
        inner.append(buttons)

        note = self._note(
            "Signing out stops the agent reaching your Gemini subscription: "
            "the models and the Task mode agent features are unavailable "
            "until you sign in again.")
        note.set_margin_top(16)

        column = self._column(panel, note)
        column.set_valign(Gtk.Align.CENTER)
        return column

    def _detail_row(self, icon_name: str, caption: str,
                    value: Gtk.Widget) -> Gtk.Widget:
        """One labelled row of account detail."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        row.set_margin_top(14)
        row.set_margin_bottom(14)

        badge = icon_square(icon_name, "", 16)
        badge.set_valign(Gtk.Align.START)
        row.append(badge)

        label = body(caption, wrap=False)
        label.set_size_request(110, -1)
        label.set_valign(Gtk.Align.START)
        row.append(label)

        value.set_valign(Gtk.Align.START)
        row.append(value)
        return row

    def _scopes_value(self, account: account_mod.Account) -> Gtk.Widget:
        """How many scopes were granted, and which ones."""
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        count = body(f"{len(account.scopes)} granted", wrap=False)
        column.append(count)
        if account.scopes:
            listing = Gtk.Label(label="\n".join(account.scopes), selectable=True)
            listing.set_xalign(0)
            listing.set_wrap(True)
            listing.set_max_width_chars(58)
            listing.add_css_class("md-code")
            column.append(listing)
        else:
            column.append(body("No scopes recorded."))
        return column

    def _expiry_value(self, account: account_mod.Account) -> Gtk.Widget:
        """When the current token runs out, or that it refreshes itself."""
        if not account.expires_at:
            if account.has_refresh_token:
                return body("Refreshes automatically", wrap=False)
            return body("No refresh token stored", wrap=False)
        when = datetime.datetime.fromtimestamp(account.expires_at)
        stamp = when.strftime("%d %b %Y, %H:%M")
        if account.expired:
            return body(f"Expired ({stamp}) — refreshes on next use",
                        wrap=False)
        return body(f"Expires {stamp}", wrap=False)

    def _path_value(self) -> Gtk.Widget:
        """Where the credentials live on disk."""
        label = Gtk.Label(label=CREDS_DISPLAY, selectable=True)
        label.set_xalign(0)
        label.add_css_class("md-code")
        return label
