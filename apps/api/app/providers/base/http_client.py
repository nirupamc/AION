"""Shared HTTP client for provider adapters.

This keeps a single httpx.AsyncClient with sane timeouts and headers, and
centralizes retry/429 handling so every provider benefits.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping, Optional

import httpx

from app.providers.base.errors import (
    ProviderAuthenticationError,
    ProviderNotFoundError,
    ProviderPermissionError,
    ProviderRateLimitError,
)

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
USER_AGENT = "AION/0.1 (+https://example.invalid)"


class HttpClient:
    """Thin async HTTP wrapper that translates transport errors to provider errors."""

    def __init__(self, base_url: str, *, timeout: httpx.Timeout = DEFAULT_TIMEOUT) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    @property
    def raw(self) -> httpx.AsyncClient:
        return self._client

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        json: Any = None,
        auth: Optional[tuple[str, str]] = None,
        max_retries: int = 3,
    ) -> httpx.Response:
        attempt = 0
        while True:
            try:
                resp = await self._client.request(
                    method,
                    path,
                    params=params,
                    headers=headers,
                    json=json,
                    auth=auth,
                )
            except httpx.TimeoutException as exc:
                if attempt >= max_retries:
                    raise ProviderRateLimitError(
                        f"timeout after {attempt + 1} attempts: {exc}"
                    ) from exc
                attempt += 1
                await asyncio.sleep(0.5 * attempt)
                continue

            if resp.status_code == 429:
                if attempt >= max_retries:
                    retry_after = _retry_after_seconds(resp)
                    raise ProviderRateLimitError(
                        "rate limited",
                        retry_after=retry_after,
                        details={"status": 429, "url": str(resp.url)},
                    )
                attempt += 1
                sleep_s = _retry_after_seconds(resp) or (0.5 * attempt)
                log.warning("rate_limited sleeping=%.2fs attempt=%d", sleep_s, attempt)
                await asyncio.sleep(sleep_s)
                continue

            if resp.status_code == 401:
                raise ProviderAuthenticationError(
                    "authentication failed",
                    details={"status": 401, "url": str(resp.url)},
                )
            if resp.status_code == 403:
                raise ProviderPermissionError(
                    "permission denied",
                    details={"status": 403, "url": str(resp.url), "body": _safe_body(resp)},
                )
            if resp.status_code == 404:
                raise ProviderNotFoundError(
                    "not found",
                    details={"status": 404, "url": str(resp.url)},
                )
            if resp.status_code >= 500:
                if attempt < max_retries:
                    attempt += 1
                    await asyncio.sleep(0.5 * attempt)
                    continue
                raise ProviderRateLimitError(
                    f"server error {resp.status_code}",
                    details={"status": resp.status_code, "url": str(resp.url)},
                )

            return resp


def _retry_after_seconds(resp: httpx.Response) -> Optional[float]:
    h = resp.headers.get("Retry-After")
    if h is None:
        return None
    try:
        return float(h)
    except ValueError:
        return None


def _safe_body(resp: httpx.Response) -> str:
    try:
        return resp.text[:500]
    except Exception:
        return ""
