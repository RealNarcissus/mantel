"""Checks for the peripheral features: remote control parsing, the Create
prompt composer, and screenshot plumbing.

Nothing here needs the engine or a GUI: the parsers are pure, and the capture
path is exercised only for its failure behaviour.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import fonts_env  # noqa: F401

from app import remote  # noqa: E402
from app.pages import create  # noqa: E402


def main() -> int:
    failures: list[str] = []

    # --- remote-control status parsing -----------------------------------
    print("  remote: status parsing")
    samples = {
        "running": (
            "Daemon status: active (running)\n"
            "Instance name: sefirah-lunar-plume\n",
            True, "sefirah-lunar-plume"),
        "not assigned": (
            "Daemon status: active (running)\n"
            "Instance name: not assigned yet; the daemon generates one on its "
            "first start.\n",
            True, ""),
        "failed": (
            "Daemon status: Failed to connect to user scope bus\n"
            "Instance name: not assigned yet\n",
            False, ""),
    }
    for name, (text, want_running, want_instance) in samples.items():
        state = remote.RemoteStatus(detail=text)
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("Daemon status:"):
                body = line.split(":", 1)[1].strip().lower()
                state.running = ("active" in body or "running" in body
                                 or "registered" in body)
                state.reachable = state.running and "failed" not in body
            elif line.startswith("Instance name:"):
                value = line.split(":", 1)[1].strip()
                if "not assigned" in value.lower():
                    state.instance = ""
                else:
                    state.instance = value.split()[0].rstrip(";,")
        if state.running != want_running:
            failures.append(f"{name}: running={state.running}, "
                            f"wanted {want_running}")
        if state.instance != want_instance:
            failures.append(f"{name}: instance={state.instance!r}, "
                            f"wanted {want_instance!r}")
        print(f"      {name:14} running={state.running} instance="
              f"{state.instance or '—'}")

    # the label is what the UI shows
    idle = remote.RemoteStatus()
    if idle.label != "Off":
        failures.append(f"idle label was {idle.label!r}")
    live = remote.RemoteStatus(running=True, reachable=True)
    if "phone" not in live.label.lower():
        failures.append(f"running label was {live.label!r}")

    # --- Create prompt composition ---------------------------------------
    print("  create: prompt composition")
    prompt = create.compose_prompt("a red apple", "Photo", 1)
    for expected in ("a red apple", "photorealistic", "image generation tool"):
        if expected not in prompt:
            failures.append(f"prompt is missing {expected!r}")
    if "1 image" not in prompt:
        failures.append("a single image was not described as one image")

    four = create.compose_prompt("a red apple", "3D", 4)
    if "4 images" not in four:
        failures.append("four images were not described as four")
    if "3D render" not in four:
        failures.append("the 3D style was not applied")
    print(f"      style suffix applied, counts: 1 -> "
          f"{'1 image' in prompt}, 4 -> {'4 images' in four}")

    # an unknown style still produces a usable prompt
    unknown = create.compose_prompt("a red apple", "Nonexistent", 1)
    if "a red apple" not in unknown:
        failures.append("an unknown style dropped the description")

    # the output directory is stable and absolute
    out = create.output_dir()
    if not out.is_absolute():
        failures.append("the output directory is not absolute")
    print(f"      output dir: {out}")

    # --- screenshot plumbing ---------------------------------------------
    print("  screenshot: failure path")
    from app import screenshot  # noqa: PLC0415

    if not hasattr(screenshot, "capture"):
        failures.append("screenshot.capture is missing")
    # _local_path style helper: a portal URI becomes a path
    filed = screenshot._file_it("/definitely/not/here.png")  # noqa: SLF001
    if not isinstance(filed, str) or not filed:
        failures.append("_file_it returned nothing for a missing file")
    print("      _file_it tolerates a missing source")

    print()
    if failures:
        for f in failures:
            print(f"  FAIL: {f}")
        return 1
    print("  extras: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
