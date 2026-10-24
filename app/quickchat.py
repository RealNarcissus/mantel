"""Quick chat: a summonable overlay for one-off questions.

Mirrors the desktop app's global-hotkey palette — a small centred card that
answers without disturbing the main window. On Wayland it is placed with
wlr-layer-shell (the compositor manages focus and stacking); on X11, or if
the protocol is unavailable, it degrades to an undecorated window.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from app import markdown, theme  # noqa: E402

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402

    HAVE_LAYER_SHELL = True
except (ValueError, ImportError):  # pragma: no cover - depends on host
    LayerShell = None  # type: ignore[assignment]
    HAVE_LAYER_SHELL = False

CARD_WIDTH = 720


def _layer_shell_usable() -> bool:
    """True only if this compositor actually implements wlr-layer-shell.

    Mutter and several other compositors do not, and gtk4-layer-shell needs to
    be preloaded ahead of libwayland to initialise at all. Both conditions are
    checked so the overlay can fall back to a plain window instead of failing.
    """
    if not HAVE_LAYER_SHELL:
        return False
    try:
        return bool(LayerShell.is_supported())
    except Exception:  # noqa: BLE001 - older bindings lack is_supported()
        return False


class QuickChat(Gtk.Window):
    """Borderless overlay: type a question, watch the answer stream in."""

    def __init__(self, application, engine, workspace: str = ""):
        super().__init__(application=application)
        self.engine = engine
        self.workspace = workspace
        self.turn = None
        self._raw = ""
        self._render_scheduled = False
        self._layered = False

        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(CARD_WIDTH + 32, 120)
        self.set_size_request(CARD_WIDTH + 32, 120)
        self.add_css_class("quickchat")

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class("quickchat-card")
        card.set_size_request(CARD_WIDTH, -1)
        for m in ("top", "bottom", "start", "end"):
            getattr(card, f"set_margin_{m}")(16)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        head.append(theme.icon("gem_spark", 22, tone=""))
        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Ask Mantel…")
        self.entry.set_has_frame(False)
        self.entry.set_hexpand(True)
        self.entry.set_size_request(-1, 34)
        self.entry.connect("activate", lambda _e: self.submit())
        head.append(self.entry)
        self.send_btn = theme.icon_button("arrow_upward", "Send")
        self.send_btn.set_size_request(38, 38)
        self.send_btn.connect("clicked", lambda _b: self.submit())
        head.append(self.send_btn)
        card.append(head)

        self.answer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.answer.set_visible(False)
        card.append(self.answer)

        self.set_child(card)

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.add_controller(key)

        if _layer_shell_usable():
            try:
                LayerShell.init_for_window(self)
                LayerShell.set_namespace(self, "gemini-quickchat")
                LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
                LayerShell.set_anchor(self, LayerShell.Edge.TOP, True)
                LayerShell.set_margin(self, LayerShell.Edge.TOP, 120)
                LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.EXCLUSIVE)
                self._layered = True
            except Exception:  # noqa: BLE001
                self._layered = False
        if not self._layered:
            # A plain floating window: centre it and keep it undecorated.
            self.set_halign(Gtk.Align.CENTER)
            self.set_valign(Gtk.Align.START)
            self.remove_css_class("quickchat")
            self.add_css_class("quickchat-window")

    # -- behaviour ----------------------------------------------------------
    def _on_key(self, _c, keyval, _code, _state) -> bool:
        if keyval == Gdk.KEY_Escape:
            if self.turn is not None:
                self.turn.cancel()
            self.set_visible(False)
            return True
        return False

    def summon(self) -> None:
        self.present()
        self.entry.grab_focus()
        self.entry.select_region(0, -1)

    def submit(self) -> None:
        text = self.entry.get_text().strip()
        if not text or self.turn is not None:
            return
        while (child := self.answer.get_first_child()) is not None:
            self.answer.remove(child)
        self.answer.set_visible(True)
        self._raw = ""

        spinner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        spinner.append(theme.icon("gem_spark", 18, tone=""))
        spinner.append(Gtk.Label(label="Thinking…", xalign=0,
                                 css_classes=["metric-sub"]))
        self.answer.append(spinner)

        self.turn = self.engine.run(prompt=text, cwd=self.workspace)
        self.turn.connect("delta", self._on_delta)
        self.turn.connect("finished", self._on_finished)
        self.turn.connect("failed", self._on_failed)

    def _on_delta(self, _t, delta: str) -> None:
        self._raw += delta
        if self._render_scheduled:
            return
        self._render_scheduled = True
        GLib.timeout_add(80, self._render)

    def _render(self) -> bool:
        self._render_scheduled = False
        while (child := self.answer.get_first_child()) is not None:
            self.answer.remove(child)
        for widget in markdown.render(self._raw):
            self.answer.append(widget)
        return False

    def _on_finished(self, _t, result: dict) -> None:
        self.turn = None
        text = (result or {}).get("text", "")
        if text:
            self._raw = text
        self._render()
        status = (result or {}).get("status", "")
        if status and status != "SUCCESS":
            err = Gtk.Label(label=(result or {}).get("error") or status, xalign=0)
            err.add_css_class("error-box")
            err.set_wrap(True)
            self.answer.append(err)

    def _on_failed(self, _t, message: str) -> None:
        self.turn = None
        self._render()
        err = Gtk.Label(label=message, xalign=0)
        err.add_css_class("error-box")
        err.set_wrap(True)
        self.answer.append(err)
