"""Tests for the M1 Library Explorer read API (GET /tracks, /library/summary).

Note: the FastAPI app mounts routes at the root (no /api prefix). The Next.js
dev server adds the /api prefix via a rewrite proxy, but tests talk to the app
directly, so we request "/tracks" and "/library/summary".
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.api import router  # noqa: F401  (ensure routes register)
from app.main import app
from app.models import ProviderTrack, Track, TrackIdentifier
from app.providers.base.models import (
    ArtistRef,
    ProviderAlbumRef,
    ProviderTrack as IncomingProviderTrack,
)
from app.tracks import import_provider_tracks


def _raw(artist: str, album: str, isrc: str | None, release="2023-05-01") -> dict:
    return {
        "name": "Title",
        "artists": [{"id": "a1", "name": artist}],
        "album": {
            "id": "al1",
            "name": album,
            "release_date": release,
            "images": [{"url": f"https://img/{album}.jpg"}],
        },
        "external_ids": {"isrc": isrc} if isrc else {},
    }


def _incoming(
    spotify_id: str,
    title: str,
    artist: str = "Artist",
    album: str = "Album",
    isrc: str | None = None,
    duration: int = 200000,
    saved_at: datetime | None = None,
    provider: str = "spotify",
    raw: dict | None = None,
    with_raw: bool = True,
) -> IncomingProviderTrack:
    return IncomingProviderTrack(
        provider=provider,
        provider_track_id=spotify_id,
        title=title,
        artists=[ArtistRef(provider_artist_id="a1", name=artist)],
        album=ProviderAlbumRef(
            provider_album_id="al1", name=album, image_url=f"https://img/{album}.jpg"
        ),
        duration_ms=duration,
        isrc=isrc,
        provider_uri=f"spotify:track:{spotify_id}",
        provider_url=f"https://open.spotify.com/track/{spotify_id}",
        release_date="2023-05-01" if raw is None else raw.get("album", {}).get("release_date"),
        raw=raw if (with_raw and raw is not None) else (raw if with_raw else None),
        saved_at=saved_at,
    )


@pytest.fixture
def client():
    return TestClient(app)


def _seed(session, items):
    import_provider_tracks(session, items)


def test_listing_returns_items_and_total(session):
    _seed(
        session,
        [
            _incoming("t1", "Alpha", isrc="ISRC1"),
            _incoming("t2", "Beta", isrc="ISRC2"),
            _incoming("t3", "Gamma", isrc=None),
        ],
    )
    client = TestClient(app)
    r = client.get("/tracks")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 50
    assert body["total_pages"] == 1
    assert len(body["items"]) == 3


def test_pagination_default_50_and_pages_disjoint(session):
    items = [_incoming(f"t{i}", f"Track {i:03d}", isrc=f"ISRC{i}") for i in range(120)]
    _seed(session, items)
    client = TestClient(app)
    p1 = client.get("/tracks?page=1&page_size=50").json()
    p2 = client.get("/tracks?page=2&page_size=50").json()
    p3 = client.get("/tracks?page=3&page_size=50").json()
    assert p1["total"] == 120
    assert p1["total_pages"] == 3
    assert len(p1["items"]) == 50
    assert len(p2["items"]) == 50
    assert len(p3["items"]) == 20
    ids1 = {it["provider_track_id"] for it in p1["items"]}
    ids2 = {it["provider_track_id"] for it in p2["items"]}
    ids3 = {it["provider_track_id"] for it in p3["items"]}
    assert ids1.isdisjoint(ids2)
    assert ids1.isdisjoint(ids3)
    assert ids2.isdisjoint(ids3)


def test_total_count_and_total_pages_math(session):
    _seed(session, [_incoming(f"t{i}", f"T{i}", isrc=f"I{i}") for i in range(75)])
    client = TestClient(app)
    body = client.get("/tracks?page_size=25").json()
    assert body["total"] == 75
    assert body["total_pages"] == 3


def test_stable_ordering_title_asc_is_deterministic(session):
    _seed(
        session,
        [
            _incoming("t2", "Banana", isrc="I2"),
            _incoming("t1", "Apple", isrc="I1"),
            _incoming("t3", "Cherry", isrc="I3"),
        ],
    )
    client = TestClient(app)
    body = client.get("/tracks?sort=title_asc").json()
    titles = [it["title"] for it in body["items"]]
    assert titles == ["Apple", "Banana", "Cherry"]


def test_stable_ordering_tiebreak_by_id(session):
    _seed(session, [_incoming(f"t{i}", "Same", isrc=f"I{i}") for i in range(10)])
    client = TestClient(app)
    page1 = [it["provider_track_id"] for it in client.get("/tracks?sort=title_asc&page=1&page_size=4").json()["items"]]
    page2 = [it["provider_track_id"] for it in client.get("/tracks?sort=title_asc&page=2&page_size=4").json()["items"]]
    assert page1[:1] != page2[:1]
    assert set(page1).isdisjoint(set(page2))


def test_search_by_title(session):
    _seed(
        session,
        [
            _incoming("t1", "Radiohead Song", artist="X", album="A", isrc="I1"),
            _incoming("t2", "Other Song", artist="Y", album="B", isrc="I2"),
        ],
    )
    client = TestClient(app)
    body = client.get("/tracks?search=Radiohead").json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Radiohead Song"


def test_search_by_artist(session):
    _seed(
        session,
        [
            _incoming("t1", "Song A", artist="Radiohead", album="A", isrc="I1"),
            _incoming("t2", "Song B", artist="Beatles", album="B", isrc="I2"),
        ],
    )
    client = TestClient(app)
    body = client.get("/tracks?search=radiohead").json()
    assert body["total"] == 1
    assert body["items"][0]["artists"] == ["Radiohead"]


def test_search_by_album(session):
    _seed(
        session,
        [
            _incoming("t1", "Song A", artist="X", album="OK Computer", isrc="I1"),
            _incoming("t2", "Song B", artist="Y", album="Abbey Road", isrc="I2"),
        ],
    )
    client = TestClient(app)
    body = client.get("/tracks?search=computer").json()
    assert body["total"] == 1
    assert body["items"][0]["album"] == "OK Computer"


def test_has_isrc_filter(session):
    _seed(
        session,
        [
            _incoming("t1", "Has", isrc="YES"),
            _incoming("t2", "Missing", isrc=None),
            _incoming("t3", "Also Missing", isrc=None),
        ],
    )
    client = TestClient(app)
    has = client.get("/tracks?has_isrc=has").json()
    assert has["total"] == 1
    assert has["items"][0]["isrc"] == "YES"
    missing = client.get("/tracks?has_isrc=missing").json()
    assert missing["total"] == 2
    assert all(it["isrc"] is None for it in missing["items"])


def test_provider_filter_isolates_spotify(session):
    _seed(
        session,
        [
            _incoming("t1", "Spotify Track", isrc="I1", provider="spotify"),
            _incoming("t2", "SoundCloud Track", isrc="I2", provider="soundcloud"),
        ],
    )
    client = TestClient(app)
    body = client.get("/tracks?provider=spotify").json()
    assert body["total"] == 1
    assert body["items"][0]["provider"] == "spotify"


def test_invalid_page_and_page_size_rejected(session):
    client = TestClient(app)
    assert client.get("/tracks?page=0").status_code == 422
    assert client.get("/tracks?page=-1").status_code == 422
    assert client.get("/tracks?page_size=0").status_code == 422
    assert client.get("/tracks?page_size=1000").status_code == 422


def test_page_beyond_total_returns_empty(session):
    _seed(session, [_incoming("t1", "Only", isrc="I1")])
    client = TestClient(app)
    body = client.get("/tracks?page=99&page_size=50").json()
    assert body["total"] == 1
    assert body["items"] == []
    assert body["total_pages"] == 1


def test_response_normalization_exposes_expected_fields_and_no_secrets(session):
    _seed(
        session,
        [
            _incoming(
                "t1", "Alpha", artist="Artist A", album="Album A", isrc="ISRC1",
                raw=_raw("Artist A", "Album A", "ISRC1"),
            )
        ]
    )
    client = TestClient(app)
    body = client.get("/tracks").json()
    it = body["items"][0]
    for key in [
        "track_id", "provider", "provider_track_id", "title", "artists",
        "album", "artwork_url", "duration_ms", "release_date", "release_year",
        "isrc", "provider_uri", "provider_url", "saved_at", "imported_at",
    ]:
        assert key in it, f"missing {key}"
    # No secrets / raw blobs.
    assert "raw_metadata" not in it
    assert "access_token" not in it
    assert "client_secret" not in it
    assert "refresh_token" not in it
    assert "img/Album" in (it["artwork_url"] or "")
    assert it["release_year"] == 2023
    assert it["isrc"] == "ISRC1"
    assert it["provider"] == "spotify"
    assert it["artists"] == ["Artist A"]


def test_missing_optional_metadata_does_not_crash(session):
    track = Track(canonical_title="(untitled)")
    session.add(track)
    session.flush()
    pt = ProviderTrack(
        track_id=track.id,
        provider="spotify",
        provider_track_id="tnull",
        raw_title=None,
        artist_display=None,
        album_name=None,
        release_date=None,
        artwork_url=None,
        raw_metadata=None,
    )
    session.add(pt)
    session.commit()

    client = TestClient(app)
    body = client.get("/tracks").json()
    it = body["items"][0]
    assert it["title"] == "(untitled)"
    assert it["artists"] == []
    assert it["album"] is None
    assert it["artwork_url"] is None
    assert it["isrc"] is None
    assert it["release_year"] is None


def test_library_summary_counts(session):
    _seed(
        session,
        [
            _incoming("t1", "A", isrc="I1"),
            _incoming("t2", "B", isrc=None),
            _incoming("t3", "C", isrc="I3"),
        ],
    )
    client = TestClient(app)
    body = client.get("/library/summary").json()
    assert body["canonical_tracks"] == 3
    assert body["provider_occurrences"] == 3
    assert body["with_isrc"] == 2
    assert body["missing_isrc"] == 1
    assert any(p["provider"] == "spotify" for p in body["providers"])
