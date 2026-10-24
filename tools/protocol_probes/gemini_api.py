"""Gemini public API backend (generativelanguage.googleapis.com).

Third-party access surface (PROTOCOL_SPEC.md §5 authorization boundary): API
key auth, official route. Sits behind the same chat interface as the recovered
desktop-protocol backend (client/chat.py), which remains first-party-gated.

Credentials: GEMINI_API_KEY env or "api_key" in client/credentials.json.
"""
import json
import os
import time
import urllib.error
import urllib.request

BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-3.8-flash"
CREDENTIALS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "credentials.json")


def api_key():
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    try:
        return json.load(open(CREDENTIALS)).get("api_key") or ""
    except OSError:
        return ""


def list_models(key):
    req = urllib.request.Request(f"{BASE}/models",
                                 headers={"x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return [m["name"] for m in json.load(resp).get("models", [])]


def generate_content(contents, key, model=DEFAULT_MODEL, tools=None, system=None):
    """One non-streaming generateContent turn (used for tool-call loops)."""
    body = {"contents": contents}
    if tools:
        body["tools"] = tools
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    req = urllib.request.Request(
        f"{BASE}/models/{model}:generateContent",
        data=json.dumps(body).encode(),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as e:
                body = e.read().decode()[:500]
                if e.code in (408, 429, 500, 502, 503) and attempt < 3:
                    time.sleep(2 * (attempt + 1))  # exponential-ish backoff
                    continue
                raise RuntimeError(
                    f"generateContent HTTP {e.code}: {body}") from e
        raise RuntimeError("generateContent: retries exhausted")
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"generateContent HTTP {e.code}: {e.read().decode()[:500]}") from e


def chat_with_tools(prompt, key, model=DEFAULT_MODEL, tools=None, system=None,
                    max_rounds=12, execute=None, log=None):
    """Multi-turn function-calling loop. Returns the model's final text.

    `execute(name, args)` runs a tool (client.skills.execute); `log` receives
    human-readable tool activity. Tool responses go back as functionResponse
    parts; the loop ends when the model answers without further calls.
    """
    history = [{"role": "user", "parts": [{"text": prompt}]}]
    for _ in range(max_rounds):
        resp = generate_content(history, key, model=model, tools=tools, system=system)
        cand = (resp.get("candidates") or [{}])[0]
        parts = cand.get("content", {}).get("parts", [])
        calls = [p["functionCall"] for p in parts if "functionCall" in p]
        if not calls:
            return "".join(p.get("text", "") for p in parts), history
        history.append({"role": "model", "parts": parts})
        results = []
        for call in calls:
            name, args = call.get("name", ""), call.get("args", {})
            if log:
                log(f"→ {name}({', '.join(f'{k}={v!r}' for k, v in args.items())})")
            try:
                out = execute(name, args) if execute else "no tool executor configured"
            except Exception as e:
                out = f"tool error: {e}"
            if log:
                log(f"← {str(out)[:160]}")
            results.append({"functionResponse": {"name": name,
                                                 "response": {"result": str(out)}}})
        history.append({"role": "user", "parts": results})
    return "(tool loop exceeded max_rounds)", history


def stream_generate_content(prompt, key, model=DEFAULT_MODEL, system=None):
    """Yield text deltas from the SSE stream of streamGenerateContent."""
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    req = urllib.request.Request(
        f"{BASE}/models/{model}:streamGenerateContent?alt=sse",
        data=json.dumps(body).encode(),
        headers={"x-goog-api-key": key,
                 "Content-Type": "application/json",
                 "Accept": "text/event-stream"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace")
            if not line.startswith("data: "):
                continue
            payload = line[6:].strip()
            if not payload or payload == "[DONE]":
                continue
            chunk = json.loads(payload)
            for cand in chunk.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    if "text" in part:
                        yield part["text"]
