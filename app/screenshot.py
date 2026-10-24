"""Screen capture: attach what is on screen to a prompt.

The desktop app's "Share window" and "Speak to Window" both start by capturing
the screen. On Linux the portable route is the XDG portal
(`org.freedesktop.portal.Screenshot`), which asks the compositor nicely and
works on Wayland and X11 alike. Two direct tools are tried as fallbacks, and
everything fails with a message rather than an exception.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"


def _output_dir() -> Path:
    base = Path(os.environ.get("XDG_PICTURES_DIR")
                or (Path.home() / "Pictures"))
    for cand in (base / "Gemini" / "screenshots",
                 Path(tempfile.gettempdir()) / "gemini-shots"):
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / ".write-probe"
            probe.write_text("")
            probe.unlink()
            return cand
        except OSError:
            continue
    return Path(tempfile.mkdtemp(prefix="gemini-shots-"))


def _target_path() -> Path:
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    return _output_dir() / f"screenshot-{stamp}.png"


def capture_via_portal(timeout: int = 25) -> str | None:
    """Ask the compositor for a screenshot through the portal."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error:
        return None

    state: dict = {}
    loop = GLib.MainLoop()
    token = f"gemini{int(time.time() * 1000)}"

    def on_response(_conn, _sender, _path, _iface, _signal, params):
        try:
            code, results = params.unpack()
        except (TypeError, ValueError):
            loop.quit()
            return
        state["code"] = code
        uri = results.get("uri") if isinstance(results, dict) else None
        if uri:
            state["uri"] = str(uri)
        loop.quit()

    subscription = bus.signal_subscribe(
        PORTAL, "org.freedesktop.portal.Request", "Response",
        None, None, Gio.DBusSignalFlags.NONE, on_response)

    try:
        bus.call_sync(
            PORTAL, PORTAL_PATH, "org.freedesktop.portal.Screenshot",
            "Screenshot",
            GLib.Variant("(sa{sv})", (
                "",
                {"handle_token": GLib.Variant("s", token),
                 "interactive": GLib.Variant("b", False)},
            )),
            None, Gio.DBusCallFlags.NONE, 10000, None)
    except GLib.Error:
        bus.signal_unsubscribe(subscription)
        return None

    timed_out = {"value": False}

    def _give_up():
        timed_out["value"] = True
        loop.quit()
        return False

    timer = GLib.timeout_add_seconds(timeout, _give_up)
    loop.run()
    GLib.source_remove(timer)
    bus.signal_unsubscribe(subscription)

    uri = state.get("uri")
    if not uri:
        return None
    if uri.startswith("file://"):
        uri = uri[len("file://"):]
    return uri if Path(uri).is_file() else None


def capture_via_tool() -> str | None:
    """Fall back to a direct capture tool."""
    target = _target_path()
    candidates: list[list[str]] = []
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("grim"):
        candidates.append(["grim", str(target)])
    if shutil.which("import"):
        candidates.append(["import", "-window", "root", str(target)])
    for argv in candidates:
        try:
            result = subprocess.run(argv, capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0 and target.is_file() and target.stat().st_size:
            return str(target)
    return None


def _file_it(path: str) -> str:
    """Move a capture into the app's own folder, keeping the name clear."""
    source = Path(path)
    target = _target_path()
    try:
        if source.resolve() != target.resolve():
            shutil.move(str(source), str(target))
            return str(target)
    except OSError:
        pass
    return path


def capture() -> tuple[bool, str]:
    """Take a screenshot. Returns (ok, path or error message)."""
    path = capture_via_portal()
    if path:
        return True, _file_it(path)
    path = capture_via_tool()
    if path:
        return True, path
    return False, ("Could not capture the screen. The desktop portal did not "
                   "respond and no capture tool (grim, import) is available.")
