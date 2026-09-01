"""Tests for the TrackAttribute provenance model."""

from __future__ import annotations

import json

from app.models import Track, TrackAttribute


def test_attribute_provenance_roundtrip(session):
    track = Track(canonical_title="T", duration_ms=200000)
    session.add(track)
    session.flush()

    obs = TrackAttribute(
        track_id=track.id,
        attribute_type="tempo_bpm",
        value_json=json.dumps(126.0),
        source_type="provider",
        source_name="soundcloud",
        confidence=0.70,
        analysis_version=None,
        is_current=False,
    )
    session.add(obs)
    session.commit()

    again = session.query(TrackAttribute).one()
    assert again.attribute_type == "tempo_bpm"
    assert json.loads(again.value_json) == 126.0
    assert again.source_type == "provider"
    assert again.source_name == "soundcloud"
    assert again.confidence == 0.70


def test_attribute_supports_multiple_observations(session):
    track = Track(canonical_title="T")
    session.add(track)
    session.flush()

    session.add_all(
        [
            TrackAttribute(
                track_id=track.id,
                attribute_type="tempo_bpm",
                value_json="126",
                source_type="provider",
                source_name="soundcloud",
                confidence=0.70,
                is_current=False,
            ),
            TrackAttribute(
                track_id=track.id,
                attribute_type="tempo_bpm",
                value_json="125.82",
                source_type="audio_analysis",
                source_name="essentia-tempo-v1",
                confidence=0.95,
                is_current=True,
            ),
        ]
    )
    session.commit()

    obs = (
        session.query(TrackAttribute)
        .filter(TrackAttribute.track_id == track.id)
        .order_by(TrackAttribute.id)
        .all()
    )
    assert len(obs) == 2
    assert {o.source_name for o in obs} == {"soundcloud", "essentia-tempo-v1"}
    # Both observations exist; "current" selection is a future resolver's job.
    current = [o for o in obs if o.is_current]
    assert len(current) == 1
    assert current[0].source_name == "essentia-tempo-v1"
