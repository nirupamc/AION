"""Tests for the MusicBrainz identity resolver and adapter.

HTTP calls to MusicBrainz are mocked. The resolver is tested for idempotency,
resumability, dedup, ambiguity handling, and persistence.
"""

from __future__ import annotations

import asyncio
import json as _json
from typing import Any
from unittest.mock import AsyncMock

import httpx
import respx
import pytest

from app.models import TrackIdentifier, TrackIdentityResolution
from app.providers.base.models import (
    ArtistRef,
    ProviderAlbumRef,
    ProviderTrack as IncomingProviderTrack,
)
from app.providers.musicbrainz import MusicBrainzClient
from app.providers.musicbrainz.resolver import (
    eligible_tracks_with_isrc,
    resolve_isrc_to_mbid,
    resolve_tracks,
    resolution_summary,
)
from app.tracks import import_provider_tracks


def _incoming(spotify_id: str, title: str, isrc: str | None, artist: str = "Artist", album: str = "Album"):
    return IncomingProviderTrack(
        provider="spotify",
        provider_track_id=spotify_id,
        title=title,
        artists=[ArtistRef("a1", artist)],
        album=ProviderAlbumRef("al1", album, "https://img/a.jpg"),
        duration_ms=200000,
        isrc=isrc,
        provider_uri="u",
        provider_url="https://x",
        release_date="2023-05-01",
    )


class FakeRecording:
    def __init__(self, mbid: str, title: str, length_ms: int | None = None, artist_credit: list[str] | None = None):
        self.mbid = mbid
        self.title = title
        self.length_ms = length_ms
        self.artist_credit = artist_credit or []


class FakeLookupResult:
    def __init__(self, isrc: str, recordings: list[FakeRecording], raw_count: int | None = None):
        self.isrc = isrc
        self.recordings = recordings
        self.raw_count = raw_count if raw_count is not None else len(recordings)


def _make_client(result: FakeLookupResult) -> AsyncMock:
    c = AsyncMock(spec=MusicBrainzClient)
    c.lookup_isrc.return_value = result
    return c


def _seed(session, items):
    import_provider_tracks(session, items)


# ---- MusicBrainz client HTTP ----

@respx.mock
async def test_musicbrainz_client_unique_match():
    client = MusicBrainzClient(min_interval=0)
    respx.get("https://musicbrainz.org/ws/2/isrc/ISRC-UNIQUE?fmt=json").mock(
        return_value=httpx.Response(200, json={
            "count": 1,
            "offset": 0,
            "recordings": [
                {"id": "rec-1", "title": "Title", "length": 200000, "artist-credit": [{"name": "Artist"}]}
            ],
        }),
    )
    res = await client.lookup_isrc("ISRC-UNIQUE")
    assert len(res.recordings) == 1
    assert res.recordings[0].mbid == "rec-1"


@respx.mock
async def test_musicbrainz_client_zero_match():
    client = MusicBrainzClient(min_interval=0)
    respx.get("https://musicbrainz.org/ws/2/isrc/ISRC-EMPTY?fmt=json").mock(
        return_value=httpx.Response(200, json={"count": 0, "offset": 0, "recordings": []}),
    )
    res = await client.lookup_isrc("ISRC-EMPTY")
    assert res.recordings == []


@respx.mock
async def test_musicbrainz_client_multiple_recordings():
    client = MusicBrainzClient(min_interval=0)
    respx.get("https://musicbrainz.org/ws/2/isrc/ISRC-AMBIG?fmt=json").mock(
        return_value=httpx.Response(200, json={
            "count": 2,
            "offset": 0,
            "recordings": [
                {"id": "rec-a", "title": "Title A", "artist-credit": [{"name": "A"}]},
                {"id": "rec-b", "title": "Title B", "artist-credit": [{"name": "B"}]},
            ],
        }),
    )
    res = await client.lookup_isrc("ISRC-AMBIG")
    assert len(res.recordings) == 2


# ---- Resolver service ----

def test_unique_match_persists_identifier_and_resolution(session):
    _seed(session, [_incoming("t1", "Title", isrc="ISRC-UNIQUE")])
    result = FakeLookupResult("ISRC-UNIQUE", [FakeRecording("rec-1", "Title", 200000, ["Artist"])])
    stats = asyncio.run(resolve_tracks(session, _make_client(result), limit=10))
    assert stats.matched == 1
    assert stats.requests_sent == 1
    mb = session.query(TrackIdentifier).filter(TrackIdentifier.identifier_type == "musicbrainz_recording_id").first()
    assert mb is not None
    assert mb.identifier_value == "rec-1"
    res = session.query(TrackIdentityResolution).first()
    assert res.status == "MATCHED"
    assert res.matched_identifier == "rec-1"


def test_zero_match_persists_no_match(session):
    _seed(session, [_incoming("t1", "Title", isrc="ISRC-EMPTY")])
    result = FakeLookupResult("ISRC-EMPTY", [])
    stats = asyncio.run(resolve_tracks(session, _make_client(result), limit=10))
    assert stats.no_match == 1
    mb = session.query(TrackIdentifier).filter(TrackIdentifier.identifier_type == "musicbrainz_recording_id").first()
    assert mb is None
    res = session.query(TrackIdentityResolution).first()
    assert res.status == "NO_MATCH"


def test_multiple_recordings_persists_ambiguous(session):
    _seed(session, [_incoming("t1", "Title", isrc="ISRC-AMBIG")])
    result = FakeLookupResult("ISRC-AMBIG", [FakeRecording("rec-a", "A"), FakeRecording("rec-b", "B")])
    stats = asyncio.run(resolve_tracks(session, _make_client(result), limit=10))
    assert stats.ambiguous == 1
    res = session.query(TrackIdentityResolution).first()
    assert res.status == "AMBIGUOUS"
    assert res.matched_identifier is None
    meta = _json.loads(res.metadata_json) if res.metadata_json else {}
    assert "candidates" in meta
    assert len(meta["candidates"]) == 2


def test_duplicate_isrc_queried_once(session):
    # Two provider tracks with the same ISRC link to the same canonical Track
    # via the importer, so only one ISRC identifier / resolution exists.
    _seed(session, [
        _incoming("t1", "A", isrc="ISRC-SHARED"),
        _incoming("t2", "B", isrc="ISRC-SHARED"),
    ])
    result = FakeLookupResult("ISRC-SHARED", [FakeRecording("rec-1", "X")])
    client = _make_client(result)
    stats = asyncio.run(resolve_tracks(session, client, limit=10))
    assert stats.requests_sent == 1
    assert stats.matched == 1
    assert client.lookup_isrc.call_count == 1


def test_resolver_idempotent_rerun(session):
    _seed(session, [_incoming("t1", "A", isrc="ISRC-1")])
    result = FakeLookupResult("ISRC-1", [FakeRecording("rec-1", "A")])
    client = _make_client(result)
    s1 = asyncio.run(resolve_tracks(session, client, limit=10))
    s2 = asyncio.run(resolve_tracks(session, client, limit=10))
    assert s1.matched == 1
    assert s2.requested == 0
    assert client.lookup_isrc.call_count == 1


def test_force_retry_resends(session):
    _seed(session, [_incoming("t1", "A", isrc="ISRC-ERR")])
    result = FakeLookupResult("ISRC-ERR", [])
    client = _make_client(result)
    asyncio.run(resolve_tracks(session, client, limit=10))
    asyncio.run(resolve_tracks(session, client, limit=10, force_retry=True))
    assert client.lookup_isrc.call_count == 2


def test_invalid_isrc_raises(session):
    client = AsyncMock(spec=MusicBrainzClient)
    with pytest.raises(ValueError):
        asyncio.run(resolve_isrc_to_mbid(client, session, type("T", (), {"id": 1})(), "", force_retry=True))
