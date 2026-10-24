"""Font environment bootstrap — must be imported before GTK/Pango initialise.

fontconfig reads FONTCONFIG_FILE once, on its first use, and Pango triggers
that during GTK initialisation. Setting the variable later (e.g. in an
activate handler) silently has no effect, which is why this lives in its own
module with no gi imports and is imported first by every entry point.

Deliberately stdlib-only so it is safe to import before anything else.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "assets" / "fonts"


def _writable(candidates):
    for cand in candidates:
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / ".write-probe"
            probe.write_text("")
            probe.unlink()
            return cand
        except OSError:
            continue
    return None


def cache_dir() -> Path:
    """Writable cache dir: XDG_CACHE_HOME if usable, else project-local."""
    base = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
    found = _writable([base / "gemini-desktop", ROOT / ".cache"])
    if found is None:
        raise RuntimeError("no writable cache directory")
    return found


def install() -> str | None:
    """Point fontconfig at the bundled fonts. Returns the config path."""
    if os.environ.get("GEMINI_LINUX_NO_BUNDLED_FONTS"):
        return None
    if not FONTS_DIR.is_dir():
        return None
    cache = cache_dir()
    conf = cache / "fonts.conf"
    conf.write_text(
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">\n'
        "<fontconfig>\n"
        '  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>\n'
        f"  <dir>{FONTS_DIR}</dir>\n"
        f"  <cachedir>{cache / 'fc-cache'}</cachedir>\n"
        "</fontconfig>\n"
    )
    os.environ["FONTCONFIG_FILE"] = str(conf)
    return str(conf)


CONFIG = install()
