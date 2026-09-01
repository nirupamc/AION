"""Library analytics service — provider-independent."""
from __future__ import annotations
import json
from typing import Any, Optional
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import Track, ProviderTrack, TrackAttribute, TrackIdentifier
from app.library import ListParams, musical_attributes_for, music_character_for, _filter_tracks_by_music, _apply_filters
from .aggregation import avg, median, min_max, dominant_range_bpm, distribution_counts
from .distributions import bpm_histogram, energy_histogram

def _filtered_provider_tracks_query(session: Session, params: ListParams):
    base = select(ProviderTrack)
    filtered = _apply_filters(base, params=params)
    filtered = _filter_tracks_by_music(filtered, bpm_min=params.bpm_min, bpm_max=params.bpm_max, musical_key=params.musical_key, camelot=params.camelot)
    # mood/vibe filters are derived, need Python post-filter if set
    mood = (params.mood or "").strip().lower() if params.mood else None
    vibe = (params.vibe or "").strip().lower() if params.vibe else None
    if mood or vibe:
        # fetch candidates
        rows = session.execute(filtered).scalars().all()
        # compute characters
        tids = list({pt.track_id for pt in rows})
        if not tids:
            return []
        from app.library import musical_attributes_for, music_character_for
        music_map = musical_attributes_for(session, tids)
        char_map = {}
        for tid in tids:
            from app.library import _music_character_for_attrs
            char_map[tid] = _music_character_for_attrs(music_map.get(tid, {}))
        filtered_rows=[]
        for pt in rows:
            char = char_map.get(pt.track_id)
            if not char:
                continue
            if mood:
                moods=[m["label"].lower() for m in char.get("moods",[])]
                if mood not in moods and (char.get("dominant_mood") or "").lower() != mood:
                    continue
            if vibe:
                vibes=[v["label"].lower() for v in char.get("vibes",[])]
                if vibe not in vibes and (char.get("dominant_vibe") or "").lower() != vibe:
                    continue
            filtered_rows.append(pt)
        return filtered_rows
    else:
        return session.execute(filtered).scalars().all()

def get_library_dna(session: Session, params: ListParams) -> dict[str, Any]:
    # total tracks overall or filtered?
    # For analytics scope, total_tracks is overall library, enriched_tracks is filtered subset that has attributes
    # But if filters are active, we also filter total to filtered subset? Spec: GET /library/dna?mood=dark should summarize that subset.
    # So we compute filtered ProviderTracks then distinct tracks.

    filtered_rows = _filtered_provider_tracks_query(session, params)
    # distinct tracks in filtered set
    filtered_track_ids = list({pt.track_id for pt in filtered_rows})
    total_tracks_filtered = len(filtered_track_ids)
    # overall library totals (unfiltered) for coverage context
    total_tracks_all = session.scalar(select(func.count(Track.id))) or 0

    if not filtered_track_ids:
        return {
            "total_tracks": total_tracks_all,
            "filtered_tracks": 0,
            "enriched_tracks": 0,
            "enrichment_percentage": 0,
            "tempo": {"average": None, "median": None, "min": None, "max": None, "dominant_range": None},
            "energy": {"average": None, "median": None},
            "danceability": {"average": None},
            "valence": {"average": None},
            "top_keys": [],
            "top_camelots": [],
            "top_moods": [],
            "top_vibes": [],
            "set_roles": [],
            "camelot_distribution": [],
            "mood_distribution": [],
            "vibe_distribution": [],
            "enriched_sample_size": 0,
        }

    # enriched: those with any musical attribute
    enriched_ids = session.execute(select(TrackAttribute.track_id).where(TrackAttribute.track_id.in_(filtered_track_ids)).distinct()).scalars().all() if filtered_track_ids else []
    # But we want only tracks that have musical attributes via _MUSIC_ATTRIBUTE_TYPES? Use any attribute
    # For accuracy, count those with tempo_bpm
    enriched_count = len(set(enriched_ids))
    # Actually better count distinct that have any of the 11 types
    # We'll count those with tempo_bpm as proxy for enrichment
    enriched_bpm_ids = session.execute(select(TrackAttribute.track_id).where(TrackAttribute.track_id.in_(filtered_track_ids), TrackAttribute.attribute_type=="tempo_bpm").distinct()).scalars().all()
    enriched_bpm_count = len(enriched_bpm_ids)

    # Gather musical attributes for enriched
    music_map = musical_attributes_for(session, filtered_track_ids)
    char_map = {tid: __import__("app.library", fromlist=["_music_character_for_attrs"])._music_character_for_attrs(attrs) for tid, attrs in music_map.items()}

    bpms=[]
    energies=[]
    danceabilities=[]
    valences=[]
    keys=[]
    camelots=[]
    moods=[]
    vibes=[]
    set_roles=[]
    for tid in filtered_track_ids:
        attrs = music_map.get(tid, {})
        if attrs.get("tempo_bpm") and attrs["tempo_bpm"].get("value") is not None:
            try:
                bpms.append(float(attrs["tempo_bpm"]["value"]))
            except: pass
        if attrs.get("energy") and attrs["energy"].get("value") is not None:
            try: energies.append(float(attrs["energy"]["value"]))
            except: pass
        if attrs.get("danceability") and attrs["danceability"].get("value") is not None:
            try: danceabilities.append(float(attrs["danceability"]["value"]))
            except: pass
        if attrs.get("valence") and attrs["valence"].get("value") is not None:
            try: valences.append(float(attrs["valence"]["value"]))
            except: pass
        if attrs.get("musical_key") and attrs["musical_key"].get("value"):
            v = attrs["musical_key"]["value"]
            if isinstance(v, dict):
                disp = v.get("display")
                if disp: keys.append(disp)
            elif isinstance(v, str):
                keys.append(v)
        if attrs.get("camelot") and attrs["camelot"].get("value"):
            camelots.append(attrs["camelot"]["value"])
        char = char_map.get(tid)
        if char:
            if char.get("dominant_mood"):
                moods.append(char["dominant_mood"])
            if char.get("dominant_vibe"):
                vibes.append(char["dominant_vibe"])
            if char.get("set_role"):
                set_roles.append(char["set_role"])

    tempo_stats = {}
    if bpms:
        mn,mx = min_max(bpms)
        tempo_stats = {"average": avg(bpms), "median": median(bpms), "min": mn, "max": mx, "dominant_range": dominant_range_bpm(bpms)}
    else:
        tempo_stats = {"average": None, "median": None, "min": None, "max": None, "dominant_range": None}

    def avg_or_none(vals):
        return round(sum(vals)/len(vals),3) if vals else None

    return {
        "total_tracks": total_tracks_all,
        "filtered_tracks": total_tracks_filtered,
        "enriched_tracks": enriched_bpm_count,
        "enrichment_percentage": round(enriched_bpm_count / total_tracks_filtered * 100,1) if total_tracks_filtered else 0,
        "enriched_sample_size": enriched_bpm_count,
        "tempo": tempo_stats,
        "energy": {"average": avg(energies), "median": median(energies)},
        "danceability": {"average": avg(danceabilities)},
        "valence": {"average": avg(valences)},
        "top_keys": distribution_counts(keys)[:5],
        "top_camelots": distribution_counts(camelots)[:5],
        "camelot_distribution": distribution_counts(camelots),
        "top_moods": distribution_counts(moods)[:5],
        "top_vibes": distribution_counts(vibes)[:5],
        "mood_distribution": distribution_counts(moods),
        "vibe_distribution": distribution_counts(vibes),
        "set_roles": distribution_counts(set_roles),
    }

def get_bpm_distribution(session: Session, params: ListParams) -> dict[str, Any]:
    filtered_rows = _filtered_provider_tracks_query(session, params)
    track_ids = list({pt.track_id for pt in filtered_rows})
    if not track_ids:
        return {"buckets": []}
    music_map = musical_attributes_for(session, track_ids)
    bpms=[]
    for attrs in music_map.values():
        if attrs.get("tempo_bpm") and attrs["tempo_bpm"].get("value") is not None:
            try: bpms.append(float(attrs["tempo_bpm"]["value"]))
            except: pass
    return {"buckets": bpm_histogram(bpms, 5)}

def get_energy_distribution(session: Session, params: ListParams) -> dict[str, Any]:
    filtered_rows = _filtered_provider_tracks_query(session, params)
    track_ids = list({pt.track_id for pt in filtered_rows})
    if not track_ids:
        return {"buckets": []}
    music_map = musical_attributes_for(session, track_ids)
    energies=[]
    for attrs in music_map.values():
        if attrs.get("energy") and attrs["energy"].get("value") is not None:
            try: energies.append(float(attrs["energy"]["value"]))
            except: pass
    return {"buckets": energy_histogram(energies, 0.1)}

def get_scatter_data(session: Session, params: ListParams, limit: int = 500) -> dict[str, Any]:
    filtered_rows = _filtered_provider_tracks_query(session, params)
    # dedupe tracks
    seen=set()
    uniq=[]
    for pt in filtered_rows:
        if pt.track_id not in seen:
            seen.add(pt.track_id)
            uniq.append(pt)
    # cap
    if len(uniq) > limit:
        # deterministic sampling: sort by track_id
        uniq = sorted(uniq, key=lambda p: p.track_id)[:limit]
    tids=[pt.track_id for pt in uniq]
    music_map = musical_attributes_for(session, tids)
    char_map = {tid: __import__("app.library", fromlist=["_music_character_for_attrs"])._music_character_for_attrs(attrs) for tid, attrs in music_map.items()}
    points=[]
    for pt in uniq:
        attrs=music_map.get(pt.track_id,{})
        bpm=None
        if attrs.get("tempo_bpm") and attrs["tempo_bpm"].get("value") is not None:
            try: bpm=float(attrs["tempo_bpm"]["value"])
            except: bpm=None
        energy=None
        if attrs.get("energy") and attrs["energy"].get("value") is not None:
            try: energy=float(attrs["energy"]["value"])
            except: energy=None
        if bpm is None or energy is None:
            continue
        char=char_map.get(pt.track_id)
        points.append({
            "track_id": pt.track_id,
            "title": pt.raw_title,
            "artist": pt.artist_display,
            "bpm": bpm,
            "energy": energy,
            "key": (attrs.get("musical_key") or {}).get("value",{}).get("display") if isinstance((attrs.get("musical_key") or {}).get("value"), dict) else (attrs.get("musical_key") or {}).get("value"),
            "camelot": (attrs.get("camelot") or {}).get("value"),
            "mood": char.get("dominant_mood") if char else None,
            "vibe": char.get("dominant_vibe") if char else None,
            "set_role": char.get("set_role") if char else None,
        })
    return {"points": points, "count": len(points)}
