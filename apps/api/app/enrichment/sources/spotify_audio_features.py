"""Spotify audio-features enrichment source.

Uses the existing Spotify account access token to call
GET /v1/audio-features/{id}. No additional scopes are required beyond what
M0/M1 already requested.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.enrichment import EnrichmentQuery, EnrichmentResult, EnrichmentSource
from app.providers.base.errors import ProviderAuthenticationError, ProviderRateLimitError

log = logging.getLogger(__name__)


class SpotifyAudioFeaturesSource:
    name = "spotify_audio_features"

    def __init__(
        self,
        access_token: str,
        base_url: str = "https://api.spotify.com/v1",
        *,
        refresh_token: Optional[str] = None,
        on_refresh: Optional[Any] = None,
    ) -> None:
        if not access_token:
            raise ValueError("access_token required")
        self._base = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        self._refresh_token = refresh_token
        self._on_refresh = on_refresh

    async def lookup(self, query: EnrichmentQuery) -> EnrichmentResult:
        if not query.provider_track_id:
            return EnrichmentResult(source=self.name, status="error", error="missing provider_track_id")

        import httpx

        url = f"{self._base}/audio-features/{query.provider_track_id}"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
                resp = await client.get(url, headers=self._headers)
        except httpx.TimeoutException as exc:
            return EnrichmentResult(source=self.name, status="error", error=f"timeout: {exc}")
        except httpx.HTTPError as exc:
            return EnrichmentResult(source=self.name, status="error", error=str(exc))

        if resp.status_code == 401:
            if self._refresh_token and self._on_refresh:
                refreshed = await self._try_refresh()
                if refreshed:
                    self._headers["Authorization"] = f"Bearer {refreshed}"
                    try:
                        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
                            resp = await client.get(url, headers=self._headers)
                    except (httpx.TimeoutException, httpx.HTTPError):
                        return EnrichmentResult(source=self.name, status="error", error="spotify auth failed")
                    if resp.status_code != 401:
                        # proceed to normal handling below
                        pass
                    else:
                        return EnrichmentResult(source=self.name, status="error", error="spotify auth failed")
                else:
                    return EnrichmentResult(source=self.name, status="error", error="reauth required: Reconnect Spotify")
            else:
                return EnrichmentResult(source=self.name, status="error", error="spotify auth failed")
        if resp.status_code == 403:
            return EnrichmentResult(source=self.name, status="error", error="spotify permission denied")
        if resp.status_code == 404:
            return EnrichmentResult(source=self.name, status="no_match", source_identifier=query.provider_track_id)
        if resp.status_code == 429:
            retry_after = _retry_after(resp)
            return EnrichmentResult(
                source=self.name,
                status="error",
                error="rate limited",
                match_evidence={"retry_after": retry_after},
            )
        if resp.status_code >= 500:
            return EnrichmentResult(source=self.name, status="error", error=f"server error {resp.status_code}")

        try:
            data = resp.json()
        except ValueError:
            return EnrichmentResult(source=self.name, status="error", error="invalid json")

        if not isinstance(data, dict) or not data.get("id"):
            return EnrichmentResult(source=self.name, status="no_match")

        from app.enrichment import normalize_bpm, normalize_key

        tempo = normalize_bpm(data.get("tempo"))
        key_norm = normalize_key(data.get("key"), data.get("mode"))
        confidence = _combine_confidence(data.get("tempo_confidence"), data.get("key_confidence"))

        evidence: dict[str, Any] = {
            "spotify_id": data.get("id"),
            "duration_ms": data.get("duration_ms"),
            "mode": data.get("mode"),
            "time_signature": data.get("time_signature"),
            "tempo_confidence": data.get("tempo_confidence"),
            "key_confidence": data.get("key_confidence"),
        }
        for k in ("energy", "danceability", "valence", "loudness", "acousticness", "instrumentalness", "speechiness"):
            if k in data:
                evidence[k] = data[k]

        return EnrichmentResult(
            source=self.name,
            status="matched",
            tempo_bpm=tempo,
            musical_key=key_norm,
            confidence=confidence,
            source_identifier=data.get("id"),
            match_evidence=evidence,
            raw=data,
        )

    async def _try_refresh(self) -> Optional[str]:
        from app.providers.spotify.oauth import refresh_tokens

        try:
            data = await refresh_tokens(refresh_token=self._refresh_token)
        except Exception:
            return None
        new_token = data.get("access_token")
        if not new_token:
            return None
        if self._on_refresh:
            try:
                self._on_refresh(data)
            except Exception:
                pass
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        return new_token


def _retry_after(resp: Any) -> Optional[float]:
    h = resp.headers.get("Retry-After") if hasattr(resp, "headers") else None
    if h is None:
        return None
    try:
        return float(h)
    except (ValueError, TypeError):
        return None


def _combine_confidence(tempo_conf: Any, key_conf: Any) -> Optional[float]:
    vals = []
    for v in (tempo_conf, key_conf):
        if v is not None:
            try:
                vals.append(float(v))
            except (ValueError, TypeError):
                pass
    if not vals:
        return None
    return sum(vals) / len(vals)
