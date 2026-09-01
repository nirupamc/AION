"""Provider protocols (interfaces).

These describe what a provider CAN do, not how. Spotify implements some,
local file import will implement others. Keeping these small makes it cheap
to add providers later and makes it impossible for core code to depend on
provider-specific behavior.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from app.providers.base.models import (
    PlaylistRef,
    ProviderPlaylist,
    ProviderPlaylistSummary,
    ProviderTrack,
    ProviderUser,
)


@runtime_checkable
class CatalogProvider(Protocol):
    """Read-side capabilities every catalog provider should expose."""

    name: str

    async def get_current_user(self) -> ProviderUser: ...

    async def iter_saved_tracks(
        self, *, limit: int = 50
    ) -> AsyncIterator[ProviderTrack]: ...

    async def get_saved_tracks(
        self, *, limit: int = 50, max_pages: int | None = None
    ) -> list[ProviderTrack]: ...

    async def get_track(self, provider_track_id: str) -> ProviderTrack: ...

    async def iter_playlists(self) -> AsyncIterator[ProviderPlaylistSummary]: ...

    async def get_playlists(self) -> list[ProviderPlaylistSummary]: ...

    async def get_playlist(self, provider_playlist_id: str) -> ProviderPlaylist: ...


@runtime_checkable
class PlaylistWriter(Protocol):
    """Write-side capabilities. Optional; not every provider will support it."""

    name: str

    async def create_playlist(
        self,
        *,
        name: str,
        description: str = "",
        is_public: bool = False,
        collaborative: bool = False,
    ) -> ProviderPlaylistSummary: ...

    async def add_playlist_items(
        self,
        playlist: PlaylistRef,
        *,
        provider_track_ids: list[str],
        position: int | None = None,
    ) -> str:
        """Returns the new provider snapshot id if the provider supplies one."""
        ...


@runtime_checkable
class AuthProvider(Protocol):
    """Separate protocol for auth flows.

    Not every provider needs an OAuth browser flow (e.g. local file imports).
    Keeping it out of CatalogProvider makes that explicit.
    """

    name: str

    def build_authorization_url(self, *, state: str) -> str: ...

    async def exchange_code(self, *, code: str) -> dict:
        """Returns raw token payload from the provider."""
        ...

    async def refresh_tokens(self, *, refresh_token: str) -> dict: ...
