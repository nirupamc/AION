"""Tests for the Liked Songs importer."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models import ProviderTrack, Track, TrackIdentifier
from app.providers.base.models import (
    ArtistRef,
    ProviderAlbumRef,
    ProviderTrack as IncomingProviderTrack,
)
from app.tracks import import_provider_tracks


def _incoming(
    spotify_id: str,
    title: str = "Track",
    isrc: str | None = None,
    duration: int = 200000,
    saved_at: datetime | None = None,
) -> IncomingProviderTrack:
    return IncomingProviderTrack(
        provider="spotify",
        provider_track_id=spotify_id,
        title=title,
        artists=[ArtistRef(provider_artist_id="a1", name="Artist")],
        album=ProviderAlbumRef(provider_album_id="al1", name="Album", image_url=None),
        duration_ms=duration,
        isrc=isrc,
        provider_uri=f"spotify:track:{spotify_id}",
        provider_url=f"https://open.spotify.com/track/{spotify_id}",
        saved_at=saved_at,
    )


def test_first_import_persists_track_and_provider_track(session):
    stats = import_provider_tracks(
        session,
        [
            _incoming("t1", "Alpha", isrc="ISRC-A"),
            _incoming("t2", "Beta", isrc="ISRC-B"),
        ],
    )
    assert stats.fetched == 2
    assert stats.tracks_created == 2
    assert stats.provider_tracks_created == 2
    assert stats.provider_tracks_existing == 0
    assert stats.isrc_present == 2
    assert stats.isrc_missing == 0

    track_count = session.query(Track).count()
    pt_count = session.query(ProviderTrack).count()
    assert track_count == 2
    assert pt_count == 2

    idents = session.query(TrackIdentifier).all()
    types = sorted(i.identifier_type for i in idents)
    assert types == ["isrc", "isrc", "spotify_id", "spotify_id"]


def test_reimport_is_idempotent(session):
    items = [_incoming("t1", "Alpha", isrc="ISRC-A")]
    s1 = import_provider_tracks(session, items)
    s2 = import_provider_tracks(session, items)
    s3 = import_provider_tracks(session, items)
    assert s1.tracks_created == 1
    assert s1.provider_tracks_created == 1
    assert s2.tracks_created == 0
    assert s2.provider_tracks_existing == 1
    assert s3.provider_tracks_existing == 1

    assert session.query(Track).count() == 1
    assert session.query(ProviderTrack).count() == 1
    assert (
        session.query(TrackIdentifier)
        .filter(TrackIdentifier.identifier_type == "spotify_id")
        .count()
        == 1
    )


def test_isrc_links_two_spotify_occurrences_to_one_track(session):
    a = _incoming("tA", "Same ISRC track A", isrc="ISRC-X")
    import_provider_tracks(session, [a])

    # Second Spotify occurrence of the same ISRC should reuse the Track.
    b = _incoming("tB", "Same ISRC track B (different spotify id)", isrc="ISRC-X")
    stats = import_provider_tracks(session, [b])

    assert stats.tracks_created == 0  # no new canonical Track
    assert stats.provider_tracks_created == 1
    assert session.query(Track).count() == 1
    assert session.query(ProviderTrack).count() == 2


def test_different_spotify_id_no_isrc_creates_separate_tracks(session):
    import_provider_tracks(session, [_incoming("t1", "Alpha")])
    import_provider_tracks(session, [_incoming("t2", "Alpha")])
    # Same title, different spotify id, no ISRC -> kept separate.
    assert session.query(Track).count() == 2
    assert session.query(ProviderTrack).count() == 2


def test_identifier_uniqueness_constraint(session):
    import_provider_tracks(session, [_incoming("t1", "Alpha", isrc="DUP")])
    # Re-import a "different" provider track with same ISRC. The importer
    # links the new provider track to the existing Track via ISRC, but
    # because (identifier_type, identifier_value) is unique the ISRC row
    # itself is not duplicated.
    import_provider_tracks(session, [_incoming("t2", "Alpha 2", isrc="DUP")])
    isrc_rows = (
        session.query(TrackIdentifier)
        .filter(TrackIdentifier.identifier_type == "isrc", TrackIdentifier.identifier_value == "DUP")
        .count()
    )
    assert isrc_rows == 1
