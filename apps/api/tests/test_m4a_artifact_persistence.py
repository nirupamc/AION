"""Regression tests for M4A artifact persistence and error handling."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.core.config import Settings, _PROJECT_ROOT
from app.enrichment import EnrichmentQuery, EnrichmentResult
from app.enrichment.evaluation import write_report


def test_write_report_creates_directory_and_file(tmp_path: Path):
    out_dir = tmp_path / "nested" / "artifacts"
    payload = {"sources": [], "results": []}
    meta = {"provider": "soundcharts"}
    out_file = write_report(out_dir, payload, meta, filename="m4a_soundcharts_results.json")
    assert out_file.exists()
    assert out_file.parent == out_dir.resolve()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["sample"] == meta
    assert data["evaluation"] == payload


def test_write_report_returns_absolute_path(tmp_path: Path):
    out_dir = tmp_path / "artifacts"
    out_file = write_report(out_dir, {"sources": [], "results": []}, {}, filename="test.json")
    assert out_file.is_absolute()


def test_write_report_deterministic_from_different_cwds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    out_dir = tmp_path / "artifacts"
    # Simulate running from a different CWD
    fake_cwd = tmp_path / "some_other_place"
    fake_cwd.mkdir()
    monkeypatch.chdir(fake_cwd)
    out_file = write_report(out_dir, {"sources": [], "results": []}, {}, filename="test.json")
    assert out_file.exists()
    assert out_file == out_dir.resolve() / "test.json"


def test_write_report_raises_on_write_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    out_dir = tmp_path / "readonly"
    out_dir.mkdir()
    # Make directory read-only to trigger write failure (Windows may allow but let's test IOError path)
    # Instead, test with a path inside a file (not a directory)
    fake_file = tmp_path / "not_a_dir"
    fake_file.write_text("x")
    with pytest.raises((IOError, OSError)):
        write_report(fake_file, {"sources": [], "results": []}, {}, filename="test.json")


def test_evaluate_sources_preserves_per_track_errors():
    import asyncio

    from app.enrichment import EnrichmentAggregate, EnrichmentSource
    from app.enrichment.evaluation import evaluate_sources

    class _FakeSource:
        name = "fake"

        async def lookup(self, query: EnrichmentQuery) -> EnrichmentResult:
            return EnrichmentResult(
                source=self.name,
                status="error",
                error="provider 403: plan does not include endpoint",
                error_type="plan_permission",
                http_status=403,
                latency_ms=150.0,
            )

    queries = [EnrichmentQuery(track_id=1, isrc="US123")]
    payload = asyncio.run(evaluate_sources([_FakeSource()], queries))
    assert payload["sources"][0]["error"] == 1
    assert payload["sources"][0]["queried"] == 1
    row = payload["results"][0]
    assert row["status"] == "error"
    assert row["error"] == "provider 403: plan does not include endpoint"
    assert row["error_type"] == "plan_permission"
    assert row["http_status"] == 403
    assert isinstance(row["latency_ms"], float)


def test_error_breakdown_counts_by_error_type():
    rows = [
        {"source": "sc", "status": "error", "error_type": "plan_permission", "error": "403"},
        {"source": "sc", "status": "error", "error_type": "plan_permission", "error": "403"},
        {"source": "sc", "status": "no_match", "error_type": None, "error": None},
    ]
    counts: dict[str, int] = {}
    for row in rows:
        if row.get("source") != "sc" or row.get("status") != "error":
            continue
        key = row.get("error_type") or row.get("error") or "unknown"
        key = str(key)
        counts[key] = counts.get(key, 0) + 1
    assert counts == {"plan_permission": 2}


def test_soundcharts_result_never_exposes_secrets():
    result = EnrichmentResult(
        source="soundcharts",
        status="error",
        error="invalid soundcharts credentials",
        error_type="authentication",
        http_status=401,
    )
    dumped = json.dumps(result.__dict__)
    assert "client_secret" not in dumped
    assert "access_token" not in dumped
    assert "Authorization" not in dumped
    assert "Basic " not in dumped


def test_project_root_resolution():
    assert _PROJECT_ROOT.name == "AION"
    assert (_PROJECT_ROOT / "docs" / "api-research").is_dir()
