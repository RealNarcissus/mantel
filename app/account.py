"""Google account sign-in for the Linux client.

The desktop app authenticates with a Google Account. The engine
(`agy`, the Antigravity-lineage agent) reads its credentials from
``~/.gemini/oauth_creds.json`` — a file this module owns, so signing in here
signs the engine in too.

The OAuth exchange follows Google's own open-source Gemini CLI
(``packages/core/src/code_assist/oauth2.ts``): a loopback redirect on
``http://127.0.0.1:<port>/oauth2callback`` with a CSRF ``state``, and the
*installed application* client it publishes.  Google's own comment on that
client is that the secret "is obviously not treated as a secret" for
installed applications, and the same values are shipped in the open-source
CLI, so they are reproduced here rather than invented.

Scopes: cloud-platform + userinfo.email + userinfo.profile.
"""
from __future__ import annotations

import base64
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Google's published "installed application" OAuth client, as used by the
# open-source Gemini CLI.  See the module docstring.
CLIENT_ID = "<redacted-google-oauth-client-id>"
CLIENT_SECRET = "<redacted-google-oauth-client-secret>"

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"

SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
)

SUCCESS_URL = "https://developers.google.com/gemini-code-assist/auth_success_gemini"
FAILURE_URL = "https://developers.google.com/gemini-code-assist/auth_failure_gemini"

CRED_FILENAME = "oauth_creds.json"
ACCOUNTS_FILENAME = "google_accounts.json"


def gemini_dir() -> Path:
    """`~/.gemini`, overridable for testing."""
    return Path(os.environ.get("GEMINI_HOME_DIR")
                or (Path.home() / ".gemini"))


def creds_path() -> Path:
    return gemini_dir() / CRED_FILENAME


def accounts_path() -> Path:
    return gemini_dir() / ACCOUNTS_FILENAME


@dataclass
class Account:
    """The signed-in identity, as far as it can be read locally."""

    email: str = ""
    scopes: list[str] = field(default_factory=list)
    expires_at: float = 0.0
    has_refresh_token: bool = False

    @property
    def signed_in(self) -> bool:
        return bool(self.email) and self.has_refresh_token

    @property
    def expired(self) -> bool:
        return bool(self.expires_at) and self.expires_at < time.time()

    @property
    def initials(self) -> str:
        if not self.email:
            return "?"
        local = self.email.split("@")[0]
        parts = [p for p in local.replace(".", " ").replace("_", " ").split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[1][0]).upper()

    @property
    def display_name(self) -> str:
        if not self.email:
            return "Not signed in"
        local = self.email.split("@")[0]
        return local.replace(".", " ").replace("_", " ").title()


def _decode_jwt_claims(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:  # noqa: BLE001
        return {}


def load_account() -> Account:
    """Read the stored credentials and work out who is signed in."""
    account = Account()
    try:
        creds = json.loads(creds_path().read_text())
    except (OSError, ValueError):
        creds = {}
    if not isinstance(creds, dict):
        return account

    account.scopes = [s for s in (creds.get("scope") or "").split() if s]
    account.has_refresh_token = bool(creds.get("refresh_token"))
    expiry = creds.get("expiry_date")
    if isinstance(expiry, (int, float)):
        # the CLI stores milliseconds
        account.expires_at = expiry / 1000.0 if expiry > 1e11 else float(expiry)

    email = ""
    id_token = creds.get("id_token")
    if isinstance(id_token, str) and id_token:
        email = _decode_jwt_claims(id_token).get("email", "")
    if not email:
        try:
            accounts = json.loads(accounts_path().read_text())
            email = (accounts or {}).get("active", "")
        except (OSError, ValueError, AttributeError):
            email = ""
    account.email = email or ""
    return account


def sign_out() -> bool:
    """Remove the stored credentials. Returns True if something was removed."""
    removed = False
    for path in (creds_path(), accounts_path()):
        try:
            if path.exists():
                path.unlink()
                removed = True
        except OSError:
            pass
    return removed


def _post_form(url: str, fields: dict) -> dict:
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def refresh(creds: dict | None = None) -> dict | None:
    """Exchange the refresh token for a fresh access token."""
    if creds is None:
        try:
            creds = json.loads(creds_path().read_text())
        except (OSError, ValueError):
            return None
    if not isinstance(creds, dict) or not creds.get("refresh_token"):
        return None
    try:
        token = _post_form(TOKEN_ENDPOINT, {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": creds["refresh_token"],
            "grant_type": "refresh_token",
        })
    except (urllib.error.URLError, OSError, ValueError):
        return None
    merged = dict(creds)
    merged.update(token)
    merged["expiry_date"] = int(time.time() * 1000) + int(
        token.get("expires_in", 3600)) * 1000
    return merged


def _store_creds(creds: dict) -> None:
    path = creds_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(creds, indent=2))
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def _fetch_email(access_token: str) -> str:
    req = urllib.request.Request(
        USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {access_token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp).get("email", "")
    except Exception:  # noqa: BLE001
        return ""


class _CallbackHandler(BaseHTTPRequestHandler):
    """Handles the single OAuth redirect."""

    server: "_CallbackServer"  # type: ignore[assignment]

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        code = (params.get("code") or [""])[0]
        state = (params.get("state") or [""])[0]
        error = (params.get("error") or [""])[0]

        if error:
            self.server.error = f"Sign-in failed: {error}"
            self._finish(FAILURE_URL, f"Sign-in failed: {error}")
            return
        if not code:
            self._finish(FAILURE_URL, "Sign-in failed: no authorization code")
            return
        if state != self.server.expected_state:
            self.server.error = "Sign-in failed: state mismatch"
            self._finish(FAILURE_URL, "Sign-in failed: state mismatch")
            return
        self.server.authorisation_code = code
        self._finish(SUCCESS_URL, "Signed in. You can close this tab.")

    def _finish(self, location: str, message: str) -> None:
        self.send_response(301)
        self.send_header("Location", location)
        self.end_headers()
        try:
            self.wfile.write(message.encode())
        except OSError:
            pass

    def log_message(self, *_args) -> None:  # noqa: D102 - silence the server
        return


class _CallbackServer(HTTPServer):
    expected_state = ""
    authorisation_code = ""
    error = ""


class SignIn:
    """A sign-in attempt.

    Start it, show `url` to the user, open the browser, and wait for
    `result()` to return the signed-in account.
    """

    def __init__(self, open_browser: bool = True):
        self.url = ""
        self.error = ""
        self._server: _CallbackServer | None = None
        self._thread: threading.Thread | None = None
        self._done = threading.Event()
        self._open_browser = open_browser
        self._account: Account | None = None
        self._error = ""

    def start(self) -> bool:
        state = secrets.token_hex(16)
        try:
            self._server = _CallbackServer(("127.0.0.1", 0), _CallbackHandler)
        except OSError as exc:
            self.error = f"Could not start the sign-in callback server: {exc}"
            return False
        self._server.expected_state = state
        port = self._server.server_address[1]
        params = {
            "client_id": CLIENT_ID,
            "redirect_uri": f"http://127.0.0.1:{port}/oauth2callback",
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        self.url = f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"

        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        if self._open_browser:
            try:
                webbrowser.open(self.url)
            except Exception:  # noqa: BLE001
                pass
        return True

    def _serve(self) -> None:
        """Accept the redirect, then exchange the code for tokens."""
        assert self._server is not None
        try:
            self._server.timeout = 300
            while not self._server.authorisation_code and not self._server.error:
                self._server.handle_request()
            self._error = self._server.error
        except Exception:  # noqa: BLE001
            pass
        finally:
            try:
                self._server.server_close()
            except OSError:
                pass
        if self._server.authorisation_code:
            self._exchange()
        elif self._error:
            self._done.set()

    def _exchange(self) -> None:
        """Exchange the captured code for tokens (runs off the UI thread)."""
        assert self._server is not None
        code = self._server.authorisation_code
        redirect = (f"http://127.0.0.1:"
                    f"{self._server.server_address[1]}/oauth2callback")
        try:
            token = _post_form(TOKEN_ENDPOINT, {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect,
            })
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self._error = f"Could not complete sign-in: {exc}"
            self._done.set()
            return

        creds = {
            "access_token": token.get("access_token", ""),
            "refresh_token": token.get("refresh_token", ""),
            "scope": token.get("scope", " ".join(SCOPES)),
            "token_type": token.get("token_type", "Bearer"),
            "id_token": token.get("id_token", ""),
            "expiry_date": int(time.time() * 1000)
            + int(token.get("expires_in", 3600)) * 1000,
        }
        try:
            _store_creds(creds)
        except OSError as exc:
            self._error = f"Could not save the sign-in: {exc}"
            self._done.set()
            return

        email = _fetch_email(creds["access_token"])
        if email:
            try:
                accounts_path().write_text(
                    json.dumps({"active": email, "old": []}, indent=1))
            except OSError:
                pass
        self._account = load_account()
        self._done.set()

    def result(self, timeout: float = 300.0) -> Account | None:
        """Block until the sign-in completes; returns the account or None."""
        if not self._done.wait(timeout):
            self.error = self.error or "Sign-in timed out"
            self._cleanup()
            return None
        self.error = self.error or self._error
        self._cleanup()
        return self._account

    def _cleanup(self) -> None:
        if self._server is not None:
            try:
                self._server.server_close()
            except OSError:
                pass
            self._server = None

    def finish(self) -> Account | None:
        """Exchange the captured code for tokens. Called from the server thread."""
        assert self._server is not None
        code = self._server.authorisation_code
        if not code:
            self.error = self.error or "No authorization code received"
            self._done.set()
            return None
        try:
            token = _post_form(TOKEN_ENDPOINT, {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": f"http://127.0.0.1:"
                                f"{self._server.server_address[1]}/oauth2callback",
            })
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self.error = f"Could not complete sign-in: {exc}"
            self._done.set()
            return None

        creds = {
            "access_token": token.get("access_token", ""),
            "refresh_token": token.get("refresh_token", ""),
            "scope": token.get("scope", " ".join(SCOPES)),
            "token_type": token.get("token_type", "Bearer"),
            "id_token": token.get("id_token", ""),
            "expiry_date": int(time.time() * 1000)
            + int(token.get("expires_in", 3600)) * 1000,
        }
        try:
            _store_creds(creds)
        except OSError as exc:
            self.error = f"Could not save the sign-in: {exc}"
            self._done.set()
            return None

        email = _fetch_email(creds["access_token"])
        if email:
            try:
                accounts_path().write_text(json.dumps({"active": email, "old": []},
                                                      indent=1))
            except OSError:
                pass
        self._account = load_account()
        self._done.set()
        return self._account
