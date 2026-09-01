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

export interface ScoredLabel {
  label: string;
  score: number;
  explanation?: string[];
}

export interface MusicCharacter {
  dominant_mood: string | null;
  dominant_vibe: string | null;
  moods: ScoredLabel[];
  vibes: ScoredLabel[];
  set_role?: string | null;
  source: string;
  analysis_version: string;
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
    time_signature?: MusicalAttribute | null;
    energy?: MusicalAttribute | null;
    danceability?: MusicalAttribute | null;
    valence?: MusicalAttribute | null;
    acousticness?: MusicalAttribute | null;
    instrumentalness?: MusicalAttribute | null;
    liveness?: MusicalAttribute | null;
    loudness_db?: MusicalAttribute | null;
    speechiness?: MusicalAttribute | null;
    camelot?: (MusicalAttribute & { number?: number; letter?: string; open_key?: string; derived_from?: string }) | null;
  };
  music_character?: MusicCharacter | null;
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
  camelot: string | null;
  mood: string | null;
  vibe: string | null;
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
  camelot: string | null;
  mood: string | null;
  vibe: string | null;
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
  if (q.camelot && q.camelot.trim())
    params.set("camelot", q.camelot.trim().toUpperCase());
  if (q.mood && q.mood.trim()) params.set("mood", q.mood.trim().toLowerCase());
  if (q.vibe && q.vibe.trim()) params.set("vibe", q.vibe.trim().toLowerCase());
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

export interface CompatibilityResponse {
  from_track_id: number;
  to_track_id: number;
  from_key: string | null;
  to_key: string | null;
  from_camelot: string | null;
  to_camelot: string | null;
  score: number;
  relationship: string;
  from_bpm: number | null;
  to_bpm: number | null;
  bpm_relationship: string | null;
}

export async function fetchCompatibility(fromId: number, toId: number): Promise<CompatibilityResponse> {
  const res = await fetch(`/api/tracks/${fromId}/compatibility/${toId}`);
  if (!res.ok) throw new Error(`Compatibility request failed: ${res.status}`);
  return (await res.json()) as CompatibilityResponse;
}

export async function fetchCompatibleTracks(trackId: number, limit = 10): Promise<{ track_id: number; compatible: CompatibilityResponse[] }> {
  const res = await fetch(`/api/tracks/${trackId}/compatible?limit=${limit}`);
  if (!res.ok) throw new Error(`Compatible tracks request failed: ${res.status}`);
  return (await res.json()) as { track_id: number; compatible: CompatibilityResponse[] };
}

export interface LibraryDNA {
  total_tracks: number;
  filtered_tracks: number;
  enriched_tracks: number;
  enrichment_percentage: number;
  tempo: { average: number | null; median: number | null; min: number | null; max: number | null; dominant_range: string | null };
  energy: { average: number | null; median: number | null };
  danceability: { average: number | null };
  valence: { average: number | null };
  top_keys: Array<{ label: string; count: number; percentage: number }>;
  top_camelots: Array<{ label: string; count: number; percentage: number }>;
  camelot_distribution: Array<{ label: string; count: number; percentage: number }>;
  top_moods: Array<{ label: string; count: number; percentage: number }>;
  top_vibes: Array<{ label: string; count: number; percentage: number }>;
  mood_distribution: Array<{ label: string; count: number; percentage: number }>;
  vibe_distribution: Array<{ label: string; count: number; percentage: number }>;
  set_roles: Array<{ label: string; count: number; percentage: number }>;
}

export async function fetchLibraryDNA(q: Partial<TracksQuery>): Promise<LibraryDNA> {
  const res = await fetch(`/api/library/dna?${buildTracksQuery(q)}`);
  if (!res.ok) throw new Error(`DNA request failed: ${res.status}`);
  return (await res.json()) as LibraryDNA;
}

export async function fetchBpmAnalytics(q: Partial<TracksQuery>): Promise<{ buckets: Array<{ min: number; max: number; count: number; label: string }> }> {
  const res = await fetch(`/api/library/analytics/bpm?${buildTracksQuery(q)}`);
  if (!res.ok) throw new Error(`BPM analytics failed: ${res.status}`);
  return (await res.json()) as { buckets: Array<{ min: number; max: number; count: number; label: string }> };
}

export async function fetchEnergyAnalytics(q: Partial<TracksQuery>): Promise<{ buckets: Array<{ min: number; max: number; count: number; label: string }> }> {
  const res = await fetch(`/api/library/analytics/energy?${buildTracksQuery(q)}`);
  if (!res.ok) throw new Error(`Energy analytics failed: ${res.status}`);
  return (await res.json()) as { buckets: Array<{ min: number; max: number; count: number; label: string }> };
}

export async function fetchScatter(q: Partial<TracksQuery>): Promise<{ points: Array<{ track_id: number; title: string; artist: string; bpm: number; energy: number; key: string | null; camelot: string | null; mood: string | null; vibe: string | null; set_role: string | null }>; count: number }> {
  const res = await fetch(`/api/library/analytics/scatter?${buildTracksQuery(q)}`);
  if (!res.ok) throw new Error(`Scatter failed: ${res.status}`);
  return (await res.json()) as { points: Array<{ track_id: number; title: string; artist: string; bpm: number; energy: number; key: string | null; camelot: string | null; mood: string | null; vibe: string | null; set_role: string | null }>; count: number };
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
    time_signature?: MusicalAttribute | null;
    energy?: MusicalAttribute | null;
    danceability?: MusicalAttribute | null;
    valence?: MusicalAttribute | null;
    acousticness?: MusicalAttribute | null;
    instrumentalness?: MusicalAttribute | null;
    liveness?: MusicalAttribute | null;
    loudness_db?: MusicalAttribute | null;
    speechiness?: MusicalAttribute | null;
    camelot?: (MusicalAttribute & { number?: number; letter?: string; open_key?: string; derived_from?: string }) | null;
  };
  music_character?: MusicCharacter | null;
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

export function formatUnit(value: unknown): string {
  if (value == null) return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(2);
}

export function formatLoudness(value: unknown): string {
  if (value == null) return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${n.toFixed(1)} dB`;
}

export function formatTimeSignature(value: unknown): string {
  if (value == null) return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n) || n <= 0) return "—";
  return `${Math.round(n)}/4`;
}

// Re-export MUSIC_KEY_DISPLAY_RE so tests can verify the canonical pattern.
export { MUSIC_KEY_DISPLAY_RE };

// ─── Saved Flows (M11) ───

export interface SavedFlowSummary {
  id: number;
  name: string;
  description: string | null;
  created_at: string | null;
  track_count: number;
  energy_shape: string;
  overall_sequence_score: number | null;
  average_transition_score: number | null;
  minimum_transition_score: number | null;
  status: string;
}

export interface SavedFlowTrack {
  position: number;
  track: {
    track_id: number;
    title: string | null;
    artist: string | null;
    bpm: number | null;
    camelot: string | null;
    energy: number | null;
    dominant_mood: string | null;
    dominant_vibe: string | null;
  };
  transition_from_previous: {
    score: number;
    components: Record<string, number> | null;
    reasons: string[] | null;
    warnings: string[] | null;
  } | null;
}

export interface SavedFlowDetail extends SavedFlowSummary {
  start_track_id: number | null;
  target_track_count: number;
  constraints_json: string | null;
  optimizer_version: string | null;
  transition_model_version: string | null;
  sequence: SavedFlowTrack[];
  exports: FlowExportRecord[];
}

export interface FlowExportRecord {
  id: number;
  provider: string;
  external_playlist_id: string | null;
  external_playlist_url: string | null;
  external_playlist_name: string | null;
  exported_track_count: number;
  skipped_track_count: number;
  skipped_tracks: any[];
  status: string;
  error_summary: string | null;
  created_at: string | null;
}

export interface SpotifyExportResult {
  provider: string;
  playlist_id: string;
  playlist_url: string;
  playlist_name: string;
  exported_track_count: number;
  skipped_track_count: number;
  skipped_tracks: any[];
}

export async function fetchSavedFlows(): Promise<{ flows: SavedFlowSummary[]; count: number }> {
  const res = await fetch("/api/flows");
  if (!res.ok) throw new Error(`Flows request failed: ${res.status}`);
  return (await res.json()) as { flows: SavedFlowSummary[]; count: number };
}

export async function fetchSavedFlow(id: number): Promise<SavedFlowDetail> {
  const res = await fetch(`/api/flows/${id}`);
  if (!res.ok) throw new Error(`Flow request failed: ${res.status}`);
  return (await res.json()) as SavedFlowDetail;
}

export async function saveFlow(params: {
  name: string;
  description?: string;
  flow_response: any;
  request_params: any;
}): Promise<{ id: number; name: string; track_count: number; created_at: string | null }> {
  const res = await fetch("/api/flows", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(`Save flow failed: ${res.status}`);
  return (await res.json()) as { id: number; name: string; track_count: number; created_at: string | null };
}

export async function deleteSavedFlow(id: number): Promise<void> {
  const res = await fetch(`/api/flows/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Delete flow failed: ${res.status}`);
}

export async function exportToSpotify(
  flowId: number,
  params: { playlist_name: string; description?: string; public?: boolean }
): Promise<SpotifyExportResult> {
  const res = await fetch(`/api/flows/${flowId}/export/spotify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Spotify export failed: ${res.status}`);
  }
  return (await res.json()) as SpotifyExportResult;
}

export function downloadText(flowId: number): void {
  window.open(`/api/flows/${flowId}/export/text`, "_blank");
}

export function downloadCsv(flowId: number): void {
  window.open(`/api/flows/${flowId}/export/csv`, "_blank");
}
