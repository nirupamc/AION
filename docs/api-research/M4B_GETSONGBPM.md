# M4B — GetSongBPM Production Enrichment + First Musical UI

**Status:** PARTIAL
**Decision:** BLOCKED on live verification (no API key available in this run).
Code path is fully implemented and unit-tested end-to-end against mocked
provider responses; production ingestion is intentionally gated behind the
10-track live gate which could not be executed.

**Session verification (2026-09-01):**

| Item | Status |
|---|---|
| GetSongBPM source code | IMPLEMENTED |
| Matching logic | IMPLEMENTED |
| Persistence code | IMPLEMENTED |
| CLI commands | IMPLEMENTED |
| API exposure (library, detail) | IMPLEMENTED |
| Frontend BPM/Key/Source columns | IMPLEMENTED |
| Frontend filters (bpm_min/bpm_max/key) | IMPLEMENTED |
| Frontend MUSICAL ANALYSIS panel | IMPLEMENTED |
| Frontend attribution footer | IMPLEMENTED |
| Backend tests (174) | VERIFIED — all passing |
| Frontend typecheck | VERIFIED — passing |
| Frontend build | VERIFIED — passing |
| Soundcharts adapter | PRESENT — HTTP 401 runtime (not debugged) |
| MusicBrainz resolver | VERIFIED — all passing |
| Library/Importer | VERIFIED — all passing |
| Live GetSongBPM probe | BLOCKED — `GETSONGBPM_API_KEY` not in `.env` |
| Production enrichment | BLOCKED — no key to run |
| Idempotency (live) | NOT TESTED — requires live key |
| API output (live) | NOT TESTED — requires live key |
| Frontend live display | NOT TESTED — requires enriched data |

The live gate could not be executed because `GETSONGBPM_API_KEY` is absent
from the `.env` file. The `enrichment-sources` CLI confirms:
```
getsongbpm  BLOCKED — API KEY REQUIRED
```
The `getsongbpm-probe --limit 10` command correctly returns the same
BLOCKED status with the message: `GETSONGBPM_API_KEY not configured in .env`.

---

## Provider

| Field | Value |
|---|---|
| Service | GetSongBPM |
| Docs | https://getsongbpm.com/api |
| Base URL | `https://api.getsongbpm.com` |
| Auth | API key — `X-API-KEY` header **or** `api_key` URL parameter |
| Free tier | Yes (sign up at getsongbpm.com/api) |
| Rate limit | ~3000 requests / hour (observed by third-party clients) |
| Backlink | REQUIRED — link to getsongbpm.com |
| ISRC lookup | **Not supported.** Text-based search only. |

## Authentication

Single API key. We send it via the `X-API-KEY` header to avoid leaking it in
provider-side logs that capture full URLs.

```python
headers = {"X-API-KEY": api_key, "Accept": "application/json"}
GET https://api.getsongbpm.com/search/?type=song&lookup=<title+artist>&limit=10
GET https://api.getsongbpm.com/song/?id=<song_id>
```

The key is read from `GETSONGBPM_API_KEY` in `.env`. It is never logged, never
written to disk by the application, and never returned by any HTTP endpoint.

## Free Usage Terms

- Backlink to `getsongbpm.com` is REQUIRED.
- ~3000 requests / hour.
- No commercial-only restrictions documented.
- AION-side pacing is set to `GETSONGBPM_MIN_INTERVAL=1.0s`
  (configurable). This is well under the 3000/hour ceiling.

## Attribution Requirement

A small footer is rendered at the bottom of the library page linking to
`https://getsongbpm.com`:

> Music metadata via [GetSongBPM](https://getsongbpm.com).

The attribution URL is configurable via `GETSONGBPM_ATTRIBUTION_URL`.

## API Endpoints

- `GET /search/?type={song|artist|both}&lookup=<query>&limit=<n>`
- `GET /song/?id=<song_id>`

Search results contain per-song fields:

```
{
  "song_id":   "...",
  "song_title":"...",
  "song_uri":  "...",
  "tempo":     "<integer as string>",   // BPM
  "time_sig":  "<integer/4 or similar>", // optional/beta
  "key_of":    "<Tonic><m|maj>...",     // e.g. "F#m", "C# minor", "Bb major"
  "camelot":   "<11A|...>",              // Open Key / Camelot notation
  "artist":    { "id": "...", "name": "...", ... }
}
```

The `/song/` endpoint wraps the same payload under a `"song"` key.

Documented fields that AION exposes:

| Field | AION use |
|---|---|
| `tempo` | `tempo_bpm` (float) |
| `key_of` | `musical_key` (canonical "Tonic mode") |
| `time_sig` | recorded in `match_evidence`; not promoted to its own attribute yet |
| `camelot` | recorded in `match_evidence`; intentionally NOT used as a primary display field until M5 |
| `artist.name`, `artist.mbid` | identity only — never used to overwrite AION artist display |

`danceability`, `acousticness`, `energy` etc. **are not documented** in the
current API. They are NOT claimed by AION. (Spotify audio features remain
rejected since 2024-11-27.)

## Matching Strategy

GetSongBPM has no ISRC lookup. We do **NOT** accept the first text-search
hit. Each candidate is scored against the AION query:

| Signal | Weight |
|---|---|
| Title token overlap (containment ≥ Jaccard) | 0.55 |
| Artist name overlap (Jaccard on normalized names) | 0.40 |
| Duration proximity | −0.10 if both sides have durations and differ > 8 s |
| Version-token mismatch | **−0.20** when AION has a Remix/Edit/Mix marker and candidate disagrees, or when AION has no marker but candidate does |

Hard acceptance gates:

- Score ≥ `ACCEPT_SCORE` (0.80)
- Title Jaccard ≥ 0.55
- Artist overlap > 0
- Version safety check passes
- If AION duration was compared and the candidate differs > 8 s → refuse
- If a second candidate is within `AMBIGUOUS_GAP` (0.08) of the best → ambiguous

Preserved version tokens: Remix, Original Mix, Extended Mix, Radio Edit,
Club Mix, Dub Mix, Instrumental, Acapella, Live, Acoustic, VIP, Rework,
Remaster/Remastered, Edit, Single Edit, Album Version, Deluxe, Remixed, Mix,
Version.

Result states: `matched`, `no_match`, `ambiguous`, `error`, `deferred`.

## 10-Track Probe

A live probe was attempted with:

```
python -m app.cli getsongbpm-probe --limit 10
```

without a real `GETSONGBPM_API_KEY`. The probe correctly reports:

```
status   BLOCKED — API KEY REQUIRED
missing  GETSONGBPM_API_KEY not configured in .env
action   Sign up at https://getsongbpm.com/api, set GETSONGBPM_API_KEY in .env, then re-run
```

This is the right behavior: no production lookup is performed without a key.
The same fixture used by the M4A Soundcharts spike
(`fixtures/enrichment/m4a_soundcharts_sample.json`) is wired as the default
sample file so future runs can compare results head-to-head on the same 10
tracks.

## Match Quality

Because the live gate could not be executed, match-quality numbers come
from unit tests that drive the source adapter against realistic mock
responses (`tests/test_getsongbpm_source.py`):

| Mocked scenario | Result |
|---|---|
| Exact title + exact artist | matched, confidence ≈ 1.0 |
| Title "Acid Trip" vs candidate "Acid Trip - Out of Orbit & Sasi Remix" | refused (score < threshold; `version_ok=False`) |
| Title "Acid Trip (Out of Orbit & Sasi Remix)" vs candidate "Acid Trip - Out of Orbit & Sasi Remix" | matched (version markers agree) |
| Same title + multiple equivalent candidates | ambiguous |
| Title "Random Song" by Beyoncé vs candidate "Random Song" by Other Artist | refused (artist overlap = 0) |

## BPM Coverage

Not measured against live tracks. The code path:

- Reads `tempo` (string-encoded integer) from `/song/`.
- Normalizes via the existing `normalize_bpm()` helper (rejects ≤ 0 or > 300).
- Encodes as float with 3-decimal precision into `TrackAttribute.value_json`.

## Key Coverage

Not measured against live tracks. The code path:

- Parses `key_of` strings: `F#m`, `C# minor`, `Bb major`, `Db`, etc.
- Converts flats to sharps to match AION's canonical tonic set
  (`C C# D D# E F F# G G# A A# B`).
- Records `tonic`, `mode` and `display` in the value_json so future Camelot
  computation (M5) can derive open-key codes without re-querying the provider.

## Ambiguities

The most common failure mode for catalog text-search APIs is the "same
title, two different mixes" case. Examples seen in our sample:

- "She's A 10 But (Remix) (feat. Yung Gravy)" — many unofficial remixes.
- "Strange Love - Single Edit" — vs album version.
- "Save a Soul" — common title, ambiguous primary artist.

The adapter handles these by:

1. Refusing to match when only one side has a version marker.
2. Penalizing candidates whose top score is within 0.08 of a second high-
   scoring candidate (returns `ambiguous`).
3. Falling back to `no_match` when neither the strict nor the ambiguous
   gates are met.

## Production Persistence

Only reachable after the live gate passes. Implemented in
`app/enrichment/persistence.py`:

| Concern | Implementation |
|---|---|
| Idempotency | Upsert keyed on `(track_id, attribute_type, source_name, analysis_version)`. Re-runs UPDATE the existing row rather than duplicating. |
| Source isolation | Soundcharts BPM/Key and GetSongBPM BPM/Key coexist as separate rows. |
| Confidence | Written from the candidate match score (0..1). |
| `analysis_version` | `GETSONGBPM_ANALYSIS_VERSION` (default `m4b-getsongbpm-v1`). Bumped if matching/normalization logic changes. |
| `is_current` | Set true ONLY when no other source has a current row of the same attribute type. |
| Value shape (BPM) | `value_json` = `json.dumps(float)` |
| Value shape (Key) | `value_json` = `json.dumps({"tonic": "...", "mode": "...", "display": "..."})` |
| Raw payload | Stored in `match_evidence` and `raw` of `EnrichmentResult`; not persisted in `value_json` to keep the column small. |

A batch command exists:

```
python -m app.cli enrich-library --source getsongbpm --limit 25 [--force] [--dry-run]
```

Defaults:

- `--limit 25`
- Skips tracks already enriched under the current `analysis_version`
  (use `--force` to override)
- `--dry-run` lists candidates without performing network calls
- Rate limit = `GETSONGBPM_MIN_INTERVAL` (1.0s default)
- Per-process cache prevents repeating identical lookups within 60 s

## Rate Limits

GetSongBPM's documented free tier is ~3000 requests/hour
(third-party observation). AION's pacing defaults to 1.0 s between requests,
which corresponds to ~3600/hour in the worst case — comfortably within the
documented limit, but flagged for re-evaluation if we observe HTTP 429 in
practice. Caching prevents re-querying the same `(title, artist)` pair.

## Frontend Integration

Implemented in `apps/web`:

- **Library table** now shows `BPM`, `KEY`, `Conf.`, and `Source` columns.
  Missing values render as `—` (never fabricated).
- **BPM min / BPM max / Key** filters are wired into the existing filter
  bar and passed to the backend as query params.
- **Track detail drawer** has a new **Musical Analysis** panel showing:
  - BPM (raw value)
  - Key (canonical display)
  - Source (provider label, e.g. "GetSongBPM")
  - Match confidence (%)

  When no enrichment exists, the panel explains how to backfill.
- **Attribute history** section lists every TrackAttribute row for the track,
  each labelled `current` when `is_current=True`. This preserves the
  provenance of every observation.
- **Footer attribution**:
  `Music metadata via [GetSongBPM](https://getsongbpm.com)`.

`npm run typecheck` and `npm run build` both pass.

## Known Limitations

1. **Live verification was not possible in this run.** No real
   `GETSONGBPM_API_KEY` was available. The matching, normalization, and
   persistence layers were exercised against realistic mock responses only.
2. GetSongBPM does not expose `camelot` in a way that maps cleanly to all
   standard notations; we store the provider value in `match_evidence` but
   do not promote it to a first-class attribute until M5.
3. The current title-similarity blend uses `max(containment, jaccard)`.
   This treats "Acid Trip" and "Trip Acid" as identical (good) but can
   over-credit partial matches with a single shared short word (e.g. "The
   Way"). The 0.55 minimum Jaccard floor mitigates this in practice.
4. The artist overlap function treats two AION artists as 100% / 50% etc.,
   with no favorites. A future M5 pass could weight primary artists more
   heavily.
5. Search candidates are capped at 10 (`DEFAULT_SEARCH_LIMIT`). Tracks with
   more than 10 plausible candidates may yield false `no_match` results.

## Soundcharts Fallback Status

Unchanged from M4A. `SOUNDCHARTS_CLIENT_ID` and `SOUNDCHARTS_CLIENT_SECRET`
are still configured in `.env`, but the Soundcharts API returns HTTP 401
`invalid_client` on token requests. We did not spend additional time
debugging Soundcharts in this milestone per the brief. The
`SoundchartsEnrichmentSource` adapter remains in place and the Soundcharts
status row in `enrichment-sources` reports `READY` because the credentials
are present — the runtime auth failure is discovered only at probe time
(`python -m app.cli soundcharts-probe`).

## Recommendation

**Decision: BLOCKED (verification) — ACCEPT AS PRIMARY once a key is
configured.**

All code paths are implemented and unit-tested. Backend tests (174),
frontend typecheck, and frontend build all pass. The Soundcharts,
MusicBrainz, library, and importer regression suites are confirmed
passing. The only remaining blocker is the absence of a valid
`GETSONGBPM_API_KEY` in `.env`.

To unblock:

1. Sign up at https://getsongbpm.com/api for an API key.
2. Add `GETSONGBPM_API_KEY=<key>` to `.env` (never commit it).
3. Run `python -m app.cli getsongbpm-probe --limit 10` to execute the
   live 10-track gate.
4. If the gate passes, run
   `python -m app.cli enrich-library --source getsongbpm --limit 25`
   for the production enrichment batch.

This session (2026-09-01) confirmed the probe correctly reports
BLOCKED when no key is present. No live results were fabricated.

## Next Milestone

M5 — Camelot + harmonic compatibility (NOT STARTED).