"""Aggregation helpers for analytics."""
from __future__ import annotations
from typing import Any, Optional
import statistics

def avg(vals: list[float]) -> Optional[float]:
    if not vals:
        return None
    return round(sum(vals)/len(vals), 2)

def median(vals: list[float]) -> Optional[float]:
    if not vals:
        return None
    return round(statistics.median(vals), 2)

def min_max(vals: list[float]) -> tuple[Optional[float], Optional[float]]:
    if not vals:
        return None, None
    return round(min(vals),2), round(max(vals),2)

def dominant_range_bpm(bpms: list[float]) -> Optional[str]:
    if not bpms:
        return None
    # find 5-bpm bucket with most counts
    buckets = {}
    for b in bpms:
        bucket_start = int(b // 5 * 5)
        key = f"{bucket_start}-{bucket_start+4}"
        buckets[key] = buckets.get(key,0)+1
    if not buckets:
        return None
    return max(buckets, key=lambda k: buckets[k])

def distribution_counts(items: list[str]) -> list[dict[str,Any]]:
    from collections import Counter
    c = Counter(items)
    total = sum(c.values())
    out=[]
    for label, count in c.most_common():
        out.append({"label": label, "count": count, "percentage": round(count/total*100,1) if total else 0})
    return out
