"""FastAPI routes for saved flows, export, and CRUD."""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db

flows_router = APIRouter(prefix="/flows", tags=["flows"])


# ─── Request models ───

class SaveFlowRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    flow_response: dict[str, Any]
    request_params: dict[str, Any]

    class Config:
        extra = "ignore"


class RenameFlowRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None

    class Config:
        extra = "ignore"


class SpotifyExportRequest(BaseModel):
    playlist_name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    public: bool = False

    class Config:
        extra = "ignore"


# ─── CRUD ───

@flows_router.get("")
def list_flows(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = __import__("fastapi", fromlist=["Depends"]).Depends(get_db),
) -> dict[str, Any]:
    from app.flows import list_flows as _list
    flows = _list(db, limit=limit, offset=offset)
    return {"flows": flows, "count": len(flows)}


@flows_router.get("/{flow_id}")
def get_flow(flow_id: int, db: Session = __import__("fastapi", fromlist=["Depends"]).Depends(get_db)) -> dict[str, Any]:
    from app.flows import get_flow as _get
    result = _get(db, flow_id)
    if not result:
        raise HTTPException(404, "flow not found")
    return result


@flows_router.post("")
def create_flow(req: SaveFlowRequest, db: Session = __import__("fastapi", fromlist=["Depends"]).Depends(get_db)) -> dict[str, Any]:
    from app.flows import save_flow
    flow = save_flow(
        db,
        name=req.name,
        description=req.description,
        flow_response=req.flow_response,
        request_params=req.request_params,
    )
    return {
        "id": flow.id,
        "name": flow.name,
        "track_count": len(flow.tracks),
        "created_at": flow.created_at.isoformat() if flow.created_at else None,
    }


@flows_router.patch("/{flow_id}")
def rename_flow(flow_id: int, req: RenameFlowRequest, db: Session = __import__("fastapi", fromlist=["Depends"]).Depends(get_db)) -> dict[str, Any]:
    from app.flows import rename_flow as _rename
    result = _rename(db, flow_id, name=req.name, description=req.description)
    if not result:
        raise HTTPException(404, "flow not found")
    return result


@flows_router.delete("/{flow_id}")
def delete_flow(flow_id: int, db: Session = __import__("fastapi", fromlist=["Depends"]).Depends(get_db)) -> dict[str, str]:
    from app.flows import delete_flow as _delete
    ok = _delete(db, flow_id)
    if not ok:
        raise HTTPException(404, "flow not found")
    return {"status": "deleted"}


# ─── SAVE from generated flow ───

@flows_router.post("/save")
def save_generated_flow(req: SaveFlowRequest, db: Session = __import__("fastapi", fromlist=["Depends"]).Depends(get_db)) -> dict[str, Any]:
    """Save a Smart Flow response directly."""
    from app.flows import save_flow
    flow = save_flow(
        db,
        name=req.name,
        description=req.description,
        flow_response=req.flow_response,
        request_params=req.request_params,
    )
    return {
        "id": flow.id,
        "name": flow.name,
        "track_count": len(flow.tracks),
        "created_at": flow.created_at.isoformat() if flow.created_at else None,
    }


# ─── EXPORTS ───

@flows_router.get("/{flow_id}/export/text")
def export_text(flow_id: int, db: Session = __import__("fastapi", fromlist=["Depends"]).Depends(get_db)) -> Response:
    from app.flows import export_text as _text, _sanitize_filename
    text = _text(db, flow_id)
    if not text:
        raise HTTPException(404, "flow not found")
    # Extract flow name for filename
    from app.models import SavedFlow
    flow = db.get(SavedFlow, flow_id)
    fname = _sanitize_filename(flow.name if flow else "aion-flow")
    from datetime import date
    today = date.today().isoformat()
    return Response(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="aion-{fname}-{today}.txt"'},
    )


@flows_router.get("/{flow_id}/export/csv")
def export_csv(flow_id: int, db: Session = __import__("fastapi", fromlist=["Depends"]).Depends(get_db)) -> Response:
    from app.flows import export_csv as _csv, _sanitize_filename
    csv_text = _csv(db, flow_id)
    if not csv_text:
        raise HTTPException(404, "flow not found")
    from app.models import SavedFlow
    flow = db.get(SavedFlow, flow_id)
    fname = _sanitize_filename(flow.name if flow else "aion-flow")
    from datetime import date
    today = date.today().isoformat()
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="aion-{fname}-{today}.csv"'},
    )


@flows_router.get("/{flow_id}/export/json")
def export_json(flow_id: int, db: Session = __import__("fastapi", fromlist=["Depends"]).Depends(get_db)) -> dict[str, Any]:
    from app.flows import export_json as _json
    result = _json(db, flow_id)
    if not result:
        raise HTTPException(404, "flow not found")
    return result


@flows_router.post("/{flow_id}/export/spotify")
async def export_spotify(
    flow_id: int,
    req: SpotifyExportRequest,
    db: Session = __import__("fastapi", fromlist=["Depends"]).Depends(get_db),
) -> dict[str, Any]:
    from app.flows import export_to_spotify
    try:
        result = await export_to_spotify(
            db,
            flow_id,
            playlist_name=req.playlist_name,
            description=req.description,
            is_public=req.public,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"export failed: {e}") from e
    return result
