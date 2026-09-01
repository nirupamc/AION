"""Liked Songs import service.

Converts Spotify saved tracks into our normalized, durable schema:

    Spotify Saved Tracks
        -> ProviderTrack
        -> Track
        -> TrackIdentifier (when ISRC is present)
        -> TrackIdentifier (spotify_id)

Idempotency:
- ProviderTrack is unique on (provider, provider_track_id).
- TrackIdentifier is unique on (identifier_type, identifier_value).
- A Spotify track id is always written as a 'spotify_id' identifier.
- ISRC, when present, is written as an 'isrc' identifier and used to attach
  the new ProviderTrack to an existing Track when one already exists for that
  ISRC. We do NOT auto-merge by title+artist — too risky.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    ProviderTrack,
    Track,
    TrackIdentifier,
)
from app.providers.base.models import ProviderTrack as IncomingProviderTrack

log = logging.getLogger(__name__)


@dataclass
class ImportStats:
    fetched: int = 0
    tracks_created: int = 0
    provider_tracks_created: int = 0
    provider_tracks_existing: int = 0
    isrc_present: int = 0
    isrc_missing: int = 0
    spotify_id_identifiers_added: int = 0
    isrc_identifiers_added: int = 0
    pages_fetched: int = 0
    short_circuited: bool = False
    remote_total: Optional[int] = None
    local_total: Optional[int] = None

    def as_dict(self) -> dict:
        return {
            "fetched": self.fetched,
            "tracks_created": self.tracks_created,
            "provider_tracks_created": self.provider_tracks_created,
            "provider_tracks_existing": self.provider_tracks_existing,
            "isrc_present": self.isrc_present,
            "isrc_missing": self.isrc_missing,
            "spotify_id_identifiers_added": self.spotify_id_identifiers_added,
            "isrc_identifiers_added": self.isrc_identifiers_added,
            "pages_fetched": self.pages_fetched,
            "short_circuited": self.short_circuited,
            "remote_total": self.remote_total,
            "local_total": self.local_total,
        }


def import_provider_tracks(
    session: Session,
    items: Iterable[IncomingProviderTrack],
    *,
    retain_raw: bool = True,
) -> ImportStats:
    stats = ImportStats()
    for pt in items:
        stats.fetched += 1
        _import_one(session, pt, stats, retain_raw=retain_raw)
    session.commit()
    return stats


def _import_one(
    session: Session,
    pt: IncomingProviderTrack,
    stats: ImportStats,
    *,
    retain_raw: bool,
) -> None:
    # 1. Existing ProviderTrack by (provider, provider_track_id)?
    existing_pt = session.execute(
        select(ProviderTrack).where(
            ProviderTrack.provider == pt.provider,
            ProviderTrack.provider_track_id == pt.provider_track_id,
        )
    ).scalar_one_or_none()

    if existing_pt is not None:
        # Refresh the things that may change over time, but never duplicate the
        # ProviderTrack row.
        existing_pt.raw_title = pt.title
        existing_pt.duration_ms = pt.duration_ms
        existing_pt.provider_uri = pt.provider_uri
        existing_pt.provider_url = pt.provider_url
        existing_pt.artist_display = _artist_display(pt)
        existing_pt.album_name = pt.album.name if pt.album else None
        existing_pt.artwork_url = pt.album.image_url if pt.album else None
        existing_pt.release_date = pt.release_date
        if retain_raw and pt.raw is not None:
            existing_pt.raw_metadata = json.dumps(pt.raw, ensure_ascii=False)
        if pt.saved_at is not None:
            existing_pt.saved_at = pt.saved_at
        stats.provider_tracks_existing += 1
        return

    # 2. Find or create a canonical Track.
    track = _find_track_for_provider_track(session, pt)
    if track is None:
        track = Track(
            canonical_title=pt.title or "(untitled)",
            duration_ms=pt.duration_ms,
        )
        session.add(track)
        session.flush()
        stats.tracks_created += 1

    # 3. Add TrackIdentifiers.
    _ensure_identifier(
        session, track, "spotify_id", pt.provider_track_id,
        stats_added_field="_spotify_id",
        stats=stats,
    )
    if pt.isrc:
        stats.isrc_present += 1
        _ensure_identifier(session, track, "isrc", pt.isrc, stats=stats)
        stats.isrc_identifiers_added += 1
    else:
        stats.isrc_missing += 1

    # 4. Add ProviderTrack.
    session.add(
        ProviderTrack(
            track_id=track.id,
            provider=pt.provider,
            provider_track_id=pt.provider_track_id,
            provider_uri=pt.provider_uri,
            provider_url=pt.provider_url,
            raw_title=pt.title,
            duration_ms=pt.duration_ms,
            saved_at=pt.saved_at,
            artist_display=_artist_display(pt),
            album_name=pt.album.name if pt.album else None,
            artwork_url=pt.album.image_url if pt.album else None,
            release_date=pt.release_date,
            raw_metadata=json.dumps(pt.raw, ensure_ascii=False) if (retain_raw and pt.raw is not None) else None,
        )
    )
    session.flush()
    stats.provider_tracks_created += 1


def _find_track_for_provider_track(
    session: Session, pt: IncomingProviderTrack
) -> Optional[Track]:
    """Strong-signal identity resolution only.

    Order:
      1. A Track that already has a 'spotify_id' identifier matching this
         track id.
      2. A Track that already has an 'isrc' identifier matching this ISRC.
    Title+artist fuzzy matching is intentionally NOT performed in M0.
    """
    # 1. spotify_id
    t = session.execute(
        select(Track)
        .join(TrackIdentifier, TrackIdentifier.track_id == Track.id)
        .where(
            TrackIdentifier.identifier_type == "spotify_id",
            TrackIdentifier.identifier_value == pt.provider_track_id,
        )
    ).scalar_one_or_none()
    if t is not None:
        return t

    # 2. isrc
    if pt.isrc:
        t = session.execute(
            select(Track)
            .join(TrackIdentifier, TrackIdentifier.track_id == Track.id)
            .where(
                TrackIdentifier.identifier_type == "isrc",
                TrackIdentifier.identifier_value == pt.isrc,
            )
        ).scalar_one_or_none()
        if t is not None:
            return t

    return None


def _artist_display(pt: IncomingProviderTrack) -> Optional[str]:
    """Comma-joined display string of artist names for search/sort columns."""
    names = [a.name for a in (pt.artists or []) if a.name]
    if not names:
        return None
    return ", ".join(names)


def _ensure_identifier(
    session: Session,
    track: Track,
    identifier_type: str,
    identifier_value: str,
    *,
    stats: ImportStats,
    stats_added_field: Optional[str] = None,
) -> None:
    existing = session.execute(
        select(TrackIdentifier).where(
            TrackIdentifier.identifier_type == identifier_type,
            TrackIdentifier.identifier_value == identifier_value,
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Already attached (possibly to another Track). We do not move it
        # automatically — duplicates from M0 re-imports are fine.
        return
    session.add(
        TrackIdentifier(
            track_id=track.id,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
        )
    )
    if stats_added_field == "_spotify_id":
        stats.spotify_id_identifiers_added += 1


def count_local_provider_tracks(session: Session, *, provider: str) -> int:
    """Return the number of ProviderTrack rows we have for the given provider.

    Cheap, indexed query. Used by the import endpoint to decide whether a
    full Spotify pagination is needed or we can short-circuit.
    """
    return (
        session.execute(
            select(func.count(ProviderTrack.id)).where(
                ProviderTrack.provider == provider
            )
        ).scalar_one()
    )


def latest_local_saved_at(session: Session, *, provider: str) -> Optional[object]:
    """Return the most recent saved_at we have on file for this provider.

    Used together with `count_local_provider_tracks` to short-circuit the
    import when the local snapshot is already in sync with the provider.
    Returns None when no rows exist.
    """
    return session.execute(
        select(func.max(ProviderTrack.saved_at)).where(ProviderTrack.provider == provider)
    ).scalar_one()
