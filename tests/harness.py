"""Reusable offscreen render harness.

The development host has no capturable compositor (no wlr-screencopy, no
portal screenshot), so UI is verified by rendering the real GTK4 widget tree
into a PNG and inspecting it. This renders through the window's own GSK
renderer, so what lands in the PNG is what the compositor would be handed.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gi  # noqa: E402

from app import fonts_env  # noqa: F401,E402  (must precede Pango init)

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Graphene, Gsk, Gtk  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def render_to_png(widget: Gtk.Widget, path: str, width: int, height: int,
                  attempts: int = 6) -> tuple[bool, str]:
    """Render a widget to a PNG.

    Two things matter here.  A snapshot can come back empty if the widget has
    not been drawn since its last resize, so the snapshot is retried.  And
    `queue_draw()` must NOT be called first: it invalidates the cached
    render node, and a snapshot taken before the next frame then finds
    nothing to draw — which is exactly how a live capture came back blank.
    """
    import time

    targets = [widget]
    if isinstance(widget, Gtk.Window):
        child = widget.get_child()
        if child is not None:
            targets.append(child)

    node = None
    for attempt in range(attempts):
        for target in targets:
            snap = Gtk.Snapshot.new()
            Gtk.WidgetPaintable.new(target).snapshot(snap, width, height)
            node = snap.to_node()
            if node is not None:
                break
        if node is not None:
            break
        time.sleep(0.05 * (attempt + 1))
    if node is None:
        return False, "empty-snapshot"
    native = widget.get_native()
    renderer = native.get_renderer() if native is not None else None
    if renderer is None:
        renderer = Gsk.CairoRenderer.new()
        renderer.realize(None)
    tex = renderer.render_texture(node, Graphene.Rect().init(0, 0, width, height))
    if tex is None:
        return False, "null-texture"
    return tex.save_to_png(path), "ok"


def shoot(
    build,
    out: str,
    width: int = 1000,
    height: int = 700,
    settle_ms: int = 1200,
    app_id: str = "dev.gemini.probe",
    setup=None,
) -> int:
    """Build a widget via `build()`, show it, and write it to `out` as PNG.

    `setup()` runs once GTK (and therefore the GDK display) is up, which is
    where theme/font registration has to happen.
    """
    status = {"code": 0}

    class Probe(Adw.Application):
        def do_activate(self):
            if setup is not None:
                setup()
            window = Adw.ApplicationWindow(
                application=self, default_width=width, default_height=height
            )
            window.set_content(build())
            window.present()

            def grab():
                try:
                    ok, how = render_to_png(window, out, width, height)
                    print(f"RENDER ok={ok} how={how} -> {out}")
                    if not ok:
                        status["code"] = 1
                except Exception as exc:  # noqa: BLE001
                    print(f"RENDER FAILED {type(exc).__name__}: {exc}")
                    status["code"] = 2
                self.quit()
                return False

            GLib.timeout_add(settle_ms, grab)

    Probe(application_id=app_id).run([])
    return status["code"]
