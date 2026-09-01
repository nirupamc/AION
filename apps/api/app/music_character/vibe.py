"""Vibe scoring - 10 DJ-oriented labels."""
from __future__ import annotations

from .models import MusicCharacterFeatures, ScoredLabel
from .features import normalize_tempo, normalize_loudness
from .scoring import weighted_score, clamp01

VIBE_RULES: dict[str, dict] = {
    "driving": {
        "desc": "high energy + high danceability + low acousticness + tempo 120-140",
        "weights": [
            ("energy", 0.30, "high energy"),
            ("danceability", 0.25, "high danceability"),
            ("acousticness_inv", 0.20, "low acousticness"),
            ("tempo_mid_high", 0.15, "driving tempo"),
            ("loudness", 0.10, "loud"),
        ],
    },
    "hypnotic": {
        "desc": "high instrumentalness + moderate energy + low speechiness + steady valence",
        "weights": [
            ("instrumentalness", 0.30, "instrumental"),
            ("energy", 0.15, "moderate energy"),
            ("speechiness_inv", 0.20, "low speechiness"),
            ("valence_mid", 0.15, "steady valence"),
            ("liveness_inv", 0.10, "controlled"),
            ("acousticness_inv", 0.10, "low acousticness"),
        ],
    },
    "psychedelic": {
        "desc": "high instrumentalness + high liveness + moderate valence + acoustic texture",
        "weights": [
            ("instrumentalness", 0.25, "instrumental"),
            ("liveness", 0.20, "live feel"),
            ("acousticness", 0.15, "textural"),
            ("valence_mid", 0.15, "moderate valence"),
            ("energy", 0.15, "moderate energy"),
            ("speechiness_inv", 0.10, "low speechiness"),
        ],
    },
    "groovy": {
        "desc": "high danceability + high valence + moderate energy",
        "weights": [
            ("danceability", 0.35, "high danceability"),
            ("valence", 0.25, "high valence"),
            ("energy", 0.20, "groovy energy"),
            ("acousticness_inv", 0.10, "not too acoustic"),
            ("tempo_mid", 0.10, "mid tempo"),
        ],
    },
    "atmospheric": {
        "desc": "high acousticness + high instrumentalness + low speechiness + calm",
        "weights": [
            ("acousticness", 0.25, "acoustic"),
            ("instrumentalness", 0.25, "instrumental"),
            ("energy_inv", 0.20, "low energy"),
            ("speechiness_inv", 0.15, "low speechiness"),
            ("loudness_inv", 0.15, "quiet"),
        ],
    },
    "organic": {
        "desc": "high acousticness + low instrumentalness? + live + moderate valence",
        "weights": [
            ("acousticness", 0.30, "acoustic"),
            ("liveness", 0.20, "live"),
            ("valence", 0.15, "warm valence"),
            ("energy_inv", 0.15, "gentle energy"),
            ("loudness_inv", 0.10, "natural loudness"),
            ("speechiness_inv", 0.10, "low speechiness"),
        ],
    },
    "peak_time": {
        "desc": "very high energy + high danceability + loud + high valence + tempo 125-135",
        "weights": [
            ("energy", 0.30, "high energy"),
            ("danceability", 0.25, "high danceability"),
            ("loudness", 0.20, "loud"),
            ("valence", 0.15, "high valence"),
            ("tempo_peak", 0.10, "peak tempo"),
        ],
    },
    "warmup": {
        "desc": "low-medium energy + moderate valence + moderate danceability",
        "weights": [
            ("energy_low_mid", 0.30, "warmup energy"),
            ("valence", 0.20, "moderate valence"),
            ("danceability", 0.20, "groovable"),
            ("acousticness", 0.15, "soft"),
            ("loudness_inv", 0.15, "not loud"),
        ],
    },
    "chill": {
        "desc": "low energy + high acousticness + low loudness + low speechiness",
        "weights": [
            ("energy_inv", 0.30, "low energy"),
            ("acousticness", 0.25, "acoustic"),
            ("loudness_inv", 0.20, "quiet"),
            ("valence_mid", 0.15, "mellow valence"),
            ("speechiness_inv", 0.10, "low speechiness"),
        ],
    },
    "vocal": {
        "desc": "high speechiness + low instrumentalness + moderate energy",
        "weights": [
            ("speechiness", 0.40, "speechy"),
            ("instrumentalness_inv", 0.30, "not instrumental"),
            ("energy", 0.15, "vocal energy"),
            ("liveness", 0.15, "live vocal"),
        ],
    },
}

def _extract(feature: MusicCharacterFeatures, key: str):
    nt = normalize_tempo(feature.tempo_bpm)
    nl = normalize_loudness(feature.loudness_db)
    # tempo helpers
    tempo_mid = 1 - abs((nt or 0.5) - 0.5)*2 if nt is not None else None
    # driving tempo ideal around 125-135 => nt ~0.54-0.625 -> mid-high
    tempo_mid_high = None
    if nt is not None:
        # peak around 0.6
        tempo_mid_high = 1 - abs(nt - 0.60)*2.5
        tempo_mid_high = max(0, min(1, tempo_mid_high))
    tempo_peak = None
    if nt is not None:
        # peak_time ideal 128 => nt (128-60)/120=0.566
        tempo_peak = 1 - abs(nt - 0.566)*4
        tempo_peak = max(0, min(1, tempo_peak))
    valence_mid = None
    if feature.valence is not None:
        valence_mid = 1 - abs(feature.valence - 0.5)*2
    energy_low_mid = None
    if feature.energy is not None:
        # warmup energy ideal 0.4
        energy_low_mid = 1 - abs(feature.energy - 0.4)*2
        energy_low_mid = max(0, min(1, energy_low_mid))

    mapping = {
        "energy": feature.energy,
        "energy_inv": 1 - feature.energy if feature.energy is not None else None,
        "danceability": feature.danceability,
        "valence": feature.valence,
        "valence_mid": valence_mid,
        "valence_inv": 1 - feature.valence if feature.valence is not None else None,
        "acousticness": feature.acousticness,
        "acousticness_inv": 1 - feature.acousticness if feature.acousticness is not None else None,
        "instrumentalness": feature.instrumentalness,
        "instrumentalness_inv": 1 - feature.instrumentalness if feature.instrumentalness is not None else None,
        "liveness": feature.liveness,
        "liveness_inv": 1 - feature.liveness if feature.liveness is not None else None,
        "speechiness": feature.speechiness,
        "speechiness_inv": 1 - feature.speechiness if feature.speechiness is not None else None,
        "loudness": nl,
        "loudness_inv": 1 - nl if nl is not None else None,
        "tempo_mid": tempo_mid,
        "tempo_mid_high": tempo_mid_high,
        "tempo_peak": tempo_peak,
        "energy_low_mid": energy_low_mid,
    }
    return mapping.get(key)


def score_vibes(features: MusicCharacterFeatures) -> list[ScoredLabel]:
    out: list[ScoredLabel] = []
    for label, rule in VIBE_RULES.items():
        contribs = []
        for feat_key, weight, expl in rule["weights"]:
            val = _extract(features, feat_key)
            contribs.append((val, weight, expl))
        score, exps = weighted_score(contribs)
        out.append(ScoredLabel(label=label, score=round(clamp01(score), 3), explanation=exps))
    out.sort(key=lambda s: -s.score)
    return out


def infer_set_role(features: MusicCharacterFeatures, moods, vibes) -> str | None:
    # Simple heuristic for DJ set role
    energy = features.energy
    nt = normalize_tempo(features.tempo_bpm)
    if energy is None:
        return None
    if energy < 0.35:
        return "warmup" if (nt or 0) < 0.5 else "cooldown"
    if energy > 0.85:
        return "peak"
    if energy > 0.55:
        return "build"
    return "warmup"
