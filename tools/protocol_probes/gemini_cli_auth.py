"""Gemini CLI credential bridge (subscription-tier access).

Reads the Gemini CLI's cached OAuth credentials (~/.gemini/oauth_creds.json)
as a token source for this client — the AI Pro/Ultra subscription tier rather
than the free API-key tier (PROTOCOL_SPEC.md §5). Refreshes expired access
tokens when the cache carries the CLI's client credentials.

Usage: GEMINI_TOKEN_SOURCE=cli client/.venv/bin/python -m client.chat chat …
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

GEMINI_DIR = os.path.expanduser("~/.gemini")
CREDS = os.path.join(GEMINI_DIR, "oauth_creds.json")
TOKEN_ENDPOINT = "https://www.googleapis.com/oauth2/v4/token"

# Public clients shipped inside the open-source Gemini CLI package (not user
# secrets): the CLI's own OAuth client and the Google Cloud SDK client.
PUBLIC_CLIENTS = (
    ("<redacted-google-oauth-client-id>",
     "<redacted-google-oauth-client-secret>"),
    ("<redacted-google-oauth-client-id>",
     "<redacted-google-oauth-client-secret>"),
)


def load():
    try:
        return json.load(open(CREDS))
    except (OSError, ValueError):
        return None


def _refresh(creds):
    pairs = []
    if creds.get("client_id"):
        pairs.append((creds["client_id"], creds.get("client_secret", "")))
    pairs.extend(PUBLIC_CLIENTS)
    last = None
    for client_id, client_secret in pairs:
        form = {"refresh_token": creds.get("refresh_token", ""),
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret}
        req = urllib.request.Request(TOKEN_ENDPOINT,
                                     data=urllib.parse.urlencode(form).encode())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                fresh = json.load(resp)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode()[:120]}"
            continue
        merged = dict(creds, **fresh)
        merged.setdefault("refresh_token", creds.get("refresh_token"))
        merged["client_id"], merged["client_secret"] = client_id, client_secret
        merged["expiry_date"] = int(time.time() * 1000) + int(merged.get("expires_in", 3600)) * 1000
        with open(CREDS, "w") as fh:
            json.dump(merged, fh, indent=2)
        return merged
    raise RuntimeError(f"all client pairs failed: {last}")


def access_token():
    """A usable access token from the CLI cache, or None."""
    creds = load()
    if not creds or not creds.get("access_token"):
        return None
    expiry = creds.get("expiry_date") or 0
    if expiry and expiry - 60_000 > time.time() * 1000:
        return creds["access_token"]
    if creds.get("refresh_token") and creds.get("client_id"):
        try:
            return _refresh(creds)["access_token"]
        except (urllib.error.HTTPError, OSError):
            return creds["access_token"]  # best effort: stale but possibly valid
    return creds["access_token"]


def main():
    """Refresh the CLI token cache and mirror it to client/token.json."""
    creds = load()
    if not creds:
        print("no ~/.gemini/oauth_creds.json — run `gemini --reauth` first")
        return 1
    expiry = creds.get("expiry_date") or 0
    if expiry - 60_000 <= time.time() * 1000:
        creds = _refresh(creds)
        print("refreshed via public client pair")
    token = creds["access_token"]
    mirror = {"access_token": token,
              "refresh_token": creds.get("refresh_token"),
              "token_type": creds.get("token_type", "Bearer"),
              "scope": creds.get("scope"),
              "expires_in": 3600}
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "token.json")
    with open(path, "w") as fh:
        json.dump(mirror, fh, indent=2)
    os.chmod(path, 0o600)
    print("token:", token[:8] + "…  scope:", creds.get("scope"))
    print("mirrored to client/token.json (0600)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
