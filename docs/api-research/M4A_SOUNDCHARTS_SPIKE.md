# M4A — Soundcharts Live BPM/Key Provider Spike

> **Status:** BLOCKED — CREDENTIALS INVALID
> **Date:** 2026-08-31

---

## Provider Access

Soundcharts requires a paid account with API client credentials.

- **Account required:** Yes
- **Trial available:** Not verified (no public self-serve signup found)
- **Contact:** `help@soundcharts.com` for access/plan details
- **Pricing:** Not publicly disclosed

**Current status:** `SOUNDCHARTS_CLIENT_ID` and `SOUNDCHARTS_CLIENT_SECRET` are configured in `.env`, but the token endpoint rejects them as invalid.

---

## Authentication

Mechanism: **OAuth2 client_credentials**

1. Create API credentials in Soundcharts console.
2. `POST https://account.soundcharts.com/oauth/token`
   - HTTP Basic auth: `client_id:client_secret`
   - Body: `grant_type=client_credentials`
   - Optional: `team_id`
3. Response:
   ```json
   {
     "access_token": "ACCESS_TOKEN",
     "token_type": "bearer",
     "expires_in": 3600,
     "refresh_token": null
   }
   ```
4. Use `Authorization: Bearer ACCESS_TOKEN` on API requests.
5. No refresh token is issued. Request a new token when the current one expires (default 3600s).

---

## Endpoint Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v2.25/song/by-isrc/{isrc}` | GET | Exact ISRC lookup → song metadata (BPM, key, time_signature) |

---

## Response Schema (Song)

Relevant fields from the Song response:

| Field | Type | Description |
|-------|------|-------------|
| `uuid` | string | Soundcharts song ID |
| `tempo` | float | BPM |
| `key` | int | Pitch class: -1=none, 0=C, 1=C#, ... 11=B |
| `mode` | int | 1=major, 0=minor |
| `time_signature` | int | 3-7 (e.g. 4 = 4/4) |

---

## Sample Selection

10 real AION tracks:

| # | Track ID | Title | Artist | ISRC | Year | Type |
|---|----------|-------|--------|------|------|------|
| 1 | 2630 | I Can't Help Myself (Sugar Pie, Honey Bunch) | Four Tops | USMO16582593 | 1965 | mainstream classic |
| 2 | 2081 | Everybody Talks | Neon Trees | USUM71119189 | 2012 | mainstream |
| 3 | 2138 | Sedona | Houndmouth | GBCVZ1403597 | 2015 | indie/alternative |
| 4 | 1595 | COFFEE BEAN | Travis Scott | USSM11806672 | 2018 | mainstream hip-hop |
| 5 | 1912 | Golden | Harry Styles | USSM11912586 | 2019 | mainstream pop |
| 6 | 1910 | Everybody | Mac Miller | USWB11801012 | 2020 | mainstream hip-hop |
| 7 | 2614 | Blue Skies | dexter in the newsagent | GBKPL2150741 | 2021 | niche/independent |
| 8 | 974 | Strange Love - Single Edit | Cautious Clay, Saba | QM6P42134545 | 2021 | edit/version |
| 9 | 740 | Save a Soul | nimino | QMDA62294501 | 2022 | niche/electronic |
| 10 | 2307 | She's A 10 But (Remix) (feat. Yung Gravy) | ARTAN, Yung Gravy | GBUM72300639 | 2023 | remix |

**Sample file:** `fixtures/enrichment/m4a_soundcharts_sample.json`

---

## Live Results

**Status: BLOCKED — CREDENTIALS INVALID**

All 10 track lookups failed at the OAuth token acquisition step with HTTP 401.

### Aggregate

| Metric | Value |
|--------|-------|
| queried | 10 |
| matched | 0 |
| no_match | 0 |
| ambiguous | 0 |
| error | 10 |
| BPM coverage | 0.0 |
| key coverage | 0.0 |
| both coverage | 0.0 |
| median latency | 1000.0 ms |

### Per-Track Errors

| Track ID | ISRC | Status | Error Type | HTTP Status | Error Message |
|----------|------|--------|-----------|-------------|---------------|
| 2630 | USMO16582593 | error | authentication | 401 | Client authentication failed |
| 2081 | USUM71119189 | error | authentication | 401 | Client authentication failed |
| 2138 | GBCVZ1403597 | error | authentication | 401 | Client authentication failed |
| 1595 | USSM11806672 | error | authentication | 401 | Client authentication failed |
| 1912 | USSM11912586 | error | authentication | 401 | Client authentication failed |
| 1910 | USWB11801012 | error | authentication | 401 | Client authentication failed |
| 2614 | GBKPL2150741 | error | authentication | 401 | Client authentication failed |
| 974 | QM6P42134545 | error | authentication | 401 | Client authentication failed |
| 740 | QMDA62294501 | error | authentication | 401 | Client authentication failed |
| 2307 | GBUM72300639 | error | authentication | 401 | Client authentication failed |

---

## Root Cause Classification

**AUTHENTICATION**

The Soundcharts OAuth2 token endpoint (`POST https://account.soundcharts.com/oauth/token`) returns:

```json
{
  "error": "invalid_client",
  "error_description": "Client authentication failed"
}
```

HTTP status: **401 Unauthorized**

This means the configured `SOUNDCHARTS_CLIENT_ID` and/or `SOUNDCHARTS_CLIENT_SECRET` are:
- Incorrect
- Revoked
- From a deactivated account
- Or the account has no active API plan

No song metadata was fetched. No BPM or key data was retrieved.

---

## BPM Coverage

0% — no tracks matched.

---

## Key Coverage

0% — no tracks matched.

---

## Match Reliability

Cannot measure. Zero successful lookups.

---

## Rate Limits

Not reached. All requests failed at authentication.

---

## Cost / Plan Limitations

Cannot verify. The configured credentials are invalid, suggesting the account may not be active or the plan does not include API access.

---

## Terms / Usage Concerns

- Soundcharts Terms of Service and Privacy Policy apply.
- Data redistribution terms not publicly documented in detail.
- AION should review Soundcharts TOS before storing/redistributing metadata.

---

## Operational Complexity

- Token management is straightforward (client_credentials, 1h tokens).
- The actual blocker is credential validity, not implementation complexity.

---

## Recommendation

### M4A Status: **BLOCKED — CREDENTIALS INVALID**

The Soundcharts spike implementation is complete and tests pass. However, the configured credentials are rejected by the Soundcharts token endpoint.

### Decision Gate: **BLOCKED — CREDENTIALS REQUIRED**

**Next steps to unblock:**
1. Verify `SOUNDCHARTS_CLIENT_ID` and `SOUNDCHARTS_CLIENT_SECRET` in `.env` are correct.
2. If credentials were recently created, confirm the account is active and the API client is enabled.
3. Contact `help@soundcharts.com` if the account is new or if activation is required.
4. Re-run `python -m app.cli soundcharts-probe --limit 10` after fixing credentials.
5. If live coverage is strong → **ACCEPT FOR PRODUCTION** and plan M4B.
6. If coverage is weak → evaluate the next provider.

---

## Implementation Summary

| Artifact | Status |
|----------|--------|
| `app/enrichment/sources/soundcharts.py` | Implemented |
| `fixtures/enrichment/m4a_soundcharts_sample.json` | Created (10 tracks) |
| `.env.example` | Updated with Soundcharts vars |
| `app/core/config.py` | Updated with Soundcharts settings |
| `app/cli.py` | Added `soundcharts-probe` command + error breakdown |
| `app/enrichment/__init__.py` | Added `error_type`, `http_status` to `EnrichmentResult` |
| `app/enrichment/evaluation.py` | Fixed `write_report` filename + absolute path resolution |
| `tests/test_soundcharts_source.py` | 15 tests, all passing |
| `tests/test_m4a_artifact_persistence.py` | 8 tests, all passing |
| Backend test suite | 96 passed, 0 regressions |

---

## Tests

| Suite | Result |
|-------|--------|
| Backend pytest | **96 passed** |
| Soundcharts source tests | **15 passed** |
| Artifact persistence tests | **8 passed** |
| Frontend typecheck | Clean (previously verified) |
| Frontend build | Clean (previously verified) |

---

## Output Path

```
D:\protofolo projectzzz\AION\docs\api-research\m4a_soundcharts_results.json
```

Artifacts are now written to an absolute, project-root-anchored path regardless of CWD.

---

## CLI Diagnostics Improvement

Before:
```
errors:
  10 x authentication
```

After:
```
errors (soundcharts):
  10 x authentication
```

Plus per-track error details in the JSON:
- `error_type`
- `http_status`
- `error` (safe provider message, no secrets)
- `latency_ms`
