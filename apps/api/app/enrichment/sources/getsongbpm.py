"""GetSongBPM enrichment source for M4B.

Implements the documented GetSongBPM REST API:
  Base URL: https://api.getsongbpm.com
  Auth:     api_key URL parameter OR X-API-KEY header
  Endpoints:
    GET /search/?type={song|artist|both}&lookup=<query>&limit=<n>
    GET /song/?id=<song_id>

Docs: https://getsongbpm.com/api
Free tier: ~3000 requests/hour. Backlink attribution REQUIRED.

Matching strategy (no ISRC lookup available):
1. Run a "song" search using AION title (+ optional primary artist).
2. Score each candidate on:
   - title token overlap (Jaccard)
   - artist overlap (Jaccard on normalized names)
   - version-token preservation (Remix / Edit / Mix / Live / ...)
   - duration proximity (when known)
3. Apply strict thresholds. The best candidate must clear
   ``ACCEPT_SCORE`` AND match at least one primary artist AND
   pass the version-token safety check. Otherwise the result is
   AMBIGUOUS, NO_MATCH, or ERROR.

Result states:
  matched    — single high-confidence candidate; BPM/key may be None
  no_match   — no candidates returned or zero scored candidates
  ambiguous  — multiple candidates with non-trivial scores
  error      — network / HTTP / parse failure
  deferred   — AION query lacks the minimum identity to search
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Iterable, Optional

import httpx

from app.core.config import settings
from app.enrichment import (
    EnrichmentQuery,
    EnrichmentResult,
    EnrichmentSource,  # noqa: F401 — protocol referenced by docstring
    normalize_bpm,
    normalize_key,  # noqa: F401 — exposed for future compatibility
)
from app.enrichment.matching import (
    artist_names_match,
    duration_close,
    has_preserved_version_marker,
    normalize_title_for_match,
    title_similarity,
    version_tokens,
)

log = logging.getLogger(__name__)


# --- thresholds ---------------------------------------------------------------
# These constants encode the "reasonably strict acceptance threshold" called
# out in the M4B brief. They are deliberately module-level (not env vars) so
# tests can import them directly.

ACCEPT_SCORE: float = 0.80
AMBIGUOUS_GAP: float = 0.08       # second-best must be at least this far below best
TITLE_MIN_JACCARD: float = 0.55    # title alone is rarely sufficient
ARTIST_REQUIRED: bool = True       # at least one AION artist must overlap
VERSION_TOKEN_MISMATCH_PENALTY: float = 0.20  # applied if AION has a version marker that candidate does not
DEFAULT_SEARCH_LIMIT: int = 10
MAX_SEARCH_LIMIT: int = 30

# --- error taxonomy ----------------------------------------------------------

class GetSongBPMError(Exception):
    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GetSongBPMAuthError(GetSongBPMError):
    pass


class GetSongBPMRateLimitError(GetSongBPMError):
    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message, status_code=status_code)
        self.retry_after = retry_after


class GetSongBPMNotFoundError(GetSongBPMError):
    pass


# --- key normalization (provider-specific) ----------------------------------

# GetSongBPM returns ``key_of`` like "F\u266fm" / "C#m" / "Bb major". We map
# these to our canonical "Tonic mode" form.

SHARP_TO_FLAT_OVERRIDE: dict[str, str] = {
    "Db": "C#",
    "Eb": "D#",
    "Gb": "F#",
    "Ab": "G#",
    "Bb": "A#",
}

KEY_OF_RE = re.compile(
    r"^\s*(?P<tonic>[A-Ga-g][#b]?)\s*(?P<mode>m|min|minor|maj|major|mj)?\s*$",
    re.IGNORECASE,
)


def _parse_key_of(value: Any) -> tuple[Optional[str], Optional[str]]:
    """Return (normalized_tonic, normalized_mode) or (None, None) on failure.

    Examples:
        "F#m"  -> ("F#", "minor")
        "C"    -> ("C",  None)
        "Bb major" -> ("A#", "major")
    """
    if value is None:
        return None, None
    s = str(value).strip()
    if not s:
        return None, None
    m = KEY_OF_RE.match(s)
    if not m:
        return None, None
    tonic_raw = m.group("tonic")
    mode_raw = (m.group("mode") or "").lower()
    # Normalize mode token.
    if mode_raw in ("m", "min", "minor"):
        mode = "minor"
    elif mode_raw in ("maj", "major", "mj"):
        mode = "major"
    else:
        mode = None
    # Upper-case first letter.
    tonic_clean = tonic_raw[0].upper() + tonic_raw[1:]
    # Convert flats to sharps to match our internal PITCH_CLASSES.
    tonic_canon = SHARP_TO_FLAT_OVERRIDE.get(tonic_clean, tonic_clean)
    return tonic_canon, mode


def normalize_getsongbpm_key(key_of: Any) -> Optional[str]:
    tonic, mode = _parse_key_of(key_of)
    if not tonic:
        return None
    if mode:
        return f"{tonic} {mode}"
    return tonic


# --- candidate scoring -------------------------------------------------------

def _score_candidate(
    *,
    aion_title: str | None,
    aion_artists: Iterable[str],
    aion_duration_ms: int | None,
    candidate: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    """Score a single GetSongBPM search-result candidate against the AION query.

    Returns (score, evidence). Score is in [0, 1]. Higher is better.
    """
    cand_title = (
        candidate.get("song_title")
        or candidate.get("title")
        or candidate.get("song_uri")
    )
    cand_artist_list: list[str] = []
    cand_artist = candidate.get("artist")
    if isinstance(cand_artist, dict):
        name = cand_artist.get("name")
        if name:
            cand_artist_list.append(name)
    elif isinstance(cand_artist, list):
        for a in cand_artist:
            if isinstance(a, dict):
                name = a.get("name")
                if name:
                    cand_artist_list.append(name)
            elif isinstance(a, str):
                cand_artist_list.append(a)
    elif isinstance(cand_artist, str):
        cand_artist_list.append(cand_artist)

    title_score = title_similarity(aion_title, cand_title)
    artists_ok, artist_score = artist_names_match(aion_artists, cand_artist_list)

    cand_duration_ms: Optional[int] = None
    if isinstance(candidate.get("duration"), (int, float, str)):
        try:
            cand_duration_ms = int(float(candidate.get("duration")))
        except (ValueError, TypeError):
            cand_duration_ms = None

    duration_ok = duration_close(aion_duration_ms, cand_duration_ms)

    score = 0.0
    score += 0.55 * title_score
    score += 0.40 * artist_score

    aion_version_markers = version_tokens(aion_title)
    cand_version_markers = version_tokens(cand_title)
    version_ok = True
    # If AION has a version marker, the candidate must agree exactly.
    if aion_version_markers and aion_version_markers != cand_version_markers:
        # AION specifies a remix/edit/version label and the candidate does
        # not match. This is dangerous: "Acid Trip" must NOT match
        # "Acid Trip - Out of Orbit & Sasi Remix".
        score -= VERSION_TOKEN_MISMATCH_PENALTY
        version_ok = False
    # If AION has NO version marker but the candidate has one (e.g. the
    # candidate is a Remix, Edit, Live, ... version), we must also refuse.
    if not aion_version_markers and cand_version_markers:
        score -= VERSION_TOKEN_MISMATCH_PENALTY
        version_ok = False

    if not duration_ok:
        # Only penalize if both sides actually have a duration.
        if aion_duration_ms is not None and cand_duration_ms is not None:
            score -= 0.10

    # Bound.
    score = max(0.0, min(1.0, score))

    evidence = {
        "title_score": round(title_score, 3),
        "artist_score": round(artist_score, 3),
        "artist_overlap_ok": artists_ok,
        "candidate_title": cand_title,
        "candidate_artists": cand_artist_list,
        "candidate_duration_ms": cand_duration_ms,
        "duration_ok": duration_ok,
        "aion_version_tokens": sorted(aion_version_markers),
        "candidate_version_tokens": sorted(cand_version_markers),
        "version_ok": version_ok,
    }
    return score, evidence


# --- main source adapter -----------------------------------------------------

class GetSongBPMEnrichmentSource:
    """Conservative text-search adapter for GetSongBPM.

    Auth: simple ``X-API-KEY`` header. The free tier requires a backlink to
    getsongbpm.com; see the M4B report and the frontend footer.
    """

    name = "getsongbpm"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        min_interval: float | None = None,
        timeout: float = 20.0,
    ) -> None:
        if not api_key:
            raise ValueError("getsongbpm api_key is required")
        self._api_key = api_key
        self._base = (base_url or settings.getsongbpm_base_url).rstrip("/")
        self._min_interval = float(
            min_interval if min_interval is not None else settings.getsongbpm_min_interval
        )
        self._timeout = timeout
        self._lock = asyncio.Lock()
        self._last_request_at: float = 0.0
        # Lightweight per-process cache. Keyed by (lookup_lower, type).
        # Value: (timestamp, raw_payload).
        self._cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
        self._cache_ttl_seconds: float = 60.0

    # -- helpers --

    def _cache_get(self, key: tuple[str, str]) -> Optional[dict[str, Any]]:
        entry = self._cache.get(key)
        if not entry:
            return None
        ts, payload = entry
        if (time.monotonic() - ts) > self._cache_ttl_seconds:
            self._cache.pop(key, None)
            return None
        return payload

    def _cache_put(self, key: tuple[str, str], payload: dict[str, Any]) -> None:
        self._cache[key] = (time.monotonic(), payload)

    async def _pace(self) -> None:
        # Single-flight pacing per source instance.
        async with self._lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = time.monotonic()

    async def _get(
        self,
        path: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        url = f"{self._base}{path}"
        await self._pace()
        headers = {
            "X-API-KEY": self._api_key,
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout, connect=10.0)
            ) as client:
                resp = await client.get(url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            raise GetSongBPMError(f"timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise GetSongBPMError(str(exc)) from exc

        if resp.status_code == 401 or resp.status_code == 403:
            raise GetSongBPMAuthError(
                f"getsongbpm auth failed (HTTP {resp.status_code})", status_code=resp.status_code
            )
        if resp.status_code == 429:
            retry_after: Optional[float] = None
            h = resp.headers.get("Retry-After")
            if h is not None:
                try:
                    retry_after = float(h)
                except (ValueError, TypeError):
                    retry_after = None
            raise GetSongBPMRateLimitError(
                "rate limited", status_code=429, retry_after=retry_after
            )
        if resp.status_code == 404:
            raise GetSongBPMNotFoundError("not found", status_code=404)
        if resp.status_code >= 500:
            raise GetSongBPMError(
                f"server error {resp.status_code}", status_code=resp.status_code
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise GetSongBPMError("invalid json") from exc
        if not isinstance(data, dict):
            raise GetSongBPMError("non-dict response")
        return data

    # -- public API --

    async def lookup(self, query: EnrichmentQuery) -> EnrichmentResult:
        aion_title = (query.title or "").strip()
        if not aion_title:
            return EnrichmentResult(
                source=self.name,
                status="deferred",
                error="missing AION title; cannot text-search",
            )

        # Use primary artist only as part of the lookup string to widen the
        # search when title alone is too generic. The provider's "song"
        # search is the most precise type, so prefer it.
        primary_artist = ""
        if query.artists:
            primary_artist = (query.artists[0] or "").strip()
        lookup_str = aion_title if not primary_artist else f"{aion_title} {primary_artist}"

        # Lookup keys are normalized to maximize cache hit rate.
        cache_key = (
            normalize_title_for_match(lookup_str),
            "song",
        )
        payload = self._cache_get(cache_key)
        from_cache = payload is not None
        if payload is None:
            try:
                payload = await self._get(
                    "/search/",
                    {
                        "type": "song",
                        "lookup": lookup_str,
                        "limit": DEFAULT_SEARCH_LIMIT,
                    },
                )
            except GetSongBPMRateLimitError as exc:
                return EnrichmentResult(
                    source=self.name,
                    status="error",
                    error=f"rate limited (retry_after={exc.retry_after})",
                    error_type="rate_limit",
                    http_status=exc.status_code,
                    match_evidence={"retry_after": exc.retry_after},
                )
            except GetSongBPMAuthError as exc:
                return EnrichmentResult(
                    source=self.name,
                    status="error",
                    error=str(exc),
                    error_type="authentication",
                    http_status=exc.status_code,
                )
            except GetSongBPMError as exc:
                return EnrichmentResult(
                    source=self.name,
                    status="error",
                    error=str(exc),
                    error_type="provider_failure",
                    http_status=exc.status_code,
                )
            self._cache_put(cache_key, payload)

        # The /search/ endpoint nests results under "search" for type=song.
        candidates = payload.get("search")
        if isinstance(candidates, dict) and "error" in candidates:
            return EnrichmentResult(
                source=self.name,
                status="error",
                error=str(candidates.get("error")),
                error_type="provider_error",
                http_status=200,
            )
        if not isinstance(candidates, list) or not candidates:
            return EnrichmentResult(
                source=self.name,
                status="no_match",
                source_identifier=None,
                match_evidence={
                    "lookup": lookup_str,
                    "candidate_count": 0,
                    "from_cache": from_cache,
                },
            )

        scored: list[dict[str, Any]] = []
        for c in candidates:
            if not isinstance(c, dict):
                continue
            score, evidence = _score_candidate(
                aion_title=aion_title,
                aion_artists=query.artists or [],
                aion_duration_ms=query.duration_ms,
                candidate=c,
            )
            scored.append({"score": score, "evidence": evidence, "raw": c})

        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[0]
        second = scored[1] if len(scored) > 1 else None

        candidate_count = len(scored)
        evidence = {
            "lookup": lookup_str,
            "candidate_count": candidate_count,
            "from_cache": from_cache,
            "top_score": round(top["score"], 3),
            "second_score": round(second["score"], 3) if second else None,
            "top_evidence": top["evidence"],
        }

        # Acceptance gates (strict):
        title_ok = top["evidence"]["title_score"] >= TITLE_MIN_JACCARD
        artist_ok = (
            top["evidence"]["artist_score"] > 0
            if ARTIST_REQUIRED
            else True
        )
        version_ok = top["evidence"]["version_ok"]
        duration_ok = top["evidence"]["duration_ok"]

        accepted = (
            top["score"] >= ACCEPT_SCORE
            and title_ok
            and artist_ok
            and version_ok
        )
        # If duration was actually compared and failed, refuse.
        if (
            query.duration_ms is not None
            and top["evidence"]["candidate_duration_ms"] is not None
            and not duration_ok
        ):
            accepted = False

        # Ambiguity gate: another candidate close to the top score.
        ambiguous = (
            second is not None
            and second["score"] > 0
            and (top["score"] - second["score"]) < AMBIGUOUS_GAP
            and second["score"] >= ACCEPT_SCORE * 0.75
        )

        if ambiguous and accepted:
            # Two strong candidates — refuse to guess.
            return EnrichmentResult(
                source=self.name,
                status="ambiguous",
                match_evidence={
                    **evidence,
                    "second_evidence": second["evidence"],
                    "match_method": "title+artist",
                    "match_score": round(top["score"], 3),
                },
            )

        if not accepted:
            if top["score"] >= ACCEPT_SCORE * 0.6 and (
                top["evidence"]["title_score"] >= TITLE_MIN_JACCARD
                or top["evidence"]["artist_score"] > 0
            ):
                return EnrichmentResult(
                    source=self.name,
                    status="ambiguous",
                    match_evidence={
                        **evidence,
                        "match_method": "title+artist",
                        "match_score": round(top["score"], 3),
                    },
                )
            return EnrichmentResult(
                source=self.name,
                status="no_match",
                match_evidence={
                    **evidence,
                    "match_method": "title+artist",
                    "match_score": round(top["score"], 3),
                },
            )

        # Accepted — fetch full /song/ detail to get a clean BPM/key payload.
        song_id = top["raw"].get("song_id") or top["raw"].get("id")
        detail = await self._fetch_detail(song_id) if song_id else None

        tempo = None
        key_norm = None
        raw_song = top["raw"]
        if detail is not None:
            raw_song = detail
            tempo_raw = detail.get("tempo")
            key_raw = detail.get("key_of")
            tempo = normalize_bpm(tempo_raw)
            key_norm = normalize_getsongbpm_key(key_raw)
        else:
            # Fall back to the search-result fields. They often already
            # include tempo/key_of, but the structure can vary; trust them
            # only when /song/ detail is unavailable.
            tempo = normalize_bpm(top["raw"].get("tempo"))
            key_norm = normalize_getsongbpm_key(top["raw"].get("key_of"))

        # If /song/ returned values that look implausible, accept whatever the
        # search result had instead.
        if tempo is None:
            tempo = normalize_bpm(top["raw"].get("tempo"))
        if key_norm is None:
            key_norm = normalize_getsongbpm_key(top["raw"].get("key_of"))

        return EnrichmentResult(
            source=self.name,
            status="matched",
            tempo_bpm=tempo,
            musical_key=key_norm,
            confidence=round(top["score"], 3),
            source_identifier=str(song_id) if song_id else None,
            match_evidence={
                **evidence,
                "match_method": "title+artist",
                "match_score": round(top["score"], 3),
            },
            raw=raw_song,
        )

    async def _fetch_detail(self, song_id: str) -> Optional[dict[str, Any]]:
        cache_key = (f"song:{song_id}", "detail")
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            payload = await self._get("/song/", {"id": song_id})
        except GetSongBPMNotFoundError:
            return None
        except GetSongBPMError as exc:
            log.warning(
                "getsongbpm detail lookup failed song_id=%s err=%s", song_id, exc
            )
            return None
        song = payload.get("song") if isinstance(payload, dict) else None
        if not isinstance(song, dict):
            return None
        self._cache_put(cache_key, song)
        return song