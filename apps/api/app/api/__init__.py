"""FastAPI HTTP routes."""

from __future__ import annotations

import logging
import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import state_store
from app.db import get_db
from app.models import (
    MusicAccount,
    OAuthToken,
    Playlist,
    PlaylistTrack,
    ProviderTrack,
    Track,
    TrackIdentifier,
)
from app.providers.base.errors import (
    ProviderAuthenticationError,
    ProviderPermissionError,
    ProviderRateLimitError,
    ProviderReauthRequiredError,
)
from app.providers.spotify import oauth
from app.providers.spotify.provider import SpotifyProvider
from app.tracks import (
    ImportStats,
    count_local_provider_tracks,
    import_provider_tracks,
    latest_local_saved_at,
)
from app.api import library as library_routes
from app.api import flows as flows_routes

log = logging.getLogger(__name__)

router = APIRouter()
router.include_router(library_routes.library_router)
router.include_router(flows_routes.flows_router)


@router.post("/smart-flow")
def smart_flow(req: dict, db: Session = Depends(get_db)) -> dict:
    from app.smart_flow.models import SmartFlowRequest
    from app.smart_flow.service import generate_smart_flow

    try:
        parsed = SmartFlowRequest(**req)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    # Validate shape
    if parsed.energy_shape not in ["maintain","build","drop","wave","peak_middle","peak_end"]:
        raise HTTPException(status_code=400, detail="invalid energy_shape")
    return generate_smart_flow(db, parsed)


@router.post("/smart-flow/preview")
def smart_flow_preview(req: dict, db: Session = Depends(get_db)) -> dict:
    from app.smart_flow.models import SmartFlowRequest
    from app.smart_flow.service import generate_smart_flow

    try:
        parsed = SmartFlowRequest(**req)
        # preview caps candidate pool
        if parsed.target_track_count > 10:
            parsed.target_track_count = 10
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return generate_smart_flow(db, parsed)


# ---- auth ----

@router.get("/auth/spotify/login")
def spotify_login() -> dict[str, str]:
    state = secrets.token_urlsafe(24)
    verifier, challenge = oauth.make_pkce_pair()
    state_store.put(state, verifier)
    return {
        "authorization_url": oauth.build_authorization_url(
            state=state, code_challenge=challenge
        ),
        "state": state,
    }


@router.get("/auth/spotify/callback")
async def spotify_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    verifier = state_store.pop(state)
    if not verifier:
        raise HTTPException(400, "invalid or expired state")
    try:
        token_payload = await oauth.exchange_code(code=code, code_verifier=verifier)
    except oauth.SpotifyOAuthError as e:
        raise HTTPException(400, f"token exchange failed: {e}") from e

    access_token = token_payload["access_token"]
    refresh_token = token_payload.get("refresh_token")
    expires_in = token_payload.get("expires_in")
    scope = token_payload.get("scope")
    token_type = token_payload.get("token_type", "Bearer")

    provider = SpotifyProvider(access_token=access_token)
    try:
        user = await provider.get_current_user()
    finally:
        await provider.aclose()

    from app.auth import upsert_account, upsert_token

    account = upsert_account(
        db,
        provider=user.provider,
        provider_user_id=user.provider_user_id,
        display_name=user.display_name,
    )
    upsert_token(
        db,
        account=account,
        access_token=access_token,
        refresh_token=refresh_token,
        token_type=token_type,
        scope=scope,
        expires_in=expires_in,
    )
    db.commit()
    return {
        "provider": user.provider,
        "provider_user_id": user.provider_user_id,
        "display_name": user.display_name,
    }


async def _refresh_spotify_token(db: Session, account: MusicAccount, token: OAuthToken) -> str:
    from app.auth import upsert_token

    if not token.refresh_token:
        raise ProviderReauthRequiredError("Reconnect Spotify")
    try:
        new_data = await oauth.refresh_tokens(refresh_token=token.refresh_token)
    except oauth.SpotifyOAuthError:
        raise ProviderReauthRequiredError("Reconnect Spotify")
    upsert_token(
        db,
        account=account,
        access_token=new_data["access_token"],
        refresh_token=new_data.get("refresh_token"),
        token_type=new_data.get("token_type", "Bearer"),
        scope=new_data.get("scope"),
        expires_in=new_data.get("expires_in"),
    )
    db.commit()
    return new_data["access_token"]


# ---- status / counts ----

@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict[str, Any]:
    accounts = db.execute(select(MusicAccount)).scalars().all()
    track_total = db.scalar(select(func.count(Track.id))) or 0
    provider_tracks = db.scalar(select(func.count(ProviderTrack.id))) or 0
    isrc_count = db.scalar(
        select(func.count(TrackIdentifier.id)).where(
            TrackIdentifier.identifier_type == "isrc"
        )
    ) or 0
    playlists = db.scalar(select(func.count(Playlist.id))) or 0
    return {
        "connected_accounts": [
            {
                "id": a.id,
                "provider": a.provider,
                "provider_user_id": a.provider_user_id,
                "display_name": a.display_name,
                "is_active": a.is_active,
            }
            for a in accounts
        ],
        "tracks": track_total,
        "provider_tracks": provider_tracks,
        "isrc_identifiers": isrc_count,
        "playlists": playlists,
    }


# ---- liked songs import ----

@router.post("/import/liked-songs")
async def import_liked_songs(
    provider_user_id: str = Query(...),
    max_pages: int | None = Query(None, ge=1, le=2000),
    force: bool = Query(False, description="Skip the short-circuit check and always re-paginate Spotify."),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    account = db.execute(
        select(MusicAccount).where(
            MusicAccount.provider == "spotify",
            MusicAccount.provider_user_id == provider_user_id,
        )
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(404, "no connected spotify account for that user")
    token = db.execute(
        select(OAuthToken).where(OAuthToken.account_id == account.id)
    ).scalar_one_or_none()
    if token is None:
        raise HTTPException(400, "no token for account; reconnect")

    started = time.monotonic()
    provider = SpotifyProvider(access_token=token.access_token)
    try:
        try:
            remote_total, remote_latest_saved_at = await provider.peek_saved_tracks()
        except ProviderAuthenticationError as exc:
            try:
                new_access_token = await _refresh_spotify_token(db, account, token)
            except ProviderReauthRequiredError as reauth_exc:
                raise HTTPException(401, str(reauth_exc)) from reauth_exc
            provider = SpotifyProvider(access_token=new_access_token)
            remote_total, remote_latest_saved_at = await provider.peek_saved_tracks()
        except ProviderPermissionError as exc:
            raise HTTPException(
                403, f"spotify permission denied: {exc.message}"
            ) from exc
        except ProviderRateLimitError as exc:
            retry_after = exc.retry_after
            headers = {"Retry-After": str(int(retry_after or 1))} if retry_after else None
            raise HTTPException(
                429, f"spotify rate limited: {exc.message}", headers=headers,
            ) from exc

        local_total = count_local_provider_tracks(db, provider="spotify")
        local_latest_saved_at = latest_local_saved_at(db, provider="spotify")

        if (
            not force
            and max_pages is None
            and local_total == remote_total
            and _saved_at_equals(local_latest_saved_at, remote_latest_saved_at)
        ):
            stats = ImportStats(
                local_total=local_total,
                remote_total=remote_total,
                short_circuited=True,
            )
            log.info(
                "import_liked_songs short_circuited provider_user_id=%s "
                "local_total=%d remote_total=%d duration_ms=%.1f",
                provider_user_id, local_total, remote_total,
                (time.monotonic() - started) * 1000,
            )
            return stats.as_dict()

        items: list = []
        pages_fetched = 0
        page_cap = max_pages if max_pages is not None else 10_000
        try:
            async for t in provider.iter_saved_tracks(limit=50):
                items.append(t)
                if len(items) % 50 == 0:
                    pages_fetched += 1
                if pages_fetched >= page_cap:
                    break
        except ProviderAuthenticationError as exc:
            try:
                new_access_token = await _refresh_spotify_token(db, account, token)
            except ProviderReauthRequiredError as reauth_exc:
                raise HTTPException(401, str(reauth_exc)) from reauth_exc
            provider = SpotifyProvider(access_token=new_access_token)
            async for t in provider.iter_saved_tracks(limit=50):
                items.append(t)
                if len(items) % 50 == 0:
                    pages_fetched += 1
                if pages_fetched >= page_cap:
                    break
        except ProviderPermissionError as exc:
            raise HTTPException(
                403, f"spotify permission denied: {exc.message}"
            ) from exc
        except ProviderRateLimitError as exc:
            retry_after = exc.retry_after
            headers = {"Retry-After": str(int(retry_after or 1))} if retry_after else None
            raise HTTPException(
                429, f"spotify rate limited: {exc.message}", headers=headers,
            ) from exc

        stats = import_provider_tracks(db, items)
        stats.pages_fetched = pages_fetched
        stats.remote_total = remote_total
        stats.local_total = local_total
        log.info(
            "import_liked_songs completed provider_user_id=%s fetched=%d "
            "created=%d existing=%d pages=%d duration_ms=%.1f",
            provider_user_id, stats.fetched, stats.provider_tracks_created,
            stats.provider_tracks_existing, stats.pages_fetched,
            (time.monotonic() - started) * 1000,
        )
    finally:
        await provider.aclose()
    return stats.as_dict()


def _saved_at_equals(a: Any, b: Any) -> bool:
    """Compare two saved_at values, tolerating timezone / naive mismatches.

    SQLite stores DateTime(timezone=True) as ISO strings without timezone
    info, so values coming back from func.max() are naive datetimes while
    the live API value is an aware datetime. Normalize both to naive UTC
    and compare.
    """
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    a_n = _to_naive_utc(a)
    b_n = _to_naive_utc(b)
    if a_n is None or b_n is None:
        return False
    return a_n == b_n


def _to_naive_utc(value: Any) -> Optional[Any]:
    if value is None:
        return None
    tz = getattr(value, "tzinfo", None)
    if tz is not None:
        try:
            from datetime import timezone
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            return None
    return value


def _to_iso(value: Any) -> Optional[str]:
    if isinstance(value, str):
        return value
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        try:
            return iso()
        except Exception:
            return None
    return None


# ---- disposable test playlist (for the reality probe) ----

@router.post("/probe/playlist")
async def probe_create_playlist(
    provider_user_id: str = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a disposable test playlist and add a few tracks.

    Intended ONLY for the M0 reality probe. Do not call from production code.
    """
    account = db.execute(
        select(MusicAccount).where(
            MusicAccount.provider == "spotify",
            MusicAccount.provider_user_id == provider_user_id,
        )
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(404, "no connected spotify account for that user")
    token = db.execute(
        select(OAuthToken).where(OAuthToken.account_id == account.id)
    ).scalar_one_or_none()
    if token is None:
        raise HTTPException(400, "no token for account; reconnect")

    provider = SpotifyProvider(access_token=token.access_token)
    try:
        try:
            summary = await provider.create_playlist(
                name="Music Intelligence M0 Test",
                description="Disposable test playlist created by the M0 reality probe.",
                is_public=False,
            )
        except ProviderAuthenticationError as exc:
            try:
                new_access_token = await _refresh_spotify_token(db, account, token)
            except ProviderReauthRequiredError as reauth_exc:
                raise HTTPException(401, str(reauth_exc)) from reauth_exc
            provider = SpotifyProvider(access_token=new_access_token)
            summary = await provider.create_playlist(
                name="Music Intelligence M0 Test",
                description="Disposable test playlist created by the M0 reality probe.",
                is_public=False,
            )
        except ProviderPermissionError as exc:
            raise HTTPException(
                403, f"spotify permission denied: {exc.message}"
            ) from exc
        except ProviderRateLimitError as exc:
            retry_after = exc.retry_after
            headers = {"Retry-After": str(int(retry_after or 1))} if retry_after else None
            raise HTTPException(
                429, f"spotify rate limited: {exc.message}", headers=headers,
            ) from exc

        spotify_ids = [
            pid
            for (pid,) in db.execute(
                select(ProviderTrack.provider_track_id)
                .where(ProviderTrack.provider == "spotify")
                .limit(3)
            ).all()
        ]
        snapshot = ""
        if spotify_ids:
            from app.providers.base.models import PlaylistRef

            try:
                snapshot = await provider.add_playlist_items(
                    PlaylistRef(
                        provider="spotify",
                        provider_playlist_id=summary.provider_playlist_id,
                    ),
                    provider_track_ids=spotify_ids,
                )
            except ProviderAuthenticationError as exc:
                try:
                    new_access_token = await _refresh_spotify_token(db, account, token)
                except ProviderReauthRequiredError as reauth_exc:
                    raise HTTPException(401, str(reauth_exc)) from reauth_exc
                provider = SpotifyProvider(access_token=new_access_token)
                snapshot = await provider.add_playlist_items(
                    PlaylistRef(
                        provider="spotify",
                        provider_playlist_id=summary.provider_playlist_id,
                    ),
                    provider_track_ids=spotify_ids,
                )
            except ProviderPermissionError as exc:
                raise HTTPException(
                    403, f"spotify permission denied: {exc.message}"
                ) from exc
            except ProviderRateLimitError as exc:
                retry_after = exc.retry_after
                headers = {"Retry-After": str(int(retry_after or 1))} if retry_after else None
                raise HTTPException(
                    429, f"spotify rate limited: {exc.message}", headers=headers,
                ) from exc
    finally:
        await provider.aclose()

    return {
        "created_playlist": {
            "id": summary.provider_playlist_id,
            "name": summary.name,
            "url": summary.provider_url,
        },
        "added_tracks": spotify_ids,
        "snapshot_id": snapshot,
    }
