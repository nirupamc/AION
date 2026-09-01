"""Shared scoring helpers."""
from __future__ import annotations

from typing import Optional

def clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))

def weighted_score(contributions: list[tuple[Optional[float], float, str]]) -> tuple[float, list[str]]:
    """Compute weighted score.

    contributions: list of (value 0-1 or None, weight, explanation)
    - None values are skipped and weight renormalized.
    - value already incorporates direction (e.g., 1-valence for low valence)
    Returns (score 0-1, explanations for active contributions)
    """
    active = [(val, w, exp) for val, w, exp in contributions if val is not None]
    if not active:
        return 0.0, []
    total_weight = sum(abs(w) for _, w, _ in active)
    if total_weight == 0:
        return 0.0, []
    score = sum(val * w for val, w, _ in active) / total_weight
    # ensure weights positive only? For simplicity weights are positive and direction handled via 1-val
    score = clamp01(score)
    explanations = [exp for val, w, exp in active if val >= 0.6]  # highlight strong contributors
    return score, explanations

def tempo_factor(normalized_tempo: Optional[float], target: str) -> Optional[float]:
    """Map normalized tempo 0-1 to factor for target band."""
    if normalized_tempo is None:
        return None
    if target == "high":
        return normalized_tempo
    if target == "low":
        return 1 - normalized_tempo
    if target == "mid":
        # peak at 0.5
        return 1 - abs(normalized_tempo - 0.5) * 2
    return normalized_tempo
