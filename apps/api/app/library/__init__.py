"""Library read API — query, paginate, filter, and sort imported tracks.

This module is the single home for the read-only library query logic. Routes
only adapt HTTP params into ``list_tracks`` / ``library_summary`` and serialize
the returned payloads. No raw SQL should leak into route handlers.

Domain honesty:
- The user's "library" is the set of ProviderTrack rows imported from Spotify
  Saved Tracks (Liked Songs). We do NOT fabricate a Playlist row.
- Each returned item is a provider occurrence joined to its canonical Track.
- Only denormalized display columns and TrackIdentifier values are exposed.
  OAuth tokens, client secrets, and raw provider blobs are never returned.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict

from app.models import ProviderTrack, Track, TrackAttribute, TrackIdentifier, TrackIdentityResolution

# Display priority for selecting the "preferred" source shown in the UI when
# multiple TrackAttribute rows of the same type exist for a track. The first
# matching source_name wins. This is purely a presentation rule; backend
# persistence never deletes the other rows.
# M4C: Soundcharts is primary high-coverage source; GetSongBPM is fallback.
PREFERRED_MUSIC_SOURCES: tuple[str, ...] = (
    "soundcharts",
    "getsongbpm",
    "spotify_audio_features",
    "essentia",
)

# ---- supported parameters ----

ALLOWED_PAGE_SIZES = (25, 50, 100)
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100

SORT_OPTIONS = {
    "title_asc",
    "title_desc",
    "artist_asc",
    "artist_desc",
    "album_asc",
    "album_desc",
    "saved_desc",
    "saved_asc",
    "duration_asc",
    "duration_desc",
}

HAS_ISRC_OPTIONS = {"all", "has", "missing"}


class TrackItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    track_id: int
    provider: str
    provider_track_id: str
    title: str
    artists: list[str]
    album: Optional[str]
    artwork_url: Optional[str]
    duration_ms: Optional[int]
    release_date: Optional[str]
    release_year: Optional[int]
    isrc: Optional[str]
    musicbrainz_recording_id: Optional[str]
    provider_uri: Optional[str]
    provider_url: Optional[str]
    saved_at: Optional[str]
    imported_at: Optional[str]
    musical_attributes: dict[str, Optional[dict[str, Any]]] = {}
    music_character: Optional[dict[str, Any]] = None


class TracksPage(BaseModel):
    items: list[TrackItem]
    page: int
    page_size: int
    total: int
    total_pages: int
    sort: str
    provider: Optional[str]
    has_isrc: str
    search: Optional[str]
    bpm_min: Optional[int] = None
    bpm_max: Optional[int] = None
    musical_key: Optional[str] = None
    camelot: Optional[str] = None
    mood: Optional[str] = None
    vibe: Optional[str] = None


@dataclass
class ListParams:
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE
    search: Optional[str] = None
    provider: Optional[str] = None
    has_isrc: str = "all"
    sort: str = "saved_desc"
    bpm_min: Optional[int] = None
    bpm_max: Optional[int] = None
    musical_key: Optional[str] = None
    camelot: Optional[str] = None
    mood: Optional[str] = None
    vibe: Optional[str] = None


# ---- parsing helpers (graceful fallbacks) ----

def _clean_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _year_from_release(release_date: Optional[str]) -> Optional[int]:
    if not release_date:
        return None
    m = re.match(r"(\d{4})", release_date)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _parse_raw_metadata(raw: Optional[str]) -> dict[str, Any]:
    """Parse raw_metadata defensively; never raises."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _artists_from(pt: ProviderTrack, raw: dict[str, Any]) -> list[str]:
    # Prefer a clean parse of the stored JSON when available.
    artists = raw.get("artists") or []
    names = [a.get("name") for a in artists if isinstance(a, dict) and a.get("name")]
    if names:
        return [str(n) for n in names]
    # Fall back to the denormalized column (comma-joined).
    if pt.artist_display:
        return [a.strip() for a in pt.artist_display.split(",") if a.strip()]
    return []


def _artwork_from(pt: ProviderTrack, raw: dict[str, Any]) -> Optional[str]:
    if pt.artwork_url:
        return pt.artwork_url
    album = raw.get("album") or {}
    images = album.get("images") or []
    if images and isinstance(images[0], dict):
        return _clean_str(images[0].get("url"))
    return None


def _release_date_from(pt: ProviderTrack, raw: dict[str, Any]) -> Optional[str]:
    if pt.release_date:
        return pt.release_date
    album = raw.get("album") or {}
    return _clean_str(album.get("release_date"))


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:
            return None
    return None


def _serialize(
    pt: ProviderTrack,
    isrc_by_track: dict[int, str],
    mb_by_track: dict[int, str],
    music_by_track: Optional[dict[int, dict[str, Optional[dict[str, Any]]]]] = None,
    character_by_track: Optional[dict[int, Optional[dict[str, Any]]]] = None,
) -> TrackItem:
    raw = _parse_raw_metadata(pt.raw_metadata)
    title = pt.raw_title or _clean_str(raw.get("name")) or "(untitled)"
    music = (music_by_track or {}).get(pt.track_id) or {
        attr: None for attr in _MUSIC_ATTRIBUTE_TYPES
    }
    # ensure camelot key exists in fallback
    if "camelot" not in music:
        music["camelot"] = None
    character = (character_by_track or {}).get(pt.track_id)
    return TrackItem(
        track_id=pt.track_id,
        provider=pt.provider,
        provider_track_id=pt.provider_track_id,
        title=title,
        artists=_artists_from(pt, raw),
        album=pt.album_name or _clean_str((raw.get("album") or {}).get("name")),
        artwork_url=_artwork_from(pt, raw),
        duration_ms=pt.duration_ms,
        release_date=_release_date_from(pt, raw),
        release_year=_year_from_release(pt.release_date or (raw.get("album") or {}).get("release_date")),
        isrc=isrc_by_track.get(pt.track_id),
        musicbrainz_recording_id=mb_by_track.get(pt.track_id),
        provider_uri=pt.provider_uri,
        provider_url=pt.provider_url,
        saved_at=_iso(pt.saved_at),
        imported_at=_iso(pt.imported_at),
        musical_attributes=music,
        music_character=character,
    )


# ---- query building ----

def _apply_filters(stmt, *, params: ListParams):
    if params.provider:
        stmt = stmt.where(ProviderTrack.provider == params.provider)
    if params.search:
        q = f"%{params.search.strip()}%"
        stmt = stmt.where(
            or_(
                ProviderTrack.raw_title.ilike(q),
                ProviderTrack.artist_display.ilike(q),
                ProviderTrack.album_name.ilike(q),
            )
        )
    if params.has_isrc == "has":
        sub = select(TrackIdentifier.track_id).where(
            TrackIdentifier.identifier_type == "isrc"
        ).distinct()
        stmt = stmt.where(ProviderTrack.track_id.in_(sub))
    elif params.has_isrc == "missing":
        sub = select(TrackIdentifier.track_id).where(
            TrackIdentifier.identifier_type == "isrc"
        ).distinct()
        stmt = stmt.where(ProviderTrack.track_id.notin_(sub))
    return stmt


def _apply_sort(stmt, *, sort: str):
    # Secondary sort on id keeps pagination stable for non-unique fields.
    mapping = {
        "title_asc": [ProviderTrack.raw_title.asc(), ProviderTrack.id.asc()],
        "title_desc": [ProviderTrack.raw_title.desc(), ProviderTrack.id.desc()],
        "artist_asc": [ProviderTrack.artist_display.asc(), ProviderTrack.id.asc()],
        "artist_desc": [ProviderTrack.artist_display.desc(), ProviderTrack.id.desc()],
        "album_asc": [ProviderTrack.album_name.asc(), ProviderTrack.id.asc()],
        "album_desc": [ProviderTrack.album_name.desc(), ProviderTrack.id.desc()],
        "saved_desc": [ProviderTrack.saved_at.desc(), ProviderTrack.id.desc()],
        "saved_asc": [ProviderTrack.saved_at.asc(), ProviderTrack.id.asc()],
        "duration_asc": [ProviderTrack.duration_ms.asc(), ProviderTrack.id.asc()],
        "duration_desc": [ProviderTrack.duration_ms.desc(), ProviderTrack.id.desc()],
    }
    order = mapping.get(sort, mapping["saved_desc"])
    return stmt.order_by(*order)


def list_tracks(session: Session, *, params: ListParams) -> TracksPage:
    base = select(ProviderTrack)
    filtered = _apply_filters(base, params=params)
    filtered = _filter_tracks_by_music(
        filtered,
        bpm_min=params.bpm_min,
        bpm_max=params.bpm_max,
        musical_key=params.musical_key,
        camelot=params.camelot,
    )

    # Mood/vibe are derived (not persisted), so handle via Python post-filter
    mood_filter = (params.mood or "").strip().lower() if params.mood else None
    vibe_filter = (params.vibe or "").strip().lower() if params.vibe else None

    if mood_filter or vibe_filter:
        # Fetch all candidates matching other filters (cap 2000 for performance)
        all_rows = session.execute(_apply_sort(filtered, sort=params.sort)).scalars().all()
        # Compute characters for all
        tids_all = [pt.track_id for pt in all_rows]
        # Batch to avoid large IN query
        music_map = musical_attributes_for(session, list(set(tids_all)))
        char_map = {}
        for tid in set(tids_all):
            char_map[tid] = _music_character_for_attrs(music_map.get(tid, {}))
        # Filter rows by dominant mood/vibe
        filtered_rows = []
        for pt in all_rows:
            char = char_map.get(pt.track_id)
            if not char:
                continue
            if mood_filter and (char.get("dominant_mood") or "").lower() != mood_filter:
                # also check if mood appears in moods list above threshold
                moods = [m["label"].lower() for m in char.get("moods", [])]
                if mood_filter not in moods:
                    continue
            if vibe_filter and (char.get("dominant_vibe") or "").lower() != vibe_filter:
                vibes = [v["label"].lower() for v in char.get("vibes", [])]
                if vibe_filter not in vibes:
                    continue
            filtered_rows.append(pt)
        total = len(filtered_rows)
        total_pages = (total + params.page_size - 1) // params.page_size if total else 0
        if total == 0:
            return TracksPage(
                items=[],
                page=params.page,
                page_size=params.page_size,
                total=0,
                total_pages=0,
                sort=params.sort,
                provider=params.provider,
                has_isrc=params.has_isrc,
                search=params.search,
                bpm_min=params.bpm_min,
                bpm_max=params.bpm_max,
                musical_key=params.musical_key,
                camelot=params.camelot,
                mood=params.mood,
                vibe=params.vibe,
            )
        # paginate in Python
        start = (params.page - 1) * params.page_size
        rows = filtered_rows[start : start + params.page_size]
    else:
        total = session.scalar(
            select(func.count()).select_from(filtered.subquery())
        ) or 0

        total_pages = (total + params.page_size - 1) // params.page_size if total else 0

        if total == 0:
            return TracksPage(
                items=[],
                page=params.page,
                page_size=params.page_size,
                total=0,
                total_pages=0,
                sort=params.sort,
                provider=params.provider,
                has_isrc=params.has_isrc,
                search=params.search,
                bpm_min=params.bpm_min,
                bpm_max=params.bpm_max,
                musical_key=params.musical_key,
                camelot=params.camelot,
                mood=params.mood,
                vibe=params.vibe,
            )

        ordered = _apply_sort(filtered, sort=params.sort)
        rows = session.execute(
            ordered.offset((params.page - 1) * params.page_size).limit(params.page_size)
        ).scalars().all()

    # Gather ISRCs + MBIDs for the page in a single round-trip (avoid N+1).
    track_ids = [pt.track_id for pt in rows]
    isrc_rows = session.execute(
        select(TrackIdentifier.track_id, TrackIdentifier.identifier_value).where(
            TrackIdentifier.track_id.in_(track_ids),
            TrackIdentifier.identifier_type == "isrc",
        )
    ).all()
    isrc_by_track = {tid: val for tid, val in isrc_rows}
    mb_rows = session.execute(
        select(TrackIdentifier.track_id, TrackIdentifier.identifier_value).where(
            TrackIdentifier.track_id.in_(track_ids),
            TrackIdentifier.identifier_type == "musicbrainz_recording_id",
        )
    ).all()
    mb_by_track = {tid: val for tid, val in mb_rows}

    music_by_track = musical_attributes_for(session, track_ids)
    character_by_track = {tid: _music_character_for_attrs(music_by_track.get(tid, {})) for tid in track_ids}

    items = [_serialize(pt, isrc_by_track, mb_by_track, music_by_track, character_by_track) for pt in rows]

    return TracksPage(
        items=items,
        page=params.page,
        page_size=params.page_size,
        total=total,
        total_pages=total_pages,
        sort=params.sort,
        provider=params.provider,
        has_isrc=params.has_isrc,
        search=params.search,
        bpm_min=params.bpm_min,
        bpm_max=params.bpm_max,
        musical_key=params.musical_key,
        camelot=params.camelot,
        mood=params.mood,
        vibe=params.vibe,
    )


def library_summary(session: Session) -> dict[str, Any]:
    """Trustworthy, non-technical counts derived purely from real data.

    ISRC counts are computed at the provider-occurrence level so they stay
    consistent with the ``has_isrc`` filter on ``/tracks``: a provider track is
    counted as having an ISRC when its canonical Track carries an isrc
    identifier.
    """
    canonical = session.scalar(select(func.count(Track.id))) or 0
    occurrences = session.scalar(select(func.count(ProviderTrack.id))) or 0

    isrc_track_ids = (
        select(TrackIdentifier.track_id)
        .where(TrackIdentifier.identifier_type == "isrc")
        .distinct()
    )
    with_isrc = (
        session.scalar(
            select(func.count(ProviderTrack.id)).where(
                ProviderTrack.track_id.in_(isrc_track_ids)
            )
        )
        or 0
    )

    # Per-provider occurrence counts (current reality: spotify only).
    provider_rows = session.execute(
        select(ProviderTrack.provider, func.count(ProviderTrack.id))
        .group_by(ProviderTrack.provider)
    ).all()
    providers = [
        {"provider": p, "occurrences": c} for p, c in provider_rows
    ]

    return {
        "canonical_tracks": canonical,
        "provider_occurrences": occurrences,
        "with_isrc": with_isrc,
        "missing_isrc": occurrences - with_isrc,
        "providers": providers,
    }


def track_detail(session: Session, *, track_id: int) -> dict[str, Any]:
    track = session.get(Track, track_id)
    if track is None:
        raise ValueError("track not found")

    pts = (
        session.execute(
            select(ProviderTrack).where(ProviderTrack.track_id == track_id)
        )
        .scalars()
        .all()
    )
    identifiers = (
        session.execute(
            select(TrackIdentifier).where(TrackIdentifier.track_id == track_id)
        )
        .scalars()
        .all()
    )
    resolutions = (
        session.execute(
            select(TrackIdentityResolution).where(TrackIdentityResolution.track_id == track_id)
        )
        .scalars()
        .all()
    )
    attributes = (
        session.execute(
            select(TrackAttribute)
            .where(TrackAttribute.track_id == track_id)
            .order_by(TrackAttribute.attribute_type, TrackAttribute.observed_at.desc())
        )
        .scalars()
        .all()
    )

    def _fmt_ident(i: TrackIdentifier) -> dict[str, str]:
        return {"type": i.identifier_type, "value": i.identifier_value}

    def _fmt_res(r: TrackIdentityResolution) -> dict[str, Any]:
        return {
            "id": r.id,
            "query_type": r.query_type,
            "query_value": r.query_value,
            "status": r.status,
            "matched_identifier": r.matched_identifier,
            "confidence": r.confidence,
            "metadata": _safe_loads(r.metadata_json),
            "resolved_at": _iso(r.resolved_at),
            "resolver_version": r.resolver_version,
        }

    def _fmt_attr(r: TrackAttribute) -> dict[str, Any]:
        return {
            "attribute_type": r.attribute_type,
            "value": _safe_loads(r.value_json),
            "source_type": r.source_type,
            "source_name": r.source_name,
            "confidence": r.confidence,
            "analysis_version": r.analysis_version,
            "observed_at": _iso(r.observed_at),
            "is_current": bool(r.is_current),
        }

    preferred = musical_attributes_for(session, [track_id]).get(track_id, {})
    music_character = _music_character_for_attrs(preferred)

    return {
        "track_id": track.id,
        "canonical_title": track.canonical_title,
        "duration_ms": track.duration_ms,
        "music_character": music_character,
        "provider_occurrences": [
            {
                "id": pt.id,
                "provider": pt.provider,
                "provider_track_id": pt.provider_track_id,
                "title": pt.raw_title,
                "duration_ms": pt.duration_ms,
                "provider_uri": pt.provider_uri,
                "provider_url": pt.provider_url,
                "saved_at": _iso(pt.saved_at),
                "imported_at": _iso(pt.imported_at),
            }
            for pt in pts
        ],
        "identifiers": [_fmt_ident(i) for i in identifiers],
        "identity_resolutions": [_fmt_res(r) for r in resolutions],
        "musical_attributes": preferred,
        "musical_attribute_history": [_fmt_attr(r) for r in attributes],
    }


def _safe_loads(text: Optional[str]) -> Optional[Any]:
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


# ---- musical attributes ----------------------------------------------------

_MUSIC_ATTRIBUTE_TYPES = (
    "tempo_bpm",
    "musical_key",
    "time_signature",
    "energy",
    "danceability",
    "valence",
    "acousticness",
    "instrumentalness",
    "liveness",
    "loudness_db",
    "speechiness",
)


def _preferred_attr(rows: list[TrackAttribute], attribute_type: str) -> Optional[dict[str, Any]]:
    """Pick the preferred attribute row of ``attribute_type`` from ``rows``.

    Preference order:
      1. PREFERRED_MUSIC_SOURCES, in order.
      2. Newest observed_at (fallback).
    Returns None if no row matches.
    """
    candidates = [r for r in rows if r.attribute_type == attribute_type]
    if not candidates:
        return None
    for src in PREFERRED_MUSIC_SOURCES:
        for r in candidates:
            if r.source_name == src:
                return _format_attr(r)
    newest = max(candidates, key=lambda r: r.observed_at or r.created_at)
    return _format_attr(newest)


def _format_attr(row: TrackAttribute) -> dict[str, Any]:
    return {
        "value": _safe_loads(row.value_json),
        "source": row.source_name,
        "confidence": row.confidence,
        "analysis_version": row.analysis_version,
        "observed_at": _iso(row.observed_at),
    }


def _camelot_derived_from_key(musical_key_attr: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Derive Camelot from preferred musical_key attribute."""
    if not musical_key_attr or not musical_key_attr.get("value"):
        return None
    try:
        from app.music_theory.camelot import canonical_to_camelot
        from app.music_theory.keys import normalize_key

        val = musical_key_attr["value"]
        ck = normalize_key(val)
        cam = canonical_to_camelot(ck)
        if not cam:
            return None
        return {
            "value": cam.code,
            "source": "aion_music_theory",
            "confidence": None,
            "analysis_version": "m5-camelot-v1",
            "observed_at": musical_key_attr.get("observed_at"),
            "derived_from": "musical_key",
            "number": cam.number,
            "letter": cam.letter,
            "open_key": cam.open_key,
        }
    except Exception:
        return None


def musical_attributes_for(
    session: Session, track_ids: list[int]
) -> dict[int, dict[str, Optional[dict[str, Any]]]]:
    """Bulk-load musical attributes for the given track IDs.

    Returns a dict keyed by track_id. Each value is a dict of
    ``{attribute_type: preferred_row_or_None}`` for all types in
    ``_MUSIC_ATTRIBUTE_TYPES`` plus derived ``camelot``.
    """
    if not track_ids:
        return {}
    rows = (
        session.execute(
            select(TrackAttribute).where(
                TrackAttribute.track_id.in_(track_ids),
                TrackAttribute.attribute_type.in_(_MUSIC_ATTRIBUTE_TYPES),
            )
        )
        .scalars()
        .all()
    )
    by_track: dict[int, list[TrackAttribute]] = {}
    for r in rows:
        by_track.setdefault(r.track_id, []).append(r)

    out: dict[int, dict[str, Optional[dict[str, Any]]]] = {}
    for tid in track_ids:
        attrs = by_track.get(tid, [])
        base = {attr: _preferred_attr(attrs, attr) for attr in _MUSIC_ATTRIBUTE_TYPES}
        base["camelot"] = _camelot_derived_from_key(base.get("musical_key"))
        out[tid] = base
    return out


def _music_character_for_attrs(music_attrs: dict[str, Optional[dict[str, Any]]]) -> Optional[dict[str, Any]]:
    """Derive character from preferred musical attributes."""
    # Check if we have any audio to derive from
    has_any = any(music_attrs.get(k) is not None for k in ("tempo_bpm", "energy", "danceability", "valence", "acousticness"))
    if not has_any:
        return None
    try:
        from app.music_character.features import build_features
        from app.music_character import infer_character

        # Build flat dict of values for build_features
        flat: dict[str, Any] = {}
        for k in ("tempo_bpm", "energy", "danceability", "valence", "acousticness", "instrumentalness", "liveness", "loudness_db", "speechiness"):
            attr = music_attrs.get(k)
            if attr and attr.get("value") is not None:
                flat[k] = {"value": attr["value"]}
            else:
                flat[k] = None
        # mode from musical_key
        mk = music_attrs.get("musical_key")
        if mk and isinstance(mk.get("value"), dict):
            flat["musical_key"] = mk
        # camelot pass through
        if music_attrs.get("camelot"):
            flat["camelot"] = music_attrs["camelot"]
        features = build_features(flat)
        profile = infer_character(features)
        # If no meaningful scores (all ~0), treat as not derived?
        # Check if at least one mood/vibe > 0.15
        if not profile.moods and not profile.vibes:
            return None
        return profile.to_dict(min_score=0.15)
    except Exception:
        return None


def music_character_for(session: Session, track_ids: list[int]) -> dict[int, Optional[dict[str, Any]]]:
    attrs_map = musical_attributes_for(session, track_ids)
    out: dict[int, Optional[dict[str, Any]]] = {}
    for tid, attrs in attrs_map.items():
        out[tid] = _music_character_for_attrs(attrs)
    return out


def _filter_tracks_by_music(
    stmt,
    *,
    bpm_min: Optional[int],
    bpm_max: Optional[int],
    musical_key: Optional[str],
    camelot: Optional[str] = None,
):
    """Apply BPM/key filters to a ProviderTrack select statement.

    Filters by joining against TrackAttribute rows. Both BPM (numeric) and
    musical_key (string match against the canonical ``display`` field) are
    applied with IN-subqueries so they don't require expensive JSON ops on
    every ProviderTrack row.
    """
    from sqlalchemy import Float, cast

    if bpm_min is not None or bpm_max is not None:
        bpm_real = cast(TrackAttribute.value_json, Float)
        subq = select(TrackAttribute.track_id).where(
            TrackAttribute.attribute_type == "tempo_bpm"
        )
        if bpm_min is not None:
            subq = subq.where(bpm_real >= bpm_min)
        if bpm_max is not None:
            subq = subq.where(bpm_real <= bpm_max)
        stmt = stmt.where(ProviderTrack.track_id.in_(subq))

    if musical_key:
        # SQLite LIKE: %/_ are wildcards. Match on canonical display
        # substring. value_json for musical_key is a JSON object with
        # ``"display": "<key>"``. We surround the key with quotes so it can
        # never match e.g. "F# minor7" when filtering for "F# minor".
        # We pre-escape the SQL LIKE wildcards so user input cannot
        # unexpectedly match anything (e.g. "%minor%" would match anything
        # containing "minor").
        escaped_key = (
            musical_key.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        like = f'%\\"display\\": \\"{escaped_key}\\"%'
        subq = select(TrackAttribute.track_id).where(
            TrackAttribute.attribute_type == "musical_key",
            TrackAttribute.value_json.like(like, escape="\\"),
        )
        stmt = stmt.where(ProviderTrack.track_id.in_(subq))

    if camelot:
        # Camelot is derived from musical_key; filter by mapping back to canonical display
        try:
            from app.music_theory.camelot import camelot_to_canonical

            canonical = camelot_to_canonical(camelot.strip())
            if canonical:
                escaped = (
                    canonical.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                like = f'%\\"display\\": \\"{escaped}\\"%'
                subq = select(TrackAttribute.track_id).where(
                    TrackAttribute.attribute_type == "musical_key",
                    TrackAttribute.value_json.like(like, escape="\\"),
                )
                stmt = stmt.where(ProviderTrack.track_id.in_(subq))
            else:
                # Invalid camelot => no results
                stmt = stmt.where(ProviderTrack.track_id.in_(select(TrackAttribute.track_id).where(False)))
        except Exception:
            pass

    return stmt


def _bpm_for_track(session: Session, track_id: int) -> Optional[float]:
    row = session.execute(
        select(TrackAttribute.value_json).where(
            TrackAttribute.track_id == track_id,
            TrackAttribute.attribute_type == "tempo_bpm",
        )
    ).scalars().first()
    if not row:
        return None
    try:
        v = json.loads(row)
        return float(v)
    except Exception:
        return None


def track_compatibility(session: Session, *, track_id: int, other_track_id: int) -> dict[str, Any]:
    track = session.get(Track, track_id)
    other = session.get(Track, other_track_id)
    if track is None or other is None:
        raise ValueError("track not found")
    attrs = musical_attributes_for(session, [track_id, other_track_id])
    a = attrs.get(track_id, {})
    b = attrs.get(other_track_id, {})
    a_cam = (a.get("camelot") or {}).get("value")
    b_cam = (b.get("camelot") or {}).get("value")
    from app.music_theory.compatibility import compatibility, is_half_or_double_bpm

    comp = compatibility(a_cam, b_cam)
    bpm_a = _bpm_for_track(session, track_id)
    bpm_b = _bpm_for_track(session, other_track_id)
    half_double = is_half_or_double_bpm(bpm_a, bpm_b)
    return {
        "from_track_id": track_id,
        "to_track_id": other_track_id,
        "from_key": a.get("musical_key", {}).get("value") if a.get("musical_key") else None,
        "to_key": b.get("musical_key", {}).get("value") if b.get("musical_key") else None,
        "from_camelot": a_cam,
        "to_camelot": b_cam,
        "score": comp.score,
        "relationship": comp.relationship,
        "from_bpm": bpm_a,
        "to_bpm": bpm_b,
        "bpm_relationship": half_double,
    }


def compatible_tracks(session: Session, *, track_id: int, limit: int = 10) -> list[dict[str, Any]]:
    base = session.get(Track, track_id)
    if base is None:
        raise ValueError("track not found")
    # Candidate pool: all tracks with musical_key
    candidate_ids = session.execute(
        select(TrackAttribute.track_id).where(TrackAttribute.attribute_type == "musical_key").distinct()
    ).scalars().all()
    candidate_ids = [cid for cid in candidate_ids if cid != track_id]
    if not candidate_ids:
        return []
    # Limit candidate pool size for performance (cap 500)
    candidate_ids = candidate_ids[:500]
    results = []
    for cid in candidate_ids:
        comp = track_compatibility(session, track_id=track_id, other_track_id=cid)
        if comp["score"] > 0:
            results.append(comp)
    # Sort by score desc, then by track_id for stability
    results.sort(key=lambda r: (-r["score"], r["to_track_id"]))
    return results[:limit]
