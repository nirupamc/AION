"""Shared pytest fixtures."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest

# Use a temporary DB before importing the app modules.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["SPOTIFY_CLIENT_ID"] = "test-client-id"
os.environ["SPOTIFY_CLIENT_SECRET"] = "test-client-secret"
os.environ["SPOTIFY_REDIRECT_URI"] = "http://localhost:8000/auth/spotify/callback"
os.environ["OAUTH_STATE_SECRET"] = "test-state-secret"

from app.db import Base, get_engine, reset_engine_for_tests  # noqa: E402
from app.db import get_session_factory  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db() -> Iterator[None]:
    reset_engine_for_tests()
    eng = get_engine()
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield
    Base.metadata.drop_all(eng)


@pytest.fixture
def session():
    Session = get_session_factory()
    s = Session()
    try:
        yield s
    finally:
        s.close()
