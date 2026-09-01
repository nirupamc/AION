"""Regression tests for the import short-circuit and endpoint error mapping.

These tests pin the behavior that prevents the POST /import/liked-songs
endpoint from hanging past the proxy timeout on a re-run: when the local
DB is already in sync with the provider (same total and same most-recent
saved_at), the import must short-circuit without paginating all of
Spotify. They also pin the 401/403/429 status mapping for provider errors
so true failures are not collapsed into a silent 500.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import MusicAccount, OAuthToken, ProviderTrack
from app.tracks import (
    ImportStats,
    count_local_provider_tracks,
    import_provider_tracks,
    latest_local_saved_at,
)
from app.providers.base.models import (
    ArtistRef,
    ProviderAlbumRef,
    ProviderTrack as IncomingProviderTrack,
)
from app.providers.spotify import oauth


def _incoming(spotify_id: str, *, isrc: str | None = None,
              saved_at: datetime | None = None) -> IncomingProviderTrack:
    return IncomingProviderTrack(
        provider="spotify",
        provider_track_id=spotify_id,
        title=f"Track {spotify_id}",
        artists=[ArtistRef(provider_artist_id="a1", name="Artist")],
        album=ProviderAlbumRef(provider_album_id="al1", name="Album", image_url=None),
        duration_ms=200000,
        isrc=isrc,
        provider_uri=f"spotify:track:{spotify_id}",
        provider_url=f"https://open.spotify.com/track/{spotify_id}",
        saved_at=saved_at,
    )


def test_import_stats_includes_short_circuit_fields():
    s = ImportStats(remote_total=10, local_total=10, short_circuited=True)
    d = s.as_dict()
    assert d["short_circuited"] is True
    assert d["remote_total"] == 10
    assert d["local_total"] == 10
    assert d["pages_fetched"] == 0


def test_count_and_latest_local_provider_tracks(session):
    import_provider_tracks(session, [
        _incoming("t1", isrc="I1", saved_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        _incoming("t2", isrc="I2", saved_at=datetime(2026, 6, 1, tzinfo=timezone.utc)),
    ])
    session.commit()
    assert count_local_provider_tracks(session, provider="spotify") == 2
    latest = latest_local_saved_at(session, provider="spotify")
    assert latest is not None
    # SQLite strips tzinfo, so we compare the naive UTC equivalent.
    from datetime import timezone as _tz
    assert latest.replace(tzinfo=_tz.utc) == datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_endpoint_short_circuits_when_in_sync(session, monkeypatch):
    """A re-run where local matches remote must NOT paginate Spotify."""
    # Seed: account + token + 2 provider tracks with known saved_at.
    acct = MusicAccount(
        provider="spotify",
        provider_user_id="test-user",
        display_name="Test",
        is_active=True,
    )
    session.add(acct)
    session.flush()
    session.add(OAuthToken(
        account_id=acct.id,
        access_token="fake-access-token",
        refresh_token="fake-refresh",
        token_type="Bearer",
        scope="user-library-read",
    ))
    # The most recent saved_at on the local side.
    latest = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)
    import_provider_tracks(session, [
        _incoming("t1", isrc="I1", saved_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        _incoming("t2", isrc="I2", saved_at=latest),
    ])
    session.commit()

    # Stub the Spotify provider so we can observe whether the expensive
    # iter_saved_tracks path was called.
    from app.api import import_liked_songs as _endpoint_module  # noqa

    class _StubProvider:
        def __init__(self, *args, **kwargs):
            self.iter_called = False

        async def peek_saved_tracks(self):
            return 2, latest

        async def iter_saved_tracks(self, *, limit: int = 50):
            self.iter_called = True
            if False:
                yield  # pragma: no cover

        async def aclose(self):
            pass

    stub = _StubProvider()

    def _factory(*args, **kwargs):
        return stub

    monkeypatch.setattr("app.api.SpotifyProvider", _factory)

    client = TestClient(app)
    r = client.post(
        "/import/liked-songs",
        params={"provider_user_id": "test-user"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["short_circuited"] is True
    assert body["remote_total"] == 2
    assert body["local_total"] == 2
    assert body["fetched"] == 0
    assert body["pages_fetched"] == 0
    assert stub.iter_called is False, "iter_saved_tracks must not run on short-circuit"


def test_endpoint_maps_provider_auth_error_to_401(session, monkeypatch):
    from app.providers.base.errors import ProviderAuthenticationError

    acct = MusicAccount(
        provider="spotify", provider_user_id="u2", display_name="U2", is_active=True,
    )
    session.add(acct)
    session.flush()
    session.add(OAuthToken(
        account_id=acct.id, access_token="x", token_type="Bearer", scope="user-library-read",
        refresh_token="bad-refresh",
    ))
    session.commit()

    class _BadProvider:
        async def peek_saved_tracks(self):
            raise ProviderAuthenticationError("token expired")

        async def iter_saved_tracks(self, *, limit: int = 50):
            if False:
                yield

        async def aclose(self):
            pass

    async def _bad_refresh(*, refresh_token: str):
        raise oauth.SpotifyOAuthError("refresh token invalid")

    monkeypatch.setattr("app.api.SpotifyProvider", lambda *a, **k: _BadProvider())
    monkeypatch.setattr("app.api.oauth.refresh_tokens", _bad_refresh)

    client = TestClient(app)
    r = client.post("/import/liked-songs", params={"provider_user_id": "u2"})
    assert r.status_code == 401, r.text
    assert "Reconnect Spotify" in r.text


def test_endpoint_maps_rate_limit_to_429(session, monkeypatch):
    from app.providers.base.errors import ProviderRateLimitError

    acct = MusicAccount(
        provider="spotify", provider_user_id="u3", display_name="U3", is_active=True,
    )
    session.add(acct)
    session.flush()
    session.add(OAuthToken(
        account_id=acct.id, access_token="x", token_type="Bearer", scope="user-library-read",
    ))
    session.commit()

    class _RateLimited:
        async def peek_saved_tracks(self):
            raise ProviderRateLimitError("slow down", retry_after=2.0)

        async def iter_saved_tracks(self, *, limit: int = 50):
            if False:
                yield

        async def aclose(self):
            pass

    monkeypatch.setattr("app.api.SpotifyProvider", lambda *a, **k: _RateLimited())

    client = TestClient(app)
    r = client.post("/import/liked-songs", params={"provider_user_id": "u3"})
    assert r.status_code == 429, r.text
    assert r.headers.get("retry-after") == "2"


def test_sensitive_log_filter_redacts_oauth_secrets(caplog):
    from app.core.logging import SensitiveDataFilter

    flt = SensitiveDataFilter()
    rec = logging.LogRecord(
        name="t", level=logging.INFO, pathname=__file__, lineno=0,
        msg="token exchange access_token=ABCDEF code_verifier=XYZ", args=(), exc_info=None,
    )
    import logging as _lg
    assert flt.filter(rec) is False

    rec_ok = logging.LogRecord(
        name="t", level=logging.INFO, pathname=__file__, lineno=0,
        msg="import_liked_songs completed provider_user_id=abc", args=(), exc_info=None,
    )
    assert flt.filter(rec_ok) is True


def test_endpoint_refreshes_token_on_401_and_retries(session, monkeypatch):
    from app.providers.base.errors import ProviderAuthenticationError

    acct = MusicAccount(
        provider="spotify", provider_user_id="u-refresh", display_name="URefresh", is_active=True,
    )
    session.add(acct)
    session.flush()
    token_row = OAuthToken(
        account_id=acct.id, access_token="old-token", token_type="Bearer", scope="user-library-read",
        refresh_token="valid-refresh",
    )
    session.add(token_row)
    session.commit()

    class _FailingThenGoodProvider:
        calls = 0

        async def peek_saved_tracks(self):
            _FailingThenGoodProvider.calls += 1
            if _FailingThenGoodProvider.calls == 1:
                raise ProviderAuthenticationError("token expired")
            return 0, None

        async def iter_saved_tracks(self, *, limit: int = 50):
            if False:
                yield

        async def aclose(self):
            pass

    async def _good_refresh(*, refresh_token: str):
        return {
            "access_token": "new-token",
            "refresh_token": "new-refresh",
            "token_type": "Bearer",
            "scope": "user-library-read",
            "expires_in": 3600,
        }

    monkeypatch.setattr("app.api.SpotifyProvider", lambda *a, **k: _FailingThenGoodProvider())
    monkeypatch.setattr("app.api.oauth.refresh_tokens", _good_refresh)

    client = TestClient(app)
    r = client.post("/import/liked-songs", params={"provider_user_id": "u-refresh"})
    assert r.status_code == 200, r.text
    assert _FailingThenGoodProvider.calls == 2

    session.refresh(token_row)
    assert token_row.access_token == "new-token"
    assert token_row.refresh_token == "new-refresh"


def test_endpoint_reauth_when_no_refresh_token(session, monkeypatch):
    from app.providers.base.errors import ProviderAuthenticationError

    acct = MusicAccount(
        provider="spotify", provider_user_id="u-norefresh", display_name="UNorefresh", is_active=True,
    )
    session.add(acct)
    session.flush()
    session.add(OAuthToken(
        account_id=acct.id, access_token="x", token_type="Bearer", scope="user-library-read",
    ))
    session.commit()

    class _BadProvider:
        async def peek_saved_tracks(self):
            raise ProviderAuthenticationError("token expired")

        async def iter_saved_tracks(self, *, limit: int = 50):
            if False:
                yield

        async def aclose(self):
            pass

    monkeypatch.setattr("app.api.SpotifyProvider", lambda *a, **k: _BadProvider())

    client = TestClient(app)
    r = client.post("/import/liked-songs", params={"provider_user_id": "u-norefresh"})
    assert r.status_code == 401, r.text
    assert "Reconnect Spotify" in r.text
