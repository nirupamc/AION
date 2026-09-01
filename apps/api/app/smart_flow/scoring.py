"""Sequence-level scoring for Smart Flow."""
from __future__ import annotations
from typing import Any, Optional

# Energy profiles per shape, normalized 0-1
def target_energy_profile(shape: str, n: int) -> list[float]:
    shape = (shape or "maintain").lower()
    if n <=0:
        return []
    if shape == "maintain":
        return [0.6]*n
    if shape == "build":
        # linear 0.45 -> 0.85
        return [0.45 + (0.85-0.45)*i/(n-1) if n>1 else 0.6 for i in range(n)]
    if shape == "drop":
        return [0.85 - (0.85-0.45)*i/(n-1) if n>1 else 0.6 for i in range(n)]
    if shape == "peak_middle":
        mid=n//2
        out=[]
        for i in range(n):
            if i <= mid:
                out.append(0.5 + 0.4*i/mid if mid!=0 else 0.5)
            else:
                out.append(0.9 -0.4*(i-mid)/(n-1-mid) if (n-1-mid)!=0 else 0.5)
        return out
    if shape == "peak_end":
        return [0.4 + (0.9-0.4)*i/(n-1) if n>1 else 0.6 for i in range(n)]
    if shape == "wave":
        import math
        out=[]
        for i in range(n):
            # sine wave 0.6 + 0.25*sin(2*pi*i/(n-1) - pi/2) to start low
            if n==1:
                out.append(0.6)
            else:
                val = 0.6 + 0.25*math.sin(2*math.pi*i/(n-1) - math.pi/2) + 0.1*math.sin(4*math.pi*i/(n-1))
                out.append(max(0, min(1, val)))
        return out
    # default maintain
    return [0.6]*n

def sequence_energy_score(actual: list[Optional[float]], target: list[float]) -> tuple[int, float]:
    if not actual or not target or len(actual)!=len(target):
        return 0, 1.0
    # compute mean absolute error for non-None actual
    errs=[]
    for a,t in zip(actual,target):
        if a is None:
            continue
        errs.append(abs(a - t))
    if not errs:
        return 0, 1.0
    mae = sum(errs)/len(errs)
    score = int(round(max(0, 100 - mae*100)))
    return score, mae

# Sequence weights: mean transition 0.5, min 0.3, energy shape 0.2? Need sum 1
# Use 0.6 mean +0.3 min +0.1 energy? But we have artist penalty separate subtract.
# We'll define central weights:
SEQ_WEIGHTS = {
    "mean_transition": 0.5,
    "min_transition": 0.3,
    "energy_shape": 0.2,
}
# Sum 1.0 (0.5+0.3+0.2=1.0)

def overall_sequence_score(mean_transition: Optional[float], min_transition: Optional[int], energy_shape_score: int) -> int:
    # mean may be None if only one track? Then overall based on energy only?
    if mean_transition is None:
        mean_transition = 0
    if min_transition is None:
        min_transition = mean_transition or 0
    # weighted
    total = mean_transition * SEQ_WEIGHTS["mean_transition"] + min_transition * SEQ_WEIGHTS["min_transition"] + energy_shape_score * SEQ_WEIGHTS["energy_shape"]
    return int(round(max(0, min(100, total))))
