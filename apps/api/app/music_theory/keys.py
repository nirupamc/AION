"""Canonical key model and enharmonic normalization."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Canonical pitch classes - sharps only, as used in M4 persistence
PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

ENHARMONIC_MAP = {
    "Db": "C#",
    "Eb": "D#",
    "Gb": "F#",
    "Ab": "G#",
    "Bb": "A#",
    # also handle rare flats like Cb, Fb
    "Cb": "B",
    "Fb": "E",
}

VALID_TONICS = set(PITCH_CLASSES)
VALID_MODES = {"major", "minor"}

_KEY_RE = re.compile(r"^\s*(?P<tonic>[A-Ga-g][#b]?)\s*(?P<mode>major|minor|maj|min|m)?\s*$", re.IGNORECASE)

MODE_ALIASES = {
    "m": "minor",
    "min": "minor",
    "minor": "minor",
    "maj": "major",
    "major": "major",
}


@dataclass(frozen=True)
class CanonicalKey:
    tonic: str  # e.g. "C#"
    mode: str  # "major" or "minor"
    display: str  # "C# minor"

    @property
    def tonic_mode(self) -> tuple[str, str]:
        return (self.tonic, self.mode)


def normalize_key(raw: Optional[str] | Optional[dict]) -> Optional[CanonicalKey]:
    """Parse raw key into CanonicalKey or None.

    Accepts:
      - "C major", "F# minor", "Bb major", "C", "Am"
      - dict {"tonic":"C#","mode":"minor","display":"C# minor"}
    Canonicalizes enharmonics to sharps (Db->C# etc) and normalizes mode.
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        # dict from TrackAttribute value_json
        tonic = raw.get("tonic")
        mode = raw.get("mode")
        if not tonic:
            return None
        # mode may be None for tonic-only
        tonic = str(tonic).strip()
        tonic = _canonical_tonic(tonic)
        if tonic not in VALID_TONICS:
            return None
        if mode is None:
            # tonic-only without mode cannot be mapped to camelot; treat as None for M5
            return None
        mode = str(mode).strip().lower()
        mode = MODE_ALIASES.get(mode, mode)
        if mode not in VALID_MODES:
            return None
        return CanonicalKey(tonic=tonic, mode=mode, display=f"{tonic} {mode}")
    s = str(raw).strip()
    if not s:
        return None
    # Handle trailing "m" shorthand like "Am", "F#m"
    # If no space and ends with m/M but not 'major', treat as minor
    # This catches GetSongBPM "F#m" etc already handled but we also support it
    m = _KEY_RE.match(s)
    if not m:
        return None
    tonic_raw = m.group("tonic")
    mode_raw = m.group("mode") or ""
    tonic = _canonical_tonic(tonic_raw[0].upper() + tonic_raw[1:] if len(tonic_raw) > 1 else tonic_raw[0].upper())
    if tonic not in VALID_TONICS:
        return None
    if not mode_raw:
        # No mode => cannot produce camelot, treat as None
        return None
    mode = MODE_ALIASES.get(mode_raw.lower(), mode_raw.lower())
    if mode not in VALID_MODES:
        return None
    return CanonicalKey(tonic=tonic, mode=mode, display=f"{tonic} {mode}")


def _canonical_tonic(tonic: str) -> str:
    # preserve case: first letter uppercase, second char as-is then map
    if len(tonic) == 0:
        return tonic
    # Normalize first letter uppercase
    t = tonic[0].upper() + tonic[1:] if len(tonic) > 1 else tonic.upper()
    return ENHARMONIC_MAP.get(t, t)


def key_to_display(canonical: CanonicalKey | None) -> Optional[str]:
    return canonical.display if canonical else None
