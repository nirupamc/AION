# M3 Enrichment Source Evaluation

> **Status:** PARTIAL — no production-ready BPM/key source selected yet.
> **Date:** 2026-08-31

---

## 1. Objective

Evaluate external data sources that can provide **BPM** and **musical key** for tracks in AION's Spotify-only library.

---

## 2. Constraints

- AION currently holds **3 185** tracks with ISRCs.
- Only **5** tracks have resolved MusicBrainz Recording MBIDs.
- No local user-owned audio files are available.
- Spotify Web API is in **Development Mode** (new app, post-Nov 27 2024).
- Do not scrape websites.

---

## 3. Source Classification

| Status | Meaning |
|--------|---------|
| READY | Implemented and live-tested with real data |
| LIVE TESTED | Verified against real API with actual credentials |
| BLOCKED — CREDENTIALS REQUIRED | API works but needs OAuth / API key we don't have |
| REJECTED | Unavailable, deprecated, or legally restricted for this app |
| NOT PRACTICAL | Technically possible but not viable for AION's constraints |
| NOT TESTED | Code exists but could not be exercised in this environment |

---

## 4. Evaluated Sources

### 4.1 Spotify Audio Features (`/v1/audio-features/{id}`)

| Attribute | Value |
|-----------|-------|
| Status | **REJECTED** |
| BPM | Would provide `tempo` |
| Key | Would provide `key` + `mode` |
| Credentials | Existing Spotify access token |
| Live Tested | No — endpoint returns 403 for Development Mode apps |

**Why rejected:**
Spotify restricted access to Audio Features, Audio Analysis, Recommendations, and Related Artists on **Nov 27 2024** for all new apps and existing Development Mode apps without a pending extension request. As a new app, AION receives `403 Forbidden` on this endpoint. The only path to access it is Extended Quota Mode, which now requires a legally registered organization with 250 000 monthly active users.

Spotify remains AION's **library source**, **track identity source**, and **playlist read/write source**. It is **not** a BPM/key enrichment source.

**Code status:** `SpotifyAudioFeaturesSource` exists in `app/enrichment/sources/spotify_audio_features.py` but is marked REJECTED in the CLI (`enrichment-sources`). The evaluation pipeline no longer includes it as a READY source.

---

### 4.2 AcousticBrainz

| Attribute | Value |
|-----------|-------|
| Status | **LIVE TESTED — COVERAGE LIMITED** |
| BPM | Yes (`rhythm.bpm`) |
| Key | Yes (`tonal.key_key`, `tonal.key_scale`) |
| Credentials | None (read-only public API) |
| Live Tested | Yes — API reachable; 0/5 local MBIDs returned data |

**What was tested:**
- Queried `https://acousticbrainz.org/api/v1/{mbid}/low-level` for all 5 MBIDs in the local database.
- API is live and responds. All 5 MBIDs returned `404 Not Found`, indicating no low-level analysis has been submitted for those recordings.

**Why coverage is limited:**
AcousticBrainz indexes data by MusicBrainz Recording ID. AION has only **5/3185** tracks with resolved MBIDs. AcousticBrainz data collection also **stopped in 2022**, so even if MBIDs were resolved today, the likelihood of finding data for recent releases is low.

**Verdict:** AcousticBrainz is a legitimate open data source for BPM/key, but its utility for AION is **blocked by upstream identity resolution**. To evaluate AcousticBrainz meaningfully, AION first needs a larger set of MusicBrainz-matched tracks.

---

### 4.3 SoundCloud

| Attribute | Value |
|-----------|-------|
| Status | **BLOCKED — CREDENTIALS REQUIRED** |
| BPM | Yes (`bpm` field, uploader-supplied) |
| Key | Yes (`key_signature` field, uploader-supplied) |
| ISRC | Yes (`isrc` field) |
| Credentials | OAuth access token required |
| Live Tested | No |

**Current official documentation findings:**
- SoundCloud API v2 (current as of 2026-03-24) exposes `bpm`, `key_signature`, `genre`, and `isrc` on the Track object.
- Search endpoint (`GET /tracks`) supports `q` (text query against title/username/description) and `bpm[from]`/`bpm[to]` range filters.
- **No ISRC search endpoint exists.** The API does not support looking up tracks by ISRC.
- Matching Spotify tracks to SoundCloud tracks would require either:
  - text search by title+artist (high ambiguity), or
  - audio fingerprinting (not available via public API).

**Why blocked:**
AION does not have SoundCloud OAuth credentials. Implementing SoundCloud OAuth is non-trivial and would only yield metadata that is uploader-supplied (not verified), with no reliable path to match against the existing Spotify library.

---

### 4.4 Essentia / Essentia.js

| Attribute | Value |
|-----------|-------|
| Status | **NOT PRACTICAL — AUDIO REQUIRED** |
| BPM | Yes (rhythm extraction algorithms) |
| Key | Yes (key detection algorithms) |
| Confidence | Yes (includes half/double tempo detection) |
| Credentials | N/A — requires actual audio files |
| Live Tested | No |

**Key facts:**
- Essentia is an open-source C++ library for audio analysis. It provides BPM, key, danceability, and many other features.
- Essentia.js is the browser/Node.js port.
- **Essentia cannot analyze Spotify metadata.** It requires actual audio waveforms (WAV, MP3, etc.).
- Spotify preview URLs (30-second clips) are insufficient for reliable key/BPM analysis and may not be available for all tracks.
- Downloading Spotify audio for analysis violates Spotify's Terms of Service.

**Browser vs Python:**
- Essentia.js runs in the browser via WebAssembly. It is feasible for a local desktop app but adds significant bundle size.
- Python Essentia requires local audio files and FFmpeg.

**Verdict:** Essentia is the correct tool for **local high-confidence analysis** when AION eventually ingests user-owned audio files. For a Spotify-only library, it is **not viable**.

---

### 4.5 ACRCloud Music Metadata API

| Attribute | Value |
|-----------|-------|
| Status | **RESEARCHED — NOT SUITABLE** |
| BPM | No (not in standard metadata response) |
| Key | No |
| ISRC | Yes |
| Credentials | API key (14-day free trial, then paid) |
| Catalog | Global DSP links (Spotify, Apple Music, YouTube, etc.) |

**Findings:**
ACRCloud's Music Metadata API is a link-aggregation service. It returns streaming URLs and identifiers for major platforms but does **not** include BPM or key in the standard track metadata response. It is designed for DSP linking, not audio feature enrichment.

---

### 4.6 Soundcharts API

| Attribute | Value |
|-----------|-------|
| Status | **RESEARCHED — POTENTIAL COMMERCIAL CANDIDATE** |
| BPM | Yes (`song.tempo`) |
| Key | Yes (`song.key`, integer pitch class) |
| Time Signature | Yes (`song.time_signature`) |
| ISRC | Yes (via `GET /song/by-isrc/{isrc}`) |
| Credentials | API key (paid plans) |
| Pricing | Not publicly disclosed; requires partnership |

**Findings:**
Soundcharts explicitly returns BPM, key, and time signature in song metadata. It supports ISRC-based lookup. The API appears to be the closest commercial match to AION's requirements. However:
- No free tier is advertised.
- Pricing requires contacting sales.
- Coverage for obscure/independent releases is unknown.

---

### 4.7 Gracenote GMD API / Sonic Descriptor API

| Attribute | Value |
|-----------|-------|
| Status | **RESEARCHED — POTENTIAL COMMERCIAL CANDIDATE** |
| BPM | Yes (via Sonic Descriptor API `sonicDescriptors.tempos`) |
| Key | No (not explicitly returned; moods/styles provided instead) |
| ISRC | Yes (GMD API `/v1.1/tracks/isrc`) |
| Credentials | API key (enterprise) |
| Pricing | Not public; requires Gracenote representative |

**Findings:**
Gracenote's Sonic Descriptor API returns tempo descriptors (e.g., "60s", "250s") given an ISRC. It does **not** return a precise BPM number or musical key. The GMD API requires an enterprise agreement. The Sonic Descriptor API is described as available to "customers" with a GMD API key.

---

## 5. Coverage Results

### 5.1 AcousticBrainz Live Test

- **Tested MBIDs:** 5 (all local tracks with resolved MusicBrainz IDs)
- **BPM found:** 0/5
- **Key found:** 0/5
- **API status:** Reachable, but no data for local MBIDs

**Conclusion:** AcousticBrainz live evaluation is **coverage-limited by upstream identity resolution**. AION has only 5 MBIDs out of 3185 tracks. Even if AcousticBrainz had data, the sample size is too small to draw meaningful conclusions about source capability.

### 5.2 Spotify Audio Features

- **Attempted:** 5/50 tracks in evaluation sample
- **Errors:** 5/5 (`403 Forbidden` — blocked for Development Mode apps)
- **Conclusion:** Not available.

---

## 6. Credential Summary

| Source | Credential Type | AION Has It? |
|--------|----------------|-------------|
| Spotify Audio Features | Spotify access token | Yes, but endpoint blocked |
| AcousticBrainz | None | Yes (public API) |
| SoundCloud | OAuth access token | No |
| Essentia | Local audio files | No |
| ACRCloud | API key | No |
| Soundcharts | API key | No |
| Gracenote | Enterprise API key | No |

---

## 7. Spotify Token Refresh (M3 Side Note)

The Spotify OAuth implementation was audited during M3. **Automatic token refresh is now implemented** in the API and CLI layers:

- On `401 Unauthorized`, if a stored refresh token exists, AION automatically requests a new access token, persists it, and retries the failed request once.
- If the refresh token itself is invalid/expired, the system reports `"Reconnect Spotify"` — a clear reauthentication signal.
- This ensures the evaluation pipeline and production API endpoints do not fail merely due to expired access tokens.

Regression tests added:
- `test_endpoint_refreshes_token_on_401_and_retries`
- `test_endpoint_reauth_when_no_refresh_token`
- `test_enrichment_source_refreshes_on_401_and_retries`
- `test_enrichment_source_reauth_when_refresh_fails`
- `test_enrichment_source_no_refresh_without_callback`

---

## 8. M3 Verdict

### M3 Status: **PARTIAL**

No single source currently satisfies all of AION's requirements for BPM/key enrichment. The evaluation has identified the following strategic options:

| Role | Source | Rationale |
|------|--------|-----------|
| **Primary** | Commercial catalog API (Soundcharts preferred) | Only source with verified BPM + key + ISRC lookup capability |
| **Secondary** | SoundCloud metadata | Free tier unavailable; requires OAuth; matching is ambiguous |
| **Historical fallback** | AcousticBrainz | Open data, but coverage limited by MBID resolution and 2022 data freeze |
| **Local analysis** | Essentia | High confidence, but requires user-owned audio files |
| **Identity / library** | Spotify | Remains the source of truth for track identity, ISRC, and playlists |

### Spotify Audio Features Decision: **REJECTED**

The endpoint is blocked for AION's Development Mode app. The codebase retains the `SpotifyAudioFeaturesSource` for historical reference but it is not used in live evaluation and is marked REJECTED in the CLI.

### Recommendation for M4

M4 should focus on integrating a **commercial metadata API** as the primary BPM/key source. The recommended approach is:

1. **Contact Soundcharts** for API pricing and trial access.
2. If Soundcharts is not viable, evaluate **Gracenote Sonic Descriptor API** as an alternative.
3. As a long-term secondary path, increase MusicBrainz MBID resolution coverage to enable AcousticBrainz fallback for catalog tracks that have been analyzed.
4. For user-uploaded or local files, add Essentia.js as a high-confidence local analysis layer.

---

## 9. Tests

| Test Suite | Status |
|------------|--------|
| Backend pytest | 73 passed |
| Frontend typecheck | Clean (verified earlier) |
| Frontend build | Clean (verified earlier) |
| Token refresh regression | 5 new tests added, all passing |
| Enrichment auth tests | 3 new tests added, all passing |

---

## 10. Next Steps

1. Sign up for a Soundcharts API trial and test ISRC → BPM/key lookup against the evaluation sample.
2. If successful, implement a production `SoundchartsMetadataSource` in `app/enrichment/sources/`.
3. Expand MusicBrainz resolution to increase MBID coverage for AcousticBrainz fallback testing.
4. Do **not** attempt to work around Spotify's Audio Features restriction.
