# M4C — Soundcharts Production Audio Feature Ingestion + Frontend Verification

**Status:** COMPLETE  
**Decision:** Soundcharts primary high-coverage enrichment verified live; fallback intact, frontend displays real audio features, idempotent.

---

## Baseline
- Backend tests: 183 passed before changes (182 baseline + updated preference)
- Frontend typecheck: PASS
- Frontend build: PASS

## Soundcharts Live Coverage (small batch `--limit 25`)
- Queried: 25
- Matched: 25
- No_match: 0
- Errors: 0
- Deferred: 0
- Median latency: ~600ms (per probe: 555ms for 10; batch similar)

### Physical probe reference (10-track sample)
- `soundcharts-probe --limit 10` after parsing fix:
  - queried 10, matched 10, bpm_present 9, key_present 9, both 9, errors 0

## Fields Available

**Endpoint:** `GET /api/v2.25/song/by-isrc/{isrc}` → `Authorization: Bearer <token>`  
**Response shape:** `{"type":"song","object":{"uuid","audio":{...}},"errors":[]}` ; `audio` contains:

| Raw field | AION attribute | Example |
|---|---|---|
| audio.tempo | tempo_bpm | 126.82 |
| audio.key + audio.mode | musical_key (canonical `Tonic mode`, e.g. `6,0 → F# minor`) | F# minor |
| audio.timeSignature | time_signature | 4 |
| audio.energy | energy | 0.68 |
| audio.danceability | danceability | 0.69 |
| audio.valence | valence | 0.97 |
| audio.acousticness | acousticness | 0.19 |
| audio.instrumentalness | instrumentalness | 0.0 |
| audio.liveness | liveness | 0.07 |
| audio.loudness | loudness_db | -6.4 |
| audio.speechiness | speechiness | 0.03 |

All 11 fields documented as present on `by-isrc` response for current plan (no second request needed). Verified on 3 live ISRCs: `USMO16582593`, `USUM71119189`, `GBCVZ1403597`.

If absent on some tracks (instrumentalness often 0), persistence skips null gracefully.

## Normalization

- `tempo_bpm`: float, 0-300, round 3 decimals
- `musical_key`: `key` 0-11 + `mode` 0=minor/1=major → `C ... B major/minor` via `PITCH_CLASSES`; raw key/mode preserved in `match_evidence`
- `time_signature`: int 1-32
- `energy/danceability/valence/acousticness/instrumentalness/liveness/speechiness`: unit float 0-1 round 4
- `loudness_db`: float -100..20 round 2
- Camelot not implemented (M5)

Encoders in `app/enrichment/persistence.py:_ATTRIBUTE_ENCODERS`.

## Persistence

- Model: `TrackAttribute` (`attribute_type`, `value_json`, `source_type=catalog_api`, `source_name=soundcharts`, `analysis_version=m4c-soundcharts-v1`, `confidence=null`, `is_current` via preference)
- Idempotency key: `(track_id, attribute_type, source_name, analysis_version)` — update in place
- Inserted 11 rows per matched track (tempo_bpm + musical_key + time_signature + 8 audio features)
- Batch `25` inserted `275` rows (11×25), `0` skipped initially; `already_enriched` checks any attribute type for that source/version
- Coexistence: GetSongBPM rows (`m4b-getsongbpm-v1`) coexist; same `attribute_type` with different `source_name` stored separately

## Preferred Source Logic

`app/library/__init__.py:PREFERRED_MUSIC_SOURCES = ("soundcharts","getsongbpm", ...)` (M4C flip)

`musical_attributes_for` picks first matching `source_name` in that order; fallback to newest `observed_at` if no preferred source. Returns dict for all 11 attribute types (each `value/source/...` or `None`).

Example: track with both sources:
- preferred `tempo_bpm` → soundcharts 140.03
- history retains getsongbpm 127.0 as non-current

## GetSongBPM Fallback

Verified: track with only `getsongbpm` tempo returns `source:getsongbpm` correctly. Library fallback logic tested in `test_musical_attributes_fallback_to_getsongbpm_when_soundcharts_missing`.

## Coverage Metrics

Fixed semantics in `EnrichmentAggregate.as_dict` and `cli enrich-library` summary:

- `overall_bpm_coverage = bpm_present / queried`
- `matched_bpm_coverage = bpm_present / matched` (legacy `bpm_coverage` kept)
- Same for key, plus per-audio-field `overall_*_coverage` / `matched_*_coverage` and extended `_present` counts

Example from 25-track batch:
- queried 25, matched 25, bpm_present 25 → overall 1.0, matched 1.0
- Previous GetSongBPM example (queried 10, matched 4, bpm_present 4) → overall 0.40, matched 1.0 (was incorrectly reported as 1.0 overall)

## API Changes

- `GET /tracks` / `GET /tracks/{id}` now expose `musical_attributes.{tempo_bpm, musical_key, time_signature, energy, danceability, valence, acousticness, instrumentalness, liveness, loudness_db, speechiness}` each as `{"value","source","confidence","analysis_version","observed_at"}` or null
- No raw provider payload leaked
- Filtering: existing `bpm_min/max`, `musical_key` unchanged; energy filters reserved for future (backend generic via `TrackAttribute` join)
- History `musical_attribute_history` unchanged (provenance for all sources)

## Frontend Changes

- `apps/web/app/lib/api.ts`: extend `TrackItem.musical_attributes` + `TrackDetailResponse.musical_attributes` to 11 fields; add `formatUnit`, `formatLoudness`, `formatTimeSignature`
- `apps/web/app/page.tsx`: table header/row add **Energy** column (now 9-col grid), keep BPM/KEY/Source lightweight; drawer `MUSICAL ANALYSIS` regrouped:
  - **MUSICAL**: BPM, Key, Time Signature
  - **CHARACTER**: Energy, Danceability, Valence
  - **TEXTURE**: Acousticness, Instrumentalness, Liveness, Speechiness, Loudness
  - Source + confidence footer; missing → `—`
- Attribution footer unchanged (`https://getsongbpm.com`); separate Soundcharts attribution not required by provider

## Idempotency

- First `enrich-library --source soundcharts --limit 25`: `inserted 11×25, skipped 0, queried 25`
- Second identical run (no `--force`): `skipped_already_enriched 25, to_query 0, queried 0, inserted 0` — **PASS**
- Third with `--force` would update 11×25 in place (via `updated` count)

Verified live on DB `data/aion.db` with 3186 tracks.

## Known Limitations

- TimeSignature stored as integer numerator (denominator assumed 4); raw `timeSignature` 3/5 etc preserved
- Loudness is source dB, not normalized
- Energy filters not yet exposed in UI (backend supports via additional query if added)
- Camelot / harmonic compatibility not in scope (M5)
- Soundcharts search fallback (`/api/v2/song/search/{term}`) confirms catalog but not used for ISRC path

## Tests

- Backend: 192 passed (was 183; +9 M4C regressions)
  - wrapped `object.audio` payload, key/mode `6,0→F# minor`, optional fields missing, persistence of 11 attributes, coexistence, preferred selection, fallback, overall vs matched coverage, idempotent rerun, API preferred values
- Frontend: `npm run typecheck` PASS, `npm run build` PASS

## Recommendation

**M4C COMPLETE** — Soundcharts is now primary enrichment with high coverage (25/25, 1.0 overall), GetSongBPM fallback intact, coverage metrics corrected, API/frontend display real audio features, idempotent.

Next: M5 Camelot + harmonic compatibility (only if desired).

