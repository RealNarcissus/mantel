"""Design system for the Linux client.

The visual language is a light, monospaced, card-based dashboard shell, in the
style of the "Hearth" concept dashboard by @UiRahMan92
(https://x.com/UiRahMan92) — the design this client was styled after. Every
token below is a measurement from that reference rather than a guess; see
`docs/DESIGN.md` for the geometry, palette and type metrics.

Structure
    tokens      light + dark palettes, both derived from the reference
    css         the stylesheet, generated from the active palette
    icons       pre-rendered glyphs, addressed by tone
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app import fonts_env  # noqa: F401  (sets FONTCONFIG_FILE before Pango)

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

ASSETS = fonts_env.ROOT / "assets"
ICON_DIR = ASSETS / "icons_rendered"

#: True when the font set extracted from the original application is present.
BUNDLED_FONTS = fonts_env.FONTS_DIR.is_dir() and any(
    fonts_env.FONTS_DIR.glob("*.ttf"))

#: Family names fall back to generics so a checkout without the extracted
#: assets still renders sensibly.
FONT_MONO = "JetBrains Mono NF" if BUNDLED_FONTS else "monospace"
FONT_BRAND = "Google Sans Flex" if BUNDLED_FONTS else "sans-serif"

# --- palette ---------------------------------------------------------------


@dataclass(frozen=True)
class Palette:
    name: str
    page: str          # main content background
    sidebar: str       # navigation rail
    surface: str       # cards (pillars panel, quick stat, vision card)
    surface_alt: str   # inset cards + icon buttons
    field: str         # search field, user card, segmented control
    chip: str          # top bar chips and icon buttons
    border: str        # card outlines
    border_soft: str
    hairline: str      # row separators inside cards
    text: str
    text_mid: str
    text_dim: str
    text_faint: str
    pill_bg: str       # active nav pill / primary button
    pill_fg: str
    accent: str        # eyebrow blue
    line: str          # sparkline stroke
    bar: str           # bar chart stroke
    icon_muted: str    # default icon tone on this scheme
    on_accent: str     # icon colour that sits on an accent/light pill
    hero: str          # the greeting card fill


LIGHT = Palette(
    name="light",
    page="#FBFBFB",
    sidebar="#F2F2F2",
    surface="#FBFBFB",
    surface_alt="#F3F5F5",
    field="#E6E6E6",
    chip="#F3F3F3",
    border="#EFEFEF",
    border_soft="#F1F1F1",
    hairline="#F6F6F6",
    text="#0B0B0B",
    text_mid="#6D6D6D",
    text_dim="#B9B9B9",
    text_faint="#DCDCDC",
    pill_bg="#0B0B0B",
    pill_fg="#FFFFFF",
    accent="#4E72C4",
    line="#BFC1C1",
    bar="#A0A3AC",
    icon_muted="gray",
    on_accent="dark",
    hero="#F6F6F6",
)

DARK = Palette(
    name="dark",
    page="#0E0E0E",
    sidebar="#141414",
    surface="#171717",
    surface_alt="#1E1E1E",
    field="#232323",
    chip="#1C1C1C",
    border="#262626",
    border_soft="#202020",
    hairline="#212121",
    text="#EDEDED",
    text_mid="#9A9A9A",
    text_dim="#636363",
    text_faint="#383838",
    pill_bg="#EDEDED",
    pill_fg="#111111",
    accent="#8FB0FF",
    line="#4C4E50",
    bar="#6E717A",
    icon_muted="graydark",
    on_accent="dark",
    hero="#1A1A1A",
)

PALETTES = {"light": LIGHT, "dark": DARK}

_active: Palette = LIGHT


# --- stylesheet ------------------------------------------------------------

def _css(p: Palette) -> str:
    return f"""
@define-color g-page {p.page};
@define-color g-sidebar {p.sidebar};
@define-color g-surface {p.surface};
@define-color g-surface_alt {p.surface_alt};
@define-color g-field {p.field};
@define-color g-chip {p.chip};
@define-color g-border {p.border};
@define-color g-border_soft {p.border_soft};
@define-color g-hairline {p.hairline};
@define-color g-text {p.text};
@define-color g-text_mid {p.text_mid};
@define-color g-text_dim {p.text_dim};
@define-color g-text_faint {p.text_faint};
@define-color g-pill_bg {p.pill_bg};
@define-color g-pill_fg {p.pill_fg};
@define-color g-accent {p.accent};
@define-color g-line {p.line};
@define-color g-bar {p.bar};
@define-color g-hero {p.hero};

window, .root {{ background: @g-page; color: @g-text; font-family: "{FONT_MONO}"; }}
view, viewport {{ background: transparent; }}

/* ============ sidebar ============ */
.sidebar {{ background: @g-sidebar; border-right: 1px solid @g-border_soft; }}
.brand-mark {{
  background: @g-pill_bg; border-radius: 12px; min-width: 46px; min-height: 46px;
}}
.brand-name {{
  font-family: "{FONT_BRAND}"; font-size: 20px; font-weight: 600; color: @g-text;
}}
.brand-sub {{
  font-family: "{FONT_BRAND}"; font-size: 12px; color: @g-text_mid;
}}
.brand-collapse {{  background-image: none;
  background: transparent; border: 1px solid @g-border; border-radius: 8px;
  padding: 5px; color: @g-text_dim;
}}
.brand-collapse:hover {{ background: @g-field; color: @g-text; }}

.search-field {{
  background: @g-field; border: none; border-radius: 12px; padding: 0 14px;
  min-height: 46px; color: @g-text;
}}
.search-field:focus {{ outline: none; box-shadow: none; }}
.search-entry {{
  background: transparent; color: @g-text; font-size: 14px; caret-color: @g-text;
}}
.search-entry:focus {{ outline: none; }}
.kbd {{
  background: @g-page; border: 1px solid @g-border; border-radius: 6px;
  padding: 1px 6px; font-size: 11px; color: @g-text_dim;
}}

.nav-label {{ font-size: 13px; color: @g-text_dim; padding: 0 12px; }}
.nav-item {{  background-image: none;
  background: transparent; border: none; border-radius: 12px;
  padding: 0 14px 0 0; color: @g-text_mid; font-size: 15.5px;
  min-height: 46px; margin-left: 20px; margin-right: 18px;
  margin-bottom: 6px;
}}
.nav-item:hover {{ background: @g-field; color: @g-text; }}
.nav-item.active {{ background: @g-pill_bg; color: @g-pill_fg; }}
.nav-item.active:hover {{ background: @g-pill_bg; color: @g-pill_fg; }}
.nav-item .badge {{
  background: @g-field; border-radius: 999px; padding: 1px 8px;
  font-size: 12px; color: @g-text_mid;
}}
.nav-item.active .badge {{ background: rgba(255,255,255,.16); color: @g-pill_fg; }}

.section-head {{  background-image: none;
  background: transparent; border: none; padding: 0 12px;
  color: @g-text_dim; font-size: 16px; min-height: 24px;
}}
.section-head:hover {{ color: @g-text; }}
.task-row {{  background-image: none;
  background: transparent; border: none; border-radius: 10px;
  padding: 0; color: @g-text_mid; font-size: 13px;
  min-height: 32px;
}}
.task-row:hover {{ background: @g-field; color: @g-text; }}
.task-list {{ padding-left: 16px; border-left: 1px solid @g-border; }}

.user-card {{  background-image: none;
  background: @g-field; border: none; border-radius: 14px; padding: 10px 12px;
}}
.user-name {{ font-size: 14px; color: @g-text; }}
.user-mail {{ font-size: 12px; color: @g-text_mid; }}

.theme-toggle {{  background-image: none;
 background: @g-field; border-radius: 10px; padding: 3px; }}
.theme-toggle button {{
  background: transparent; background-image: none; border: none; border-radius: 8px;
  padding: 6px 10px; color: @g-text_mid; font-size: 12.5px;
}}
.theme-toggle button:hover {{ color: @g-text; }}
.theme-toggle button.active {{ background: @g-pill_bg; color: @g-pill_fg; }}

/* ============ top bar ============ */
.topbar {{ background: @g-page; }}
.crumb {{  background-image: none;
  background: @g-chip; border: none; border-radius: 12px;
  padding: 9px 16px; color: @g-text_mid; font-size: 15px;
}}
.crumb:hover {{ color: @g-text; }}
.icon-btn {{
  background: @g-chip; border: none; border-radius: 12px; padding: 10px;
  color: @g-text;
}}
.icon-btn:hover {{ background: @g-field; }}
.icon-btn.ghost {{ background: transparent; }}
.icon-btn.ghost:hover {{ background: @g-chip; }}
.btn-primary {{
  background: @g-pill_bg; color: @g-pill_fg; border: none; border-radius: 12px;
  padding: 10px 16px; font-size: 15px; font-weight: 500;
}}
.btn-primary:hover {{ opacity: .88; }}
.btn-secondary {{
  background: @g-surface; color: @g-text; border: 1px solid @g-border;
  border-radius: 12px; padding: 10px 16px; font-size: 15px;
}}
.btn-secondary:hover {{ background: @g-chip; }}

/* ============ content ============ */
.content {{ background: @g-page; }}

.hero {{
  background: @g-hero; border: 1px solid @g-border;
  border-radius: 20px;
}}
.hero-eyebrow {{
  font-size: 12px; color: @g-accent; letter-spacing: 1.6px; font-weight: 600;
}}
.hero-title {{ font-size: 40px; font-weight: 600; color: @g-text; }}
.hero-sub {{ font-size: 17px; color: @g-text_mid; }}
.hero-art {{ background: @g-hero; }}

/* tabs */
.segmented {{
  background: @g-chip; border-radius: 14px; padding: 4px;
}}
.segmented button {{
  background: transparent; border: none; border-radius: 11px;
  padding: 9px 20px; color: @g-text_mid; font-size: 15px;
}}
.segmented button:hover {{ color: @g-text; }}
.segmented button.active {{
  background: @g-surface; color: @g-text; box-shadow: 0 1px 2px rgba(0,0,0,.06);
}}

/* section headings */
.section-title {{ font-size: 19px; font-weight: 600; color: @g-text; }}

/* cards */
.card {{
  background: @g-surface; border: 1px solid @g-border; border-radius: 18px;
}}
.card.inset {{ background: @g-surface_alt; }}
.card-title {{ font-size: 17px; font-weight: 600; color: @g-text; }}
.card-title-13 {{ font-size: 13px; }}
.card-title-15 {{ font-size: 15px; }}
.card-title-19 {{ font-size: 19px; }}
.card-title-24 {{ font-size: 24px; }}
.card-eyebrow {{
  font-size: 12px; color: @g-text_mid; letter-spacing: .8px;
}}
.card-body {{ font-size: 14px; color: @g-text_mid; }}
.metric {{ font-size: 44px; font-weight: 600; color: @g-text; }}
.metric-sub {{ font-size: 13px; color: @g-text_mid; }}

.icon-square {{  background-image: none;
  background: @g-surface_alt; border: none; border-radius: 12px; padding: 9px;
}}
.icon-square:hover {{ background: @g-field; }}
.icon-square.on-dark {{ background: rgba(255,255,255,.14); }}

.chip-grade {{  background-image: none;
  background: @g-field; border: none; border-radius: 8px;
  padding: 4px 9px; font-size: 12.5px; color: @g-text_mid;
}}

.divider {{ background: @g-hairline; min-height: 1px; }}

/* quick stat */
.stat-num {{ font-size: 26px; font-weight: 600; color: @g-text; }}
.stat-label {{ font-size: 13px; color: @g-text_mid; }}

/* ============ chat ============ */
.transcript, .transcript viewport {{ background: @g-page; }}
.msg-user {{
  background: @g-surface_alt; border-radius: 18px; padding: 13px 18px;
  font-size: 15px; color: @g-text;
}}
.msg-ai label {{ font-size: 15px; color: @g-text; }}
label.md-h1 {{ font-size: 24px; font-weight: 600; }}
label.md-h2 {{ font-size: 19px; font-weight: 600; }}
label.md-h3 {{ font-size: 16px; font-weight: 600; }}
.md-code {{ background: @g-surface_alt; border-radius: 6px; font-size: 13.5px; }}
.md-pre {{
  background: @g-surface_alt; border: 1px solid @g-border; border-radius: 14px;
  padding: 14px 16px; font-size: 13.5px;
}}
.md-quote {{ color: @g-text_mid; border-left: 2px solid @g-border; padding-left: 14px; }}
.md-image {{ border-radius: 12px; }}
.thought {{ color: @g-text_mid; font-size: 13.5px; }}
.tool-block {{
  background: @g-surface_alt; border: 1px solid @g-border; border-radius: 14px;
  padding: 11px 14px;
}}
.tool-name {{ font-size: 13.5px; color: @g-text; }}
.tool-detail {{ font-size: 12.5px; color: @g-text_mid; }}
.error-box {{
  background: #2B1A1A; border: 1px solid #5C2B2B; border-radius: 12px;
  padding: 11px 15px; color: #F2B8B5; font-size: 13.5px;
}}

/* composer */
.composer-shell {{
  background: @g-surface_alt; border: 1px solid @g-border; border-radius: 20px;
}}
.mode-switch {{
  background: @g-field; border-radius: 999px; padding: 2px;
}}
.mode-switch button {{
  background: transparent; border: none; border-radius: 999px;
  padding: 5px 12px; color: @g-text_mid; font-size: 12.5px;
}}
.mode-switch button:hover {{ color: @g-text; }}
.mode-switch button:checked {{
  background: @g-pill_bg; color: @g-pill_fg;
}}

/* ---- approval cards ---- */
.approval-card {{
  background: @g-surface; border: 1px solid @g-border; border-radius: 16px;
  padding: 14px 16px;
}}
.approval-title {{ font-size: 15px; font-weight: 600; color: @g-text; }}
.approval-detail {{
  font-family: "{FONT_MONO}"; font-size: 12.5px; color: @g-text_mid;
}}
.approval-stack {{ margin-top: 8px; }}
.approval-deny {{
  background-image: none;
  color: #8C2F2F;
  border-color: rgba(140, 47, 47, 0.35);
}}
.approval-note {{ font-size: 11.5px; color: @g-text_dim; }}

/* ---- work panel ---- */
.work-panel {{
  background: @g-surface_alt; border: 1px solid @g-border; border-radius: 16px;
  padding: 12px 14px;
}}
.work-item {{ font-size: 13px; color: @g-text_mid; }}
.work-item.current {{ color: @g-text; }}
.work-heading {{
  font-size: 11px; font-weight: 600; color: @g-text_dim; letter-spacing: .6px;
}}

/* ---- status dot ---- */
.status-pill {{
  background: @g-field; border-radius: 999px; padding: 2px 9px;
  font-size: 11.5px; color: @g-text_mid;
}}
.status-pill.needs_input {{
  background: #FDE9C8; color: #7A4B00;
}}
.user-initials {{ font-size: 12px; font-weight: 600; color: @g-text_mid; }}
.status-dot-idle {{ background: @g-text_faint; }}
.status-dot-thinking {{ background: #7FA4F0; }}
.status-dot-complete {{ background: #6FBF8B; }}
.status-dot-needs_input {{ background: #E8A33D; }}
.status-dot-error {{ background: #D97066; }}
.status-pill.thinking {{ background: #DCE7FB; color: #17457F; }}
.status-pill.error {{ background: #F7DDDB; color: #8C2B22; }}
.composer textview, .composer text {{ background: transparent; color: @g-text; font-size: 15px; }}
.composer-placeholder {{ color: @g-text_dim; }}
.composer-btn {{  background-image: none;
 background: transparent; border: none; border-radius: 999px; padding: 8px; }}
.composer-btn:hover {{ background: @g-field; }}
.send-btn {{ background: @g-pill_bg; border: none; border-radius: 999px; padding: 9px; }}
.send-btn:hover {{ opacity: .88; }}
.send-btn:disabled {{ background: @g-field; }}

/* quick chat overlay */
.quickchat {{ background: transparent; }}
.quickchat-window {{ background: @g-page; }}
.quickchat-card {{
  background: @g-surface; border: 1px solid @g-border; border-radius: 18px;
}}
.quickchat-card entry {{
  background: transparent; color: @g-text; font-size: 16px;
  font-family: "{FONT_MONO}"; caret-color: @g-text;
}}
.quickchat-card entry:focus {{
  outline-style: none; outline-width: 0; box-shadow: none; border: none;
}}

/* ---- focus ----
   The reference shows no focus ring; the caret is the affordance.  The
   `outline` shorthand is not valid GTK4 CSS, so the longhands are used. */
entry, entry:focus, entry:focus-visible {{
  outline-style: none; outline-width: 0; box-shadow: none; border: none;
}}
textview:focus, textview:focus-visible {{
  outline-style: none; outline-width: 0; box-shadow: none;
}}

/* ---- switches ----
   The stock Adwaita switch is purple; the app's palette is monochrome, so
   the accent colour is retinted to match. */
switch {{
  background-color: @g-field;
  min-width: 44px; min-height: 26px;
}}
switch:checked {{ background-color: @g-text; }}
switch slider {{
  background-color: @g-surface; min-width: 20px; min-height: 20px;
  margin: 3px; border-radius: 999px;
}}
switch:checked slider {{ background-color: @g-pill_fg; }}

/* scrollbars */
scrollbar {{ background: transparent; }}
scrollbar slider {{ background: @g-text_faint; border-radius: 999px; min-width: 6px; }}
"""


def install() -> None:
    """Load the stylesheet for the current palette."""
    display = Gdk.Display.get_default()
    if display is None:
        return
    _apply_adwaita_scheme()
    provider = Gtk.CssProvider()
    provider.load_from_string(_css(_active))
    # USER priority, not APPLICATION: the theme-name provider ("Adwaita-empty"
    # here) outranks APPLICATION, which left every Gtk.Button unstyled — no
    # background, no border, white-on-white text.
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
    )


def _apply_adwaita_scheme() -> None:
    """Force libadwaita's base scheme so unstyled widgets match the palette.

    The stock Adwaita theme follows the system preference, which leaves
    widgets the stylesheet does not cover (text views, menus, popovers)
    mismatched against the light surface.
    """
    try:
        import gi as _gi  # noqa: PLC0415

        _gi.require_version("Adw", "1")
        from gi.repository import Adw  # noqa: PLC0415

        Adw.StyleManager.get_default().set_color_scheme(
            Adw.ColorScheme.FORCE_DARK if _active.name == "dark"
            else Adw.ColorScheme.FORCE_LIGHT
        )
    except Exception:  # noqa: BLE001 - libadwaita is optional
        pass


def set_scheme(name: str) -> None:
    """Switch palette ('light' | 'dark') and reload the stylesheet."""
    global _active
    _active = PALETTES.get(name, LIGHT)
    install()


def scheme() -> Palette:
    return _active


# --- icons -----------------------------------------------------------------

_GLYPHS: dict[str, int] | None = None
_ICON_CACHE: dict[tuple, object] = {}

_ALIASES = {
    "content_copy": "share_1",
    "auto_awesome": "gemini_spark",
    "lightbulb": "lightbulb_tips",
    "summarize": "notes_spark",
    "share": "share_2",
    "clock": "schedule",
    "target": "trending_up",
    "board": "dashboard",
    "pillar": "extension",
    "track_changes": "trending_up",
    "monitor_heart": "heart_check",
    "model_training": "school",
    "account_tree": "extension",
    "forum": "chat",
    "bolt": "bolt",
    "edit_square": "edit_square",
    "tune": "tune",
    "keyboard_double_arrow_left": "keyboard",
    "expand_more": "expand_more",
    "chevron_left": "chevron_left",
    "chevron_right": "chevron_right",
    "notifications": "notifications",
    "calendar_month": "calendar_month",
    "checklist": "checklist",
    "psychology": "mood_spark",
    "folder": "folder",
    "search": "search",
    "settings": "settings",
    "help": "help",
    "person": "person",
    "light_mode": "sunny",
    "dark_mode": "nightlight",
    "contrast": "brightness_7",
    "build": "build",
    "attach_file": "attach_file",
    "add": "add",
    "arrow_upward": "arrow_upward",
    "stop": "stop",
    "image": "image",
    "chat": "chat",
    "explore": "explore",
    "gemini_spark": "gemini_spark",
    "schedule": "schedule",
    "share_1": "share_1",
    "share_2": "share_2",
    "tips_and_updates": "lightbulb_tips",
    "notes_spark": "notes_spark",
    "radio_button_unchecked": "radio_button_unchecked",
    "query_stats": "query_stats",
    "thinking_model": "thinking_model",
    "extension": "extension",
}


def _glyphs() -> dict[str, int]:
    global _GLYPHS
    if _GLYPHS is None:
        try:
            data = json.loads((ASSETS / "icon_glyphs.json").read_text())
            _GLYPHS = {str(k): int(v) for k, v in data["glyphs"].items()}
        except Exception:
            _GLYPHS = {}
    return _GLYPHS


def icon_char(name: str) -> str:
    g = _glyphs()
    cp = g.get(name)
    if cp is None:
        cp = g.get(_ALIASES.get(name, ""))
    return chr(cp) if cp else _ALIASES.get(name, name)


def _resolve(name: str) -> str:
    """The glyph on disk for this name, or "" when there is none."""
    for cand in (name, _ALIASES.get(name, "")):
        if cand and (ICON_DIR / f"{cand}.png").exists():
            return cand
    return ""


#: Stock icons used when the extracted glyph set is not present. The client
#: ships no third-party glyphs, so a fresh checkout falls back to these.
SYSTEM_ICONS = {
    "add": "list-add-symbolic",
    "arrow_upward": "go-up-symbolic",
    "attach_file": "mail-attachment-symbolic",
    "auto_awesome": "starred-symbolic",
    "bolt": "power-profile-performance-symbolic",
    "build": "applications-engineering-symbolic",
    "calendar_month": "x-office-calendar-symbolic",
    "chat": "chat-message-new-symbolic",
    "check_circle": "emblem-ok-symbolic",
    "checklist": "view-list-symbolic",
    "chevron_left": "pan-start-symbolic",
    "chevron_right": "pan-end-symbolic",
    "close": "window-close-symbolic",
    "contrast": "preferences-system-symbolic",
    "dark": "weather-clear-night-symbolic",
    "delete": "user-trash-symbolic",
    "devices": "computer-symbolic",
    "edit_square": "document-edit-symbolic",
    "error": "dialog-error-symbolic",
    "expand_more": "pan-down-symbolic",
    "explore": "starred-symbolic",
    "extension": "application-x-addon-symbolic",
    "folder": "folder-symbolic",
    "folder_open": "folder-open-symbolic",
    "gem_spark": "starred-symbolic",
    "gemini_spark": "starred-symbolic",
    "help": "help-browser-symbolic",
    "image": "image-x-generic-symbolic",
    "add_image_spark": "image-x-generic-symbolic",
    "info": "help-about-symbolic",
    "about": "help-about-symbolic",
    "keyboard": "input-keyboard-symbolic",
    "keyboard_double_arrow_left": "go-previous-symbolic",
    "light_mode": "weather-clear-symbolic",
    "lock": "changes-prevent-symbolic",
    "memory": "utilities-system-monitor-symbolic",
    "monitor_heart": "preferences-system-symbolic",
    "notes_spark": "emblem-system-symbolic",
    "notifications": "notifications-symbolic",
    "person": "avatar-default-symbolic",
    "schedule": "alarm-symbolic",
    "search": "system-search-symbolic",
    "settings": "preferences-system-symbolic",
    "stop": "media-playback-stop-symbolic",
    "tune": "preferences-other-symbolic",
}

#: Shown when neither a rendered glyph nor a mapped stock icon is available.
FALLBACK_ICON = "image-missing-symbolic"


def system_icon_name(name: str) -> str:
    """The stock icon to use for one of the client's semantic icon names."""
    resolved = _ALIASES.get(name, name)
    return SYSTEM_ICONS.get(name) or SYSTEM_ICONS.get(resolved) or FALLBACK_ICON


def icon_texture(name: str, tone: str = "", filled: bool = False):
    """Load a pre-rendered glyph as a Gdk.Texture, or None if it is absent."""
    key = (name, tone, filled)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    texture = None
    base = _resolve(name)
    if base:
        fill = "~filled" if filled else ""
        t = tone or _active.icon_muted
        for candidate in (ICON_DIR / f"{base}{fill}~{t}.png",
                          ICON_DIR / f"{base}{fill}.png",
                          ICON_DIR / f"{base}.png"):
            if candidate.exists():
                try:
                    texture = Gdk.Texture.new_from_filename(str(candidate))
                except Exception:  # noqa: BLE001 - a broken glyph is not fatal
                    texture = None
                break
    _ICON_CACHE[key] = texture
    return texture


def icon(name: str, size: int = 20, tone: str = "", filled: bool = False) -> Gtk.Image:
    """A Gtk.Image showing one pre-rendered glyph.

    The image is pinned to a square: a Gtk.Image stretches its paintable to
    the allocation, so in a taller row the glyph would be drawn distorted.
    """
    texture = icon_texture(name, tone, filled)
    if texture is None:
        img = Gtk.Image.new_from_icon_name(system_icon_name(name))
    else:
        img = Gtk.Image.new_from_paintable(texture)
    img.set_pixel_size(size)
    img.set_size_request(size, size)
    img.set_halign(Gtk.Align.CENTER)
    img.set_valign(Gtk.Align.CENTER)
    img.set_accessible_role(Gtk.AccessibleRole.IMG)
    return img


def icon_button(name: str, tooltip: str = "", size: int = 20,
                tone: str = "", filled: bool = False) -> Gtk.Button:
    btn = Gtk.Button()
    btn.add_css_class("icon-btn")
    btn.set_child(icon(name, size, tone, filled))
    if tooltip:
        btn.set_tooltip_text(tooltip)
    return btn
