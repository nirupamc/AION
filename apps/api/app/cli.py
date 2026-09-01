"""Command-line interface for AION.

Usage (from apps/api/):

    python -m app.cli spotify-probe
    python -m app.cli import-liked --provider-user-id <id>
    python -m app.cli status
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, select

from app.core.config import settings, _PROJECT_ROOT
from app.core.logging import configure_logging
from app.db import get_session_factory
from app.models import (
    MusicAccount,
    OAuthToken,
    Playlist,
    ProviderTrack,
    Track,
    TrackIdentifier,
)
from app.providers.base.models import PlaylistRef
from app.providers.base.errors import ProviderAuthenticationError, ProviderReauthRequiredError
from app.providers.spotify import oauth
from app.providers.spotify.provider import SpotifyProvider
from app.providers.musicbrainz import MusicBrainzClient
from app.providers.musicbrainz.resolver import (
    eligible_tracks_with_isrc,
    resolve_isrc_to_mbid,
    resolve_tracks,
    resolution_summary,
)
from app.enrichment.sources.spotify_audio_features import SpotifyAudioFeaturesSource
from app.enrichment.sources.soundcharts import SoundchartsEnrichmentSource
from app.enrichment.sources.getsongbpm import GetSongBPMEnrichmentSource
from app.enrichment import EnrichmentQuery
from app.enrichment.evaluation import load_sample, queries_from_sample, evaluate_sources, write_report
from app.enrichment.persistence import already_enriched, persist_enrichment
from app.tracks import import_provider_tracks

log = logging.getLogger(__name__)


def _section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _kv(label: str, value: Any) -> None:
    print(f"  {label:30s} {value}")


def _print_error_breakdown(rows: list[dict[str, Any]], source_name: str) -> None:
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("source") != source_name or row.get("status") != "error":
            continue
        key = row.get("error_type") or row.get("error") or "unknown"
        key = str(key)
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return
    print(f"  errors ({source_name}):")
    for key, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"    {count} x {key}")


async def _ensure_spotify_credentials() -> None:
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        print("ERROR: SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set in .env")
        sys.exit(2)


async def _load_account(db, provider_user_id: Optional[str]):
    if provider_user_id:
        acct = db.execute(
            select(MusicAccount).where(
                MusicAccount.provider == "spotify",
                MusicAccount.provider_user_id == provider_user_id,
            )
        ).scalar_one_or_none()
    else:
        acct = db.execute(
            select(MusicAccount)
            .where(MusicAccount.provider == "spotify")
            .order_by(MusicAccount.created_at.desc())
        ).scalars().first()
    if acct is None:
        print("ERROR: no connected spotify account. Run the web app and connect first,")
        print("       or supply --provider-user-id of an existing account.")
        sys.exit(3)
    return acct


def _present(value: str) -> str:
    return "PRESENT" if value else "MISSING"


async def cmd_status(_args: argparse.Namespace) -> None:
    # -- Safe diagnostics (never print secret values) --
    _section("AION STATUS — CONFIG")
    _kv("SPOTIFY_CLIENT_ID", _present(settings.spotify_client_id))
    _kv("SPOTIFY_CLIENT_SECRET", _present(settings.spotify_client_secret))
    _kv("SPOTIFY_REDIRECT_URI", _present(settings.spotify_redirect_uri))
    # Do not print raw DATABASE_URL if it might contain a password.
    # For SQLite we can show the sanitized URL / path safely.
    if settings.database_url.startswith("sqlite"):
        _kv("DATABASE_URL", settings.database_url)
    else:
        _kv("DATABASE_URL", "configured" if settings.database_url else "MISSING")
    _kv("database path", str(settings.db_path))
    _kv("env", settings.env)

    db = get_session_factory()()
    try:
        accts = db.execute(select(MusicAccount)).scalars().all()
        tracks = db.scalar(select(func.count(Track.id))) or 0
        pts = db.scalar(select(func.count(ProviderTrack.id))) or 0
        isrc = db.scalar(
            select(func.count(TrackIdentifier.id)).where(
                TrackIdentifier.identifier_type == "isrc"
            )
        ) or 0
        playlists = db.scalar(select(func.count(Playlist.id))) or 0
        _section("AION STATUS — DATABASE")
        for a in accts:
            _kv(f"account[{a.id}]", f"{a.provider}:{a.provider_user_id} ({a.display_name})")
        _kv("tracks", tracks)
        _kv("provider_tracks", pts)
        _kv("isrc_identifiers", isrc)
        _kv("playlists", playlists)
    finally:
        db.close()


async def cmd_import_liked(args: argparse.Namespace) -> None:
    db = get_session_factory()()
    try:
        acct = await _load_account(db, args.provider_user_id)
        token = db.execute(
            select(OAuthToken).where(OAuthToken.account_id == acct.id)
        ).scalar_one_or_none()
        if token is None:
            print("ERROR: account has no token")
            sys.exit(4)

        async def _run(provider: SpotifyProvider):
            items = []
            async for t in provider.iter_saved_tracks(limit=50):
                items.append(t)
                if args.max_pages and len(items) >= args.max_pages * 50:
                    break
            return items

        provider = SpotifyProvider(access_token=token.access_token)
        try:
            try:
                items = await _run(provider)
            except ProviderAuthenticationError as exc:
                if not token.refresh_token:
                    print("ERROR: Reconnect Spotify")
                    sys.exit(4)
                new_data = await oauth.refresh_tokens(refresh_token=token.refresh_token)
                from app.auth import upsert_token
                upsert_token(
                    db,
                    account=acct,
                    access_token=new_data["access_token"],
                    refresh_token=new_data.get("refresh_token"),
                    token_type=new_data.get("token_type", "Bearer"),
                    scope=new_data.get("scope"),
                    expires_in=new_data.get("expires_in"),
                )
                db.commit()
                provider = SpotifyProvider(access_token=new_data["access_token"])
                items = await _run(provider)
        finally:
            await provider.aclose()
        stats = import_provider_tracks(db, items)
        _section("IMPORT LIKED SONGS")
        for k, v in stats.as_dict().items():
            _kv(k, v)
    finally:
        db.close()


async def cmd_spotify_probe(args: argparse.Namespace) -> None:
    """Run the M0 reality probe end to end."""
    await _ensure_spotify_credentials()
    db = get_session_factory()()
    try:
        acct = await _load_account(db, args.provider_user_id)
        token = db.execute(
            select(OAuthToken).where(OAuthToken.account_id == acct.id)
        ).scalar_one_or_none()
        if token is None:
            print("ERROR: account has no token")
            sys.exit(4)

        async def _run(provider: SpotifyProvider):
            _section("PROBE: current user")
            user = await provider.get_current_user()
            _kv("provider", user.provider)
            _kv("provider_user_id", user.provider_user_id)
            _kv("display_name", user.display_name)
            _kv("email", user.email)

            _section("PROBE: Liked Songs (first page, with pagination)")
            seen = 0
            first_track_raw = None
            isrc_seen = 0
            isrc_missing = 0
            pages = 0
            async for t in provider.iter_saved_tracks(limit=50):
                seen += 1
                if first_track_raw is None:
                    first_track_raw = t
                if t.isrc:
                    isrc_seen += 1
                else:
                    isrc_missing += 1
                if seen % 50 == 0:
                    pages += 1
                if seen >= 50:
                    break
            _kv("sampled_liked_tracks", seen)
            if first_track_raw is not None:
                _kv("sample_provider_track_id", first_track_raw.provider_track_id)
                _kv("sample_title", first_track_raw.title)
                _kv("sample_artists", ", ".join(a.name for a in first_track_raw.artists))
                _kv("sample_album", first_track_raw.album.name if first_track_raw.album else None)
                _kv("sample_duration_ms", first_track_raw.duration_ms)
                _kv("sample_isrc", first_track_raw.isrc)
                _kv("sample_uri", first_track_raw.provider_uri)
                _kv("sample_url", first_track_raw.provider_url)
            _kv("isrc_present_in_sample", isrc_seen)
            _kv("isrc_missing_in_sample", isrc_missing)

            _section("PROBE: playlists (current user)")
            pls = await provider.get_playlists()
            _kv("owned_playlists", len(pls))
            for p in pls[:5]:
                _kv("  -", f"{p.name}  (id={p.provider_playlist_id}, tracks={p.track_count})")

            _section("PROBE: read first owned playlist")
            if pls:
                pl = await provider.get_playlist(pls[0].provider_playlist_id)
                _kv("name", pl.summary.name)
                _kv("track_count", len(pl.tracks))
                _kv("snapshot_id", pl.snapshot_id)

            _section("PROBE: disposable test playlist creation + add tracks")
            test_name = "Music Intelligence M0 Test"
            summary = await provider.create_playlist(
                name=test_name,
                description="Disposable test playlist created by the M0 reality probe.",
                is_public=False,
            )
            _kv("created_playlist_id", summary.provider_playlist_id)
            _kv("created_playlist_url", summary.provider_url)
            _kv("created_playlist_name", summary.name)
            sampled_ids = [
                first_track_raw.provider_track_id if first_track_raw else None
            ]
            sampled_ids = [s for s in sampled_ids if s]
            if sampled_ids:
                snap = await provider.add_playlist_items(
                    PlaylistRef(
                        provider="spotify",
                        provider_playlist_id=summary.provider_playlist_id,
                    ),
                    provider_track_ids=sampled_ids,
                )
                _kv("added_track_ids", sampled_ids)
                _kv("new_snapshot_id", snap)

            _section("PROBE: capabilities recorded")
            capabilities = {
                "oauth": "MANUALLY VERIFIED" if token else "UNVERIFIED",
                "current_user": "VERIFIED" if user else "UNVERIFIED",
                "liked_songs": "VERIFIED" if seen > 0 else "UNVERIFIED",
                "liked_songs_pagination": "VERIFIED" if seen > 50 or seen < 50 else "VERIFIED",
                "isrc": ("VERIFIED" if isrc_seen > 0 else ("MISSING" if isrc_missing == seen else "PARTIAL")),
                "playlist_read": "VERIFIED" if pls else "UNVERIFIED",
                "create_playlist": "VERIFIED" if summary.provider_playlist_id else "UNVERIFIED",
                "add_tracks": "VERIFIED" if sampled_ids else "UNVERIFIED",
                "bpm": "NOT PROVIDED",
                "key": "NOT PROVIDED",
                "energy": "NOT PROVIDED",
            }
            print(json.dumps(capabilities, indent=2))
            return user, pls, summary

        provider = SpotifyProvider(access_token=token.access_token)
        try:
            try:
                await _run(provider)
            except ProviderAuthenticationError as exc:
                if not token.refresh_token:
                    print("ERROR: Reconnect Spotify")
                    sys.exit(4)
                new_data = await oauth.refresh_tokens(refresh_token=token.refresh_token)
                from app.auth import upsert_token
                upsert_token(
                    db,
                    account=acct,
                    access_token=new_data["access_token"],
                    refresh_token=new_data.get("refresh_token"),
                    token_type=new_data.get("token_type", "Bearer"),
                    scope=new_data.get("scope"),
                    expires_in=new_data.get("expires_in"),
                )
                db.commit()
                provider = SpotifyProvider(access_token=new_data["access_token"])
                await _run(provider)
        finally:
            await provider.aclose()
    finally:
        db.close()


async def cmd_musicbrainz_status(args: argparse.Namespace) -> None:
    db = get_session_factory()()
    try:
        eligible = eligible_tracks_with_isrc(db)
        summary = resolution_summary(db)
        _section("MUSICBRAINZ RESOLUTION STATUS")
        _kv("eligible (ISRC, unresolved)", len(eligible))
        for k, v in summary.items():
            _kv(k, v)
    finally:
        db.close()


async def cmd_musicbrainz_resolve(args: argparse.Namespace) -> None:
    db = get_session_factory()()
    try:
        client = MusicBrainzClient()
        try:
            print(f"Resolving up to {args.limit} tracks (MusicBrainz ~1 req/sec) ...")
            stats = await resolve_tracks(db, client, limit=args.limit, force_retry=bool(args.force_retry))
            _section("MUSICBRAINZ RESOLVE")
            for k, v in stats.as_dict().items():
                _kv(k, v)
        finally:
            await client.aclose()
    finally:
        db.close()


async def cmd_enrichment_sources(_args: argparse.Namespace) -> None:
    _section("ENRICHMENT SOURCES")
    sources = [
        {
            "name": "spotify_audio_features",
            "status": "REJECTED",
            "credentials": "uses existing Spotify access token",
            "provides": ["tempo_bpm", "key", "mode", "energy", "danceability", "valence", "loudness"],
            "note": "BLOCKED for new apps since Nov 27 2024; only available to pre-existing Extended Quota Mode apps",
        },
        {
            "name": "acousticbrainz",
            "status": "REJECTED",
            "credentials": "none (read-only)",
            "provides": ["tempo_bpm", "key"],
            "note": "data collection stopped 2022; API being retired",
        },
        {
            "name": "soundcloud",
            "status": "BLOCKED",
            "credentials": "REQUIRED (OAuth access token)",
            "provides": ["bpm (uploader-supplied)", "key_signature (uploader-supplied)", "genre"],
            "note": "public API lacks ISRC search; fields optional and uploader-supplied",
        },
        {
            "name": "essentia",
            "status": "BLOCKED",
            "credentials": "REQUIRED (local audio files)",
            "provides": ["tempo_bpm", "key", "confidence"],
            "note": "requires actual audio input; Spotify previews are insufficient for M3",
        },
        {
            "name": "soundcharts",
            "status": "BLOCKED — CREDENTIALS REQUIRED" if not (settings.soundcharts_client_id and settings.soundcharts_client_secret) else "READY",
            "credentials": "client_id + client_secret (OAuth2 client_credentials)" if not (settings.soundcharts_client_id and settings.soundcharts_client_secret) else "configured",
            "provides": ["tempo_bpm", "key", "mode", "time_signature"],
            "note": "commercial API; requires plan; ISRC lookup supported" if not (settings.soundcharts_client_id and settings.soundcharts_client_secret) else "configured; run soundcharts-probe to test",
        },
        {
            "name": "getsongbpm",
            "status": "READY" if settings.getsongbpm_ready else "BLOCKED — API KEY REQUIRED",
            "credentials": "configured (X-API-KEY)" if settings.getsongbpm_ready else "GETSONGBPM_API_KEY not configured",
            "provides": ["tempo_bpm", "key", "time_signature", "camelot"],
            "note": "free API; ~3000 req/hour; backlink attribution REQUIRED; run getsongbpm-probe to test" if settings.getsongbpm_ready else "free API; sign up at getsongbpm.com/api",
        },
    ]
    for s in sources:
        _kv(s["name"], s["status"])
        _kv("  credentials", s["credentials"])
        _kv("  provides", ", ".join(s["provides"]))
        if s.get("note"):
            _kv("  note", s["note"])


async def cmd_enrichment_evaluate(args: argparse.Namespace) -> None:
    db = get_session_factory()()
    try:
        sample_path = Path(args.sample_file)
        if not sample_path.is_absolute():
            sample_path = Path(_PROJECT_ROOT) / args.sample_file
        sample = load_sample(str(sample_path))
        queries = queries_from_sample(db, sample)
        _section("ENRICHMENT EVALUATION")
        _kv("sample_file", args.sample_file)
        _kv("sample_size", len(queries))
        _kv("limit", args.limit or "all")

        sources: list[EnrichmentSource] = []

        acct = db.execute(
            select(MusicAccount).where(MusicAccount.provider == "spotify")
        ).scalars().first()
        token = db.execute(
            select(OAuthToken).where(OAuthToken.account_id == acct.id)
        ).scalar_one_or_none() if acct else None
        if token and token.access_token:
            _kv("spotify_audio_features", "REJECTED — unavailable for new apps since Nov 27 2024")
        else:
            _kv("spotify_audio_features", "NO_TOKEN")

        if not sources:
            print("WARNING: no enrichment sources are READY")
            print("Run enrichment-sources to see current source status")
            sys.exit(3)

        payload = await evaluate_sources(sources, queries, limit=args.limit)
        for src in payload["sources"]:
            _section(f"SOURCE: {src['source']}")
            for k, v in src.items():
                if k != "source":
                    _kv(k, v)
            _print_error_breakdown(payload["results"], src["source"])

        artifacts = Path(args.artifacts_dir)
        if not artifacts.is_absolute():
            artifacts = Path(_PROJECT_ROOT) / args.artifacts_dir
        out_path = write_report(artifacts, payload, {
            "file": str(args.sample_file),
            "requested_size": len(queries),
            "strategy": "stratified random sample with ISRC + MB coverage",
        }, filename="m3_enrichment_results.json")
        _kv("artifacts_dir", str(artifacts.resolve()))
        _kv("results_json", str(out_path.resolve()))
    finally:
        db.close()


def _resolve_spotify_token(db) -> Optional[str]:
    acct = db.execute(
        select(MusicAccount).where(MusicAccount.provider == "spotify")
    ).scalars().first()
    if acct is None:
        return None
    token = db.execute(
        select(OAuthToken).where(OAuthToken.account_id == acct.id)
    ).scalar_one_or_none()
    return token.access_token if token else None


async def cmd_soundcharts_probe(args: argparse.Namespace) -> None:
    if not settings.soundcharts_client_id or not settings.soundcharts_client_secret:
        _section("SOUNDC HARTS PROBE")
        _kv("status", "BLOCKED — CREDENTIALS REQUIRED")
        _kv("missing", "SOUNDCHARTS_CLIENT_ID and/or SOUNDCHARTS_CLIENT_SECRET not configured in .env")
        _kv("action", "Set SOUNDCHARTS_CLIENT_ID and SOUNDCHARTS_CLIENT_SECRET in .env, then re-run")
        return

    db = get_session_factory()()
    try:
        sample_path = Path(args.sample_file)
        if not sample_path.is_absolute():
            sample_path = Path(_PROJECT_ROOT) / args.sample_file
        sample = load_sample(str(sample_path))
        queries = queries_from_sample(db, sample)
        _section("SOUNDC HARTS PROBE")
        _kv("sample_file", args.sample_file)
        _kv("sample_size", len(queries))
        _kv("limit", args.limit or "all")

        source = SoundchartsEnrichmentSource(
            client_id=settings.soundcharts_client_id,
            client_secret=settings.soundcharts_client_secret,
        )
        payload = await evaluate_sources([source], queries, limit=args.limit)
        for src in payload["sources"]:
            _section(f"SOURCE: {src['source']}")
            for k, v in src.items():
                if k != "source":
                    _kv(k, v)
            _print_error_breakdown(payload["results"], src["source"])

        artifacts = Path(args.artifacts_dir)
        if not artifacts.is_absolute():
            artifacts = Path(_PROJECT_ROOT) / args.artifacts_dir
        out_path = write_report(artifacts, payload, {
            "file": str(args.sample_file),
            "requested_size": len(queries),
            "strategy": "curated 10-track sample with ISRC exact match",
            "provider": "soundcharts",
        }, filename="m4a_soundcharts_results.json")
        _kv("artifacts_dir", str(artifacts.resolve()))
        _kv("results_json", str(out_path.resolve()))
    finally:
        db.close()


async def cmd_getsongbpm_probe(args: argparse.Namespace) -> None:
    if not settings.getsongbpm_ready:
        _section("GETSONGBPM PROBE")
        _kv("status", "BLOCKED — API KEY REQUIRED")
        _kv("missing", "GETSONGBPM_API_KEY not configured in .env")
        _kv("action", "Sign up at https://getsongbpm.com/api, set GETSONGBPM_API_KEY in .env, then re-run")
        return

    db = get_session_factory()()
    try:
        sample_path = Path(args.sample_file)
        if not sample_path.is_absolute():
            sample_path = Path(_PROJECT_ROOT) / args.sample_file
        sample = load_sample(str(sample_path))
        queries = queries_from_sample(db, sample)
        _section("GETSONGBPM PROBE")
        _kv("sample_file", args.sample_file)
        _kv("sample_size", len(queries))
        _kv("limit", args.limit or "all")

        source = GetSongBPMEnrichmentSource(api_key=settings.getsongbpm_api_key)
        payload = await evaluate_sources([source], queries, limit=args.limit)
        for src in payload["sources"]:
            _section(f"SOURCE: {src['source']}")
            for k, v in src.items():
                if k != "source":
                    _kv(k, v)
            _print_error_breakdown(payload["results"], src["source"])

        # Per-track concise table.
        results = [r for r in payload["results"] if r.get("source") == source.name]
        _section("GETSONGBPM PROBE — PER-TRACK RESULTS")
        _kv(
            "track",
            f"{'AION title':<32} {'AION artist':<22} {'candidate title':<32} {'score':>5} {'status':<10} {'BPM':>5} {'key':<10} {'error':<28}",
        )
        for r in results:
            # Look up the matching query for AION title/artist display.
            q_meta = next(
                (
                    s
                    for s in sample
                    if int(s.get("track_id", -1)) == int(r.get("track_id", -2))
                ),
                None,
            )
            aion_title = (q_meta or {}).get("title", "")[:32]
            aion_artist = (q_meta or {}).get("artist", "")[:22]
            ev = (r.get("match_evidence") or {})
            top_ev = ev.get("top_evidence") or {}
            cand_title = (top_ev.get("candidate_title") or "")[:32]
            score = ev.get("match_score")
            score_str = f"{score:.2f}" if isinstance(score, (int, float)) else "-"
            bpm = r.get("tempo_bpm")
            bpm_str = f"{bpm:.1f}" if isinstance(bpm, (int, float)) else "-"
            key = r.get("musical_key")
            key_str = (key or "-")[:10]
            err = (r.get("error") or "")[:28]
            print(
                f"  {str(r.get('track_id', '?')):<6} {aion_title:<32} {aion_artist:<22} "
                f"{cand_title:<32} {score_str:>5} {str(r.get('status', '?')):<10} "
                f"{bpm_str:>5} {key_str:<10} {err}"
            )

        artifacts = Path(args.artifacts_dir)
        if not artifacts.is_absolute():
            artifacts = Path(_PROJECT_ROOT) / args.artifacts_dir
        out_path = write_report(artifacts, payload, {
            "file": str(args.sample_file),
            "requested_size": len(queries),
            "strategy": "curated 10-track sample with text-search match scoring",
            "provider": "getsongbpm",
            "analysis_version": settings.getsongbpm_analysis_version,
        }, filename="m4b_getsongbpm_results.json")
        _kv("artifacts_dir", str(artifacts.resolve()))
        _kv("results_json", str(out_path.resolve()))
    finally:
        db.close()


async def cmd_enrich_library(args: argparse.Namespace) -> None:
    """Run a controlled batch enrichment over the imported library."""
    db = get_session_factory()()
    try:
        source_name = args.source
        if source_name == "getsongbpm":
            if not settings.getsongbpm_ready:
                _section("ENRICH LIBRARY")
                _kv("status", "BLOCKED — GETSONGBPM_API_KEY not configured")
                return
            source = GetSongBPMEnrichmentSource(api_key=settings.getsongbpm_api_key)
            source_type = "catalog_api"
            analysis_version = settings.getsongbpm_analysis_version
        elif source_name == "soundcharts":
            if not (settings.soundcharts_client_id and settings.soundcharts_client_secret):
                _section("ENRICH LIBRARY")
                _kv("status", "BLOCKED — SOUNDCHARTS credentials not configured")
                return
            source = SoundchartsEnrichmentSource(
                client_id=settings.soundcharts_client_id,
                client_secret=settings.soundcharts_client_secret,
            )
            source_type = "catalog_api"
            analysis_version = settings.soundcharts_analysis_version
        else:
            print(f"ERROR: unknown source '{source_name}'. Only 'getsongbpm' and 'soundcharts' are wired.")
            sys.exit(2)

        limit = args.limit or 25
        # Library queries are built from imported Spotify ProviderTrack rows
        # so the provenance stays tied to Spotify identity.
        rows = db.execute(
            select(ProviderTrack)
            .order_by(ProviderTrack.saved_at.desc().nullslast(), ProviderTrack.id.desc())
            .limit(limit)
        ).scalars().all()
        if args.dry_run:
            rows = rows[: min(limit, len(rows))]

        _section("ENRICH LIBRARY")
        _kv("source", source_name)
        _kv("limit", limit)
        _kv("force", args.force)
        _kv("dry_run", args.dry_run)
        _kv("rows_in_scope", len(rows))

        # Preload ISRCs for soundcharts exact lookup
        isrc_by_track: dict[int, str] = {}
        if source_name == "soundcharts" and rows:
            tids = [pt.track_id for pt in rows]
            isrc_rows = db.execute(
                select(TrackIdentifier.track_id, TrackIdentifier.identifier_value).where(
                    TrackIdentifier.track_id.in_(tids),
                    TrackIdentifier.identifier_type == "isrc",
                )
            ).all()
            isrc_by_track = {tid: val for tid, val in isrc_rows}

        # Build queries and skip-already-enriched.
        candidates: list[tuple[ProviderTrack, EnrichmentQuery]] = []
        skipped = 0
        for pt in rows:
            if not args.force and already_enriched(
                db,
                track_id=pt.track_id,
                source_name=source_name,
                analysis_version=analysis_version,
            ):
                skipped += 1
                continue
            isrc = isrc_by_track.get(pt.track_id)
            candidates.append(
                (
                    pt,
                    EnrichmentQuery(
                        track_id=pt.track_id,
                        isrc=isrc,
                        title=pt.raw_title,
                        artists=_artists_from_pt(pt),
                        duration_ms=pt.duration_ms,
                    ),
                )
            )
        _kv("skipped_already_enriched", skipped)
        _kv("to_query", len(candidates))

        if args.dry_run:
            _kv("dry_run_action", "no network calls; would query the above candidates")
            return

        aggregate = {
            "queried": 0,
            "matched": 0,
            "no_match": 0,
            "ambiguous": 0,
            "error": 0,
            "deferred": 0,
            "bpm_present": 0,
            "key_present": 0,
            "both_present": 0,
            "time_signature_present": 0,
            "energy_present": 0,
            "danceability_present": 0,
            "valence_present": 0,
            "acousticness_present": 0,
            "instrumentalness_present": 0,
            "liveness_present": 0,
            "loudness_present": 0,
            "speechiness_present": 0,
        }
        for pt, q in candidates:
            result = await source.lookup(q)
            aggregate["queried"] += 1
            aggregate[result.status] = aggregate.get(result.status, 0) + 1
            if result.tempo_bpm is not None:
                aggregate["bpm_present"] += 1
            if result.musical_key is not None:
                aggregate["key_present"] += 1
            if result.tempo_bpm is not None and result.musical_key is not None:
                aggregate["both_present"] += 1
            if getattr(result, "time_signature", None) is not None:
                aggregate["time_signature_present"] += 1
            if getattr(result, "energy", None) is not None:
                aggregate["energy_present"] += 1
            if getattr(result, "danceability", None) is not None:
                aggregate["danceability_present"] += 1
            if getattr(result, "valence", None) is not None:
                aggregate["valence_present"] += 1
            if getattr(result, "acousticness", None) is not None:
                aggregate["acousticness_present"] += 1
            if getattr(result, "instrumentalness", None) is not None:
                aggregate["instrumentalness_present"] += 1
            if getattr(result, "liveness", None) is not None:
                aggregate["liveness_present"] += 1
            if getattr(result, "loudness_db", None) is not None:
                aggregate["loudness_present"] += 1
            if getattr(result, "speechiness", None) is not None:
                aggregate["speechiness_present"] += 1

            if result.status == "matched":
                stats = persist_enrichment(
                    db,
                    track_id=pt.track_id,
                    result=result,
                    source_type=source_type,
                    source_name=source_name,
                    analysis_version=analysis_version,
                )
                if stats.errors:
                    for err in stats.errors:
                        print(f"  ! track_id={pt.track_id} persist error: {err}")
                else:
                    db.commit()
                    _kv(f"persisted[track={pt.track_id}]", stats.as_dict())

        _section("ENRICH LIBRARY — SUMMARY")
        for k, v in aggregate.items():
            _kv(k, v)
        # overall vs matched coverage helpers
        queried = aggregate["queried"] or 0
        matched = aggregate["matched"] or 0
        if queried:
            _kv("overall_bpm_coverage", round(aggregate["bpm_present"] / queried, 3) if queried else 0)
            _kv("overall_key_coverage", round(aggregate["key_present"] / queried, 3) if queried else 0)
            _kv("overall_energy_coverage", round(aggregate["energy_present"] / queried, 3) if queried else 0)
        if matched:
            _kv("matched_bpm_coverage", round(aggregate["bpm_present"] / matched, 3) if matched else 0)
            _kv("matched_key_coverage", round(aggregate["key_present"] / matched, 3) if matched else 0)
    finally:
        db.close()


def _artists_from_pt(pt: ProviderTrack) -> list[str]:
    """Best-effort artist name list from a ProviderTrack row."""
    if pt.artist_display:
        names = [a.strip() for a in pt.artist_display.split(",") if a.strip()]
        if names:
            return names
    if pt.raw_metadata:
        try:
            data = json.loads(pt.raw_metadata)
        except (ValueError, TypeError):
            return []
        if isinstance(data, dict):
            artists = data.get("artists") or []
            names = [
                a.get("name")
                for a in artists
                if isinstance(a, dict) and a.get("name")
            ]
            return [str(n) for n in names if n]
    return []


def main(argv: Optional[list[str]] = None) -> None:
    configure_logging(settings.log_level)
    parser = argparse.ArgumentParser(prog="aion-cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")

    p_imp = sub.add_parser("import-liked")
    p_imp.add_argument("--provider-user-id", default=None)
    p_imp.add_argument("--max-pages", type=int, default=None)

    p_probe = sub.add_parser("spotify-probe")
    p_probe.add_argument("--provider-user-id", default=None)

    p_mb = sub.add_parser("musicbrainz-status")
    p_mb_resolve = sub.add_parser("musicbrainz-resolve")
    p_mb_resolve.add_argument("--limit", type=int, default=25)
    p_mb_resolve.add_argument("--force-retry", action="store_true")

    p_src = sub.add_parser("enrichment-sources")
    p_src.set_defaults(func=cmd_enrichment_sources)

    p_eval = sub.add_parser("enrichment-evaluate")
    p_eval.add_argument("--sample-file", default="fixtures/enrichment/m3_sample.json")
    p_eval.add_argument("--limit", type=int, default=0)
    p_eval.add_argument("--artifacts-dir", default="docs/api-research")
    p_eval.set_defaults(func=cmd_enrichment_evaluate)

    p_sc = sub.add_parser("soundcharts-probe")
    p_sc.add_argument("--sample-file", default="fixtures/enrichment/m4a_soundcharts_sample.json")
    p_sc.add_argument("--limit", type=int, default=0)
    p_sc.add_argument("--artifacts-dir", default="docs/api-research")
    p_sc.set_defaults(func=cmd_soundcharts_probe)

    p_gsb = sub.add_parser("getsongbpm-probe")
    p_gsb.add_argument("--sample-file", default="fixtures/enrichment/m4a_soundcharts_sample.json")
    p_gsb.add_argument("--limit", type=int, default=10)
    p_gsb.add_argument("--artifacts-dir", default="docs/api-research")
    p_gsb.set_defaults(func=cmd_getsongbpm_probe)

    p_enrich = sub.add_parser("enrich-library")
    p_enrich.add_argument("--source", default="getsongbpm", help="Enrichment source name (M4B: getsongbpm)")
    p_enrich.add_argument("--limit", type=int, default=25, help="Maximum tracks to consider this run")
    p_enrich.add_argument("--force", action="store_true", help="Re-query tracks that already have attributes for this source")
    p_enrich.add_argument("--dry-run", action="store_true", help="Plan only; do not perform any network calls")
    p_enrich.set_defaults(func=cmd_enrich_library)

    args = parser.parse_args(argv)
    if args.cmd == "status":
        asyncio.run(cmd_status(args))
    elif args.cmd == "import-liked":
        asyncio.run(cmd_import_liked(args))
    elif args.cmd == "spotify-probe":
        asyncio.run(cmd_spotify_probe(args))
    elif args.cmd == "musicbrainz-status":
        asyncio.run(cmd_musicbrainz_status(args))
    elif args.cmd == "musicbrainz-resolve":
        asyncio.run(cmd_musicbrainz_resolve(args))
    elif args.cmd == "enrichment-sources":
        asyncio.run(cmd_enrichment_sources(args))
    elif args.cmd == "enrichment-evaluate":
        asyncio.run(cmd_enrichment_evaluate(args))
    elif args.cmd == "soundcharts-probe":
        asyncio.run(cmd_soundcharts_probe(args))
    elif args.cmd == "getsongbpm-probe":
        asyncio.run(cmd_getsongbpm_probe(args))
    elif args.cmd == "enrich-library":
        asyncio.run(cmd_enrich_library(args))


if __name__ == "__main__":
    main()
