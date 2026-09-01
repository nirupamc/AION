"""Production TrackAttribute persistence for enrichment sources.

Enrichment sources produce ``EnrichmentResult`` objects. This module turns
those into durable rows in the ``track_attributes`` table while preserving:

- full provenance (source_type, source_name, confidence, analysis_version)
- idempotency per (track_id, attribute_type, source_name, analysis_version)
- the raw provider response under value_json
- never overwriting a different source's rows

Design choices:
- We use UPSERT semantics keyed on the natural unique tuple. SQLite supports
  this via the ON CONFLICT clause; for portable SQL we use SELECT-then-
  INSERT/UPDATE inside a transaction. The unique tuple is enforced at the
  application layer because adding a partial unique index in this milestone
  is out of scope; the model has separate indexes only.
- We mark the upserted row ``is_current=True`` ONLY when no other
  ``is_current=True`` row of the same ``attribute_type`` exists yet. If a
  track already has a current value from another source, the new row is
  still persisted (for audit) but stays ``is_current=False`` until a future
  resolver runs.

This module does not perform any network IO. It is the persistence boundary.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.enrichment import EnrichmentResult
from app.models import Track, TrackAttribute

log = logging.getLogger(__name__)


@dataclass
class PersistenceStats:
    """Per-attribute outcome counts returned by :func:`persist_enrichment`."""

    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    invalid: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "invalid": self.invalid,
            "errors": list(self.errors),
        }


# Attribute-type canonicalization. M4B persisted tempo_bpm + musical_key from
# GetSongBPM. M4C extends to full Soundcharts audio feature set.
# Each attribute type declares how its value is encoded in TrackAttribute.value_json.

def _encode_bpm(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (ValueError, TypeError):
        return None
    if v <= 0 or v > 300:
        return None
    return round(v, 3)


_KEY_TONICS = {"C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"}
_KEY_MODES = {"major", "minor"}


def _encode_key(value: Any) -> Optional[dict[str, Any]]:
    """Encode a canonical musical key into a JSON-serializable dict.

    Accepts:
      - "C# minor" / "F major" (canonical)
      - {"tonic": "C#", "mode": "minor"} (dict)
      - "C#" (tonic only — mode left null)
    """
    if value is None:
        return None
    if isinstance(value, dict):
        tonic = value.get("tonic")
        mode = value.get("mode")
    else:
        s = str(value).strip()
        if not s:
            return None
        parts = s.split()
        if len(parts) == 1:
            tonic, mode = parts[0], None
        elif len(parts) == 2:
            tonic, mode = parts[0], parts[1]
        else:
            return None
    if tonic is None or str(tonic).strip() not in _KEY_TONICS:
        return None
    if mode is not None and str(mode).strip() not in _KEY_MODES:
        return None
    return {
        "tonic": str(tonic).strip(),
        "mode": str(mode).strip() if mode is not None else None,
        "display": f"{tonic} {mode}" if mode else str(tonic),
    }


def _encode_unit(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (ValueError, TypeError):
        return None
    if v < 0 or v > 1:
        return None
    return round(v, 4)


def _encode_loudness(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (ValueError, TypeError):
        return None
    if v < -100 or v > 20:
        return None
    return round(v, 2)


def _encode_time_signature(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        v = int(value)
    except (ValueError, TypeError):
        return None
    if v < 1 or v > 32:
        return None
    return v


_ATTRIBUTE_ENCODERS = {
    "tempo_bpm": _encode_bpm,
    "musical_key": _encode_key,
    "time_signature": _encode_time_signature,
    "energy": _encode_unit,
    "danceability": _encode_unit,
    "valence": _encode_unit,
    "acousticness": _encode_unit,
    "instrumentalness": _encode_unit,
    "liveness": _encode_unit,
    "loudness_db": _encode_loudness,
    "speechiness": _encode_unit,
}


def _find_existing(
    session: Session,
    *,
    track_id: int,
    attribute_type: str,
    source_name: str,
    analysis_version: Optional[str],
) -> Optional[TrackAttribute]:
    """Return the existing row matching the upsert key, if any."""
    conds = [
        TrackAttribute.track_id == track_id,
        TrackAttribute.attribute_type == attribute_type,
        TrackAttribute.source_name == source_name,
    ]
    if analysis_version is None:
        conds.append(TrackAttribute.analysis_version.is_(None))
    else:
        conds.append(TrackAttribute.analysis_version == analysis_version)
    return session.execute(
        select(TrackAttribute).where(and_(*conds))
    ).scalar_one_or_none()


def _any_current(
    session: Session,
    *,
    track_id: int,
    attribute_type: str,
    exclude_id: Optional[int] = None,
) -> bool:
    q = select(TrackAttribute.id).where(
        TrackAttribute.track_id == track_id,
        TrackAttribute.attribute_type == attribute_type,
        TrackAttribute.is_current.is_(True),
    )
    if exclude_id is not None:
        q = q.where(TrackAttribute.id != exclude_id)
    return session.execute(q.limit(1)).first() is not None


def persist_enrichment(
    session: Session,
    *,
    track_id: int,
    result: EnrichmentResult,
    source_type: str,
    source_name: str,
    analysis_version: Optional[str],
) -> PersistenceStats:
    """Persist a single enrichment result to ``track_attributes``.

    Returns a :class:`PersistenceStats` describing what happened. Idempotent
    re-runs for the same upsert key update the existing row in place rather
    than duplicating it.
    """
    stats = PersistenceStats()

    if result.status != "matched":
        stats.skipped += 1
        return stats

    track = session.get(Track, track_id)
    if track is None:
        stats.errors.append(f"track_id={track_id} not found")
        return stats

    candidates: list[tuple[str, Any]] = [
        ("tempo_bpm", result.tempo_bpm),
        ("musical_key", result.musical_key),
        ("time_signature", getattr(result, "time_signature", None)),
        ("energy", getattr(result, "energy", None)),
        ("danceability", getattr(result, "danceability", None)),
        ("valence", getattr(result, "valence", None)),
        ("acousticness", getattr(result, "acousticness", None)),
        ("instrumentalness", getattr(result, "instrumentalness", None)),
        ("liveness", getattr(result, "liveness", None)),
        ("loudness_db", getattr(result, "loudness_db", None)),
        ("speechiness", getattr(result, "speechiness", None)),
    ]

    for attribute_type, raw_value in candidates:
        encoder = _ATTRIBUTE_ENCODERS.get(attribute_type)
        if encoder is None:
            stats.invalid += 1
            continue
        encoded = encoder(raw_value)
        if encoded is None:
            # Attribute is genuinely missing for this match.
            continue

        existing = _find_existing(
            session,
            track_id=track_id,
            attribute_type=attribute_type,
            source_name=source_name,
            analysis_version=analysis_version,
        )
        if existing is not None:
            existing.value_json = json.dumps(encoded, ensure_ascii=False)
            existing.confidence = result.confidence
            existing.observed_at = result.match_evidence.get("observed_at") or existing.observed_at
            # Promote this row to "current" only if no other current exists.
            if not _any_current(
                session,
                track_id=track_id,
                attribute_type=attribute_type,
                exclude_id=existing.id,
            ):
                existing.is_current = True
            stats.updated += 1
            continue

        is_current = not _any_current(
            session, track_id=track_id, attribute_type=attribute_type
        )
        session.add(
            TrackAttribute(
                track_id=track_id,
                attribute_type=attribute_type,
                value_json=json.dumps(encoded, ensure_ascii=False),
                source_type=source_type,
                source_name=source_name,
                confidence=result.confidence,
                analysis_version=analysis_version,
                is_current=is_current,
            )
        )
        stats.inserted += 1

    return stats


def already_enriched(
    session: Session,
    *,
    track_id: int,
    source_name: str,
    analysis_version: Optional[str],
) -> bool:
    """Return True if any TrackAttribute row already exists for this upsert key.

    Used by the batch command to skip tracks that were already processed.
    Checks all attribute types — a track is considered enriched if *any*
    attribute of this source/version exists (not just tempo/key).
    """
    for attr_type in _ATTRIBUTE_ENCODERS.keys():
        if _find_existing(
            session,
            track_id=track_id,
            attribute_type=attr_type,
            source_name=source_name,
            analysis_version=analysis_version,
        ) is not None:
            return True
    return False