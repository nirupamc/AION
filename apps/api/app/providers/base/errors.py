"""Provider-layer error hierarchy.

Providers must translate transport-level errors (HTTP 401/403/404/429, JSON
parse failures, etc.) into one of these so the rest of the system does not
depend on provider-specific error shapes.
"""

from __future__ import annotations

from typing import Any, Optional


class ProviderError(Exception):
    """Base error raised by a provider adapter."""

    def __init__(self, message: str, *, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ProviderAuthenticationError(ProviderError):
    """The provider rejected our credentials (bad/expired token, etc.)."""


class ProviderReauthRequiredError(ProviderError):
    """The stored credentials are invalid/expired and the user must re-authenticate."""


class ProviderPermissionError(ProviderError):
    """The credentials are valid but lack required scopes/permissions."""


class ProviderRateLimitError(ProviderError):
    """We are being rate-limited; details may include retry_after seconds."""

    def __init__(self, message: str, *, retry_after: Optional[float] = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ProviderNotFoundError(ProviderError):
    """The requested resource does not exist or is not visible to us."""
