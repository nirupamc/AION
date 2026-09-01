// Thin client for the AION Library API (FastAPI).
// The Next.js dev server proxies /api/* to the backend, so these helpers call
// relative /api paths.

export interface MusicalAttribute {
  value: unknown;
  source: string;
  confidence: number | null;
  analysis_version?: string | null;
  observed_at?: string | null;
}

export interface TrackItem {
  track_id: number;
  provider: string;
  provider_track_id: string;
  title: string;
  artists: string[];
  album: string | null;
  artwork_url: string | null;
  duration_ms: number | null;
  release_date: string | null;
  release_year: number | null;
  isrc: string | null;
  musicbrainz_recording_id: string | null;
  provider_uri: string | null;
  provider_url: string | null;
  saved_at: string | null;
  imported_at: string | null;
  musical_attributes: {
    tempo_bpm?: MusicalAttribute | null;
    musical_key?: MusicalAttribute | null;
  };
}

export interface TracksResponse {
  items: TrackItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  sort: string;
  provider: string | null;
  has_isrc: string;
  search: string | null;
  bpm_min: number | null;
  bpm_max: number | null;
  musical_key: string | null;
}

export interface LibrarySummary {
  canonical_tracks: number;
  provider_occurrences: number;
  with_isrc: number;
  missing_isrc: number;
  providers: Array<{ provider: string; occurrences: number }>;
}

export interface StatusAccount {
  id: number;
  provider: string;
  provider_user_id: string;
  display_name: string | null;
  is_active: boolean;
}

export interface StatusResponse {
  connected_accounts: StatusAccount[];
  tracks: number;
  provider_tracks: number;
  isrc_identifiers: number;
  playlists: number;
}

export type SortKey =
  | "title_asc"
  | "title_desc"
  | "artist_asc"
  | "artist_desc"
  | "album_asc"
  | "album_desc"
  | "saved_desc"
  | "saved_asc"
  | "duration_asc"
  | "duration_desc";

export type HasIsrc = "all" | "has" | "missing";

export interface TracksQuery {
  page: number;
  pageSize: number;
  search: string;
  provider: string | null;
  hasIsrc: HasIsrc;
  sort: SortKey;
  bpmMin: number | null;
  bpmMax: number | null;
  musicalKey: string | null;
}

// Pure: build the query string for GET /api/tracks. Exported for testing.
export function buildTracksQuery(q: Partial<TracksQuery>): string {
  const params = new URLSearchParams();
  params.set("page", String(q.page ?? 1));
  params.set("page_size", String(q.pageSize ?? 50));
  if (q.search && q.search.trim()) params.set("search", q.search.trim());
  if (q.provider) params.set("provider", q.provider);
  params.set("has_isrc", q.hasIsrc ?? "all");
  params.set("sort", q.sort ?? "saved_desc");
  if (q.bpmMin != null) params.set("bpm_min", String(q.bpmMin));
  if (q.bpmMax != null) params.set("bpm_max", String(q.bpmMax));
  if (q.musicalKey && q.musicalKey.trim())
    params.set("musical_key", q.musicalKey.trim());
  return params.toString();
}

export async function fetchTracks(q: Partial<TracksQuery>): Promise<TracksResponse> {
  const res = await fetch(`/api/tracks?${buildTracksQuery(q)}`);
  if (!res.ok) {
    throw new Error(`Library request failed: ${res.status}`);
  }
  return (await res.json()) as TracksResponse;
}

export async function fetchSummary(): Promise<LibrarySummary> {
  const res = await fetch("/api/library/summary");
  if (!res.ok) throw new Error(`Summary request failed: ${res.status}`);
  return (await res.json()) as LibrarySummary;
}

export async function fetchTrackDetail(trackId: number): Promise<TrackDetailResponse> {
  const res = await fetch(`/api/tracks/${trackId}`);
  if (!res.ok) throw new Error(`Detail request failed: ${res.status}`);
  return (await res.json()) as TrackDetailResponse;
}

export async function fetchStatus(): Promise<StatusResponse> {
  const res = await fetch("/api/status");
  if (!res.ok) throw new Error(`Status request failed: ${res.status}`);
  return (await res.json()) as StatusResponse;
}

// Pure helpers (also unit-tested in scripts/contract check).

export interface TrackIdentityResolution {
  id: number;
  query_type: string;
  query_value: string;
  status: string;
  matched_identifier: string | null;
  confidence: number | null;
  metadata: any;
  resolved_at: string | null;
  resolver_version: string | null;
}

export interface TrackAttributeHistory {
  attribute_type: string;
  value: unknown;
  source_type: string;
  source_name: string;
  confidence: number | null;
  analysis_version: string | null;
  observed_at: string | null;
  is_current: boolean;
}

export interface TrackDetailResponse {
  track_id: number;
  canonical_title: string;
  duration_ms: number | null;
  provider_occurrences: Array<{
    id: number;
    provider: string;
    provider_track_id: string;
    title: string | null;
    duration_ms: number | null;
    provider_uri: string | null;
    provider_url: string | null;
    saved_at: string | null;
    imported_at: string | null;
  }>;
  identifiers: Array<{ type: string; value: string }>;
  identity_resolutions: TrackIdentityResolution[];
  musical_attributes: {
    tempo_bpm?: MusicalAttribute | null;
    musical_key?: MusicalAttribute | null;
  };
  musical_attribute_history: TrackAttributeHistory[];
}

export function formatDuration(durationMs: number | null | undefined): string {
  if (durationMs == null || durationMs <= 0) return "—";
  const totalSec = Math.round(durationMs / 1000);
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${min}:${sec.toString().padStart(2, "0")}`;
}

export function formatYear(releaseDate: string | null | undefined): string {
  if (!releaseDate) return "—";
  const m = /^(\d{4})/.exec(releaseDate);
  return m ? m[1] : "—";
}

export function artistLine(artists: string[] | undefined): string {
  if (!artists || artists.length === 0) return "Unknown artist";
  return artists.join(", ");
}

const MUSIC_KEY_DISPLAY_RE = /^[A-G](#|b)?\s*(major|minor)?$/i;

export function musicalKeyDisplay(value: unknown): string | null {
  if (value == null) return null;
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return null;
    return trimmed;
  }
  if (typeof value === "object") {
    const v = value as { display?: unknown; tonic?: unknown; mode?: unknown };
    if (typeof v.display === "string" && v.display.trim()) return v.display.trim();
    if (typeof v.tonic === "string" && v.tonic.trim()) {
      const mode = typeof v.mode === "string" && v.mode.trim() ? ` ${v.mode.trim()}` : "";
      return `${v.tonic.trim()}${mode}`;
    }
  }
  return null;
}

export function formatBpm(value: unknown): string {
  if (value == null) return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n) || n <= 0) return "—";
  if (Number.isInteger(n)) return n.toString();
  return n.toFixed(1);
}

export function formatMusicalKey(value: unknown): string {
  const display = musicalKeyDisplay(value);
  if (!display) return "—";
  return display;
}

export function musicalSourceLabel(source: string | null | undefined): string {
  if (!source) return "—";
  switch (source) {
    case "getsongbpm":
      return "GetSongBPM";
    case "soundcharts":
      return "Soundcharts";
    case "spotify_audio_features":
      return "Spotify audio features";
    case "essentia":
      return "Essentia";
    default:
      return source;
  }
}

export function formatConfidence(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const pct = Math.round(value * 100);
  return `${pct}%`;
}

// Re-export MUSIC_KEY_DISPLAY_RE so tests can verify the canonical pattern.
export { MUSIC_KEY_DISPLAY_RE };
