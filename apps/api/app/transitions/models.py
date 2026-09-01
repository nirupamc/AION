"""Transition input models."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional, Dict

@dataclass(frozen=True)
class TransitionTrackFeatures:
    track_id: int
    tempo_bpm: Optional[float] = None
    musical_key: Optional[str] = None  # display e.g. "C major" or dict?
    camelot: Optional[str] = None
    energy: Optional[float] = None
    danceability: Optional[float] = None
    valence: Optional[float] = None
    loudness_db: Optional[float] = None
    acousticness: Optional[float] = None
    instrumentalness: Optional[float] = None
    liveness: Optional[float] = None
    speechiness: Optional[float] = None
    dominant_mood: Optional[str] = None
    mood_scores: Dict[str, float] = None  # type: ignore
    dominant_vibe: Optional[str] = None
    vibe_scores: Dict[str, float] = None  # type: ignore
    set_role: Optional[str] = None

    def __post_init__(self):
        # ensure dict defaults
        if self.mood_scores is None:
            object.__setattr__(self, "mood_scores", {})
        if self.vibe_scores is None:
            object.__setattr__(self, "vibe_scores", {})
