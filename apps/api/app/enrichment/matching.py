"""Shared normalization helpers for enrichment candidate matching.

GetSongBPM (and most catalog APIs) do not support exact-ISRC lookup. They
return title-based search results, so we have to match candidates conservatively
against the AION query. These helpers are intentionally framework-free so they
can be unit tested in isolation.

Design rules:
- Strip diacritics and lowercase.
- Keep important version tokens ("Remix", "Original Mix", "Radio Edit", ...).
- Collapse punctuation/whitespace so "Acid Trip" and "acid  trip!!" compare equal.
- Do NOT collapse two distinct version labels into the same string.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable

# Version tokens we want to PRESERVE during normalization. These are the
# strings most likely to disambiguate between two mixes of the same song.
PRESERVED_VERSION_TOKENS: tuple[str, ...] = (
    "remix",
    "original mix",
    "extended mix",
    "extended version",
    "radio edit",
    "club mix",
    "dub mix",
    "instrumental",
    "acapella",
    "live",
    "acoustic",
    "vip",
    "vip mix",
    "rework",
    "remaster",
    "remastered",
    "edit",
    "single edit",
    "album version",
    "deluxe",
    "remixed",
    "mix",
    "version",
)

# Parenthetical/bracketed version markers should still be retained in a
# normalized form. We do not strip "(Remix)" etc. because the candidate scoring
# below relies on these tokens for safety.

# Non-alphanumeric characters are collapsed to single spaces. The apostrophe is
# preserved (it carries meaning in titles like "Don't Stop").
_NON_ALNUM = re.compile(r"[^a-z0-9' ]+")
_MULTI_SPACE = re.compile(r"\s+")


def strip_diacritics(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_title_for_match(text: str | None) -> str:
    """Return a canonical form of ``text`` suitable for equality comparison.

    - Lowercased, diacritics removed.
    - Punctuation collapsed to single spaces.
    - Whitespace collapsed to single spaces and trimmed.
    - Version tokens preserved exactly as written.
    """
    if not text:
        return ""
    s = strip_diacritics(str(text)).lower()
    s = _NON_ALNUM.sub(" ", s)
    s = _MULTI_SPACE.sub(" ", s).strip()
    return s


def version_tokens(text: str | None) -> set[str]:
    """Return the set of preserved version tokens present in ``text``.

    Useful for cross-checking that an AION query and a candidate agree on
    important remix/edit/version information before accepting the match.
    """
    if not text:
        return set()
    norm = normalize_title_for_match(text)
    tokens: set[str] = set()
    for tok in PRESERVED_VERSION_TOKENS:
        if tok in norm:
            tokens.add(tok)
    return tokens


def artist_names_match(
    aion_artists: Iterable[str],
    candidate_artists: Iterable[str],
) -> tuple[bool, float]:
    """Compare artist name lists from AION and a provider candidate.

    Returns (overlap_ok, score).
      - overlap_ok is True when at least one normalized primary artist name
        appears in both sets.
      - score is the share of AION artists that have a matching candidate
        name (0.0..1.0). Equal-weight; no favorites.

    Both inputs are normalized via :func:`normalize_title_for_match` so
    diacritics/case/punctuation do not block matches.
    """
    aion_norm = {normalize_title_for_match(a) for a in aion_artists if a}
    cand_norm = {normalize_title_for_match(a) for a in candidate_artists if a}
    aion_norm.discard("")
    cand_norm.discard("")
    if not aion_norm or not cand_norm:
        return False, 0.0
    overlap = aion_norm & cand_norm
    if not overlap:
        return False, 0.0
    score = len(overlap) / len(aion_norm)
    return True, min(1.0, max(0.0, score))


def title_similarity(aion_title: str | None, candidate_title: str | None) -> float:
    """Token-overlap similarity in 0..1 between two normalized titles.

    Uses Jaccard similarity over whitespace-split tokens. Returns 0.0 if
    either side is empty.
    """
    a = normalize_title_for_match(aion_title)
    b = normalize_title_for_match(candidate_title)
    if not a or not b:
        return 0.0
    a_tokens = set(a.split(" "))
    b_tokens = set(b.split(" "))
    a_tokens.discard("")
    b_tokens.discard("")
    if not a_tokens or not b_tokens:
        return 0.0
    # Use containment ratio instead of pure Jaccard so that
    # "Acid Trip" vs "Trip Acid" (same tokens, different order)
    # is recognized as a strong match rather than partial.
    inter = a_tokens & b_tokens
    if not inter:
        return 0.0
    containment = len(inter) / min(len(a_tokens), len(b_tokens))
    jaccard = len(inter) / len(a_tokens | b_tokens)
    return max(containment, jaccard)


def duration_close(
    aion_ms: int | None, candidate_ms: int | None, *, tolerance_ms: int = 8000
) -> bool:
    """True when durations are within ``tolerance_ms`` of each other.

    Returns True if either side is missing (we don't punish the candidate
    when we have no duration to compare).
    """
    if aion_ms is None or candidate_ms is None:
        return True
    try:
        a = int(aion_ms)
        b = int(candidate_ms)
    except (ValueError, TypeError):
        return True
    return abs(a - b) <= tolerance_ms


def has_preserved_version_marker(text: str | None) -> bool:
    """True when ``text`` contains any preserved version token."""
    return bool(version_tokens(text))