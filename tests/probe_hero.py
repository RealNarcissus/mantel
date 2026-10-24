import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/"tests"))
from harness import shoot
from app import theme
from app.hero_art import HeroArt
import gi
gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")
from gi.repository import Gtk

def build():
    return HeroArt()

if __name__ == "__main__":
    out = ROOT/"tests"/"out"/"hero_art.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    raise SystemExit(shoot(build, str(out), 700, 452, app_id="dev.gemini.heroart"))
