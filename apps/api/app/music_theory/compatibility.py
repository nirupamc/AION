"""Harmonic compatibility rules and BPM half/double helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Literal

from .camelot import CamelotKey, canonical_to_camelot

Relationship = Literal["same_key", "relative_major_minor", "adjacent_camelot", "energy_boost", "energy_drop", "incompatible"]

# Central score definitions — do not scatter magic numbers
SCORES: dict[str, int] = {
    "same_key": 100,
    "relative_major_minor": 95,
    "adjacent_camelot": 90,
    "energy_boost": 85,  # +1 with valid transition (e.g. 8A->9A considered boost if desired)
    "energy_drop": 85,
    "incompatible": 0,
    # diagonal relative+adjacent (e.g. 8A->9B) is less compatible but still workable
    "diagonal": 70,
}


@dataclass(frozen=True)
class Compatibility:
    score: int
    relationship: str
    from_code: Optional[str]
    to_code: Optional[str]


def compatibility(from_camelot: str | CamelotKey | None, to_camelot: str | CamelotKey | None) -> Compatibility:
    """Deterministic compatibility between two Camelot codes."""
    def _norm(c):
        if c is None:
            return None
        if isinstance(c, CamelotKey):
            return c
        s = str(c).strip().upper()
        if len(s) < 2:
            return None
        try:
            num = int(s[:-1])
            let = s[-1]
            if let not in ("A", "B") or not (1 <= num <= 12):
                return None
            return CamelotKey(number=num, letter=let, code=s)
        except:  # noqa
            return None

    a = _norm(from_camelot)
    b = _norm(to_camelot)
    if a is None or b is None:
        return Compatibility(score=0, relationship="incompatible", from_code=getattr(a, "code", None), to_code=getattr(b, "code", None))

    if a.code == b.code:
        return Compatibility(score=SCORES["same_key"], relationship="same_key", from_code=a.code, to_code=b.code)

    # relative major/minor: same number, different letter
    if a.number == b.number and a.letter != b.letter:
        return Compatibility(score=SCORES["relative_major_minor"], relationship="relative_major_minor", from_code=a.code, to_code=b.code)

    # adjacent same-mode (perfect fifth on wheel): same letter, number +/-1 with wrap
    if a.letter == b.letter and _is_adjacent(a.number, b.number):
        # classify boost/drop by direction (higher number = boost in wheel direction)
        # but score same 90
        rel = "adjacent_camelot"
        # Optionally distinguish boost/drop
        # if b.number == _next(a.number): rel = "energy_boost" etc — keep adjacent for now
        return Compatibility(score=SCORES["adjacent_camelot"], relationship=rel, from_code=a.code, to_code=b.code)

    # diagonal: same as relative+adjacent (e.g. 8A -> 9B): one step number + letter flip
    if _is_adjacent(a.number, b.number) and a.letter != b.letter:
        return Compatibility(score=SCORES["diagonal"], relationship="diagonal", from_code=a.code, to_code=b.code)

    # energy boost/drop variants could be +2 steps (not implemented as separate rule for M5)
    return Compatibility(score=SCORES["incompatible"], relationship="incompatible", from_code=a.code, to_code=b.code)


def _is_adjacent(n1: int, n2: int) -> bool:
    diff = abs(n1 - n2)
    return diff == 1 or diff == 11  # wrap 12<->1


def is_half_or_double_bpm(bpm_a: float | None, bpm_b: float | None, tolerance: float = 0.06) -> Optional[str]:
    """Helper to detect half/double tempo relationships.

    Returns "half", "double", or None. Tolerance is relative (6% default).
    """
    if bpm_a is None or bpm_b is None:
        return None
    try:
        a = float(bpm_a)
        b = float(bpm_b)
    except:
        return None
    if a <= 0 or b <= 0:
        return None
    ratio = a / b if b != 0 else 0
    if abs(ratio - 2.0) <= tolerance * 2:  # allow absolute tolerance scaled
        # a ≈ 2*b => a is double of b
        if abs(a - 2*b) / (2*b) <= tolerance:
            return "double"
    if abs(ratio - 0.5) <= tolerance:
        if abs(a - 0.5*b) / (0.5*b) <= tolerance:
            return "half"
    # also check reciprocal
    if abs(b - 2*a) / (2*a) <= tolerance:
        return "half"
    if abs(b - 0.5*a) / (0.5*a) <= tolerance:
        return "double"
    return None


# Convenience: support canonical key strings directly
def compatibility_for_keys(key_a: str | None, key_b: str | None) -> Compatibility:
    ca = canonical_to_camelot(key_a)
    cb = canonical_to_camelot(key_b)
    if ca is None or cb is None:
        return Compatibility(score=0, relationship="incompatible", from_code=getattr(ca, "code", None), to_code=getattr(cb, "code", None))
    return compatibility(ca.code, cb.code)
