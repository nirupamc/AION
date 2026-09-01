// AION Track Inspector — right-side drawer with organic technical layout
// Sections: Identity, Musical, Character, Texture, Mood/Vibe, Provenance, Best Next

"use client";

import React from "react";
import { colors } from "../lib/tokens";
import {
  SectionLabel,
  InspectorGroup,
  InspectorRow,
  SignalBar,
  EmptyState,
  StatusDot,
} from "../lib/components";
import {
  formatBpm,
  formatMusicalKey,
  formatUnit,
  formatLoudness,
  formatTimeSignature,
  formatDuration,
  musicalSourceLabel,
  formatConfidence,
  artistLine,
  type TrackDetailResponse,
  type TrackItem,
} from "../lib/api";

interface TrackInspectorProps {
  track: TrackItem;
  detail: TrackDetailResponse | null;
  detailLoading: boolean;
  detailError: string | null;
  onClose: () => void;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 10);
}

export function TrackInspector({ track, detail, detailLoading, detailError, onClose }: TrackInspectorProps) {
  const attrs: any = track.musical_attributes || {};
  const detailAttrs: any = detail?.musical_attributes || {};
  const a = { ...attrs, ...detailAttrs };
  const hasAny = a.tempo_bpm || a.musical_key || a.time_signature || a.energy || a.danceability || a.valence || a.acousticness;
  const char: any = (detail as any)?.music_character ?? (track as any)?.music_character;

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-black/50"
      onClick={onClose}
    >
      <div
        className="h-full w-full max-w-md overflow-y-auto border-l border-aion-border bg-aion-bg"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ─── HEADER ─── */}
        <div className="sticky top-0 z-10 flex items-start justify-between border-b border-aion-border bg-aion-bg/95 backdrop-blur-sm px-5 py-4">
          <div className="min-w-0 flex-1">
            <p className="truncate text-lg font-display font-bold text-aion-text">{track.title}</p>
            <p className="truncate text-sm text-aion-text-secondary">{artistLine(track.artists)}</p>
            <p className="mt-0.5 text-[11px] text-aion-text-faint">{track.album ?? "Unknown album"}</p>
          </div>
          <button
            onClick={onClose}
            className="ml-3 shrink-0 text-aion-text-muted hover:text-aion-text transition-colors"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        <div className="px-5 py-4 space-y-6">
          {/* ─── IDENTITY ─── */}
          <InspectorGroup label="Identity">
            <InspectorRow label="Duration">{formatDuration(track.duration_ms)}</InspectorRow>
            <InspectorRow label="Release">{fmtDate(track.release_date)}</InspectorRow>
            <InspectorRow label="Provider">{track.provider}</InspectorRow>
            <InspectorRow label="ISRC">{track.isrc ?? "—"}</InspectorRow>
            <InspectorRow label="Spotify ID">{track.provider_track_id}</InspectorRow>
          </InspectorGroup>

          {/* ─── MUSICAL ─── */}
          {hasAny ? (
            <InspectorGroup label="Musical" color={colors.accent.moss}>
              <div className="space-y-3">
                <div>
                  <SectionLabel className="!text-[9px] mb-1" color={colors.accent.moss}>BPM</SectionLabel>
                  <p className="aion-metric text-2xl text-aion-text">{formatBpm(a.tempo_bpm?.value)}</p>
                  <SignalBar
                    value={typeof a.tempo_bpm?.value === "number" ? a.tempo_bpm.value : 0}
                    max={200}
                    color={colors.accent.moss}
                    className="mt-1"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <SectionLabel className="!text-[9px] mb-1">Key</SectionLabel>
                    <p className="aion-metric text-sm text-aion-text">{formatMusicalKey(a.musical_key?.value)}</p>
                  </div>
                  <div>
                    <SectionLabel className="!text-[9px] mb-1">Camelot</SectionLabel>
                    <p className="aion-metric text-sm" style={{ color: colors.accent.mineral }}>{(a.camelot?.value as string) ?? "—"}</p>
                  </div>
                </div>
                <div>
                  <SectionLabel className="!text-[9px] mb-1">Time Signature</SectionLabel>
                  <p className="aion-metric text-sm text-aion-text">{formatTimeSignature(a.time_signature?.value)}</p>
                </div>
              </div>
            </InspectorGroup>
          ) : (
            <InspectorGroup label="Musical" color={colors.accent.moss}>
              <EmptyState>Not analyzed</EmptyState>
            </InspectorGroup>
          )}

          {/* ─── CHARACTER ─── */}
          <InspectorGroup label="Character" color={colors.accent.violet}>
            <div className="space-y-3">
              <div>
                <div className="flex items-baseline justify-between">
                  <SectionLabel className="!text-[9px]">Energy</SectionLabel>
                  <span className="aion-metric text-[11px] text-aion-text-secondary">{formatUnit(a.energy?.value)}</span>
                </div>
                <SignalBar
                  value={typeof a.energy?.value === "number" ? a.energy.value : 0}
                  max={1}
                  color={colors.accent.violet}
                  className="mt-1"
                />
              </div>
              <div>
                <div className="flex items-baseline justify-between">
                  <SectionLabel className="!text-[9px]">Danceability</SectionLabel>
                  <span className="aion-metric text-[11px] text-aion-text-secondary">{formatUnit(a.danceability?.value)}</span>
                </div>
                <SignalBar
                  value={typeof a.danceability?.value === "number" ? a.danceability.value : 0}
                  max={1}
                  color={colors.accent.violet}
                  className="mt-1"
                  height={2}
                />
              </div>
              <div>
                <div className="flex items-baseline justify-between">
                  <SectionLabel className="!text-[9px]">Valence</SectionLabel>
                  <span className="aion-metric text-[11px] text-aion-text-secondary">{formatUnit(a.valence?.value)}</span>
                </div>
                <SignalBar
                  value={typeof a.valence?.value === "number" ? a.valence.value : 0}
                  max={1}
                  color={colors.accent.violet}
                  className="mt-1"
                  height={2}
                />
              </div>
            </div>
          </InspectorGroup>

          {/* ─── TEXTURE ─── */}
          <InspectorGroup label="Texture">
            <InspectorRow label="Acousticness">{formatUnit(a.acousticness?.value)}</InspectorRow>
            <InspectorRow label="Instrumentalness">{formatUnit(a.instrumentalness?.value)}</InspectorRow>
            <InspectorRow label="Liveness">{formatUnit(a.liveness?.value)}</InspectorRow>
            <InspectorRow label="Speechiness">{formatUnit(a.speechiness?.value)}</InspectorRow>
            <InspectorRow label="Loudness">{formatLoudness(a.loudness_db?.value)}</InspectorRow>
          </InspectorGroup>

          {/* ─── MOOD / VIBE ─── */}
          {char && (char.moods?.length > 0 || char.vibes?.length > 0) && (
            <InspectorGroup label="Mood / Vibe" color={colors.accent.violet}>
              <div className="space-y-3">
                {char.dominant_mood && (
                  <div>
                    <SectionLabel className="!text-[9px] mb-1" color={colors.accent.violet}>Mood</SectionLabel>
                    <p className="text-sm text-aion-text capitalize">{char.dominant_mood}</p>
                    <div className="mt-1.5 space-y-1.5">
                      {char.moods?.slice(0, 3).map((m: any) => (
                        <div key={m.label}>
                          <div className="flex items-baseline justify-between text-[11px]">
                            <span className="text-aion-text-secondary capitalize">{m.label}</span>
                            <span className="aion-metric text-aion-text-faint">{Math.round(m.score * 100)}%</span>
                          </div>
                          <SignalBar
                            value={m.score}
                            max={1}
                            color={colors.accent.violet}
                            height={2}
                            className="mt-0.5"
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {char.dominant_vibe && (
                  <div>
                    <SectionLabel className="!text-[9px] mb-1" color={colors.accent.mineral}>Vibe</SectionLabel>
                    <p className="text-sm text-aion-text capitalize">{char.dominant_vibe}</p>
                    <div className="mt-1.5 space-y-1.5">
                      {char.vibes?.slice(0, 3).map((v: any) => (
                        <div key={v.label}>
                          <div className="flex items-baseline justify-between text-[11px]">
                            <span className="text-aion-text-secondary capitalize">{v.label}</span>
                            <span className="aion-metric text-aion-text-faint">{Math.round(v.score * 100)}%</span>
                          </div>
                          <SignalBar
                            value={v.score}
                            max={1}
                            color={colors.accent.mineral}
                            height={2}
                            className="mt-0.5"
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {char.set_role && (
                  <InspectorRow label="Set role">{char.set_role}</InspectorRow>
                )}
                <p className="text-[10px] text-aion-text-faint">
                  {char.source} · {char.analysis_version}
                </p>
              </div>
            </InspectorGroup>
          )}

          {/* ─── DATA PROVENANCE ─── */}
          <InspectorGroup label="Provenance">
            <InspectorRow label="Title">Spotify</InspectorRow>
            <InspectorRow label="BPM / Key">
              {a.tempo_bpm?.source ? musicalSourceLabel(a.tempo_bpm.source) : "Not enriched"}
            </InspectorRow>
            <InspectorRow label="Confidence">
              {formatConfidence(a.tempo_bpm?.confidence ?? null)}
            </InspectorRow>
          </InspectorGroup>

          {/* ─── IDENTIFIERS ─── */}
          {detail && detail.identifiers.length > 0 && (
            <InspectorGroup label="Identifiers">
              <div className="space-y-1">
                {detail.identifiers.map((id) => (
                  <div key={`${id.type}-${id.value}`} className="flex items-baseline justify-between gap-3 aion-hairline py-1">
                    <span className="text-[10px] text-aion-text-faint">{id.type}</span>
                    <span className="text-[11px] text-aion-text-muted font-mono truncate">{id.value}</span>
                  </div>
                ))}
              </div>
            </InspectorGroup>
          )}

          {/* ─── LOADING / ERROR ─── */}
          {detailLoading && (
            <p className="text-[11px] text-aion-text-faint">Loading detail…</p>
          )}
          {detailError && (
            <p className="text-[11px] text-aion-error">{detailError}</p>
          )}

          {/* ─── OPEN IN SPOTIFY ─── */}
          {track.provider_url && (
            <a
              href={track.provider_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded border border-aion-border px-4 py-2 text-sm text-aion-text-secondary hover:bg-aion-elevated hover:text-aion-text transition-colors"
            >
              Open in Spotify →
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
