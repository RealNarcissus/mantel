# Design

The shell follows **@UiRahMan92's "Hearth" concept dashboard**
([x.com/UiRahMan92](https://x.com/UiRahMan92)) — a light, monospaced,
card-based layout. The tribute is deliberate: the grid, the rhythm and the
muted palette are the point, and every number below is a measurement taken from
that design rather than an estimate.

All values are in the application's own coordinate space, **1744 × 1168**.

> This client ships no third-party fonts or glyphs. If you supply your own
> copies of the fonts (see `assets/README.md`) the wordmark and body type match
> the reference exactly; otherwise the shell falls back to generic
> `sans-serif` / `monospace` and stock symbolic icons, and still lays out
> identically.

## Layout

| Element | Value |
|---|---|
| Sidebar width | **304 px** (border at x = 302–303) |
| Content origin | x = 304 |
| Content left padding | 36 px (cards start at x = 340) |
| Content right padding | 36 px (cards end at x = 1700) |
| Top bar height | 100 px (hero card starts at y = 105) |
| Hero card | x 340–1700, y 105–376, radius 20, fill `#F6F6F6` |
| Tab row | y 400–460 |
| Section header ("Active Targets") | ink y 478–500 |
| Target cards | y 522–765, fill `#F3F5F5`, radius 18 |
| Vision card row | y 828–1140 |
| Right column | x 1265–1700 (width 435) |
| Left column | x 340–1230 (width 890) |
| Column gap | 35 px |
| Target cards | 2 across, 430 px each, 20 px gap |
| Vision cards | 3 across, 277 px each, 18 px gap |

## Palette (light)

Sampled with a per-region histogram rather than a single pixel, so anti-aliased
text does not skew the result.

| Token | Value | Where |
|---|---|---|
| page | `#FBFBFB` | content background |
| sidebar | `#F2F2F2` | navigation rail |
| surface | `#FBFBFB` | pillars panel, quick-stat card, vision card |
| surface_alt | `#F3F5F5` | target cards, icon buttons, inset |
| field | `#E6E6E6` | search field, user card, segmented control |
| chip | `#F3F3F3` | top-bar chip, bell, filter button |
| border | `#EFEFEF` / `#F1F1F1` | card outlines |
| hairline | `#F6F6F6` | row separators |
| text | `#0B0B0B` | headings, body |
| text_mid | `#6D6D6D` | subtitles, nav items |
| text_dim | `#B9B9B9` | section labels, placeholder |
| pill | `#0B0B0B` on `#FFFFFF` | active nav item, primary button |
| accent | `#4E72C4` | "WELCOME BACK" eyebrow (core pixels `#4E72C4`–`#79A5FF`) |
| line | `#BFC1C1` | sparkline stroke |
| bar | `#A0A3AC` | bar-chart stroke (slightly blue-grey) |
| icon muted | `#8A8A8A` | navigation icons |

The dark palette in `app/theme.py` is derived from these, not sampled from the
reference (which is light-only).

## Type

Two families, mixed by role:

- **Monospace** for essentially all content — headings, body, labels, nav.
  Square `i` dot, `f` with a wide crossbar, wide flat `L` foot, double-storey
  `a`, `G` with a bar and spur. Measured ink heights (cap height → size):

  | Text | ink h | ink w | ≈ size |
  |---|---|---|---|
  | `Life Goals` | 27 | 200 | 37–38 px |
  | `Health & Longevity` | 16 | 197 | 22 px |
  | `PHYSICAL PILLAR` | 10 | 122 | 14 px |
  | `Build My Dream Career` | 13 | 201 | 15 px |
  | `Plan my vacation` | 11 | 136 | 14 px |

  The reference face is proprietary and cannot be redistributed, so
  **JetBrains Mono** (SIL OFL 1.1) is the intended substitute — the closest
  available match for the square `i` dot and technical tone. Supply it in
  `assets/fonts/`; otherwise Pango falls back to the system monospace.

- **Sans** for the wordmark only. The reference pairs the mark with a humanist
  sans; the client uses Google Sans when the font is present.

The uppercase eyebrow (`WELCOME BACK`) is monospace, 12 px, letter-spaced
≈ 1.6 px, accent blue.

## Components

**Sidebar** (304 px, fill `#F2F2F2`)

1. Brand row, 20 px inset: 44 px black rounded square (radius 12) with a white
   asterisk, wordmark + subtitle, and a collapse button on the right
   (transparent, 1 px border, radius 8).
2. Search field, full width minus 20 px inset: fill `#E6E6E6`, radius 12,
   height 40, magnifier icon, placeholder "Search …", `⌘K` chip on the right.
3. `Main` section label (13 px, `#B9B9B9`).
4. Nav rows, height 38, radius 12, icon 20 px + label 15 px; the active row is a
   `#0B0B0B` pill with white text. Trailing badge on some rows (radius 999,
   fill `#E6E6E6`).
5. Divider.
6. `Today` section header with a chevron on the right, then a list of rows
   indented behind a 1 px vertical rule.
7. Divider.
8. `Setting` / `Help Center` section headers with chevrons.
9. User card: fill `#E6E6E6`, radius 14, avatar, name, e-mail, chevron.
10. Theme toggle: fill `#E6E6E6`, radius 10, three segments
    (Light / Dark / System); the active one is a black pill.

**Top bar** (100 px)

- Left: breadcrumb chip — fill `#F3F3F3`, radius 12, chevron-left + label.
- Right: bell icon button (fill `#F3F3F3`, radius 12), a black pill button
  "New" with an edit-in-square icon, and a sliders/filter icon button.

**Hero card** — fill `#F6F6F6`, radius 20, 271 px tall. Left: eyebrow, 40 px
title, 17 px subtitle, then two buttons (black primary with a `+`, outlined
secondary). Right: a full-bleed illustration clipped by the card's rounded
corner.

**Tab row** — segmented control: fill `#F3F3F3`, radius 14, 4 px padding, inner
white pill (radius 11) for the active tab. On the far right a bordered button
with a calendar icon, a quarter label and a chevron.

**Active Targets** card — 17 px title, 12 px uppercase eyebrow, a 36 px
`icon-square` button top-right, a 44 px metric, 13 px sub-label, and a chart at
the bottom. Two variants: a smooth sparkline with a dotted vertical marker, and
a dense bar chart where one region is highlighted.

**Vision Board** card — image placeholder area (fill `#F2F2F2`, radius 12) with
a 32 px `icon-square` button overlapping its top-left corner; bold title;
three-line description; footer row with a small circled icon, a status and a
date.

**Pillars panel** — one card, rows separated by hairlines. Each row: a 36 px
`icon-square` icon, a bold name, a muted sub-label, and a grade chip (`A+`,
`B+`, `A-`) on the right.

**Quick Stats** — 2 × 2 grid of small cards; each has a 36 px `icon-square`, a
26 px number and a 13 px label.

## Verifying the layout

Render offscreen at the reference size and read the image:

```bash
python3 -m app.main --smoke out.png --size 1744x1168 --page home
```

`tests/harness.py` is the reusable version of this: it builds a widget tree,
renders it through a `Gsk.Renderer` with `GSK_RENDERER=cairo`, and writes a PNG.
That is how every screen in `docs/screenshots/` was produced — there is no
compositor and no GPU in the verification loop.

## How close it lands

| Measurement | Reference | This client |
|---|---|---|
| Sidebar width | 304 | 304 |
| Content left margin | 340 | 340 |
| Content right edge | 1699 | 1707 |
| Nav row pitch | 48 | 48 |
| Nav text ink | x 55, w 72 | x 56, w 71 |
| Nav text baseline | y 312 | y 313 |
| Task row pitch | 32 | 32 |
| Top bar height | 100 | 100 |
| Hero card height | 271 | 271 |
| Sidebar background | `#F2F2F2` | `#F2F2F2` |
| Target card fill | `#F3F5F5` | `#F3F5F5` |
| Nav pill | `#0B0B0B` | `#0B0B0B` |
| Accent (eyebrow) | `#4E72C4` | `#4E72C4` |

Differences that remain, stated plainly:

- Type: JetBrains Mono stands in for the reference's proprietary condensed
  mono. The advance matches within 1 %; ascenders are ~1 px shorter.
- The hero artwork is drawn procedurally (from shaders recovered out of the
  original app), not the reference's painting. Composition and palette follow
  the reference; the shapes do not.
- The reference's placeholder cards carry illustrations; these use flat
  placeholders.
- The reference is a different product, so the **content** of every panel is
  Gemini's, laid out on the reference's grid.
