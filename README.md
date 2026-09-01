# AION — Music Intelligence

A provider-independent digital music crate for understanding, organizing, and
preparing music for DJing.

**Current milestone: M2 — MusicBrainz Identity Resolution**

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the architectural overview and
[`docs/decisions/`](./docs/decisions/) for ADRs.

M1 establishes the architecture and proves the Spotify integration against a
real account. M2 adds MusicBrainz Recording MBID resolution via ISRC lookups,
with full auditability, rate limiting, and resumable batch processing. It does
NOT implement BPM, key, energy, or any audio enrichment. Those sources will be
wired in later milestones, with provenance preserved.

M2 is NOT BPM/key enrichment. M2 is cross-source recording identity only.

See [`docs/api-research/SPOTIFY_CAPABILITY_REPORT.md`](./docs/api-research/SPOTIFY_CAPABILITY_REPORT.md)
for what was actually verified, and `python -m app.cli musicbrainz-status` /
`python -m app.cli musicbrainz-resolve --limit 25` for the resolver CLI.

## Repository layout

```
apps/
  api/      FastAPI backend (Python 3.11+/3.12+, SQLAlchemy 2, Alembic)
  web/      Next.js frontend (M1: Library Explorer "Your Crate")
docs/
  architecture/
  api-research/     Capability reports (Spotify, etc.)
  decisions/         ADRs
fixtures/           Non-secret sample data for tests
scripts/            Operational scripts
```

## M0 scope

M0 establishes the architecture and proves the Spotify integration against a
real account. It does NOT implement BPM, key, energy, or any enrichment. Those
sources will be wired in later milestones, with provenance preserved.

See [`docs/api-research/SPOTIFY_CAPABILITY_REPORT.md`](./docs/api-research/SPOTIFY_CAPABILITY_REPORT.md)
for what was actually verified.

## M1 scope — Library Explorer

M1 is the first read-only, user-facing view of the imported library:

- **Domain model stays truthful.** The "library" is the set of
  `ProviderTrack` rows imported from Spotify Saved Tracks (Liked Songs). No
  `Playlist` row is fabricated to make the UI look like a playlist.
- **Backend read API** (`apps/api/app/library/`):
  - `GET /api/tracks` — paginated, searchable, filterable, sortable listing.
    Query params: `page`, `page_size` (25/50/100), `search`, `provider`,
    `has_isrc` (`all`/`has`/`missing`), `sort`.
  - `GET /api/library/summary` — trustworthy counts (canonical tracks,
    provider occurrences, ISRC presence, per-provider breakdown).
- **Response model** exposes only normalized, safe fields (title, artists,
  album, artwork, duration, release date/year, Spotify id/uri/url, ISRC,
  provider, saved/imported timestamps). OAuth tokens, client secrets, and raw
  provider blobs are never returned.
- **Frontend** (`apps/web/app/`) — "Your Crate": connection status, library
  summary, search, filters, sort, pagination, and a track detail panel. It
  handles empty / loading / error / no-results / missing-artwork states
  gracefully and renders fast (server-side pagination, 50/page default).

M1 explicitly does NOT implement BPM, key, Camelot, energy, genre inference,
mood, vibe, MusicBrainz/AcousticBrainz/SoundCloud/Essentia lookups, transition
scoring, Smart Flow, DJ export, or Three.js visualizations. Those are deferred.


## Local development

### Backend

```bash
# 1. Create the root env file (single source of truth)
copy .env.example .env            # from repository root (AION/)
# Edit AION/.env and fill in SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET

# 2. Install backend (from repository root or apps/api)
cd apps/api
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows
pip install -e .

# 3. Run migrations — the data/ directory is created automatically
alembic upgrade head

# 4. Verify config and DB (safe — never prints secrets)
python -m app.cli status

# 5. Start API
uvicorn app.main:app --reload --port 8000
```

> **Working directory:** The backend resolves `.env` and the SQLite path
> deterministically via `app/core/config.py` (`AION/.env` and
> `AION/data/aion.db`), so `alembic` and `python -m app.cli` work from
> `AION/apps/api` without needing a duplicate `apps/api/.env`. The
> `apps/api/.env` path is also checked as an optional override, but a single
> root `.env` is the supported workflow. OS environment variables always
> override `.env`. From the repository root, use
> `PYTHONPATH=apps/api python -m app.cli status` if you prefer not to `cd`.

### CLI reality probe

```bash
cd apps/api
# Check that credentials are seen (PRESENT) without exposing values:
python -m app.cli status

# Only after OAuth has created an account — do NOT use placeholder YOUR_ID_HERE:
python -m app.cli spotify-probe --provider-user-id <real_spotify_user_id>
```

### Web

```bash
cd apps/web
npm install
npm run dev
```

## Security

- All credentials live in `.env`, which is gitignored.
- OAuth state and tokens are never logged or written to tracked files.
- The local SQLite database (which can hold live OAuth tokens) is gitignored.
