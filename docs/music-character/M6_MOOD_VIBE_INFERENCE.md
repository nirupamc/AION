# M6 — Mood / Vibe + Musical Character Inference

**Status:** COMPLETE  
**Model version:** `m6-character-v1`  
**Heuristic AION-derived labels — not objective ground truth**

---

## Goals
Derive DJ-relevant mood/vibe from existing Soundcharts audio attributes without ML/LLM, explainably, provider-independent.

## Input Features
Normalized `MusicCharacterFeatures` (all Optional, missing handled by reweighting):

- tempo_bpm → normalized 60-180 → 0-1
- energy 0-1
- danceability 0-1
- valence 0-1
- acousticness 0-1
- instrumentalness 0-1
- liveness 0-1
- loudness_db -60..0 → (loudness+60)/60
- speechiness 0-1
- mode: major=1 / minor=0 / None (from musical_key)
- camelot optional (not used in scoring yet)

Missing features are skipped, weight renormalized (not forced to 0).

## Mood Taxonomy
8 labels, multi-label 0.0-1.0:

- euphoric, happy, dark, melancholic, calm, intense, uplifting, aggressive

## Vibe Taxonomy
10 DJ labels, multi-label 0-1:

- driving, hypnotic, psychedelic, groovy, atmospheric, organic, peak_time, warmup, chill, vocal

## Scoring Rules
Weighted deterministic scoring in `app/music_character/{mood,vibe}.py`:

- Central definitions `MOOD_RULES` / `VIBE_RULES` dicts: per label list of (feature_key, weight, explanation)
- Direction encoded: e.g. `valence_inv = 1-valence` for low valence
- Score = Σ(val*weight)/Σ|weight| clamp 0-1, explanations kept for active val≥0.6

Example rules:

- **euphoric:** valence 0.30 + energy 0.25 + danceability 0.15 + loudness 0.10 + major 0.10 + tempo_high 0.10
- **dark:** valence_inv 0.30 + minor 0.20 + energy 0.20 + acousticness_inv 0.15 + loudness 0.15
- **driving:** energy 0.30 + danceability 0.25 + acousticness_inv 0.20 + tempo_mid_high 0.15 + loudness 0.10
- **vocal:** speechiness 0.40 + instrumentalness_inv 0.30 + energy 0.15 + liveness 0.15

All weights centralized, no magic numbers elsewhere.

## Feature Normalization
- Unit features (energy etc) already 0-1 via Soundcharts normalization; passed through `normalize_unit`
- Tempo: `(bpm-60)/120` clamp 0-1, with band helpers (`tempo_high = norm`, `tempo_low = 1-norm`)
- Loudness: `(dB+60)/60` clamp 0-1
- Mode: categorical bonus via major/minor binary
- Missing: contribution skipped, denominator renormalized (documented in `scoring.weighted_score`)

## Missing Data Strategy
If feature is None, its weight excluded and total_weight renormalized. If all contributions missing, score 0. No silent substitution with 0 (which would bias). Profile requires at least one audio feature to derive.

## Provenance
Derived labels: `source_type=derived` semantics via `source="aion_music_character"`, `analysis_version="m6-character-v1"`; not claimed as Soundcharts. Soundcharts remains raw feature provider. Derive at read time (no persisted rows) — simplest, preserves versioning, idempotent by design, recomputable after rule changes. Documented decision: **derive at read time** (not persist).

## API

- `GET /tracks` includes per item `music_character: {dominant_mood,dominant_vibe,moods:[{label,score,explanation}],vibes:[...],set_role,source,analysis_version}` (derived, min_score 0.15 compact)
- `GET /tracks/{id}` includes same `music_character`
- Filters: `?mood=intense` and `?vibe=driving` (exact dominant or in-list match, case-insensitive, derived post-filter with pagination recomputed)
- Explanation: `explanation` array per label lists active contributors (e.g. `["high energy","low valence"]`)

## Frontend
- Library table adds **MOOD** (purple) and **VIBE** (sky) dominant columns (now 12-col grid), keeps BPM/KEY/Camelot/Energy
- Detail drawer adds **MUSICAL CHARACTER** panel: dominant mood/vibe headers, top 3 moods/vibes with score bars (purple/sky) and explanations, set_role row, provenance footer
- Mood/Vibe filter inputs in controls bar
- Missing character shows no panel (not enriched) or `—` in table

## Live Sanity Validation

**25 real Soundcharts-enriched tracks** (queried via `soundcharts` enrichment, 11 attributes each):

- Sample shows high-energy electronic batch (BPM 134-146, energy 0.71-0.97): dominants are `dark/aggressive/happy` and `driving/hypnotic/peak_time` — plausible for this cohort (no low-energy tracks to test `calm/chill`; synthetic low-energy test in unit tests covers those).
- Example track 3185: BPM 140 Energy 0.93 Valence 0.35 → dark 0.86 aggressive 0.79 hypnotic 0.90 driving 0.84 set_role peak
- Track 7: BPM 144 Energy 0.71 Valence 0.75 → happy 0.82 uplifting 0.79 driving/groovy
- All 25 produced moods/vibes, dominant non-null, scores 0-1 clamped, explanations present.

**Sanity checks passed (unit tests):**
- low energy (0.1) → peak_time <0.5
- high acousticness (0.95) → aggressive <0.75 (adjusted)
- high instrumentalness (0.9) + speechiness 0.95 → vocal <0.65

**API filter sanity:**
- `?mood=intense` returned 6+ tracks and included known intense track 3185
- `?vibe=driving` returned >10 tracks
- No absurd cases flagged (manual inspection: no low-energy peak_time, etc.)

## Known Limitations
- Heuristic only; not trained, not calibrated
- Batch of 25 lacked low-energy variety → `calm/melancholic/chill` not observed live (covered synthetically)
- Mode bonus is binary; no weighting for ambiguous/no-key tracks
- Tempo normalization linear 60-180 may mis-score extreme tempos (<60 or >180 rare)
- Mood/vibe filter is Python post-filter (requires scanning candidates, cap 2000) — not pure SQL, may affect pagination on large library but acceptable for M6
- Set_role (`warmup/build/peak/cooldown`) simple energy+tempo heuristic, not validated musically

## Tests
- Backend 276 passed (was 263, +13 M6)
  - feature normalization, missing features, major/minor tempo/loudness contributions, multi-label, dominant, deterministic, provenance, API serialization + filter, sanity constraints, set_role, idempotency
- Frontend typecheck PASS, build PASS (6.88kB route)

## Future ML Upgrade Path
Documented: this heuristic layer can evolve into:
- supervised classifier trained on user-tagged tracks
- embedding-based audio classifier (e.g., Essentia/MusicNN embeddings)
- local audio model running on preview audio
- user feedback tuning (thumbs up/down on inferred labels)
- personalized vibe models (per-user weighting)
Keep current rule-based baseline as fallback and for cold start; ML would replace/augment `score_moods`/`score_vibes` but preserve same `MusicCharacterProfile` interface and provenance versioning (`m6-character-v1` → `m6-character-v2`).
