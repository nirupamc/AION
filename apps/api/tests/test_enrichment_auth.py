"""Tests for enrichment source token refresh behavior."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.enrichment import EnrichmentQuery
from app.enrichment.sources.spotify_audio_features import SpotifyAudioFeaturesSource
from app.providers.base.errors import ProviderAuthenticationError


SPOTIFY_API = "https://api.spotify.com/v1"


@pytest.mark.asyncio
async def test_enrichment_source_refreshes_on_401_and_retries(monkeypatch):
    persisted = {}

    async def _refresh(*, refresh_token: str):
        persisted["refreshed"] = True
        return {
            "access_token": "new-token",
            "refresh_token": "new-refresh",
            "token_type": "Bearer",
            "scope": "user-library-read",
            "expires_in": 3600,
        }

    monkeypatch.setattr(
        "app.providers.spotify.oauth.refresh_tokens", _refresh
    )

    with respx.mock(base_url=SPOTIFY_API) as router:
        router.get("/audio-features/t1").mock(
            side_effect=[
                httpx.Response(401, json={"error": {"status": 401}}),
                httpx.Response(200, json={"id": "t1", "tempo": 120.0, "key": 0, "mode": 1, "duration_ms": 200000}),
            ]
        )

        source = SpotifyAudioFeaturesSource(
            access_token="old-token",
            refresh_token="valid-refresh",
            on_refresh=_refresh,
        )
        result = await source.lookup(EnrichmentQuery(track_id=1, provider_track_id="t1"))
        assert result.status == "matched"
        assert result.tempo_bpm == 120.0
        assert result.musical_key == "C major"
        assert persisted.get("refreshed") is True


@pytest.mark.asyncio
async def test_enrichment_source_reauth_when_refresh_fails(monkeypatch):
    async def _refresh(*, refresh_token: str):
        raise ProviderAuthenticationError("refresh token invalid")

    monkeypatch.setattr(
        "app.providers.spotify.oauth.refresh_tokens", _refresh
    )

    with respx.mock(base_url=SPOTIFY_API) as router:
        router.get("/audio-features/t1").mock(return_value=httpx.Response(401, json={"error": {"status": 401}}))

        source = SpotifyAudioFeaturesSource(
            access_token="old-token",
            refresh_token="bad-refresh",
            on_refresh=lambda data: None,
        )
        result = await source.lookup(EnrichmentQuery(track_id=1, provider_track_id="t1"))
        assert result.status == "error"
        assert "reauth required" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_enrichment_source_no_refresh_without_callback():
    with respx.mock(base_url=SPOTIFY_API) as router:
        router.get("/audio-features/t1").mock(return_value=httpx.Response(401, json={"error": {"status": 401}}))

        source = SpotifyAudioFeaturesSource(access_token="old-token")
        result = await source.lookup(EnrichmentQuery(track_id=1, provider_track_id="t1"))
        assert result.status == "error"
        assert result.error == "spotify auth failed"
