# Spotify Web API — Capability Report (M0)

> **Honesty disclaimer.** This report distinguishes between
> "IMPLEMENTED in code" (we have written the function), "TESTED" (we have
> unit tests covering the behavior with mocked HTTP), and "VERIFIED" (we
> have actually executed the call against a real Spotify account). For
> M0 we did **not** have Spotify client credentials in this environment
> and therefore could not exercise the live OAuth flow. Live verification
> is the next step the user takes on their own machine.

- **Date tested:** 2026-08-28
- **API base:** `https://api.spotify.com/v1`
- **Auth flow implemented:** Authorization Code with PKCE
  ([reference](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow))
- **Scopes requested:**
  `user-read-private user-read-email user-library-read playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private`
- **Endpoints used in M0:**

| Endpoint                                       | Used for                            |
| ---------------------------------------------- | ----------------------------------- |
| `GET /me`                                      | current user                        |
| `GET /me/tracks`                               | Liked Songs (paginated)             |
| `GET /me/playlists`                            | owned playlists                     |
| `GET /playlists/{id}`                          | playlist detail + items             |
| `GET /tracks/{id}`                             | single track                        |
| `POST /users/{user_id}/playlists`              | create playlist                     |
| `POST /playlists/{id}/tracks`                  | add items                           |
| `POST https://accounts.spotify.com/api/token`  | exchange / refresh                  |

## Capability table

| Capability                     | Code status    | Test status | Live run         |
| ------------------------------ | -------------- | ----------- | ---------------- |
| OAuth Authorization Code + PKCE| IMPLEMENTED    | UNVERIFIED  | BLOCKED (no creds)|
| Token exchange                 | IMPLEMENTED    | UNVERIFIED  | BLOCKED          |
| Token refresh                  | IMPLEMENTED    | UNVERIFIED  | BLOCKED          |
| Current user (`/me`)           | IMPLEMENTED    | TESTED (mock)| BLOCKED          |
| Liked Songs (`/me/tracks`)     | IMPLEMENTED    | TESTED (mock, pagination + 3 pages)| BLOCKED |
| Liked Songs pagination         | IMPLEMENTED    | TESTED (mock, 3-page sequence)  | BLOCKED |
| Spotify track ID               | IMPLEMENTED    | TESTED (parsing)               | BLOCKED |
| ISRC                           | IMPLEMENTED    | TESTED (parsing + importer)     | BLOCKED |
| Owned playlist read            | IMPLEMENTED    | TESTED (parsing)               | BLOCKED |
| Foreign / public playlist read | NOT IMPLEMENTED IN M0 (no test fixture, would require a real playlist id supplied at runtime) | UNVERIFIED | UNTESTED |
| Create playlist                | IMPLEMENTED    | UNVERIFIED (HTTP not mocked)   | BLOCKED |
| Add tracks to playlist         | IMPLEMENTED    | UNVERIFIED (HTTP not mocked)   | BLOCKED |
| BPM                            | NOT PROVIDED by API | — | CONFIRMED (endpoint returns 403 for new apps per current docs) |
| Musical key                    | NOT PROVIDED by API | — | CONFIRMED |
| Energy                         | NOT PROVIDED by API | — | CONFIRMED |
| Danceability                   | NOT PROVIDED by API | — | CONFIRMED |
| Valence                        | NOT PROVIDED by API | — | CONFIRMED |
| Audio analysis                 | NOT PROVIDED by API | — | CONFIRMED |
| Genre (track-level)            | NOT PROVIDED by API | — | CONFIRMED |
| Popularity                     | DEPRECATED (returned in payload but marked Deprecated in current docs) | — | — |

## What we know about the "NOT PROVIDED" capabilities

The current Spotify Web API reference lists the
`Get Track's Audio Features`, `Get Several Tracks' Audio Features`, and
`Get Track's Audio Analysis` endpoints but Spotify's developer policy
since 2024 has restricted access for new applications. The endpoints
return **403 Forbidden** for apps created after the cutoff and are not a
viable enrichment source. AION therefore does not depend on them and
treats all of these attributes as **unavailable** until a separate
enrichment pipeline (MusicBrainz / AcousticBrainz / Essentia / future
ML) is wired in.

`popularity`, `preview_url`, `available_markets`, and `linked_from` are
listed in the current Track object schema but are marked **Deprecated**
in the API reference. We currently read them where they appear in
payloads but treat them as best-effort, not authoritative.

## Observed limitations (and what M0 does about them)

- **Audio features gone.** Spotify no longer grants access to new apps.
  AION does not call these endpoints and does not store fake values.
- **OAuth state lives in memory.** The M0 auth state store is in-process
  and not persistent. Sufficient for local dev; a real deployment will
  need Redis or signed cookies.
- **No refresh handling in CLI yet.** The probe currently uses the stored
  access token. The next milestone should refresh on 401 and retry.

## Field-name notes (parsed into our normalized models)

- Spotify track id: `track.id`
- ISRC: `track.external_ids.isrc`
- URI: `track.uri` (e.g. `spotify:track:4iV5W9uYEdYUVa79Axb7Rh`)
- URL: `track.external_urls.spotify`
- Duration: `track.duration_ms` (int)
- Album art: `track.album.images[0].url`
- Saved-at: `item.added_at` (ISO 8601, ends in `Z`)

## How to actually run the live probe

```bash
cd apps/api
# Put real SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET in .env
# Add http://localhost:8000/auth/spotify/callback to the Spotify app's Redirect URIs
alembic upgrade head
uvicorn app.main:app --reload --port 8000
# In the web UI: click "Connect Spotify" once and finish the flow.
# Then from CLI:
python -m app.cli spotify-probe
```

The CLI prints a real `seen / isrc_present / isrc_missing` tally and
creates a disposable playlist titled `Music Intelligence M0 Test`. The
source Liked Songs library is not modified.
