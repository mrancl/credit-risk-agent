"""Access-token management for the DemoANAF MCP server.

The server (https://demoanaf.ro/mcp) is an OAuth 2.1 protected resource.
Run ``python3 scripts/demoanaf_login.py`` once to authorize in the browser;
after that this module serves fresh access tokens, refreshing them with the
stored refresh token when they near expiry.

A static ``MCP_AUTH_TOKEN`` environment variable, when set, takes precedence
over the token file (useful for tests or pre-provisioned tokens).

For deployed environments, the full ``tokens.json`` content can be supplied as
``DEMOANAF_TOKENS_JSON`` (e.g. from Secret Manager). The refresh token inside
it is used to keep the access token valid while the process is running.
"""

import json
import os
import threading
import time
from pathlib import Path

import httpx

TOKEN_ENDPOINT = "https://demoanaf.ro/oauth/token"
RESOURCE = "https://demoanaf.ro/mcp"
_EXPIRY_LEEWAY_SECONDS = 60

_lock = threading.Lock()


def _token_file() -> Path:
    return Path(
        os.getenv(
            "DEMOANAF_TOKEN_FILE",
            str(Path.home() / ".config" / "demoanaf" / "tokens.json"),
        )
    )


def _load_tokens() -> tuple[dict, Path | None]:
    """Load token set from env var or file. Returns (tokens, file_or_none)."""
    tokens_json = os.getenv("DEMOANAF_TOKENS_JSON", "")
    if tokens_json:
        return json.loads(tokens_json), None

    token_file = _token_file()
    if token_file.exists():
        return json.loads(token_file.read_text()), token_file

    raise RuntimeError(
        "No DemoANAF tokens available. Set DEMOANAF_TOKENS_JSON, "
        f"or run once: python3 scripts/demoanaf_login.py (expected {token_file})"
    )


def _refresh(tokens: dict, token_file: Path | None) -> dict:
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise RuntimeError(
            "DemoANAF access token expired and no refresh token is stored. "
            "Re-run: python3 scripts/demoanaf_login.py"
        )
    response = httpx.post(
        TOKEN_ENDPOINT,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": tokens["client_id"],
            "resource": RESOURCE,
        },
        headers={"User-Agent": "credit-risk-agent/0.1 (demoanaf-token-refresh)"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()

    tokens["access_token"] = payload["access_token"]
    tokens["expires_at"] = time.time() + float(payload.get("expires_in", 3600))
    if payload.get("refresh_token"):
        tokens["refresh_token"] = payload["refresh_token"]

    if token_file is not None:
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(json.dumps(tokens, indent=2))
    return tokens


def get_access_token() -> str:
    """Return a valid DemoANAF access token, refreshing it if needed."""
    static_token = os.getenv("MCP_AUTH_TOKEN", "")
    if static_token:
        return static_token

    with _lock:
        tokens, token_file = _load_tokens()
        if tokens.get("expires_at", 0) - _EXPIRY_LEEWAY_SECONDS <= time.time():
            tokens = _refresh(tokens, token_file)
        return tokens["access_token"]

    with _lock:
        tokens = json.loads(token_file.read_text())
        if tokens.get("expires_at", 0) - _EXPIRY_LEEWAY_SECONDS <= time.time():
            tokens = _refresh(tokens)
        return tokens["access_token"]
