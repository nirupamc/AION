"""Transition service."""
from __future__ import annotations
from typing import Any, Optional

from sqlalchemy.orm import Session

from .features import load_transition_features
from .models import TransitionTrackFeatures
from .scoring import (
    WEIGHTS, harmonic_score, tempo_score, energy_score, mood_score, vibe_score, set_role_score,
    loudness_warning, danceability_warning
)

def score_transition(src: TransitionTrackFeatures, dst: TransitionTrackFeatures, energy_intent: str = "maintain") -> dict[str, Any]:
    # Component scores
    h_score, h_rel = harmonic_score(src, dst)
    t_score, t_label, hd = tempo_score(src, dst)
    e_score, e_label = energy_score(src, dst, intent=energy_intent)
    m_score, m_label = mood_score(src, dst)
    v_score, v_label = vibe_score(src, dst)
    s_score, s_label = set_role_score(src, dst)

    components: dict[str, Optional[int]] = {
        "harmonic": h_score,
        "tempo": t_score,
        "energy": e_score,
        "mood": m_score,
        "vibe": v_score,
        "set_role": s_score,
    }
    labels = {
        "harmonic": h_rel,
        "tempo": t_label,
        "energy": e_label,
        "mood": m_label,
        "vibe": v_label,
        "set_role": s_label,
    }

    # Missing handling: omit None components and renormalize weights
    available = {k: v for k, v in components.items() if v is not None}
    missing = [k for k, v in components.items() if v is None]

    # Minimum evidence: require at least tempo + one of harmonic/energy
    has_tempo = t_score is not None
    has_harmonic_or_energy = (h_score is not None or e_score is not None)
    if not (has_tempo and has_harmonic_or_energy):
        # still compute but flag as low evidence? We allow but note missing
        pass

    total_weight = sum(WEIGHTS[k] for k in available.keys())
    if total_weight == 0:
        overall = 0
    else:
        weighted_sum = sum(available[k] * WEIGHTS[k] for k in available)
        overall = int(round(weighted_sum / total_weight))

    # Explanations
    reasons: list[str] = []
    warnings: list[str] = []

    if h_score is not None:
        if h_score == 100:
            reasons.append(f"Camelot {src.camelot} → {dst.camelot}: same key")
        elif h_score >= 95:
            reasons.append(f"Camelot {src.camelot} → {dst.camelot}: relative {h_rel}")
        elif h_score >= 90:
            reasons.append(f"Camelot {src.camelot} → {dst.camelot}: adjacent harmonic move")
        elif h_score >= 70:
            reasons.append(f"Camelot {src.camelot} → {dst.camelot}: diagonal {h_rel}")
        else:
            warnings.append(f"harmonic {h_rel} {h_score}/100")
            reasons.append(f"harmonic {h_rel}")

    if t_score is not None:
        reasons.append(f"BPM {src.tempo_bpm} → {dst.tempo_bpm}: {t_label}")
        if t_score < 60:
            warnings.append(f"BPM gap large {t_label}")
        if hd:
            reasons.append(f"half/double related ({hd})")

    if e_score is not None:
        reasons.append(f"energy {src.energy:.2f} → {dst.energy:.2f}: {e_label}")
        if energy_intent == "maintain" and abs((dst.energy or 0) - (src.energy or 0)) > 0.25:
            warnings.append("energy jump large for maintain intent")
        if energy_intent == "build" and (dst.energy or 0) < (src.energy or 0):
            warnings.append("build intent but energy drops")
        if energy_intent == "drop" and (dst.energy or 0) > (src.energy or 0):
            warnings.append("drop intent but energy rises")

    if m_score is not None:
        if m_score >= 70:
            reasons.append(f"mood continuity {m_score}/100")
        else:
            warnings.append(f"mood shift {m_score}/100")

    if v_score is not None:
        if v_score >= 70:
            reasons.append(f"vibe continuity {v_score}/100 ({src.dominant_vibe}→{dst.dominant_vibe})")

    # optional warnings for loudness/danceability
    lw = loudness_warning(src, dst)
    if lw:
        warnings.append(lw)
    dw = danceability_warning(src, dst)
    if dw:
        warnings.append(dw)

    # Valence loudness etc not separate components but could be warnings for large valence shift
    if src.valence is not None and dst.valence is not None:
        if abs(src.valence - dst.valence) > 0.4:
            warnings.append(f"valence shift {src.valence:.2f}→{dst.valence:.2f}")

    return {
        "transition_score": overall,
        "components": components,
        "missing_components": missing,
        "labels": labels,
        "reasons": reasons,
        "warnings": warnings,
        "energy_intent": energy_intent,
    }


def get_best_next_tracks(session: Session, track_id: int, limit: int = 10, energy_intent: str = "maintain", bpm_tolerance: Optional[float] = None, exclude_track_ids: Optional[list[int]] = None) -> dict[str, Any]:
    from app.models import Track
    base = session.get(Track, track_id)
    if base is None:
        raise ValueError("track not found")
    # Load source features
    src_map = load_transition_features(session, [track_id])
    src = src_map.get(track_id)
    if src is None:
        raise ValueError("source track not found")

    # Candidate pool: all enriched tracks with at least tempo or harmonic/energy
    from sqlalchemy import select
    from app.models import TrackAttribute
    candidate_ids = session.execute(select(TrackAttribute.track_id).where(TrackAttribute.attribute_type.in_(["tempo_bpm","musical_key","energy"])).distinct()).scalars().all()
    candidate_ids = [cid for cid in candidate_ids if cid != track_id]
    if exclude_track_ids:
        exclude_set = set(exclude_track_ids)
        candidate_ids = [cid for cid in candidate_ids if cid not in exclude_set]
    # Optional BPM prefilter broad window: if bpm_tolerance provided, filter within ±bpm_tolerance %
    if bpm_tolerance is not None and src.tempo_bpm is not None:
        # Keep only candidates within broad window (e.g., 20% or half/double)
        filtered=[]
        for cid in candidate_ids:
            # need tempo for candidate
            pass
        # For now not implemented, just keep all
        pass

    # Cap candidate pool for performance
    # deterministic sample: sort by track_id
    candidate_ids = sorted(set(candidate_ids))[:2000]
    # truncate to 1000 for scoring if large? Use 2000 cap already
    if len(candidate_ids) > 1000:
        candidate_ids = candidate_ids[:1000]

    dst_map = load_transition_features(session, candidate_ids)

    scored=[]
    for cid in candidate_ids:
        dst = dst_map.get(cid)
        if dst is None:
            continue
        # Minimum evidence: require at least tempo + (harmonic or energy)
        has_tempo = dst.tempo_bpm is not None and src.tempo_bpm is not None
        has_harmonic = dst.camelot is not None and src.camelot is not None
        has_energy = dst.energy is not None and src.energy is not None
        if not (has_tempo and (has_harmonic or has_energy)):
            continue
        result = score_transition(src, dst, energy_intent=energy_intent)
        scored.append((cid, dst, result))

    # Sort by transition_score desc, then track_id for stability
    scored.sort(key=lambda x: (-x[2]["transition_score"], x[0]))

    recommendations=[]
    # Need track metadata for response
    from app.models import ProviderTrack
    for cid, dst, res in scored[:limit]:
        # fetch provider title/artist for display
        pt = session.execute(select(ProviderTrack).where(ProviderTrack.track_id==cid).limit(1)).scalars().first()
        title = pt.raw_title if pt else None
        artist = pt.artist_display if pt else None
        recommendations.append({
            "track_id": cid,
            "title": title,
            "artist": artist,
            "transition_score": res["transition_score"],
            "components": res["components"],
            "reasons": res["reasons"],
            "warnings": res["warnings"],
            "missing_components": res["missing_components"],
            "energy_intent": res["energy_intent"],
            # include key/camelot/bpm etc for frontend display
            "bpm": dst.tempo_bpm,
            "camelot": dst.camelot,
            "energy": dst.energy,
            "dominant_mood": dst.dominant_mood,
            "dominant_vibe": dst.dominant_vibe,
        })

    # include source track info
    src_pt = session.execute(select(ProviderTrack).where(ProviderTrack.track_id==track_id).limit(1)).scalars().first()
    source_info = {
        "track_id": track_id,
        "title": src_pt.raw_title if src_pt else None,
        "artist": src_pt.artist_display if src_pt else None,
        "bpm": src.tempo_bpm,
        "camelot": src.camelot,
        "energy": src.energy,
        "dominant_mood": src.dominant_mood,
        "dominant_vibe": src.dominant_vibe,
    }

    return {
        "source_track": source_info,
        "energy_intent": energy_intent,
        "recommendations": recommendations,
    }

def get_pair_transition(session: Session, track_id_a: int, track_id_b: int, energy_intent: str = "maintain") -> dict[str, Any]:
    from app.models import Track
    if session.get(Track, track_id_a) is None or session.get(Track, track_id_b) is None:
        raise ValueError("track not found")
    m = load_transition_features(session, [track_id_a, track_id_b])
    src = m.get(track_id_a)
    dst = m.get(track_id_b)
    if src is None or dst is None:
        raise ValueError("track not found")
    res = score_transition(src, dst, energy_intent=energy_intent)
    return {
        "from_track_id": track_id_a,
        "to_track_id": track_id_b,
        "from_key": src.musical_key,
        "to_key": dst.musical_key,
        "from_camelot": src.camelot,
        "to_camelot": dst.camelot,
        "score": res["transition_score"],
        "transition_score": res["transition_score"],
        "components": res["components"],
        "reasons": res["reasons"],
        "warnings": res["warnings"],
        "missing_components": res["missing_components"],
        "from_bpm": src.tempo_bpm,
        "to_bpm": dst.tempo_bpm,
    }
