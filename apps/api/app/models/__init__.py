"""ORM models for the music intelligence domain.

Domain boundary rules:
- Spotify JSON never touches these models directly.
- Track is the canonical identity. A track can have many ProviderTrack
  occurrences (one per provider) and many TrackIdentifier values
  (ISRC, MusicBrainz recording id, etc.).
- TrackAttribute stores every observation (BPM, key, energy, ...) with full
  provenance so future resolvers can pick the "current" value without losing
  history. M0 does not populate any fake attribute values.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
    )


class Track(TimestampMixin, Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_title: Mapped[str] = mapped_column(String(512), nullable=False)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    identifiers: Mapped[list["TrackIdentifier"]] = relationship(
        back_populates="track",
        cascade="all, delete-orphan",
    )
    provider_occurrences: Mapped[list["ProviderTrack"]] = relationship(
        back_populates="track",
        cascade="all, delete-orphan",
    )
    attributes: Mapped[list["TrackAttribute"]] = relationship(
        back_populates="track",
        cascade="all, delete-orphan",
    )
    playlist_entries: Mapped[list["PlaylistTrack"]] = relationship(
        back_populates="track",
        cascade="all, delete-orphan",
    )


class TrackIdentifier(TimestampMixin, Base):
    """External identifiers that help resolve a Track to a real-world recording."""

    __tablename__ = "track_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "identifier_type", "identifier_value", name="uq_track_identifier_value"
        ),
        Index("ix_track_identifiers_track", "track_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False
    )
    identifier_type: Mapped[str] = mapped_column(String(64), nullable=False)
    identifier_value: Mapped[str] = mapped_column(String(255), nullable=False)

    track: Mapped[Track] = relationship(back_populates="identifiers")


class ProviderTrack(TimestampMixin, Base):
    """A provider-specific occurrence of a Track.

    A given Track may have many ProviderTrack rows (Spotify, SoundCloud, etc.).
    Uniqueness is enforced on (provider, provider_track_id) so re-imports of
    the same provider track are idempotent.
    """

    __tablename__ = "provider_tracks"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_track_id", name="uq_provider_track"
        ),
        Index("ix_provider_tracks_track", "track_id"),
        Index("ix_provider_tracks_artist", "artist_display"),
        Index("ix_provider_tracks_album", "album_name"),
        Index("ix_provider_tracks_saved_at", "saved_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_track_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_uri: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    provider_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    raw_title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    raw_metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Denormalized display/search columns derived from raw_metadata at import
    # time. They exist so that search/sort on artist/album/release can run in
    # SQL without parsing the JSON blob on every request. The canonical source
    # of truth remains raw_metadata and the TrackIdentifier rows.
    artist_display: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    album_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    release_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    artwork_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    saved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    track: Mapped[Track] = relationship(back_populates="provider_occurrences")


class TrackAttribute(TimestampMixin, Base):
    """A single observation of a musical attribute for a Track.

    Examples of attribute_type: 'tempo_bpm', 'musical_key', 'camelot_key',
    'energy', 'danceability', 'valence', 'genre', 'mood'.

    Every observation keeps its provenance so a future resolver can choose
    the "current" value without losing history. M0 stores zero rows of this
    type — Spotify does not provide these attributes.
    """

    __tablename__ = "track_attributes"
    __table_args__ = (
        Index("ix_track_attributes_track", "track_id"),
        Index("ix_track_attributes_type", "attribute_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False
    )

    attribute_type: Mapped[str] = mapped_column(String(64), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)

    # Provenance
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_name: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    analysis_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    track: Mapped[Track] = relationship(back_populates="attributes")


class MusicAccount(TimestampMixin, Base):
    """A connected provider account for a user."""

    __tablename__ = "music_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_music_account"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tokens: Mapped[list["OAuthToken"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class OAuthToken(TimestampMixin, Base):
    """OAuth credentials for a MusicAccount.

    Never log these. Never commit the database that contains them.
    """

    __tablename__ = "oauth_tokens"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_oauth_token_account"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("music_accounts.id", ondelete="CASCADE"), nullable=False
    )
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_type: Mapped[str] = mapped_column(String(32), nullable=False, default="Bearer")
    scope: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    account: Mapped[MusicAccount] = relationship(back_populates="tokens")


class Playlist(TimestampMixin, Base):
    __tablename__ = "playlists"
    __table_args__ = (
        Index("ix_playlists_provider", "provider", "provider_playlist_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    provider_playlist_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    owner_music_account_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("music_accounts.id", ondelete="SET NULL"), nullable=True
    )

    entries: Mapped[list["PlaylistTrack"]] = relationship(
        back_populates="playlist",
        cascade="all, delete-orphan",
        order_by="PlaylistTrack.position",
    )
    snapshots: Mapped[list["PlaylistSnapshot"]] = relationship(
        back_populates="playlist",
        cascade="all, delete-orphan",
    )


class PlaylistTrack(TimestampMixin, Base):
    __tablename__ = "playlist_tracks"
    __table_args__ = (
        UniqueConstraint(
            "playlist_id", "position", name="uq_playlist_position"
        ),
        Index("ix_playlist_tracks_playlist", "playlist_id"),
        Index("ix_playlist_tracks_track", "track_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    playlist_id: Mapped[int] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False
    )
    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    original_position: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    added_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    playlist: Mapped[Playlist] = relationship(back_populates="entries")
    track: Mapped[Track] = relationship(back_populates="playlist_entries")


class PlaylistSnapshot(TimestampMixin, Base):
    """A reproducible snapshot of a playlist's track sequence."""

    __tablename__ = "playlist_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    playlist_id: Mapped[int] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False
    )
    provider_snapshot_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )
    track_sequence_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    track_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    playlist: Mapped[Playlist] = relationship(back_populates="snapshots")


class TrackIdentityResolution(TimestampMixin, Base):
    """Auditable record of an identity resolution attempt for a Track.

    M2 focuses on ISRC → MusicBrainz Recording MBID resolution. The same table
    can record other identity sources later without changing the schema.
    """

    __tablename__ = "track_identity_resolutions"
    __table_args__ = (
        UniqueConstraint(
            "track_id", "query_type", "query_value", name="uq_identity_resolution"
        ),
        Index("ix_identity_resolutions_status", "status"),
        Index("ix_identity_resolutions_resolved_at", "resolved_at"),
        Index("ix_identity_resolutions_query_value", "query_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[int] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False
    )
    query_type: Mapped[str] = mapped_column(String(64), nullable=False)
    query_value: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    matched_identifier: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolver_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    track: Mapped[Track] = relationship()
