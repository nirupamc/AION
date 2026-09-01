# ADR 0002 — Denormalized display columns on `ProviderTrack`

## Status

Accepted (M1).

## Context

M1 needs to let the user **search** (title / artist / album) and **sort**
(title / artist / album / release) the imported library without loading all
~3,200 provider tracks into the browser. In M0, the only persisted normalized
fields on `ProviderTrack` were `raw_title` and `duration_ms`; artist, album,
artwork, and release date lived only inside the `raw_metadata` JSON blob.

Options considered:

1. **Parse `raw_metadata` at query time** for every row. Simple, no migration,
   but search/sort would require loading and parsing JSON for all matching rows
   (and SQLite `LIKE` / `ORDER BY` cannot reliably target nested JSON fields),
   so it does not satisfy server-side search/sort.
2. **Store everything enriched up front** (full normalization of every Spotify
   field). Overkill for M1 and risks scope creep into enrichment territory.
3. **Add small denormalized display columns** (`artist_display`, `album_name`,
   `release_date`, `artwork_url`) derived from `raw_metadata` at import time,
   indexed, and backfilled for existing rows.

## Decision

Adopt option 3. Add four nullable columns to `ProviderTrack`, populate them in
the importer (`app/tracks/__init__.py`) from the normalized `ProviderTrack`
model, and backfill existing rows via Alembic migration
`0002_provider_track_display` (which parses `raw_metadata` in-process).

The canonical source of truth remains `raw_metadata` + `TrackIdentifier`. The
new columns are a derived, read-optimized projection. The API serialization
also falls back to parsing `raw_metadata` when a column is null, so the system
is robust even for rows that predate the column or were imported with
`retain_raw=False`.

## Consequences

- Positive: reliable, index-friendly SQL search/sort; no N+1; no JSON parsing in
  the hot path; backfill is a one-time, offline-safe operation.
- Negative: minor duplication of data; importer and migration must stay in sync
  with the derivation logic. Acceptable for M1 and re-evaluated if/when a richer
  normalized schema is introduced for enrichment.

## Alternatives rejected

- Full normalization now: premature; would blur the M0/M1 boundary that
  explicitly defers enrichment.
- Pure runtime JSON parsing: cannot deliver server-side search/sort at scale.
