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
    )
    try:
        return list_tracks(db, params=params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@library_router.get("/tracks/{track_id}")
def get_track_detail(track_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        return track_detail(db, track_id=track_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@library_router.get("/library/summary")
def get_library_summary(db: Session = Depends(get_db)) -> dict:
    return library_summary(db)
