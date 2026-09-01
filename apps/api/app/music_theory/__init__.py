"""Provider-independent music theory domain for M5."""
from .keys import CanonicalKey, normalize_key, PITCH_CLASSES, ENHARMONIC_MAP
from .camelot import CamelotKey, canonical_to_camelot, camelot_to_canonical, all_camelot_codes
from .compatibility import compatibility, compatibility_for_keys, is_half_or_double_bpm, SCORES

__all__ = [
    "CanonicalKey",
    "normalize_key",
    "PITCH_CLASSES",
    "ENHARMONIC_MAP",
    "CamelotKey",
    "canonical_to_camelot",
    "camelot_to_canonical",
    "all_camelot_codes",
    "compatibility",
    "compatibility_for_keys",
    "is_half_or_double_bpm",
    "SCORES",
]
