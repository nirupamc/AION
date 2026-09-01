"""Saved Flow CRUD, text export, CSV export, and Spotify export service."""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    FlowExport,
    MusicAccount,
    OAuthToken,
    ProviderTrack,
    SavedFlow,
    SavedFlowTrack,
    Track,
)


OPTIMIZER_VERSION = "m9-beam-v1"
TRANSITION_MODEL_VERSION = "m8-transition-v1"


# ─── SAVE ───

def save_flow(
    session: Session,
    *,
    name: str,
    description: Optional[str],
    flow_response: dict[str, Any],
    request_params: dict[str, Any],
) -> SavedFlow:
    """Persist a Smart Flow response as a SavedFlow with SavedFlowTracks."""
    flow = SavedFlow(
        name=name,
        description=description,
        start_track_id=request_params.get("start_track_id"),
        target_track_count=request_params.get("target_track_count", flow_response.get("target_track_count", 0)),
        energy_shape=flow_response.get("energy_shape", request_params.get("energy_shape", "maintain")),
        constraints_json=json.dumps({
            k: v for k, v in request_params.items()
            if k not in ("start_track_id", "target_track_count", "energy_shape")
            and v is not None
        }),
        overall_sequence_score=flow_response.get("overall_sequence_score"),
        average_transition_score=flow_response.get("average_transition_score"),
        minimum_transition_score=flow_response.get("minimum_transition_score"),
        optimizer_version=OPTIMIZER_VERSION,
        transition_model_version=TRANSITION_MODEL_VERSION,
        status=flow_response.get("status", "ok"),
    )
    session.add(flow)
    session.flush()

    for item in flow_response.get("sequence", []):
        track_data = item.get("track", {})
        trans = item.get("transition_from_previous") or {}
        sft = SavedFlowTrack(
            flow_id=flow.id,
            track_id=track_data.get("track_id", 0),
            position=item.get("position", 0),
            title=track_data.get("title"),
            artist=track_data.get("artist"),
            bpm=track_data.get("bpm"),
            camelot=track_data.get("camelot"),
            energy=track_data.get("energy"),
            dominant_mood=track_data.get("dominant_mood"),
            dominant_vibe=track_data.get("dominant_vibe"),
            transition_score=trans.get("score"),
            transition_components_json=json.dumps(trans.get("components")) if trans.get("components") else None,
            transition_reasons_json=json.dumps(trans.get("reasons")) if trans.get("reasons") else None,
            transition_warnings_json=json.dumps(trans.get("warnings")) if trans.get("warnings") else None,
        )
        session.add(sft)

    session.commit()
    session.refresh(flow)
    return flow


# ─── CRUD ───

def list_flows(session: Session, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    stmt = (
        select(SavedFlow)
        .order_by(SavedFlow.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    flows = session.execute(stmt).scalars().all()
    return [_flow_summary(f) for f in flows]


def get_flow(session: Session, flow_id: int) -> Optional[dict[str, Any]]:
    flow = session.get(SavedFlow, flow_id)
    if not flow:
        return None
    return _flow_detail(flow)


def delete_flow(session: Session, flow_id: int) -> bool:
    flow = session.get(SavedFlow, flow_id)
    if not flow:
        return False
    session.delete(flow)
    session.commit()
    return True


def rename_flow(session: Session, flow_id: int, name: str, description: Optional[str] = None) -> Optional[dict[str, Any]]:
    flow = session.get(SavedFlow, flow_id)
    if not flow:
        return None
    flow.name = name
    if description is not None:
        flow.description = description
    session.commit()
    session.refresh(flow)
    return _flow_summary(flow)


def _flow_summary(f: SavedFlow) -> dict[str, Any]:
    return {
        "id": f.id,
        "name": f.name,
        "description": f.description,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "track_count": len(f.tracks) if f.tracks else 0,
        "energy_shape": f.energy_shape,
        "overall_sequence_score": f.overall_sequence_score,
        "average_transition_score": f.average_transition_score,
        "minimum_transition_score": f.minimum_transition_score,
        "status": f.status,
    }


def _flow_detail(f: SavedFlow) -> dict[str, Any]:
    tracks = sorted(f.tracks, key=lambda t: t.position) if f.tracks else []
    exports = sorted(f.exports, key=lambda e: e.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True) if f.exports else []
    return {
        **_flow_summary(f),
        "start_track_id": f.start_track_id,
        "target_track_count": f.target_track_count,
        "constraints_json": f.constraints_json,
        "optimizer_version": f.optimizer_version,
        "transition_model_version": f.transition_model_version,
        "sequence": [_track_dict(t) for t in tracks],
        "exports": [_export_summary(e) for e in exports],
    }


def _track_dict(t: SavedFlowTrack) -> dict[str, Any]:
    return {
        "position": t.position,
        "track": {
            "track_id": t.track_id,
            "title": t.title,
            "artist": t.artist,
            "bpm": t.bpm,
            "camelot": t.camelot,
            "energy": t.energy,
            "dominant_mood": t.dominant_mood,
            "dominant_vibe": t.dominant_vibe,
        },
        "transition_from_previous": {
            "score": t.transition_score,
            "components": json.loads(t.transition_components_json) if t.transition_components_json else None,
            "reasons": json.loads(t.transition_reasons_json) if t.transition_reasons_json else None,
            "warnings": json.loads(t.transition_warnings_json) if t.transition_warnings_json else None,
        } if t.transition_score is not None else None,
    }


def _export_summary(e: FlowExport) -> dict[str, Any]:
    return {
        "id": e.id,
        "provider": e.provider,
        "external_playlist_id": e.external_playlist_id,
        "external_playlist_url": e.external_playlist_url,
        "external_playlist_name": e.external_playlist_name,
        "exported_track_count": e.exported_track_count,
        "skipped_track_count": e.skipped_track_count,
        "skipped_tracks": json.loads(e.skipped_tracks_json) if e.skipped_tracks_json else [],
        "status": e.status,
        "error_summary": e.error_summary,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


# ─── TEXT DJ SET EXPORT ───

def export_text(session: Session, flow_id: int) -> Optional[str]:
    flow = session.get(SavedFlow, flow_id)
    if not flow:
        return None
    tracks = sorted(flow.tracks, key=lambda t: t.position)
    lines = []
    lines.append("AION SMART FLOW")
    lines.append(flow.name)
    if flow.description:
        lines.append(flow.description)
    lines.append(f"{len(tracks)} tracks")
    lines.append("")

    for t in tracks:
        pos = f"{t.position:02d}"
        artist_title = f"{t.artist} — {t.title}" if t.artist else (t.title or f"Track {t.track_id}")
        lines.append(f"{pos}. {artist_title}")
        meta_parts = []
        if t.bpm:
            meta_parts.append(f"{t.bpm:g} BPM")
        if t.camelot:
            meta_parts.append(t.camelot)
        if t.energy is not None:
            meta_parts.append(f"Energy {t.energy:.2f}")
        if t.dominant_mood:
            meta_parts.append(t.dominant_mood)
        if t.dominant_vibe:
            meta_parts.append(t.dominant_vibe)
        if meta_parts:
            lines.append(f"    {' · '.join(meta_parts)}")
        if t.transition_score is not None:
            lines.append(f"    ↓ {t.transition_score} transition")
        lines.append("")

    lines.append("Summary:")
    lines.append(f"Overall: {flow.overall_sequence_score or '—'}")
    lines.append(f"Average transition: {flow.average_transition_score or '—'}")
    lines.append(f"Weakest transition: {flow.minimum_transition_score or '—'}")
    lines.append(f"Energy shape: {flow.energy_shape}")
    lines.append("")
    lines.append(f"Generated by AION · {flow.optimizer_version or 'unknown'} optimizer")
    return "\n".join(lines)


# ─── CSV EXPORT ───

def export_csv(session: Session, flow_id: int) -> Optional[str]:
    flow = session.get(SavedFlow, flow_id)
    if not flow:
        return None
    tracks = sorted(flow.tracks, key=lambda t: t.position)

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "position", "title", "artist", "bpm", "key", "camelot", "energy",
        "mood", "vibe", "transition_score", "transition_reasons",
    ])
    for t in tracks:
        reasons = ""
        if t.transition_reasons_json:
            try:
                reasons = " | ".join(json.loads(t.transition_reasons_json))
            except Exception:
                reasons = t.transition_reasons_json
        writer.writerow([
            t.position,
            t.title or "",
            t.artist or "",
            t.bpm if t.bpm is not None else "",
            "",
            t.camelot or "",
            f"{t.energy:.2f}" if t.energy is not None else "",
            t.dominant_mood or "",
            t.dominant_vibe or "",
            t.transition_score if t.transition_score is not None else "",
            reasons,
        ])
    return buf.getvalue()


# ─── JSON EXPORT ───

def export_json(session: Session, flow_id: int) -> Optional[dict[str, Any]]:
    return get_flow(session, flow_id)


# ─── SPOTIFY EXPORT ───

def _sanitize_filename(name: str) -> str:
    """Remove characters unsafe for filenames."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
    name = name.strip('. ')
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:200] or "aion-flow"


async def export_to_spotify(
    session: Session,
    flow_id: int,
    *,
    playlist_name: str,
    description: str = "",
    is_public: bool = False,
) -> dict[str, Any]:
    """Export a saved flow to a Spotify playlist."""
    from app.providers.spotify.provider import SpotifyProvider
    from app.providers.base.errors import (
        ProviderAuthenticationError,
        ProviderPermissionError,
        ProviderRateLimitError,
        ProviderReauthRequiredError,
    )
    from app.providers.base.models import PlaylistRef
    from app.providers.spotify import oauth

    flow = session.get(SavedFlow, flow_id)
    if not flow:
        raise ValueError("flow not found")

    tracks = sorted(flow.tracks, key=lambda t: t.position)

    # Get Spotify account + token
    account = session.execute(
        select(MusicAccount).where(MusicAccount.provider == "spotify")
    ).scalar_one_or_none()
    if not account:
        raise ValueError("no connected Spotify account")

    token = session.execute(
        select(OAuthToken).where(OAuthToken.account_id == account.id)
    ).scalar_one_or_none()
    if not token:
        raise ValueError("no token for Spotify account")

    # Resolve Spotify track IDs
    skipped = []
    spotify_ids = []
    for t in tracks:
        pt = session.execute(
            select(ProviderTrack).where(
                ProviderTrack.track_id == t.track_id,
                ProviderTrack.provider == "spotify",
            ).limit(1)
        ).scalars().first()
        if pt and pt.provider_track_id:
            spotify_ids.append(pt.provider_track_id)
        else:
            skipped.append({
                "position": t.position,
                "title": t.title,
                "artist": t.artist,
                "reason": "no Spotify provider mapping",
            })

    # Create playlist
    provider = SpotifyProvider(access_token=token.access_token)
    try:
        try:
            summary = await provider.create_playlist(
                name=playlist_name,
                description=description or f"AION Smart Flow — {flow.name}",
                is_public=is_public,
            )
        except (ProviderAuthenticationError, ProviderPermissionError):
            from app.api import _refresh_spotify_token
            new_token = await _refresh_spotify_token(session, account, token)
            provider = SpotifyProvider(access_token=new_token)
            summary = await provider.create_playlist(
                name=playlist_name,
                description=description or f"AION Smart Flow — {flow.name}",
                is_public=is_public,
            )

        # Add tracks in batches of 100 (Spotify API limit)
        BATCH_SIZE = 100
        added_count = 0
        for i in range(0, len(spotify_ids), BATCH_SIZE):
            batch = spotify_ids[i:i + BATCH_SIZE]
            try:
                await provider.add_playlist_items(
                    PlaylistRef(
                        provider="spotify",
                        provider_playlist_id=summary.provider_playlist_id,
                    ),
                    provider_track_ids=batch,
                )
                added_count += len(batch)
            except (ProviderAuthenticationError, ProviderPermissionError):
                from app.api import _refresh_spotify_token
                new_token = await _refresh_spotify_token(session, account, token)
                provider = SpotifyProvider(access_token=new_token)
                await provider.add_playlist_items(
                    PlaylistRef(
                        provider="spotify",
                        provider_playlist_id=summary.provider_playlist_id,
                    ),
                    provider_track_ids=batch,
                )
                added_count += len(batch)
            except Exception as exc:
                skipped.append({
                    "batch_start": i,
                    "batch_end": i + len(batch),
                    "reason": str(exc),
                })

    finally:
        await provider.aclose()

    # Record export
    export = FlowExport(
        flow_id=flow.id,
        provider="spotify",
        external_playlist_id=summary.provider_playlist_id,
        external_playlist_url=summary.provider_url,
        external_playlist_name=summary.name,
        exported_track_count=added_count,
        skipped_track_count=len(skipped),
        skipped_tracks_json=json.dumps(skipped) if skipped else None,
        status="success" if not skipped else "partial",
    )
    session.add(export)
    session.commit()

    return {
        "provider": "spotify",
        "playlist_id": summary.provider_playlist_id,
        "playlist_url": summary.provider_url,
        "playlist_name": summary.name,
        "exported_track_count": added_count,
        "skipped_track_count": len(skipped),
        "skipped_tracks": skipped,
    }
