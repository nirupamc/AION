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


def _normalize_unit(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (ValueError, TypeError):
        return None
    if v < 0 or v > 1:
        return None
    return round(v, 4)


def _normalize_loudness(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (ValueError, TypeError):
        return None
    if v < -100 or v > 20:
        return None
    return round(v, 2)


def _normalize_time_signature(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        v = int(value)
    except (ValueError, TypeError):
        return None
    if v < 1 or v > 32:
        return None
    return v


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

        # Soundcharts wraps payload as {"type":"song","object":{...},"errors":[]}
        # Handle both wrapped (current API) and legacy flat shapes.
        payload_obj = data.get("object") if isinstance(data.get("object"), dict) else data

        song_uuid = payload_obj.get("uuid") or payload_obj.get("id") or data.get("uuid") or data.get("id")
        if not song_uuid:
            return EnrichmentResult(source=self.name, status="no_match")

        # Audio features are nested under "audio" in current API; fall back to top-level for legacy mocks.
        audio = payload_obj.get("audio") if isinstance(payload_obj.get("audio"), dict) else {}

        tempo_raw = audio.get("tempo") if audio else None
        if tempo_raw is None:
            tempo_raw = payload_obj.get("tempo") if payload_obj.get("tempo") is not None else data.get("tempo")
        tempo = _normalize_bpm(tempo_raw)

        key_raw = audio.get("key") if audio and "key" in audio else payload_obj.get("key", data.get("key"))
        mode_raw = audio.get("mode") if audio and "mode" in audio else payload_obj.get("mode", data.get("mode"))
        key_norm = _normalize_key(key_raw, mode_raw)

        time_signature = None
        if audio and "timeSignature" in audio:
            time_signature = audio.get("timeSignature")
        elif audio and "time_signature" in audio:
            time_signature = audio.get("time_signature")
        else:
            time_signature = payload_obj.get("time_signature") or payload_obj.get("timeSignature") or data.get("time_signature")

        tempo_ev = tempo_raw
        key_ev = key_raw
        mode_ev = mode_raw

        # Normalize time_signature + audio character fields
        time_signature_norm = _normalize_time_signature(time_signature)

        def _pick_audio(key: str) -> Any:
            if audio and key in audio:
                return audio[key]
            if key in payload_obj:
                return payload_obj[key]
            return data.get(key)

        energy = _normalize_unit(_pick_audio("energy"))
        danceability = _normalize_unit(_pick_audio("danceability"))
        valence = _normalize_unit(_pick_audio("valence"))
        acousticness = _normalize_unit(_pick_audio("acousticness"))
        instrumentalness = _normalize_unit(_pick_audio("instrumentalness"))
        liveness = _normalize_unit(_pick_audio("liveness"))
        speechiness = _normalize_unit(_pick_audio("speechiness"))
        loudness_db = _normalize_loudness(_pick_audio("loudness"))

        evidence: dict[str, Any] = {
            "soundcharts_uuid": song_uuid,
            "tempo": tempo_ev,
            "key": key_ev,
            "mode": mode_ev,
            "time_signature": time_signature_norm,
            "energy": energy,
            "danceability": danceability,
            "valence": valence,
            "acousticness": acousticness,
            "instrumentalness": instrumentalness,
            "liveness": liveness,
            "loudness_db": loudness_db,
            "speechiness": speechiness,
        }
        # Keep raw extras for provenance if present
        for extra in ("acousticness", "danceability", "energy", "instrumentalness", "liveness", "loudness", "speechiness", "valence"):
            raw_val = _pick_audio(extra)
            if raw_val is not None and extra not in evidence:
                evidence[extra] = raw_val

        return EnrichmentResult(
            source=self.name,
            status="matched",
            tempo_bpm=tempo,
            musical_key=key_norm,
            time_signature=time_signature_norm,
            energy=energy,
            danceability=danceability,
            valence=valence,
            acousticness=acousticness,
            instrumentalness=instrumentalness,
            liveness=liveness,
            loudness_db=loudness_db,
            speechiness=speechiness,
            confidence=None,
            source_identifier=song_uuid,
            match_evidence=evidence,
            raw=data,
        )
