"""saved flows, flow tracks, and flow exports

Revision ID: 0004_saved_flows
Revises: 0003_identity_resolution
Create Date: 2026-09-02

Creates the M11 schema for persisting Smart Flow sequences and export history:
  saved_flows, saved_flow_tracks, flow_exports
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_saved_flows"
down_revision = "0003_identity_resolution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_flows",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("start_track_id", sa.Integer, sa.ForeignKey("tracks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_track_count", sa.Integer, nullable=False),
        sa.Column("energy_shape", sa.String(32), nullable=False),
        sa.Column("constraints_json", sa.Text, nullable=True),
        sa.Column("overall_sequence_score", sa.Integer, nullable=True),
        sa.Column("average_transition_score", sa.Float, nullable=True),
        sa.Column("minimum_transition_score", sa.Integer, nullable=True),
        sa.Column("optimizer_version", sa.String(64), nullable=True),
        sa.Column("transition_model_version", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="ok"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_saved_flows_created", "saved_flows", ["created_at"])

    op.create_table(
        "saved_flow_tracks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("flow_id", sa.Integer, sa.ForeignKey("saved_flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("track_id", sa.Integer, sa.ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("artist", sa.String(512), nullable=True),
        sa.Column("bpm", sa.Float, nullable=True),
        sa.Column("camelot", sa.String(8), nullable=True),
        sa.Column("energy", sa.Float, nullable=True),
        sa.Column("dominant_mood", sa.String(64), nullable=True),
        sa.Column("dominant_vibe", sa.String(64), nullable=True),
        sa.Column("transition_score", sa.Integer, nullable=True),
        sa.Column("transition_components_json", sa.Text, nullable=True),
        sa.Column("transition_reasons_json", sa.Text, nullable=True),
        sa.Column("transition_warnings_json", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("flow_id", "position", name="uq_saved_flow_track_position"),
    )
    op.create_index("ix_saved_flow_tracks_flow", "saved_flow_tracks", ["flow_id"])
    op.create_index("ix_saved_flow_tracks_track", "saved_flow_tracks", ["track_id"])

    op.create_table(
        "flow_exports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("flow_id", sa.Integer, sa.ForeignKey("saved_flows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("external_playlist_id", sa.String(128), nullable=True),
        sa.Column("external_playlist_url", sa.String(512), nullable=True),
        sa.Column("external_playlist_name", sa.String(255), nullable=True),
        sa.Column("exported_track_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("skipped_track_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("skipped_tracks_json", sa.Text, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="success"),
        sa.Column("error_summary", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_flow_exports_flow", "flow_exports", ["flow_id"])


def downgrade() -> None:
    op.drop_table("flow_exports")
    op.drop_table("saved_flow_tracks")
    op.drop_table("saved_flows")
