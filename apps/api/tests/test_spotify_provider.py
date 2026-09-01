"""Test pagination and error mapping for the Spotify provider using mocked HTTP."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.providers.base.http_client import HttpClient
from app.providers.base.errors import (
    ProviderAuthenticationError,
    ProviderNotFoundError,
    ProviderPermissionError,
    ProviderRateLimitError,
)
from app.providers.spotify.provider import SpotifyProvider

SPOTIFY_API = "https://api.spotify.com/v1"


def _saved_page(offset: int, limit: int = 50) -> dict:
    return {
        "href": f"https://api.spotify.com/v1/me/tracks?offset={offset}",
        "limit": limit,
        "next": (
            f"https://api.spotify.com/v1/me/tracks?offset={offset + limit}&limit={limit}"
            if offset < 100
            else None
        ),
        "offset": offset,
        "previous": None,
        "total": 150,
        "items": [
            {
                "added_at": "2024-01-01T00:00:00Z",
                "track": {
                    "id": f"track-{offset + i}",
                    "name": f"Track {offset + i}",
                    "uri": f"spotify:track:{offset + i}",
                    "duration_ms": 100000,
                    "external_ids": {"isrc": f"ISRC-{offset + i}"},
                    "external_urls": {"spotify": f"https://open.spotify.com/track/{offset + i}"},
                    "artists": [{"id": "a1", "name": "Artist"}],
                    "album": {
                        "id": f"al-{offset + i}",
                        "name": "Album",
                        "images": [],
                    },
                },
            }
            for i in range(limit)
        ],
    }


@pytest.mark.asyncio
async def test_iter_saved_tracks_paginates_and_collects_all():
    call_count = {"n": 0}

    def _side_effect(request):
        call_count["n"] += 1
        # request.url.query -> "limit=50&offset=0" etc.
        offset = int(request.url.params.get("offset", "0"))
        return httpx.Response(200, json=_saved_page(offset))

    with respx.mock(base_url=SPOTIFY_API, assert_all_called=False) as router:
        router.get("/me/tracks").mock(side_effect=_side_effect)
        provider = SpotifyProvider(access_token="TOKEN")
        try:
            tracks = await provider.get_saved_tracks(limit=50)
        finally:
            await provider.aclose()
    assert len(tracks) == 150
    assert tracks[0].provider_track_id == "track-0"
    assert tracks[149].provider_track_id == "track-149"
    assert call_count["n"] == 3


@pytest.mark.asyncio
async def test_401_maps_to_authentication_error():
    with respx.mock(base_url=SPOTIFY_API) as router:
        router.get("/me").mock(return_value=httpx.Response(401, json={"error": {"status": 401}}))
        provider = SpotifyProvider(access_token="BAD")
        try:
            with pytest.raises(ProviderAuthenticationError):
                await provider.get_current_user()
        finally:
            await provider.aclose()


@pytest.mark.asyncio
async def test_403_maps_to_permission_error():
    with respx.mock(base_url=SPOTIFY_API) as router:
        router.get("/me").mock(return_value=httpx.Response(403, json={"error": {"status": 403}}))
        provider = SpotifyProvider(access_token="TOKEN")
        try:
            with pytest.raises(ProviderPermissionError):
                await provider.get_current_user()
        finally:
            await provider.aclose()


@pytest.mark.asyncio
async def test_404_maps_to_not_found():
    with respx.mock(base_url=SPOTIFY_API) as router:
        router.get("/tracks/xyz").mock(return_value=httpx.Response(404, json={}))
        provider = SpotifyProvider(access_token="TOKEN")
        try:
            with pytest.raises(ProviderNotFoundError):
                await provider.get_track("xyz")
        finally:
            await provider.aclose()


@pytest.mark.asyncio
async def test_429_eventually_raises_rate_limit():
    with respx.mock(base_url=SPOTIFY_API) as router:
        router.get("/me").mock(
            return_value=httpx.Response(
                429, json={}, headers={"Retry-After": "0"}
            )
        )
        provider = SpotifyProvider(access_token="TOKEN")
        try:
            with pytest.raises(ProviderRateLimitError):
                await provider.get_current_user()
        finally:
            await provider.aclose()
