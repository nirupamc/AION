"""Models for M6 musical character inference."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class MusicCharacterFeatures:
    tempo_bpm: Optional[float] = None
    energy: Optional[float] = None
    danceability: Optional[float] = None
    valence: Optional[float] = None
    acousticness: Optional[float] = None
    instrumentalness: Optional[float] = None
    liveness: Optional[float] = None
    loudness_db: Optional[float] = None
    speechiness: Optional[float] = None
    mode: Optional[str] = None  # "major" | "minor" | None
    camelot: Optional[str] = None


@dataclass(frozen=True)
class ScoredLabel:
    label: str
    score: float  # 0.0-1.0
    explanation: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MusicCharacterProfile:
    moods: list[ScoredLabel]
    vibes: list[ScoredLabel]
    dominant_mood: Optional[str]
    dominant_vibe: Optional[str]
    set_role: Optional[str] = None  # warmup/build/peak/cooldown
    model_version: str = "m6-character-v1"
    source: str = "aion_music_character"

    def to_dict(self, min_score: float = 0.15) -> dict[str, Any]:
        # compact output filtering
        moods = [{"label": m.label, "score": round(m.score, 3), "explanation": m.explanation} for m in self.moods if m.score >= min_score]
        vibes = [{"label": v.label, "score": round(v.score, 3), "explanation": v.explanation} for v in self.vibes if v.score >= min_score]
        d: dict[str, Any] = {
            "dominant_mood": self.dominant_mood,
            "dominant_vibe": self.dominant_vibe,
            "moods": moods,
            "vibes": vibes,
            "source": self.source,
            "analysis_version": self.model_version,
        }
        if self.set_role:
            d["set_role"] = self.set_role
        return d

    def full_scores(self) -> dict[str, dict[str, float]]:
        return {
            "moods": {m.label: m.score for m in self.moods},
            "vibes": {v.label: v.score for v in self.vibes},
        }
