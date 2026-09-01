"""M6 music character tests."""
import pytest

from app.music_character.features import normalize_tempo, normalize_loudness, normalize_unit, build_features
from app.music_character.models import MusicCharacterFeatures
from app.music_character import infer_character
from app.music_character.mood import score_moods
from app.music_character.vibe import score_vibes


def test_feature_normalization():
    assert normalize_tempo(120) == pytest.approx(0.5, abs=0.01)
    assert normalize_tempo(60) == pytest.approx(0.0)
    assert normalize_tempo(180) == pytest.approx(1.0)
    assert normalize_tempo(None) is None
    assert normalize_tempo(400) is None
    assert normalize_loudness(-6) == pytest.approx(0.9, abs=0.01)
    assert normalize_loudness(-60) == 0.0
    assert normalize_loudness(0) == 1.0
    assert normalize_unit(0.5) == 0.5
    assert normalize_unit(1.2) is None
    assert normalize_unit(None) is None


def test_missing_features_handled():
    f = MusicCharacterFeatures()  # all None
    profile = infer_character(f)
    # Should still produce scores but all low (since no contributions)
    assert profile.dominant_mood is None or isinstance(profile.dominant_mood, str)
    # No crash
    assert len(profile.moods) == 8
    assert len(profile.vibes) == 10


def test_mood_major_minor_contribution():
    happy_major = MusicCharacterFeatures(valence=0.9, energy=0.8, danceability=0.7, mode="major")
    happy_minor = MusicCharacterFeatures(valence=0.9, energy=0.8, danceability=0.7, mode="minor")
    pmaj = infer_character(happy_major)
    pmin = infer_character(happy_minor)
    # euphoric/happy should be higher for major
    emaj = next(m for m in pmaj.moods if m.label == "euphoric").score
    emin = next(m for m in pmin.moods if m.label == "euphoric").score
    assert emaj > emin
    # dark should be higher for minor
    dark_maj = next(m for m in pmaj.moods if m.label == "dark").score
    dark_min = next(m for m in pmin.moods if m.label == "dark").score
    assert dark_min > dark_maj


def test_tempo_contribution():
    fast = MusicCharacterFeatures(tempo_bpm=140, energy=0.8, valence=0.8, danceability=0.7, mode="major")
    slow = MusicCharacterFeatures(tempo_bpm=70, energy=0.8, valence=0.8, danceability=0.7, mode="major")
    # euphoric favors high tempo slightly, so fast should be >= slow
    pf = infer_character(fast)
    ps = infer_character(slow)
    ef = next(m for m in pf.moods if m.label == "euphoric").score
    es = next(m for m in ps.moods if m.label == "euphoric").score
    assert ef >= es


def test_loudness_normalization_used():
    loud = MusicCharacterFeatures(energy=0.9, valence=0.2, loudness_db=-5, acousticness=0.1, mode="minor")
    quiet = MusicCharacterFeatures(energy=0.9, valence=0.2, loudness_db=-30, acousticness=0.1, mode="minor")
    pl = infer_character(loud)
    pq = infer_character(quiet)
    # aggressive favors loud
    al = next(m for m in pl.moods if m.label == "aggressive").score
    aq = next(m for m in pq.moods if m.label == "aggressive").score
    assert al > aq


def test_multi_label_behavior():
    f = MusicCharacterFeatures(energy=0.9, valence=0.9, danceability=0.8, mode="major", tempo_bpm=128, loudness_db=-5)
    p = infer_character(f)
    scores = [m.score for m in p.moods]
    # multiple moods should have non-zero scores
    assert sum(1 for s in scores if s > 0.3) >= 2
    assert sum(1 for s in [v.score for v in p.vibes] if s > 0.3) >= 2


def test_dominant_label_selection():
    f = MusicCharacterFeatures(energy=0.95, valence=0.95, danceability=0.9, mode="major", tempo_bpm=128, loudness_db=-4)
    p = infer_character(f)
    assert p.dominant_mood == max(p.moods, key=lambda m: m.score).label
    assert p.dominant_vibe == max(p.vibes, key=lambda v: v.score).label


def test_deterministic_results():
    f = MusicCharacterFeatures(energy=0.7, valence=0.6, danceability=0.5, acousticness=0.2, tempo_bpm=120, mode="major", loudness_db=-8)
    p1 = infer_character(f)
    p2 = infer_character(f)
    assert p1.to_dict() == p2.to_dict()


def test_provenance():
    f = MusicCharacterFeatures(energy=0.8, valence=0.8, danceability=0.7, mode="major")
    p = infer_character(f)
    d = p.to_dict()
    assert d["source"] == "aion_music_character"
    assert d["analysis_version"] == "m6-character-v1"


def test_api_serialization_and_filters(session):
    from app.models import Track, ProviderTrack, TrackAttribute
    from app.enrichment.persistence import persist_enrichment
    from app.enrichment import EnrichmentResult
    from app.library import list_tracks, ListParams, track_detail
    import json

    # Create two tracks with distinct characters: intense/dark vs calm/chill
    t1 = Track(canonical_title="intense")
    t2 = Track(canonical_title="calm")
    session.add_all([t1, t2]); session.flush()
    for t in [t1, t2]:
        pt = ProviderTrack(track_id=t.id, provider="spotify", provider_track_id=f"sp-{t.id}", raw_title=t.canonical_title, artist_display="A", raw_metadata='{"artists":[{"name":"A"}]}')
        session.add(pt)
    session.flush()
    # intense track: high energy etc
    r1 = EnrichmentResult(source="soundcharts", status="matched", tempo_bpm=140, musical_key="B minor", energy=0.95, danceability=0.7, valence=0.2, acousticness=0.1, instrumentalness=0.0, liveness=0.2, loudness_db=-5, speechiness=0.05, confidence=None, source_identifier="u1")
    # manually persist via extended fields: need to use persist with all fields
    # create result with full fields via helper
    from app.music_character.models import MusicCharacterFeatures
    # Use persist directly with result containing all
    r1_full = EnrichmentResult(source="soundcharts", status="matched", tempo_bpm=140, musical_key="B minor", time_signature=4, energy=0.95, danceability=0.7, valence=0.2, acousticness=0.1, instrumentalness=0.0, liveness=0.2, loudness_db=-5, speechiness=0.05, confidence=None, source_identifier="u1")
    r2_full = EnrichmentResult(source="soundcharts", status="matched", tempo_bpm=70, musical_key="C major", time_signature=4, energy=0.2, danceability=0.3, valence=0.7, acousticness=0.8, instrumentalness=0.0, liveness=0.1, loudness_db=-20, speechiness=0.02, confidence=None, source_identifier="u2")
    persist_enrichment(session, track_id=t1.id, result=r1_full, source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    persist_enrichment(session, track_id=t2.id, result=r2_full, source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()

    # API via library
    page = list_tracks(session, params=ListParams(page=1, page_size=50))
    items = {i.track_id: i for i in page.items}
    assert items[t1.id].music_character is not None
    assert items[t1.id].music_character["dominant_mood"] in ["intense","dark","aggressive"]
    assert items[t2.id].music_character["dominant_mood"] in ["calm","melancholic","warmup"] or items[t2.id].music_character["dominant_vibe"] in ["chill","warmup","atmospheric"]

    # detail
    d = track_detail(session, track_id=t1.id)
    assert "music_character" in d
    assert d["music_character"]["source"] == "aion_music_character"

    # filter by mood
    mood = items[t1.id].music_character["dominant_mood"]
    filtered = list_tracks(session, params=ListParams(page=1, page_size=50, mood=mood))
    assert any(i.track_id == t1.id for i in filtered.items)
    # filter by vibe
    vibe = items[t1.id].music_character["dominant_vibe"]
    filtered2 = list_tracks(session, params=ListParams(page=1, page_size=50, vibe=vibe))
    assert any(i.track_id == t1.id for i in filtered2.items)


def test_sanity_constraints():
    # very low energy but peak_time near 1 should not happen
    low_energy = MusicCharacterFeatures(energy=0.1, danceability=0.2, valence=0.5, loudness_db=-30, tempo_bpm=90, acousticness=0.8)
    p = infer_character(low_energy)
    peak = next(v for v in p.vibes if v.label == "peak_time")
    assert peak.score < 0.5, f"low energy peak_time {peak.score} is absurd"

    # very high acousticness but aggressive near 1 should not
    acoustic = MusicCharacterFeatures(energy=0.9, acousticness=0.95, loudness_db=-5, valence=0.2, mode="minor", speechiness=0.05)
    p2 = infer_character(acoustic)
    agg = next(m for m in p2.moods if m.label == "aggressive")
    assert agg.score < 0.75

    # speechiness near 1 but vocal near 0 absurd
    speechy = MusicCharacterFeatures(speechiness=0.95, instrumentalness=0.9, energy=0.5)
    p3 = infer_character(speechy)
    vocal = next(v for v in p3.vibes if v.label == "vocal")
    assert vocal.score < 0.65  # high instrumentalness should suppress vocal


def test_set_role():
    warm = MusicCharacterFeatures(energy=0.2, tempo_bpm=80)
    peak = MusicCharacterFeatures(energy=0.95, tempo_bpm=130)
    assert infer_character(warm).set_role in ["warmup","cooldown"]
    assert infer_character(peak).set_role == "peak"


def test_idempotency_derive():
    f = MusicCharacterFeatures(energy=0.7, valence=0.6, danceability=0.6, tempo_bpm=120, mode="major", loudness_db=-8)
    p1 = infer_character(f).to_dict()
    p2 = infer_character(f).to_dict()
    assert p1 == p2
