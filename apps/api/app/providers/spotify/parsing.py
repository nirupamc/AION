"""Conversion of Spotify's wire format into our internal provider models.

This is the ONLY place in the codebase that should know the shape of Spotify's
JSON. Everything else uses the normalized dataclasses in app.providers.base.models.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.providers.base.models import (
    ArtistRef,
    ProviderAlbumRef,
    ProviderPlaylist,
    ProviderPlaylistSummary,
    ProviderTrack,
    ProviderUser,
)

log = logging.getLogger(__name__)

SPOTIFY_PROVIDER_NAME = "spotify"


# ---- helpers ----

def _iso_to_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Spotify uses "...Z" UTC format.
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        log.warning("invalid_datetime value=%s", value)
        return None


def _artists(raw: list[dict[str, Any]] | None) -> list[ArtistRef]:
    out: list[ArtistRef] = []
    for a in raw or []:
        if not a:
            continue
        aid = a.get("id")
        name = a.get("name")
        if not aid or not name:
            continue
        out.append(ArtistRef(provider_artist_id=aid, name=name))
    return out


def _album(raw: dict[str, Any] | None) -> Optional[ProviderAlbumRef]:
    if not raw:
        return None
    aid = raw.get("id")
    name = raw.get("name")
    if not aid or not name:
        return None
    images = raw.get("images") or []
    image_url = images[0]["url"] if images else None
    return ProviderAlbumRef(
        provider_album_id=aid, name=name, image_url=image_url
    )


def _external_track_ids(raw: dict[str, Any]) -> dict[str, str]:
    ext = raw.get("external_ids") or {}
    out: dict[str, str] = {}
    isrc = ext.get("isrc")
    ean = ext.get("ean")
    upc = ext.get("upc")
    if isrc:
        out["isrc"] = isrc
    if ean:
        out["ean"] = ean
    if upc:
        out["upc"] = upc
    return out


# ---- top-level conversions ----

def track_from_spotify(
    raw: dict[str, Any], *, saved_at: Optional[datetime] = None, include_raw: bool = True
) -> ProviderTrack:
    """Normalize a Spotify track object (or saved-track wrapper)."""
    # Saved-track wrapper has the track under "track".
    is_saved_wrapper = "track" in raw and isinstance(raw.get("track"), dict)
    inner = raw.get("track") if is_saved_wrapper else raw
    if not inner or inner.get("id") is None:
        raise ValueError("spotify track missing id")

    if saved_at is None and is_saved_wrapper:
        saved_at = _iso_to_dt(raw.get("added_at"))

    isrc = (inner.get("external_ids") or {}).get("isrc")
    album_raw = inner.get("album") or {}
    return ProviderTrack(
        provider=SPOTIFY_PROVIDER_NAME,
        provider_track_id=inner["id"],
        title=inner.get("name") or "",
        artists=_artists(inner.get("artists")),
        album=_album(inner.get("album")),
        duration_ms=inner.get("duration_ms"),
        isrc=isrc,
        ean=(inner.get("external_ids") or {}).get("ean"),
        upc=(inner.get("external_ids") or {}).get("upc"),
        provider_uri=inner.get("uri"),
        provider_url=(inner.get("external_urls") or {}).get("spotify"),
        extra_external_ids=_external_track_ids(inner),
        raw=raw if include_raw else None,
        saved_at=saved_at,
        release_date=album_raw.get("release_date"),
    )


def user_from_spotify(raw: dict[str, Any]) -> ProviderUser:
    return ProviderUser(
        provider=SPOTIFY_PROVIDER_NAME,
        provider_user_id=raw["id"],
        display_name=raw.get("display_name"),
        email=raw.get("email"),
    )


def playlist_summary_from_spotify(raw: dict[str, Any]) -> ProviderPlaylistSummary:
    images = raw.get("images") or []
    image_url = images[0]["url"] if images else None
    return ProviderPlaylistSummary(
        provider=SPOTIFY_PROVIDER_NAME,
        provider_playlist_id=raw["id"],
        name=raw.get("name") or "",
        owner_display_name=(raw.get("owner") or {}).get("display_name"),
        track_count=(raw.get("tracks") or {}).get("total"),
        is_public=raw.get("public"),
        is_collaborative=raw.get("collaborative"),
        provider_url=(raw.get("external_urls") or {}).get("spotify") or image_url,
    )


def playlist_from_spotify(
    raw: dict[str, Any], *, include_raw: bool = True
) -> ProviderPlaylist:
    summary = playlist_summary_from_spotify(raw)
    tracks: list[ProviderTrack] = []
    for item in (raw.get("tracks") or {}).get("items", []):
        if not item:
            continue
        saved_at = _iso_to_dt(item.get("added_at"))
        tr = item.get("track")
        if not tr:
            continue
        try:
            tracks.append(track_from_spotify(tr, saved_at=saved_at, include_raw=include_raw))
        except ValueError:
            continue
    return ProviderPlaylist(
        summary=summary,
        tracks=tracks,
        snapshot_id=(raw.get("tracks") or {}).get("snapshot_id"),
    )
