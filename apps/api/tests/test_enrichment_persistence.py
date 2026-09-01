"""Tests for production enrichment persistence to TrackAttribute."""
from __future__ import annotations

import json

import pytest

from app.enrichment import EnrichmentResult
from app.enrichment.persistence import (
    already_enriched,
    persist_enrichment,
)
from app.models import Track, TrackAttribute


def _matched(bpm=120.0, key="A minor", conf=0.9):
    return EnrichmentResult(
        source="getsongbpm",
        status="matched",
        tempo_bpm=bpm,
        musical_key=key,
        confidence=conf,
        source_identifier="abc",
        match_evidence={"match_score": 0.95, "match_method": "title+artist"},
    )


def test_persist_inserts_bpm_and_key(session):
    track = Track(canonical_title="T")
    session.add(track)
    session.flush()

    stats = persist_enrichment(
        session,
        track_id=track.id,
        result=_matched(),
        source_type="catalog_api",
        source_name="getsongbpm",
        analysis_version="m4b-getsongbpm-v1",
    )
    session.commit()
    assert stats.inserted == 2
    assert stats.updated == 0

    rows = (
        session.query(TrackAttribute)
        .filter(TrackAttribute.track_id == track.id)
        .all()
    )
    types = {r.attribute_type: json.loads(r.value_json) for r in rows}
    assert types["tempo_bpm"] == pytest.approx(120.0, abs=0.001)
    assert types["musical_key"] == {"tonic": "A", "mode": "minor", "display": "A minor"}
    # Both should be marked current since nothing else exists.
    assert all(r.is_current for r in rows)


def test_persist_upserts_existing_rows(session):
    track = Track(canonical_title="T")
    session.add(track)
    session.flush()

    persist_enrichment(
        session,
        track_id=track.id,
        result=_matched(bpm=120.0, key="A minor"),
        source_type="catalog_api",
        source_name="getsongbpm",
        analysis_version="m4b-getsongbpm-v1",
    )
    session.commit()

    # Second run with a slightly different BPM/key — should UPDATE, not duplicate.
    stats = persist_enrichment(
        session,
        track_id=track.id,
        result=_matched(bpm=121.5, key="A minor"),
        source_type="catalog_api",
        source_name="getsongbpm",
        analysis_version="m4b-getsongbpm-v1",
    )
    session.commit()

    assert stats.inserted == 0
    assert stats.updated == 2

    rows = (
        session.query(TrackAttribute)
        .filter(TrackAttribute.track_id == track.id)
        .all()
    )
    # Still exactly 2 rows: no duplicates.
    assert len(rows) == 2
    bpm = next(r for r in rows if r.attribute_type == "tempo_bpm")
    assert json.loads(bpm.value_json) == pytest.approx(121.5, abs=0.001)


def test_persist_isolates_sources(session):
    """Soundcharts BPM must coexist with GetSongBPM BPM."""
    track = Track(canonical_title="T")
    session.add(track)
    session.flush()

    persist_enrichment(
        session,
        track_id=track.id,
        result=_matched(bpm=120.0),
        source_type="catalog_api",
        source_name="getsongbpm",
        analysis_version="m4b-getsongbpm-v1",
    )
    session.commit()

    stats = persist_enrichment(
        session,
        track_id=track.id,
        result=_matched(bpm=121.0),
        source_type="catalog_api",
        source_name="soundcharts",
        analysis_version="m4a-soundcharts-v1",
    )
    session.commit()
    assert stats.inserted == 2  # two new rows from a different source

    rows = (
        session.query(TrackAttribute)
        .filter(TrackAttribute.track_id == track.id)
        .all()
    )
    by_src = {(r.attribute_type, r.source_name) for r in rows}
    assert ("tempo_bpm", "getsongbpm") in by_src
    assert ("tempo_bpm", "soundcharts") in by_src


def test_persist_skips_non_matched_result(session):
    track = Track(canonical_title="T")
    session.add(track)
    session.flush()

    res = EnrichmentResult(
        source="getsongbpm",
        status="no_match",
    )
    stats = persist_enrichment(
        session,
        track_id=track.id,
        result=res,
        source_type="catalog_api",
        source_name="getsongbpm",
        analysis_version="m4b-getsongbpm-v1",
    )
    assert stats.skipped == 1
    assert stats.inserted == 0


def test_persist_rejects_invalid_bpm(session):
    track = Track(canonical_title="T")
    session.add(track)
    session.flush()

    res = EnrichmentResult(
        source="getsongbpm",
        status="matched",
        tempo_bpm=0,  # invalid; _encode_bpm returns None
        musical_key=None,
        confidence=0.9,
    )
    stats = persist_enrichment(
        session,
        track_id=track.id,
        result=res,
        source_type="catalog_api",
        source_name="getsongbpm",
        analysis_version="m4b-getsongbpm-v1",
    )
    # BPM encoder rejects; no valid attribute to write.
    assert stats.inserted == 0
    assert (
        session.query(TrackAttribute)
        .filter(TrackAttribute.track_id == track.id)
        .count()
        == 0
    )


def test_persist_rejects_garbage_key(session):
    track = Track(canonical_title="T")
    session.add(track)
    session.flush()

    res = EnrichmentResult(
        source="getsongbpm",
        status="matched",
        tempo_bpm=120.0,
        musical_key="Z major",  # not a valid tonic
        confidence=0.9,
    )
    stats = persist_enrichment(
        session,
        track_id=track.id,
        result=res,
        source_type="catalog_api",
        source_name="getsongbpm",
        analysis_version="m4b-getsongbpm-v1",
    )
    session.commit()
    # Only BPM should be written; key should be silently skipped.
    rows = (
        session.query(TrackAttribute)
        .filter(TrackAttribute.track_id == track.id)
        .all()
    )
    types = {r.attribute_type for r in rows}
    assert "tempo_bpm" in types
    assert "musical_key" not in types


def test_already_enriched_returns_true_after_run(session):
    track = Track(canonical_title="T")
    session.add(track)
    session.flush()

    persist_enrichment(
        session,
        track_id=track.id,
        result=_matched(),
        source_type="catalog_api",
        source_name="getsongbpm",
        analysis_version="m4b-getsongbpm-v1",
    )
    session.commit()

    assert already_enriched(
        session,
        track_id=track.id,
        source_name="getsongbpm",
        analysis_version="m4b-getsongbpm-v1",
    ) is True


def test_already_enriched_false_for_different_version(session):
    track = Track(canonical_title="T")
    session.add(track)
    session.flush()

    persist_enrichment(
        session,
        track_id=track.id,
        result=_matched(),
        source_type="catalog_api",
        source_name="getsongbpm",
        analysis_version="v1",
    )
    session.commit()

    assert already_enriched(
        session,
        track_id=track.id,
        source_name="getsongbpm",
        analysis_version="v2",
    ) is False


def test_persist_does_not_overwrite_current_when_other_source_exists(session):
    """When another source already has is_current=True, the new row stays not-current."""
    track = Track(canonical_title="T")
    session.add(track)
    session.flush()

    # Establish a "current" BPM from one source.
    persist_enrichment(
        session,
        track_id=track.id,
        result=_matched(bpm=120.0),
        source_type="catalog_api",
        source_name="essentia",
        analysis_version="v1",
    )
    session.commit()

    # Now persist from a different source.
    stats = persist_enrichment(
        session,
        track_id=track.id,
        result=_matched(bpm=121.0),
        source_type="catalog_api",
        source_name="getsongbpm",
        analysis_version="m4b-getsongbpm-v1",
    )
    session.commit()

    gsb_rows = (
        session.query(TrackAttribute)
        .filter(
            TrackAttribute.track_id == track.id,
            TrackAttribute.source_name == "getsongbpm",
        )
        .all()
    )
    # getsongbpm wrote both BPM and key — expect 2 rows total.
    assert len(gsb_rows) == 2
    # None of them should be marked current — the essentia row keeps that flag.
    assert all(r.is_current is False for r in gsb_rows)
    assert stats.inserted == 2