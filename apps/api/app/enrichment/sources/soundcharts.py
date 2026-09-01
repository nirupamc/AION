"""Soundcharts enrichment source for M4A spike.

Uses the Soundcharts client_credentials OAuth2 flow:
  POST https://account.soundcharts.com/oauth/token
  Basic auth: client_id:client_secret
  Body: grant_type=client_credentials

Then calls:
  GET /api/v2.25/song/by-isrc/{isrc}

No refresh tokens are issued; when the access token expires (default 3600s)
a new one is requested from the token endpoint.

Docs: https://developers.soundcharts.com/api/authorization
      https://developers.soundcharts.com/api/reference/song/get-song-by-isrc
      https://developers.soundcharts.com/api/reference/song/get-song-metadata
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.enrichment import EnrichmentQuery, EnrichmentResult, EnrichmentSource

log = logging.getLogger(__name__)

_SOUNDCHARTS_TOKEN_URL = getattr(settings, "soundcharts_token_url", None) or "https://account.soundcharts.com/oauth/token"
_SOUNDCHARTS_API_BASE = getattr(settings, "soundcharts_base_url", None) or "https://customer.api.soundcharts.com"
_SOUNDCHARTS_API_VERSION = "/api/v2.25"


class SoundchartsError(Exception):
    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SoundchartsAuthError(SoundchartsError):
    pass


class SoundchartsPermissionError(SoundchartsError):
    pass


class SoundchartsNotFoundError(SoundchartsError):
    pass


class SoundchartsRateLimitError(SoundchartsError):
    def __init__(self, message: str, *, status_code: Optional[int] = None, retry_after: Optional[float] = None) -> None:
        super().__init__(message, status_code=status_code)
        self.retry_after = retry_after


def _basic_auth(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}"
    return base64.b64encode(raw.encode("ascii")).decode("ascii")


async def _get_soundcharts_token(client_id: str, client_secret: str, team_id: Optional[str] = None) -> dict[str, Any]:
    headers = {
        "Authorization": f"Basic {_basic_auth(client_id, client_secret)}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    data = {"grant_type": "client_credentials"}
    if team_id:
        data["team_id"] = team_id

    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
        resp = await client.post(_SOUNDCHARTS_TOKEN_URL, headers=headers, data=data)

    if resp.status_code == 401:
        msg = "invalid client credentials"
        try:
            body = resp.json()
            desc = body.get("error_description") or body.get("error") or msg
            if isinstance(desc, str) and desc.strip():
                msg = desc.strip()[:300]
        except Exception:
            pass
        raise SoundchartsAuthError(msg, status_code=401)
    if resp.status_code == 400:
        msg = "bad token request"
        try:
            body = resp.json()
            desc = body.get("error_description") or body.get("error") or msg
            if isinstance(desc, str) and desc.strip():
                msg = desc.strip()[:300]
        except Exception:
            pass
        raise SoundchartsAuthError(msg, status_code=400)
    if resp.status_code == 429:
        retry_after = _retry_after(resp)
        raise SoundchartsRateLimitError("rate limited on token endpoint", status_code=429, retry_after=retry_after)
    if resp.status_code >= 500:
        raise SoundchartsError(f"token endpoint server error {resp.status_code}", status_code=resp.status_code)

    try:
        payload = resp.json()
    except ValueError:
        raise SoundchartsError("invalid json from token endpoint")

    access_token = payload.get("access_token")
    if not access_token:
        raise SoundchartsError("missing access_token in token response")

    return payload


def _retry_after(resp: httpx.Response) -> Optional[float]:
    h = resp.headers.get("Retry-After")
    if h is None:
        return None
    try:
        return float(h)
    except (ValueError, TypeError):
        return None


def _normalize_bpm(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (ValueError, TypeError):
        return None
    if v <= 0 or v > 300:
        return None
    return round(v, 3)


def _normalize_key(value: Any, mode: Any = None) -> Optional[str]:
    PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    if value is None:
        return None
    try:
        pc = int(value)
    except (ValueError, TypeError):
        return None
    if pc < -1 or pc > 11:
        return None
    if pc == -1:
        return None
    tonic = PITCH_CLASSES[pc]
    m = "major" if mode == 1 else "minor" if mode == 0 else None
    if m:
        return f"{tonic} {m}"
    return tonic


class SoundchartsEnrichmentSource:
    name = "soundcharts"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        team_id: Optional[str] = None,
        base_url: str = _SOUNDCHARTS_API_BASE,
        token_url: str = _SOUNDCHARTS_TOKEN_URL,
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError("soundcharts client_id and client_secret are required")
        self._client_id = client_id
        self._client_secret = client_secret
        self._team_id = team_id
        self._base = base_url.rstrip("/")
        self._token_url = token_url
        self._access_token: Optional[str] = None

    async def _ensure_token(self) -> str:
        if self._access_token:
            return self._access_token
        payload = await _get_soundcharts_token(self._client_id, self._client_secret, self._team_id)
        self._access_token = payload["access_token"]
        return self._access_token

    async def lookup(self, query: EnrichmentQuery) -> EnrichmentResult:
        if not query.isrc:
            return EnrichmentResult(
                source=self.name,
                status="error",
                error="missing isrc; exact ISRC lookup required",
            )

        try:
            access_token = await self._ensure_token()
        except SoundchartsRateLimitError as exc:
            return EnrichmentResult(
                source=self.name,
                status="error",
                error=f"rate limited on token request: retry_after={exc.retry_after}",
                error_type="rate_limit",
                http_status=exc.status_code,
            )
        except SoundchartsAuthError as exc:
            return EnrichmentResult(
                source=self.name,
                status="error",
                error=str(exc),
                error_type="authentication",
                http_status=exc.status_code,
            )
        except SoundchartsError as exc:
            return EnrichmentResult(
                source=self.name,
                status="error",
                error=str(exc),
                error_type="provider_failure",
                http_status=exc.status_code,
            )

        url = f"{self._base}{_SOUNDCHARTS_API_VERSION}/song/by-isrc/{query.isrc}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
                resp = await client.get(url, headers=headers)
        except httpx.TimeoutException as exc:
            return EnrichmentResult(source=self.name, status="error", error=f"timeout: {exc}", error_type="timeout")
        except httpx.HTTPError as exc:
            return EnrichmentResult(source=self.name, status="error", error=str(exc), error_type="http_error")

        if resp.status_code == 401:
            self._access_token = None
            msg = "soundcharts auth failed"
            try:
                body = resp.json()
                desc = body.get("error_description") or body.get("error") or msg
                if isinstance(desc, str) and desc.strip():
                    msg = desc.strip()[:300]
            except Exception:
                pass
            return EnrichmentResult(
                source=self.name,
                status="error",
                error=msg,
                error_type="authentication",
                http_status=resp.status_code,
            )
        if resp.status_code == 403:
            msg = "soundcharts permission denied: endpoint not included in current plan"
            try:
                body = resp.json()
                desc = body.get("error_description") or body.get("error") or msg
                if isinstance(desc, str) and desc.strip():
                    msg = desc.strip()[:300]
            except Exception:
                pass
            return EnrichmentResult(
                source=self.name,
                status="error",
                error=msg,
                error_type="plan_permission",
                http_status=resp.status_code,
            )
        if resp.status_code == 404:
            return EnrichmentResult(
                source=self.name,
                status="no_match",
                source_identifier=query.isrc,
            )
        if resp.status_code == 410:
            return EnrichmentResult(
                source=self.name,
                status="error",
                error="soundcharts ISRC blacklisted: multiple tracks identified from DSP",
                error_type="provider_isrc_blacklisted",
                http_status=resp.status_code,
            )
        if resp.status_code == 429:
            retry_after = _retry_after(resp)
            return EnrichmentResult(
                source=self.name,
                status="error",
                error="rate limited",
                error_type="rate_limit",
                http_status=resp.status_code,
                match_evidence={"retry_after": retry_after},
            )
        if resp.status_code >= 500:
            return EnrichmentResult(
                source=self.name,
                status="error",
                error=f"soundcharts server error {resp.status_code}",
                error_type="provider_failure",
                http_status=resp.status_code,
            )

        try:
            data = resp.json()
        except ValueError:
            return EnrichmentResult(source=self.name, status="error", error="invalid json")

        if not isinstance(data, dict):
            return EnrichmentResult(source=self.name, status="no_match")

        song_uuid = data.get("uuid") or data.get("id")
        if not song_uuid:
            return EnrichmentResult(source=self.name, status="no_match")

        tempo = _normalize_bpm(data.get("tempo"))
        key_norm = _normalize_key(data.get("key"), data.get("mode"))
        time_signature = data.get("time_signature")

        evidence: dict[str, Any] = {
            "soundcharts_uuid": song_uuid,
            "tempo": data.get("tempo"),
            "key": data.get("key"),
            "mode": data.get("mode"),
            "time_signature": time_signature,
        }
        for extra in ("acousticness", "danceability", "energy", "instrumentalness", "liveness", "loudness", "speechiness", "valence"):
            if extra in data:
                evidence[extra] = data[extra]

        return EnrichmentResult(
            source=self.name,
            status="matched",
            tempo_bpm=tempo,
            musical_key=key_norm,
            confidence=None,
            source_identifier=song_uuid,
            match_evidence=evidence,
            raw=data,
        )
