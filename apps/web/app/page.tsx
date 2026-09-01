"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  artistLine,
  fetchBpmAnalytics,
  fetchEnergyAnalytics,
  fetchLibraryDNA,
  fetchScatter,
  fetchStatus,
  fetchSummary,
  fetchTracks,
  fetchTrackDetail,
  fetchSavedFlows,
  fetchSavedFlow,
  saveFlow,
  deleteSavedFlow,
  exportToSpotify,
  downloadText,
  downloadCsv,
  formatBpm,
  formatConfidence,
  formatDuration,
  formatLoudness,
  formatMusicalKey,
  formatTimeSignature,
  formatUnit,
  formatYear,
  musicalSourceLabel,
  type HasIsrc,
  type LibraryDNA,
  type LibrarySummary,
  type SortKey,
  type StatusResponse,
  type TrackDetailResponse,
  type TrackItem,
  type TracksResponse,
  type SavedFlowSummary,
  type SavedFlowDetail,
  type SpotifyExportResult,
} from "./lib/api";
import { colors } from "./lib/tokens";
import { SectionLabel, EmptyState } from "./lib/components";
import { CrateView } from "./components/CrateView";
import { TrackInspector } from "./components/TrackInspector";
import { DNAView } from "./components/DNAView";
import { SmartFlowView } from "./components/SmartFlowView";
import { BestNextTrack } from "./components/BestNextTrack";

const SORT_OPTIONS: Array<{ value: SortKey; label: string }> = [
  { value: "saved_desc", label: "Recently saved" },
  { value: "saved_asc", label: "Oldest saved" },
  { value: "title_asc", label: "Title A–Z" },
  { value: "title_desc", label: "Title Z–A" },
  { value: "artist_asc", label: "Artist A–Z" },
  { value: "artist_desc", label: "Artist Z–A" },
  { value: "album_asc", label: "Album A–Z" },
  { value: "album_desc", label: "Album Z–A" },
  { value: "duration_asc", label: "Shortest" },
  { value: "duration_desc", label: "Longest" },
];

type View = "crate" | "dna" | "flow";

export default function Page() {
  // Core data
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [summary, setSummary] = useState<LibrarySummary | null>(null);
  const [data, setData] = useState<TracksResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Inspector
  const [selected, setSelected] = useState<TrackItem | null>(null);
  const [detail, setDetail] = useState<TrackDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Query state
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [provider, setProvider] = useState<string | null>(null);
  const [hasIsrc, setHasIsrc] = useState<HasIsrc>("all");
  const [sort, setSort] = useState<SortKey>("saved_desc");
  const [bpmMin, setBpmMin] = useState<string>("");
  const [bpmMax, setBpmMax] = useState<string>("");
  const [musicalKey, setMusicalKey] = useState<string>("");
  const [camelot, setCamelot] = useState<string>("");
  const [mood, setMood] = useState<string>("");
  const [vibe, setVibe] = useState<string>("");

  // View state
  const [view, setView] = useState<View>("crate");

  // DNA state
  const [dna, setDna] = useState<LibraryDNA | null>(null);
  const [bpmBuckets, setBpmBuckets] = useState<any[]>([]);
  const [energyBuckets, setEnergyBuckets] = useState<any[]>([]);
  const [scatterPoints, setScatterPoints] = useState<any[]>([]);

  // Best Next Track state
  const [nextData, setNextData] = useState<any>(null);
  const [energyIntent, setEnergyIntent] = useState<"maintain" | "build" | "drop">("maintain");

  // Smart Flow state
  const [flowStartId, setFlowStartId] = useState<string>("");
  const [flowCount, setFlowCount] = useState<number>(5);
  const [flowShape, setFlowShape] = useState<string>("maintain");
  const [flowResult, setFlowResult] = useState<any>(null);
  const [flowLoading, setFlowLoading] = useState(false);

  // Saved Flows state (M11)
  const [savedFlows, setSavedFlows] = useState<SavedFlowSummary[]>([]);
  const [savedFlowsLoading, setSavedFlowsLoading] = useState(false);
  const [savedFlowDetail, setSavedFlowDetail] = useState<SavedFlowDetail | null>(null);
  const [flowSubView, setFlowSubView] = useState<"builder" | "saved">("builder");
  const [saveName, setSaveName] = useState("");
  const [saveDesc, setSaveDesc] = useState("");
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [exportPanelFlowId, setExportPanelFlowId] = useState<number | null>(null);
  const [exportPlaylistName, setExportPlaylistName] = useState("AION Flow");
  const [exportPublic, setExportPublic] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [exportResult, setExportResult] = useState<SpotifyExportResult | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const spotifyAcct = status?.connected_accounts.find((a) => a.provider === "spotify");
  const providers = useMemo(() => summary?.providers.map((p) => p.provider) ?? [], [summary]);
  const hasActiveFilters = !!(bpmMin || bpmMax || musicalKey || camelot || mood || vibe);

  // ─── DATA LOADING ───

  const loadStatus = useCallback(async () => {
    try {
      const [s, sum] = await Promise.all([fetchStatus(), fetchSummary()]);
      setStatus(s);
      setSummary(sum);
    } catch { /* non-fatal */ }
  }, []);

  const loadTracks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const parsedBpmMin = bpmMin.trim() === "" ? null : Number(bpmMin);
      const parsedBpmMax = bpmMax.trim() === "" ? null : Number(bpmMax);
      if (parsedBpmMin != null && !Number.isFinite(parsedBpmMin)) throw new Error("BPM min must be a number");
      if (parsedBpmMax != null && !Number.isFinite(parsedBpmMax)) throw new Error("BPM max must be a number");
      if (parsedBpmMin != null && parsedBpmMax != null && parsedBpmMin > parsedBpmMax) throw new Error("BPM min must be ≤ BPM max");
      const resp = await fetchTracks({
        page, pageSize, search, provider, hasIsrc, sort,
        bpmMin: parsedBpmMin, bpmMax: parsedBpmMax,
        musicalKey: musicalKey.trim() || null,
        camelot: camelot.trim() || null,
        mood: mood.trim() || null,
        vibe: vibe.trim() || null,
      });
      setData(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load library");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, provider, hasIsrc, sort, bpmMin, bpmMax, musicalKey, camelot, mood, vibe]);

  const loadAnalytics = useCallback(async () => {
    const q: any = {
      search: search || undefined,
      provider: provider ?? undefined,
      hasIsrc, sort,
      bpmMin: bpmMin.trim() ? Number(bpmMin) : null,
      bpmMax: bpmMax.trim() ? Number(bpmMax) : null,
      musicalKey: musicalKey.trim() || null,
      camelot: camelot.trim() || null,
      mood: mood.trim() || null,
      vibe: vibe.trim() || null,
    };
    try {
      const [d, bpm, en, sc] = await Promise.all([
        fetchLibraryDNA(q), fetchBpmAnalytics(q), fetchEnergyAnalytics(q), fetchScatter(q),
      ]);
      setDna(d);
      setBpmBuckets(bpm.buckets);
      setEnergyBuckets(en.buckets);
      setScatterPoints(sc.points);
    } catch { /* dna failure is non-fatal */ }
  }, [search, provider, hasIsrc, sort, bpmMin, bpmMax, musicalKey, camelot, mood, vibe]);

  const loadSavedFlows = useCallback(async () => {
    setSavedFlowsLoading(true);
    try {
      const data = await fetchSavedFlows();
      setSavedFlows(data.flows);
    } catch { /* non-fatal */ }
    finally { setSavedFlowsLoading(false); }
  }, []);

  // ─── EFFECTS ───

  useEffect(() => { void loadStatus(); void loadTracks(); }, [loadStatus, loadTracks]);
  useEffect(() => { if (view === "dna") void loadAnalytics(); }, [view, loadAnalytics]);
  useEffect(() => { if (view === "flow") void loadSavedFlows(); }, [view, loadSavedFlows]);

  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    let cancelled = false;
    setDetailLoading(true);
    setDetailError(null);
    void (async () => {
      try {
        const d = await fetchTrackDetail(selected.track_id);
        if (!cancelled) setDetail(d);
      } catch (e) {
        if (!cancelled) setDetailError(e instanceof Error ? e.message : "failed");
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [selected]);

  useEffect(() => {
    if (!selected) { setNextData(null); return; }
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch(`/api/tracks/${selected.track_id}/next?limit=5&energy_intent=${energyIntent}`);
        if (!res.ok) throw new Error("next failed");
        const j = await res.json();
        if (!cancelled) setNextData(j);
      } catch {
        if (!cancelled) setNextData(null);
      }
    })();
    return () => { cancelled = true; };
  }, [selected?.track_id, energyIntent]);

  // ─── HANDLERS ───

  const onSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setSearch(searchInput);
  };

  const changeFilter = <T,>(setter: (v: T) => void, value: T) => {
    setPage(1);
    setter(value);
  };

  const clearAllFilters = () => {
    setBpmMin(""); setBpmMax(""); setMusicalKey("");
    setCamelot(""); setMood(""); setVibe("");
  };

  const handleGenerateFlow = async () => {
    setFlowLoading(true);
    try {
      const body: any = {
        target_track_count: flowCount,
        energy_shape: flowShape,
        max_repeat_artist: 1,
      };
      if (flowStartId.trim()) body.start_track_id = Number(flowStartId);
      if (mood) body.mood = [mood];
      if (vibe) body.vibe = [vibe];
      if (bpmMin) body.bpm_min = Number(bpmMin);
      if (bpmMax) body.bpm_max = Number(bpmMax);
      const res = await fetch("/api/smart-flow", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await res.json();
      setFlowResult(j);
    } catch {
      setFlowResult(null);
    } finally {
      setFlowLoading(false);
    }
  };

  const handleSaveFlow = async () => {
    if (!flowResult || !saveName.trim()) return;
    setSaveLoading(true);
    setSaveMsg(null);
    try {
      const result = await saveFlow({
        name: saveName.trim(),
        description: saveDesc.trim() || undefined,
        flow_response: flowResult,
        request_params: {
          start_track_id: flowStartId.trim() ? Number(flowStartId) : undefined,
          target_track_count: flowCount,
          energy_shape: flowShape,
        },
      });
      setSaveMsg(`Saved as "${result.name}" (${result.track_count} tracks)`);
      setSaveName("");
      setSaveDesc("");
      void loadSavedFlows();
    } catch (e) {
      setSaveMsg(`Save failed: ${e instanceof Error ? e.message : "unknown"}`);
    } finally {
      setSaveLoading(false);
    }
  };

  const handleDeleteFlow = async (id: number) => {
    try {
      await deleteSavedFlow(id);
      void loadSavedFlows();
      if (savedFlowDetail?.id === id) setSavedFlowDetail(null);
    } catch { /* non-fatal */ }
  };

  const handleOpenSavedFlow = async (id: number) => {
    try {
      const detail = await fetchSavedFlow(id);
      setSavedFlowDetail(detail);
      setFlowSubView("saved");
    } catch { /* non-fatal */ }
  };

  const handleExportSpotify = async (flowId: number) => {
    setExportLoading(true);
    setExportResult(null);
    setExportError(null);
    try {
      const result = await exportToSpotify(flowId, {
        playlist_name: exportPlaylistName.trim() || "AION Flow",
        description: `AION Smart Flow export`,
        public: exportPublic,
      });
      setExportResult(result);
      void loadSavedFlows();
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExportLoading(false);
    }
  };

  const total = data?.total ?? 0;
  const totalPages = data?.total_pages ?? 0;
  const items = data?.items ?? [];
  const connectedLabel = spotifyAcct
    ? spotifyAcct.display_name || spotifyAcct.provider_user_id
    : null;

  // ─── RENDER ───

  return (
    <div className="min-h-screen bg-aion-bg">
      {/* ─── SHELL HEADER ─── */}
      <header className="sticky top-0 z-30 border-b border-aion-border bg-aion-bg/90 backdrop-blur-md">
        <div className="mx-auto max-w-7xl px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-6">
            {/* Logo / Title */}
            <div>
              <h1 className="font-display text-lg font-bold tracking-tight text-aion-text">AION</h1>
            </div>

            {/* Navigation — CRATE / DNA / FLOW */}
            <nav className="flex items-center gap-1">
              {([
                { id: "crate" as View, label: "CRATE" },
                { id: "dna" as View, label: "DNA" },
                { id: "flow" as View, label: "FLOW" },
              ]).map((item) => (
                <button
                  key={item.id}
                  onClick={() => {
                    setView(item.id);
                    if (item.id === "dna") void loadAnalytics();
                  }}
                  className={`px-3 py-1.5 text-[11px] font-mono font-medium tracking-wider transition-colors rounded ${
                    view === item.id
                      ? "bg-aion-acid/15 text-aion-acid-bright"
                      : "text-aion-text-muted hover:text-aion-text-secondary hover:bg-aion-elevated"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </nav>
          </div>

          {/* Connection status */}
          <div className="flex items-center gap-3">
            {connectedLabel ? (
              <span className="text-[11px] text-aion-text-muted">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-aion-success mr-1.5" />
                {connectedLabel}
              </span>
            ) : (
              <span className="text-[11px] text-aion-text-faint">Not connected</span>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-6">
        {/* ─── CONNECTION BAR ─── */}
        <div className="mb-6 flex flex-wrap items-center gap-3 aion-surface px-4 py-3">
          {!spotifyAcct ? (
            <button
              onClick={async () => {
                const r = await fetch("/api/auth/spotify/login");
                const d = await r.json();
                window.location.href = d.authorization_url;
              }}
              className="rounded bg-aion-acid/20 px-4 py-1.5 text-[12px] font-medium text-aion-acid-bright hover:bg-aion-acid/30 transition-colors"
            >
              Connect Spotify
            </button>
          ) : (
            <button
              onClick={async () => {
                await fetch(`/api/import/liked-songs?provider_user_id=${encodeURIComponent(spotifyAcct.provider_user_id)}`, { method: "POST" });
                void loadStatus();
                void loadTracks();
              }}
              className="rounded border border-aion-border px-4 py-1.5 text-[12px] font-medium text-aion-text-secondary hover:bg-aion-elevated transition-colors"
            >
              Re-import Liked Songs
            </button>
          )}
          <p className="text-[11px] text-aion-text-muted font-mono">
            {summary ? (
              <>
                <span className="text-aion-text-secondary">{summary.canonical_tracks.toLocaleString()}</span> canonical
                {" · "}
                <span className="text-aion-text-secondary">{summary.with_isrc.toLocaleString()}</span> ISRC
              </>
            ) : (
              "Loading…"
            )}
          </p>
        </div>

        {/* ─── FILTERS ─── */}
        <div className="mb-6 flex flex-wrap items-center gap-2">
          <form onSubmit={onSearchSubmit} className="flex-1 min-w-[200px]">
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search crate…"
              className="w-full rounded border border-aion-border bg-aion-raised px-3 py-1.5 text-[13px] text-aion-text placeholder:text-aion-text-faint outline-none focus:border-aion-acid/40 transition-colors"
            />
          </form>

          <FilterSelect
            value={provider ?? ""}
            onChange={(v) => changeFilter(setProvider, v || null)}
            options={[{ value: "", label: "All providers" }, ...providers.map((p) => ({ value: p, label: p }))]}
          />
          <FilterSelect
            value={hasIsrc}
            onChange={(v) => changeFilter(setHasIsrc, v as HasIsrc)}
            options={[
              { value: "all", label: "All ISRC" },
              { value: "has", label: "Has ISRC" },
              { value: "missing", label: "Missing ISRC" },
            ]}
          />
          <FilterSelect
            value={sort}
            onChange={(v) => changeFilter(setSort, v as SortKey)}
            options={SORT_OPTIONS}
          />
          <FilterInput
            value={bpmMin}
            onChange={(v) => changeFilter(setBpmMin, v)}
            placeholder="BPM min"
            width="w-16"
          />
          <FilterInput
            value={bpmMax}
            onChange={(v) => changeFilter(setBpmMax, v)}
            placeholder="BPM max"
            width="w-16"
          />
          <FilterInput
            value={musicalKey}
            onChange={(v) => changeFilter(setMusicalKey, v)}
            placeholder="Key"
            width="w-20"
          />
          <FilterInput
            value={camelot}
            onChange={(v) => changeFilter(setCamelot, v)}
            placeholder="Cam"
            width="w-14"
          />
          <FilterInput
            value={mood}
            onChange={(v) => changeFilter(setMood, v)}
            placeholder="Mood"
            width="w-20"
          />
          <FilterInput
            value={vibe}
            onChange={(v) => changeFilter(setVibe, v)}
            placeholder="Vibe"
            width="w-20"
          />
          {hasActiveFilters && (
            <button
              onClick={clearAllFilters}
              className="text-[10px] text-aion-text-faint hover:text-aion-text-muted transition-colors px-1"
            >
              clear
            </button>
          )}
        </div>

        {/* ─── LOADING STATE ─── */}
        {loading && !data && (
          <div className="space-y-1 py-8">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-aion-raised/40" />
            ))}
          </div>
        )}

        {/* ─── ERROR STATE ─── */}
        {error && (
          <div className="rounded border border-aion-error/20 bg-aion-error/5 p-4 text-sm text-aion-error">
            <p>{error}</p>
            <button
              onClick={() => void loadTracks()}
              className="mt-2 rounded border border-aion-error/30 px-3 py-1 text-[11px] text-aion-text-muted hover:bg-aion-error/10 transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        {/* ─── EMPTY STATES ─── */}
        {!loading && !error && data && total === 0 && !search && (
          <div className="py-12 text-center">
            <EmptyState>No tracks imported yet. Connect Spotify and import your Liked Songs.</EmptyState>
          </div>
        )}
        {!loading && !error && data && total === 0 && search && (
          <div className="py-12 text-center">
            <EmptyState>No tracks match &ldquo;{search}&rdquo;</EmptyState>
          </div>
        )}

        {/* ─── CRATE VIEW ─── */}
        {view === "crate" && !loading && !error && data && total > 0 && (
          <CrateView
            items={items}
            total={total}
            page={page}
            totalPages={totalPages}
            pageSize={pageSize}
            loading={loading}
            onSelectTrack={(t) => setSelected(t)}
            onPageChange={setPage}
            onPageSizeChange={(v) => changeFilter(setPageSize, v)}
          />
        )}

        {/* ─── DNA VIEW ─── */}
        {view === "dna" && dna && (
          <DNAView
            dna={dna}
            bpmBuckets={bpmBuckets}
            energyBuckets={energyBuckets}
            scatterPoints={scatterPoints}
            selectedMood={mood || null}
            selectedVibe={vibe || null}
            selectedCamelot={camelot || null}
            onSelectMood={(m) => changeFilter(setMood, m ?? "")}
            onSelectVibe={(v) => changeFilter(setVibe, v ?? "")}
            onSelectCamelot={(code) => { setCamelot(code); setView("crate"); }}
            onSelectScatterTrack={(id) => {
              const found = items.find((it) => it.track_id === id);
              if (found) setSelected(found);
            }}
            onClearFilters={clearAllFilters}
            hasActiveFilters={hasActiveFilters}
          />
        )}

        {/* ─── FLOW VIEW ─── */}
        {view === "flow" && (
          <div className="space-y-6">
            {/* Sub-view toggle */}
            <div className="flex gap-1">
              {([
                { id: "builder" as const, label: "BUILDER" },
                { id: "saved" as const, label: "SAVED FLOWS" },
              ]).map((item) => (
                <button
                  key={item.id}
                  onClick={() => { setFlowSubView(item.id); if (item.id === "saved") void loadSavedFlows(); }}
                  className={`px-3 py-1.5 text-[11px] font-mono font-medium tracking-wider transition-colors rounded ${
                    flowSubView === item.id
                      ? "bg-aion-clay/15 text-aion-clay-bright"
                      : "text-aion-text-muted hover:text-aion-text-secondary hover:bg-aion-elevated"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>

            {/* ─── BUILDER ─── */}
            {flowSubView === "builder" && (
              <>
                <div className="aion-surface p-5">
                  <SectionLabel>Smart Flow Builder</SectionLabel>
                  <p className="mt-1 text-[12px] text-aion-text-muted">
                    Deterministic beam-search · harmonic 30% · BPM 25% · energy 20% · vibe 10% · mood 10%
                  </p>
                  <div className="mt-4 grid gap-3 md:grid-cols-4">
                    <label className="text-[11px] text-aion-text-muted">
                      Start track ID
                      <input
                        value={flowStartId}
                        onChange={(e) => setFlowStartId(e.target.value)}
                        placeholder="optional"
                        className="mt-1 w-full rounded border border-aion-border bg-aion-raised px-2 py-1.5 text-[12px] font-mono text-aion-text placeholder:text-aion-text-faint outline-none focus:border-aion-acid/40"
                      />
                    </label>
                    <label className="text-[11px] text-aion-text-muted">
                      Track count
                      <select
                        value={flowCount}
                        onChange={(e) => setFlowCount(Number(e.target.value))}
                        className="mt-1 w-full rounded border border-aion-border bg-aion-raised px-2 py-1.5 text-[12px] font-mono text-aion-text"
                      >
                        <option value={5}>5</option>
                        <option value={10}>10</option>
                        <option value={20}>20</option>
                      </select>
                    </label>
                    <label className="text-[11px] text-aion-text-muted">
                      Energy shape
                      <select
                        value={flowShape}
                        onChange={(e) => setFlowShape(e.target.value)}
                        className="mt-1 w-full rounded border border-aion-border bg-aion-raised px-2 py-1.5 text-[12px] font-mono text-aion-text"
                      >
                        <option value="maintain">maintain</option>
                        <option value="build">build</option>
                        <option value="drop">drop</option>
                        <option value="wave">wave</option>
                        <option value="peak_middle">peak middle</option>
                        <option value="peak_end">peak end</option>
                      </select>
                    </label>
                    <div className="flex items-end">
                      <button
                        onClick={handleGenerateFlow}
                        disabled={flowLoading}
                        className="w-full rounded bg-aion-acid/20 px-4 py-1.5 text-[12px] font-medium text-aion-acid-bright hover:bg-aion-acid/30 disabled:opacity-50 transition-colors"
                      >
                        {flowLoading ? "Generating…" : "GENERATE FLOW"}
                      </button>
                    </div>
                  </div>
                </div>

                {/* Results + Save */}
                {flowResult && (
                  <>
                    <SmartFlowView
                      result={flowResult}
                      onSelectTrack={(id) => {
                        const found = items.find((it) => it.track_id === id);
                        if (found) setSelected(found);
                      }}
                    />

                    {/* Save form */}
                    <div className="aion-surface p-4">
                      <SectionLabel>Save Flow</SectionLabel>
                      <div className="mt-3 grid gap-3 md:grid-cols-3">
                        <input
                          value={saveName}
                          onChange={(e) => setSaveName(e.target.value)}
                          placeholder="Flow name"
                          className="rounded border border-aion-border bg-aion-raised px-2 py-1.5 text-[12px] font-mono text-aion-text placeholder:text-aion-text-faint outline-none focus:border-aion-acid/40"
                        />
                        <input
                          value={saveDesc}
                          onChange={(e) => setSaveDesc(e.target.value)}
                          placeholder="Description (optional)"
                          className="rounded border border-aion-border bg-aion-raised px-2 py-1.5 text-[12px] font-mono text-aion-text placeholder:text-aion-text-faint outline-none focus:border-aion-acid/40"
                        />
                        <button
                          onClick={handleSaveFlow}
                          disabled={saveLoading || !saveName.trim()}
                          className="rounded bg-aion-clay/20 px-4 py-1.5 text-[12px] font-medium text-aion-clay-bright hover:bg-aion-clay/30 disabled:opacity-50 transition-colors"
                        >
                          {saveLoading ? "Saving…" : "SAVE FLOW"}
                        </button>
                      </div>
                      {saveMsg && (
                        <p className="mt-2 text-[11px] text-aion-text-secondary">{saveMsg}</p>
                      )}
                    </div>
                  </>
                )}
              </>
            )}

            {/* ─── SAVED FLOWS ─── */}
            {flowSubView === "saved" && (
              <div className="space-y-4">
                {savedFlowsLoading && (
                  <div className="space-y-1 py-4">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <div key={i} className="h-12 animate-pulse rounded bg-aion-raised/40" />
                    ))}
                  </div>
                )}

                {!savedFlowsLoading && savedFlows.length === 0 && (
                  <EmptyState>No saved flows yet. Generate and save a flow first.</EmptyState>
                )}

                {savedFlows.map((f) => (
                  <div key={f.id} className="aion-surface p-4">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-sm text-aion-text font-medium">{f.name}</p>
                        {f.description && <p className="text-[11px] text-aion-text-muted mt-0.5">{f.description}</p>}
                        <div className="mt-1 flex items-center gap-2 text-[10px] font-mono text-aion-text-faint">
                          <span>{f.track_count} tracks</span>
                          <span>·</span>
                          <span>{f.energy_shape}</span>
                          <span>·</span>
                          <span style={{ color: f.overall_sequence_score != null && f.overall_sequence_score >= 80 ? "var(--aion-moss)" : "var(--aion-clay)" }}>
                            {f.overall_sequence_score ?? "—"} overall
                          </span>
                          <span>·</span>
                          <span>weakest {f.minimum_transition_score ?? "—"}</span>
                          <span>·</span>
                          <span>{f.created_at ? new Date(f.created_at).toLocaleDateString() : "—"}</span>
                        </div>
                      </div>
                      <div className="flex gap-1.5">
                        <button
                          onClick={() => handleOpenSavedFlow(f.id)}
                          className="rounded border border-aion-border px-2 py-1 text-[10px] text-aion-text-muted hover:bg-aion-elevated transition-colors"
                        >
                          OPEN
                        </button>
                        <button
                          onClick={() => { setExportPanelFlowId(exportPanelFlowId === f.id ? null : f.id); setExportResult(null); setExportError(null); setExportPlaylistName(f.name); }}
                          className="rounded border border-aion-border px-2 py-1 text-[10px] text-aion-text-muted hover:bg-aion-elevated transition-colors"
                        >
                          EXPORT
                        </button>
                        <button
                          onClick={() => handleDeleteFlow(f.id)}
                          className="rounded border border-aion-error/20 px-2 py-1 text-[10px] text-aion-error/60 hover:bg-aion-error/5 transition-colors"
                        >
                          DELETE
                        </button>
                      </div>
                    </div>

                    {/* Export panel */}
                    {exportPanelFlowId === f.id && (
                      <div className="mt-3 rounded border border-aion-border bg-aion-raised p-3 space-y-3">
                        <SectionLabel>Export to Spotify</SectionLabel>
                        <div className="grid gap-2 md:grid-cols-3">
                          <input
                            value={exportPlaylistName}
                            onChange={(e) => setExportPlaylistName(e.target.value)}
                            placeholder="Playlist name"
                            className="rounded border border-aion-border bg-aion-bg px-2 py-1.5 text-[11px] font-mono text-aion-text outline-none focus:border-aion-acid/40"
                          />
                          <label className="flex items-center gap-2 text-[11px] text-aion-text-muted">
                            <input
                              type="checkbox"
                              checked={exportPublic}
                              onChange={(e) => setExportPublic(e.target.checked)}
                              className="rounded"
                            />
                            Public playlist
                          </label>
                          <button
                            onClick={() => handleExportSpotify(f.id)}
                            disabled={exportLoading || !exportPlaylistName.trim()}
                            className="rounded bg-aion-moss/20 px-3 py-1.5 text-[11px] font-medium text-aion-moss-bright hover:bg-aion-moss/30 disabled:opacity-50 transition-colors"
                          >
                            {exportLoading ? "Exporting…" : "EXPORT TO SPOTIFY"}
                          </button>
                        </div>
                        {exportResult && (
                          <div className="rounded border border-aion-moss/20 bg-aion-moss/5 p-2 text-[11px]">
                            <p className="text-aion-moss-bright">
                              Exported {exportResult.exported_track_count} tracks to{" "}
                              <a href={exportResult.playlist_url} target="_blank" rel="noreferrer" className="underline hover:text-aion-text">
                                {exportResult.playlist_name}
                              </a>
                            </p>
                            {exportResult.skipped_track_count > 0 && (
                              <p className="mt-1 text-aion-clay">
                                {exportResult.skipped_track_count} tracks skipped (no Spotify mapping)
                              </p>
                            )}
                          </div>
                        )}
                        {exportError && (
                          <p className="text-[11px] text-aion-error">{exportError}</p>
                        )}
                        <div className="flex gap-2 text-[10px]">
                          <button onClick={() => downloadText(f.id)} className="text-aion-text-muted hover:text-aion-text-secondary transition-colors">
                            Download TXT
                          </button>
                          <span className="text-aion-text-faint">·</span>
                          <button onClick={() => downloadCsv(f.id)} className="text-aion-text-muted hover:text-aion-text-secondary transition-colors">
                            Download CSV
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}

                {/* Opened saved flow detail */}
                {savedFlowDetail && (
                  <div className="aion-surface p-5">
                    <div className="flex items-baseline justify-between mb-4">
                      <div>
                        <SectionLabel>{savedFlowDetail.name}</SectionLabel>
                        {savedFlowDetail.description && (
                          <p className="text-[11px] text-aion-text-muted mt-0.5">{savedFlowDetail.description}</p>
                        )}
                      </div>
                      <button
                        onClick={() => setSavedFlowDetail(null)}
                        className="text-[10px] text-aion-text-faint hover:text-aion-text-muted transition-colors"
                      >
                        Close
                      </button>
                    </div>
                    <SmartFlowView
                      result={savedFlowDetail}
                      onSelectTrack={(id) => {
                        const found = items.find((it) => it.track_id === id);
                        if (found) setSelected(found);
                      }}
                    />
                    {savedFlowDetail.exports.length > 0 && (
                      <div className="mt-4 border-t border-aion-border pt-3">
                        <SectionLabel className="mb-2">Export History</SectionLabel>
                        {savedFlowDetail.exports.map((exp) => (
                          <div key={exp.id} className="flex items-center gap-2 text-[10px] font-mono text-aion-text-faint">
                            <span>{exp.provider}</span>
                            <span>·</span>
                            <span>{exp.exported_track_count} tracks</span>
                            {exp.external_playlist_url && (
                              <>
                                <span>·</span>
                                <a href={exp.external_playlist_url} target="_blank" rel="noreferrer" className="text-aion-text-muted underline hover:text-aion-text-secondary">
                                  {exp.external_playlist_name}
                                </a>
                              </>
                            )}
                            <span>·</span>
                            <span>{exp.created_at ? new Date(exp.created_at).toLocaleDateString() : "—"}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>

      {/* ─── TRACK INSPECTOR ─── */}
      {selected && (
        <TrackInspector
          track={selected}
          detail={detail}
          detailLoading={detailLoading}
          detailError={detailError}
          onClose={() => setSelected(null)}
        />
      )}

      {/* ─── INSPECTOR-OVERLAID BEST NEXT ─── */}
      {selected && nextData?.recommendations?.length > 0 && (
        <div className="fixed bottom-0 left-0 right-0 z-30 lg:hidden">
          <div className="mx-auto max-w-7xl p-4">
            <BestNextTrack
              recommendations={nextData.recommendations}
              energyIntent={energyIntent}
              onSelectIntent={setEnergyIntent}
              onSelectTrack={(id) => {
                const found = items.find((it) => it.track_id === id);
                if (found) setSelected(found);
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Filter primitives ─── */

function FilterSelect({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded border border-aion-border bg-aion-raised px-2 py-1.5 text-[11px] font-mono text-aion-text-secondary"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

function FilterInput({
  value,
  onChange,
  placeholder,
  width = "w-16",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  width?: string;
}) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={`rounded border border-aion-border bg-aion-raised px-2 py-1.5 text-[11px] font-mono text-aion-text placeholder:text-aion-text-faint outline-none focus:border-aion-acid/40 transition-colors ${width}`}
    />
  );
}
