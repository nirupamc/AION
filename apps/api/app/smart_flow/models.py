"""Smart Flow request/response models."""
from __future__ import annotations
from typing import Any, Optional, List
from pydantic import BaseModel, Field, field_validator

class SmartFlowFilters(BaseModel):
    mood: Optional[List[str]] = None
    vibe: Optional[List[str]] = None
    bpm_min: Optional[int] = None
    bpm_max: Optional[int] = None
    allowed_camelot: Optional[List[str]] = None
    set_role: Optional[List[str]] = None

class SmartFlowRequest(BaseModel):
    start_track_id: Optional[int] = None
    candidate_track_ids: Optional[List[int]] = None
    target_track_count: int = Field(..., ge=2, le=30)
    target_duration_minutes: Optional[int] = Field(None, ge=5, le=300)
    energy_shape: str = Field("maintain", description="maintain|build|drop|wave|peak_middle|peak_end")

    @field_validator("energy_shape")
    @classmethod
    def validate_energy_shape(cls, v: str) -> str:
        allowed = {"maintain","build","drop","wave","peak_middle","peak_end"}
        if v not in allowed:
            raise ValueError(f"invalid energy_shape {v}")
        return v
    bpm_range: Optional[List[int]] = None
    allowed_camelot: Optional[List[str]] = None
    mood: Optional[List[str]] = None
    vibe: Optional[List[str]] = None
    set_role: Optional[List[str]] = None
    max_repeat_artist: Optional[int] = Field(1, ge=1, le=10)
    minimum_transition_score: Optional[int] = Field(None, ge=0, le=100)
    filters: Optional[SmartFlowFilters] = None
    # legacy flat filters compat
    bpm_min: Optional[int] = None
    bpm_max: Optional[int] = None

    class Config:
        extra = "ignore"

class SmartFlowTrack(BaseModel):
    position: int
    track: dict[str, Any]
    transition_from_previous: Optional[dict[str, Any]] = None

class SmartFlowResponse(BaseModel):
    sequence: List[SmartFlowTrack]
    overall_sequence_score: int
    average_transition_score: Optional[float] = None
    minimum_transition_score: Optional[int] = None
    energy_shape: str
    energy_profile: List[float]
    actual_energies: List[Optional[float]]
    warnings: List[str] = []
    status: str = "ok"  # ok | insufficient_candidates
    candidate_pool_size: int
    generation_time_ms: float
    beam_width: int
