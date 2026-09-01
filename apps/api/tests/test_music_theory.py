"""M5 - music theory comprehensive tests."""
import pytest

from app.music_theory.keys import normalize_key, CanonicalKey, ENHARMONIC_MAP
from app.music_theory.camelot import canonical_to_camelot, camelot_to_canonical, all_camelot_codes, all_canonical_keys
from app.music_theory.compatibility import compatibility, compatibility_for_keys, is_half_or_double_bpm, SCORES


# ---- canonical keys ----
@pytest.mark.parametrize("raw,expected_display", [
    ("C major", "C major"),
    ("C minor", "C minor"),
    ("C# major", "C# major"),
    ("C# minor", "C# minor"),
    ("Db major", "C# major"),  # enharmonic
    ("Eb minor", "D# minor"),
    ("Gb major", "F# major"),
    ("Ab minor", "G# minor"),
    ("Bb major", "A# major"),
    ("F#m", "F# minor"),
    ("Bb minor", "A# minor"),
    ("Db minor", "C# minor"),
    ("Cb major", "B major"),  # rare
])
def test_enharmonic_normalization(raw, expected_display):
    ck = normalize_key(raw)
    assert ck is not None
    assert ck.display == expected_display


def test_all_24_canonical_keys_parse():
    keys = all_canonical_keys()
    assert len(keys) == 24
    for k in keys:
        ck = normalize_key(k)
        assert ck is not None, f"key {k} failed"
        assert ck.display == k


@pytest.mark.parametrize("raw", [None, "", "  ", "Z major", "H minor", "C major7", "invalid"])
def test_malformed_key_returns_none(raw):
    assert normalize_key(raw) is None
    assert canonical_to_camelot(raw) is None


def test_null_key():
    assert normalize_key(None) is None
    assert canonical_to_camelot(None) is None


def test_major_minor_distinction():
    assert normalize_key("C major").mode == "major"
    assert normalize_key("C minor").mode == "minor"
    assert canonical_to_camelot("C major").code == "8B"
    assert canonical_to_camelot("C minor").code == "5A"
    assert canonical_to_camelot("C major").code != canonical_to_camelot("C minor").code


# ---- Camelot mapping 24/24 ----
EXPECTED_CAMELOT = {
    "G# minor": "1A", "B major": "1B",
    "D# minor": "2A", "F# major": "2B",
    "A# minor": "3A", "C# major": "3B",
    "F minor": "4A", "G# major": "4B",
    "C minor": "5A", "D# major": "5B",
    "G minor": "6A", "A# major": "6B",
    "D minor": "7A", "F major": "7B",
    "A minor": "8A", "C major": "8B",
    "E minor": "9A", "G major": "9B",
    "B minor": "10A", "D major": "10B",
    "F# minor": "11A", "A major": "11B",
    "C# minor": "12A", "E major": "12B",
}

@pytest.mark.parametrize("canonical,expected_code", list(EXPECTED_CAMELOT.items()))
def test_camelot_mapping(canonical, expected_code):
    cam = canonical_to_camelot(canonical)
    assert cam is not None
    assert cam.code == expected_code
    assert cam.number == int(expected_code[:-1])
    assert cam.letter == expected_code[-1]


def test_all_camelot_codes_count():
    codes = all_camelot_codes()
    assert len(codes) == 24
    for code in codes:
        assert camelot_to_canonical(code) is not None


@pytest.mark.parametrize("code,expected_canonical", [("8B","C major"),("8A","A minor"),("9B","G major"),("10A","B minor")])
def test_examples_from_spec(code, expected_canonical):
    assert camelot_to_canonical(code) == expected_canonical
    assert canonical_to_camelot(expected_canonical).code == code


def test_camelot_roundtrip():
    for canonical, code in EXPECTED_CAMELOT.items():
        assert camelot_to_canonical(code) == canonical
        assert canonical_to_camelot(canonical).code == code


# ---- Compatibility scoring ----
def test_same_key_score():
    c = compatibility("8A", "8A")
    assert c.score == 100
    assert c.relationship == "same_key"

def test_relative_major_minor():
    c = compatibility("8A", "8B")
    assert c.score == SCORES["relative_major_minor"] == 95
    assert c.relationship == "relative_major_minor"
    # reverse also relative
    c2 = compatibility("8B", "8A")
    assert c2.score == 95

def test_adjacent_camelot():
    c = compatibility("8A", "9A")
    assert c.score == 90
    assert c.relationship == "adjacent_camelot"
    c2 = compatibility("8A", "7A")
    assert c2.score == 90
    # wrap-around
    assert compatibility("12A", "1A").score == 90
    assert compatibility("1B", "12B").score == 90

def test_incompatible():
    c = compatibility("8A", "2B")
    assert c.score == 0
    assert c.relationship == "incompatible"

def test_diagonal():
    c = compatibility("8A", "9B")
    assert c.score == 70
    assert c.relationship == "diagonal"

def test_compatibility_for_keys():
    c = compatibility_for_keys("C major", "A minor")  # 8B vs 8A relative
    assert c.score == 95
    c2 = compatibility_for_keys("  Db major ", "C# major")  # enharmonic same
    assert c2.score == 100


def test_malformed_compatibility_returns_incompatible():
    c = compatibility("invalid", "8A")
    assert c.score == 0
    c2 = compatibility(None, "8A")
    assert c2.score == 0
    c3 = compatibility_for_keys(None, "C major")
    assert c3.score == 0


# ---- Half/double BPM helper ----
@pytest.mark.parametrize("a,b,expected", [
    (70, 140, "half"),
    (140, 70, "double"),
    (75, 150, "half"),
    (87, 174, "half"),
    (174, 87, "double"),
    (120, 121, None),
    (100, 100, None),
    (None, 120, None),
])
def test_half_double_helper(a, b, expected):
    assert is_half_or_double_bpm(a, b) == expected


# ---- Derived provenance ----
def test_camelot_derived_provenance(session):
    from app.models import Track, TrackAttribute
    import json
    from app.library import musical_attributes_for
    t = Track(canonical_title="x")
    session.add(t); session.flush()
    # Add musical_key as G# minor -> should derive 1A
    from app.enrichment.persistence import persist_enrichment
    from app.enrichment import EnrichmentResult
    res = EnrichmentResult(source="soundcharts", status="matched", tempo_bpm=140.0, musical_key="G# minor", confidence=None, source_identifier="u")
    persist_enrichment(session, track_id=t.id, result=res, source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    out = musical_attributes_for(session, [t.id])
    cam = out[t.id]["camelot"]
    assert cam is not None
    assert cam["value"] == "1A"
    assert cam["source"] == "aion_music_theory"
    assert cam["analysis_version"] == "m5-camelot-v1"
    assert cam["derived_from"] == "musical_key"


def test_missing_key_camelot_none(session):
    from app.models import Track
    from app.library import musical_attributes_for
    t = Track(canonical_title="y")
    session.add(t); session.flush()
    session.commit()
    out = musical_attributes_for(session, [t.id])
    assert out[t.id]["camelot"] is None


# ---- API serialization (derive, not persist) ----
def test_api_exposes_camelot(session):
    from app.library import list_tracks, ListParams
    from app.models import ProviderTrack, Track
    import json
    from app.enrichment.persistence import persist_enrichment
    from app.enrichment import EnrichmentResult
    t = Track(canonical_title="api")
    session.add(t); session.flush()
    pt = ProviderTrack(track_id=t.id, provider="spotify", provider_track_id="sp-api", raw_title="api", artist_display="A", raw_metadata='{"artists":[{"name":"A"}]}')
    session.add(pt); session.flush()
    res = EnrichmentResult(source="soundcharts", status="matched", tempo_bpm=120.0, musical_key="C major", confidence=None, source_identifier="u")
    persist_enrichment(session, track_id=t.id, result=res, source_type="catalog_api", source_name="soundcharts", analysis_version="m4c-soundcharts-v1")
    session.commit()
    page = list_tracks(session, params=ListParams(page=1, page_size=50))
    item = next(i for i in page.items if i.track_id == t.id)
    assert item.musical_attributes["camelot"]["value"] == "8B"
    assert item.musical_attributes["camelot"]["source"] == "aion_music_theory"
