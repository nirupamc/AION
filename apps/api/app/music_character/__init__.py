"""Public API for M6 character inference."""
from .models import MusicCharacterFeatures, MusicCharacterProfile, ScoredLabel
from .features import build_features, normalize_tempo, normalize_loudness
from .mood import score_moods
from .vibe import score_vibes, infer_set_role

def infer_character(features: MusicCharacterFeatures) -> MusicCharacterProfile:
    moods = score_moods(features)
    vibes = score_vibes(features)
    dominant_mood = moods[0].label if moods and moods[0].score >= 0.15 else None
    dominant_vibe = vibes[0].label if vibes and vibes[0].score >= 0.15 else None
    set_role = infer_set_role(features, moods, vibes)
    return MusicCharacterProfile(
        moods=moods,
        vibes=vibes,
        dominant_mood=dominant_mood,
        dominant_vibe=dominant_vibe,
        set_role=set_role,
    )

__all__ = ["MusicCharacterFeatures","MusicCharacterProfile","ScoredLabel","build_features","infer_character"]
