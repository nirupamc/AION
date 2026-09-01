"""Tests for Spotify JSON -> normalized models."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.providers.spotify.parsing import (
    playlist_from_spotify,
    playlist_summary_from_spotify,
    track_from_spotify,
    user_from_spotify,
)


SAMPLE_TRACK = {
    "id": "4iV5W9uYEdYUVa79Axb7Rh",
    "name": "One More Time",
    "uri": "spotify:track:4iV5W9uYEdYUVa79Axb7Rh",
    "duration_ms": 320000,
    "external_ids": {"isrc": "GBDUW0000058"},
    "external_urls": {"spotify": "https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh"},
    "artists": [
        {"id": "1Cs0zKBU1kc0i8ypK3B9ai", "name": "Daft Punk"},
    ],
    "album": {
        "id": "2up3OPMp9Tb4dAKM2erWXQ",
        "name": "Discovery",
        "images": [
            {"url": "https://example.com/cover.jpg", "height": 300, "width": 300}
        ],
    },
}


SAMPLE_SAVED = {
    "added_at": "2024-08-01T12:34:56Z",
    "track": SAMPLE_TRACK,
}


def test_track_from_spotify_basic():
    t = track_from_spotify(SAMPLE_TRACK)
    assert t.provider == "spotify"
    assert t.provider_track_id == "4iV5W9uYEdYUVa79Axb7Rh"
    assert t.title == "One More Time"
    assert t.duration_ms == 320000
    assert t.isrc == "GBDUW0000058"
    assert t.provider_uri == "spotify:track:4iV5W9uYEdYUVa79Axb7Rh"
    assert t.artists[0].name == "Daft Punk"
    assert t.album is not None
    assert t.album.name == "Discovery"
    assert t.album.image_url == "https://example.com/cover.jpg"


def test_track_from_spotify_saved_wrapper_uses_added_at():
    t = track_from_spotify(SAMPLE_SAVED)
    assert t.provider_track_id == "4iV5W9uYEdYUVa79Axb7Rh"
    assert t.saved_at == datetime(2024, 8, 1, 12, 34, 56, tzinfo=timezone.utc)


def test_track_from_spotify_saved_wrapper_explicit_saved_at_wins():
    explicit = datetime(2030, 1, 1, tzinfo=timezone.utc)
    t = track_from_spotify(SAMPLE_SAVED, saved_at=explicit)
    assert t.saved_at == explicit


def test_track_from_spotify_missing_isrc():
    raw = dict(SAMPLE_TRACK)
    raw["external_ids"] = {}
    t = track_from_spotify(raw)
    assert t.isrc is None


def test_user_from_spotify():
    u = user_from_spotify({"id": "alice", "display_name": "Alice", "email": "a@b.com"})
    assert u.provider == "spotify"
    assert u.provider_user_id == "alice"
    assert u.display_name == "Alice"
    assert u.email == "a@b.com"


def test_playlist_summary_from_spotify():
    s = playlist_summary_from_spotify(
        {
            "id": "playlist-1",
            "name": "My Mix",
            "owner": {"display_name": "Alice"},
            "tracks": {"total": 12},
            "public": False,
            "collaborative": True,
            "external_urls": {"spotify": "https://open.spotify.com/playlist/playlist-1"},
        }
    )
    assert s.provider_playlist_id == "playlist-1"
    assert s.track_count == 12
    assert s.is_collaborative is True


def test_playlist_from_spotify_normalizes_items():
    raw = {
        "id": "playlist-1",
        "name": "My Mix",
        "owner": {"display_name": "Alice"},
        "tracks": {
            "total": 1,
            "snapshot_id": "snap-xyz",
            "items": [SAMPLE_SAVED],
        },
        "external_urls": {"spotify": "https://open.spotify.com/playlist/playlist-1"},
    }
    pl = playlist_from_spotify(raw)
    assert pl.summary.provider_playlist_id == "playlist-1"
    assert pl.snapshot_id == "snap-xyz"
    assert len(pl.tracks) == 1
    assert pl.tracks[0].isrc == "GBDUW0000058"


def test_track_from_spotify_invalid_raises():
    with pytest.raises(ValueError):
        track_from_spotify({})
