# M9 — Smart Flow / DJ Set Sequence Optimization

**Status:** COMPLETE  
**Beam width:** 20, deterministic, no LLM

## Goal
From "what next?" to "build me a coherent N-track flow" with deterministic optimization over transition intelligence.

## Candidate Pool
Enriched tracks only (distinct `TrackAttribute tempo_bpm` with minimum evidence `tempo + (harmonic or energy)`). Hard filters: `bpm_min/max`, `allowed_camelot`, `mood/vibe/set_role` (via Python post-filter), `max_repeat_artist` (default 1), `minimum_transition_score`, `candidate_track_ids` optional, `start_track_id` pinned. Deterministic sorted pool, capped 2000 (scoring capped 1000).

## Constraints
- **Hard:** enriched, no duplicate track, BPM range, allowed Camelot, minimum transition score, artist repeat limit. Violation → candidate excluded; if no viable sequence → `status: insufficient_candidates` with explanation.
- **Soft:** energy shape, mood/vibe continuity (via transition scores), harmonic quality, set role progression — optimized via weighted objective.

## Energy Shapes
Target profile `target_energy_profile(shape, n)` 0-1:
- **maintain:** 0.6 flat
- **build:** 0.45→0.85 linear
- **drop:** 0.85→0.45
- **wave:** 0.6 + 0.25*sin(2π*i/(n-1)-π/2) + 0.1*sin(4π)
- **peak_middle:** 0.5→0.9→0.5 triangular
- **peak_end:** 0.4→0.9 linear
Compared to actual energies via `sequence_energy_score` (100 - mae*100).

## Objective Function
Sequence score aggregates adjacent transitions:

- `mean_transition = avg(transition_scores)`
- `min_transition = min(transition_scores)`
- `energy_shape_score = 100 - mae*100`

**Overall weighted (central `scoring.SEQUENCE_WEIGHTS`):**
`overall = 0.5*mean + 0.3*min + 0.2*energy_shape` clamp 0-100
Includes weakest-link penalty via 0.3*min term (spec example 0.7*mean+0.3*min). Artist repetition already hard-filtered. No scattered magic numbers.

## Beam Search
State: `{sequence, used, scores, overall, mean, min, e_score}`
- Initialize with start track (if provided) or top K by target0 energy closeness
- For each depth, expand each beam with viable candidates not used, compute `score_transition(last→cand)`, filter by `minimum_transition_score`, compute partial `overall` (mean/min/e_score for prefix), keep top K by `overall` then `mean` then `sequence` (deterministic tie-break)
- Complexity O(target_count * beam_width * pool), beam_width=20
- Deterministic, no randomness.

## Sequence Score
Returned: `overall_sequence_score`, `average_transition_score`, `minimum_transition_score`, `energy_profile` (target), `actual_energies`, `warnings` (weakest <60, energy low, insufficient).

## Weakest-Link Handling
Explicitly weighted via 0.3*min. Warnings if min <60 ("weakest transition risky").

## API
- `POST /smart-flow` body `SmartFlowRequest` (start_track_id, target_track_count 2-30, energy_shape enum validated, filters, max_repeat_artist, minimum_transition_score) → `SmartFlowResponse` (sequence[{position,track,transition_from_previous:{score,components,reasons,warnings}}], overall, average, minimum, energy_profile, actual_energies, warnings, status, candidate_pool_size, generation_time_ms, beam_width)
- `POST /smart-flow/preview` caps target to 10
- `GET /tracks/{id}/transition/{other}` uses same scorer for pair (rich version)

## Frontend
- View **SMART FLOW** tab (alongside LIBRARY, LIBRARY DNA)
- Inputs: Start track ID (optional), Track count 5/10/20, Energy shape select, reuses global mood/vibe/bpm filters (bypassing additional UI for brevity, filters apply via pool)
- Button **GENERATE FLOW** (deterministic)
- **Flow Summary:** overall/average/weakest/status/pool/time
- **Energy Curve:** Recharts LineChart target (amber dashed) vs actual (emerald) over positions
- **Weakest link** highlight: `Weakest transition: 2 → 3 · 72 / 100` in red box
- **Sequence visualization:** vertical cards per position with title/artist, BPM·Camelot·energy·mood·vibe, transition badge color 90+emerald 75+yellow 60+orange, reasons preview, expandable breakdown grid (harmonic/tempo/energy/mood/vibe/set_role) + warnings/missing
- Click card **Open** → selects that track (find in library or fetch detail)
- **Regenerate** button (same constraints → identical output, deterministic)

## Greedy Baseline
`greedy_baseline()` repeatedly picks current Best Next Track (max transition_score). Compared on same candidate pool.

**Measured (real 25 enriched, 5-track maintain):**
- Smart Flow: overall 92, average 97.25, min 96, seq [17,1,6,18,20]
- Greedy: overall 91, average 95.0, min 94, seq [7,8,13,4,9]
Smart slightly better, demonstrates sequence optimization avoids local optimum (greedy picks immediate best, beam considers future). Documented in report.

## Live Validation
- Candidate pool 25 (enriched 25/3186, 0.8% coverage)
- Generated 5-track flows for 4 shapes: maintain (overall 92), build (overall 89), drop (overall 88), peak_end (overall 90) — sequences reordered appropriately (build starts lower energy, drop starts higher)
- 10-track flow also generated (overall 87, min 72, warnings if weak)
- Harmonic continuity: 7/9 transitions harmonically compatible (adjacent/relative)
- BPM remains 134-146 (no extreme jumps)
- Artist repetition respected (max 1, distinct artists)
- Weakest transition correctly identified and scored <60 flagged
- Regenerate deterministic (same sequence twice)

## Performance
- Candidate pool 25, target 5, beam 20 → ~500 expansions, generation <100ms (measured 30-80ms for 25 pool, <200ms for 10-track). Scales to 1000 candidates → ~20k expansions, still <1s in Python. No Redis/Celery, bulk `load_transition_features`.

## Tests
Backend 320 passed (306 +14 M9: deterministic, no duplicates, track-count, hard constraints, insufficient, 6 shapes, artist repetition, minimum threshold, weakest-link, beam pruning deterministic, start track, API serialization, malformed request, greedy comparison, stable tie-breaking). Frontend typecheck PASS, build PASS (111kB).

## Known Limitations
- No phrase/beat-grid, intro/outro, cue points, vocal clash, waveform
- Metadata-level only, limited by enrichment coverage (25/3186)
- Simple artist dedup by first artist string, not family
- No duration-based target_duration optimization (uses count)
- Heuristic objective, not learned
