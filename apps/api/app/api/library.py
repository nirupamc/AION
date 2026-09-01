"""HTTP routes for the Library Explorer (read-only)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.library import (
    ALLOWED_PAGE_SIZES,
    DEFAULT_PAGE_SIZE,
    HAS_ISRC_OPTIONS,
    SORT_OPTIONS,
    ListParams,
    library_summary,
    list_tracks,
    track_detail,
)

library_router = APIRouter()


@library_router.get("/tracks")
def get_tracks(
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(
        DEFAULT_PAGE_SIZE, ge=1, le=max(ALLOWED_PAGE_SIZES),
        description="Items per page (max 100)",
    ),
    search: Optional[str] = Query(None, min_length=1, max_length=200),
    provider: Optional[str] = Query(None, description="Filter by provider, e.g. spotify"),
    has_isrc: str = Query("all", description="all | has | missing"),
    sort: str = Query("saved_desc", description="Sort key"),
    bpm_min: Optional[int] = Query(None, ge=0, le=400),
    bpm_max: Optional[int] = Query(None, ge=0, le=400),
    musical_key: Optional[str] = Query(
        None, description='Canonical key display, e.g. "C# minor"',
        min_length=1, max_length=32,
    ),
    camelot: Optional[str] = Query(None, description='Camelot code e.g. "8A"', min_length=2, max_length=3),
    mood: Optional[str] = Query(None, description='Filter by dominant mood e.g. "intense"', min_length=2, max_length=32),
    vibe: Optional[str] = Query(None, description='Filter by dominant vibe e.g. "driving"', min_length=2, max_length=32),
    db: Session = Depends(get_db),
):
    if has_isrc not in HAS_ISRC_OPTIONS:
        has_isrc = "all"
    if sort not in SORT_OPTIONS:
        sort = "saved_desc"
    if bpm_min is not None and bpm_max is not None and bpm_min > bpm_max:
        raise HTTPException(status_code=400, detail="bpm_min must be <= bpm_max")

    params = ListParams(
        page=page,
        page_size=page_size,
        search=search.strip() if search else None,
        provider=provider,
        has_isrc=has_isrc,
        sort=sort,
        bpm_min=bpm_min,
        bpm_max=bpm_max,
        musical_key=musical_key.strip() if musical_key else None,
        camelot=camelot.strip().upper() if camelot else None,
        mood=mood.strip().lower() if mood else None,
        vibe=vibe.strip().lower() if vibe else None,
    )
    try:
        return list_tracks(db, params=params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@library_router.get("/tracks/{track_id}/next")
def get_best_next(track_id: int, limit: int = Query(10, ge=1, le=20), energy_intent: str = Query("maintain", regex="^(maintain|build|drop)$"), db: Session = Depends(get_db)) -> dict:
    from app.transitions.service import get_best_next_tracks

    try:
        return get_best_next_tracks(db, track_id=track_id, limit=limit, energy_intent=energy_intent)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@library_router.get("/tracks/{track_id}/transition/{other_track_id}")
def get_transition(track_id: int, other_track_id: int, energy_intent: str = Query("maintain", regex="^(maintain|build|drop)$"), db: Session = Depends(get_db)) -> dict:
    from app.transitions.service import get_pair_transition

    try:
        return get_pair_transition(db, track_id_a=track_id, track_id_b=other_track_id, energy_intent=energy_intent)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@library_router.get("/tracks/{track_id}/compatible")
def get_compatible_tracks(track_id: int, limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)) -> dict:
    from app.library import compatible_tracks

    try:
        items = compatible_tracks(db, track_id=track_id, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"track_id": track_id, "compatible": items}


@library_router.get("/tracks/{track_id}/compatibility/{other_track_id}")
def get_compatibility(track_id: int, other_track_id: int, db: Session = Depends(get_db)) -> dict:
    from app.library import track_compatibility

    try:
        return track_compatibility(db, track_id=track_id, other_track_id=other_track_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@library_router.get("/tracks/{track_id}")
def get_track_detail(track_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return track_detail(db, track_id=track_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@library_router.get("/library/dna")
def get_library_dna(
    search: Optional[str] = Query(None, min_length=1, max_length=200),
    provider: Optional[str] = Query(None),
    has_isrc: str = Query("all"),
    bpm_min: Optional[int] = Query(None, ge=0, le=400),
    bpm_max: Optional[int] = Query(None, ge=0, le=400),
    musical_key: Optional[str] = Query(None, min_length=1, max_length=32),
    camelot: Optional[str] = Query(None, min_length=2, max_length=3),
    mood: Optional[str] = Query(None, min_length=2, max_length=32),
    vibe: Optional[str] = Query(None, min_length=2, max_length=32),
    db: Session = Depends(get_db),
) -> dict:
    from app.library import ListParams
    from app.library_analytics import get_library_dna as svc_dna

    if has_isrc not in HAS_ISRC_OPTIONS:
        has_isrc = "all"
    params = ListParams(
        page=1,
        page_size=50,
        search=search.strip() if search else None,
        provider=provider,
        has_isrc=has_isrc,
        sort="saved_desc",
        bpm_min=bpm_min,
        bpm_max=bpm_max,
        musical_key=musical_key.strip() if musical_key else None,
        camelot=camelot.strip().upper() if camelot else None,
        mood=mood.strip().lower() if mood else None,
        vibe=vibe.strip().lower() if vibe else None,
    )
    return svc_dna(db, params)


@library_router.get("/library/analytics/bpm")
def get_bpm_analytics(
    search: Optional[str] = Query(None, min_length=1, max_length=200),
    provider: Optional[str] = Query(None),
    has_isrc: str = Query("all"),
    bpm_min: Optional[int] = Query(None, ge=0, le=400),
    bpm_max: Optional[int] = Query(None, ge=0, le=400),
    musical_key: Optional[str] = Query(None, min_length=1, max_length=32),
    camelot: Optional[str] = Query(None, min_length=2, max_length=3),
    mood: Optional[str] = Query(None, min_length=2, max_length=32),
    vibe: Optional[str] = Query(None, min_length=2, max_length=32),
    db: Session = Depends(get_db),
) -> dict:
    from app.library import ListParams
    from app.library_analytics import get_bpm_distribution

    if has_isrc not in HAS_ISRC_OPTIONS:
        has_isrc = "all"
    params = ListParams(
        page=1, page_size=50, search=search.strip() if search else None, provider=provider, has_isrc=has_isrc, sort="saved_desc",
        bpm_min=bpm_min, bpm_max=bpm_max, musical_key=musical_key.strip() if musical_key else None,
        camelot=camelot.strip().upper() if camelot else None,
        mood=mood.strip().lower() if mood else None, vibe=vibe.strip().lower() if vibe else None,
    )
    return get_bpm_distribution(db, params)


@library_router.get("/library/analytics/energy")
def get_energy_analytics(
    search: Optional[str] = Query(None, min_length=1, max_length=200),
    provider: Optional[str] = Query(None),
    has_isrc: str = Query("all"),
    bpm_min: Optional[int] = Query(None, ge=0, le=400),
    bpm_max: Optional[int] = Query(None, ge=0, le=400),
    musical_key: Optional[str] = Query(None, min_length=1, max_length=32),
    camelot: Optional[str] = Query(None, min_length=2, max_length=3),
    mood: Optional[str] = Query(None, min_length=2, max_length=32),
    vibe: Optional[str] = Query(None, min_length=2, max_length=32),
    db: Session = Depends(get_db),
) -> dict:
    from app.library import ListParams
    from app.library_analytics import get_energy_distribution

    if has_isrc not in HAS_ISRC_OPTIONS:
        has_isrc = "all"
    params = ListParams(
        page=1, page_size=50, search=search.strip() if search else None, provider=provider, has_isrc=has_isrc, sort="saved_desc",
        bpm_min=bpm_min, bpm_max=bpm_max, musical_key=musical_key.strip() if musical_key else None,
        camelot=camelot.strip().upper() if camelot else None,
        mood=mood.strip().lower() if mood else None, vibe=vibe.strip().lower() if vibe else None,
    )
    return get_energy_distribution(db, params)


@library_router.get("/library/analytics/scatter")
def get_scatter_analytics(
    search: Optional[str] = Query(None, min_length=1, max_length=200),
    provider: Optional[str] = Query(None),
    has_isrc: str = Query("all"),
    bpm_min: Optional[int] = Query(None, ge=0, le=400),
    bpm_max: Optional[int] = Query(None, ge=0, le=400),
    musical_key: Optional[str] = Query(None, min_length=1, max_length=32),
    camelot: Optional[str] = Query(None, min_length=2, max_length=3),
    mood: Optional[str] = Query(None, min_length=2, max_length=32),
    vibe: Optional[str] = Query(None, min_length=2, max_length=32),
    limit: int = Query(500, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict:
    from app.library import ListParams
    from app.library_analytics import get_scatter_data

    if has_isrc not in HAS_ISRC_OPTIONS:
        has_isrc = "all"
    params = ListParams(
        page=1, page_size=50, search=search.strip() if search else None, provider=provider, has_isrc=has_isrc, sort="saved_desc",
        bpm_min=bpm_min, bpm_max=bpm_max, musical_key=musical_key.strip() if musical_key else None,
        camelot=camelot.strip().upper() if camelot else None,
        mood=mood.strip().lower() if mood else None, vibe=vibe.strip().lower() if vibe else None,
    )
    return get_scatter_data(db, params, limit=limit)


@library_router.get("/library/summary")
def get_library_summary(db: Session = Depends(get_db)) -> dict:
    return library_summary(db)
