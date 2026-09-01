"""Enrichment source abstraction for M3 evaluation.

This package defines the lightweight interface used to evaluate external
sources for BPM/key enrichment. It does NOT write production TrackAttribute
rows; evaluation results are stored in separate artifacts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

# ---- query / result models ----

PITCH_CLASSES = [
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"
]


@dataclass(frozen=True)
class EnrichmentQuery:
    """Normalized identity for an enrichment lookup."""

    track_id: int
    isrc: Optional[str] = None
    musicbrainz_recording_id: Optional[str] = None
    provider: str = "spotify"
    provider_track_id: Optional[str] = None
    title: Optional[str] = None
    artists: list[str] = field(default_factory=list)
    album: Optional[str] = None
    duration_ms: Optional[int] = None


@dataclass(frozen=True)
class EnrichmentResult:
    """Outcome of a single enrichment source lookup."""

    source: str
    status: str  # matched | no_match | ambiguous | error | deferred
    tempo_bpm: Optional[float] = None
    musical_key: Optional[str] = None  # normalized "Tonic mode", e.g. "A minor"
    confidence: Optional[float] = None
    source_identifier: Optional[str] = None
    match_evidence: dict[str, Any] = field(default_factory=dict)
    raw: Optional[dict[str, Any]] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    http_status: Optional[int] = None


@runtime_checkable
class EnrichmentSource(Protocol):
    """Minimal interface for an enrichment evaluation source."""

    name: str

    async def lookup(self, query: EnrichmentQuery) -> EnrichmentResult:
        ...


# ---- normalization helpers ----

def normalize_bpm(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (ValueError, TypeError):
        return None
    if v <= 0 or v > 300:
        return None
    return round(v, 3)


def normalize_key(pitch_class: Any, mode: Any = None) -> Optional[str]:
    """Normalize Spotify-style key+mode into 'Tonic mode'.

    pitch_class: int 0-11 (0=C), or -1 for none.
    mode: int 0=minor, 1=major.
    """
    if pitch_class is None:
        return None
    try:
        pc = int(pitch_class)
    except (ValueError, TypeError):
        return None
    if pc < 0 or pc > 11:
        return None
    tonic = PITCH_CLASSES[pc]
    m = "major" if mode == 1 else "minor" if mode == 0 else None
    if m:
        return f"{tonic} {m}"
    return tonic


def key_agreement(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Compare two normalized keys and return a relationship label."""
    if a is None or b is None:
        return None
    if a == b:
        return "exact"
    # relative major/minor check
    parts_a = a.split(" ")
    parts_b = b.split(" ")
    if len(parts_a) == 2 and len(parts_b) == 2:
        if parts_a[0] == parts_b[0] and parts_a[1] != parts_b[1]:
            return "relative"
    return "disagree"


# ---- aggregation ----

@dataclass
class EnrichmentAggregate:
    source: str
    queried: int = 0
    matched: int = 0
    no_match: int = 0
    ambiguous: int = 0
    error: int = 0
    deferred: int = 0
    bpm_present: int = 0
    key_present: int = 0
    both_present: int = 0
    latencies: list[float] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d = {
            "source": self.source,
            "queried": self.queried,
            "matched": self.matched,
            "no_match": self.no_match,
            "ambiguous": self.ambiguous,
            "error": self.error,
            "deferred": self.deferred,
            "bpm_present": self.bpm_present,
            "key_present": self.key_present,
            "both_present": self.both_present,
            "bpm_coverage": (self.bpm_present / self.matched) if self.matched else 0.0,
            "key_coverage": (self.key_present / self.matched) if self.matched else 0.0,
            "both_coverage": (self.both_present / self.matched) if self.matched else 0.0,
            "median_latency_ms": _median(self.latencies) if self.latencies else None,
        }
        return d


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2.0
