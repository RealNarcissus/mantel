"""Tests for the plugin host.

The promise being tested is mostly negative: installing never executes code,
bad manifests are refused before anything is copied, safe mode stops everything,
a plugin that hangs becomes an error rather than a hang, and every action is
auditable. The reference plugin proves the positive path.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import (
    fonts_env,  # noqa: F401,E402
    plugins,  # noqa: E402
)

REFERENCE = ROOT / "plugins" / "day-summary"


def good_manifest(**overrides) -> dict:
    manifest = {
        "id": "com.test.sample",
        "name": "Sample",
        "version": "0.1.0",
        "apiVersion": 1,
        "entry": ["python3", "-c", "print('{}')"],
        "permissions": {"fs": "none", "net": [], "memory": "none",
                        "exec": False, "ui": []},
        "commands": [{"id": "go", "title": "Go"}],
    }
    manifest.update(overrides)
    return manifest


def main() -> int:
    failures: list[str] = []
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="mantel-plugins-")
    os.environ.pop("MANTEL_SAFE_MODE", None)

    # --- manifest validation --------------------------------------------
    manifest, problems = plugins.parse_manifest(good_manifest())
    print(f"  valid manifest: {manifest.id if manifest else problems}")
    if manifest is None or problems:
        failures.append(f"a valid manifest was rejected: {problems}")

    bad_cases = {
        "no id": good_manifest(id=""),
        "no name": good_manifest(name=""),
        "wrong api": good_manifest(apiVersion=99),
        "entry is a string": good_manifest(entry="python3 main.py"),
        "unknown permission": good_manifest(
            permissions={"fs": "none", "camera": True}),
        "bad permission value": good_manifest(permissions={"fs": "everywhere"}),
        "command without title": good_manifest(commands=[{"id": "x"}]),
    }
    for label, raw in bad_cases.items():
        got, issues = plugins.parse_manifest(raw)
        if got is not None:
            failures.append(f"{label} was accepted")
        elif not issues:
            failures.append(f"{label} produced no explanation")

    # --- capability sheet -----------------------------------------------
    risky, _ = plugins.parse_manifest(good_manifest(
        permissions={"fs": "workspace", "net": ["api.example.com"],
                     "memory": "read", "exec": True, "ui": ["panel"]}))
    print(f"  capabilities: {risky.capabilities}")
    if len(risky.capabilities) < 5:
        failures.append(f"capability sheet is incomplete: {risky.capabilities}")

    # --- install never runs the plugin ----------------------------------
    marker = Path(tempfile.mkdtemp(prefix="mantel-marker-")) / "ran"
    hostile = Path(tempfile.mkdtemp(prefix="mantel-hostile-"))
    (hostile / "mantel.json").write_text(json.dumps(good_manifest(
        id="com.test.hostile",
        entry=["python3", "-c",
               f"open({str(marker)!r}, 'w').write('x'); print('{{}}')"])))
    plugin, errors = plugins.install(hostile)
    print(f"  installed without executing: {plugin is not None} errors={errors}")
    if plugin is None:
        failures.append(f"install failed: {errors}")
    if marker.exists():
        failures.append("installing a plugin executed it")

    # --- install the reference plugin and call it ----------------------
    reference, errors = plugins.install(REFERENCE)
    if reference is None:
        failures.append(f"reference plugin install failed: {errors}")
    else:
        ok, result = plugins.run_command(reference, "summarise", {
            "tasks": ["pay the invoice", "ship the release"],
            "overdue": 1, "date": "today"})
        print(f"  reference command -> ok={ok} result={result}")
        if not ok:
            failures.append(f"the reference plugin failed: {result}")
        elif "2 tasks today" not in str(result):
            failures.append(f"unexpected plugin output: {result}")

        unknown_ok, unknown = plugins.run_command(reference, "nope")
        if unknown_ok:
            failures.append("an unknown command was accepted")

    # --- enable/disable and safe mode ----------------------------------
    plugins.set_enabled("com.mantel.day-summary", False)
    enabled_now = [p.manifest.id for p in plugins.installed()]
    disabled = plugins.find("com.mantel.day-summary")
    print(f"  after disable: installed={enabled_now} disabled={not disabled.enabled}")
    if disabled.enabled:
        failures.append("disabling a plugin did not stick")
    ok, error = plugins.run_command(disabled, "summarise")
    if ok:
        failures.append("a disabled plugin still ran")

    plugins.set_enabled("com.mantel.day-summary", True)
    os.environ["MANTEL_SAFE_MODE"] = "1"
    print(f"  safe mode: installed={len(plugins.installed())}")
    if plugins.installed():
        failures.append("safe mode still lists plugins")
    ok, error = plugins.run_command(plugins.find("com.mantel.day-summary") or
                                    reference, "summarise")
    if ok:
        failures.append("safe mode ran a plugin")
    os.environ.pop("MANTEL_SAFE_MODE", None)

    # --- a hanging plugin becomes an error, not a hang -----------------
    slow_dir = Path(tempfile.mkdtemp(prefix="mantel-slow-"))
    (slow_dir / "mantel.json").write_text(json.dumps(good_manifest(
        id="com.test.slow",
        entry=["python3", "-c", "import time; time.sleep(30); print('{}')"])))
    slow, _ = plugins.install(slow_dir)
    if slow is not None:
        import time  # noqa: PLC0415

        started = time.time()
        ok, error = plugins.call(slow, "command", {}, timeout=1)
        elapsed = time.time() - started
        print(f"  hanging plugin -> ok={ok} after {elapsed:.1f}s: {str(error)[:60]}")
        if ok:
            failures.append("a hanging plugin was reported as success")
        if elapsed > 8:
            failures.append(f"a hanging plugin blocked for {elapsed:.1f}s")

    # --- palette integration -------------------------------------------
    from app import palette  # noqa: PLC0415

    contributed = [palette.Action("plugin", "Summarise my day",
                                  "Day summary · plugin",
                                  "com.mantel.day-summary|summarise")]
    merged = palette.actions_for("summarise", extras=contributed)
    print(f"  palette merge -> {[(a.kind, a.label) for a in merged][:3]}")
    if not any(action.kind == "plugin" for action in merged):
        failures.append("plugin commands did not reach the palette")
    unrelated = palette.actions_for("call the dentist", extras=contributed)
    if any(action.kind == "plugin" for action in unrelated):
        failures.append("an unrelated query surfaced a plugin command")

    # --- audit log ------------------------------------------------------
    entries = plugins.audit_log(30)
    actions = {entry.get("action") for entry in entries}
    print(f"  audit actions: {sorted(actions)}")
    if not entries:
        failures.append("the audit log is empty")
    if "install" not in actions:
        failures.append("installs are not audited")

    # --- uninstall ------------------------------------------------------
    if not plugins.remove("com.test.hostile"):
        failures.append("uninstall failed")
    if plugins.find("com.test.hostile") is not None:
        failures.append("an uninstalled plugin is still listed")
    if (plugins.plugins_dir() / "com.test.hostile").exists():
        failures.append("uninstall left the plugin's folder behind")

    # --- corrupt state reads as empty ----------------------------------
    plugins.state_path().write_text("{not json")
    if plugins.installed():
        failures.append("a corrupt registry should read as empty")
    print("  corrupt registry reads as empty")

    print()
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        return 1
    print("  plugins: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
