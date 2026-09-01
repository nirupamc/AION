"""Structured error hierarchy.

All application-level errors derive from AppError. Provider-specific errors
should be caught and translated into these so the rest of the system doesn't
depend on provider JSON shapes.
"""

from __future__ import annotations

from typing import Optional


class AppError(Exception):
    """Base error for the application."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ProviderError(AppError):
    """Generic provider (Spotify, SoundCloud, etc.) failure."""

    status_code = 502
    code = "provider_error"


class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_error"


class PermissionError_(AppError):
    """Renamed to avoid shadowing the builtin; used for scope/permission issues."""

    status_code = 403
    code = "permission_error"


# Alias kept readable for callers.
PermissionError = PermissionError_


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limit"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ValidationError(AppError):
    status_code = 400
    code = "validation_error"
