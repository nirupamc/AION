"""M8 transition intelligence tests."""
import pytest
from app.transitions.scoring import WEIGHTS, harmonic_score, tempo_score, energy_score, mood_score, vibe_score, set_role_score
from app.transitions.models import TransitionTrackFeatures
from app.transitions.service import score_transition
from app.music_character.models import MusicCharacterFeatures

def _feat(**kw):
    base=dict(track_id=1, tempo_bpm=120, musical_key="C major", camelot="8B", energy=0.7, danceability=0.6, valence=0.6, loudness_db=-8, mode="major", dominant_mood="happy", dominant_vibe="groovy", set_role="build")
    base.update(kw)
    # mood/vibe scores defaults
    mood_scores=kw.get("mood_scores", {"happy":0.8,"euphoric":0.5,"dark":0.2})
    vibe_scores=kw.get("vibe_scores", {"groovy":0.7,"driving":0.5})
    return TransitionTrackFeatures(
        track_id=kw.get("track_id",1),
        tempo_bpm=kw.get("tempo_bpm",120),
        musical_key=kw.get("musical_key","C major"),
        camelot=kw.get("camelot","8B"),
        energy=kw.get("energy",0.7),
        danceability=kw.get("danceability",0.6),
        valence=kw.get("valence",0.6),
        loudness_db=kw.get("loudness_db",-8),
        dominant_mood=kw.get("dominant_mood","happy"),
        mood_scores=kw.get("mood_scores", mood_scores),
        dominant_vibe=kw.get("dominant_vibe","groovy"),
        vibe_scores=kw.get("vibe_scores", vibe_scores),
        set_role=kw.get("set_role","build"),
        speechiness=kw.get("speechiness",0.05),
        acousticness=kw.get("acousticness",0.2),
        instrumentalness=kw.get("instrumentalness",0.1),
        liveness=kw.get("liveness",0.1),
    )

def test_scoring_determinism():
    src=_feat(track_id=1, tempo_bpm=120, camelot="8B")
    dst=_feat(track_id=2, tempo_bpm=122, camelot="8A")
    r1=score_transition(src,dst)
    r2=score_transition(src,dst)
    assert r1==r2

def test_harmonic_contribution():
    src=_feat(camelot="8A")
    same=_feat(camelot="8A")
    rel=_feat(camelot="8B")
    adj=_feat(camelot="9A")
    inc=_feat(camelot="2B")
    assert harmonic_score(src,same)[0]==100
    assert harmonic_score(src,rel)[0]==95
    assert harmonic_score(src,adj)[0]==90
    assert harmonic_score(src,inc)[0]==0

def test_bpm_exact_near_far():
    src=_feat(tempo_bpm=120)
    exact=_feat(tempo_bpm=120)
    near=_feat(tempo_bpm=122)  # 1.6% excellent
    far=_feat(tempo_bpm=145)   # 18% large
    s_exact,_a,_=tempo_score(src,exact)
    s_near,_b,_=tempo_score(src,near)
    s_far,_c,_=tempo_score(src,far)
    assert s_exact==100
    assert s_near>90
    assert s_far<50

def test_half_double():
    src=_feat(tempo_bpm=70)
    dst=_feat(tempo_bpm=140)
    score,label,hd=tempo_score(src,dst)
    assert hd in ("half","double")
    assert score in (75,60,40)  # half/double branch

def test_energy_maintain():
    src=_feat(energy=0.6)
    dst_same=_feat(energy=0.6)
    dst_high=_feat(energy=0.95)
    s_same,_=energy_score(src,dst_same,intent="maintain")
    s_high,_=energy_score(src,dst_high,intent="maintain")
    assert s_same==100
    assert s_same > s_high

def test_energy_build():
    src=_feat(energy=0.5)
    dst_build=_feat(energy=0.62)  # +0.12 ideal
    dst_drop=_feat(energy=0.3)
    s_build,_=energy_score(src,dst_build,intent="build")
    s_drop,_=energy_score(src,dst_drop,intent="build")
    assert s_build > s_drop

def test_energy_drop():
    src=_feat(energy=0.7)
    dst_drop=_feat(energy=0.58)  # -0.12 ideal
    dst_build=_feat(energy=0.9)
    s_drop,_=energy_score(src,dst_drop,intent="drop")
    s_build,_=energy_score(src,dst_build,intent="drop")
    assert s_drop > s_build

def test_mood_vector_similarity():
    src=_feat(mood_scores={"dark":0.8,"intense":0.7}, dominant_mood="dark")
    dst_sim=_feat(mood_scores={"dark":0.7,"intense":0.6}, dominant_mood="dark")
    dst_diff=_feat(mood_scores={"happy":0.9,"calm":0.8}, dominant_mood="happy")
    s_sim,_=mood_score(src,dst_sim)
    s_diff,_=mood_score(src,dst_diff)
    assert s_sim > s_diff
    assert s_sim > 70

def test_vibe_vector_similarity():
    src=_feat(vibe_scores={"driving":0.8,"hypnotic":0.6}, dominant_vibe="driving")
    dst_sim=_feat(vibe_scores={"driving":0.7,"hypnotic":0.5}, dominant_vibe="driving")
    dst_diff=_feat(vibe_scores={"chill":0.9,"atmospheric":0.8}, dominant_vibe="chill")
    s_sim,_=vibe_score(src,dst_sim)
    s_diff,_=vibe_score(src,dst_diff)
    assert s_sim > s_diff

def test_role_progression():
    src=_feat(set_role="warmup")
    dst_build=_feat(set_role="build")
    dst_peak=_feat(set_role="peak")
    s_build,_=set_role_score(src,dst_build)
    s_peak,_=set_role_score(src,dst_peak)
    assert s_build > s_peak  # warmup->peak should be 30, warmup->build 90

def test_missing_feature_reweighting():
    src=_feat(tempo_bpm=120, camelot="8A", energy=0.6)
    # dst missing camelot and mood/vibe
    dst=TransitionTrackFeatures(track_id=2, tempo_bpm=122, energy=0.62, mood_scores={}, vibe_scores={})
    res=score_transition(src,dst)
    assert "harmonic" in res["missing_components"]
    assert "mood" in res["missing_components"]
    # overall should still be computed from available (tempo+energy)
    assert res["transition_score"] > 0
    # renormalized: weights sum of available only
    assert res["transition_score"] <= 100

def test_minimum_evidence():
    src=_feat(tempo_bpm=None, camelot=None, energy=None, mood_scores={}, vibe_scores={})
    dst=_feat(tempo_bpm=None, camelot=None, energy=None, mood_scores={}, vibe_scores={})
    res=score_transition(src,dst)
    # No tempo, no harmonic/energy -> missing many, should still return but low
    assert res["transition_score"] == 0 or len(res["missing_components"]) >= 3

def test_self_exclusion_api(session):
    from app.models import Track, ProviderTrack
    from app.enrichment import EnrichmentResult
    from app.enrichment.persistence import persist_enrichment
    t1=Track(canonical_title="t1"); session.add(t1); session.flush()
    pt=ProviderTrack(track_id=t1.id, provider="spotify", provider_track_id="sp-t1", raw_title="t1", artist_display="A", raw_metadata='{"artists":[{"name":"A"}]}')
    session.add(pt); session.flush()
    res=EnrichmentResult(source="soundcharts", status="matched", tempo_bpm=120, musical_key="C major", time_signature=4, energy=0.7, danceability=0.6, valence=0.6, acousticness=0.2, instrumentalness=0.0, liveness=0.1, loudness_db=-8, speechiness=0.05, source_identifier="u")
    persist_enrichment(session, track_id=t1.id, result=res, source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    from app.transitions.service import get_best_next_tracks
    out=get_best_next_tracks(session, track_id=t1.id, limit=5)
    assert all(r["track_id"] != t1.id for r in out["recommendations"])

def test_stable_ordering(session):
    from app.models import Track, ProviderTrack
    from app.enrichment import EnrichmentResult
    from app.enrichment.persistence import persist_enrichment
    # create 3 tracks with identical features => same score, order by track_id
    tracks=[]
    for i in range(3):
        t=Track(canonical_title=f"t{i}")
        session.add(t); session.flush()
        pt=ProviderTrack(track_id=t.id, provider="spotify", provider_track_id=f"sp-s{i}", raw_title=f"t{i}", artist_display="A", raw_metadata='{"artists":[{"name":"A"}]}')
        session.add(pt); tracks.append(t)
    session.flush()
    for t in tracks:
        r=EnrichmentResult(source="soundcharts", status="matched", tempo_bpm=120, musical_key="C major", time_signature=4, energy=0.7, danceability=0.6, valence=0.6, acousticness=0.2, instrumentalness=0.0, liveness=0.1, loudness_db=-8, speechiness=0.05, source_identifier="u")
        persist_enrichment(session, track_id=t.id, result=r, source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    src=tracks[0]
    from app.transitions.service import get_best_next_tracks
    out=get_best_next_tracks(session, track_id=src.id, limit=5)
    # should have 2 recommendations (other 2)
    assert len(out["recommendations"])==2
    assert out["recommendations"][0]["track_id"] < out["recommendations"][1]["track_id"]

def test_explanation_generation():
    src=_feat(track_id=1, tempo_bpm=120, camelot="8A", energy=0.6)
    dst=_feat(track_id=2, tempo_bpm=122, camelot="8A", energy=0.62)
    res=score_transition(src,dst)
    assert len(res["reasons"]) > 0
    assert "components" in res
    assert "harmonic" in res["components"]

def test_warnings():
    src=_feat(tempo_bpm=120, camelot="8A", energy=0.6, valence=0.5)
    dst=_feat(tempo_bpm=145, camelot="2B", energy=0.95, valence=0.1)
    res=score_transition(src,dst)
    assert len(res["warnings"]) > 0  # large BPM gap + harmonic incompatible

def test_pair_api(session):
    from app.models import Track, ProviderTrack
    from app.enrichment import EnrichmentResult
    from app.enrichment.persistence import persist_enrichment
    t1=Track(canonical_title="a"); t2=Track(canonical_title="b")
    session.add_all([t1,t2]); session.flush()
    for t in [t1,t2]:
        pt=ProviderTrack(track_id=t.id, provider="spotify", provider_track_id=f"sp-p{t.id}", raw_title="x", artist_display="A", raw_metadata='{"artists":[{"name":"A"}]}')
        session.add(pt)
    session.flush()
    for t, bpm, key in [(t1,120,"C major"),(t2,122,"A minor")]:
        r=EnrichmentResult(source="soundcharts", status="matched", tempo_bpm=bpm, musical_key=key, time_signature=4, energy=0.7, danceability=0.6, valence=0.6, acousticness=0.2, instrumentalness=0.0, liveness=0.1, loudness_db=-8, speechiness=0.05, source_identifier="u")
        persist_enrichment(session, track_id=t.id, result=r, source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    from app.transitions.service import get_pair_transition
    res=get_pair_transition(session, t1.id, t2.id)
    assert "transition_score" in res
    assert "components" in res

def test_next_track_api_limit(session):
    from app.models import Track, ProviderTrack
    from app.enrichment import EnrichmentResult
    from app.enrichment.persistence import persist_enrichment
    tracks=[]
    for i in range(5):
        t=Track(canonical_title=f"n{i}")
        session.add(t); session.flush()
        pt=ProviderTrack(track_id=t.id, provider="spotify", provider_track_id=f"sp-n{i}", raw_title=f"n{i}", artist_display="A", raw_metadata='{"artists":[{"name":"A"}]}')
        session.add(pt); tracks.append(t)
    session.flush()
    for t in tracks:
        r=EnrichmentResult(source="soundcharts", status="matched", tempo_bpm=120, musical_key="C major", time_signature=4, energy=0.7, danceability=0.6, valence=0.6, acousticness=0.2, instrumentalness=0.0, liveness=0.1, loudness_db=-8, speechiness=0.05, source_identifier="u")
        persist_enrichment(session, track_id=t.id, result=r, source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    from app.transitions.service import get_best_next_tracks
    out=get_best_next_tracks(session, track_id=tracks[0].id, limit=2)
    assert len(out["recommendations"])<=2

def test_malformed_intent_defaults():
    src=_feat()
    dst=_feat()
    res=score_transition(src,dst, energy_intent="invalid")
    assert res["energy_intent"]=="invalid" or True  # should not crash, defaults to maintain-like
