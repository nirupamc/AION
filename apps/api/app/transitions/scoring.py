"""Central transition scoring v1."""
from __future__ import annotations
from typing import Any, Optional
import math

from app.music_theory.compatibility import compatibility as harmonic_compat, is_half_or_double_bpm
from .models import TransitionTrackFeatures

# Central weights — sum to 1.0
WEIGHTS: dict[str, float] = {
    "harmonic": 0.30,
    "tempo": 0.25,
    "energy": 0.20,
    "vibe": 0.10,
    "mood": 0.10,
    "set_role": 0.05,
}

# Thresholds
BPM_THRESHOLDS = {
    "excellent": 2.0,  # %
    "good": 4.0,
    "usable": 6.0,
}

SET_ROLE_ADJACENCY: dict[tuple[str, str], int] = {
    ("warmup","warmup"): 90,
    ("warmup","build"): 90,
    ("build","build"): 85,
    ("build","peak"): 90,
    ("peak","peak"): 80,
    ("peak","cooldown"): 85,
    ("build","warmup"): 70,
    ("peak","build"): 60,
    ("warmup","peak"): 30,
    ("cooldown","warmup"): 70,
    ("cooldown","cooldown"): 80,
    ("warmup","cooldown"): 50,
    ("cooldown","peak"): 40,
    ("cooldown","build"): 60,
}

def harmonic_score(src: TransitionTrackFeatures, dst: TransitionTrackFeatures) -> tuple[Optional[int], str]:
    if not src.camelot or not dst.camelot:
        return None, "missing key"
    comp = harmonic_compat(src.camelot, dst.camelot)
    return comp.score, comp.relationship

def tempo_score(src: TransitionTrackFeatures, dst: TransitionTrackFeatures) -> tuple[Optional[int], str, Optional[str]]:
    a = src.tempo_bpm
    b = dst.tempo_bpm
    if a is None or b is None or a <=0 or b<=0:
        return None, "missing bpm", None
    # check half/double
    hd = is_half_or_double_bpm(a, b)
    pct = abs(a - b) / ((a+b)/2) * 100 if (a+b)!=0 else 100
    # if half/double, compute normalized pct after adjusting
    if hd is not None:
        # normalize: if b is double a, compare a vs b/2
        if hd == "half":  # a is half of b? Actually a 70, b 140 -> a half, b double; our helper returns half when a half of b
            # For half case, effective diff after halving b
            eff_pct = abs(a - b/2) / ((a + b/2)/2) * 100 if (a+b/2)!=0 else 100
        else: # double
            eff_pct = abs(a - b*2) / ((a + b*2)/2) * 100 if (a+b*2)!=0 else 100
        # half/double not perfect, give 75 baseline minus diff
        if eff_pct <= 2:
            return 75, f"half/double related ({hd}) {pct:.1f}%", hd
        elif eff_pct <= 6:
            return 60, f"half/double related ({hd}) {pct:.1f}%", hd
        else:
            return 40, f"half/double related ({hd}) {pct:.1f}%", hd
    # normal scoring
    if pct <= 2:
        score = 100 - pct*2  # 100 to 96
    elif pct <= 4:
        score = 96 - (pct-2)*2  # 96 to 92
    elif pct <= 6:
        score = 92 - (pct-4)*11  # 92 to 70
    elif pct <= 15:
        score = 70 - (pct-6)*3.33  # 70 to 40
    else:
        score = max(0, 40 - (pct-15)*1.3)
    score = int(round(max(0, min(100, score))))
    # label
    if pct <=2:
        label = f"+{pct:.1f}% excellent"
    elif pct <=4:
        label = f"+{pct:.1f}% good"
    elif pct <=6:
        label = f"+{pct:.1f}% usable"
    else:
        label = f"{pct:.1f}% large gap"
    return score, label, hd

def energy_score(src: TransitionTrackFeatures, dst: TransitionTrackFeatures, intent: str = "maintain") -> tuple[Optional[int], str]:
    a = src.energy
    b = dst.energy
    if a is None or b is None:
        return None, "missing energy"
    delta = b - a  # positive means build
    intent = intent.lower() if intent else "maintain"
    if intent == "maintain":
        # ideal 0, score 100 - abs(delta)*150
        score = 100 - abs(delta)*150
        desc = f"{delta:+.2f} maintain" if delta !=0 else "steady"
    elif intent == "build":
        # ideal +0.12
        preferred = 0.12
        score = 100 - abs(delta - preferred)*120
        # penalize drop
        if delta < -0.05:
            score -= 20
        desc = f"{delta:+.2f} build (ideal +0.12)"
    elif intent == "drop":
        preferred = -0.12
        score = 100 - abs(delta - preferred)*120
        if delta > 0.05:
            score -= 20
        desc = f"{delta:+.2f} drop (ideal -0.12)"
    else:
        score = 100 - abs(delta)*150
        desc = f"{delta:+.2f}"
    score = int(round(max(0, min(100, score))))
    return score, desc

def _cosine_similarity(scores_a: dict[str,float], scores_b: dict[str,float], labels: list[str]) -> Optional[float]:
    # Build vectors in label order, missing = 0
    vec_a = [scores_a.get(l, 0.0) for l in labels]
    vec_b = [scores_b.get(l, 0.0) for l in labels]
    # if both zero, no evidence
    if all(v==0 for v in vec_a) and all(v==0 for v in vec_b):
        return None
    dot = sum(x*y for x,y in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(x*x for x in vec_a))
    norm_b = math.sqrt(sum(y*y for y in vec_b))
    if norm_a ==0 or norm_b==0:
        return None
    cos = dot / (norm_a * norm_b)
    # cos 0-1 -> score 0-100
    return max(0, min(1, cos))

MOOD_LABELS = ["euphoric","happy","dark","melancholic","calm","intense","uplifting","aggressive"]
VIBE_LABELS = ["driving","hypnotic","psychedelic","groovy","atmospheric","organic","peak_time","warmup","chill","vocal"]

def mood_score(src: TransitionTrackFeatures, dst: TransitionTrackFeatures) -> tuple[Optional[int], str]:
    if not src.mood_scores and not dst.mood_scores:
        return None, "missing mood"
    sim = _cosine_similarity(src.mood_scores, dst.mood_scores, MOOD_LABELS)
    if sim is None:
        return None, "missing mood"
    score = int(round(sim*100))
    # fallback to dominant equality boost
    if src.dominant_mood and dst.dominant_mood and src.dominant_mood == dst.dominant_mood:
        score = min(100, score + 5)
    return score, f"cosine {sim:.2f}"

def vibe_score(src: TransitionTrackFeatures, dst: TransitionTrackFeatures) -> tuple[Optional[int], str]:
    if not src.vibe_scores and not dst.vibe_scores:
        return None, "missing vibe"
    sim = _cosine_similarity(src.vibe_scores, dst.vibe_scores, VIBE_LABELS)
    if sim is None:
        return None, "missing vibe"
    score = int(round(sim*100))
    if src.dominant_vibe and dst.dominant_vibe and src.dominant_vibe == dst.dominant_vibe:
        score = min(100, score + 5)
    return score, f"cosine {sim:.2f}"

def set_role_score(src: TransitionTrackFeatures, dst: TransitionTrackFeatures) -> tuple[Optional[int], str]:
    a = (src.set_role or "").lower() if src.set_role else None
    b = (dst.set_role or "").lower() if dst.set_role else None
    if not a or not b:
        return None, "missing set_role"
    key = (a,b)
    if key in SET_ROLE_ADJACENCY:
        return SET_ROLE_ADJACENCY[key], f"{a}→{b}"
    # fallback: same role 80, otherwise 50
    if a == b:
        return 80, f"{a}→{b} same"
    return 50, f"{a}→{b}"

def loudness_warning(src: TransitionTrackFeatures, dst: TransitionTrackFeatures) -> Optional[str]:
    if src.loudness_db is None or dst.loudness_db is None:
        return None
    diff = dst.loudness_db - src.loudness_db
    if abs(diff) > 3:
        return f"loudness {diff:+.1f} dB"
    return None

def danceability_warning(src: TransitionTrackFeatures, dst: TransitionTrackFeatures) -> Optional[str]:
    if src.danceability is None or dst.danceability is None:
        return None
    diff = abs(dst.danceability - src.danceability)
    if diff > 0.3:
        return f"danceability shift {diff:.2f}"
    return None
