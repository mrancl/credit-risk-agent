#!/usr/bin/env python3
"""One-time OAuth login for the DemoANAF MCP server (https://demoanaf.ro/mcp).

Runs the standard OAuth 2.1 flow the server advertises: dynamic client
registration, authorization code with PKCE (S256), then saves the token set to
the file used by app.integrations.demoanaf_auth (default:
~/.config/demoanaf/tokens.json, override with DEMOANAF_TOKEN_FILE).

Stdlib only, so it runs with any Python 3.9+:

    python3 scripts/demoanaf_login.py

A browser window opens for you to log in / authorize on demoanaf.ro; the
script catches the redirect on localhost and exchanges the code for tokens.
After that, the agent refreshes access tokens automatically.
"""

import base64
import hashlib
import json
import os
import secrets
import ssl
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ISSUER = "https://demoanaf.ro"
RESOURCE = "https://demoanaf.ro/mcp"
REGISTRATION_ENDPOINT = f"{ISSUER}/oauth/register"
AUTHORIZATION_ENDPOINT = f"{ISSUER}/oauth/authorize"
TOKEN_ENDPOINT = f"{ISSUER}/oauth/token"
SCOPE = "mcp:tools"
# Cloudflare in front of demoanaf.ro rejects the default Python-urllib agent.
USER_AGENT = "credit-risk-agent/0.1 (demoanaf-oauth-login)"


def _ssl_context() -> ssl.SSLContext:
    """python.org macOS installers ship without system CAs; prefer certifi."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()

CALLBACK_PORT = int(os.getenv("DEMOANAF_CALLBACK_PORT", "8976"))
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"

CONFIG_DIR = Path(
    os.getenv("DEMOANAF_TOKEN_FILE", str(Path.home() / ".config" / "demoanaf" / "tokens.json"))
).parent
TOKEN_FILE = Path(
    os.getenv("DEMOANAF_TOKEN_FILE", str(Path.home() / ".config" / "demoanaf" / "tokens.json"))
)
CLIENT_FILE = CONFIG_DIR / "client.json"


def _post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=30, context=_ssl_context()) as response:
        return json.loads(response.read().decode())


def _post_form(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(payload).encode(),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=30, context=_ssl_context()) as response:
        return json.loads(response.read().decode())


def get_or_register_client() -> dict:
    if CLIENT_FILE.exists():
        client = json.loads(CLIENT_FILE.read_text())
        if REDIRECT_URI in client.get("redirect_uris", []):
            return client

    client = _post_json(
        REGISTRATION_ENDPOINT,
        {
            "client_name": "credit-risk-agent",
            "redirect_uris": [REDIRECT_URI],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": SCOPE,
        },
    )
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CLIENT_FILE.write_text(json.dumps(client, indent=2))
    os.chmod(CLIENT_FILE, 0o600)
    return client


class _CallbackHandler(BaseHTTPRequestHandler):
    result: dict = {}

    def do_GET(self):  # noqa: N802 (http.server API)
        query = urllib.parse.urlparse(self.path).query
        params = dict(urllib.parse.parse_qsl(query))
        _CallbackHandler.result = params
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        body = (
            "<h2>Authorization received.</h2><p>You can close this tab and "
            "return to the terminal.</p>"
            if "code" in params
            else f"<h2>Authorization failed.</h2><pre>{params}</pre>"
        )
        self.wfile.write(body.encode())

    def log_message(self, *args):  # silence request logging
        pass


def main() -> int:
    client = get_or_register_client()
    client_id = client["client_id"]

    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    state = secrets.token_urlsafe(24)

    authorize_url = AUTHORIZATION_ENDPOINT + "?" + urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPE,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": RESOURCE,
        }
    )

    server = HTTPServer(("localhost", CALLBACK_PORT), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print(f"Opening browser for authorization:\n  {authorize_url}\n")
    webbrowser.open(authorize_url)
    print(f"Waiting for the OAuth redirect on {REDIRECT_URI} ...")
    thread.join(timeout=300)
    server.server_close()

    params = _CallbackHandler.result
    if not params:
        print("Timed out waiting for the authorization redirect.", file=sys.stderr)
        return 1
    if params.get("state") != state:
        print("State mismatch in OAuth redirect; aborting.", file=sys.stderr)
        return 1
    if "code" not in params:
        print(f"Authorization failed: {params}", file=sys.stderr)
        return 1

    tokens = _post_form(
        TOKEN_ENDPOINT,
        {
            "grant_type": "authorization_code",
            "code": params["code"],
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": verifier,
            "resource": RESOURCE,
        },
    )

    import time

    stored = {
        "client_id": client_id,
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "expires_at": time.time() + float(tokens.get("expires_in", 3600)),
        "scope": tokens.get("scope", SCOPE),
    }
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(stored, indent=2))
    os.chmod(TOKEN_FILE, 0o600)

    print(f"\nTokens saved to {TOKEN_FILE}")
    if not stored["refresh_token"]:
        print(
            "Warning: no refresh_token returned; you will need to re-run this "
            "script when the access token expires.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
