# M8 — Transition Intelligence + Best Next Track

**Status:** COMPLETE  
**Weights version:** `v1` (centralized `app/transitions/scoring.py:WEIGHTS`)

## Goal
Rank candidates for next DJ transition deterministically, explainably, provider-independent.

## Feature Inputs
`TransitionTrackFeatures` (from `app/library` musical_attributes + music_character):
- tempo_bpm (float)
- musical_key display, camelot (derived 1A-12B)
- energy, danceability, valence, loudness_db, acousticness, instrumentalness, liveness, speechiness
- dominant_mood / mood_scores (8), dominant_vibe / vibe_scores (10), set_role (warmup/build/peak/cooldown)
Missing → None, reweighted (not fake 0).

## Scoring Model
Overall `transition_score` 0-100 weighted average of available components, renormalized weights.

- **Weights (central):** harmonic 0.30, tempo 0.25, energy 0.20, vibe 0.10, mood 0.10, set_role 0.05 = 1.0
- No scattered magic numbers; all thresholds in `scoring.py`.

## Weights
As above; if component missing, weight omitted and denominator renormalized. Example: if harmonic missing, remaining weights sum 0.70 → divide by 0.70.

## Harmonic Score
Reuses M5 `compatibility(camelotA, camelotB)`:
- same 100, relative 95, adjacent 90, diagonal 70, incompatible 0
Passed through as harmonic component (0-100).

## BPM Score
- 0-2% excellent → 100-96
- 2-4% good → 96-92
- 4-6% usable → 92-70
- 6-15% 70-40
- >15% 40→0
Half/double detected via `is_half_or_double_bpm` → baseline 75/60/40 after normalizing `a` vs `b/2` or `b*2`. Not auto-perfect.

## Energy Intent
`maintain` (ideal 0, score 100-abs(delta)*150), `build` (ideal +0.12, 100-abs(delta-0.12)*120 minus 20 if drop), `drop` (ideal -0.12). Controlled build/drop vs huge jumps.

## Mood Similarity
Cosine similarity of 8-dim mood vectors (missing=0), `score = cos*100` +5 if dominant equal. Example dark/intense continuity high when vectors align.

## Vibe Similarity
Same for 10-dim vibe vectors, same cosine, dominant boost.

## Set Role
Adjacency table `SET_ROLE_ADJACENCY`: warmup→build 90, build→peak 90, peak→cooldown 85, warmup→peak 30 etc. Same role 80, unknown 50.

## Missing Feature Handling
Omit component, renormalize. Report `missing_components:["harmonic"]`. Minimum evidence: require at least `tempo + (harmonic or energy)` to score; otherwise candidate skipped in `get_best_next_tracks`. Prevents scoring from pure mood alone.

## Explanations
Deterministic `reasons` per component:
- Camelot 10A→11A adjacent harmonic move
- BPM 140→142 +1.4% excellent
- energy 0.82→0.87 controlled build
- mood continuity 85/100, vibe continuity etc
`warnings`: large BPM gap, incompatible Camelot, energy jump vs intent, valence shift >0.4, loudness >3dB, danceability shift >0.3.

## Best Next Track
`GET /tracks/{id}/next?limit=10&energy_intent=maintain|build|drop`
- Candidate pool: all enriched tracks with tempo+harmonic/energy (distinct track_id, up to 2000, capped 1000 for scoring)
- Excludes self
- Scores via `score_transition`
- Sorted `transition_score desc, track_id asc` deterministic
- Returns `{source_track:{track_id,title,artist,bpm,camelot,energy,mood,vibe}, energy_intent, recommendations:[{track_id,title,artist,transition_score,components,reasons,warnings,missing_components, bpm,camelot,energy,mood,vibe}]}`

Prefilter optional BPM broad window not yet enforced (could add).

## API
- Pair: `GET /tracks/{a}/transition/{b}?energy_intent=...` → same scorer `{transition_score, components, reasons, warnings, from_key,to_key,from_camelot,to_camelot,from_bpm,to_bpm}`
- Harmonic legacy `GET /tracks/{a}/compatibility/{b}` remains (M5) for pure harmonic.
- Both share scorer via `score_transition` (no duplicate logic).

## Frontend
- Drawer **BEST NEXT TRACK** shows top 5, each with title/artist, BPM·Camelot·energy·mood·vibe, score badge color (90+ emerald, 75+ yellow, 60+ orange, <60 gray), reasons preview.
- Energy intent control: Maintain/Build/Drop buttons re-query.
- Expand → component breakdown grid (harmonic/tempo/energy/mood/vibe/set_role) + warnings/missing.
- Click recommendation → selects that track (find in current list or fetch detail), opens its drawer with its own recommendations (chain).
- Visual language: `91 / 100` with bands 90-100 excellent, 75-89 strong, 60-74 usable, <60 risky.

## Live Sanity Validation
25 analyzed tracks (Soundcharts 25/3211, 0.8% coverage):
- 5 source tracks (Your Skin 10A, Acid Trip 1A, Amonati 12A, Teder Beseder 9B, 3 Hits 7B) each top 5 inspected.
- All recommendations had reasonable tempo (≤6% diff or half/double handled), Camelot adjacent/relative/diagonal, energy trajectory matched intent, mood/vibe continuity 70-100.
- Build intent reordered correctly (e.g., source 5 maintain top 13 Nova Psique, build top 13→21 Corrupted Sound (higher energy), drop top 13→23 Peacock (also high but different), verified distinct order).
- No self-duplicate, no massive BPM mismatch in top ranks (far tracks scored <50).
- Performance: candidate count 24, scoring <50ms, response <200ms (bulk feature load, no N+1, Python scoring over <1000 candidates acceptable).

## Performance
Bulk `load_transition_features` (one `musical_attributes_for` + `music_character_for` query), scoring loop O(N) for N≈25-1000, capped 1000. No vector DB/Redis. Measured ~30-50ms for 24 candidates.

## Tests
Backend 306 passed (287 +19 transition: determinism, harmonic, BPM exact/near/far, half/double, energy maintain/build/drop, mood/vibe cosine, role progression, missing reweighting, minimum evidence, self exclusion, stable ordering, explanations/warnings, pair API, next API limit, malformed intent). Frontend typecheck PASS, build PASS (107kB).

## Known Limitations
- No phrase/beat-grid, intro/outro, cue points, vocal clash detection
- No actual audio overlap analysis
- Simple cosine mood/vibe, not learned embedding
- Set_role weight small (5%), simple adjacency table
- Candidate pool limited to enriched tracks (25 currently); full library not enriched
- No transition graph optimization (M9)
