"""add provider_track display columns

Revision ID: 0002_provider_track_display
Revises: 0001_initial
Create Date: 2026-08-31

M1 Library Explorer needs to search and sort the user's imported library by
artist, album, and release date without parsing the raw_metadata JSON blob on
every request. This migration adds small denormalized display columns to
provider_tracks and backfills them from the already-persisted raw_metadata.
The canonical source of truth remains raw_metadata + TrackIdentifier rows.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import sqlalchemy as sa
from alembic import op

revision = "0002_provider_track_display"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _extract(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    album = data.get("album") or {}
    artists = data.get("artists") or []
    images = album.get("images") or []
    artwork_url = images[0].get("url") if images and isinstance(images[0], dict) else None
    artist_display = ", ".join(
        a.get("name") for a in artists if isinstance(a, dict) and a.get("name")
    )
    return {
        "artist_display": artist_display or None,
        "album_name": album.get("name"),
        "release_date": album.get("release_date"),
        "artwork_url": artwork_url,
    }


def upgrade() -> None:
    op.add_column(
        "provider_tracks",
        sa.Column("artist_display", sa.String(512), nullable=True),
    )
    op.add_column(
        "provider_tracks",
        sa.Column("album_name", sa.String(512), nullable=True),
    )
    op.add_column(
        "provider_tracks",
        sa.Column("release_date", sa.String(32), nullable=True),
    )
    op.add_column(
        "provider_tracks",
        sa.Column("artwork_url", sa.String(1024), nullable=True),
    )
    op.create_index("ix_provider_tracks_artist", "provider_tracks", ["artist_display"])
    op.create_index("ix_provider_tracks_album", "provider_tracks", ["album_name"])
    op.create_index("ix_provider_tracks_saved_at", "provider_tracks", ["saved_at"])

    # Backfill from existing raw_metadata. Runs once, in-process, on the live DB.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, raw_metadata FROM provider_tracks")
    ).fetchall()
    for row_id, raw in rows:
        values = _extract(raw)
        if not values:
            continue
        bind.execute(
            sa.text(
                "UPDATE provider_tracks "
                "SET artist_display = :a, album_name = :b, "
                "release_date = :c, artwork_url = :d WHERE id = :id"
            ),
            {
                "a": values["artist_display"],
                "b": values["album_name"],
                "c": values["release_date"],
                "d": values["artwork_url"],
                "id": row_id,
            },
        )


def downgrade() -> None:
    op.drop_index("ix_provider_tracks_saved_at", table_name="provider_tracks")
    op.drop_index("ix_provider_tracks_album", table_name="provider_tracks")
    op.drop_index("ix_provider_tracks_artist", table_name="provider_tracks")
    op.drop_column("provider_tracks", "artwork_url")
    op.drop_column("provider_tracks", "release_date")
    op.drop_column("provider_tracks", "album_name")
    op.drop_column("provider_tracks", "artist_display")
