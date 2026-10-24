"""Composer: the input shell and the row of controls beneath it.

The control row follows the desktop agents: the row under the prompt box
holds the mode toggle, the tools menu, the working folder, the approval
mode, the model and the effort level.  The approval selector is deliberately
*under* the prompt, where Codex puts it.
"""
from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from app import session as session_mod
from app import theme  # noqa: E402

MAX_LINES_PX = 220
#: Width of the composer's text field, in pixels.
COMPOSER_MEASURE = 720
PLACEHOLDER = "Ask Mantel…"
PLACEHOLDER_TASK = "Describe a task…"
PLACEHOLDER_RESEARCH = "What should Mantel research?"


class Composer(Gtk.Box):
    """Text entry plus its controls. Calls back on submit / stop."""

    def __init__(self, on_submit, on_stop=None, on_pick_workspace=None,
                 on_pick_model=None, on_pick_approval=None, on_pick_effort=None,
                 on_toggle_mode=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._on_submit = on_submit
        self._on_stop = on_stop
        self._on_pick_model = on_pick_model
        self._on_pick_approval = on_pick_approval
        self._on_pick_effort = on_pick_effort
        self._on_toggle_mode = on_toggle_mode
        self._streaming = False
        self._placeholder = PLACEHOLDER
        self._mode = session_mod.MODE_CHAT

        shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        shell.add_css_class("composer-shell")
        shell.set_size_request(COMPOSER_MEASURE, -1)

        self.view = Gtk.TextView()
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_accepts_tab(False)
        self.view.add_css_class("composer")
        self._set_placeholder(True)
        self.view.get_buffer().connect("changed", self._on_changed)
        shell.append(self.view)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        controls.set_margin_start(10)
        controls.set_margin_end(10)
        controls.set_margin_bottom(10)

        # --- Chat / Task toggle (the desktop app's Spark → Task mode) -------
        self.mode_chat = Gtk.ToggleButton(label="Chat")
        self.mode_task = Gtk.ToggleButton(label="Task")
        self.mode_research = Gtk.ToggleButton(label="Research")
        self.mode_chat.set_active(True)
        self.mode_task.set_group(self.mode_chat)
        self.mode_research.set_group(self.mode_chat)
        for button in (self.mode_chat, self.mode_task, self.mode_research):
            button.connect("toggled", self._on_mode_toggled)
        mode_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        mode_row.add_css_class("mode-switch")
        mode_row.append(self.mode_chat)
        mode_row.append(self.mode_task)
        mode_row.append(self.mode_research)
        controls.append(mode_row)

        self.tools_btn = theme.icon_button("add", "Add files and tools")
        self.tools_btn.set_size_request(34, 34)
        controls.append(self.tools_btn)

        self.workspace_btn = Gtk.Button()
        self.workspace_btn.add_css_class("chip-grade")
        self.workspace_label = Gtk.Label(label="workspace")
        self.workspace_label.set_ellipsize(3)
        self.workspace_label.set_max_width_chars(18)
        self.workspace_btn.set_child(self.workspace_label)
        self.workspace_btn.set_tooltip_text("Working folder")
        if on_pick_workspace:
            self.workspace_btn.connect("clicked", lambda _b: on_pick_workspace())
        controls.append(self.workspace_btn)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        controls.append(spacer)

        # --- approval mode (Codex: Ask for approval / Approve for me / …) --
        self.approval_btn = Gtk.Button()
        self.approval_btn.add_css_class("chip-grade")
        self.approval_label = Gtk.Label(label="Ask for approval")
        self.approval_btn.set_child(self.approval_label)
        self.approval_btn.set_tooltip_text(
            "What the agent may do without asking")
        if on_pick_approval:
            self.approval_btn.connect("clicked", lambda _b: on_pick_approval())
        controls.append(self.approval_btn)

        # --- model -----------------------------------------------------------
        self.model_btn = Gtk.Button()
        self.model_btn.add_css_class("chip-grade")
        self.model_label = Gtk.Label(label="model")
        self.model_btn.set_child(self.model_label)
        self.model_btn.set_tooltip_text("Choose model")
        if on_pick_model:
            self.model_btn.connect("clicked", lambda _b: on_pick_model())
        controls.append(self.model_btn)

        # --- effort ----------------------------------------------------------
        self.effort_btn = Gtk.Button()
        self.effort_btn.add_css_class("chip-grade")
        self.effort_label = Gtk.Label(label="medium")
        self.effort_btn.set_child(self.effort_label)
        self.effort_btn.set_tooltip_text("Reasoning effort")
        if on_pick_effort:
            self.effort_btn.connect("clicked", lambda _b: on_pick_effort())
        controls.append(self.effort_btn)

        self.send_btn = Gtk.Button()
        self.send_btn.add_css_class("send-btn")
        self.send_btn.set_child(theme.icon("arrow_upward", 20, tone="dark"))
        self.send_btn.set_tooltip_text("Send  (Enter)")
        self.send_btn.connect("clicked", lambda _b: self._activate())
        controls.append(self.send_btn)

        shell.append(controls)
        self.append(shell)

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.view.add_controller(key)

    @staticmethod
    def _wrap(widget: Gtk.Widget, css: str) -> Gtk.Widget:
        holder = Gtk.Box()
        holder.add_css_class(css)
        holder.append(widget)
        return holder

    # -- mode ---------------------------------------------------------------
    def _on_mode_toggled(self, button: Gtk.ToggleButton) -> None:
        if not button.get_active():
            return
        self._mode = {
            self.mode_task: session_mod.MODE_TASK,
            self.mode_research: session_mod.MODE_RESEARCH,
        }.get(button, session_mod.MODE_CHAT)
        self._set_placeholder(True)
        if self._on_toggle_mode:
            self._on_toggle_mode(self._mode)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        button = {session_mod.MODE_TASK: self.mode_task,
                  session_mod.MODE_RESEARCH: self.mode_research}.get(
                      mode, self.mode_chat)
        if not button.get_active():
            button.set_active(True)

    @property
    def mode(self) -> str:
        return self._mode

    # -- placeholder --------------------------------------------------------
    def _set_placeholder(self, on: bool) -> None:
        if on:
            text = {session_mod.MODE_TASK: PLACEHOLDER_TASK,
                    session_mod.MODE_RESEARCH: PLACEHOLDER_RESEARCH}.get(
                        self._mode, PLACEHOLDER)
            self._placeholder = text
            self.view.get_buffer().set_text(text)
            self.view.set_opacity(0.55)

    def _on_changed(self, *_args) -> None:
        buf = self.view.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        if text.strip() and text.strip() != self._placeholder:
            self.view.set_opacity(1.0)
        self._autosize()
        self._sync_send()

    def _autosize(self) -> None:
        lines = self.view.get_buffer().get_line_count()
        self.view.set_size_request(-1, min(MAX_LINES_PX, max(30, lines * 23)))

    def _sync_send(self) -> None:
        if self._streaming:
            self.send_btn.set_sensitive(True)
            return
        self.send_btn.set_sensitive(bool(self.text()))

    # -- key handling -------------------------------------------------------
    def _on_key(self, _c, keyval, _code, state) -> bool:
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if state & Gdk.ModifierType.SHIFT_MASK:
                return False  # newline
            self._activate()
            return True
        if keyval == Gdk.KEY_Escape and self._streaming:
            self._do_stop()
            return True
        return False

    def _activate(self) -> None:
        if self._streaming:
            self._do_stop()
            return
        text = self.text()
        if text:
            self._on_submit(text)

    def _do_stop(self) -> None:
        if self._on_stop:
            self._on_stop()

    # -- public API ---------------------------------------------------------
    def text(self) -> str:
        buf = self.view.get_buffer()
        raw = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
        return "" if raw == self._placeholder else raw

    def clear(self) -> None:
        self.view.get_buffer().set_text("")
        self._set_placeholder(True)
        self._autosize()
        self._sync_send()

    def focus(self) -> None:
        self.view.grab_focus()

    def set_model(self, label: str) -> None:
        self.model_label.set_text(label)

    def set_effort(self, label: str) -> None:
        self.effort_label.set_text(label)

    def set_approval(self, key: str) -> None:
        mode = session_mod.MODE_BY_KEY.get(key)
        self.approval_label.set_text(mode.label if mode else key)

    def set_workspace(self, path: str) -> None:
        self.workspace_label.set_text(os.path.basename(path.rstrip("/")) or path)
        self.workspace_btn.set_tooltip_text(path)

    def set_streaming(self, streaming: bool) -> None:
        self._streaming = streaming
        if streaming:
            self.send_btn.set_child(theme.icon("stop", 20, filled=True,
                                               tone="dark"))
            self.send_btn.set_tooltip_text("Stop  (Esc)")
            self.send_btn.set_sensitive(True)
        else:
            self.send_btn.set_child(theme.icon("arrow_upward", 20,
                                               tone="dark"))
            self.send_btn.set_tooltip_text("Send  (Enter)")
            self._sync_send()
