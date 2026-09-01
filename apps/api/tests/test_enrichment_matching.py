"""Tests for the candidate-matching helpers used by GetSongBPM."""
from __future__ import annotations

import pytest

from app.enrichment.matching import (
    artist_names_match,
    duration_close,
    has_preserved_version_marker,
    normalize_title_for_match,
    title_similarity,
    version_tokens,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Acid Trip", "acid trip"),
        ("Acid  Trip!!", "acid trip"),
        ("café", "cafe"),
        ("Café", "cafe"),
        ("  Spaces  Around  ", "spaces around"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_title_for_match(raw, expected):
    assert normalize_title_for_match(raw) == expected


def test_version_tokens_picks_remix_edit_mix_live_acoustic():
    norm = version_tokens("Acid Trip - Out of Orbit & Sasi Remix")
    assert "remix" in norm


def test_version_tokens_empty_when_no_marker():
    assert version_tokens("Acid Trip") == set()


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Acid Trip (Radio Edit)", True),
        ("Song - Live", True),
        ("Song", False),
        ("", False),
        (None, False),
    ],
)
def test_has_preserved_version_marker(text, expected):
    assert has_preserved_version_marker(text) is expected


def test_title_similarity_identical_strings():
    assert title_similarity("Acid Trip", "Acid Trip") == pytest.approx(1.0)


def test_title_similarity_partial_overlap():
    sim = title_similarity("Acid Trip Original", "Acid Voyage")
    assert 0 < sim < 1


def test_title_similarity_recognizes_token_reordering_as_strong():
    """Same tokens in different order should be considered a strong match."""
    sim = title_similarity("Acid Trip", "Trip Acid")
    assert sim == pytest.approx(1.0)


def test_title_similarity_disjoint_returns_zero():
    assert title_similarity("foo bar", "baz qux") == 0.0


def test_title_similarity_empty_returns_zero():
    assert title_similarity("", "foo") == 0.0
    assert title_similarity("foo", "") == 0.0
    assert title_similarity(None, "foo") == 0.0


def test_artist_names_match_exact_returns_full_score():
    ok, score = artist_names_match(["AC/DC"], ["AC/DC"])
    assert ok is True
    assert score == pytest.approx(1.0)


def test_artist_names_match_case_diacritic_insensitive():
    ok, score = artist_names_match(["Café"], ["cafe"])
    assert ok is True
    assert score == pytest.approx(1.0)


def test_artist_names_match_disjoint_returns_false():
    ok, score = artist_names_match(["A"], ["B"])
    assert ok is False
    assert score == 0.0


def test_artist_names_match_partial_overlap():
    ok, score = artist_names_match(["A", "B"], ["A", "C"])
    assert ok is True
    # 1 of 2 AION artists overlap → 0.5
    assert score == pytest.approx(0.5)


@pytest.mark.parametrize(
    "a,b,tol,expected",
    [
        (200000, 200000, 8000, True),
        (200000, 205000, 8000, True),
        (200000, 220000, 8000, False),
        (None, 200000, 8000, True),
        (200000, None, 8000, True),
    ],
)
def test_duration_close(a, b, tol, expected):
    assert duration_close(a, b, tolerance_ms=tol) is expected