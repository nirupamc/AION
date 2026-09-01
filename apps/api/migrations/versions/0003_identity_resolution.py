"""add track_identity_resolutions

Revision ID: 0003_identity_resolution
Revises: 0002_provider_track_display
Create Date: 2026-08-31

M2 stores auditable identity resolution outcomes (e.g. ISRC → MusicBrainz
Recording MBID) in a dedicated table. Existing canonical Track / ProviderTrack
/ TrackIdentifier rows are untouched.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_identity_resolution"
down_revision = "0002_provider_track_display"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "track_identity_resolutions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("track_id", sa.Integer, sa.ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("query_type", sa.String(64), nullable=False),
        sa.Column("query_value", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("matched_identifier", sa.String(255), nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("metadata_json", sa.Text, nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolver_version", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("track_id", "query_type", "query_value", name="uq_identity_resolution"),
    )
    op.create_index("ix_identity_resolutions_status", "track_identity_resolutions", ["status"])
    op.create_index("ix_identity_resolutions_resolved_at", "track_identity_resolutions", ["resolved_at"])
    op.create_index("ix_identity_resolutions_query_value", "track_identity_resolutions", ["query_value"])


def downgrade() -> None:
    op.drop_index("ix_identity_resolutions_query_value", table_name="track_identity_resolutions")
    op.drop_index("ix_identity_resolutions_resolved_at", table_name="track_identity_resolutions")
    op.drop_index("ix_identity_resolutions_status", table_name="track_identity_resolutions")
    op.drop_table("track_identity_resolutions")
