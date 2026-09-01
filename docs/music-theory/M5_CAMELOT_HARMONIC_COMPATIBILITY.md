# M5 — Camelot + Harmonic Compatibility

**Status:** COMPLETE  
**Decision:** Derive at read time (simplest, preserves provenance, idempotent). No persisted `camelot` rows.

---

## Canonical Key Model
Provider-independent `CanonicalKey { tonic, mode, display }`.
- Tonics: `C C# D D# E F F# G G# A A# B` (12 pitch classes, sharps canonical)
- Modes: `major | minor` only; tonic-only without mode treated as undetermined (no Camelot)
- JSON shape from `TrackAttribute musical_key`: `{"tonic":"G#","mode":"minor","display":"G# minor"}` → normalized.
- Helpers: `app/music_theory/keys.py:normalize_key`, `PITCH_CLASSES`, `ENHARMONIC_MAP`.

## Enharmonic Policy
All flats canonicalized to sharps **once**, documented, single source:
`Db→C#, Eb→D#, Gb→F#, Ab→G#, Bb→A#, Cb→B, Fb→E`. Original provider value (`Sasi` raw `key_of` etc.) kept in `match_evidence` but never exposed as primary display. Same policy used in `app/enrichment/persistence.py::_encode_key` and `app/music_theory/keys.py`.

## Camelot Mapping
Single canonical mapping module `app/music_theory/camelot.py:_CANONICAL_TO_CAMELOT` (24 entries). Examples per spec:

- C major → 8B, A minor → 8A, G major → 9B, E minor → 9A, D major → 10B, B minor → 10A

Full 24:

1A G# minor / 1B B major
2A D# minor / 2B F# major
3A A# minor / 3B C# major
4A F minor / 4B G# major
5A C minor / 5B D# major
6A G minor / 6B A# major
7A D minor / 7B F major
8A A minor / 8B C major
9A E minor / 9B G major
10A B minor / 10B D major
11A F# minor / 11B A major
12A C# minor / 12B E major

Exposed as `CamelotKey { number:1-12, letter:A|B, code, open_key }`. Open Key derived as `A→m, B→d` (e.g. 8A→8m, 8B→8d) for optional readability.

## Compatibility Rules
`app/music_theory/compatibility.py:compatibility()` deterministic:

| Relationship | Condition | Score |
|---|---|---|
| `same_key` | same code (8A→8A) | 100 |
| `relative_major_minor` | same number, opposite letter (8A↔8B) | 95 |
| `adjacent_camelot` | same letter, number ±1 wrap (8A↔7A,8A↔9A) | 90 |
| `diagonal` | number ±1 + letter flip (8A↔9B) | 70 |
| `incompatible` | otherwise | 0 |

Scores centralized in `SCORES` dict, not scattered. Documented in module header.

## Compatibility Score
0–100 deterministic, not probabilistic. Returns `{score, relationship, from, to}`. Example:

```json
{"score":95,"relationship":"relative_major_minor","from":"8A","to":"8B"}
```

Pair helpers: `compatibility(codeA, codeB)` and `compatibility_for_keys("C major","A minor")`.

## BPM Half/Double Helper
`is_half_or_double_bpm(a,b, tolerance=0.06)` returns `"half"` if `a ≈ 0.5*b`, `"double"` if `a ≈ 2*b`, else `None`. Relative tolerance 6% (absolute scaled). Examples verified: 70↔140, 75↔150, 87↔174, and negatives 120↔121 none, 100↔100 none.

## API
- **Derived attribute** (not persisted): `musical_attributes.camelot` added to `GET /tracks` and `GET /tracks/{id}` via `musical_attributes_for()` derivation:

```json
"camelot": {"value":"1A","source":"aion_music_theory","analysis_version":"m5-camelot-v1","derived_from":"musical_key","number":1,"letter":"A","open_key":"1m"}
```

`source_type=derived` semantics via `source=aion_music_theory`.

- **Persist or derive decision:** **Derive at read time** — simplest, preserves provenance/versioning, naturally idempotent, no migration, no duplicate rows. Alternative (persist derived `TrackAttribute camelot`) would duplicate derived data and require backfill; rejected.

- **Library table:** Camelot column added (table grid now 10 cols, Camelot after Key, monospace amber 1A style).

- **Camelot filter:** `GET /tracks?camelot=8A` maps back to canonical display via `camelot_to_canonical` then filters `TrackAttribute musical_key LIKE`.

- **Compatibility endpoints:**
  - `GET /tracks/{track_id}/compatibility/{other_track_id}` → `{from_track_id,to_track_id,from_key,to_key,from_camelot,to_camelot,score,relationship,from_bpm,to_bpm,bpm_relationship}`
  - `GET /tracks/{track_id}/compatible?limit=10` → `{track_id, compatible:[...]}` sorted by score desc, filtered to `score>0`, capped pool 500 for performance.

## Frontend
- `app/lib/api.ts` extended `TrackItem.musical_attributes.camelot`, `TracksQuery.camelot`, `buildTracksQuery` camelot param, `TracksResponse.camelot`, `CompatibilityResponse` + fetchers.
- `app/page.tsx` state `camelot`, controls input `Camelot e.g. 8A`, table column `Camelot`, drawer `MUSICAL` group adds `Camelot` row with secondary text `"Harmonic mixing key"`, time signature retained; missing key → `—`.
- Existing BPM/Key/Energy/Source preserved.

## Live Examples

**5 enriched tracks (Soundcharts → derived Camelot):**
- Track 5 (B minor) → 10A (10m)
- Track 3185 (G# minor) → 1A (1m)
- Track 3186 (C# minor) → 12A (12m)
- Track 1 (G major) → 9B (9d)
- Track 2 (F major) → 7B (7d)

**3 pair comparisons (live):**
- `5 (10A B minor) ↔ 9 (10A B minor)` → `same_key 100`
- `5 (10A) ↔ 4 (10B D major)` → `relative_major_minor 95`
- `5 (10A) ↔ 19 (11A F# minor)` → `adjacent_camelot 90`
- `5 (10A) ↔ 3185 (1A G# minor)` → `incompatible 0`
- Compatibility API `3185/5` returns `score 0 incompatible` with BPM half/double `null` correctly.

Camelot filter `?camelot=10A` returns only B minor tracks (verified).

## Tests
- Backend 263 passed (was 192, +71 M5)
  - 24 canonical keys, 24 camelot roundtrips, enharmonics, major/minor distinction, malformed/null, 4 compatibility bands + diagonal, incompatible, half/double (6 cases), derived provenance, missing key, API camelot exposure
- Frontend typecheck PASS, build PASS (6.28kB route)

## Known Limitations
- Tonic-only keys (e.g. "C" without mode) cannot map to Camelot (returns null → `—`)
- Open Key simplified to `number + m/d`; full Open Key spec (different numbering) not implemented
- Energy boost/drop merged into `adjacent_camelot` (score 90) rather than separate 85 bands; diagonal 70 captures mixed moves
- Compatible list scoring uses harmonic only (no BPM/energy/mood weighting) per M5 scope

## Next Milestone
M6 — Mood/Vibe + Musical Character Inference (only after M5 COMPLETE)
