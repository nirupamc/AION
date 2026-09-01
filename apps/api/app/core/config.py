"""Application settings loaded from environment variables.

Uses pydantic-settings. Do NOT read os.environ directly elsewhere; go through
this module so behavior is consistent and testable.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Deterministic path resolution — do NOT rely on the caller's CWD.
# config.py lives at  apps/api/app/core/config.py
#   parents[2] -> apps/api
#   parents[4] -> repository root (AION/)
# ---------------------------------------------------------------------------
_API_DIR: Path = Path(__file__).resolve().parents[2]
_PROJECT_ROOT: Path = _API_DIR.parent.parent  # AION/


def _normalize_sqlite_url(url: str) -> str:
    """Convert a relative SQLite URL into an absolute, project-root-anchored URL.

    - Leaves non-SQLite URLs untouched.
    - Leaves absolute SQLite paths and in-memory URLs untouched.
    - Resolves relative paths against _PROJECT_ROOT so that
      sqlite:///./data/aion.db always means  AION/data/aion.db
      regardless of where the process was launched (AION/ or AION/apps/api/).
    """
    if not url.startswith("sqlite:///"):
        return url
    # Strip prefix and split off any query string (?cache=...).
    raw = url.removeprefix("sqlite:///")
    if raw in ("", ":memory:"):
        return url
    # Separate file part from query string, if present.
    if "?" in raw:
        file_part, query = raw.split("?", 1)
        query_suffix = "?" + query
    else:
        file_part, query_suffix = raw, ""
    # Already absolute (Unix /foo or Windows D:/foo / C:\foo) → keep as-is.
    # On Windows Path("/foo") is not considered absolute, so also check leading slash.
    if Path(file_part).is_absolute() or file_part.startswith(("/", "\\")):
        return url
    # Relative → anchor to project root.
    abs_path = (_PROJECT_ROOT / file_part).resolve()
    return f"sqlite:///{abs_path.as_posix()}{query_suffix}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Load .env from the repository root first, then apps/api/.env as
        # optional override. Absolute paths so resolution does not depend on CWD.
        # Later files override earlier ones; OS env vars still override both.
        env_file=(
            str(_PROJECT_ROOT / ".env"),
            str(_API_DIR / ".env"),
        ),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    env: str = "development"
    log_level: str = "INFO"

    database_url: str = "sqlite:///./data/aion.db"

    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    spotify_redirect_uri: str = "http://localhost:8000/auth/spotify/callback"
    spotify_scopes: str = (
        "user-read-private user-read-email playlist-read-private "
        "playlist-read-collaborative user-library-read "
        "playlist-modify-public playlist-modify-private"
    )

    oauth_state_secret: str = "change-me"

    # ---- MusicBrainz (read-only, anonymous) ----
    # No API key required for Web Service v2 reads. A meaningful User-Agent is
    # mandatory and enforced at startup.
    musicbrainz_base_url: str = "https://musicbrainz.org/ws/2"
    musicbrainz_user_agent: str = "AION/0.1 ( https://github.com/kilocode/aion )"
    # Application-side pacing: MusicBrainz asks clients to make at most ~1 call
    # per second. This is the minimum interval between requests (seconds).
    musicbrainz_min_interval: float = 1.1

    # ---- Soundcharts (commercial metadata) ----
    # M4A spike. Client credentials for the Soundcharts OAuth2 client_credentials flow.
    soundcharts_client_id: str = ""
    soundcharts_client_secret: str = ""
    soundcharts_base_url: str = "https://customer.api.soundcharts.com"
    soundcharts_token_url: str = "https://account.soundcharts.com/oauth/token"

    # ---- GetSongBPM (free metadata, BPM/key) ----
    # M4B primary. Simple API-key auth via header or query string.
    # Free tier: ~3000 req/hour. Backlink attribution REQUIRED.
    # Docs: https://getsongbpm.com/api
    getsongbpm_api_key: str = ""
    getsongbpm_base_url: str = "https://api.getsong.co"
    # Conservative pacing — well under the documented 3000/hour free limit
    # (3000/hour ~= 0.83 req/sec). 1.0s gives a comfortable margin.
    getsongbpm_min_interval: float = 1.0
    # Enrichment version tag written into TrackAttribute.analysis_version
    # for all rows created by this adapter. Bump if matching/normalization
    # logic changes.
    getsongbpm_analysis_version: str = "m4b-getsongbpm-v1"
    soundcharts_analysis_version: str = "m4c-soundcharts-v1"
    # Optional attribution override for the frontend footer.
    getsongbpm_attribution_url: str = "https://getsongbpm.com"

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        return _normalize_sqlite_url(v)

    @field_validator("spotify_scopes")
    @classmethod
    def _strip_scopes(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("musicbrainz_user_agent")
    @classmethod
    def _validate_musicbrainz_user_agent(cls, v: str) -> str:
        # MusicBrainz requires a meaningful User-Agent. Reject obviously
        # invalid / placeholder values that look like defaults or are too short.
        v = v.strip()
        if not v or len(v) < 10 or "AION" not in v.upper():
            raise ValueError(
                "MUSICBRAINZ_USER_AGENT must be a meaningful string identifying the "
                "application and contact (e.g. 'AION/0.1 ( https://example.org )')"
            )
        return v

    @field_validator("musicbrainz_min_interval")
    @classmethod
    def _validate_musicbrainz_min_interval(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("MUSICBRAINZ_MIN_INTERVAL must be a positive number")
        return v

    @field_validator("getsongbpm_min_interval")
    @classmethod
    def _validate_getsongbpm_min_interval(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("GETSONGBPM_MIN_INTERVAL must be a positive number")
        return v

    @field_validator("getsongbpm_attribution_url")
    @classmethod
    def _validate_getsongbpm_attribution_url(cls, v: str) -> str:
        v = (v or "").strip()
        if v and not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("GETSONGBPM_ATTRIBUTION_URL must start with http:// or https://")
        return v

    @property
    def getsongbpm_ready(self) -> bool:
        """True when a GetSongBPM API key is configured."""
        return bool(self.getsongbpm_api_key)

    @property
    def spotify_scope_list(self) -> List[str]:
        return [s for s in self.spotify_scopes.split(" ") if s]

    @property
    def db_path(self) -> Path:
        """Return the SQLite file path derived from database_url, if applicable."""
        if self.database_url.startswith("sqlite:///"):
            raw = self.database_url.removeprefix("sqlite:///")
            # Strip query string before creating Path
            file_part = raw.split("?", 1)[0]
            if file_part in ("", ":memory:"):
                return Path(file_part)
            return Path(file_part)
        # Non-sqlite (e.g. postgres) — return the project-root data path for diagnostics.
        return (_PROJECT_ROOT / "data" / "aion.db").resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Module-level singleton for convenience.
settings = get_settings()
