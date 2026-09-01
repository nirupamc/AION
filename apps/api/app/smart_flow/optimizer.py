"""Beam search optimizer for M9."""
from __future__ import annotations
from typing import Any, Optional
import time

from .scoring import target_energy_profile, sequence_energy_score, overall_sequence_score
from app.transitions.service import score_transition

def beam_search(
    candidate_features: dict[int, Any],  # track_id -> TransitionTrackFeatures
    start_track_id: Optional[int],
    target_count: int,
    energy_shape: str,
    beam_width: int = 20,
    minimum_transition_score: Optional[int] = None,
    max_repeat_artist: int = 1,
    artist_map: Optional[dict[int, str]] = None,
) -> tuple[list[int], dict[str, Any]]:
    """Deterministic beam search. Returns (best_sequence_track_ids, stats)."""
    if not candidate_features:
        return [], {"depth":0}
    # If start track provided, must be in candidate_features or we add it
    # Ensure start is included
    all_ids = sorted(candidate_features.keys())
    if start_track_id is not None and start_track_id not in candidate_features:
        # If start not enriched, still allow but we need its features - if missing, fail
        return [], {"error": "start track not in candidate pool"}

    # Initial beams
    beams: list[dict[str, Any]] = []
    if start_track_id is not None:
        beams.append({"sequence": [start_track_id], "used": {start_track_id}, "scores": []})
    else:
        # seed with top candidates by energy closeness to target[0]? For determinism, seed with highest energy shape adherence? Simple: start with each candidate as beam starter limited to beam_width
        target_profile = target_energy_profile(energy_shape, target_count)
        target0 = target_profile[0] if target_profile else 0.6
        # score initial by closeness to target0 + maybe high transition not applicable
        scored = []
        for tid in all_ids:
            feat = candidate_features[tid]
            energy = feat.energy if feat.energy is not None else 0.5
            score = 100 - abs(energy - target0)*100
            scored.append((score, tid))
        scored.sort(key=lambda x: (-x[0], x[1]))
        for _, tid in scored[:beam_width]:
            beams.append({"sequence": [tid], "used": {tid}, "scores": []})

    target_profile = target_energy_profile(energy_shape, target_count)

    # Beam expansion
    for depth in range(1, target_count):
        new_beams: list[dict[str, Any]] = []
        for beam in beams:
            seq = beam["sequence"]
            used = beam["used"]
            last_id = seq[-1]
            # generate candidates
            for cid in all_ids:
                if cid in used:
                    continue
                # artist repetition hard constraint
                if artist_map and max_repeat_artist is not None:
                    cand_artist = artist_map.get(cid, "")
                    if cand_artist:
                        count = sum(1 for tid in seq if artist_map.get(tid) == cand_artist)
                        if count >= max_repeat_artist:
                            continue
                # transition score for last -> cid
                from app.transitions.features import load_transition_features  # not needed, we have features
                src_feat = candidate_features[last_id]
                dst_feat = candidate_features[cid]
                res = score_transition(src_feat, dst_feat, energy_intent="maintain")  # for beam, use maintain; final energy shape will adjust overall
                tscore = res["transition_score"]
                if minimum_transition_score is not None and tscore < minimum_transition_score:
                    continue
                # partial sequence score approximation: mean + min so far + energy adherence so far
                new_scores = beam["scores"] + [tscore]
                # compute partial energy error for prefix
                actual_energies = [candidate_features[tid].energy for tid in seq + [cid]]
                # target prefix
                target_prefix = target_profile[:len(actual_energies)]
                # energy score for prefix
                from .scoring import sequence_energy_score
                e_score, _ = sequence_energy_score(actual_energies, target_prefix)
                mean = sum(new_scores)/len(new_scores) if new_scores else 0
                min_s = min(new_scores) if new_scores else 0
                overall = overall_sequence_score(mean, min_s, e_score)
                new_beams.append({
                    "sequence": seq + [cid],
                    "used": used | {cid},
                    "scores": new_scores,
                    "overall": overall,
                    "mean": mean,
                    "min": min_s,
                    "e_score": e_score,
                })
        if not new_beams:
            break
        # Keep top K by overall, tie-break by sequence tuple for determinism
        new_beams.sort(key=lambda b: (-b["overall"], -b["mean"], b["sequence"]))
        beams = new_beams[:beam_width]
        # If we have reached target_count, we can stop early? But continue to fill
        if all(len(b["sequence"]) == target_count for b in beams):
            break

    # Choose best beam (highest overall)
    if not beams:
        return [], {}
    # Among beams, prefer those with length == target_count, else longest
    max_len = max(len(b["sequence"]) for b in beams)
    candidates = [b for b in beams if len(b["sequence"]) == max_len]
    # If no beam reached target, candidates is longest
    candidates.sort(key=lambda b: (-b.get("overall",0), -b.get("mean",0), b["sequence"]))
    best = candidates[0]
    return best["sequence"], {"beams_considered": len(beams), "best_overall": best.get("overall"), "best_mean": best.get("mean"), "best_min": best.get("min")}

def greedy_baseline(candidate_features: dict[int, Any], start_track_id: Optional[int], target_count: int, energy_intent: str = "maintain") -> list[int]:
    if not candidate_features:
        return []
    all_ids = sorted(candidate_features.keys())
    if start_track_id is not None and start_track_id in candidate_features:
        seq = [start_track_id]
        used = {start_track_id}
    else:
        # pick highest energy closeness to target[0] as start
        from .scoring import target_energy_profile
        target_profile = target_energy_profile(energy_intent if energy_intent in ["maintain","build","drop","wave","peak_middle","peak_end"] else "maintain", target_count)
        # Actually greedy uses maintain intent? For baseline, use maintain
        target0 = target_profile[0] if target_profile else 0.6
        best = min(all_ids, key=lambda tid: abs((candidate_features[tid].energy or 0.5) - target0))
        seq=[best]
        used={best}
    while len(seq) < target_count:
        last = seq[-1]
        src = candidate_features[last]
        best_cand = None
        best_score = -1
        for cid in all_ids:
            if cid in used:
                continue
            dst = candidate_features[cid]
            res = score_transition(src, dst, energy_intent=energy_intent)
            if res["transition_score"] > best_score or (res["transition_score"]==best_score and (best_cand is None or cid < best_cand)):
                best_score = res["transition_score"]
                best_cand = cid
        if best_cand is None:
            break
        seq.append(best_cand)
        used.add(best_cand)
    return seq
