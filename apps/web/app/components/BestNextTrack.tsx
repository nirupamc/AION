// AION Best Next Track — connected possibilities visualization
// Selected track as center, candidates as connected nodes with score lines

"use client";

import React, { useState } from "react";
import { colors, scoreColor } from "../lib/tokens";
import { SectionLabel, ScorePill } from "../lib/components";

interface BestNextTrackProps {
  recommendations: any[];
  energyIntent: "maintain" | "build" | "drop";
  onSelectIntent: (intent: "maintain" | "build" | "drop") => void;
  onSelectTrack: (trackId: number) => void;
}

export function BestNextTrack({ recommendations, energyIntent, onSelectIntent, onSelectTrack }: BestNextTrackProps) {
  const [expanded, setExpanded] = useState<number | null>(null);

  if (!recommendations || recommendations.length === 0) {
    return (
      <div className="aion-surface p-4">
        <SectionLabel>Best Next Track</SectionLabel>
        <p className="mt-3 text-sm text-aion-text-muted">
          No recommendations — missing BPM/key/energy for candidates
        </p>
      </div>
    );
  }

  return (
    <div className="aion-surface p-4">
      <div className="flex items-baseline justify-between">
        <SectionLabel>Best Next Track</SectionLabel>
        <div className="flex gap-1">
          {(["maintain", "build", "drop"] as const).map((opt) => (
            <button
              key={opt}
              onClick={() => onSelectIntent(opt)}
              className={`rounded px-2 py-0.5 text-[11px] font-mono capitalize transition-colors ${
                energyIntent === opt
                  ? "bg-aion-acid/20 text-aion-acid-bright"
                  : "text-aion-text-muted hover:text-aion-text-secondary hover:bg-aion-elevated"
              }`}
            >
              {opt}
            </button>
          ))}
        </div>
      </div>

      {/* Score legend */}
      <div className="mt-2 flex items-center gap-3 text-[10px] text-aion-text-faint">
        <span>90+ excellent</span>
        <span>·</span>
        <span>75–89 strong</span>
        <span>·</span>
        <span>60–74 usable</span>
        <span>·</span>
        <span>&lt;60 risky</span>
      </div>

      <ul className="mt-3 space-y-1">
        {recommendations.map((rec: any, idx: number) => {
          const isExpanded = expanded === rec.track_id;
          return (
            <li key={rec.track_id} className="group">
              <button
                onClick={() => onSelectTrack(rec.track_id)}
                className="w-full text-left rounded px-3 py-2.5 transition-colors hover:bg-aion-elevated/50"
              >
                <div className="flex items-center gap-3">
                  {/* Rank indicator */}
                  <span className="aion-metric text-[11px] text-aion-text-faint w-4 shrink-0">
                    {idx + 1}
                  </span>

                  {/* Score connection line */}
                  <div className="relative w-12 shrink-0">
                    <div className="h-px w-full" style={{ background: "rgba(255,255,255,0.06)" }} />
                    <div
                      className="absolute top-0 left-0 h-px"
                      style={{
                        width: `${rec.transition_score}%`,
                        background: scoreColor(rec.transition_score),
                        opacity: 0.7,
                      }}
                    />
                  </div>

                  {/* Track info */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <p className="truncate text-sm text-aion-text">{rec.title ?? `Track ${rec.track_id}`}</p>
                      <span className="text-[11px] text-aion-text-faint shrink-0">{rec.artist ?? ""}</span>
                    </div>
                    <div className="mt-0.5 flex items-center gap-1.5 text-[10px] font-mono text-aion-text-muted">
                      <span>{rec.bpm ? `${rec.bpm} BPM` : "—"}</span>
                      <span>·</span>
                      <span style={{ color: colors.accent.mineral }}>{rec.camelot ?? "—"}</span>
                      {rec.energy != null && (
                        <>
                          <span>·</span>
                          <span>{rec.energy.toFixed(2)}</span>
                        </>
                      )}
                      <span>·</span>
                      <span style={{ color: colors.accent.violet }}>{rec.dominant_mood ?? "—"}</span>
                      <span>·</span>
                      <span style={{ color: colors.accent.mineral }}>{rec.dominant_vibe ?? "—"}</span>
                    </div>
                  </div>

                  {/* Score */}
                  <span className="aion-metric text-sm font-bold shrink-0" style={{ color: scoreColor(rec.transition_score) }}>
                    {rec.transition_score}
                  </span>

                  {/* Expand toggle */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setExpanded(isExpanded ? null : rec.track_id);
                    }}
                    className="text-[10px] text-aion-text-faint hover:text-aion-text-muted shrink-0"
                  >
                    {isExpanded ? "−" : "+"}
                  </button>
                </div>

                {/* Reason line */}
                <p className="ml-16 mt-1 text-[10px] text-aion-text-faint truncate">
                  {rec.reasons?.slice(0, 2).join(" · ")}
                </p>
              </button>

              {/* Expanded breakdown */}
              {isExpanded && (
                <div className="ml-16 mr-3 mb-2 rounded border border-aion-border bg-aion-raised p-3">
                  <div className="grid grid-cols-2 gap-1.5 text-[11px]">
                    {Object.entries(rec.components ?? {}).map(([k, v]: any) => (
                      <div key={k} className="flex justify-between">
                        <span className="text-aion-text-muted capitalize">{k}</span>
                        <span className={`font-mono ${v == null ? "text-aion-text-faint" : "text-aion-text-secondary"}`}>{v ?? "—"}</span>
                      </div>
                    ))}
                  </div>
                  {rec.warnings?.length > 0 && (
                    <p className="mt-2 text-[10px] text-aion-clay">{rec.warnings.join(" · ")}</p>
                  )}
                  {rec.missing_components?.length > 0 && (
                    <p className="mt-1 text-[10px] text-aion-text-faint">Missing: {rec.missing_components.join(", ")}</p>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
