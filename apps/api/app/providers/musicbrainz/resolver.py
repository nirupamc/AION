"""MusicBrainz identity resolver service.

Resolves canonical Tracks with ISRCs to MusicBrainz Recording MBIDs using the
ISRC lookup endpoint, with explicit pacing, idempotency, deduplication, and
resumability.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Track, TrackIdentifier, TrackIdentityResolution
from app.providers.musicbrainz import MusicBrainzClient, IsrcLookupResult

log = logging.getLogger(__name__)

RESOLUTION_STATUSES = ("MATCHED", "NO_MATCH", "AMBIGUOUS", "ERROR", "DEFERRED")
RESOLVER_VERSION = "m2-isrc-mbid-v1"


class MusicBrainzResolutionError(Exception):
    pass


@dataclass
class ResolutionStats:
    requested: int = 0
    matched: int = 0
    no_match: int = 0
    ambiguous: int = 0
    error: int = 0
    skipped: int = 0
    requests_sent: int = 0

    def as_dict(self) -> dict:
        return {
            "requested": self.requested,
            "matched": self.matched,
            "no_match": self.no_match,
            "ambiguous": self.ambiguous,
            "error": self.error,
            "skipped": self.skipped,
            "requests_sent": self.requests_sent,
        }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _existing_resolution(session: Session, *, track_id: int, query_type: str, query_value: str) -> Optional[TrackIdentityResolution]:
    return session.execute(
        select(TrackIdentityResolution).where(
            TrackIdentityResolution.track_id == track_id,
            TrackIdentityResolution.query_type == query_type,
            TrackIdentityResolution.query_value == query_value,
        )
    ).scalar_one_or_none()


def _ensure_identifier(session: Session, *, track_id: int, identifier_type: str, identifier_value: str) -> None:
    existing = session.execute(
        select(TrackIdentifier).where(
            TrackIdentifier.identifier_type == identifier_type,
            TrackIdentifier.identifier_value == identifier_value,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    session.add(
        TrackIdentifier(
            track_id=track_id,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
        )
    )


def _persist_outcome(
    session: Session,
    *,
    track_id: int,
    query_type: str,
    query_value: str,
    status: str,
    matched_identifier: Optional[str],
    confidence: Optional[float],
    metadata: Optional[dict],
    requests_sent: int,
) -> None:
    now = _utcnow()
    existing = _existing_resolution(session, track_id=track_id, query_type=query_type, query_value=query_value)
    if existing is not None:
        existing.status = status
        existing.matched_identifier = matched_identifier
        existing.confidence = confidence
        existing.metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else None
        existing.resolved_at = now
        existing.updated_at = now
        existing.resolver_version = RESOLVER_VERSION
    else:
        session.add(
            TrackIdentityResolution(
                track_id=track_id,
                query_type=query_type,
                query_value=query_value,
                status=status,
                matched_identifier=matched_identifier,
                confidence=confidence,
                metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
                resolved_at=now,
                resolver_version=RESOLVER_VERSION,
            )
        )
    if status == "MATCHED" and matched_identifier:
        _ensure_identifier(session, track_id=track_id, identifier_type="musicbrainz_recording_id", identifier_value=matched_identifier)


def eligible_tracks_with_isrc(session: Session, *, limit: Optional[int] = None, force_retry: bool = False) -> list[tuple[Track, str]]:
    """Return canonical Tracks that have an ISRC identifier and no prior MB resolution.

    Returns [(track, isrc), ...].
    """
    isrc_subq = (
        select(TrackIdentifier.track_id, TrackIdentifier.identifier_value)
        .where(TrackIdentifier.identifier_type == "isrc")
        .subquery()
    )
    q = (
        select(Track, isrc_subq.c.identifier_value)
        .join(isrc_subq, isrc_subq.c.track_id == Track.id)
        .order_by(Track.id.asc())
    )
    if not force_retry:
        no_resolution_subq = (
            select(TrackIdentityResolution.track_id)
            .where(
                TrackIdentityResolution.query_type == "isrc",
                TrackIdentityResolution.query_value == isrc_subq.c.identifier_value,
                TrackIdentityResolution.status.in_(("MATCHED", "NO_MATCH", "AMBIGUOUS", "ERROR")),
            )
            .subquery()
        )
        q = q.where(Track.id.notin_(select(no_resolution_subq.c.track_id)))
    if limit:
        q = q.limit(limit)
    rows = session.execute(q).all()
    return [(row[0], row[1]) for row in rows]


async def resolve_isrc_to_mbid(
    client: MusicBrainzClient,
    session: Session,
    track: Track,
    isrc: str,
    *,
    force_retry: bool = False,
) -> tuple[str, Optional[str], Optional[float], Optional[dict]]:
    """Resolve a single ISRC for a Track.

    Returns (status, matched_mbid, confidence, metadata).
    """
    if not isrc or not str(isrc).strip():
        raise ValueError("isrc must be a non-empty string")
    if not force_retry:
        existing = _existing_resolution(session, track_id=track.id, query_type="isrc", query_value=isrc)
        if existing is not None:
            return existing.status, existing.matched_identifier, existing.confidence, None

    try:
        result: IsrcLookupResult = await client.lookup_isrc(isrc)
    except ProviderRateLimitError as exc:
        log.warning("musicbrainz rate limited isrc=%s retry_after=%s", isrc, exc.retry_after)
        raise MusicBrainzResolutionError(f"rate limited: {exc.message}") from exc
    except Exception as exc:
        log.error("musicbrainz lookup failed isrc=%s err=%s", isrc, exc)
        return "ERROR", None, None, {"error": str(exc)}

    candidates = [
        {
            "mbid": r.mbid,
            "title": r.title,
            "length_ms": r.length_ms,
            "artist_credit": r.artist_credit,
        }
        for r in result.recordings
    ]
    metadata = {
        "isrc": isrc,
        "raw_count": result.raw_count,
        "candidates": candidates,
    }

    if not candidates:
        return "NO_MATCH", None, 0.0, metadata

    # For M2, enforce a single exact match only. Multiple recordings for the
    # same ISRC are marked AMBIGUOUS and preserved with candidates.
    if len(candidates) == 1:
        return "MATCHED", candidates[0]["mbid"], 1.0, metadata
    return "AMBIGUOUS", None, None, metadata


async def resolve_tracks(session: Session, client: MusicBrainzClient, *, limit: int = 50, force_retry: bool = False) -> ResolutionStats:
    """Resolve up to ``limit`` eligible ISRCs to MusicBrainz Recording MBIDs."""
    if limit is None or limit <= 0:
        raise ValueError("limit must be a positive integer")

    tracks = eligible_tracks_with_isrc(session, limit=limit, force_retry=force_retry)
    stats = ResolutionStats(requested=len(tracks))
    for track, isrc in tracks:
        if not force_retry:
            existing = _existing_resolution(session, track_id=track.id, query_type="isrc", query_value=isrc)
            if existing is not None:
                stats.skipped += 1
                continue
        try:
            status, mbid, confidence, metadata = await resolve_isrc_to_mbid(client, session, track, isrc, force_retry=force_retry)
        except MusicBrainzResolutionError:
            status, mbid, confidence, metadata = "ERROR", None, None, None
        _persist_outcome(
            session,
            track_id=track.id,
            query_type="isrc",
            query_value=isrc,
            status=status,
            matched_identifier=mbid,
            confidence=confidence,
            metadata=metadata,
            requests_sent=1 if metadata and "error" not in (metadata or {}) else 0,
        )
        if status == "MATCHED":
            stats.matched += 1
        elif status == "NO_MATCH":
            stats.no_match += 1
        elif status == "AMBIGUOUS":
            stats.ambiguous += 1
        elif status == "ERROR":
            stats.error += 1
        stats.requests_sent += 1
    session.commit()
    return stats


def resolution_summary(session: Session) -> dict:
    """Aggregated resolution counts for the CLI/API."""
    by_status = dict(
        session.execute(
            select(TrackIdentityResolution.status, func.count(TrackIdentityResolution.id))
            .group_by(TrackIdentityResolution.status)
        ).all()
    )
    total = sum(by_status.values()) or 0
    return {
        "total_resolutions": total,
        "matched": by_status.get("MATCHED", 0),
        "no_match": by_status.get("NO_MATCH", 0),
        "ambiguous": by_status.get("AMBIGUOUS", 0),
        "error": by_status.get("ERROR", 0),
        "deferred": by_status.get("DEFERRED", 0),
    }
