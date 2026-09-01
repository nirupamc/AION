"""Evaluation runner for M3 enrichment sources.

Does NOT write production TrackAttribute rows. Results are returned as
structured dicts and can be persisted to JSON/CSV for the M3 report.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.enrichment import EnrichmentAggregate, EnrichmentQuery, EnrichmentResult, EnrichmentSource
from app.models import Track, TrackIdentifier

log = logging.getLogger(__name__)


def load_sample(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"sample file not found: {path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    tracks = data.get("tracks") if isinstance(data, dict) else data
    if not isinstance(tracks, list):
        raise ValueError("sample JSON must have a 'tracks' list")
    return tracks


def queries_from_sample(session: Session, sample_tracks: list[dict[str, Any]]) -> list[EnrichmentQuery]:
    """Convert persisted sample track dicts into EnrichmentQuery objects.

    For ISRCs not stored in the sample JSON, look them up from the live DB
    so sources that require ISRC can still be evaluated.
    """
    out: list[EnrichmentQuery] = []
    for item in sample_tracks:
        track = session.get(Track, item["track_id"])
        if track is None:
            continue
        isrc = item.get("isrc")
        mb = item.get("musicbrainz_recording_id")
        if not isrc:
            ident = (
                session.execute(
                    select(TrackIdentifier.identifier_value).where(
                        TrackIdentifier.track_id == track.id,
                        TrackIdentifier.identifier_type == "isrc",
                    )
                )
                .scalars()
                .first()
            )
            isrc = ident or None
        out.append(
            EnrichmentQuery(
                track_id=track.id,
                isrc=isrc,
                musicbrainz_recording_id=mb,
                provider="spotify",
                provider_track_id=item.get("spotify_id"),
                title=item.get("title"),
                artists=[item.get("artist")] if item.get("artist") else [],
                album=item.get("album"),
                duration_ms=item.get("duration_ms"),
            )
        )
    return out


async def _lookup_one(source: EnrichmentSource, query: EnrichmentQuery) -> EnrichmentResult:
    t0 = time.monotonic()
    try:
        result = await source.lookup(query)
        return replace(result, latency_ms=round((time.monotonic() - t0) * 1000, 2))
    except Exception as exc:
        log.error("enrichment source error source=%s track_id=%s err=%s", source.name, query.track_id, exc)
        return replace(
            EnrichmentResult(
                source=source.name,
                status="error",
                error=str(exc),
            ),
            latency_ms=round((time.monotonic() - t0) * 1000, 2),
        )


async def evaluate_sources(
    sources: list[EnrichmentSource],
    queries: list[EnrichmentQuery],
    *,
    limit: Optional[int] = None,
) -> dict[str, Any]:
    if limit is not None and limit > 0:
        queries = queries[:limit]

    rows: list[dict[str, Any]] = []
    aggregates: dict[str, EnrichmentAggregate] = {s.name: EnrichmentAggregate(source=s.name) for s in sources}

    for query in queries:
        for source in sources:
            result = await _lookup_one(source, query)
            agg = aggregates[source.name]
            agg.queried += 1
            if result.status == "matched":
                agg.matched += 1
            elif result.status == "no_match":
                agg.no_match += 1
            elif result.status == "ambiguous":
                agg.ambiguous += 1
            elif result.status == "error":
                agg.error += 1
            elif result.status == "deferred":
                agg.deferred += 1
            if result.tempo_bpm is not None:
                agg.bpm_present += 1
            if result.musical_key is not None:
                agg.key_present += 1
            if result.tempo_bpm is not None and result.musical_key is not None:
                agg.both_present += 1
            if result.latency_ms is not None:
                agg.latencies.append(result.latency_ms)

            rows.append({
                "track_id": query.track_id,
                "isrc": query.isrc,
                "musicbrainz_recording_id": query.musicbrainz_recording_id,
                "spotify_id": query.provider_track_id,
                "source": source.name,
                "status": result.status,
                "tempo_bpm": result.tempo_bpm,
                "musical_key": result.musical_key,
                "confidence": result.confidence,
                "source_identifier": result.source_identifier,
                "match_evidence": result.match_evidence,
                "latency_ms": result.latency_ms,
                "error": result.error,
                "error_type": result.error_type,
                "http_status": result.http_status,
            })

    return {
        "sources": [aggregates[s.name].as_dict() for s in sources],
        "results": rows,
    }


def write_report(artifacts_dir: Path, payload: dict[str, Any], sample_meta: dict[str, Any], filename: str = "m3_enrichment_results.json") -> Path:
    artifacts_dir = artifacts_dir.resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out_path = artifacts_dir / filename
    out_path.write_text(
        json.dumps({"sample": sample_meta, "evaluation": payload}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise IOError(f"report write failed: {out_path}")
    return out_path
