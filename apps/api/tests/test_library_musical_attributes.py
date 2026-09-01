"""Tests for the library API exposing musical attributes."""
from __future__ import annotations

import json

from app.library import (
    ListParams,
    list_tracks,
    musical_attributes_for,
    track_detail,
)
from app.models import (
    ProviderTrack,
    Track,
    TrackAttribute,
    TrackIdentifier,
)


def _seed_library(session):
    t1 = Track(canonical_title="Formation")
    t2 = Track(canonical_title="Your Skin")
    session.add_all([t1, t2])
    session.flush()
    session.add(
        ProviderTrack(
            track_id=t1.id,
            provider="spotify",
            provider_track_id="sp-1",
            raw_title="Formation",
            artist_display="Beyoncé",
            duration_ms=210000,
        )
    )
    session.add(
        ProviderTrack(
            track_id=t2.id,
            provider="spotify",
            provider_track_id="sp-2",
            raw_title="Your Skin",
            artist_display="Mia",
            duration_ms=180000,
        )
    )
    session.flush()
    return t1, t2


def test_list_tracks_exposes_musical_attributes(session):
    t1, t2 = _seed_library(session)
    session.add(
        TrackAttribute(
            track_id=t1.id,
            attribute_type="tempo_bpm",
            value_json=json.dumps(125.0),
            source_type="catalog_api",
            source_name="getsongbpm",
            confidence=0.9,
            analysis_version="m4b-getsongbpm-v1",
            is_current=True,
        )
    )
    session.add(
        TrackAttribute(
            track_id=t1.id,
            attribute_type="musical_key",
            value_json=json.dumps({"tonic": "E", "mode": "minor", "display": "E minor"}),
            source_type="catalog_api",
            source_name="getsongbpm",
            confidence=0.9,
            analysis_version="m4b-getsongbpm-v1",
            is_current=True,
        )
    )
    session.commit()

    page = list_tracks(session, params=ListParams(page=1, page_size=50))
    by_id = {item.track_id: item for item in page.items}
    assert by_id[t1.id].musical_attributes["tempo_bpm"] is not None
    assert by_id[t1.id].musical_attributes["musical_key"] is not None
    assert by_id[t2.id].musical_attributes["tempo_bpm"] is None
    assert by_id[t2.id].musical_attributes["musical_key"] is None


def test_track_detail_exposes_musical_attributes(session):
    t1, t2 = _seed_library(session)
    session.add(
        TrackAttribute(
            track_id=t1.id,
            attribute_type="tempo_bpm",
            value_json=json.dumps(125.0),
            source_type="catalog_api",
            source_name="getsongbpm",
            confidence=0.9,
            analysis_version="m4b-getsongbpm-v1",
            is_current=True,
        )
    )
    session.commit()

    detail = track_detail(session, track_id=t1.id)
    assert detail["musical_attributes"]["tempo_bpm"]["value"] == pytest.approx(125.0)
    assert detail["musical_attributes"]["tempo_bpm"]["source"] == "getsongbpm"
    assert "musical_attribute_history" in detail
    assert len(detail["musical_attribute_history"]) == 1


def test_list_tracks_filters_by_bpm(session):
    from app.library import ListParams as _P  # re-export to placate linters

    t1, t2 = _seed_library(session)
    session.add_all(
        [
            TrackAttribute(
                track_id=t1.id,
                attribute_type="tempo_bpm",
                value_json=json.dumps(125.0),
                source_type="catalog_api",
                source_name="getsongbpm",
                is_current=True,
            ),
            TrackAttribute(
                track_id=t2.id,
                attribute_type="tempo_bpm",
                value_json=json.dumps(98.0),
                source_type="catalog_api",
                source_name="getsongbpm",
                is_current=True,
            ),
        ]
    )
    session.commit()

    page = list_tracks(
        session, params=_P(page=1, page_size=50, bpm_min=100, bpm_max=200)
    )
    ids = {it.track_id for it in page.items}
    assert t1.id in ids
    assert t2.id not in ids


def test_list_tracks_filters_by_musical_key(session):
    t1, t2 = _seed_library(session)
    session.add_all(
        [
            TrackAttribute(
                track_id=t1.id,
                attribute_type="musical_key",
                value_json=json.dumps(
                    {"tonic": "F#", "mode": "minor", "display": "F# minor"}
                ),
                source_type="catalog_api",
                source_name="getsongbpm",
                is_current=True,
            ),
            TrackAttribute(
                track_id=t2.id,
                attribute_type="musical_key",
                value_json=json.dumps(
                    {"tonic": "C", "mode": "major", "display": "C major"}
                ),
                source_type="catalog_api",
                source_name="getsongbpm",
                is_current=True,
            ),
        ]
    )
    session.commit()

    page = list_tracks(
        session, params=ListParams(page=1, page_size=50, musical_key="F# minor")
    )
    ids = {it.track_id for it in page.items}
    assert t1.id in ids
    assert t2.id not in ids


def test_musical_attributes_for_returns_empty_dict_when_none(session):
    out = musical_attributes_for(session, [])
    assert out == {}


def test_musical_attributes_prefers_getsongbpm_over_soundcharts(session):
    t1, _ = _seed_library(session)
    session.add_all(
        [
            TrackAttribute(
                track_id=t1.id,
                attribute_type="tempo_bpm",
                value_json=json.dumps(125.0),
                source_type="catalog_api",
                source_name="soundcharts",
                confidence=0.95,
                is_current=True,
            ),
            TrackAttribute(
                track_id=t1.id,
                attribute_type="tempo_bpm",
                value_json=json.dumps(124.0),
                source_type="catalog_api",
                source_name="getsongbpm",
                confidence=0.80,
                is_current=False,
            ),
        ]
    )
    session.commit()
    out = musical_attributes_for(session, [t1.id])
    assert out[t1.id]["tempo_bpm"]["source"] == "getsongbpm"
    assert out[t1.id]["tempo_bpm"]["value"] == pytest.approx(124.0)


import pytest  # noqa: E402  (imported late for the assertions above)