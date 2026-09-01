"""Tests for playlist ordering persistence."""

from __future__ import annotations

from app.models import Playlist, PlaylistTrack, Track


def _track(session, title: str) -> Track:
    t = Track(canonical_title=title)
    session.add(t)
    session.flush()
    return t


def test_playlist_track_preserves_order(session):
    p = Playlist(name="My Set")
    session.add(p)
    session.flush()
    t1, t2, t3 = _track(session, "A"), _track(session, "B"), _track(session, "C")
    session.add_all(
        [
            PlaylistTrack(playlist_id=p.id, track_id=t1.id, position=0),
            PlaylistTrack(playlist_id=p.id, track_id=t2.id, position=1),
            PlaylistTrack(playlist_id=p.id, track_id=t3.id, position=2),
        ]
    )
    session.commit()

    rows = (
        session.query(PlaylistTrack)
        .filter(PlaylistTrack.playlist_id == p.id)
        .order_by(PlaylistTrack.position)
        .all()
    )
    assert [r.track.canonical_title for r in rows] == ["A", "B", "C"]


def test_playlist_position_uniqueness(session):
    from sqlalchemy.exc import IntegrityError

    p = Playlist(name="Dup")
    session.add(p)
    session.flush()
    t = _track(session, "X")
    session.add(PlaylistTrack(playlist_id=p.id, track_id=t.id, position=0))
    session.commit()
    session.add(PlaylistTrack(playlist_id=p.id, track_id=t.id, position=0))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
    else:
        raise AssertionError("expected IntegrityError on duplicate (playlist, position)")
