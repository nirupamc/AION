"""M7 library analytics tests."""
import json
import pytest
from app.models import Track, ProviderTrack, TrackAttribute
from app.library import ListParams
from app.library_analytics.service import get_library_dna, get_bpm_distribution, get_energy_distribution, get_scatter_data
from app.enrichment import EnrichmentResult
from app.enrichment.persistence import persist_enrichment

def _seed_with_attrs(session, n=3):
    tracks=[]
    for i in range(n):
        t=Track(canonical_title=f"T{i}")
        session.add(t); session.flush()
        pt=ProviderTrack(track_id=t.id, provider="spotify", provider_track_id=f"sp-{i}", raw_title=f"T{i}", artist_display="A", raw_metadata='{"artists":[{"name":"A"}]}')
        session.add(pt)
        tracks.append(t)
    session.flush()
    return tracks

def _enrich(track, bpm, key, energy=0.8, valence=0.5):
    return EnrichmentResult(source="soundcharts", status="matched", tempo_bpm=bpm, musical_key=key, time_signature=4, energy=energy, danceability=0.6, valence=valence, acousticness=0.2, instrumentalness=0.0, liveness=0.1, loudness_db=-6, speechiness=0.05, source_identifier="u")

def test_dna_empty_library(session):
    dna=get_library_dna(session, ListParams())
    assert dna["total_tracks"]==0
    assert dna["enriched_tracks"]==0
    assert dna["tempo"]["average"] is None

def test_dna_enriched_only_calculation(session):
    tracks=_seed_with_attrs(session, 2)
    # enrich only first
    persist_enrichment(session, track_id=tracks[0].id, result=_enrich(tracks[0], 120, "C major", energy=0.8), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    persist_enrichment(session, track_id=tracks[1].id, result=_enrich(tracks[1], 140, "A minor", energy=0.9), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    dna=get_library_dna(session, ListParams())
    assert dna["total_tracks"]==2
    assert dna["enriched_tracks"]==2
    assert dna["tempo"]["average"] == pytest.approx(130)
    assert dna["tempo"]["median"] == pytest.approx(130)

def test_dna_partial_enrichment(session):
    tracks=_seed_with_attrs(session, 3)
    persist_enrichment(session, track_id=tracks[0].id, result=_enrich(tracks[0], 100, "C major"), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    dna=get_library_dna(session, ListParams())
    assert dna["total_tracks"]==3
    assert dna["enriched_tracks"]==1
    assert dna["enrichment_percentage"] == pytest.approx(33.3, abs=0.1)

def test_bpm_histogram(session):
    tracks=_seed_with_attrs(session, 3)
    for t,bpm in zip(tracks, [120,122,135]):
        persist_enrichment(session, track_id=t.id, result=_enrich(t,bpm,"C major"), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    hist=get_bpm_distribution(session, ListParams())
    buckets=hist["buckets"]
    assert any(b["min"]==120 and b["count"]==2 for b in buckets)
    assert any(b["min"]==135 and b["count"]==1 for b in buckets)

def test_energy_buckets(session):
    tracks=_seed_with_attrs(session, 2)
    persist_enrichment(session, track_id=tracks[0].id, result=_enrich(tracks[0],120,"C major", energy=0.15), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    persist_enrichment(session, track_id=tracks[1].id, result=_enrich(tracks[1],120,"C major", energy=0.85), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    hist=get_energy_distribution(session, ListParams())
    assert hist["buckets"][1]["count"]==1  # 0.1-0.2
    assert hist["buckets"][8]["count"]==1  # 0.8-0.9

def test_camelot_counts(session):
    tracks=_seed_with_attrs(session, 2)
    persist_enrichment(session, track_id=tracks[0].id, result=_enrich(tracks[0],120,"C major"), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    persist_enrichment(session, track_id=tracks[1].id, result=_enrich(tracks[1],120,"C major"), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    dna=get_library_dna(session, ListParams())
    assert any(c["label"]=="8B" for c in dna["camelot_distribution"])

def test_mood_vibe_distribution(session):
    tracks=_seed_with_attrs(session, 2)
    persist_enrichment(session, track_id=tracks[0].id, result=_enrich(tracks[0],140,"B minor", energy=0.95, valence=0.2), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    persist_enrichment(session, track_id=tracks[1].id, result=_enrich(tracks[1],70,"C major", energy=0.2, valence=0.8), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    dna=get_library_dna(session, ListParams())
    assert len(dna["mood_distribution"])>0
    assert len(dna["vibe_distribution"])>0
    assert len(dna["set_roles"])>0

def test_filter_aware_analytics(session):
    tracks=_seed_with_attrs(session, 2)
    persist_enrichment(session, track_id=tracks[0].id, result=_enrich(tracks[0],120,"C major", energy=0.9), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    persist_enrichment(session, track_id=tracks[1].id, result=_enrich(tracks[1],140,"A minor", energy=0.2), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    dna_all=get_library_dna(session, ListParams())
    dna_filtered=get_library_dna(session, ListParams(bpm_min=130))
    assert dna_filtered["filtered_tracks"] < dna_all["filtered_tracks"] or dna_filtered["tempo"]["average"] != dna_all["tempo"]["average"]

def test_malformed_filters_not_crash(session):
    tracks=_seed_with_attrs(session, 1)
    persist_enrichment(session, track_id=tracks[0].id, result=_enrich(tracks[0],120,"C major"), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    # invalid camelot should return 0 filtered not error
    dna=get_library_dna(session, ListParams(camelot="ZZZ"))
    assert dna["filtered_tracks"]==0

def test_scatter_data(session):
    tracks=_seed_with_attrs(session, 2)
    persist_enrichment(session, track_id=tracks[0].id, result=_enrich(tracks[0],120,"C major", energy=0.5), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    persist_enrichment(session, track_id=tracks[1].id, result=_enrich(tracks[1],130,"A minor", energy=0.7), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    sc=get_scatter_data(session, ListParams(), limit=500)
    assert sc["count"]==2
    assert all("bpm" in p and "energy" in p for p in sc["points"])

def test_deterministic_output(session):
    tracks=_seed_with_attrs(session, 1)
    persist_enrichment(session, track_id=tracks[0].id, result=_enrich(tracks[0],123,"C major"), source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    d1=get_library_dna(session, ListParams())
    d2=get_library_dna(session, ListParams())
    assert d1==d2
