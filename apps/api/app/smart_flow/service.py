"""Smart Flow service."""
from __future__ import annotations
import time
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import Track, ProviderTrack, TrackAttribute
from app.library import ListParams
from app.transitions.features import load_transition_features
from .scoring import target_energy_profile, sequence_energy_score, overall_sequence_score
from .optimizer import beam_search, greedy_baseline
from app.transitions.service import score_transition

def _build_candidate_pool(session: Session, req) -> list[int]:
    # Merge filters from req and req.filters
    bpm_min = req.bpm_min or (req.filters.bpm_min if req.filters else None)
    bpm_max = req.bpm_max or (req.filters.bpm_max if req.filters else None)
    mood = req.mood or (req.filters.mood if req.filters else None)
    vibe = req.vibe or (req.filters.vibe if req.filters else None)
    # candidate_track_ids if provided
    if req.candidate_track_ids:
        base_ids = req.candidate_track_ids
        # validate existence
        existing = session.execute(select(Track.id).where(Track.id.in_(base_ids))).scalars().all()
        base_ids = [tid for tid in base_ids if tid in existing]
    else:
        # Build from enriched tracks with filters
        # Use ListParams to reuse filter logic? Simpler: get all enriched track ids then filter via library
        # For now, get all distinct enriched track ids
        all_enriched = session.execute(select(TrackAttribute.track_id).where(TrackAttribute.attribute_type=="tempo_bpm").distinct()).scalars().all()
        # Apply filters via library if needed: we will filter via Python after
        base_ids = all_enriched

    # Apply additional hard filters: bpm_range, allowed_camelot, mood/vibe/set_role via Python
    # For simplicity, if filters present, use library to filter?
    # We'll do Python filtering for mood/vibe/camelot/bpm
    if any([mood, vibe, req.allowed_camelot, req.set_role, bpm_min is not None, bpm_max is not None]):
        # Load features for base_ids and filter
        feats = load_transition_features(session, base_ids)
        filtered=[]
        for tid in base_ids:
            f = feats.get(tid)
            if not f:
                continue
            if bpm_min is not None and f.tempo_bpm is not None and f.tempo_bpm < bpm_min:
                continue
            if bpm_max is not None and f.tempo_bpm is not None and f.tempo_bpm > bpm_max:
                continue
            if req.allowed_camelot and f.camelot not in req.allowed_camelot:
                continue
            if mood:
                # mood may be list or string
                moods = mood if isinstance(mood, list) else [mood]
                if f.dominant_mood not in moods and not any(f.mood_scores.get(m,0)>0.5 for m in moods):
                    continue
            if vibe:
                vibes = vibe if isinstance(vibe, list) else [vibe]
                if f.dominant_vibe not in vibes and not any(f.vibe_scores.get(v,0)>0.5 for v in vibes):
                    continue
            if req.set_role:
                roles = req.set_role if isinstance(req.set_role, list) else [req.set_role]
                if f.set_role not in roles:
                    continue
            filtered.append(tid)
        base_ids = filtered

    return sorted(set(base_ids))

def generate_smart_flow(session: Session, req) -> dict[str, Any]:
    start = time.time()
    candidate_ids = _build_candidate_pool(session, req)
    # Artist map for repetition
    # Fetch provider tracks for artist
    artist_map: dict[int, str] = {}
    if candidate_ids:
        # include start track even if not in candidate_ids
        all_for_artist = set(candidate_ids)
        if req.start_track_id:
            all_for_artist.add(req.start_track_id)
        pts = session.execute(select(ProviderTrack.track_id, ProviderTrack.artist_display).where(ProviderTrack.track_id.in_(list(all_for_artist)))).all()
        # Need first artist per track
        for tid, artist in pts:
            # artist_display may be comma joined; take first
            if artist:
                first = artist.split(",")[0].strip()
                artist_map[tid] = first
            else:
                artist_map[tid] = ""

    # Ensure start track in pool if provided
    if req.start_track_id and req.start_track_id not in candidate_ids:
        # Check if start track exists and is enriched? If not, still allow but we will handle
        # For now, add it
        if session.get(Track, req.start_track_id):
            candidate_ids.append(req.start_track_id)
            candidate_ids = sorted(set(candidate_ids))

    # Build features for candidates
    # Need also start track features
    all_needed = set(candidate_ids)
    if req.start_track_id:
        all_needed.add(req.start_track_id)
    feats = load_transition_features(session, list(all_needed))

    # Filter to only those with minimum evidence (tempo + harmonic/energy) – already enforced via candidate pool distinct tempo_bpm, but ensure
    # Remove candidates that lack minimum evidence
    filtered_candidates = {}
    for tid, f in feats.items():
        has_tempo = f.tempo_bpm is not None
        has_harmonic_or_energy = f.camelot is not None or f.energy is not None
        if has_tempo and has_harmonic_or_energy:
            filtered_candidates[tid] = f
        elif tid == req.start_track_id:
            # allow start even if missing? But then transitions will be low
            filtered_candidates[tid] = f

    # If candidate pool after filtering is empty
    if not filtered_candidates:
        return {
            "sequence": [],
            "overall_sequence_score": 0,
            "average_transition_score": None,
            "minimum_transition_score": None,
            "energy_shape": req.energy_shape,
            "energy_profile": target_energy_profile(req.energy_shape, req.target_track_count),
            "actual_energies": [],
            "warnings": ["no candidates with minimum evidence"],
            "status": "insufficient_candidates",
            "candidate_pool_size": 0,
            "generation_time_ms": (time.time()-start)*1000,
            "beam_width": 20,
        }

    # Check insufficient candidates vs target count
    unique_needed = req.target_track_count
    # If start provided, need at least target_count distinct tracks including start
    available = len(filtered_candidates)
    # If start not in filtered but we have it, count
    if req.start_track_id and req.start_track_id not in filtered_candidates:
        available +=1  # but we added

    if available < unique_needed:
        # Still try to generate best possible with available
        status = "insufficient_candidates"
    else:
        status = "ok"

    beam_width = 20
    seq, stats = beam_search(
        candidate_features=filtered_candidates,
        start_track_id=req.start_track_id,
        target_count=req.target_track_count,
        energy_shape=req.energy_shape,
        beam_width=beam_width,
        minimum_transition_score=req.minimum_transition_score,
        max_repeat_artist=req.max_repeat_artist,
        artist_map=artist_map,
    )

    if not seq:
        return {
            "sequence": [],
            "overall_sequence_score": 0,
            "average_transition_score": None,
            "minimum_transition_score": None,
            "energy_shape": req.energy_shape,
            "energy_profile": target_energy_profile(req.energy_shape, req.target_track_count),
            "actual_energies": [],
            "warnings": ["beam search found no viable sequence; constraints too strict"],
            "status": "insufficient_candidates",
            "candidate_pool_size": len(filtered_candidates),
            "generation_time_ms": (time.time()-start)*1000,
            "beam_width": beam_width,
        }

    # Compute sequence-level metrics
    # Need transition scores for seq
    transition_scores=[]
    actual_energies=[]
    for tid in seq:
        f = filtered_candidates.get(tid)
        actual_energies.append(f.energy if f else None)
    for i in range(len(seq)-1):
        src = filtered_candidates[seq[i]]
        dst = filtered_candidates[seq[i+1]]
        res = score_transition(src, dst, energy_intent=req.energy_shape if req.energy_shape in ["maintain","build","drop"] else "maintain")
        transition_scores.append(res["transition_score"])
    avg_trans = sum(transition_scores)/len(transition_scores) if transition_scores else None
    min_trans = min(transition_scores) if transition_scores else None
    target_profile = target_energy_profile(req.energy_shape, len(seq))
    e_score, mae = sequence_energy_score(actual_energies, target_profile)
    overall = overall_sequence_score(avg_trans, min_trans, e_score)

    # Warnings
    warnings=[]
    if min_trans is not None and min_trans < 60:
        warnings.append(f"weakest transition {min_trans}/100 is risky")
    if e_score < 60:
        warnings.append(f"energy shape adherence low {e_score}/100 (mae {mae:.2f})")
    if len(seq) < req.target_track_count:
        warnings.append(f"only {len(seq)} tracks found, requested {req.target_track_count}")

    # Build sequence response with track metadata and transition_from_previous
    from sqlalchemy import select as sel
    seq_response=[]
    for idx, tid in enumerate(seq):
        pt = session.execute(sel(ProviderTrack).where(ProviderTrack.track_id==tid).limit(1)).scalars().first()
        track_info = {
            "track_id": tid,
            "title": pt.raw_title if pt else None,
            "artist": pt.artist_display if pt else None,
            "bpm": filtered_candidates[tid].tempo_bpm,
            "camelot": filtered_candidates[tid].camelot,
            "energy": filtered_candidates[tid].energy,
            "dominant_mood": filtered_candidates[tid].dominant_mood,
            "dominant_vibe": filtered_candidates[tid].dominant_vibe,
            "set_role": filtered_candidates[tid].set_role,
        }
        trans = None
        if idx > 0:
            src = filtered_candidates[seq[idx-1]]
            dst = filtered_candidates[tid]
            res = score_transition(src, dst, energy_intent=req.energy_shape if req.energy_shape in ["maintain","build","drop"] else "maintain")
            trans = {
                "score": res["transition_score"],
                "components": res["components"],
                "reasons": res["reasons"],
                "warnings": res["warnings"],
                "missing_components": res["missing_components"],
                "from_bpm": src.tempo_bpm,
                "to_bpm": dst.tempo_bpm,
                "from_camelot": src.camelot,
                "to_camelot": dst.camelot,
            }
        seq_response.append({
            "position": idx+1,
            "track": track_info,
            "transition_from_previous": trans,
        })

    return {
        "sequence": seq_response,
        "overall_sequence_score": overall,
        "average_transition_score": round(avg_trans,2) if avg_trans is not None else None,
        "minimum_transition_score": min_trans,
        "energy_shape": req.energy_shape,
        "energy_profile": target_profile,
        "actual_energies": actual_energies,
        "warnings": warnings,
        "status": status if status=="insufficient_candidates" and len(seq) < req.target_track_count else "ok",
        "candidate_pool_size": len(filtered_candidates),
        "generation_time_ms": round((time.time()-start)*1000,2),
        "beam_width": beam_width,
        "target_track_count": req.target_track_count,
    }

def greedy_sequence_for_comparison(session: Session, req) -> dict[str, Any]:
    # Reuse same candidate pool but greedy
    from .optimizer import greedy_baseline
    candidate_ids = _build_candidate_pool(session, req)
    feats = load_transition_features(session, candidate_ids + ([req.start_track_id] if req.start_track_id else []))
    # filter minimum evidence
    filtered = {tid:f for tid,f in feats.items() if f.tempo_bpm is not None and (f.camelot is not None or f.energy is not None)}
    if not filtered:
        return {"average": None, "minimum": None, "overall": 0, "sequence": []}
    seq = greedy_baseline(filtered, start_track_id=req.start_track_id, target_count=req.target_track_count, energy_intent=req.energy_shape)
    if len(seq) <2:
        return {"average": None, "minimum": None, "overall": 0, "sequence": seq}
    scores=[]
    for i in range(len(seq)-1):
        res = score_transition(filtered[seq[i]], filtered[seq[i+1]], energy_intent=req.energy_shape if req.energy_shape in ["maintain","build","drop"] else "maintain")
        scores.append(res["transition_score"])
    avg = sum(scores)/len(scores) if scores else None
    mn = min(scores) if scores else None
    from .scoring import target_energy_profile, sequence_energy_score, overall_sequence_score
    actual = [filtered[tid].energy for tid in seq]
    target = target_energy_profile(req.energy_shape, len(seq))
    e_score,_ = sequence_energy_score(actual, target)
    overall = overall_sequence_score(avg, mn, e_score)
    return {"average": avg, "minimum": mn, "overall": overall, "sequence": seq, "energy_score": e_score}
