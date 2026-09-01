"""MusicBrainz provider: read-only ISRC → Recording identity resolution.

Uses MusicBrainz Web Service v2. No API key is required; a meaningful
User-Agent is mandatory. Requests are paced to respect ~1 req/sec.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.providers.base.errors import ProviderError, ProviderRateLimitError

log = logging.getLogger(__name__)

MUSICBRAINZ_BASE_URL_DEFAULT = "https://musicbrainz.org/ws/2"


@dataclass(frozen=True)
class MBRecording:
    """Normalized MusicBrainz recording entity."""

    mbid: str
    title: str
    length_ms: Optional[int] = None
    artist_credit: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IsrcLookupResult:
    """Outcome of an ISRC lookup."""

    isrc: str
    recordings: list[MBRecording]
    raw_count: int = 0


class MusicBrainzClient:
    """Thin async MusicBrainz Web Service v2 client with application-side pacing."""

    def __init__(
        self,
        base_url: str = "",
        user_agent: str = "",
        min_interval: float = 1.1,
        timeout: float = 20.0,
    ) -> None:
        self._base = (base_url or settings.musicbrainz_base_url or MUSICBRAINZ_BASE_URL_DEFAULT).rstrip("/")
        self._user_agent = user_agent or settings.musicbrainz_user_agent
        self._min_interval = float(min_interval or settings.musicbrainz_min_interval or 1.1)
        self._timeout = httpx.Timeout(timeout, connect=10.0)
        self._client = httpx.AsyncClient(
            base_url=self._base,
            timeout=self._timeout,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "application/json",
            },
        )
        self._lock = asyncio.Lock()
        self._last_request_ts: float = 0.0

    async def aclose(self) -> None:
        await self._client.aclose()

    async def lookup_isrc(self, isrc: str) -> IsrcLookupResult:
        """Lookup recordings by ISRC.

        Returns all linked recordings (no paging). An unmatched ISRC returns
        an empty recordings list, not an HTTP error.
        """
        if not isrc or not isrc.strip():
            raise ValueError("isrc must be a non-empty string")

        isrc = isrc.strip()
        await self._pace()

        resp = await self._client.get(
            f"/isrc/{isrc}",
            params={"fmt": "json"},
        )
        text = _safe_text(resp)
        data = _safe_json(text)
        recordings_raw = (data or {}).get("recordings") or []
        recordings = [_parse_recording(r) for r in recordings_raw if isinstance(r, dict)]
        return IsrcLookupResult(
            isrc=isrc,
            recordings=recordings,
            raw_count=(data or {}).get("count") or len(recordings_raw),
        )

    async def _pace(self) -> None:
        async with self._lock:
            wait = self._last_request_ts + self._min_interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_ts = time.monotonic()


# ---- parsing helpers ----

def _safe_text(resp: httpx.Response) -> str:
    try:
        return resp.text or ""
    except Exception:
        return ""


def _safe_json(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def _parse_recording(raw: dict[str, Any]) -> MBRecording:
    rid = raw.get("id") or ""
    title = raw.get("title") or ""
    length = raw.get("length")
    try:
        length_ms = int(length) if length is not None else None
    except (ValueError, TypeError):
        length_ms = None
    artists: list[str] = []
    for ac in raw.get("artist-credit") or []:
        if isinstance(ac, dict):
            n = ac.get("name")
            if n:
                artists.append(str(n))
            j = ac.get("joinphrase") or ""
            if j and artists:
                artists[-1] = artists[-1] + j
    return MBRecording(mbid=str(rid), title=str(title), length_ms=length_ms, artist_credit=artists)
