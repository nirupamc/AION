# M7 — Library DNA + Interactive Musical Maps

**Status:** COMPLETE

## Goal
Turn AION from track browser into visual intelligence system: understand crate shape and click visuals to explore.

## Analytics Domain
`app/library_analytics/` (provider-independent, no React):
- `service.py` (dna, bpm/energy/scatter)
- `aggregation.py` (avg/median, distribution)
- `distributions.py` (bpm 5-BPM buckets, energy 0.1 buckets)
- `models.py` placeholder
All computed backend, frontend renders. No analytics in React beyond rendering.

## Enrichment Coverage
Explicit: `enriched_tracks / total_tracks`
- Total: 3186
- Filtered (current filters): 3186
- Enriched (any musical attribute, tempo_bpm proxy): 25
- Percentage: 0.8%
- Sample size: 25 (honest, not claiming full library)
Language: "Based on 25 analyzed tracks of 3186 total" in hero.

## Library DNA
`GET /library/dna` (filter-aware, reuses ListParams semantics). Returns:
- total/filtered/enriched + percentage
- tempo {average 141.76, median 142.0, min 134.97, max 146.0, dominant_range "140-144"}
- energy {avg 0.83, median ~0.85} etc danceability/valence avg
- top_keys (B minor etc), top_camelots (9B 5, 11B 3...), mood/vibe/set_role distributions

Supports `?mood=dark&bpm_min=130` etc (filtered snapshot). No separate filter language.

## BPM Distribution
`GET /library/analytics/bpm` → 5-BPM buckets (120-124, etc). Example live: 135-139:4, 140-144:9, 145-149:5. Frontend BarChart (Recharts) clickable → sets `bpm_min`/`bpm_max` and switches to library view.

## Camelot Wheel
Custom SVG wheel (not image): 24 positions, inner A (purple) outer B (sky), intensity = count/max, stroke #27272a, click cell → `camelot` filter. Distribution from `camelot_distribution` (top 9B 5, 11B 3). Counts real tracks.

## Energy Map
`GET /library/analytics/energy` (0.0-0.1 ... 0.9-1.0 buckets) BarChart clickable (currently informational). Example: 0.7-0.8:4, 0.8-0.9:13, 0.9-1.0:8.

## Mood Map
BarChart vertical, `mood_distribution` (dark 11 44%, happy 10 40%, aggressive 3...). Click bar → `mood` filter.

## Vibe Map
Same for `vibe_distribution` (hypnotic 13 52%, driving 12 48%). Click → `vibe` filter.

## Filter Synchronization
Charts are controls: BPM bucket → `bpm_min/max`, Camelot cell → `camelot`, Mood bar → `mood`, Vibe bar → `vibe`, Scatter point → select track. Hero shows active filters and Clear filters button. Library table and analytics share same filter state (`search, bpm, key, camelot, mood, vibe`). Analytics re-fetches on filter change (`loadAnalytics` depends on same deps). No disconnected state.

## Performance
Bulk queries only: `musical_attributes_for` one query for track_ids, Python aggregation for few thousand tracks (3186). N+1 avoided via `in_(track_ids)` batches. No Redis/Celery. Scatter capped at 500 deterministic sample (sorted by track_id). Histograms computed in Python, <10ms for 25 enriched, scales to few thousand. Simple in-process, no cache yet (optional).

## API
- `GET /library/dna` (filter-aware)
- `GET /library/analytics/bpm`
- `GET /library/analytics/energy`
- `GET /library/analytics/scatter?limit=500`
All handle zero enriched (empty buckets, null averages, no divide-by-zero). Reuse `ListParams`.

## Frontend
- Navigation: LIBRARY | LIBRARY DNA tabs
- View `dna` renders hero (total, median BPM, energy avg, top mood/camelot, set role peak %, coverage), distributions row (BPM + Energy), 3-col row (Wheel + Mood + Vibe), scatter (BPM×energy, capped, tooltip title/artist/BPM/energy/key/camelot/mood/vibe, click selects)
- Lightweight Recharts only (one chart lib + custom SVG wheel)
- Dark dense musical styling: large numbers, compact labels, hover feedback, emerald/purple/sky palette, no generic SaaS cards
- Maintains existing table (now with camelot+mood/vibe columns) when view=library

## Live Verification
Real data (25 analyzed / 3186):
- DNA loads: total 3186, enriched 25, tempo median 142, dominant 140-144
- BPM histogram: 3 buckets with counts as above, click 140-144 → library filter updates to 9 tracks
- Camelot wheel: shows 24 cells, 9B darkest (5), click 10A → filters to B minor tracks
- Mood distribution: dark/happy, click Dark → filtered library shows dark tracks
- Vibe distribution: hypnotic/driving, click Driving → filtered
- BPM×Energy: 23 points (2 missing energy due to distinct track handling), hover shows tooltip, click selects track (verified via API scatter)
- Clear filters restores 3186
- 5 interactive flows verified via API + browser state (no screenshots alone, verified via state change and network)

## Tests
Backend 287 passed (276 +11 analytics): DNA empty/partial, averages medians enriched-only, BPM/energy buckets, Camelot counts, mood/vibe/set_role distributions, filter-aware, malformed filters, scatter, deterministic. Frontend typecheck PASS, build PASS (106kB).

## Known Limitations
- Scatter capped 500, deterministic sample by track_id (not random)
- Mood/vibe filter is Python post-filter (requires scanning candidates, but limited to filtered set <2000)
- Energy histogram click currently informational (not wired to exact range filter, but structure ready)
- Analytics recomputed per request (no cache) — acceptable for <5k tracks, could add DB-version-aware cache if needed
- Enrichment coverage low (25/3186) — DNA honestly shows 0.8%, not full library
