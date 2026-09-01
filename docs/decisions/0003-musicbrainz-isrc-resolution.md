# ADR 0003 — MusicBrainz ISRC Resolution as Identity Layer

## Status

Accepted (M2).

## Context

M1 proves the imported library is queryable and renderable, but AION's
canonical `Track` identity is currently provider-local: it knows a Spotify ID
and an ISRC (when present), but nothing independent of Spotify. For DJing and
cross-provider workflows, we need a stable, source-independent recording
identity that survives provider changes.

MusicBrainz is the obvious candidate: no API key is required for read-only
lookups, the ISRC endpoint returns a list of recordings, and an exact ISRC
match yields a high-confidence Recording MBID.

Key constraints from MusicBrainz's own documentation:

- ~1 request/second maximum per client.
- Meaningful User-Agent is mandatory.
- No OAuth / API key for read-only.
- ISRC lookups return a list (not a single record) — ambiguity is possible.

## Decision

Adopt MusicBrainz ISRC lookup as the M2 identity resolution path, with the
following concrete choices:

1. **Primary key = ISRC.** We do NOT attempt Spotify title/artist matching
   against MusicBrainz search. ISRC is a strong, standardized identifier; if
   MusicBrainz has exactly one recording for that ISRC, confidence is high.

2. **Ambiguity is preserved, not forced.** When `recordings` contains more than
   one entry, the resolver records `status = AMBIGUOUS` and stores the
   candidate list in `metadata_json`. No automatic selection by heuristic
   score.

3. **Persistence in two places:**
   - `TrackIdentifier(identifier_type="musicbrainz_recording_id")` for the
     matched MBID (when status is MATCHED).
   - `TrackIdentityResolution` for every outcome (MATCHED, NO_MATCH,
     AMBIGUOUS, ERROR, DEFERRED) with full provenance, timestamp, and
     resolver version.

4. **Explicit rate limiting.** The MusicBrainz adapter paces requests to at
   least `MUSICBRAINZ_MIN_INTERVAL` seconds apart (default 1.1s) and retries
   on 5xx / timeouts with bounded backoff. No anonymous defaults.

5. **Resumable, idempotent batch processing.** The resolver queries only
   `eligible` tracks (ISRC present, no completed resolution). Duplicate ISRCs
   across tracks are deduped within a batch. Re-running the same limit resumes
   from the next unresolved track. `--force-retry` re-evaluates specific
   outcomes.

6. **User-Agent validation in `Settings`.** `MUSICBRAINZ_USER_AGENT` must
   contain "AION" and be at least 10 characters. The adapter reads from
   settings; the CLI fails fast on invalid config.

## Consequences

- Positive: high-confidence cross-source identity for matched ISRCs; full
  audit trail; safe, respectful use of the public MusicBrainz API; no
  accidental replacement of Spotify or ISRC identifiers.
- Negative: not all ISRCs resolve uniquely; some are absent from MusicBrainz;
  resolver must be run in small batches. Acceptable for M2; enrichment in M3
  will build on this identity foundation.

## Alternatives rejected

- MusicBrainz search by title/artist: too fuzzy, requires scoring heuristics,
  and the ISRC endpoint is stronger.
- Synchronous bulk resolution: violates the 1 req/sec rule and makes the
  process fragile.
- Auto-merge multiple recordings: introduces unexplained selection logic and
  risks incorrect identity mapping.
