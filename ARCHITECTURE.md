# AION Architecture (M2)

## Mission

A provider-independent digital music crate for understanding, organizing, and
preparing music for DJing. The same core engine will support Spotify today
and SoundCloud, local audio, Rekordbox/Serato exports, and CSV imports later.

## Layered view

```
                  ┌──────────────────────────────────────────┐
                   │              Web (Next.js)               │
                   │   M1 Library Explorer "Your Crate"        │
                  └────────────────────┬─────────────────────┘
                                       │  /api/*  (proxied)
                  ┌────────────────────▼─────────────────────┐
                   │           FastAPI application             │
                   │  routes · importer · auth · health · lib  │
                  └────┬─────────────┬────────────┬───────────┘
                       │             │            │
        ┌──────────────▼─┐  ┌────────▼────────┐  ┌▼─────────────────┐
        │ Provider layer │  │  Tracks service │  │ Playlists service│
        │  (Catalog +    │  │  (importer)     │  │ (snapshots)      │
        │   Writer +     │  │                 │  │                  │
        │   Auth)        │  │                 │  │                  │
        └──────┬─────────┘  └────────┬────────┘  └────────┬─────────┘
               │                     │                   │
               ▼                     ▼                   ▼
      ┌─────────────────┐   ┌──────────────────────────────┐
      │ Spotify adapter │   │  SQLAlchemy 2 models         │
      │  httpx client   │   │  Track, TrackIdentifier,     │
      │  normalized DTO │   │  ProviderTrack, TrackAttribute│
      │  error mapping  │   │  MusicAccount, OAuthToken,   │
      └────────┬────────┘   │  Playlist, PlaylistTrack,    │
               │            │  PlaylistSnapshot            │
               ▼            └──────────────┬───────────────┘
        ┌─────────────────┐                 │
        │  api.spotify.com│                 ▼
        └─────────────────┘          ┌──────────────┐
                                      │  SQLite (M1) │
                                      │  Alembic     │
                                     └──────────────┘
```

## Domain boundaries (the central decision)

Five distinct concepts that M0 keeps separate. Future enrichment hooks attach
to (3) without touching (1) or (2).

1. **Track identity** — a canonical recording (`Track`).
2. **Provider-specific occurrences** — `ProviderTrack` rows, one per
   provider, joined back to (1). Uniqueness on `(provider, provider_track_id)`.
3. **Track attributes** — `TrackAttribute` rows. Every observation keeps
   `source_type`, `source_name`, `confidence`, `analysis_version`, and an
   `is_current` flag. A future resolver picks the current value from
   history; we do not collapse observations into a single column.
4. **Playlists** — `Playlist` + `PlaylistTrack` (with `position` and
   `original_position`) + `PlaylistSnapshot` for reproducibility.
5. **MusicAccount / OAuthToken** — separated so we can store multiple
   connected providers per user.

A track never has `track.bpm = 126`. A track has zero or more observations
of `tempo_bpm`, each with its own provenance. M0 stores zero of these.

## Provider abstraction

```
app/providers/base/
  protocols.py    CatalogProvider, PlaylistWriter, AuthProvider
  models.py       provider-agnostic dataclasses (ProviderTrack, ProviderUser, ...)
  errors.py       ProviderError / Auth / Permission / RateLimit / NotFound
  http_client.py  shared httpx wrapper, retries on 429 and 5xx
app/providers/spotify/
  parsing.py      ONLY place that knows Spotify JSON
  oauth.py        Authorization Code + PKCE; refresh tokens
  provider.py     SpotifyProvider implements CatalogProvider + PlaylistWriter
```

A future SoundCloud or local-file adapter implements the same protocols and
the rest of the system does not change. Core services depend on
`CatalogProvider` and `PlaylistRef`, never on Spotify types.

## Authentication

Spotify OAuth uses the **Authorization Code flow with PKCE** (the
recommended flow for long-running server-side apps, per current Spotify
docs). Scopes used in M0:

- `user-read-private`, `user-read-email` (current user)
- `user-library-read` (Liked Songs)
- `playlist-read-private`, `playlist-read-collaborative` (playlists)
- `playlist-modify-public`, `playlist-modify-private` (later: export)

State is held in an in-memory store (TTL 10 min) keyed by a
cryptographically random value; PKCE verifier is stored alongside.
Tokens are persisted in the database (which is gitignored). The client
secret never leaves the backend.

## What M0 deliberately does NOT do

See `docs/decisions/0001-provider-independent-track-model.md`. The
short version: we do not assume Spotify supplies BPM, key, energy, or any
musical analysis. The schema is ready for those columns; M0 leaves them
empty.

## Where to extend

- Enrichment: new adapter implementing `CatalogProvider` or a dedicated
  `EnrichmentProvider` writes `TrackAttribute` rows.
- Identity resolution: tighten `_find_track_for_provider_track` in
  `app/tracks/__init__.py` once we have a real MusicBrainz adapter.
- Visualization: the web layer is currently a thin client; the next
  milestone can read from `/api/tracks` (a new endpoint) without touching
  the importer or provider layer.

## M1 — Library Explorer (read-only)

M1 proves the imported canonical/provider data can be queried, paginated,
filtered, searched, and rendered reliably. It does NOT enrich.

Data flow:

```
Spotify Liked Songs (Saved Tracks)
        │  (already imported in M0)
        ▼
ProviderTrack  (one row per Spotify occurrence)
        │  joined to
        ▼
Track  (canonical identity)
        │  joined to
        ▼
TrackIdentifier (isrc, spotify_id)
        │
        ▼
GET /api/tracks  →  Library query (app/library/__init__.py)
        │
        ▼
Library Explorer UI ("Your Crate")
```

Design notes:

- **No fabricated playlist.** Liked Songs are not modeled as a `Playlist`. The
  library is the `ProviderTrack` set; the UI labels it "Your Crate" / "Liked
  Songs" without lying about the domain model.
- **Denormalized display columns.** `ProviderTrack` gained four small columns
  (`artist_display`, `album_name`, `release_date`, `artwork_url`) so that
  search/sort on artist/album/release can run in SQL without parsing the
  `raw_metadata` JSON blob on every request. The canonical source of truth
  remains `raw_metadata` and `TrackIdentifier`; the columns are derived at
  import time and backfilled by migration `0002_provider_track_display`. See
  `docs/decisions/0002-provider-track-display-columns.md`.
- **No N+1.** Per page, ISRCs are fetched in a single query keyed by the page's
  `track_id`s; artwork/artist/album come from denormalized columns or a safe
  JSON parse fallback.
- **Safe responses.** The API exposes only normalized fields. Tokens, client
  secrets, OAuth data, and the raw provider blob are never serialized.
 - **Stable ordering.** Every sort adds a secondary `id` tiebreak so pagination
   is deterministic even for duplicate titles/artists.

## M2 — MusicBrainz Identity Resolution

M2 enriches the canonical Track identity with independent cross-source
Recording MBIDs from MusicBrainz, resolved from existing ISRCs. It does NOT
enrich with BPM, key, energy, genre, or mood.

Data flow:

```
Spotify ProviderTrack
        ↓
      ISRC  (stored in TrackIdentifier)
        ↓
MusicBrainz Web Service v2  (anonymous, ~1 req/sec, meaningful User-Agent)
        ↓
MusicBrainz Recording  (MBID)
        ↓
TrackIdentifier:  identifier_type = musicbrainz_recording_id
TrackIdentityResolution:  status = MATCHED / NO_MATCH / AMBIGUOUS / ERROR
        │
        ▼
GET /api/tracks/{id}  →  identity + resolution detail
        │
        ▼
Library Explorer UI ("Your Crate") — detail panel shows MB identity + status
```

Design notes:

- **ISRC is the primary key.** No Spotify title/artist matching is performed.
- **No API key required.** MusicBrainz Web Service v2 reads require only a
  meaningful User-Agent, which is validated in `Settings` and never sent
  anonymously.
- **Rate limiting is explicit.** The adapter enforces a minimum interval
  between requests (default 1.1s) and retries on 5xx/timeouts. No parallel
  high-volume requests.
- **Conservative ambiguity.** Multiple recordings for one ISRC are preserved as
  `AMBIGUOUS` with candidate metadata; no random forced match.
- **Dedup + cache.** Identical ISRCs are queried once per batch. Resolution
  outcomes are persisted in `track_identity_resolutions` so restarts resume
  cheaply.
- **Resumable.** `eligible_tracks_with_isrc` skips already-resolved tracks by
  default; `--force-retry` re-evaluates explicit retry targets.
- **Idempotent.** Re-running the same batch skips completed resolutions.
- **Safe responses.** The API returns only normalized identifiers and
  resolution status. Giant raw MusicBrainz blobs are never serialized.
- **Track detail API.** `GET /api/tracks/{track_id}` exposes identifiers and
  resolution history. The frontend detail panel shows Spotify ID, ISRC,
  MusicBrainz MBID (or "Not resolved"), and resolution status.


