"""Regression tests for SQLite path and .env loading robustness."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from app.core.config import Settings, _normalize_sqlite_url, _API_DIR, _PROJECT_ROOT
from app.db import _ensure_sqlite_directory


def test_normalize_relative_sqlite_url_resolves_to_project_root():
    url = _normalize_sqlite_url("sqlite:///./data/aion.db")
    assert url.startswith("sqlite:///")
    # Should be absolute and anchored to _PROJECT_ROOT
    expected = (_PROJECT_ROOT / "data" / "aion.db").resolve().as_posix()
    assert url == f"sqlite:///{expected}"


def test_normalize_relative_without_dot():
    url = _normalize_sqlite_url("sqlite:///data/aion.db")
    expected = (_PROJECT_ROOT / "data" / "aion.db").resolve().as_posix()
    assert url == f"sqlite:///{expected}"


def test_normalize_absolute_sqlite_url_unchanged():
    # Unix absolute (4 slashes → file_part starts with /)
    url = "sqlite:////tmp/aion.db"
    assert _normalize_sqlite_url(url) == url
    # Windows-style absolute — Path.is_absolute() returns True
    abs_path = (_PROJECT_ROOT / "data" / "aion.db").resolve().as_posix()
    url2 = f"sqlite:///{abs_path}"
    assert _normalize_sqlite_url(url2) == url2


def test_normalize_memory_url_unchanged():
    assert _normalize_sqlite_url("sqlite:///:memory:") == "sqlite:///:memory:"
    assert _normalize_sqlite_url("sqlite:///") == "sqlite:///"


def test_normalize_preserves_query_string():
    url = _normalize_sqlite_url("sqlite:///./data/aion.db?mode=ro")
    assert url.endswith("?mode=ro")
    assert "data/aion.db" in url


def test_normalize_postgres_untouched():
    pg = "postgresql://user:pass@localhost:5432/aion"
    assert _normalize_sqlite_url(pg) == pg


def test_settings_validator_normalizes_relative():
    s = Settings(database_url="sqlite:///./data/aion.db", _env_file=None)
    assert s.database_url.startswith("sqlite:///")
    # db_path should be absolute and parent should be project root data dir
    assert s.db_path.is_absolute()
    assert s.db_path == (_PROJECT_ROOT / "data" / "aion.db").resolve()


def test_settings_db_path_for_absolute():
    # When an absolute path is given, db_path should reflect it exactly
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    try:
        url = f"sqlite:///{tmp.name}"
        s = Settings(database_url=url, _env_file=None)
        assert s.db_path == Path(tmp.name)
        assert s.database_url == url
    finally:
        os.unlink(tmp.name)


def test_settings_env_file_points_to_known_locations():
    # model_config env_file must contain absolute paths to both root and api .env
    env_files = Settings.model_config.get("env_file")
    assert env_files is not None
    # Normalize to tuple/list
    files = list(env_files) if isinstance(env_files, (list, tuple)) else [env_files]
    # Both should be absolute
    for f in files:
        assert Path(f).is_absolute(), f"env_file {f} should be absolute"
    # Root .env should be present
    assert str(_PROJECT_ROOT / ".env") in files
    assert str(_API_DIR / ".env") in files


def test_ensure_sqlite_directory_creates_parent():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "nested" / "deep" / "aion.db"
        url = f"sqlite:///{db_path.as_posix()}"
        assert not db_path.parent.exists()
        _ensure_sqlite_directory(url)
        assert db_path.parent.exists()
        assert db_path.parent.is_dir()


def test_ensure_sqlite_directory_noop_for_memory():
    # Should not raise and not create anything
    _ensure_sqlite_directory("sqlite:///:memory:")
    _ensure_sqlite_directory("sqlite:///")


def test_ensure_sqlite_directory_noop_for_postgres():
    _ensure_sqlite_directory("postgresql://user:pass@localhost/db")


def test_consistent_path_resolution_independent_of_cwd():
    # _normalize should give same result regardless of cwd
    url_relative = "sqlite:///./data/aion.db"
    expected = (_PROJECT_ROOT / "data" / "aion.db").resolve().as_posix()
    orig_cwd = os.getcwd()
    try:
        os.chdir(tempfile.gettempdir())
        assert _normalize_sqlite_url(url_relative) == f"sqlite:///{expected}"
        os.chdir(_PROJECT_ROOT)
        assert _normalize_sqlite_url(url_relative) == f"sqlite:///{expected}"
    finally:
        os.chdir(orig_cwd)


def test_ensure_directory_via_build_engine(tmp_path, monkeypatch):
    """Integration: _ensure_sqlite_directory + get_engine() creates the parent dir."""
    from app.db import _ensure_sqlite_directory

    # Use a fresh temp DB path nested two levels deep that doesn't exist yet
    nested_db = tmp_path / "a" / "b" / "test_build.db"
    url = f"sqlite:///{nested_db.as_posix()}"
    assert not nested_db.parent.exists()
    # Simulate what _build_engine does
    _ensure_sqlite_directory(url)
    assert nested_db.parent.exists()
    # Also verify we can actually create an engine/file there
    from sqlalchemy import create_engine, text

    eng = create_engine(url, future=True)
    with eng.connect() as conn:
        conn.execute(text("SELECT 1"))
    eng.dispose()
    assert nested_db.parent.exists()
