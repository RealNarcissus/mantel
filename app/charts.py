"""Cairo-drawn chart primitives for the Linux client.

Every "Active Targets" card in the reference design ("Hearth")
ends with a small chart, and the reference has two variants of it — both
measured from the reference design (see `docs/DESIGN.md`):

* a smooth **sparkline** with a dotted vertical rule marking the current
  position — the *Health & Longevity* target card;
* a dense **bar chart** with one contiguous region drawn darker — the
  *Financial Freedom* target card.

Both widgets are plain `Gtk.DrawingArea`s painted with Cairo. The palette is
looked up from `app.theme` *inside* the draw function, so switching between
the light and dark scheme repaints the charts in the new colours without
having to rebuild them.
"""
from __future__ import annotations

from app import theme  # noqa: E402  (imports fonts_env before GTK/Pango)

import cairo
import math
import weakref

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

# --- helpers ---------------------------------------------------------------

_LIVE: weakref.WeakSet[Gtk.DrawingArea] = weakref.WeakSet()


def refresh_all() -> None:
    """Repaint every live chart.

    Call this after `theme.set_scheme(...)` so charts pick up the new palette
    even when the display's own colour-scheme preference did not change.
    """
    for widget in list(_LIVE):
        widget.queue_draw()


def _rgb(colour: str) -> tuple[float, float, float]:
    """Parse a ``#rrggbb`` palette token into normalised floats."""
    c = colour.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return (
            int(c[0:2], 16) / 255.0,
            int(c[2:4], 16) / 255.0,
            int(c[4:6], 16) / 255.0,
        )
    except ValueError:
        return (0.5, 0.5, 0.5)


def _clamp(value: float, low: float, high: float) -> float:
    """Constrain `value` to the ``[low, high]`` band."""
    if value < low:
        return low
    if value > high:
        return high
    return value


def _watch_color_scheme(widget: Gtk.Widget) -> None:
    """Repaint `widget` whenever the display's colour scheme changes."""
    display = Gdk.Display.get_default()
    if display is None:
        return
    try:
        style = Gtk.StyleContext.get_for_display(display)
    except Exception:
        return
    ref = weakref.ref(widget)

    def _on_scheme(*_args: object) -> None:
        target = ref()
        if target is not None:
            target.queue_draw()

    style.connect("notify::color-scheme", _on_scheme)


def _catmull_rom(cr: cairo.Context, points: list[tuple[float, float]],
                 top: float, bottom: float) -> None:
    """Trace `points` as a smooth Catmull-Rom spline of cubic Béziers.

    The spline passes exactly through every data point, so a marker drawn on a
    data point also lands on the curve. Control points are clamped to the
    chart band so the curve can never leave the widget, however sharp the
    series gets.
    """
    n = len(points)
    if n == 0:
        return
    cr.move_to(*points[0])
    if n == 1:
        return
    if n == 2:
        cr.line_to(*points[1])
        return
    for i in range(n - 1):
        p0 = points[i - 1] if i > 0 else points[0]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[i + 2] if i + 2 < n else points[n - 1]
        c1x = p1[0] + (p2[0] - p0[0]) / 6.0
        c1y = _clamp(p1[1] + (p2[1] - p0[1]) / 6.0, top, bottom)
        c2x = p2[0] - (p3[0] - p1[0]) / 6.0
        c2y = _clamp(p2[1] - (p3[1] - p1[1]) / 6.0, top, bottom)
        cr.curve_to(c1x, c1y, c2x, c2y, p2[0], p2[1])


# --- sparkline -------------------------------------------------------------

class Sparkline(Gtk.DrawingArea):
    """A smooth line chart with an optional "current position" marker.

    Reference component: the pale curve at the foot of the *Health &
    Longevity* target card — a hairline stroke in the `line` colour with a
    dotted vertical rule and a small dot marking where the user stands today.

    The series is normalised into the available height (its own min..max) and
    the curve is inset by `INSET` pixels so it never touches the edges.

    Args:
        values: the series, oldest first.
        marker: index into `values` to mark; `None` for no marker.
        height: requested height of the widget in pixels.
    """

    STROKE = 1.6          # curve width, in pixels
    INSET = 6.0           # vertical breathing room, in pixels
    MARKER_RADIUS = 3.0   # radius of the dot on the curve
    DASH = (2.0, 3.0)     # 2 px on / 3 px off, for the marker rule

    def __init__(self, values: list[float], marker: int | None = None,
                 height: int = 84):
        super().__init__()
        self._values = [float(v) for v in values]
        self._marker = marker
        self.set_size_request(-1, int(height))
        self.set_hexpand(True)
        self.set_accessible_role(Gtk.AccessibleRole.IMG)
        self.set_draw_func(self._draw)
        _LIVE.add(self)
        _watch_color_scheme(self)

    # -- data ---------------------------------------------------------------

    def set_values(self, values: list[float]) -> None:
        """Replace the series and repaint."""
        self._values = [float(v) for v in values]
        self.queue_draw()

    def set_marker(self, marker: int | None) -> None:
        """Move (or remove, with `None`) the current-position marker."""
        self._marker = marker
        self.queue_draw()

    def set_height(self, height: int) -> None:
        """Change the requested height of the widget."""
        self.set_size_request(-1, int(height))
        self.queue_draw()

    def get_values(self) -> list[float]:
        """The current series."""
        return list(self._values)

    def get_marker(self) -> int | None:
        """The current marker index, if any."""
        return self._marker

    # -- drawing ------------------------------------------------------------

    def _points(self, width: float, height: float) -> list[tuple[float, float]]:
        """Map the series onto widget pixels (x across the full width)."""
        vals = self._values
        n = len(vals)
        pad = self.STROKE / 2.0
        x0, x1 = pad, max(pad, width - pad)
        top, bottom = self.INSET, height - self.INSET
        mid = (top + bottom) / 2.0
        if n == 1:
            return [(x0, mid)]
        lo, hi = min(vals), max(vals)
        if hi <= lo:                       # flat series — draw it in the middle
            return [(x0 + (x1 - x0) * i / (n - 1), mid) for i in range(n)]
        span = bottom - top
        return [
            (x0 + (x1 - x0) * i / (n - 1),
             bottom - (v - lo) / (hi - lo) * span)
            for i, v in enumerate(vals)
        ]

    def _draw(self, area: Gtk.DrawingArea, cr: cairo.Context,
              width: int, height: int) -> None:
        palette = theme.scheme()
        if width <= 0 or height <= 0 or not self._values:
            return

        points = self._points(float(width), float(height))
        if len(points) == 1:               # a lone value reads as a flat line
            points = [points[0], (float(width) - self.STROKE / 2.0, points[0][1])]

        marker_at: tuple[float, float] | None = None
        if self._marker is not None and 0 <= self._marker < len(self._values):
            marker_at = points[self._marker]

        # the dotted rule goes down first, so the curve sits on top of it
        if marker_at is not None:
            r, g, b = _rgb(palette.text_dim)
            cr.set_source_rgba(r, g, b, 0.9)
            cr.set_line_width(1.0)
            cr.set_dash(list(self.DASH), 0.0)
            cr.move_to(marker_at[0], 0.0)
            cr.line_to(marker_at[0], float(height))
            cr.stroke()
            cr.set_dash([], 0.0)

        # the curve
        r, g, b = _rgb(palette.line)
        cr.set_source_rgba(r, g, b, 1.0)
        cr.set_line_width(self.STROKE)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.new_path()
        _catmull_rom(cr, points, self.INSET, float(height) - self.INSET)
        cr.stroke()

        # the dot on the curve
        if marker_at is not None:
            r, g, b = _rgb(palette.text_dim)
            cr.set_source_rgba(r, g, b, 1.0)
            cr.new_path()
            cr.arc(marker_at[0], marker_at[1], self.MARKER_RADIUS,
                   0.0, 2 * math.pi)
            cr.fill()


# --- bar chart -------------------------------------------------------------

class BarChart(Gtk.DrawingArea):
    """A dense vertical bar chart with one highlighted region.

    Reference component: the chart at the foot of the *Financial Freedom*
    target card — a picket of hairline bars in the `bar` colour, with one
    contiguous run drawn at full opacity to show the active period.

    Bars are 1 px wide with a 1 px gap, so a 400 px wide chart carries
    roughly 200 bars. The bar count follows the length of the series when
    one is given and falls back to the widget width otherwise; pass one value
    per 2 px of width for the dense reference look.

    Args:
        values: the series, oldest first.
        highlight: inclusive ``(start, end)`` index range drawn at full
            opacity; `None` for no highlight.
        height: requested height of the widget in pixels.
    """

    BAR_WIDTH = 1.0     # bar width, in pixels
    GAP = 1.0           # gap between bars, in pixels
    BASELINE = 2.0      # space left under the bars, in pixels
    ALPHA = 0.55        # opacity of the un-highlighted bars

    def __init__(self, values: list[float],
                 highlight: tuple[int, int] | None = None, height: int = 84):
        super().__init__()
        self._values = [float(v) for v in values]
        self._highlight = tuple(highlight) if highlight is not None else None
        self.set_size_request(-1, int(height))
        self.set_hexpand(True)
        self.set_accessible_role(Gtk.AccessibleRole.IMG)
        self.set_draw_func(self._draw)
        _LIVE.add(self)
        _watch_color_scheme(self)

    # -- data ---------------------------------------------------------------

    def set_values(self, values: list[float]) -> None:
        """Replace the series and repaint."""
        self._values = [float(v) for v in values]
        self.queue_draw()

    def set_highlight(self, highlight: tuple[int, int] | None) -> None:
        """Move (or remove, with `None`) the highlighted index range."""
        self._highlight = tuple(highlight) if highlight is not None else None
        self.queue_draw()

    def set_height(self, height: int) -> None:
        """Change the requested height of the widget."""
        self.set_size_request(-1, int(height))
        self.queue_draw()

    def get_values(self) -> list[float]:
        """The current series."""
        return list(self._values)

    def get_highlight(self) -> tuple[int, int] | None:
        """The current highlighted index range, if any."""
        return self._highlight

    # -- drawing ------------------------------------------------------------

    def _span(self) -> tuple[int, int]:
        """The inclusive index range drawn at full opacity (empty if none)."""
        if self._highlight is None:
            return (1, 0)
        start, end = self._highlight
        if start > end:
            start, end = end, start
        return (max(0, int(start)), min(len(self._values) - 1, int(end)))

    def _draw(self, area: Gtk.DrawingArea, cr: cairo.Context,
              width: int, height: int) -> None:
        palette = theme.scheme()
        if width <= 0 or height <= 0:
            return

        pitch = self.BAR_WIDTH + self.GAP
        count = len(self._values) or max(1, int(width // pitch))
        step = float(width) / count
        bar_w = min(self.BAR_WIDTH, step * 0.55)

        baseline = float(height) - self.BASELINE
        avail = max(0.0, baseline)
        top = max(self._values) if self._values else 0.0
        r, g, b = _rgb(palette.bar)
        lo, hi = self._span()

        for i, value in enumerate(self._values):
            frac = (value / top) if top > 0 else 0.0
            frac = _clamp(frac, 0.0, 1.0)
            bar_h = frac * avail
            if value > 0 and bar_h < 1.0:
                bar_h = 1.0
            if bar_h <= 0:
                continue
            alpha = 1.0 if lo <= i <= hi else self.ALPHA
            # snap to the pixel grid so every hairline keeps the same weight
            x = float(round(i * step)) if step >= 1.0 else i * step
            cr.set_source_rgba(r, g, b, alpha)
            cr.rectangle(x, baseline - bar_h, bar_w, bar_h)
            cr.fill()
