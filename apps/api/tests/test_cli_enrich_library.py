"""Regression test for M4B production-enrichment CLI crash.

Ensures cmd_enrich_library can construct EnrichmentQuery without NameError
(https://github.com/kilocode/aion — M4B milestone).
"""
from __future__ import annotations

import argparse
import asyncio

from app import cli
from app.enrichment import EnrichmentQuery
from app.models import ProviderTrack, Track


def test_enrichment_query_imported_in_cli():
    # EnrichmentQuery must be importable from its canonical module and
    # also bound in app.cli (no duplicate definition).
    assert hasattr(cli, "EnrichmentQuery")
    assert cli.EnrichmentQuery is EnrichmentQuery


def test_cmd_enrich_library_dry_run_does_not_raise_name_error(session, monkeypatch):
    # Seed one track + provider track so enrich-library has something to query.
    track = Track(canonical_title="Test Song")
    session.add(track)
    session.flush()
    pt = ProviderTrack(
        track_id=track.id,
        provider="spotify",
        provider_track_id="sp-test-1",
        raw_title="Test Song",
        artist_display="Test Artist",
        duration_ms=210000,
        raw_metadata='{"artists": [{"name": "Test Artist"}]}',
    )
    session.add(pt)
    session.commit()

    # Mock DB factory: return the test session, with close as no-op so fixture teardown still works
    class _NoopSession:
        def __init__(self, s):
            self._s = s
        def __getattr__(self, name):
            return getattr(self._s, name)
        def close(self):
            pass

    noop = _NoopSession(session)
    monkeypatch.setattr(cli, "get_session_factory", lambda: lambda: noop)
    # getsongbpm_ready is a property derived from getsongbpm_api_key; set the key instead
    monkeypatch.setattr(cli.settings, "getsongbpm_api_key", "fake-key-for-test", raising=False)

    args = argparse.Namespace(source="getsongbpm", limit=5, force=False, dry_run=True)

    # Should not raise NameError: name 'EnrichmentQuery' is not defined
    asyncio.run(cli.cmd_enrich_library(args))

    # Direct construction parity check
    q = EnrichmentQuery(track_id=track.id, title="Test Song", artists=["Test Artist"], duration_ms=210000)
    assert q.title == "Test Song"
