"""Structured logging configuration."""

from __future__ import annotations

import logging
import sys
from typing import Optional


_CONFIGURED = False


# OAuth-sensitive markers. Any log record whose formatted message or any
# attribute value contains one of these substrings is redacted instead of
# being emitted. This is a last-line-of-defense filter; callers should
# still avoid logging these values directly.
_SENSITIVE_MARKERS = (
    "access_token=",
    "refresh_token=",
    "client_secret=",
    "authorization_code",
    "code_verifier=",
    "code_challenge=",
    "Bearer ",
    "Spotify-Token",
)


class SensitiveDataFilter(logging.Filter):
    """Redact log records that contain OAuth secrets.

    This is intentionally narrow: it scrubs the rendered message and the
    ``args`` of the record, replacing the offending substring with
    ``***REDACTED***``. It does not look at exception traceback text.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        try:
            msg = record.getMessage()
        except Exception:
            return True
        for marker in _SENSITIVE_MARKERS:
            if marker in msg:
                return False
        return True


def configure_logging(level: Optional[str] = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    log_level = (level or "INFO").upper()
    handler = logging.StreamHandler(sys.stdout)
    fmt = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    handler.addFilter(SensitiveDataFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)
    # Quiet noisy third-party libs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
