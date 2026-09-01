"""Tests for the Soundcharts enrichment source."""

from __future__ import annotations

import base64
import httpx
import pytest
import respx

from app.core.config import Settings
from app.enrichment import EnrichmentQuery
from app.enrichment.sources.soundcharts import (
    SoundchartsEnrichmentSource,
    SoundchartsAuthError,
    SoundchartsRateLimitError,
    _basic_auth,
    _get_soundcharts_token,
    _normalize_bpm,
    _normalize_key,
)


def test_basic_auth():
    token = _basic_auth("cid", "csecret")
    assert base64.b64decode(token).decode() == "cid:csecret"


def test_normalize_bpm():
    assert _normalize_bpm(120.0) == 120.0
    assert _normalize_bpm(120) == 120.0
    assert _normalize_bpm(None) is None
    assert _normalize_bpm("120.5") == 120.5
    assert _normalize_bpm(0) is None
    assert _normalize_bpm(-5) is None
    assert _normalize_bpm(400) is None
    assert _normalize_bpm("abc") is None


def test_normalize_key():
    assert _normalize_key(0, 1) == "C major"
    assert _normalize_key(0, 0) == "C minor"
    assert _normalize_key(9, 1) == "A major"
    assert _normalize_key(-1) is None
    assert _normalize_key(None) is None
    assert _normalize_key(11, 0) == "B minor"
    assert _normalize_key(5) == "F"
    assert _normalize_key("abc") is None


@pytest.mark.asyncio
async def test_get_token_success():
    with respx.mock(base_url="https://account.soundcharts.com") as router:
        router.post("/oauth/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "token123",
                    "token_type": "bearer",
                    "expires_in": 3600,
                    "refresh_token": None,
                },
            )
        )
        result = await _get_soundcharts_token("cid", "csecret")
        assert result["access_token"] == "token123"


@pytest.mark.asyncio
async def test_get_token_auth_failure():
    with respx.mock(base_url="https://account.soundcharts.com") as router:
        router.post("/oauth/token").mock(return_value=httpx.Response(401, json={"error": "invalid_client"}))
        with pytest.raises(SoundchartsAuthError):
            await _get_soundcharts_token("bad", "bad")


@pytest.mark.asyncio
async def test_source_requires_credentials():
    with pytest.raises(ValueError):
        SoundchartsEnrichmentSource(client_id="", client_secret="secret")
    with pytest.raises(ValueError):
        SoundchartsEnrichmentSource(client_id="cid", client_secret="")


@pytest.mark.asyncio
async def test_source_missing_isrc():
    source = SoundchartsEnrichmentSource(client_id="cid", client_secret="secret")
    result = await source.lookup(EnrichmentQuery(track_id=1))
    assert result.status == "error"
    assert "missing isrc" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_source_exact_isrc_match(monkeypatch):
    async def _fake_token(*args, **kwargs):
        return {"access_token": "tok", "token_type": "bearer", "expires_in": 3600}

    monkeypatch.setattr("app.enrichment.sources.soundcharts._get_soundcharts_token", _fake_token)

    with respx.mock(base_url="https://customer.api.soundcharts.com") as router:
        router.get("/api/v2.25/song/by-isrc/USABC1234567").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "song-abc",
                    "tempo": 128.0,
                    "key": 5,
                    "mode": 1,
                    "time_signature": 4,
                },
            )
        )
        source = SoundchartsEnrichmentSource(client_id="cid", client_secret="secret")
        result = await source.lookup(EnrichmentQuery(track_id=1, isrc="USABC1234567"))
        assert result.status == "matched"
        assert result.tempo_bpm == 128.0
        assert result.musical_key == "F major"
        assert result.source_identifier == "song-abc"


@pytest.mark.asyncio
async def test_source_isrc_no_match(monkeypatch):
    async def _fake_token(*args, **kwargs):
        return {"access_token": "tok", "token_type": "bearer", "expires_in": 3600}

    monkeypatch.setattr("app.enrichment.sources.soundcharts._get_soundcharts_token", _fake_token)

    with respx.mock(base_url="https://customer.api.soundcharts.com") as router:
        router.get("/api/v2.25/song/by-isrc/USABC1234567").mock(return_value=httpx.Response(404, json={}))

        source = SoundchartsEnrichmentSource(client_id="cid", client_secret="secret")
        result = await source.lookup(EnrichmentQuery(track_id=1, isrc="USABC1234567"))
        assert result.status == "no_match"


@pytest.mark.asyncio
async def test_source_auth_failure(monkeypatch):
    async def _fake_token(*args, **kwargs):
        return {"access_token": "tok", "token_type": "bearer", "expires_in": 3600}

    monkeypatch.setattr("app.enrichment.sources.soundcharts._get_soundcharts_token", _fake_token)

    with respx.mock(base_url="https://customer.api.soundcharts.com") as router:
        router.get("/api/v2.25/song/by-isrc/USABC1234567").mock(return_value=httpx.Response(401, json={}))

        source = SoundchartsEnrichmentSource(client_id="cid", client_secret="secret")
        result = await source.lookup(EnrichmentQuery(track_id=1, isrc="USABC1234567"))
        assert result.status == "error"
        assert "auth failed" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_source_rate_limit(monkeypatch):
    async def _fake_token(*args, **kwargs):
        return {"access_token": "tok", "token_type": "bearer", "expires_in": 3600}

    monkeypatch.setattr("app.enrichment.sources.soundcharts._get_soundcharts_token", _fake_token)

    with respx.mock(base_url="https://customer.api.soundcharts.com") as router:
        router.get("/api/v2.25/song/by-isrc/USABC1234567").mock(
            return_value=httpx.Response(429, json={}, headers={"Retry-After": "2"})
        )
        source = SoundchartsEnrichmentSource(client_id="cid", client_secret="secret")
        result = await source.lookup(EnrichmentQuery(track_id=1, isrc="USABC1234567"))
        assert result.status == "error"
        assert "rate limited" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_source_server_error(monkeypatch):
    async def _fake_token(*args, **kwargs):
        return {"access_token": "tok", "token_type": "bearer", "expires_in": 3600}

    monkeypatch.setattr("app.enrichment.sources.soundcharts._get_soundcharts_token", _fake_token)

    with respx.mock(base_url="https://customer.api.soundcharts.com") as router:
        router.get("/api/v2.25/song/by-isrc/USABC1234567").mock(return_value=httpx.Response(502, json={}))

        source = SoundchartsEnrichmentSource(client_id="cid", client_secret="secret")
        result = await source.lookup(EnrichmentQuery(track_id=1, isrc="USABC1234567"))
        assert result.status == "error"
        assert "server error" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_source_malformed_payload(monkeypatch):
    async def _fake_token(*args, **kwargs):
        return {"access_token": "tok", "token_type": "bearer", "expires_in": 3600}

    monkeypatch.setattr("app.enrichment.sources.soundcharts._get_soundcharts_token", _fake_token)

    with respx.mock(base_url="https://customer.api.soundcharts.com") as router:
        router.get("/api/v2.25/song/by-isrc/USABC1234567").mock(return_value=httpx.Response(200, json="not a dict"))

        source = SoundchartsEnrichmentSource(client_id="cid", client_secret="secret")
        result = await source.lookup(EnrichmentQuery(track_id=1, isrc="USABC1234567"))
        assert result.status == "no_match"


@pytest.mark.asyncio
async def test_source_token_rate_limit_propagates():
    with respx.mock(base_url="https://account.soundcharts.com") as router:
        router.post("/oauth/token").mock(
            return_value=httpx.Response(429, json={}, headers={"Retry-After": "1"})
        )
        source = SoundchartsEnrichmentSource(client_id="cid", client_secret="secret")
        result = await source.lookup(EnrichmentQuery(track_id=1, isrc="USABC1234567"))
        assert result.status == "error"
        assert "rate limited" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_source_wrapped_object_with_nested_audio(monkeypatch):
    """Regression for 10 NO_MATCH: live API wraps payload as {type, object: {uuid, audio:{tempo,key,...}}}"""
    async def _fake_token(*args, **kwargs):
        return {"access_token": "tok", "token_type": "bearer", "expires_in": 3600}

    monkeypatch.setattr("app.enrichment.sources.soundcharts._get_soundcharts_token", _fake_token)

    with respx.mock(base_url="https://customer.api.soundcharts.com") as router:
        router.get("/api/v2.25/song/by-isrc/USWRAPPED123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "type": "song",
                    "object": {
                        "uuid": "wrapped-uuid",
                        "name": "Wrapped Song",
                        "audio": {
                            "tempo": 126.82,
                            "key": 8,
                            "mode": 1,
                            "timeSignature": 4,
                            "danceability": 0.69,
                        },
                    },
                    "errors": [],
                },
            )
        )
        source = SoundchartsEnrichmentSource(client_id="cid", client_secret="secret")
        result = await source.lookup(EnrichmentQuery(track_id=1, isrc="USWRAPPED123"))
        assert result.status == "matched"
        assert result.tempo_bpm == 126.82
        assert result.musical_key == "G# major"  # key 8 = G#, mode 1 = major
        assert result.source_identifier == "wrapped-uuid"
        assert result.match_evidence["tempo"] == 126.82
        assert result.match_evidence["key"] == 8


@pytest.mark.asyncio
async def test_source_preserves_raw_metadata(monkeypatch):
    async def _fake_token(*args, **kwargs):
        return {"access_token": "tok", "token_type": "bearer", "expires_in": 3600}

    monkeypatch.setattr("app.enrichment.sources.soundcharts._get_soundcharts_token", _fake_token)

    with respx.mock(base_url="https://customer.api.soundcharts.com") as router:
        router.get("/api/v2.25/song/by-isrc/USABC1234567").mock(
            return_value=httpx.Response(
                200,
                json={
                    "uuid": "song-abc",
                    "tempo": 128.0,
                    "key": 5,
                    "mode": 1,
                    "time_signature": 4,
                    "acousticness": 0.5,
                },
            )
        )
        source = SoundchartsEnrichmentSource(client_id="cid", client_secret="secret")
        result = await source.lookup(EnrichmentQuery(track_id=1, isrc="USABC1234567"))
        assert result.raw is not None
        assert result.raw["uuid"] == "song-abc"
        assert result.match_evidence["acousticness"] == 0.5
