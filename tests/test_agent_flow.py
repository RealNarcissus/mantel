"""End-to-end test of the agent approval loop, against the real engine.

Proves the thing that makes this an agent rather than a chat box:

    1. the agent tries to write a file and is refused (ask mode)
    2. the engine reports the refusal as `denied_actions`
    3. the client turns that into an approval
    4. granting it writes a permission rule the engine honours
    5. the same request now succeeds

Runs against a throwaway HOME so it never touches the real `~/.gemini`.
The credentials are copied (not moved) so the engine can authenticate.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import fonts_env  # noqa: F401,E402

import gi  # noqa: E402

gi.require_version("GLib", "2.0")
from gi.repository import GLib  # noqa: E402

from app import engine as engine_mod  # noqa: E402
from app import permissions  # noqa: E402
from app import session as session_mod  # noqa: E402

MODEL = "gemini-3.8-flash-low"
PROMPT = "Create a file called build.txt containing exactly: ok"


def make_home(base: Path) -> Path:
    """A throwaway HOME with credentials and an empty permission set."""
    home = base / "home"
    gem = home / ".gemini"
    (gem / "config").mkdir(parents=True)
    real = Path.home() / ".gemini"
    for name in ("oauth_creds.json", "google_accounts.json"):
        src = real / name
        if src.is_file():
            shutil.copy2(src, gem / name)
    # `ask` holds the write so the refusal is deterministic in print mode
    (gem / "config" / "config.json").write_text(json.dumps({
        "userSettings": {
            "permissionGrantsV2Migrated": True,
            "globalPermissionGrants": {
                "allow": ["read_file(*)"], "deny": [], "ask": ["write_file(*)"]},
        },
    }, indent=1))
    return home


def run_turn(engine, prompt, session, cwd):
    """Run one turn and wait for it to finish. Returns the result dict."""
    loop = GLib.MainLoop()
    box = {}

    turn = engine.run(prompt=prompt, model=MODEL, cwd=str(cwd),
                      extra_flags=tuple(session.flags()))
    turn.connect("tool", lambda _t, n, d: session.record_tool(n, {"detail": d},
                                                             "ACTIVE"))

    def done(_t, result):
        box["result"] = result
        loop.quit()

    turn.connect("finished", done)
    turn.connect("failed", lambda _t, m: (box.update(result={"error": m}),
                                          loop.quit()))
    GLib.timeout_add_seconds(240, lambda: (turn.cancel(), loop.quit(), False)[2])
    loop.run()
    return box.get("result", {})


def main() -> int:
    binary = engine_mod.find_binary()
    if not binary:
        print("  SKIP: no engine binary")
        return 0

    failures: list[str] = []
    base = Path(tempfile.mkdtemp(prefix="gemini-agent-"))
    workspace = base / "workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("existing notes\n")

    home = make_home(base)
    os.environ["HOME"] = str(home)
    os.environ["GEMINI_HOME_DIR"] = str(home / ".gemini")

    print(f"  home     : {home}")
    print(f"  workspace: {workspace}")
    print(f"  creds    : {(home / '.gemini' / 'oauth_creds.json').is_file()}")
    print(f"  grants writable: {permissions.writable()}")

    engine = engine_mod.Engine()
    sess = session_mod.Session(engine, mode=session_mod.MODE_TASK,
                               approval="ask", workspace=str(workspace))

    # --- 1. the agent is refused -----------------------------------------
    print("\n  [1] ask mode: the write should be refused")
    result = run_turn(engine, PROMPT, sess, workspace)
    denied = result.get("denied") or []
    print(f"      status={result.get('status')} denied={denied}")
    if not (workspace / "build.txt").exists():
        print("      build.txt not created (correct)")
    else:
        failures.append("ask mode wrote the file anyway")
    if not denied:
        failures.append("engine did not report the refusal as denied_actions")

    # --- 2. the refusal becomes an approval -------------------------------
    print("\n  [2] the refusal becomes an approval")
    approvals = sess.record_approvals(denied)
    for a in approvals:
        print(f"      approval: {a.action} -> {a.title} ({a.path})")
    if not approvals:
        failures.append("no approval card was produced")
        write_approval = None
    else:
        write_approval = next((a for a in approvals
                               if a.action == "write_file"), approvals[0])

    # --- 3. granting writes a rule the engine honours ---------------------
    if write_approval is not None:
        print("\n  [3] granting the approval")
        added = sess.grant(write_approval, "project")
        print(f"      rules added: {added}")
        rules = permissions.allowed_rules()
        print(f"      allow rules now: {len(rules)}")
        if not any("write_file" in r for r in rules):
            failures.append("the grant did not add a write_file rule")
        if not permissions.is_trusted(str(workspace)):
            # the folder is trusted separately; not fatal, but report it
            print("      note: folder is not in trustedWorkspaces")

        # --- 4. the same request now succeeds ---------------------------
        print("\n  [4] retrying the same request with the grant in place")
        sess2 = session_mod.Session(engine, mode=session_mod.MODE_TASK,
                                    approval="ask", workspace=str(workspace))
        result2 = run_turn(engine, PROMPT, sess2, workspace)
        print(f"      status={result2.get('status')} "
              f"denied={result2.get('denied')}")
        time.sleep(0.2)
        created = workspace / "build.txt"
        if created.exists():
            print(f"      build.txt created: {created.read_text().strip()!r}")
        else:
            failures.append("the retry still did not write the file")

    # --- 5. full-access mode skips the refusal entirely -------------------
    print("\n  [5] full-access mode should not need approvals")
    (workspace / "build.txt").unlink(missing_ok=True)
    sess3 = session_mod.Session(engine, mode=session_mod.MODE_TASK,
                                approval="full", workspace=str(workspace))
    result3 = run_turn(engine, "Create a file called quick.txt containing: hi",
                       sess3, workspace)
    print(f"      status={result3.get('status')} "
          f"denied={result3.get('denied')}")
    if not (workspace / "quick.txt").exists():
        failures.append("full-access mode did not write the file")

    print()
    if failures:
        for f in failures:
            print(f"  FAIL: {f}")
        return 1
    print("  the approval loop works end to end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
