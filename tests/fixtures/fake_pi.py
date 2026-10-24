#!/usr/bin/env python3
"""A fake `pi` for the adapter tests.

Speaks just enough of Pi's RPC protocol (docs/rpc.md) to exercise the adapter:
`get_state`, `get_available_models`, `prompt`, `abort`, session events, tool
events and a blocking extension dialog. Deterministic, instant, no Node, no
credentials.

Scenarios are selected by the prompt text:

    "hello"     streams "Hello " + "world", runs one bash tool, settles
    "slow"      streams a delta, then waits until aborted
    "fail"      rejects the prompt with success:false
    "approve"   asks the client to approve a tool call, then reports the answer
    "crash"     exits mid-turn without settling

Usage: MANTEL_PI_BIN=tests/fixtures/fake_pi.py
"""
from __future__ import annotations

import json
import sys
import time

MODELS = [
    {"id": "fake-fast", "name": "Fake Fast", "provider": "fake",
     "contextWindow": 128000, "reasoning": False},
    {"id": "fake-think", "name": "Fake Think", "provider": "fake",
     "contextWindow": 200000, "reasoning": True},
]

SESSION_ID = "fake-session-0001"


def send(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def respond(request_id, command, data=None, success=True, error=None) -> None:
    record = {"type": "response", "command": command, "success": success}
    if request_id is not None:
        record["id"] = request_id
    if data is not None:
        record["data"] = data
    if error is not None:
        record["error"] = error
    send(record)


def stream(text: str, usage_total: int = 12) -> None:
    for index, chunk in enumerate([text[i:i + 6] for i in range(0, len(text), 6)]):
        send({"type": "message_update",
              "usage": {"input": 10, "output": 2, "cacheRead": 0,
                        "cacheWrite": 0, "totalTokens": usage_total,
                        "cost": {"total": 0.001}},
              "assistantMessageEvent": {"type": "text_delta",
                                        "contentIndex": 0, "delta": chunk}})
        time.sleep(0.01)


def main() -> int:
    scenario = ""
    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg == "--model" and index + 1 < len(argv):
            scenario = scenario or ""
    if "--mode" in argv and "rpc" not in argv:
        sys.stderr.write("fake pi: only --mode rpc is implemented\n")
        return 2

    session_id = SESSION_ID
    if "--session-id" in argv:
        session_id = argv[argv.index("--session-id") + 1]

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            command = json.loads(line)
        except ValueError:
            continue
        kind = command.get("type")
        request_id = command.get("id")

        if kind == "get_state":
            respond(request_id, "get_state", {
                "sessionId": session_id,
                "thinkingLevel": "medium",
                "isStreaming": False,
                "model": {"id": "fake-fast", "name": "Fake Fast",
                          "provider": "fake"},
                "messageCount": 0,
            })

        elif kind == "get_available_models":
            respond(request_id, "get_available_models", {"models": MODELS})

        elif kind == "prompt":
            message = str(command.get("message") or "")
            if message == "fail":
                respond(request_id, "prompt", success=False,
                        error="no provider configured")
                continue
            respond(request_id, "prompt", {"disposition": "started"})
            _run_turn(message, session_id)

        elif kind == "abort":
            respond(request_id, "abort")
            send({"type": "agent_settled", "aborted": True})
            return 0

    send({"type": "agent_settled", "aborted": False})
    return 0


def _run_turn(message: str, session_id: str) -> None:
    send({"type": "agent_start"})
    send({"type": "turn_start"})
    send({"type": "message_start",
          "message": {"role": "assistant", "content": [],
                      "stopReason": "pending"}})

    if message == "crash":
        sys.stderr.write("fake pi: provider disconnected\n")
        sys.exit(3)

    if message == "slow":
        send({"type": "message_update",
              "usage": {"totalTokens": 1},
              "assistantMessageEvent": {"type": "text_delta",
                                        "contentIndex": 0, "delta": "work"}})
        time.sleep(30)      # until aborted
        send({"type": "agent_settled", "aborted": True})
        return

    if message == "approve":
        request_id = "dlg-1"
        send({"type": "extension_ui_request", "id": request_id,
              "method": "select", "title": "Allow bash: echo hi?",
              "options": ["Allow once", "Allow for this session",
                          "Always allow in this folder", "Deny"],
              "timeout": 5000})
        answer = None
        while True:
            line = sys.stdin.readline()
            if not line:
                send({"type": "agent_settled", "aborted": True})
                return
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("type") == "extension_ui_response" and \
                    record.get("id") == request_id:
                answer = record
                break
        decision = ("cancelled" if answer.get("cancelled")
                    else str(answer.get("value")))
        stream("decision:" + decision)
        if decision in ("Allow once", "Allow for this session",
                        "Always allow in this folder"):
            send({"type": "tool_execution_start", "toolCallId": "call_9",
                  "toolName": "bash", "args": {"command": "echo hi"}})
            send({"type": "tool_execution_end", "toolCallId": "call_9",
                  "toolName": "bash", "args": {"command": "echo hi"},
                  "result": {"content": [{"type": "text", "text": "hi\n"}]},
                  "isError": False, "durationMs": 5})
        else:
            send({"type": "turn_end",
                  "message": {"role": "assistant", "content": []},
                  "toolResults": []})
        send({"type": "agent_end", "messages": [], "willRetry": False})
        send({"type": "agent_settled", "aborted": False})
        return

    stream("Hello world")
    send({"type": "tool_execution_start", "toolCallId": "call_1",
          "toolName": "bash", "args": {"command": "echo hi"}})
    send({"type": "tool_execution_end", "toolCallId": "call_1",
          "toolName": "bash", "args": {"command": "echo hi"},
          "result": {"content": [{"type": "text", "text": "hi\n"}]},
          "isError": False, "durationMs": 42})
    send({"type": "turn_end", "message": {"role": "assistant", "content": []},
          "toolResults": []})
    send({"type": "agent_end", "messages": [], "willRetry": False})
    send({"type": "agent_settled", "aborted": False})


if __name__ == "__main__":
    raise SystemExit(main())
