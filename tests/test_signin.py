"""End-to-end check of the sign-in flow, against a mock Google.

Verifies the loopback server, the CSRF `state` check, the code exchange, the
credential file the engine reads, and the account identity — everything
except Google's own endpoints.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import account  # noqa: E402

# --- a mock Google ---------------------------------------------------------

MOCK_TOKEN = {
    "access_token": "mock-access-token",
    "refresh_token": "mock-refresh-token",
    "scope": " ".join(account.SCOPES),
    "token_type": "Bearer",
    "id_token": ("header."                    # payload
                 + "eyJlbWFpbCI6Im9saXZlQGV4YW1wbGUuY29tIiwi"
                   "ZW1haWwiX3ZlcmlmaWVkIjp0cnVlfQ"  # {"email":...}
                 + ".sig"),
    "expires_in": 3600,
}
REQUESTS: list[dict] = []


class MockHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()
        fields = dict(urllib.parse.parse_qsl(body))
        REQUESTS.append(fields)
        payload = json.dumps(MOCK_TOKEN).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        payload = json.dumps({"email": "oliver@example.com"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_a) -> None:
        return


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="gemini-signin-")
    os.environ["GEMINI_HOME_DIR"] = tmp

    mock = HTTPServer(("127.0.0.1", 0), MockHandler)
    threading.Thread(target=mock.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{mock.server_address[1]}"

    account.AUTH_ENDPOINT = f"{base}/auth"
    account.TOKEN_ENDPOINT = f"{base}/token"
    account.USERINFO_ENDPOINT = f"{base}/userinfo"

    failures = []

    # 1. no account before signing in
    acc = account.load_account()
    print(f"  before sign-in: signed_in={acc.signed_in} email={acc.email!r}")
    if acc.signed_in:
        failures.append("expected no account before signing in")

    # 2. start the flow
    flow = account.SignIn(open_browser=False)
    if not flow.start():
        print(f"  FAIL: could not start: {flow.error}")
        return 1
    print(f"  auth url: {flow.url[:96]}…")
    for required in ("client_id=681255809395", "response_type=code",
                     "access_type=offline", "state="):
        if required not in flow.url:
            failures.append(f"auth url missing {required}")

    # 3. act as the browser: follow the redirect back to the callback
    params = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(flow.url).query))
    callback = (f"http://127.0.0.1:{urllib.parse.urlparse(flow.url).query}"
                if False else "")
    redirect = dict(urllib.parse.parse_qsl(
        urllib.parse.urlparse(flow.url).query))["redirect_uri"]
    state = params["state"]
    try:
        urllib.request.urlopen(
            f"{redirect}?code=mock-code&state={state}", timeout=10)
    except urllib.error.HTTPError as exc:      # 301 is expected
        if exc.code not in (301, 302):
            failures.append(f"unexpected callback status {exc.code}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"callback request failed: {exc}")

    # 4. the flow completes
    acc = flow.result(timeout=30)
    if acc is None:
        failures.append(f"sign-in did not complete: {flow.error}")
    else:
        print(f"  signed in as: {acc.email!r}  display={acc.display_name!r} "
              f"initials={acc.initials!r}")
        print(f"  refresh token stored: {acc.has_refresh_token}  "
              f"scopes: {len(acc.scopes)}")
        if acc.email != "oliver@example.com":
            failures.append(f"wrong email: {acc.email}")
        if not acc.has_refresh_token:
            failures.append("no refresh token stored")

    # 5. the credential file the engine reads is in place
    creds_file = Path(tmp) / "oauth_creds.json"
    if not creds_file.is_file():
        failures.append("oauth_creds.json was not written")
    else:
        data = json.loads(creds_file.read_text())
        print(f"  creds file keys: {sorted(data)}")
        for key in ("access_token", "refresh_token", "scope", "token_type",
                    "id_token", "expiry_date"):
            if key not in data:
                failures.append(f"creds file missing {key}")
        mode = creds_file.stat().st_mode & 0o777
        if mode & 0o077:
            failures.append(f"creds file is too permissive: {oct(mode)}")

    # 6. reloading sees the account
    acc2 = account.load_account()
    if acc2.email != "oliver@example.com":
        failures.append("reload did not find the account")

    # 7. the token exchange sent the right thing
    if not REQUESTS:
        failures.append("no token request was made")
    else:
        sent = REQUESTS[-1]
        print(f"  token request: grant_type={sent.get('grant_type')} "
              f"code={sent.get('code')}")
        if sent.get("grant_type") != "authorization_code":
            failures.append("wrong grant_type")
        if sent.get("code") != "mock-code":
            failures.append("wrong code sent")

    # 8. a mismatched state is refused
    flow2 = account.SignIn(open_browser=False)
    flow2.start()
    redirect2 = dict(urllib.parse.parse_qsl(
        urllib.parse.urlparse(flow2.url).query))["redirect_uri"]
    try:
        urllib.request.urlopen(
            f"{redirect2}?code=mock-code&state=wrong-state", timeout=10)
    except Exception:  # noqa: BLE001
        pass
    acc3 = flow2.result(timeout=8)
    if acc3 is not None:
        failures.append("a mismatched state was accepted")
    else:
        print(f"  mismatched state refused: {flow2.error!r}")

    # 9. signing out clears it
    account.sign_out()
    if account.load_account().signed_in:
        failures.append("sign-out did not clear the account")
    else:
        print("  sign-out cleared the account")

    mock.shutdown()
    print()
    if failures:
        for f in failures:
            print(f"  FAIL: {f}")
        return 1
    print("  all sign-in checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
