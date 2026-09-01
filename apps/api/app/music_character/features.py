"""Feature normalization for M6."""
from __future__ import annotations

from typing import Optional

from .models import MusicCharacterFeatures


def normalize_tempo(tempo: Optional[float]) -> Optional[float]:
    if tempo is None:
        return None
    try:
        v = float(tempo)
    except:
        return None
    # Musically practical range 60-180; clamp and map 60->0, 180->1
    if v < 20 or v > 300:
        return None
    # Linear map 60-180
    norm = (v - 60) / 120.0
    return max(0.0, min(1.0, norm))


def normalize_loudness(loudness_db: Optional[float]) -> Optional[float]:
    if loudness_db is None:
        return None
    try:
        v = float(loudness_db)
    except:
        return None
    # -60 .. 0 dB -> 0..1 (louder = higher)
    norm = (v + 60) / 60.0
    return max(0.0, min(1.0, norm))


def normalize_unit(v: Optional[float]) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except:
        return None
    if f < 0 or f > 1:
        return None
    return f


def build_features(raw: dict) -> MusicCharacterFeatures:
    """Build from library musical_attributes dict or direct values."""
    # raw may be dict of {tempo_bpm:{value:...}, energy:{value:...}} or flat
    def _val(key: str):
        v = raw.get(key)
        if isinstance(v, dict):
            return v.get("value")
        return v

    # mode from musical_key value dict
    mode = None
    mk = raw.get("musical_key")
    if isinstance(mk, dict):
        mv = mk.get("value")
        if isinstance(mv, dict):
            mode = mv.get("mode")
    elif isinstance(mk, dict):
        # already extracted?
        pass
    # also allow direct mode
    if mode is None:
        m = raw.get("mode")
        if isinstance(m, dict):
            mode = m.get("value")
        elif isinstance(m, str):
            mode = m

    return MusicCharacterFeatures(
        tempo_bpm=_val("tempo_bpm"),
        energy=normalize_unit(_val("energy")),
        danceability=normalize_unit(_val("danceability")),
        valence=normalize_unit(_val("valence")),
        acousticness=normalize_unit(_val("acousticness")),
        instrumentalness=normalize_unit(_val("instrumentalness")),
        liveness=normalize_unit(_val("liveness")),
        loudness_db=_val("loudness_db"),
        speechiness=normalize_unit(_val("speechiness")),
        mode=mode,
        camelot=(raw.get("camelot") or {}).get("value") if isinstance(raw.get("camelot"), dict) else raw.get("camelot"),
    )


def tempo_band(normalized_tempo: Optional[float]) -> str:
    if normalized_tempo is None:
        return "unknown"
    if normalized_tempo < 0.25:
        return "slow"  # <90
    if normalized_tempo < 0.6:
        return "medium"  # 90-132
    return "fast"  # >132


def loudness_band(normalized_loudness: Optional[float]) -> str:
    if normalized_loudness is None:
        return "unknown"
    if normalized_loudness < 0.4:
        return "quiet"
    if normalized_loudness < 0.7:
        return "moderate"
    return "loud"
