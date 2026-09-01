# ADR 0001 — Provider-Independent Track Model

- **Status:** Accepted (M0)
- **Date:** 2026-08-28
- **Context:** AION imports tracks from Spotify today and will import from
  SoundCloud, local audio, Rekordbox, Serato, and CSV later. Multiple
  enrichment sources (MusicBrainz, AcousticBrainz, Essentia, future ML)
  will produce overlapping but not identical musical attributes.

## Decision

The schema treats Spotify (and every other provider) as **one possible
source of identity and metadata** — not as the source of musical analysis.
Concretely:

1. `Track` is a canonical recording-level entity. It is not a Spotify row.
2. `ProviderTrack` is a provider-specific occurrence. Uniqueness is on
   `(provider, provider_track_id)`.
3. `TrackIdentifier` carries external IDs (`spotify_id`, `isrc`,
   `musicbrainz_recording_id`, ...). Uniqueness is on
   `(identifier_type, identifier_value)`.
4. `TrackAttribute` is **append-only observations with provenance**.
   Every row has `source_type` (`provider | external_metadata |
   audio_analysis | derived | ml_inference | user`), `source_name`,
   `confidence`, and `analysis_version`. There is no `track.bpm` column.
5. The "current" value for an attribute is a *resolver* problem. M0
   leaves every row `is_current=False` except in tests; the resolver is a
   later concern.

## Why

- Different sources **will** disagree (e.g. one provider reports 126 BPM
  from a fingerprint, Essentia reports 125.82 from a local file). Storing
  only the latest value loses information and makes later improvements
  impossible.
- Spotify's Web API does not currently expose audio features / audio
  analysis to new applications. We must not pretend it does.
- Identity resolution across providers is hard. The M0 importer uses
  only strong signals (same `spotify_id`, same `isrc`) and intentionally
  does not fuzzy-match by title+artist. That work is deferred.
- Provider adapters can be swapped without breaking the domain. Adding
  SoundCloud later means writing a `SoundCloudProvider` and the importer
  keeps working.

## Consequences

- A "current BPM" lookup is a query, not a column read. M0 returns
  empty / not-implemented for all attribute-based UI.
- Tests must not assert fake attribute values. The provenance model
  exists so future sources can argue.
- Visualization features are deferred until at least one real source
  populates `TrackAttribute`.

## Alternatives considered

- "Just store `track.bpm` and overwrite on each source." Rejected:
  destructive, loses history, makes "which source?" unanswerable.
- "Store the latest value per source in separate columns." Rejected:
  schema explodes with N sources × M attributes, and conflict
  resolution still lives somewhere implicit.
- "Compute attributes from audio we don't have." Rejected: we have no
  audio and no rights to it for Spotify tracks.
