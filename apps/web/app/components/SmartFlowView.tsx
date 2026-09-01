// AION Smart Flow — signature path visualization
// Flowing path with track nodes, transition connections, energy curve, weakest link

"use client";

import React, { useState } from "react";
import { colors, scoreColor } from "../lib/tokens";
import { SectionLabel, MetricReadout, ScorePill, GraphContainer } from "../lib/components";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";

interface SmartFlowViewProps {
  result: any;
  onSelectTrack: (trackId: number) => void;
}

export function SmartFlowView({ result, onSelectTrack }: SmartFlowViewProps) {
  const [expanded, setExpanded] = useState<number | null>(null);

  if (!result) return null;

  const seq = result.sequence ?? [];
  const hasSequence = seq.length > 0;

  // Find weakest transition
  let weakestIdx = -1;
  let weakestScore = 101;
  for (let i = 1; i < seq.length; i++) {
    const t = seq[i].transition_from_previous;
    if (t && t.score < weakestScore) {
      weakestScore = t.score;
      weakestIdx = i;
    }
  }

  return (
    <div className="space-y-6">
      {/* ─── FLOW SUMMARY ─── */}
      <div className="aion-surface p-5">
        <div className="flex items-baseline justify-between">
          <SectionLabel>Flow Summary</SectionLabel>
          <span className="text-[10px] text-aion-text-faint font-mono">
            {result.candidate_pool_size} candidates · {result.generation_time_ms}ms · beam {result.beam_width}
          </span>
        </div>
        <div className="mt-4 grid grid-cols-4 gap-4">
          <div>
            <SectionLabel>Overall</SectionLabel>
            <p className="aion-metric text-3xl mt-1" style={{ color: scoreColor(result.overall_sequence_score) }}>
              {result.overall_sequence_score}
            </p>
          </div>
          <div>
            <SectionLabel>Average</SectionLabel>
            <p className="aion-metric text-3xl mt-1 text-aion-text">
              {result.average_transition_score ?? "—"}
            </p>
          </div>
          <div>
            <SectionLabel>Weakest</SectionLabel>
            <p
              className="aion-metric text-3xl mt-1"
              style={{ color: result.minimum_transition_score != null && result.minimum_transition_score < 60 ? colors.state.error : colors.state.success }}
            >
              {result.minimum_transition_score ?? "—"}
            </p>
          </div>
          <div>
            <SectionLabel>Status</SectionLabel>
            <p className="text-sm text-aion-text-secondary mt-1">{result.status}</p>
          </div>
        </div>
        {result.warnings?.length > 0 && (
          <div className="mt-3 rounded border border-aion-border px-3 py-2">
            <p className="text-[11px] text-aion-clay-bright">{result.warnings.join(" · ")}</p>
          </div>
        )}
      </div>

      {/* ─── ENERGY CURVE ─── */}
      {hasSequence && (
        <GraphContainer title="Energy Curve" meta={`${result.energy_shape} shape`}>
          <div style={{ height: 160 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={result.energy_profile.map((t: number, i: number) => ({
                  idx: i + 1,
                  target: t,
                  actual: result.actual_energies[i],
                }))}
              >
                <XAxis
                  dataKey="idx"
                  tick={{ fontSize: 9, fill: "var(--aion-text-faint)", fontFamily: "'JetBrains Mono', monospace" }}
                  axisLine={{ stroke: "rgba(255,255,255,0.04)" }}
                  tickLine={false}
                />
                <YAxis
                  domain={[0, 1]}
                  tick={{ fontSize: 9, fill: "var(--aion-text-faint)", fontFamily: "'JetBrains Mono', monospace" }}
                  axisLine={false}
                  tickLine={false}
                  width={30}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--aion-overlay)",
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 6,
                    fontSize: 11,
                    fontFamily: "'JetBrains Mono', monospace",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="target"
                  stroke={colors.accent.clay}
                  strokeDasharray="6 4"
                  dot={false}
                  strokeWidth={1.5}
                  opacity={0.6}
                />
                <Line
                  type="monotone"
                  dataKey="actual"
                  stroke={colors.accent.moss}
                  dot={{ r: 3, fill: colors.accent.moss, strokeWidth: 0 }}
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex items-center gap-4 text-[10px] text-aion-text-faint">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-[2px] w-4" style={{ background: colors.accent.clay, opacity: 0.6 }} />
              Target ({result.energy_shape})
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-[2px] w-4 rounded" style={{ background: colors.accent.moss }} />
              Actual
            </span>
          </div>
        </GraphContainer>
      )}

      {/* ─── FLOW PATH ─── */}
      {hasSequence && (
        <div>
          <SectionLabel className="mb-4">Sequence</SectionLabel>
          <div className="relative">
            {/* Vertical connection line */}
            <div
              className="absolute left-[18px] top-0 bottom-0 w-px"
              style={{ background: "rgba(255,255,255,0.06)" }}
            />

            <div className="space-y-0">
              {seq.map((item: any, idx: number) => {
                const isWeakest = idx === weakestIdx;
                const isExpanded = expanded === item.position;

                return (
                  <div key={item.position} className="relative">
                    {/* Track node */}
                    <div
                      className={`flex items-start gap-4 py-3 pl-0 pr-3 cursor-pointer rounded-r transition-colors ${
                        isExpanded ? "bg-aion-elevated/50" : "hover:bg-aion-elevated/30"
                      }`}
                      onClick={() => setExpanded(isExpanded ? null : item.position)}
                    >
                      {/* Node circle */}
                      <div className="relative z-10 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border"
                        style={{
                          background: isWeakest ? "rgba(138,90,90,0.15)" : "var(--aion-raised)",
                          borderColor: isWeakest ? colors.state.error : "rgba(255,255,255,0.08)",
                        }}
                      >
                        <span className="aion-metric text-xs" style={{ color: isWeakest ? colors.state.error : "var(--aion-text-muted)" }}>
                          {item.position}
                        </span>
                      </div>

                      {/* Content */}
                      <div className="min-w-0 flex-1 pt-0.5">
                        <div className="flex items-baseline gap-2">
                          <p className="truncate text-sm text-aion-text font-medium">
                            {item.track.title ?? `Track ${item.track.track_id}`}
                          </p>
                          <span className="text-[11px] text-aion-text-faint shrink-0">
                            {item.track.artist ?? ""}
                          </span>
                        </div>

                        {/* Metadata row */}
                        <div className="mt-1 flex items-center gap-2 text-[11px] font-mono text-aion-text-muted">
                          {item.track.bpm && <span>{item.track.bpm}</span>}
                          {item.track.bpm && <span className="text-aion-text-faint">·</span>}
                          <span style={{ color: colors.accent.mineral }}>{item.track.camelot ?? "—"}</span>
                          {item.track.energy != null && (
                            <>
                              <span className="text-aion-text-faint">·</span>
                              <span>{item.track.energy.toFixed(2)}</span>
                            </>
                          )}
                          {item.track.dominant_mood && (
                            <>
                              <span className="text-aion-text-faint">·</span>
                              <span style={{ color: colors.accent.violet }}>{item.track.dominant_mood}</span>
                            </>
                          )}
                          {item.track.dominant_vibe && (
                            <>
                              <span className="text-aion-text-faint">·</span>
                              <span style={{ color: colors.accent.mineral }}>{item.track.dominant_vibe}</span>
                            </>
                          )}
                        </div>

                        {/* Transition from previous */}
                        {item.transition_from_previous && (
                          <div className="mt-2 flex items-center gap-2">
                            <span className="text-aion-text-faint text-[10px]">↓</span>
                            <ScorePill score={item.transition_from_previous.score} />
                            <span className="text-[10px] text-aion-text-faint truncate">
                              {item.transition_from_previous.reasons?.slice(0, 2).join(" · ")}
                            </span>
                            {isWeakest && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded"
                                style={{ background: "rgba(138,90,90,0.15)", color: colors.state.error }}
                              >
                                weakest
                              </span>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Score badge */}
                      {item.transition_from_previous && (
                        <div className="shrink-0 pt-1">
                          <span
                            className="aion-metric text-lg font-bold"
                            style={{ color: scoreColor(item.transition_from_previous.score) }}
                          >
                            {item.transition_from_previous.score}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Expanded breakdown */}
                    {isExpanded && item.transition_from_previous && (
                      <div className="ml-13 pl-9 pb-3">
                        <div className="rounded border border-aion-border bg-aion-raised p-3 space-y-2">
                          <div className="grid grid-cols-3 gap-2 text-[11px]">
                            {Object.entries(item.transition_from_previous.components ?? {}).map(([k, v]: any) => (
                              <div key={k} className="flex justify-between">
                                <span className="text-aion-text-muted capitalize">{k}</span>
                                <span className="font-mono text-aion-text-secondary">{v ?? "—"}</span>
                              </div>
                            ))}
                          </div>
                          {item.transition_from_previous.warnings?.length > 0 && (
                            <p className="text-[10px] text-aion-clay">
                              {item.transition_from_previous.warnings.join(" · ")}
                            </p>
                          )}
                          {item.transition_from_previous.missing_components?.length > 0 && (
                            <p className="text-[10px] text-aion-text-faint">
                              Missing: {item.transition_from_previous.missing_components.join(", ")}
                            </p>
                          )}
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectTrack(item.track.track_id);
                          }}
                          className="mt-2 text-[11px] text-aion-acid hover:underline"
                        >
                          Open in inspector →
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Weakest link summary */}
            {weakestIdx >= 0 && (
              <div className="mt-4 rounded border px-3 py-2" style={{ borderColor: "rgba(138,90,90,0.2)", background: "rgba(138,90,90,0.05)" }}>
                <p className="text-[11px] font-medium" style={{ color: colors.state.error }}>
                  Weakest transition: {seq[weakestIdx - 1]?.position} → {seq[weakestIdx]?.position} · {weakestScore} / 100
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
