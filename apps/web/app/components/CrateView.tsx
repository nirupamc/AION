// AION Crate — library table, redesigned for organic technical feel
// Dense, editorial, musical. Thin row separators, compact typography, monospaced metadata.

"use client";

import React, { useState } from "react";
import { colors } from "../lib/tokens";
import { SectionLabel, DataChip } from "../lib/components";
import {
  artistLine,
  formatBpm,
  formatMusicalKey,
  formatUnit,
  formatYear,
  formatConfidence,
  musicalSourceLabel,
  type TrackItem,
} from "../lib/api";

interface CrateViewProps {
  items: TrackItem[];
  total: number;
  page: number;
  totalPages: number;
  pageSize: number;
  loading: boolean;
  onSelectTrack: (track: TrackItem) => void;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}

export function CrateView({
  items,
  total,
  page,
  totalPages,
  pageSize,
  loading,
  onSelectTrack,
  onPageChange,
  onPageSizeChange,
}: CrateViewProps) {
  const PAGE_SIZES = [25, 50, 100];

  return (
    <div>
      {/* ─── TABLE ─── */}
      <div className="relative overflow-hidden rounded-lg">
        {/* Header */}
        <div className="grid grid-cols-[2.5rem_1fr_1fr_3rem_3.5rem_3rem_3rem_3rem_4.5rem_4.5rem_2.5rem_3.5rem] gap-x-2 border-b border-aion-border-strong bg-aion-raised/50 px-3 py-2">
          <div />
          <div className="text-[10px] uppercase tracking-wider text-aion-text-faint">Track</div>
          <div className="text-[10px] uppercase tracking-wider text-aion-text-faint">Album</div>
          <div className="text-right text-[10px] uppercase tracking-wider text-aion-text-faint">Year</div>
          <div className="text-right text-[10px] uppercase tracking-wider text-aion-text-faint">BPM</div>
          <div className="text-right text-[10px] uppercase tracking-wider text-aion-text-faint">Key</div>
          <div className="text-right text-[10px] uppercase tracking-wider text-aion-text-faint">Cam</div>
          <div className="text-right text-[10px] uppercase tracking-wider text-aion-text-faint">Energy</div>
          <div className="text-right text-[10px] uppercase tracking-wider text-aion-text-faint">Mood</div>
          <div className="text-right text-[10px] uppercase tracking-wider text-aion-text-faint">Vibe</div>
          <div className="text-right text-[10px] uppercase tracking-wider text-aion-text-faint">Conf</div>
          <div className="text-right text-[10px] uppercase tracking-wider text-aion-text-faint">Source</div>
        </div>

        {/* Rows */}
        <ul>
          {items.map((t) => {
            const bpm = t.musical_attributes?.tempo_bpm;
            const key = t.musical_attributes?.musical_key;
            const energy = t.musical_attributes?.energy;
            const camelot = (t.musical_attributes as any)?.camelot;
            const mc: any = (t as any).music_character;
            const primary = bpm ?? key ?? energy ?? camelot ?? null;

            return (
              <li key={`${t.provider}:${t.provider_track_id}`}>
                <button
                  onClick={() => onSelectTrack(t)}
                  className="group grid w-full grid-cols-[2.5rem_1fr_1fr_3rem_3.5rem_3rem_3rem_3rem_4.5rem_4.5rem_2.5rem_3.5rem] items-center gap-x-2 border-b border-aion-border-subtle px-3 py-2 text-left transition-colors hover:bg-aion-elevated/40"
                >
                  {/* Artwork */}
                  <TrackArtwork track={t} />

                  {/* Track / Artist */}
                  <div className="min-w-0">
                    <p className="truncate text-[13px] text-aion-text group-hover:text-aion-text transition-colors">
                      {t.title}
                    </p>
                    <p className="truncate text-[11px] text-aion-text-muted">
                      {artistLine(t.artists)}
                    </p>
                  </div>

                  {/* Album */}
                  <p className="truncate text-[11px] text-aion-text-faint">{t.album ?? "—"}</p>

                  {/* Year */}
                  <p className="text-right text-[11px] font-mono text-aion-text-faint">
                    {formatYear(t.release_date)}
                  </p>

                  {/* BPM */}
                  <p className="text-right text-[12px] font-mono text-aion-text-secondary tabular-nums">
                    {formatBpm(bpm?.value)}
                  </p>

                  {/* Key */}
                  <p className="text-right text-[11px] font-mono text-aion-text-secondary">
                    {formatMusicalKey(key?.value)}
                  </p>

                  {/* Camelot */}
                  <p className="text-right text-[11px] font-mono" style={{ color: colors.accent.mineral }}>
                    {(camelot?.value as string) ?? "—"}
                  </p>

                  {/* Energy */}
                  <p className="text-right text-[11px] font-mono text-aion-text-secondary tabular-nums">
                    {formatUnit(energy?.value)}
                  </p>

                  {/* Mood */}
                  <p className="text-right text-[11px] font-mono capitalize truncate" style={{ color: colors.accent.violet }}>
                    {mc?.dominant_mood ?? "—"}
                  </p>

                  {/* Vibe */}
                  <p className="text-right text-[11px] font-mono capitalize truncate" style={{ color: colors.accent.mineral }}>
                    {mc?.dominant_vibe ?? "—"}
                  </p>

                  {/* Confidence */}
                  <p className="text-right text-[10px] font-mono text-aion-text-faint tabular-nums">
                    {formatConfidence(primary?.confidence ?? null)}
                  </p>

                  {/* Source */}
                  <p className="text-right text-[9px] font-mono uppercase text-aion-text-faint">
                    {musicalSourceLabel(primary?.source ?? t.provider)}
                  </p>
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      {/* ─── PAGINATION ─── */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-[11px] text-aion-text-muted font-mono">
          <span className="text-aion-text-secondary">{total.toLocaleString()}</span> tracks
          {" · "}page <span className="text-aion-text-secondary">{page}</span>/{totalPages}
        </p>
        <div className="flex items-center gap-2">
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="rounded border border-aion-border bg-aion-raised px-2 py-1 text-[11px] font-mono text-aion-text-secondary"
          >
            {PAGE_SIZES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <button
            onClick={() => onPageChange(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="rounded border border-aion-border px-2.5 py-1 text-[11px] text-aion-text-muted hover:bg-aion-elevated disabled:opacity-30 transition-colors"
          >
            ← Prev
          </button>
          <button
            onClick={() => onPageChange(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="rounded border border-aion-border px-2.5 py-1 text-[11px] text-aion-text-muted hover:bg-aion-elevated disabled:opacity-30 transition-colors"
          >
            Next →
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Track artwork with fallback ─── */
function TrackArtwork({ track }: { track: TrackItem }) {
  const [failed, setFailed] = useState(false);
  const url = track.artwork_url;
  if (!url || failed) {
    return (
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-aion-raised text-[10px] font-mono text-aion-text-faint border border-aion-border-subtle">
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
      className="h-8 w-8 shrink-0 rounded object-cover bg-aion-raised"
    />
  );
}
