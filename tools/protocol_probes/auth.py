"""OAuth2 authentication for the Gemini client.

Endpoints, client identities and scopes are recovered facts (PROTOCOL_SPEC.md
§5, RE_REPORT.md §4) — not guesses. Interactive login stays with the user; this
module only builds requests and refresh material.
"""
import os
import secrets
import urllib.parse

# Recovered client identities (RE_REPORT.md §4) — RE evidence; a shippable
# client should use its own Desktop-app OAuth client via env overrides.
CLIENT_IDS = (
    "<redacted-google-oauth-client-id>",
    "<redacted-google-oauth-client-id>",
)

# Your own OAuth client (Desktop app): export GEMINI_CLIENT_ID / GEMINI_CLIENT_SECRET.
CLIENT_ID = os.environ.get("GEMINI_CLIENT_ID", CLIENT_IDS[0])
CLIENT_SECRET = os.environ.get("GEMINI_CLIENT_SECRET", "")

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/auth"
TOKEN_ENDPOINT = "https://www.googleapis.com/oauth2/v4/token"
STS_ENDPOINT = "https://sts.googleapis.com/v1/oauthtoken"
DEFAULT_REDIRECT = "http://localhost:2444"

# Recovered scope strings (PROTOCOL_SPEC.md §5).
SCOPES = (
    "https://www.googleapis.com/auth/gemini",
    "https://www.googleapis.com/auth/aicode",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/assistant",
    "https://www.googleapis.com/auth/notifications",
    "https://www.googleapis.com/auth/experimentsandconfigs",
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/photos.image.readonly",
    "https://www.googleapis.com/auth/photospicker.mediaitems.readonly",
    "https://www.googleapis.com/auth/supportcontent",
    "https://www.googleapis.com/auth/oauth_integrations",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
)


def auth_url(client_id=None, redirect_uri=DEFAULT_REDIRECT, scopes=SCOPES,
             state=None):
    """Authorization-code URL to open in a browser (loopback redirect)."""
    if state is None:
        state = secrets.token_urlsafe(16)
    query = urllib.parse.urlencode({
        "client_id": client_id or CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
    })
    return f"{AUTH_ENDPOINT}?{query}"


def token_exchange_form(code, client_id=None, redirect_uri=DEFAULT_REDIRECT,
                        client_secret=None):
    """Form body for TOKEN_ENDPOINT (grant_type=authorization_code)."""
    form = {
        "code": code,
        "client_id": client_id or CLIENT_ID,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    secret = CLIENT_SECRET if client_secret is None else client_secret
    if secret:
        form["client_secret"] = secret
    return form


def refresh_form(refresh_token, client_id=None):
    """Form body for TOKEN_ENDPOINT (grant_type=refresh_token)."""
    form = {
        "refresh_token": refresh_token,
        "client_id": client_id or CLIENT_ID,
        "grant_type": "refresh_token",
    }
    if CLIENT_SECRET:
        form["client_secret"] = CLIENT_SECRET
    return form


def sts_form(subject_token, audience, scope="https://www.googleapis.com/auth/cloud-platform"):
    """Form body for STS_ENDPOINT token exchange (mint API access tokens)."""
    return {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "subject_token": subject_token,
        "audience": audience,
        "scope": scope,
    }


def bearer(token):
    """gRPC call metadata carrying the access token."""
    return (("authorization", f"Bearer {token}"),)
