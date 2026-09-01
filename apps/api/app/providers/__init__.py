"""Provider adapter system.

A provider is anything that can supply catalog and/or write operations:
Spotify, SoundCloud, local files, Rekordbox exports, etc.

Provider-specific response JSON must be converted into the normalized
provider-internal models defined here BEFORE it reaches the core services.
"""

from app.providers.base.errors import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderNotFoundError,
    ProviderPermissionError,
    ProviderRateLimitError,
)
from app.providers.base.models import (
    ArtistRef,
    PlaylistRef,
    ProviderAlbumRef,
    ProviderPlaylist,
    ProviderPlaylistSummary,
    ProviderTrack,
    ProviderUser,
)
from app.providers.base.protocols import (
    AuthProvider,
    CatalogProvider,
    PlaylistWriter,
)

__all__ = [
    "ProviderError",
    "ProviderAuthenticationError",
    "ProviderPermissionError",
    "ProviderRateLimitError",
    "ProviderNotFoundError",
    "ProviderUser",
    "ProviderTrack",
    "ProviderAlbumRef",
    "ArtistRef",
    "ProviderPlaylistSummary",
    "ProviderPlaylist",
    "PlaylistRef",
    "CatalogProvider",
    "PlaylistWriter",
    "AuthProvider",
]
