"""Histograms for BPM and energy."""
from __future__ import annotations
from typing import Any

def bpm_histogram(bpms: list[float], bucket_size: int = 5) -> list[dict[str,Any]]:
    if not bpms:
        return []
    min_b = int(min(bpms) // bucket_size * bucket_size)
    max_b = int(max(bpms) // bucket_size * bucket_size)
    buckets = []
    for start in range(min_b, max_b+1, bucket_size):
        end = start + bucket_size -1
        count = sum(1 for b in bpms if start <= b <= end)
        buckets.append({"min": start, "max": end, "count": count, "label": f"{start}-{end}"})
    # filter zero? keep all for visual consistency but frontend can hide zero
    return buckets

def energy_histogram(energies: list[float], step: float = 0.1) -> list[dict[str,Any]]:
    if not energies:
        return []
    buckets=[]
    for i in range(10):
        low = round(i*step,1)
        high = round((i+1)*step,1)
        count = sum(1 for e in energies if low <= e < high or (high==1.0 and e==1.0))
        buckets.append({"min": low, "max": high, "count": count, "label": f"{low:.1f}-{high:.1f}"})
    return buckets
