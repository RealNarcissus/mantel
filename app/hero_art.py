"""The greeting card's artwork.

The reference application fills the right of its greeting card with a
painterly mountain landscape: a teal sky with cream cloud banks, a blue-grey
range with warm sunlit faces, green slopes, dark forest and a figure in the
foreground looking up at the peaks.

It is drawn here with Cairo rather than shipped as a bitmap, so it scales
cleanly, adapts to the card's size, and follows the colour scheme. The
composition is authored in a fixed 700 x 452 virtual space and scaled to fit.
"""
from __future__ import annotations

import math
import random

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

# Virtual authoring space.
VW, VH = 700.0, 452.0

# Palette sampled from the reference illustration.
SKY_TOP = (0.93, 0.96, 0.95)
SKY_MID = (0.42, 0.73, 0.81)
SKY_LOW = (0.62, 0.85, 0.80)
CLOUD = (0.95, 0.93, 0.85)
PEAK_FAR = (0.56, 0.66, 0.75)
PEAK_MID = (0.36, 0.48, 0.60)
PEAK_LIT = (0.85, 0.75, 0.54)
SLOPE_1 = (0.50, 0.69, 0.41)
SLOPE_2 = (0.35, 0.60, 0.35)
SLOPE_3 = (0.25, 0.48, 0.34)
FOREST = (0.11, 0.23, 0.26)
FIGURE = (0.09, 0.15, 0.18)


def _ramp(c0, c1, t: float) -> tuple[float, float, float]:
    return tuple(a + (b - a) * t for a, b in zip(c0, c1))


class HeroArt(Gtk.DrawingArea):
    """The landscape panel."""

    def __init__(self, corner_radius: float = 20.0,
                 fade_colour: tuple[float, float, float] | None = None,
                 dim: float = 0.0) -> None:
        super().__init__()
        self.corner_radius = corner_radius
        self.fade_colour = fade_colour
        self.dim = dim
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    @staticmethod
    def _poly(cr, pts) -> None:
        cr.move_to(*pts[0])
        for p in pts[1:]:
            cr.line_to(*p)
        cr.close_path()

    def _draw(self, _area, ctx, width, height) -> bool:
        cr = ctx
        if width <= 1 or height <= 1:
            return False
        scale = min(width / VW, height / VH)
        if scale <= 0:
            return False
        ox = (width - VW * scale) / 2
        oy = (height - VH * scale) / 2
        cr.save()
        cr.translate(ox, oy)
        cr.scale(scale, scale)
        if self.corner_radius > 0:
            r = self.corner_radius / max(scale, 0.001)
            cr.move_to(0, 0)
            cr.line_to(VW - r, 0)
            cr.arc(VW - r, r, r, -math.pi / 2, 0)
            cr.line_to(VW, VH - r)
            cr.arc(VW - r, VH - r, r, 0, math.pi / 2)
            cr.line_to(0, VH)
            cr.close_path()
        else:
            cr.rectangle(0, 0, VW, VH)
        cr.clip()

        rng = random.Random(20261021)
        self._sky(cr)
        self._sun(cr)
        self._clouds(cr, rng)
        self._birds(cr, rng)
        self._far_range(cr, rng)
        self._mid_range(cr, rng)
        self._hills(cr, rng)
        self._forest(cr, rng)
        self._figure(cr)
        self._foreground(cr)
        if self.dim > 0:
            cr.set_source_rgba(0, 0, 0, self.dim)
            cr.rectangle(0, 0, VW, VH)
            cr.fill()
        self._fade(cr)
        cr.restore()
        return False

    def _fade(self, cr) -> None:
        """Soften the left edge so the art blends into the card."""
        if not self.fade_colour:
            return
        grad = cairo.LinearGradient(0, 0, 150, 0)
        grad.add_color_stop_rgba(0.0, *self.fade_colour, 1.0)
        grad.add_color_stop_rgba(0.55, *self.fade_colour, 0.55)
        grad.add_color_stop_rgba(1.0, *self.fade_colour, 0.0)
        cr.set_source(grad)
        cr.rectangle(0, 0, 150, VH)
        cr.fill()

    def _sky(self, cr) -> None:
        grad = cairo.LinearGradient(0, 0, VW * 0.30, VH * 0.70)
        grad.add_color_stop_rgba(0.00, *SKY_TOP, 1.0)
        grad.add_color_stop_rgba(0.26, *SKY_MID, 1.0)
        grad.add_color_stop_rgba(0.62, *SKY_LOW, 1.0)
        grad.add_color_stop_rgba(0.82, 0.55, 0.86, 0.70, 1.0)
        grad.add_color_stop_rgba(1.00, 0.74, 0.89, 0.78, 1.0)
        cr.set_source(grad)
        cr.rectangle(0, 0, VW, VH)
        cr.fill()

    def _sun(self, cr) -> None:
        cr.save()
        grad = cairo.RadialGradient(36, 26, 2, 36, 26, 150)
        grad.add_color_stop_rgba(0.00, 1.00, 0.99, 0.92, 0.70)
        grad.add_color_stop_rgba(0.40, 0.97, 0.99, 0.95, 0.16)
        grad.add_color_stop_rgba(1.00, 0.95, 0.99, 0.95, 0.00)
        cr.set_source(grad)
        cr.arc(36, 26, 150, 0, 2 * math.pi)
        cr.fill()
        cr.restore()

    def _clouds(self, cr, rng) -> None:
        """Soft cloud banks: a diffuse halo, then a brighter core."""
        banks = [
            (168, 92, 150, 34, 8),
            (300, 66, 96, 22, 6),
            (470, 46, 170, 32, 9),
            (598, 96, 120, 26, 7),
            (96, 152, 104, 22, 6),
        ]
        for cx, cy, w, h, puffs in banks:
            blobs = []
            for i in range(puffs):
                t = i / max(1, puffs - 1)
                px = cx + (t - 0.5) * w
                py = cy + rng.uniform(-h * 0.30, h * 0.30)
                rx = w / puffs * rng.uniform(0.75, 1.35)
                ry = h * rng.uniform(0.55, 0.95)
                blobs.append((px, py, rx, ry))
            for alpha, grow, colour in ((0.22, 1.45, CLOUD),
                                        (0.45, 1.15, CLOUD),
                                        (0.88, 0.95, (0.99, 0.98, 0.93))):
                cr.set_source_rgba(*colour, alpha)
                for px, py, rx, ry in blobs:
                    cr.save()
                    cr.translate(px, py)
                    # clouds are wide and flat, not round
                    cr.scale(1.0, (ry * grow) / (rx * grow) * 0.62)
                    cr.arc(0, 0, rx * grow, 0, 2 * math.pi)
                    cr.fill()
                    cr.restore()

    def _birds(self, cr, rng) -> None:
        cr.set_source_rgba(0.16, 0.27, 0.32, 0.45)
        cr.set_line_width(1.4)
        cr.set_line_cap(1)
        for bx, by, s in ((96, 40, 1.0), (130, 60, 0.85), (172, 30, 0.7),
                          (246, 86, 0.6), (306, 22, 0.5)):
            cr.save()
            cr.translate(bx, by)
            cr.scale(s, s)
            cr.move_to(-6, 0)
            cr.curve_to(-4, -3, -2, -3, 0, -1)
            cr.curve_to(2, -3, 4, -3, 6, 0)
            cr.stroke()
            cr.restore()

    def _range(self, cr, rng, base, peaks, height, colour, lit=None,
               haze=None) -> None:
        """A mountain range, optionally with sunlit faces on the peaks."""
        pts = [(0.0, base)]
        step = VW / peaks
        for i in range(peaks):
            x = step * (i + 0.5)
            h = height * rng.uniform(0.55, 1.0)
            if i % 2:
                h *= 0.62
            pts.append((x, base - h))
            # the left flank is short and steep, the right one long and low
            pts.append((x + step * rng.uniform(0.10, 0.22),
                        base - h * rng.uniform(0.30, 0.52)))
            pts.append((x + step * rng.uniform(0.45, 0.80),
                        base - h * rng.uniform(0.10, 0.26)))
        pts.append((VW, base))

        if haze is not None:
            cr.set_source_rgba(*haze, 0.55)
            self._poly(cr, pts)
            cr.fill()

        cr.set_source_rgba(*colour, 1.0)
        self._poly(cr, pts)
        cr.fill()

        if lit is not None:
            for i in range(1, len(pts) - 1):
                x, y = pts[i]
                if y > base - height * 0.35:
                    continue
                nx, ny = pts[i + 1] if i + 1 < len(pts) else (x, base)
                cr.set_source_rgba(*lit, 0.92)
                cr.move_to(x, y)
                cr.line_to(x - 5, y + (base - y) * 0.5)
                cr.line_to(x + (nx - x) * 0.85, ny)
                cr.close_path()
                cr.fill()

    def _far_range(self, cr, rng) -> None:
        self._range(cr, rng, 318, 6, 205, PEAK_FAR, haze=(0.85, 0.92, 0.93))

    def _mid_range(self, cr, rng) -> None:
        self._range(cr, rng, 352, 4, 250, PEAK_MID, lit=PEAK_LIT)

    def _hills(self, cr, rng) -> None:
        """Rolling green slopes with a lit facet on each rise."""
        for base, col, amp, phase in (
            (296, SLOPE_1, 40, 0.0),
            (346, SLOPE_2, 32, 1.9),
            (392, SLOPE_3, 24, 3.4),
        ):
            pts = []
            x = 0.0
            while x <= VW:
                y = (base - amp * (0.5 + 0.5 * math.sin(x * 0.0105 + phase))
                     - rng.uniform(0, 6))
                pts.append((x, y))
                x += 12
            poly = [(0, VH)] + pts + [(VW, VH)]
            cr.set_source_rgba(*col, 1.0)
            self._poly(cr, poly)
            cr.fill()

            cr.set_source_rgba(*_ramp(col, (0.92, 0.97, 0.80), 0.28), 0.5)
            facet = [pts[i] for i in range(len(pts) - 1)
                     if pts[i][1] < pts[i + 1][1]]
            if len(facet) > 2:
                self._poly(cr, facet + [(facet[-1][0], VH), (facet[0][0], VH)])
                cr.fill()

    def _forest(self, cr, rng) -> None:
        for _ in range(60):
            tx = 400 + rng.random() * 320
            ty = 336 + rng.random() * 54
            h = 12 + rng.random() * 22
            w = h * 0.40
            cr.set_source_rgba(*FOREST, 0.55 + rng.random() * 0.4)
            cr.move_to(tx, ty - h)
            cr.line_to(tx + w, ty)
            cr.line_to(tx - w, ty)
            cr.close_path()
            cr.fill()

    def _figure(self, cr) -> None:
        """The person in the foreground, looking up at the range."""
        cr.set_source_rgba(*FIGURE, 1.0)
        cx = 300.0
        base = VH + 6
        cr.move_to(cx - 78, base)
        cr.curve_to(cx - 76, base - 118, cx - 42, base - 146, cx, base - 148)
        cr.curve_to(cx + 42, base - 146, cx + 76, base - 118, cx + 78, base)
        cr.close_path()
        cr.fill()
        cr.arc(cx, base - 178, 33, 0, 2 * math.pi)
        cr.fill()
        cr.arc(cx - 5, base - 188, 32, math.pi * 0.82, math.pi * 2.12)
        cr.fill()

    def _foreground(self, cr) -> None:
        cr.set_source_rgba(*_ramp(FOREST, (0.20, 0.42, 0.30), 0.55), 1.0)
        pts = [(0, VH), (0, 412)]
        x = 0.0
        while x <= VW:
            pts.append((x, 412 + 14 * math.sin(x * 0.013)))
            x += 16
        pts.append((VW, 412))
        pts.append((VW, VH))
        self._poly(cr, pts)
        cr.fill()
