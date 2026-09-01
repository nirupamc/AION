"""Spotify OAuth: Authorization Code with PKCE.

This is the recommended flow for our case: a long-running server-side
application that can safely store the client secret.

References (consulted 2026-08-28):
  - https://developer.spotify.com/documentation/web-api/concepts/authorization
  - https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow
  - https://developer.spotify.com/documentation/web-api/tutorials/refreshing-tokens
  - https://developer.spotify.com/documentation/web-api/concepts/scopes

We add PKCE even though we are a confidential client, as the docs recommend
it for additional safety.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"


# ---- PKCE ----

def _b64url_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge)."""
    verifier = _b64url_nopad(secrets.token_bytes(64))
    challenge = _b64url_nopad(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


# ---- authorization URL ----

def build_authorization_url(*, state: str, code_challenge: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.spotify_client_id,
        "scope": settings.spotify_scopes,
        "redirect_uri": settings.spotify_redirect_uri,
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
    }
    return f"{SPOTIFY_AUTH_URL}?{urlencode(params)}"


# ---- token exchange / refresh ----

class SpotifyOAuthError(RuntimeError):
    pass


async def exchange_code(*, code: str, code_verifier: str) -> dict[str, Any]:
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        raise SpotifyOAuthError(
            "SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET not configured"
        )
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.spotify_redirect_uri,
        "client_id": settings.spotify_client_id,
        "client_secret": settings.spotify_client_secret,
        "code_verifier": code_verifier,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            SPOTIFY_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        raise SpotifyOAuthError(
            f"token exchange failed status={resp.status_code} body={resp.text[:300]}"
        )
    return resp.json()


async def refresh_tokens(*, refresh_token: str) -> dict[str, Any]:
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        raise SpotifyOAuthError(
            "SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET not configured"
        )
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": settings.spotify_client_id,
        "client_secret": settings.spotify_client_secret,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            SPOTIFY_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        raise SpotifyOAuthError(
            f"refresh failed status={resp.status_code} body={resp.text[:300]}"
        )
    return resp.json()
