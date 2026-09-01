"""Tests for the GetSongBPM enrichment source.

All tests use respx to mock httpx — no live API calls.
"""
from __future__ import annotations

import asyncio
import httpx
import pytest
import respx

from app.enrichment import EnrichmentQuery
from app.enrichment.sources.getsongbpm import (
    ACCEPT_SCORE,
    GetSongBPMEnrichmentSource,
    GetSongBPMAuthError,
    GetSongBPMError,
    GetSongBPMRateLimitError,
    _parse_key_of,
    _score_candidate,
    normalize_getsongbpm_key,
)


def _gsb_key_payload() -> list[dict]:
    # Search results use these per-song fields.
    return [
        {
            "song_id": "abc",
            "song_title": "Highway to Hell",
            "song_uri": "https://getsongbpm.com/song/highway-to-hell/abc",
            "tempo": "118",
            "time_sig": "4/4",
            "key_of": "A",
            "camelot": "11B",
            "artist": {"id": "qB3", "name": "AC/DC"},
        }
    ]


# --- construction ------------------------------------------------------------

def test_source_requires_api_key():
    with pytest.raises(ValueError):
        GetSongBPMEnrichmentSource(api_key="")


def test_source_uses_settings_base_url_when_none(monkeypatch):
    monkeypatch.setattr(
        "app.enrichment.sources.getsongbpm.settings.getsongbpm_base_url",
        "https://api.getsong.co",
        raising=False,
    )
    src = GetSongBPMEnrichmentSource(api_key="k")
    assert src._base == "https://api.getsong.co"


# --- key normalization -------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("F#m", ("F#", "minor")),
        ("C# minor", ("C#", "minor")),
        ("Bb major", ("A#", "major")),
        ("A major", ("A", "major")),
        ("C", ("C", None)),
        ("c", ("C", None)),
        ("Db", ("C#", None)),
        ("Garbage", (None, None)),
        ("", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_key_of(raw, expected):
    assert _parse_key_of(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("F#m", "F# minor"),
        ("C# minor", "C# minor"),
        ("Bb major", "A# major"),
        ("A major", "A major"),
        ("C", "C"),
        ("garbage", None),
    ],
)
def test_normalize_getsongbpm_key(raw, expected):
    assert normalize_getsongbpm_key(raw) == expected


# --- request construction ---------------------------------------------------

@pytest.mark.asyncio
async def test_search_uses_x_api_key_header(monkeypatch):
    captured: dict = {}

    def _transport(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["api_key_query"] = request.url.params.get("api_key")
        captured["x_api_key"] = request.headers.get("X-API-KEY")
        captured["type"] = request.url.params.get("type")
        captured["lookup"] = request.url.params.get("lookup")
        captured["limit"] = request.url.params.get("limit")
        return httpx.Response(200, json={"search": _gsb_key_payload()})

    src = GetSongBPMEnrichmentSource(api_key="secret-key", min_interval=0)
    with respx.mock(base_url="https://api.getsong.co") as router:
        router.get("/search/").mock(side_effect=_transport)
        router.get("/song/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "song": {
                        "id": "abc",
                        "title": "Highway to Hell",
                        "tempo": "118",
                        "key_of": "A major",
                        "artist": {"name": "AC/DC"},
                    }
                },
            )
        )
        result = await src.lookup(
            EnrichmentQuery(track_id=1, title="Highway to Hell", artists=["AC/DC"])
        )
    assert result.status == "matched"
    assert captured["path"] == "/search/"
    assert captured["api_key_query"] is None  # we do NOT use URL param auth
    assert captured["x_api_key"] == "secret-key"
    assert captured["type"] == "both"
    assert captured["lookup"] == "song:Highway to Hell artist:AC/DC"
    assert captured["limit"] == "10"


@pytest.mark.asyncio
async def test_lookup_returns_no_match_when_empty():
    src = GetSongBPMEnrichmentSource(api_key="k", min_interval=0)
    with respx.mock(base_url="https://api.getsong.co") as router:
        router.get("/search/").mock(return_value=httpx.Response(200, json={"search": []}))
        result = await src.lookup(
            EnrichmentQuery(track_id=1, title="Nothing", artists=["Nobody"])
        )
    assert result.status == "no_match"
    assert result.match_evidence["candidate_count"] == 0


@pytest.mark.asyncio
async def test_lookup_returns_deferred_when_no_title():
    src = GetSongBPMEnrichmentSource(api_key="k", min_interval=0)
    result = await src.lookup(EnrichmentQuery(track_id=1))
    assert result.status == "deferred"


@pytest.mark.asyncio
async def test_lookup_handles_provider_error_payload():
    src = GetSongBPMEnrichmentSource(api_key="k", min_interval=0)
    with respx.mock(base_url="https://api.getsong.co") as router:
        router.get("/search/").mock(
            return_value=httpx.Response(200, json={"search": {"error": "Invalid API key"}})
        )
        result = await src.lookup(
            EnrichmentQuery(track_id=1, title="x", artists=["y"])
        )
    assert result.status == "error"
    assert "Invalid API key" in (result.error or "")


@pytest.mark.asyncio
async def test_lookup_handles_401():
    src = GetSongBPMEnrichmentSource(api_key="k", min_interval=0)
    with respx.mock(base_url="https://api.getsong.co") as router:
        router.get("/search/").mock(return_value=httpx.Response(401, json={}))
        result = await src.lookup(
            EnrichmentQuery(track_id=1, title="x", artists=["y"])
        )
    assert result.status == "error"
    assert result.error_type == "authentication"
    assert result.http_status == 401


@pytest.mark.asyncio
async def test_lookup_handles_429_with_retry_after():
    src = GetSongBPMEnrichmentSource(api_key="k", min_interval=0)
    with respx.mock(base_url="https://api.getsong.co") as router:
        router.get("/search/").mock(
            return_value=httpx.Response(429, json={}, headers={"Retry-After": "5"})
        )
        result = await src.lookup(
            EnrichmentQuery(track_id=1, title="x", artists=["y"])
        )
    assert result.status == "error"
    assert result.error_type == "rate_limit"
    assert result.match_evidence["retry_after"] == 5.0


@pytest.mark.asyncio
async def test_lookup_handles_500():
    src = GetSongBPMEnrichmentSource(api_key="k", min_interval=0)
    with respx.mock(base_url="https://api.getsong.co") as router:
        router.get("/search/").mock(return_value=httpx.Response(502, json={}))
        result = await src.lookup(
            EnrichmentQuery(track_id=1, title="x", artists=["y"])
        )
    assert result.status == "error"
    assert "server error" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_lookup_handles_invalid_json():
    src = GetSongBPMEnrichmentSource(api_key="k", min_interval=0)
    with respx.mock(base_url="https://api.getsong.co") as router:
        router.get("/search/").mock(return_value=httpx.Response(200, text="not json"))
        result = await src.lookup(
            EnrichmentQuery(track_id=1, title="x", artists=["y"])
        )
    assert result.status == "error"
    assert "json" in (result.error or "").lower()


# --- matching / scoring -----------------------------------------------------

def test_score_candidate_accepts_strong_match():
    score, ev = _score_candidate(
        aion_title="Highway to Hell",
        aion_artists=["AC/DC"],
        aion_duration_ms=None,
        candidate={
            "song_id": "abc",
            "song_title": "Highway to Hell",
            "artist": {"id": "qB3", "name": "AC/DC"},
        },
    )
    assert score >= ACCEPT_SCORE
    assert ev["title_score"] >= 0.9
    assert ev["artist_score"] == 1.0


def test_score_candidate_rejects_remix_mismatch():
    """"Acid Trip" must NOT auto-match "Acid Trip - Out of Orbit & Sasi Remix"."""
    score, ev = _score_candidate(
        aion_title="Acid Trip",
        aion_artists=["Some Artist"],
        aion_duration_ms=None,
        candidate={
            "song_id": "remix1",
            "song_title": "Acid Trip - Out of Orbit & Sasi Remix",
            "artist": {"name": "Some Artist"},
        },
    )
    assert ev["version_ok"] is False
    # The score should be well below the acceptance threshold.
    assert score < ACCEPT_SCORE


def test_score_candidate_accepts_matching_remix():
    score, ev = _score_candidate(
        aion_title="Acid Trip (Out of Orbit & Sasi Remix)",
        aion_artists=["Some Artist"],
        aion_duration_ms=None,
        candidate={
            "song_id": "remix1",
            "song_title": "Acid Trip - Out of Orbit & Sasi Remix",
            "artist": {"name": "Some Artist"},
        },
    )
    assert ev["version_ok"] is True
    assert score >= ACCEPT_SCORE


def test_score_candidate_handles_artist_list():
    score, ev = _score_candidate(
        aion_title="Foo",
        aion_artists=["A", "B"],
        aion_duration_ms=None,
        candidate={"song_title": "Foo", "artist": [{"name": "A"}, {"name": "C"}]},
    )
    # Only one of two AION artists overlaps → score is partial.
    assert 0 < ev["artist_score"] < 1.0


# --- end-to-end match logic with mocked search ------------------------------

@pytest.mark.asyncio
async def test_lookup_matched_persists_bpm_and_key():
    src = GetSongBPMEnrichmentSource(api_key="k", min_interval=0)
    with respx.mock(base_url="https://api.getsong.co") as router:
        router.get("/search/").mock(
            return_value=httpx.Response(200, json={"search": _gsb_key_payload()})
        )
        # /song/ detail returns slightly richer payload.
        router.get("/song/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "song": {
                        "id": "abc",
                        "title": "Highway to Hell",
                        "tempo": "118",
                        "time_sig": "4/4",
                        "key_of": "A major",
                        "camelot": "11B",
                        "artist": {"id": "qB3", "name": "AC/DC"},
                    }
                },
            )
        )
        result = await src.lookup(
            EnrichmentQuery(
                track_id=1,
                title="Highway to Hell",
                artists=["AC/DC"],
                duration_ms=210000,
            )
        )
    assert result.status == "matched"
    assert result.tempo_bpm == 118.0
    assert result.musical_key == "A major"
    assert result.source_identifier == "abc"
    assert 0.0 < (result.confidence or 0.0) <= 1.0


@pytest.mark.asyncio
async def test_lookup_ambiguous_when_top_two_close():
    src = GetSongBPMEnrichmentSource(api_key="k", min_interval=0)
    payload = {
        "search": [
            {
                "song_id": "1",
                "song_title": "Formation",
                "artist": {"name": "Beyoncé"},
                "tempo": "120",
                "key_of": "C# minor",
            },
            {
                "song_id": "2",
                "song_title": "Formation",
                "artist": {"name": "Beyoncé"},
                "tempo": "121",
                "key_of": "C# minor",
            },
        ]
    }
    with respx.mock(base_url="https://api.getsong.co") as router:
        router.get("/search/").mock(return_value=httpx.Response(200, json=payload))
        result = await src.lookup(
            EnrichmentQuery(track_id=1, title="Formation", artists=["Beyoncé"])
        )
    assert result.status == "ambiguous"


@pytest.mark.asyncio
async def test_lookup_no_match_when_artist_mismatch():
    src = GetSongBPMEnrichmentSource(api_key="k", min_interval=0)
    payload = {
        "search": [
            {
                "song_id": "1",
                "song_title": "Random Song",
                "artist": {"name": "Other Artist"},
                "tempo": "120",
                "key_of": "C minor",
            }
        ]
    }
    with respx.mock(base_url="https://api.getsong.co") as router:
        router.get("/search/").mock(return_value=httpx.Response(200, json=payload))
        result = await src.lookup(
            EnrichmentQuery(track_id=1, title="Random Song", artists=["Beyoncé"])
        )
    assert result.status in {"no_match", "ambiguous"}
    assert result.match_evidence["top_score"] < ACCEPT_SCORE


@pytest.mark.asyncio
async def test_lookup_uses_cache_within_ttl(monkeypatch):
    """A second lookup with the same title must NOT hit the network."""
    src = GetSongBPMEnrichmentSource(api_key="k", min_interval=0)
    call_count = {"n": 0}

    def _side(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json={"search": _gsb_key_payload()})

    with respx.mock(base_url="https://api.getsong.co") as router:
        router.get("/search/").mock(side_effect=_side)
        router.get("/song/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "song": {
                        "id": "abc",
                        "title": "Highway to Hell",
                        "tempo": "118",
                        "key_of": "A major",
                        "artist": {"name": "AC/DC"},
                    }
                },
            )
        )
        r1 = await src.lookup(
            EnrichmentQuery(track_id=1, title="Highway to Hell", artists=["AC/DC"])
        )
        r2 = await src.lookup(
            EnrichmentQuery(track_id=2, title="Highway to Hell", artists=["AC/DC"])
        )
    assert r1.status == "matched"
    assert r2.status == "matched"
    # Cache must have prevented a second /search/ call.
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_lookup_paces_requests(monkeypatch):
    """Two sequential cache-miss calls must respect the configured min_interval."""
    # Use a small but non-zero interval so the test still runs fast.
    src = GetSongBPMEnrichmentSource(api_key="k", min_interval=0.20)
    # Return a candidate that will actually be accepted (matching title + artist).
    payload_a = {
        "search": [
            {
                "song_id": "aaa",
                "song_title": "Match Me",
                "artist": {"name": "Artist X"},
                "tempo": "120",
                "key_of": "C major",
            }
        ]
    }
    payload_b = {
        "search": [
            {
                "song_id": "bbb",
                "song_title": "Other Match",
                "artist": {"name": "Artist Y"},
                "tempo": "121",
                "key_of": "D minor",
            }
        ]
    }
    call_count = {"n": 0}

    def _transport(request: httpx.Request) -> httpx.Response:
        idx = call_count["n"]
        call_count["n"] += 1
        return httpx.Response(200, json=payload_a if idx == 0 else payload_b)

    with respx.mock(base_url="https://api.getsong.co") as router:
        router.get("/search/").mock(side_effect=_transport)
        router.get("/song/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "song": {
                        "id": "aaa",
                        "title": "Match Me",
                        "tempo": "120",
                        "key_of": "C major",
                        "artist": {"name": "Artist X"},
                    }
                },
            )
        )
        # Two distinct queries (no cache hit) — the second call must be paced.
        t0 = asyncio.get_event_loop().time()
        await src.lookup(
            EnrichmentQuery(track_id=1, title="Match Me", artists=["Artist X"])
        )
        await src.lookup(
            EnrichmentQuery(track_id=2, title="Other Match", artists=["Artist Y"])
        )
        elapsed = asyncio.get_event_loop().time() - t0
    # Two paced calls @ 0.20s minimum separation => at least ~0.20s.
    assert elapsed >= 0.18
    assert call_count["n"] == 2


# --- regression: exact host/path/header diagnostics (safe, no secrets) --------


@pytest.mark.asyncio
async def test_outbound_request_has_correct_host_path_and_header_names():
    """Safe diagnostics: prove host/path/header NAMES are correct without exposing secrets."""
    captured: dict = {}

    def _transport(request: httpx.Request) -> httpx.Response:
        captured["host"] = request.url.host
        captured["path"] = request.url.path
        captured["method"] = request.method
        captured["header_names"] = [k.lower() for k in request.headers.keys()]
        captured["query_names"] = sorted(request.url.params.keys())
        # Do NOT capture header values or full URL
        return httpx.Response(200, json={"search": _gsb_key_payload()})

    src = GetSongBPMEnrichmentSource(api_key="secret-key", min_interval=0)
    with respx.mock(base_url="https://api.getsong.co") as router:
        router.get("/search/").mock(side_effect=_transport)
        router.get("/song/").mock(
            return_value=httpx.Response(
                200,
                json={"song": {"id": "abc", "title": "Highway to Hell", "tempo": "118", "key_of": "A major", "artist": {"name": "AC/DC"}}},
            )
        )
        await src.lookup(EnrichmentQuery(track_id=1, title="Highway to Hell", artists=["AC/DC"]))

    assert captured["host"] == "api.getsong.co"
    assert captured["path"] == "/search/"
    assert captured["method"] == "GET"
    assert "x-api-key" in captured["header_names"]
    assert "type" in captured["query_names"]
    assert "lookup" in captured["query_names"]


@pytest.mark.asyncio
async def test_x_api_key_header_has_no_bearer_prefix():
    captured: dict = {}

    def _transport(request: httpx.Request) -> httpx.Response:
        captured["x_api_key"] = request.headers.get("X-API-KEY")
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"search": _gsb_key_payload()})

    src = GetSongBPMEnrichmentSource(api_key="my-secret-key", min_interval=0)
    with respx.mock(base_url="https://api.getsong.co") as router:
        router.get("/search/").mock(side_effect=_transport)
        router.get("/song/").mock(return_value=httpx.Response(200, json={"song": {"id": "abc", "title": "Highway to Hell", "tempo": "118", "key_of": "A major"}}))
        await src.lookup(EnrichmentQuery(track_id=1, title="Highway to Hell", artists=["AC/DC"]))

    assert captured["x_api_key"] == "my-secret-key"
    assert captured["x_api_key"] is not None and not captured["x_api_key"].startswith("Bearer ")
    assert captured["auth"] is None  # must not use Authorization header


@pytest.mark.asyncio
async def test_query_params_passed_separately_not_in_url_string(caplog):
    """Ensure params are passed via httpx params, not manually concatenated in URL."""
    captured: dict = {}

    def _transport(request: httpx.Request) -> httpx.Response:
        # If URL was built manually, raw path would contain '?' — httpx separates it
        captured["query_names"] = sorted(request.url.params.keys())
        captured["url_string"] = str(request.url)
        return httpx.Response(200, json={"search": []})

    src = GetSongBPMEnrichmentSource(api_key="k", min_interval=0)
    with respx.mock(base_url="https://api.getsong.co") as router:
        router.get("/search/").mock(side_effect=_transport)
        await src.lookup(EnrichmentQuery(track_id=1, title="Test", artists=["A"]))

    assert "type" in captured["query_names"]
    assert "lookup" in captured["query_names"]
    assert "limit" in captured["query_names"]
    # API key must never appear as query param
    assert "api_key" not in captured["query_names"]
    assert "api-key" not in captured["query_names"]


def test_secret_never_logged(caplog):
    import logging

    # Ensure no code path logs X-API-KEY value via logging module
    src = GetSongBPMEnrichmentSource(api_key="super-secret-xyz", min_interval=0)
    # Internal storage naturally holds key, but repr/logging must not expose it
    # repr check is best-effort — httpx datastructures shouldn't leak via logs
    with caplog.at_level(logging.WARNING):
        import pathlib

        # Resolve from this test file location to ensure path works regardless of CWD
        code_path = pathlib.Path(__file__).parent.parent / "app" / "enrichment" / "sources" / "getsongbpm.py"
        code = code_path.read_text(encoding="utf-8")
        assert "X-API-KEY" in code  # header is set
        for line in code.splitlines():
            low = line.lower()
            if "log" in low and "api_key" in low:
                assert "self._api_key" not in line, "potential secret logging"
    # Ensure caplog never captured the secret
    assert "super-secret-xyz" not in caplog.text


@pytest.mark.asyncio
async def test_403_classified_as_authentication():
    src = GetSongBPMEnrichmentSource(api_key="k", min_interval=0)
    with respx.mock(base_url="https://api.getsong.co") as router:
        router.get("/search/").mock(return_value=httpx.Response(403, json={}))
        result = await src.lookup(EnrichmentQuery(track_id=1, title="x", artists=["y"]))
    assert result.status == "error"
    assert result.error_type == "authentication"
    assert result.http_status == 403