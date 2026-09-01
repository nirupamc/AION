"""M4C regression: Soundcharts production ingestion, preference, coverage, idempotency."""
from __future__ import annotations

import json

import pytest

from app.enrichment import EnrichmentResult
from app.enrichment.persistence import persist_enrichment, already_enriched
from app.enrichment.sources.soundcharts import SoundchartsEnrichmentSource
from app.library import musical_attributes_for, PREFERRED_MUSIC_SOURCES
from app.models import Track, TrackAttribute


def _matched_soundcharts(bpm=120.0, key="A minor", extra=None):
    # helper to build EnrichmentResult with full audio fields
    base = dict(
        source="soundcharts",
        status="matched",
        tempo_bpm=bpm,
        musical_key=key,
        time_signature=4,
        energy=0.8,
        danceability=0.6,
        valence=0.5,
        acousticness=0.1,
        instrumentalness=0.0,
        liveness=0.2,
        loudness_db=-6.0,
        speechiness=0.05,
        confidence=None,
        source_identifier="sc-uuid",
        match_evidence={},
    )
    if extra:
        base.update(extra)
    return EnrichmentResult(**base)


def test_nested_audio_fields_persisted(session):
    track = Track(canonical_title="T")
    session.add(track)
    session.flush()
    result = _matched_soundcharts()
    stats = persist_enrichment(session, track_id=track.id, result=result, source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    assert stats.inserted == 11
    rows = session.query(TrackAttribute).filter(TrackAttribute.track_id == track.id).all()
    types = {r.attribute_type for r in rows}
    assert types == {"tempo_bpm","musical_key","time_signature","energy","danceability","valence","acousticness","instrumentalness","liveness","loudness_db","speechiness"}
    # check encoding
    bpm = next(r for r in rows if r.attribute_type == "tempo_bpm")
    assert json.loads(bpm.value_json) == 120.0
    energy = next(r for r in rows if r.attribute_type == "energy")
    assert json.loads(energy.value_json) == 0.8


def test_key_mode_normalization_via_soundcharts(session, monkeypatch):
    import httpx, respx
    async def _fake_token(*a, **kw):
        return {"access_token": "tok", "token_type":"bearer","expires_in":3600}
    monkeypatch.setattr("app.enrichment.sources.soundcharts._get_soundcharts_token", _fake_token)
    # key 6, mode 0 = F# minor per PITCH_CLASSES
    with respx.mock(base_url="https://customer.api.soundcharts.com") as router:
        router.get("/api/v2.25/song/by-isrc/US123").mock(return_value=httpx.Response(200, json={
            "type":"song","object":{"uuid":"u","audio":{"tempo":120,"key":6,"mode":0,"timeSignature":4}},"errors":[]
        }))
        import asyncio
        src = SoundchartsEnrichmentSource(client_id="cid", client_secret="s")
        res = asyncio.run(src.lookup(__import__("app.enrichment", fromlist=["EnrichmentQuery"]).EnrichmentQuery(track_id=1, isrc="US123")))
        assert res.musical_key == "F# minor"
        assert res.tempo_bpm == 120.0
        assert res.time_signature == 4


def test_optional_audio_fields_missing_gracefully(session, monkeypatch):
    import httpx, respx, asyncio
    async def _fake_token(*a, **kw):
        return {"access_token": "tok", "token_type":"bearer","expires_in":3600}
    monkeypatch.setattr("app.enrichment.sources.soundcharts._get_soundcharts_token", _fake_token)
    with respx.mock(base_url="https://customer.api.soundcharts.com") as router:
        router.get("/api/v2.25/song/by-isrc/US456").mock(return_value=httpx.Response(200, json={
            "type":"song","object":{"uuid":"u2","audio":{"tempo":100,"key":0,"mode":1}},"errors":[]
        }))
        src = SoundchartsEnrichmentSource(client_id="cid", client_secret="s")
        res = asyncio.run(src.lookup(__import__("app.enrichment", fromlist=["EnrichmentQuery"]).EnrichmentQuery(track_id=1, isrc="US456")))
        assert res.tempo_bpm == 100.0
        assert res.musical_key == "C major"
        # optional fields absent => None, not error
        assert res.energy is None
        assert res.time_signature is None


def test_persistence_coexistence_with_getsongbpm(session):
    track = Track(canonical_title="T")
    session.add(track); session.flush()
    sc = _matched_soundcharts(bpm=120.0, key="A minor")
    gsb = EnrichmentResult(source="getsongbpm", status="matched", tempo_bpm=127.0, musical_key="C major", confidence=0.9, source_identifier="gsb")
    import json
    s1 = persist_enrichment(session, track_id=track.id, result=sc, source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    s2 = persist_enrichment(session, track_id=track.id, result=gsb, source_type="catalog_api", source_name="getsongbpm", analysis_version="m4b-getsongbpm-v1")
    session.commit()
    rows = session.query(TrackAttribute).filter(TrackAttribute.track_id==track.id).all()
    # 11 + 2 =13
    assert len(rows) == 13
    # ensure both sources present
    assert any(r.source_name=="soundcharts" for r in rows)
    assert any(r.source_name=="getsongbpm" for r in rows)


def test_preferred_source_selection_soundcharts_over_getsongbpm(session):
    assert PREFERRED_MUSIC_SOURCES[0] == "soundcharts"
    assert PREFERRED_MUSIC_SOURCES[1] == "getsongbpm"
    track = Track(canonical_title="T")
    session.add(track); session.flush()
    # add both
    persist_enrichment(session, track_id=track.id, result=_matched_soundcharts(bpm=100.0), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    persist_enrichment(session, track_id=track.id, result=EnrichmentResult(source="getsongbpm", status="matched", tempo_bpm=200.0, musical_key="C major", confidence=0.9, source_identifier="gsb"), source_type="catalog_api", source_name="getsongbpm", analysis_version="m4b-getsongbpm-v1")
    session.commit()
    out = musical_attributes_for(session, [track.id])
    assert out[track.id]["tempo_bpm"]["source"] == "soundcharts"
    assert out[track.id]["tempo_bpm"]["value"] == 100.0


def test_fallback_to_getsongbpm_when_soundcharts_missing(session):
    track = Track(canonical_title="T")
    session.add(track); session.flush()
    persist_enrichment(session, track_id=track.id, result=EnrichmentResult(source="getsongbpm", status="matched", tempo_bpm=111.0, musical_key="D major", confidence=0.8, source_identifier="gsb"), source_type="catalog_api", source_name="getsongbpm", analysis_version="m4b-getsongbpm-v1")
    session.commit()
    out = musical_attributes_for(session, [track.id])
    assert out[track.id]["tempo_bpm"]["source"] == "getsongbpm"
    assert out[track.id]["tempo_bpm"]["value"] == 111.0


def test_overall_vs_matched_coverage_metrics():
    from app.enrichment import EnrichmentAggregate
    agg = EnrichmentAggregate(source="soundcharts", queried=10, matched=4, bpm_present=4, key_present=4, both_present=4)
    d = agg.as_dict()
    assert d["overall_bpm_coverage"] == 0.4
    assert d["matched_bpm_coverage"] == 1.0
    assert d["overall_key_coverage"] == 0.4
    assert d["matched_key_coverage"] == 1.0
    # old fields remain for compat
    assert d["bpm_coverage"] == 1.0


def test_idempotent_rerun_does_not_duplicate(session):
    track = Track(canonical_title="T")
    session.add(track); session.flush()
    r = _matched_soundcharts(bpm=120.0)
    s1 = persist_enrichment(session, track_id=track.id, result=r, source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    assert s1.inserted == 11
    s2 = persist_enrichment(session, track_id=track.id, result=r, source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    assert s2.inserted == 0
    assert s2.updated == 11
    rows = session.query(TrackAttribute).filter(TrackAttribute.track_id==track.id).all()
    assert len(rows) == 11


def test_api_preferred_values_exposed(session):
    from app.library import list_tracks, ListParams
    from app.models import ProviderTrack
    t = Track(canonical_title="Song")
    session.add(t); session.flush()
    pt = ProviderTrack(track_id=t.id, provider="spotify", provider_track_id="sp-1", raw_title="Song", artist_display="A", duration_ms=200000, raw_metadata='{"artists":[{"name":"A"}]}')
    session.add(pt); session.flush()
    persist_enrichment(session, track_id=t.id, result=_matched_soundcharts(bpm=133.0, key="G major"), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    page = list_tracks(session, params=ListParams(page=1, page_size=50))
    item = next(i for i in page.items if i.track_id==t.id)
    assert item.musical_attributes["tempo_bpm"]["value"] == 133.0
    assert item.musical_attributes["energy"]["value"] == 0.8
    assert item.musical_attributes["musical_key"]["value"]["display"] == "G major"
