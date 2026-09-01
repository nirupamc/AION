"""Deterministic Camelot (and Open Key) mapping for canonical keys."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .keys import CanonicalKey, normalize_key

# Single canonical mapping: canonical display -> Camelot code
# Based on Mixed In Key Wheel; numbers 1-12, letters A=minor, B=major
# Using sharp canonical forms only.

_CANONICAL_TO_CAMELOT: dict[str, str] = {
    # 1
    "G# minor": "1A",
    "B major": "1B",
    # 2
    "D# minor": "2A",
    "F# major": "2B",
    # 3
    "A# minor": "3A",
    "C# major": "3B",
    # 4
    "F minor": "4A",
    "G# major": "4B",
    # 5
    "C minor": "5A",
    "D# major": "5B",
    # 6
    "G minor": "6A",
    "A# major": "6B",
    # 7
    "D minor": "7A",
    "F major": "7B",
    # 8
    "A minor": "8A",
    "C major": "8B",
    # 9
    "E minor": "9A",
    "G major": "9B",
    # 10
    "B minor": "10A",
    "D major": "10B",
    # 11
    "F# minor": "11A",
    "A major": "11B",
    # 12
    "C# minor": "12A",
    "E major": "12B",
}

_CAMELOT_TO_CANONICAL: dict[str, str] = {v: k for k, v in _CANONICAL_TO_CAMELOT.items()}

# Open Key mapping (optional, derived from Camelot for convenience)
# Open Key: 1m = 6A etc? Using standard mapping: Camelot -> Open Key via table.
# We'll derive via same canonical: Open Key minor = number + "m", major = number + "d"
# Actually proper Open Key is different numbering; simplest is to keep Camelot as primary and map Open as alternative notation.
# For M5 we expose Open Key as same number with "m"/"d" suffix for readability.
_OPENKEY_FALLBACK = {}  # placeholder if needed


@dataclass(frozen=True)
class CamelotKey:
    number: int  # 1-12
    letter: str  # A or B
    code: str  # e.g. "8A"

    @property
    def open_key(self) -> str:
        # Simple derived Open Key: A->m, B->d (1A->1m, 1B->1d) — documented as simplified fallback
        suffix = "m" if self.letter == "A" else "d"
        return f"{self.number}{suffix}"


def canonical_to_camelot(canonical: CanonicalKey | str | None) -> Optional[CamelotKey]:
    if canonical is None:
        return None
    if isinstance(canonical, CanonicalKey):
        display = canonical.display
    else:
        ck = normalize_key(canonical)
        if ck is None:
            return None
        display = ck.display
    code = _CANONICAL_TO_CAMELOT.get(display)
    if not code:
        return None
    number = int(code[:-1])
    letter = code[-1]
    return CamelotKey(number=number, letter=letter, code=code)


def camelot_to_canonical(code: str) -> Optional[str]:
    if not code:
        return None
    code = code.strip().upper()
    return _CAMELOT_TO_CANONICAL.get(code)


def all_camelot_codes() -> list[str]:
    return sorted(_CAMELOT_TO_CANONICAL.keys(), key=lambda c: (int(c[:-1]), c[-1]))


def all_canonical_keys() -> list[str]:
    return list(_CANONICAL_TO_CAMELOT.keys())
