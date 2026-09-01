"""Build TransitionTrackFeatures from DB."""
from __future__ import annotations
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.library import musical_attributes_for, music_character_for
from .models import TransitionTrackFeatures

def load_transition_features(session: Session, track_ids: list[int]) -> dict[int, TransitionTrackFeatures]:
    if not track_ids:
        return {}
    music_map = musical_attributes_for(session, track_ids)
    char_map = music_character_for(session, track_ids)
    out: dict[int, TransitionTrackFeatures] = {}
    for tid in track_ids:
        attrs = music_map.get(tid, {})
        char = char_map.get(tid)
        # tempo
        tempo = None
        tb = attrs.get("tempo_bpm")
        if tb and tb.get("value") is not None:
            try:
                tempo = float(tb["value"])
            except:
                tempo = None
        # key display
        key_disp = None
        mk = attrs.get("musical_key")
        if mk and mk.get("value") is not None:
            v = mk["value"]
            if isinstance(v, dict):
                key_disp = v.get("display")
            elif isinstance(v, str):
                key_disp = v
        camelot = None
        cam = attrs.get("camelot")
        if cam and cam.get("value"):
            camelot = cam["value"]
        # energy etc
        def _val(k: str):
            a = attrs.get(k)
            if a and a.get("value") is not None:
                try:
                    return float(a["value"])
                except:
                    return None
            return None
        energy = _val("energy")
        danceability = _val("danceability")
        valence = _val("valence")
        loudness = _val("loudness_db")
        acousticness = _val("acousticness")
        instrumentalness = _val("instrumentalness")
        liveness = _val("liveness")
        speechiness = _val("speechiness")

        mood_scores = {}
        vibe_scores = {}
        dominant_mood = None
        dominant_vibe = None
        set_role = None
        if char:
            dominant_mood = char.get("dominant_mood")
            dominant_vibe = char.get("dominant_vibe")
            set_role = char.get("set_role")
            for m in char.get("moods", []):
                mood_scores[m["label"]] = float(m["score"])
            for v in char.get("vibes", []):
                vibe_scores[v["label"]] = float(v["score"])

        out[tid] = TransitionTrackFeatures(
            track_id=tid,
            tempo_bpm=tempo,
            musical_key=key_disp,
            camelot=camelot,
            energy=energy,
            danceability=danceability,
            valence=valence,
            loudness_db=loudness,
            acousticness=acousticness,
            instrumentalness=instrumentalness,
            liveness=liveness,
            speechiness=speechiness,
            dominant_mood=dominant_mood,
            mood_scores=mood_scores,
            dominant_vibe=dominant_vibe,
            vibe_scores=vibe_scores,
            set_role=set_role,
        )
    return out
