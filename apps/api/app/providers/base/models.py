"""Normalized provider models.

These are deliberately provider-agnostic. Spotify, SoundCloud, and local
imports all convert to these before anything else in the system sees the data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass(frozen=True)
class ArtistRef:
    provider_artist_id: str
    name: str


@dataclass(frozen=True)
class ProviderAlbumRef:
    provider_album_id: str
    name: str
    image_url: Optional[str] = None


@dataclass(frozen=True)
class ProviderTrack:
    """A track as the provider sees it. Already normalized."""

    provider: str
    provider_track_id: str
    title: str
    artists: list[ArtistRef]
    album: Optional[ProviderAlbumRef] = None
    duration_ms: Optional[int] = None
    isrc: Optional[str] = None
    ean: Optional[str] = None
    upc: Optional[str] = None
    provider_uri: Optional[str] = None
    provider_url: Optional[str] = None
    extra_external_ids: dict[str, str] = field(default_factory=dict)
    raw: Optional[dict[str, Any]] = None  # only populated when explicitly retained
    saved_at: Optional[datetime] = None  # e.g. when it was added to Liked Songs
    release_date: Optional[str] = None  # album release_date, e.g. "2026-07-31"


@dataclass(frozen=True)
class ProviderUser:
    provider: str
    provider_user_id: str
    display_name: Optional[str] = None
    email: Optional[str] = None


@dataclass(frozen=True)
class ProviderPlaylistSummary:
    provider: str
    provider_playlist_id: str
    name: str
    owner_display_name: Optional[str] = None
    track_count: Optional[int] = None
    is_public: Optional[bool] = None
    is_collaborative: Optional[bool] = None
    provider_url: Optional[str] = None


@dataclass(frozen=True)
class PlaylistRef:
    provider: str
    provider_playlist_id: str


@dataclass(frozen=True)
class ProviderPlaylist:
    summary: ProviderPlaylistSummary
    tracks: list[ProviderTrack]
    snapshot_id: Optional[str] = None
