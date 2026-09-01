"""Tiny in-memory store for OAuth state during the auth-code callback.

A real deployment would use Redis or a signed cookie. For M0 we keep it dead
simple: state -> (code_verifier, created_at). The store auto-expires entries
older than 10 minutes.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

_TTL_SECONDS = 600
_store: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


def put(state: str, code_verifier: str) -> None:
    with _lock:
        _purge_locked()
        _store[state] = (code_verifier, time.time())


def pop(state: str) -> Optional[str]:
    with _lock:
        _purge_locked()
        v = _store.pop(state, None)
    return v[0] if v else None


def _purge_locked() -> None:
    now = time.time()
    expired = [k for k, (_, ts) in _store.items() if now - ts > _TTL_SECONDS]
    for k in expired:
        _store.pop(k, None)


def size() -> int:
    with _lock:
        _purge_locked()
        return len(_store)
