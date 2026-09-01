"""Hard vs soft constraints."""
from __future__ import annotations
from typing import Any, Optional

def check_hard_constraints(track_features, req, candidate_pool) -> list[str]:
    """Return list of violation reasons if hard constraint fails (empty if ok)."""
    # track must be enriched - check tempo or key or energy exists
    has_min = (track_features.tempo_bpm is not None) or (track_features.camelot is not None) or (track_features.energy is not None)
    # Actually require at least tempo + (harmonic or energy) as in M8
    has_tempo = track_features.tempo_bpm is not None
    has_harmonic_or_energy = track_features.camelot is not None or track_features.energy is not None
    if not (has_tempo and has_harmonic_or_energy):
        return ["missing minimum evidence (tempo + harmonic/energy)"]
    # BPM range
    bpm_min = req.bpm_min or (req.filters.bpm_min if req.filters and req.filters.bpm_min else None)
    bpm_max = req.bpm_max or (req.filters.bpm_max if req.filters and req.filters.bpm_max else None)
    if req.bpm_range and len(req.bpm_range)==2:
        bpm_min, bpm_max = req.bpm_range[0], req.bpm_range[1]
    if bpm_min is not None and track_features.tempo_bpm is not None and track_features.tempo_bpm < bpm_min:
        return [f"BPM {track_features.tempo_bpm} below min {bpm_min}"]
    if bpm_max is not None and track_features.tempo_bpm is not None and track_features.tempo_bpm > bpm_max:
        return [f"BPM {track_features.tempo_bpm} above max {bpm_max}"]
    allowed = req.allowed_camelot or (req.filters.allowed_camelot if req.filters and req.filters.allowed_camelot else None)
    if allowed and track_features.camelot not in allowed:
        return [f"Camelot {track_features.camelot} not allowed"]
    # mood/vibe hard filters if specified as exact required? For now treat as soft unless explicit?
    return []

def artist_violation(sequence_track_ids, candidate_artist, max_repeat, artist_map):
    if max_repeat is None:
        return False
    # count occurrences of candidate's artist in sequence
    # artist_map: track_id -> artist string (first artist)
    cand_art = artist_map.get(candidate_artist, "")
    if not cand_art:
        return False
    count = sum(1 for tid in sequence_track_ids if artist_map.get(tid)==cand_art)
    if count >= max_repeat:
        return True
    # also check within N positions? For v1, same as max_repeat
    return False
