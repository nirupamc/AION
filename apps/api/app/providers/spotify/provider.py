"""Spotify provider: catalog reads, playlist writes.

All methods return normalized provider-internal dataclasses — never raw JSON.
HTTP errors are translated into the provider error hierarchy by HttpClient.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Optional

from app.providers.base.http_client import HttpClient
from app.providers.base.models import (
    PlaylistRef,
    ProviderPlaylist,
    ProviderPlaylistSummary,
    ProviderTrack,
    ProviderUser,
)
from app.providers.spotify import oauth
from app.providers.spotify.parsing import (
    SPOTIFY_PROVIDER_NAME,
    playlist_from_spotify,
    playlist_summary_from_spotify,
    track_from_spotify,
    user_from_spotify,
)

log = logging.getLogger(__name__)


class SpotifyProvider:
    name = SPOTIFY_PROVIDER_NAME

    def __init__(self, *, access_token: str) -> None:
        if not access_token:
            raise ValueError("access_token required")
        self._access_token = access_token
        self._http = HttpClient(oauth.SPOTIFY_API_BASE)

    async def aclose(self) -> None:
        await self._http.aclose()

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    # ---- read ----

    async def get_current_user(self) -> ProviderUser:
        resp = await self._http.request(
            "GET", "/me", headers=self._auth_headers()
        )
        resp.raise_for_status()  # unexpected non-error
        return user_from_spotify(resp.json())

    async def get_track(self, provider_track_id: str) -> ProviderTrack:
        resp = await self._http.request(
            "GET", f"/tracks/{provider_track_id}", headers=self._auth_headers()
        )
        return track_from_spotify(resp.json())

    async def iter_saved_tracks(
        self, *, limit: int = 50
    ) -> AsyncIterator[ProviderTrack]:
        offset = 0
        while True:
            resp = await self._http.request(
                "GET",
                "/me/tracks",
                params={"limit": min(limit, 50), "offset": offset},
                headers=self._auth_headers(),
            )
            data = resp.json()
            for item in data.get("items", []):
                if not item:
                    continue
                from datetime import datetime, timezone
                saved_at_raw = item.get("added_at")
                saved_at: Optional[datetime] = None
                if saved_at_raw:
                    try:
                        saved_at = datetime.fromisoformat(
                            saved_at_raw.replace("Z", "+00:00")
                        ).astimezone(timezone.utc)
                    except ValueError:
                        saved_at = None
                tr = item.get("track")
                if not tr:
                    continue
                try:
                    yield track_from_spotify(
                        tr, saved_at=saved_at, include_raw=True
                    )
                except ValueError:
                    continue
            if not data.get("next"):
                return
            offset += data.get("limit", limit)

    async def peek_saved_tracks(self) -> tuple[int, Optional[object]]:
        """Cheap one-call probe of the user's Liked Songs.

        Returns ``(total, most_recent_added_at)``. Used by the import endpoint
        to decide whether a full pagination is required or the local DB is
        already in sync. The most recent ``added_at`` lets us detect new
        additions to Liked Songs even when the total hasn't changed.
        """
        resp = await self._http.request(
            "GET",
            "/me/tracks",
            params={"limit": 1, "offset": 0},
            headers=self._auth_headers(),
        )
        data = resp.json()
        total = int(data.get("total") or 0)
        items = data.get("items") or []
        if not items:
            return total, None
        added_at_raw = items[0].get("added_at")
        if not added_at_raw:
            return total, None
        from datetime import datetime, timezone
        try:
            return (
                total,
                datetime.fromisoformat(
                    added_at_raw.replace("Z", "+00:00")
                ).astimezone(timezone.utc),
            )
        except ValueError:
            return total, None

    async def get_saved_tracks(
        self, *, limit: int = 50, max_pages: int | None = None
    ) -> list[ProviderTrack]:
        out: list[ProviderTrack] = []
        page_size = min(limit, 50)
        pages = 0
        async for t in self.iter_saved_tracks(limit=page_size):
            out.append(t)
            if len(out) % page_size == 0:
                pages += 1
                if max_pages is not None and pages >= max_pages:
                    break
        return out

    async def iter_playlists(self) -> AsyncIterator[ProviderPlaylistSummary]:
        offset = 0
        while True:
            resp = await self._http.request(
                "GET",
                "/me/playlists",
                params={"limit": 50, "offset": offset},
                headers=self._auth_headers(),
            )
            data = resp.json()
            for item in data.get("items", []):
                if item:
                    yield playlist_summary_from_spotify(item)
            if not data.get("next"):
                return
            offset += data.get("limit", 50)

    async def get_playlists(self) -> list[ProviderPlaylistSummary]:
        return [p async for p in self.iter_playlists()]

    async def get_playlist(self, provider_playlist_id: str) -> ProviderPlaylist:
        # First, the playlist itself.
        resp = await self._http.request(
            "GET",
            f"/playlists/{provider_playlist_id}",
            params={"fields": "id,name,owner(display_name),public,collaborative,external_urls,images,snapshot_id,tracks(total,items(added_at,track(id,name,uri,external_urls,external_ids,duration_ms,artists(id,name),album(id,name,images))))"},
            headers=self._auth_headers(),
        )
        return playlist_from_spotify(resp.json())

    # ---- write ----

    async def create_playlist(
        self,
        *,
        name: str,
        description: str = "",
        is_public: bool = False,
        collaborative: bool = False,
    ) -> ProviderPlaylistSummary:
        # We need the current user id to know which account to create on.
        me = await self.get_current_user()
        resp = await self._http.request(
            "POST",
            f"/users/{me.provider_user_id}/playlists",
            json={
                "name": name,
                "description": description,
                "public": is_public,
                "collaborative": collaborative,
            },
            headers=self._auth_headers(),
        )
        return playlist_summary_from_spotify(resp.json())

    async def add_playlist_items(
        self,
        playlist: PlaylistRef,
        *,
        provider_track_ids: list[str],
        position: int | None = None,
    ) -> str:
        if not provider_track_ids:
            return ""
        body: dict = {"uris": [f"spotify:track:{tid}" for tid in provider_track_ids]}
        if position is not None:
            body["position"] = position
        resp = await self._http.request(
            "POST",
            f"/playlists/{playlist.provider_playlist_id}/tracks",
            json=body,
            headers=self._auth_headers(),
        )
        return (resp.json() or {}).get("snapshot_id", "")
