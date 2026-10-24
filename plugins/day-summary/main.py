#!/usr/bin/env python3
"""Reference Mantel plugin: one JSON request in, one JSON response out.

The host spawns this file, writes a single line of JSON to stdin and reads a
single line from stdout. Nothing else is shared — no imports from the app, no
credentials, no shell. That is the whole contract, which is why it fits in a
page.

Request:  {"id": "…", "method": "command", "params": {"command": "summarise",
           "tasks": [...], "overdue": 0, "date": "24 Oct"}}
Response: {"id": "…", "ok": true, "result": {"message": "…"}}
"""
from __future__ import annotations

import json
import sys


def summarise(params: dict) -> dict:
    tasks = [str(task) for task in params.get("tasks") or []]
    overdue = int(params.get("overdue") or 0)
    when = str(params.get("date") or "today")

    if not tasks:
        return {"message": f"Nothing is due {when}. Good day to plan, not to grind."}

    parts = [f"{len(tasks)} task{'s' if len(tasks) != 1 else ''} {when}"]
    if overdue:
        parts.append(f"{overdue} overdue")
    head = " · ".join(parts)
    first = tasks[0]
    if len(tasks) == 1:
        return {"message": f"{head}: {first}."}
    rest = ", ".join(tasks[1:3])
    more = "" if len(tasks) <= 3 else f", and {len(tasks) - 3} more"
    return {"message": f"{head}. Start with “{first}”, then {rest}{more}."}


def main() -> int:
    line = sys.stdin.readline()
    try:
        request = json.loads(line or "{}")
    except ValueError:
        print(json.dumps({"ok": False, "error": "invalid JSON request"}))
        return 0

    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    if method != "command":
        print(json.dumps({"id": request_id, "ok": False,
                          "error": f"unknown method {method!r}"}))
        return 0

    command = params.get("command")
    if command != "summarise":
        print(json.dumps({"id": request_id, "ok": False,
                          "error": f"unknown command {command!r}"}))
        return 0

    print(json.dumps({"id": request_id, "ok": True,
                      "result": summarise(params)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
