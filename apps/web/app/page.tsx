"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  artistLine,
  fetchStatus,
  fetchSummary,
  fetchTracks,
  fetchTrackDetail,
  formatBpm,
  formatConfidence,
  formatDuration,
  formatMusicalKey,
  formatYear,
  musicalSourceLabel,
  type HasIsrc,
  type LibrarySummary,
  type SortKey,
  type StatusResponse,
  type TrackDetailResponse,
  type TrackItem,
  type TracksResponse,
} from "./lib/api";

const ATTRIBUTION_URL = "https://getsongbpm.com";

const SORT_OPTIONS: Array<{ value: SortKey; label: string }> = [
  { value: "saved_desc", label: "Recently saved" },
  { value: "saved_asc", label: "Oldest saved" },
  { value: "title_asc", label: "Title A–Z" },
  { value: "title_desc", label: "Title Z–A" },
  { value: "artist_asc", label: "Artist A–Z" },
  { value: "artist_desc", label: "Artist Z–A" },
  { value: "album_asc", label: "Album A–Z" },
  { value: "album_desc", label: "Album Z–A" },
  { value: "duration_asc", label: "Shortest first" },
  { value: "duration_desc", label: "Longest first" },
];

const PAGE_SIZES = [25, 50, 100];

function TrackArtwork({ track }: { track: TrackItem }) {
  const [failed, setFailed] = useState(false);
  const url = track.artwork_url;
  if (!url || failed) {
    return (
      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded bg-zinc-800 text-zinc-500 text-sm font-semibold">
        {track.title.slice(0, 1).toUpperCase() || "?"}
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={url}
      alt=""
      loading="lazy"
      onError={() => setFailed(true)}
      className="h-12 w-12 shrink-0 rounded object-cover bg-zinc-800"
    />
  );
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 10);
}

export default function Page() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [summary, setSummary] = useState<LibrarySummary | null>(null);
  const [data, setData] = useState<TracksResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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

  const spotifyAcct = status?.connected_accounts.find((a) => a.provider === "spotify");
  const providers = useMemo(
    () => summary?.providers.map((p) => p.provider) ?? [],
    [summary]
  );

  const loadStatus = useCallback(async () => {
    try {
      const [s, sum] = await Promise.all([fetchStatus(), fetchSummary()]);
      setStatus(s);
      setSummary(sum);
    } catch {
      /* status failures are non-fatal for the explorer */
    }
  }, []);

  const loadTracks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const parsedBpmMin = bpmMin.trim() === "" ? null : Number(bpmMin);
      const parsedBpmMax = bpmMax.trim() === "" ? null : Number(bpmMax);
      if (parsedBpmMin != null && !Number.isFinite(parsedBpmMin)) {
        throw new Error("BPM min must be a number");
      }
      if (parsedBpmMax != null && !Number.isFinite(parsedBpmMax)) {
        throw new Error("BPM max must be a number");
      }
      if (
        parsedBpmMin != null &&
        parsedBpmMax != null &&
        parsedBpmMin > parsedBpmMax
      ) {
        throw new Error("BPM min must be ≤ BPM max");
      }
      const resp = await fetchTracks({
        page,
        pageSize,
        search,
        provider,
        hasIsrc,
        sort,
        bpmMin: parsedBpmMin,
        bpmMax: parsedBpmMax,
        musicalKey: musicalKey.trim() ? musicalKey.trim() : null,
      });
      setData(resp);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load library");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, provider, hasIsrc, sort, bpmMin, bpmMax, musicalKey]);

  // Initial load
  useEffect(() => {
    void loadStatus();
    void loadTracks();
  }, [loadStatus, loadTracks]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
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
    return () => {
      cancelled = true;
    };
  }, [selected]);

  const onSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setSearch(searchInput);
  };

  const changeFilter = <T,>(setter: (v: T) => void, value: T) => {
    setPage(1);
    setter(value);
  };

  const total = data?.total ?? 0;
  const totalPages = data?.total_pages ?? 0;
  const items = data?.items ?? [];

  const connectedLabel = spotifyAcct
    ? spotifyAcct.display_name || spotifyAcct.provider_user_id
    : null;

  return (
    <main className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">AION</h1>
          <p className="text-zinc-400 text-sm">
            Music intelligence — your imported library
          </p>
        </div>
        <div className="text-right text-sm">
          {connectedLabel ? (
            <p>
              Connected as{" "}
              <span className="font-semibold text-emerald-400">{connectedLabel}</span>
            </p>
          ) : (
            <p className="text-zinc-400">Not connected</p>
          )}
          {spotifyAcct && (
            <p className="text-zinc-500 text-xs">
              spotify · {spotifyAcct.provider_user_id}
            </p>
          )}
        </div>
      </header>

      {/* Connection / import controls (M0 preserved) */}
      <section className="mb-8 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <div className="flex flex-wrap items-center gap-3">
          {!spotifyAcct ? (
            <button
              onClick={async () => {
                const r = await fetch("/api/auth/spotify/login");
                const d = await r.json();
                window.location.href = d.authorization_url;
              }}
              className="rounded bg-emerald-500 px-4 py-2 text-sm font-medium text-black hover:bg-emerald-400"
            >
              Connect Spotify
            </button>
          ) : (
            <button
              onClick={async () => {
                await fetch(
                  `/api/import/liked-songs?provider_user_id=${encodeURIComponent(
                    spotifyAcct.provider_user_id
                  )}`,
                  { method: "POST" }
                );
                void loadStatus();
                void loadTracks();
              }}
              className="rounded bg-zinc-100 px-4 py-2 text-sm font-medium text-black hover:bg-white"
            >
              Re-import Liked Songs
            </button>
          )}
          <p className="text-zinc-400 text-sm">
            {summary ? (
              <>
                <span className="font-semibold text-zinc-100">
                  {summary.canonical_tracks.toLocaleString()}
                </span>{" "}
                canonical tracks ·{" "}
                <span className="font-semibold text-zinc-100">
                  {summary.provider_occurrences.toLocaleString()}
                </span>{" "}
                Spotify occurrences ·{" "}
                <span className="font-semibold text-zinc-100">
                  {summary.with_isrc.toLocaleString()}
                </span>{" "}
                with ISRC
              </>
            ) : (
              "Loading library…"
            )}
          </p>
        </div>
      </section>

      {/* Controls */}
      <section className="mb-4 flex flex-wrap items-center gap-3">
        <form onSubmit={onSearchSubmit} className="flex-1 min-w-[240px]">
          <input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search your music…"
            className="w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm outline-none focus:border-emerald-500"
          />
        </form>

        <label className="text-xs text-zinc-400">
          Provider
          <select
            value={provider ?? ""}
            onChange={(e) =>
              changeFilter(setProvider, e.target.value || null)
            }
            className="ml-2 rounded border border-zinc-700 bg-zinc-900 px-2 py-2 text-sm text-zinc-100"
          >
            <option value="">All</option>
            {providers.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>

        <label className="text-xs text-zinc-400">
          ISRC
          <select
            value={hasIsrc}
            onChange={(e) => changeFilter(setHasIsrc, e.target.value as HasIsrc)}
            className="ml-2 rounded border border-zinc-700 bg-zinc-900 px-2 py-2 text-sm text-zinc-100"
          >
            <option value="all">All</option>
            <option value="has">Has ISRC</option>
            <option value="missing">Missing ISRC</option>
          </select>
        </label>

        <label className="text-xs text-zinc-400">
          Sort
          <select
            value={sort}
            onChange={(e) => changeFilter(setSort, e.target.value as SortKey)}
            className="ml-2 rounded border border-zinc-700 bg-zinc-900 px-2 py-2 text-sm text-zinc-100"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>

        <label className="text-xs text-zinc-400">
          BPM min
          <input
            type="number"
            inputMode="numeric"
            min={0}
            max={400}
            value={bpmMin}
            onChange={(e) => changeFilter(setBpmMin, e.target.value)}
            placeholder="—"
            className="ml-2 w-20 rounded border border-zinc-700 bg-zinc-900 px-2 py-2 text-sm text-zinc-100"
          />
        </label>

        <label className="text-xs text-zinc-400">
          BPM max
          <input
            type="number"
            inputMode="numeric"
            min={0}
            max={400}
            value={bpmMax}
            onChange={(e) => changeFilter(setBpmMax, e.target.value)}
            placeholder="—"
            className="ml-2 w-20 rounded border border-zinc-700 bg-zinc-900 px-2 py-2 text-sm text-zinc-100"
          />
        </label>

        <label className="text-xs text-zinc-400">
          Key
          <input
            type="text"
            value={musicalKey}
            onChange={(e) => changeFilter(setMusicalKey, e.target.value)}
            placeholder="e.g. F# minor"
            className="ml-2 w-32 rounded border border-zinc-700 bg-zinc-900 px-2 py-2 text-sm text-zinc-100"
          />
        </label>
      </section>

      {/* State: loading */}
      {loading && !data && (
        <div className="space-y-2 py-8">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-14 animate-pulse rounded bg-zinc-800/60" />
          ))}
        </div>
      )}

      {/* State: error */}
      {error && (
        <div className="rounded border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">
          <p>{error}</p>
          <button
            onClick={() => void loadTracks()}
            className="mt-2 rounded bg-red-500/80 px-3 py-1 text-xs font-medium text-black hover:bg-red-400"
          >
            Retry
          </button>
        </div>
      )}

      {/* State: empty (no import) */}
      {!loading && !error && data && total === 0 && !search && (
        <div className="rounded border border-zinc-800 bg-zinc-900/50 p-8 text-center text-zinc-400">
          <p>No tracks imported yet.</p>
          <p className="mt-1 text-sm">
            Connect Spotify and import your Liked Songs to build your crate.
          </p>
        </div>
      )}

      {/* State: no search results */}
      {!loading && !error && data && total === 0 && search && (
        <div className="rounded border border-zinc-800 bg-zinc-900/50 p-8 text-center text-zinc-400">
          <p>
            No tracks match <span className="text-zinc-100">“{search}”</span>.
          </p>
        </div>
      )}

      {/* Track list */}
      {!loading && !error && data && total > 0 && (
        <>
          <div className="overflow-hidden rounded-lg border border-zinc-800">
            <div className="grid grid-cols-[auto_1fr_1fr_56px_72px_56px_72px_72px] gap-3 border-b border-zinc-800 bg-zinc-900 px-4 py-2 text-[11px] uppercase tracking-wide text-zinc-500">
              <div />
              <div>Track / Artist</div>
              <div>Album</div>
              <div className="text-right">Year</div>
              <div className="text-right">BPM</div>
              <div className="text-right">Key</div>
              <div className="text-right">Conf.</div>
              <div className="text-right">Source</div>
            </div>
            <ul>
              {items.map((t) => {
                const bpm = t.musical_attributes?.tempo_bpm;
                const key = t.musical_attributes?.musical_key;
                const primary = bpm ?? key ?? null;
                return (
                  <li key={`${t.provider}:${t.provider_track_id}`}>
                    <button
                      onClick={() => setSelected(t)}
                      className="grid w-full grid-cols-[auto_1fr_1fr_56px_72px_56px_72px_72px] items-center gap-3 border-b border-zinc-800/60 px-4 py-2 text-left text-sm transition-colors hover:bg-zinc-800/50"
                    >
                      <TrackArtwork track={t} />
                      <div className="min-w-0">
                        <div className="truncate font-medium text-zinc-100">
                          {t.title}
                        </div>
                        <div className="truncate text-xs text-zinc-400">
                          {artistLine(t.artists)}
                        </div>
                      </div>
                      <div className="truncate text-zinc-300">{t.album ?? "—"}</div>
                      <div className="text-right text-zinc-400">
                        {formatYear(t.release_date)}
                      </div>
                      <div className="text-right tabular-nums text-zinc-200">
                        {formatBpm(bpm?.value)}
                      </div>
                      <div className="text-right text-zinc-200">
                        {formatMusicalKey(key?.value)}
                      </div>
                      <div className="text-right tabular-nums text-xs text-zinc-500">
                        {formatConfidence(primary?.confidence ?? null)}
                      </div>
                      <div className="text-right">
                        <span className="rounded bg-zinc-800 px-2 py-0.5 text-[11px] uppercase text-zinc-300">
                          {musicalSourceLabel(primary?.source ?? t.provider)}
                        </span>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* Pagination */}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
            <div className="text-zinc-400">
              <span className="text-zinc-100">{total.toLocaleString()}</span> tracks
              · page{" "}
              <span className="text-zinc-100">
                {page}
              </span> of {totalPages}
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs text-zinc-400">
                Per page
                <select
                  value={pageSize}
                  onChange={(e) =>
                    changeFilter(setPageSize, Number(e.target.value))
                  }
                  className="ml-2 rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm text-zinc-100"
                >
                  {PAGE_SIZES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="rounded border border-zinc-700 px-3 py-1 disabled:opacity-40 hover:bg-zinc-800"
              >
                Prev
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="rounded border border-zinc-700 px-3 py-1 disabled:opacity-40 hover:bg-zinc-800"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}

      {/* Detail panel */}
      {selected && (
        <div
          className="fixed inset-0 z-40 flex justify-end bg-black/60"
          onClick={() => setSelected(null)}
        >
          <div
            className="h-full w-full max-w-md overflow-y-auto border-l border-zinc-800 bg-zinc-950 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between">
              <h2 className="text-lg font-semibold">Track detail</h2>
              <button
                onClick={() => setSelected(null)}
                className="text-zinc-400 hover:text-zinc-100"
              >
                ✕
              </button>
            </div>

            <div className="mt-4 flex gap-4">
              <TrackArtwork track={selected} />
              <div className="min-w-0">
                <p className="truncate text-lg font-medium">{selected.title}</p>
                <p className="truncate text-zinc-400">
                  {artistLine(selected.artists)}
                </p>
                <p className="truncate text-sm text-zinc-500">
                  {selected.album ?? "Unknown album"}
                </p>
              </div>
            </div>

            <dl className="mt-6 space-y-2 text-sm">
              <Row label="Duration" value={formatDuration(selected.duration_ms)} />
              <Row label="Release date" value={fmtDate(selected.release_date)} />
              <Row label="Provider" value={selected.provider} />
              <Row label="Spotify ID" value={selected.provider_track_id} />
              <Row label="ISRC" value={selected.isrc ?? "—"} />
              <Row
                label="MusicBrainz"
                value={selected.musicbrainz_recording_id ?? "—"}
              />
              <Row
                label="Saved at"
                value={selected.saved_at ? fmtDate(selected.saved_at) : "—"}
              />
            </dl>

            {/* MUSICAL ANALYSIS */}
            <div className="mt-6 rounded-lg border border-emerald-900/60 bg-emerald-950/20 p-4">
              <p className="mb-2 text-[11px] uppercase tracking-wide text-emerald-400">
                Musical analysis
              </p>
              {(() => {
                const attrs = selected.musical_attributes || {};
                const bpm = attrs.tempo_bpm;
                const key = attrs.musical_key;
                if (!bpm && !key) {
                  return (
                    <p className="text-sm text-zinc-400">
                      Not enriched yet. Run{" "}
                      <code className="rounded bg-zinc-800 px-1 py-0.5 text-xs">
                        python -m app.cli enrich-library --source getsongbpm
                      </code>{" "}
                      to backfill.
                    </p>
                  );
                }
                return (
                  <dl className="space-y-2 text-sm">
                    <Row label="BPM" value={formatBpm(bpm?.value)} />
                    <Row
                      label="Key"
                      value={formatMusicalKey(key?.value)}
                    />
                    <Row
                      label="Source"
                      value={musicalSourceLabel(
                        (bpm ?? key)?.source ?? null
                      )}
                    />
                    <Row
                      label="Match confidence"
                      value={formatConfidence(
                        (bpm ?? key)?.confidence ?? null
                      )}
                    />
                  </dl>
                );
              })()}
            </div>

            {detailLoading && (
              <p className="mt-4 text-xs text-zinc-500">Loading identity detail…</p>
            )}
            {detailError && (
              <p className="mt-4 text-xs text-red-400">Detail failed: {detailError}</p>
            )}
            {detail && (
              <>
                <div className="mt-6">
                  <p className="mb-2 text-[11px] uppercase tracking-wide text-zinc-500">
                    Identifiers
                  </p>
                  <ul className="space-y-1 text-xs text-zinc-400">
                    {detail.identifiers.map((id) => (
                      <li key={`${id.type}-${id.value}`}>
                        <span className="text-zinc-500">{id.type}</span> — {id.value}
                      </li>
                    ))}
                  </ul>
                </div>

                {detail.identity_resolutions.length > 0 && (
                  <div className="mt-6">
                    <p className="mb-2 text-[11px] uppercase tracking-wide text-zinc-500">
                      Identity resolution
                    </p>
                    <ul className="space-y-3">
                      {detail.identity_resolutions.map((r) => (
                        <li key={r.id} className="rounded border border-zinc-800 p-3 text-xs">
                          <div className="flex items-center justify-between">
                            <span className="text-zinc-300">{r.query_type}: {r.query_value}</span>
                            <StatusBadge status={r.status} />
                          </div>
                          {r.matched_identifier && (
                            <p className="mt-1 text-zinc-400">Matched: {r.matched_identifier}</p>
                          )}
                          {r.confidence != null && (
                            <p className="text-zinc-500">Confidence: {r.confidence.toFixed(2)}</p>
                          )}
                          {r.resolved_at && (
                            <p className="text-zinc-500">Resolved at: {fmtDate(r.resolved_at)}</p>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {detail.musical_attribute_history && detail.musical_attribute_history.length > 0 && (
                  <div className="mt-6">
                    <p className="mb-2 text-[11px] uppercase tracking-wide text-zinc-500">
                      Attribute history
                    </p>
                    <ul className="space-y-1 text-xs text-zinc-400">
                      {detail.musical_attribute_history.map((h, i) => (
                        <li key={`${h.attribute_type}-${h.source_name}-${i}`}>
                          <span className="text-zinc-500">{h.attribute_type}</span>{" "}
                          — {JSON.stringify(h.value)} from{" "}
                          <span className="text-zinc-300">{musicalSourceLabel(h.source_name)}</span>
                          {h.is_current ? (
                            <span className="ml-2 rounded bg-emerald-900 px-1.5 py-0.5 text-[10px] uppercase text-emerald-200">
                              current
                            </span>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}

            <div className="mt-6">
              <p className="mb-2 text-[11px] uppercase tracking-wide text-zinc-500">
                Data provenance
              </p>
              <ul className="space-y-1 text-xs text-zinc-400">
                <li>Title — Spotify</li>
                <li>Artist — Spotify</li>
                <li>Album — Spotify</li>
                {selected.isrc ? <li>ISRC — Spotify</li> : <li>ISRC — not provided</li>}
                <li>
                  BPM / Key —{" "}
                  {selected.musical_attributes?.tempo_bpm?.source
                    ? musicalSourceLabel(selected.musical_attributes.tempo_bpm.source)
                    : "not yet enriched"}
                </li>
              </ul>
            </div>

            {selected.provider_url && (
              <a
                href={selected.provider_url}
                target="_blank"
                rel="noreferrer"
                className="mt-6 inline-block rounded bg-emerald-500 px-4 py-2 text-sm font-medium text-black hover:bg-emerald-400"
              >
                Open in Spotify
              </a>
            )}
          </div>
        </div>
      )}

      <footer className="mt-12 border-t border-zinc-800 pt-4 text-center text-[11px] text-zinc-500">
        Music metadata via{" "}
        <a
          href={ATTRIBUTION_URL}
          target="_blank"
          rel="noreferrer"
          className="text-zinc-400 underline-offset-2 hover:text-zinc-200 hover:underline"
        >
          GetSongBPM
        </a>
        .
      </footer>
    </main>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-zinc-800/60 pb-2">
      <dt className="text-zinc-500">{label}</dt>
      <dd className="truncate text-right text-zinc-200">{value}</dd>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    MATCHED: "bg-emerald-900 text-emerald-200",
    NO_MATCH: "bg-zinc-800 text-zinc-300",
    AMBIGUOUS: "bg-orange-900 text-orange-200",
    ERROR: "bg-red-900 text-red-200",
    DEFERRED: "bg-zinc-800 text-zinc-400",
  };
  const cls = map[status] || "bg-zinc-800 text-zinc-300";
  return <span className={`rounded px-2 py-0.5 text-[11px] uppercase ${cls}`}>{status}</span>;
}
