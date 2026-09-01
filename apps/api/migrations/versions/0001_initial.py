"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-28

Creates the M0 schema:
  tracks, track_identifiers, provider_tracks, track_attributes,
  music_accounts, oauth_tokens, playlists, playlist_tracks, playlist_snapshots
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tracks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("canonical_title", sa.String(512), nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "track_identifiers",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("track_id", sa.Integer, sa.ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("identifier_type", sa.String(64), nullable=False),
        sa.Column("identifier_value", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("identifier_type", "identifier_value", name="uq_track_identifier_value"),
    )
    op.create_index("ix_track_identifiers_track", "track_identifiers", ["track_id"])

    op.create_table(
        "provider_tracks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("track_id", sa.Integer, sa.ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_track_id", sa.String(128), nullable=False),
        sa.Column("provider_uri", sa.String(512), nullable=True),
        sa.Column("provider_url", sa.String(512), nullable=True),
        sa.Column("raw_title", sa.String(512), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("raw_metadata", sa.Text, nullable=True),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_track_id", name="uq_provider_track"),
    )
    op.create_index("ix_provider_tracks_track", "provider_tracks", ["track_id"])

    op.create_table(
        "track_attributes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("track_id", sa.Integer, sa.ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attribute_type", sa.String(64), nullable=False),
        sa.Column("value_json", sa.Text, nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_name", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("analysis_version", sa.String(64), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_track_attributes_track", "track_attributes", ["track_id"])
    op.create_index("ix_track_attributes_type", "track_attributes", ["attribute_type"])

    op.create_table(
        "music_accounts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_user_id", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_music_account"),
    )

    op.create_table(
        "oauth_tokens",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("music_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("access_token", sa.Text, nullable=False),
        sa.Column("refresh_token", sa.Text, nullable=True),
        sa.Column("token_type", sa.String(32), nullable=False, server_default="Bearer"),
        sa.Column("scope", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("account_id", name="uq_oauth_token_account"),
    )

    op.create_table(
        "playlists",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("provider_playlist_id", sa.String(128), nullable=True),
        sa.Column("owner_music_account_id", sa.Integer, sa.ForeignKey("music_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_playlists_provider", "playlists", ["provider", "provider_playlist_id"])

    op.create_table(
        "playlist_tracks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("playlist_id", sa.Integer, sa.ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("track_id", sa.Integer, sa.ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("original_position", sa.Integer, nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("playlist_id", "position", name="uq_playlist_position"),
    )
    op.create_index("ix_playlist_tracks_playlist", "playlist_tracks", ["playlist_id"])
    op.create_index("ix_playlist_tracks_track", "playlist_tracks", ["track_id"])

    op.create_table(
        "playlist_snapshots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("playlist_id", sa.Integer, sa.ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_snapshot_id", sa.String(255), nullable=True),
        sa.Column("track_sequence_hash", sa.String(128), nullable=False),
        sa.Column("track_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("playlist_snapshots")
    op.drop_table("playlist_tracks")
    op.drop_table("playlists")
    op.drop_table("oauth_tokens")
    op.drop_table("music_accounts")
    op.drop_table("track_attributes")
    op.drop_table("provider_tracks")
    op.drop_table("track_identifiers")
    op.drop_table("tracks")
