"""Mood scoring - 8 labels: euphoric, happy, dark, melancholic, calm, intense, uplifting, aggressive."""
from __future__ import annotations

from .models import MusicCharacterFeatures, ScoredLabel
from .features import normalize_tempo, normalize_loudness
from .scoring import weighted_score, clamp01

# Centralized weights per mood: list of (feature_getter, weight, explanation)
# Weights are positive; direction encoded via 1-value for negative.

MOOD_RULES: dict[str, dict] = {
    "euphoric": {
        "desc": "high valence + high energy + major + danceable + bright loudness",
        "weights": [
            ("valence", 0.30, "high valence"),
            ("energy", 0.25, "high energy"),
            ("danceability", 0.15, "high danceability"),
            ("loudness", 0.10, "loud"),
            ("major", 0.10, "major mode"),
            ("tempo_high", 0.10, "upbeat tempo"),
        ],
    },
    "happy": {
        "desc": "high valence + moderate energy + major",
        "weights": [
            ("valence", 0.35, "high valence"),
            ("energy", 0.20, "moderate energy"),
            ("major", 0.15, "major mode"),
            ("danceability", 0.15, "danceable"),
            ("acousticness_inv", 0.15, "not too acoustic"),
        ],
    },
    "dark": {
        "desc": "low valence + minor + moderate/high energy",
        "weights": [
            ("valence_inv", 0.30, "low valence"),
            ("minor", 0.20, "minor mode"),
            ("energy", 0.20, "high energy"),
            ("acousticness_inv", 0.15, "low acousticness"),
            ("loudness", 0.15, "loud"),
        ],
    },
    "melancholic": {
        "desc": "low valence + low energy + acoustic + minor + slow",
        "weights": [
            ("valence_inv", 0.25, "low valence"),
            ("energy_inv", 0.25, "low energy"),
            ("acousticness", 0.15, "acoustic"),
            ("minor", 0.15, "minor mode"),
            ("tempo_low", 0.10, "slow tempo"),
            ("loudness_inv", 0.10, "quiet"),
        ],
    },
    "calm": {
        "desc": "low energy + low loudness + high acousticness + low speechiness",
        "weights": [
            ("energy_inv", 0.30, "low energy"),
            ("loudness_inv", 0.20, "quiet"),
            ("acousticness", 0.20, "acoustic"),
            ("speechiness_inv", 0.15, "low speechiness"),
            ("tempo_low", 0.15, "slow tempo"),
        ],
    },
    "intense": {
        "desc": "high energy + loud + low valence? + minor + high liveness",
        "weights": [
            ("energy", 0.30, "high energy"),
            ("loudness", 0.25, "loud"),
            ("liveness", 0.15, "live"),
            ("valence_inv", 0.10, "low valence"),
            ("minor", 0.10, "minor mode"),
            ("tempo_high", 0.10, "fast tempo"),
        ],
    },
    "uplifting": {
        "desc": "high valence + high energy + major + danceable + bright",
        "weights": [
            ("valence", 0.30, "high valence"),
            ("energy", 0.25, "high energy"),
            ("major", 0.15, "major mode"),
            ("danceability", 0.15, "high danceability"),
            ("loudness", 0.10, "loud"),
            ("tempo_high", 0.05, "upbeat tempo"),
        ],
    },
    "aggressive": {
        "desc": "high energy + low valence + loud + low acousticness + minor + speechy",
        "weights": [
            ("energy", 0.25, "high energy"),
            ("valence_inv", 0.20, "low valence"),
            ("loudness", 0.20, "loud"),
            ("acousticness_inv", 0.15, "low acousticness"),
            ("minor", 0.10, "minor mode"),
            ("speechiness", 0.10, "speechy"),
        ],
    },
}

def _extract(feature: MusicCharacterFeatures, key: str):
    nt = normalize_tempo(feature.tempo_bpm)
    nl = normalize_loudness(feature.loudness_db)
    mode = (feature.mode or "").lower() if feature.mode else None
    major = 1.0 if mode == "major" else 0.0 if mode == "minor" else None
    minor = 1.0 if mode == "minor" else 0.0 if mode == "major" else None
    mapping = {
        "valence": feature.valence,
        "valence_inv": 1 - feature.valence if feature.valence is not None else None,
        "energy": feature.energy,
        "energy_inv": 1 - feature.energy if feature.energy is not None else None,
        "danceability": feature.danceability,
        "acousticness": feature.acousticness,
        "acousticness_inv": 1 - feature.acousticness if feature.acousticness is not None else None,
        "liveness": feature.liveness,
        "speechiness": feature.speechiness,
        "speechiness_inv": 1 - feature.speechiness if feature.speechiness is not None else None,
        "loudness": nl,
        "loudness_inv": 1 - nl if nl is not None else None,
        "major": major,
        "minor": minor,
        "tempo_high": nt,
        "tempo_low": 1 - nt if nt is not None else None,
    }
    return mapping.get(key)


def score_moods(features: MusicCharacterFeatures) -> list[ScoredLabel]:
    out: list[ScoredLabel] = []
    for label, rule in MOOD_RULES.items():
        contribs = []
        for feat_key, weight, expl in rule["weights"]:
            val = _extract(features, feat_key)
            contribs.append((val, weight, expl))
        score, exps = weighted_score(contribs)
        # small boost for mode bonus already included
        out.append(ScoredLabel(label=label, score=round(clamp01(score), 3), explanation=exps))
    out.sort(key=lambda s: -s.score)
    return out
