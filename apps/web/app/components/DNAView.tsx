// AION Library DNA — organic technical redesign
// Hero composition, distributions, Camelot wheel, scatter, mood/vibe

"use client";

import React from "react";
import type { LibraryDNA } from "../lib/api";
import { colors } from "../lib/tokens";
import { SectionLabel, MetricReadout, GraphContainer } from "../lib/components";
import { CamelotWheel } from "../components/CamelotWheel";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ScatterChart, Scatter, Cell,
} from "recharts";

interface DNAViewProps {
  dna: LibraryDNA;
  bpmBuckets: any[];
  energyBuckets: any[];
  scatterPoints: any[];
  selectedMood: string | null;
  selectedVibe: string | null;
  selectedCamelot: string | null;
  onSelectMood: (mood: string | null) => void;
  onSelectVibe: (vibe: string | null) => void;
  onSelectCamelot: (code: string) => void;
  onSelectScatterTrack: (trackId: number) => void;
  onClearFilters: () => void;
  hasActiveFilters: boolean;
}

export function DNAView({
  dna,
  bpmBuckets,
  energyBuckets,
  scatterPoints,
  selectedMood,
  selectedVibe,
  selectedCamelot,
  onSelectMood,
  onSelectVibe,
  onSelectCamelot,
  onSelectScatterTrack,
  onClearFilters,
  hasActiveFilters,
}: DNAViewProps) {
  return (
    <div className="space-y-8">
      {/* ─── HERO COMPOSITION ─── */}
      <div className="aion-surface relative overflow-hidden p-6 aion-contour">
        <div className="relative z-10">
          <SectionLabel>Library DNA</SectionLabel>
          <p className="mt-1 text-sm text-aion-text-secondary">
            {dna.enriched_tracks} / {dna.total_tracks} analyzed
            <span className="ml-2 text-aion-text-faint">· {dna.enrichment_percentage}% coverage</span>
          </p>

          {/* Key metrics — breathing composition */}
          <div className="mt-6 grid grid-cols-2 gap-6 md:grid-cols-4">
            <div>
              <SectionLabel>BPM Median</SectionLabel>
              <p className="aion-metric text-4xl mt-1 text-aion-text">
                {dna.tempo.median ?? "—"}
              </p>
              <p className="text-[11px] text-aion-text-faint font-mono mt-1">
                avg {dna.tempo.average ?? "—"} · {dna.tempo.dominant_range ?? ""}
              </p>
            </div>
            <div>
              <SectionLabel>Energy</SectionLabel>
              <p className="aion-metric text-4xl mt-1 text-aion-text">
                {dna.energy.average != null ? dna.energy.average.toFixed(2) : "—"}
              </p>
              <p className="text-[11px] text-aion-text-faint font-mono mt-1">
                median {dna.energy.median?.toFixed(2) ?? "—"}
              </p>
            </div>
            <div>
              <SectionLabel>Dominant Mood</SectionLabel>
              <p className="text-2xl font-display font-bold mt-1 text-aion-violet-bright capitalize">
                {dna.top_moods[0]?.label ?? "—"}
              </p>
              <p className="text-[11px] text-aion-text-faint font-mono mt-1">
                {dna.top_moods[0]?.count ?? 0} tracks
              </p>
            </div>
            <div>
              <SectionLabel>Dominant Camelot</SectionLabel>
              <p className="aion-metric text-4xl mt-1 text-aion-mineral-bright">
                {dna.top_camelots[0]?.label ?? "—"}
              </p>
              <p className="text-[11px] text-aion-text-faint font-mono mt-1">
                {dna.top_camelots[0]?.count ?? 0} tracks
              </p>
            </div>
          </div>

          <div className="mt-4 flex items-center gap-4 text-[11px] text-aion-text-faint">
            <span>
              Dominant vibe: <span className="text-aion-text-secondary capitalize">{dna.top_vibes[0]?.label ?? "—"}</span>
            </span>
            <span>·</span>
            <span>
              Set role peak <span className="text-aion-text-secondary">{dna.set_roles.find((r: any) => r.label === "peak")?.percentage ?? 0}%</span>
            </span>
          </div>

          {hasActiveFilters && (
            <button
              onClick={onClearFilters}
              className="mt-4 rounded border border-aion-border px-3 py-1 text-[11px] text-aion-text-muted hover:bg-aion-elevated hover:text-aion-text-secondary transition-colors"
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      {/* ─── DISTRIBUTIONS ─── */}
      <div className="grid gap-6 md:grid-cols-2">
        <GraphContainer title="BPM Distribution" meta="5 BPM buckets">
          <div style={{ height: 180 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={bpmBuckets}>
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 9, fill: "var(--aion-text-faint)", fontFamily: "'JetBrains Mono', monospace" }}
                  interval={1}
                  axisLine={{ stroke: "rgba(255,255,255,0.04)" }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 9, fill: "var(--aion-text-faint)", fontFamily: "'JetBrains Mono', monospace" }}
                  allowDecimals={false}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--aion-overlay)",
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 6,
                    fontSize: 11,
                    fontFamily: "'JetBrains Mono', monospace",
                  }}
                  cursor={{ fill: "rgba(255,255,255,0.03)" }}
                />
                <Bar
                  dataKey="count"
                  fill={colors.graph.primary}
                  radius={[3, 3, 0, 0]}
                  cursor="pointer"
                  onClick={(d: any) => {}}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-1 text-[10px] text-aion-text-faint">Click bar to filter library</p>
        </GraphContainer>

        <GraphContainer title="Energy Distribution" meta="0.0 – 1.0">
          <div style={{ height: 180 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={energyBuckets}>
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 9, fill: "var(--aion-text-faint)", fontFamily: "'JetBrains Mono', monospace" }}
                  axisLine={{ stroke: "rgba(255,255,255,0.04)" }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 9, fill: "var(--aion-text-faint)", fontFamily: "'JetBrains Mono', monospace" }}
                  allowDecimals={false}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--aion-overlay)",
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 6,
                    fontSize: 11,
                    fontFamily: "'JetBrains Mono', monospace",
                  }}
                  cursor={{ fill: "rgba(255,255,255,0.03)" }}
                />
                <Bar
                  dataKey="count"
                  fill={colors.graph.secondary}
                  radius={[3, 3, 0, 0]}
                  cursor="pointer"
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </GraphContainer>
      </div>

      {/* ─── CAMELOT + MOOD + VIBE ─── */}
      <div className="grid gap-6 md:grid-cols-3">
        <GraphContainer title="Camelot Wheel">
          <CamelotWheel
            distribution={dna.camelot_distribution}
            selected={selectedCamelot}
            onSelect={(code) => onSelectCamelot(code)}
            size={260}
          />
          <p className="mt-2 text-[10px] text-aion-text-faint text-center">
            Click cell to filter · Selected illuminates compatible neighbors
          </p>
        </GraphContainer>

        <GraphContainer title="Mood Distribution">
          <div style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dna.mood_distribution} layout="vertical">
                <XAxis
                  type="number"
                  tick={{ fontSize: 9, fill: "var(--aion-text-faint)", fontFamily: "'JetBrains Mono', monospace" }}
                  axisLine={{ stroke: "rgba(255,255,255,0.04)" }}
                  tickLine={false}
                />
                <YAxis
                  dataKey="label"
                  type="category"
                  width={72}
                  tick={{ fontSize: 10, fill: "var(--aion-text-muted)" }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--aion-overlay)",
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 6,
                    fontSize: 11,
                  }}
                />
                <Bar
                  dataKey="count"
                  radius={[0, 3, 3, 0]}
                  cursor="pointer"
                  onClick={(d: any) => onSelectMood(d.label === selectedMood ? null : d.label)}
                >
                  {dna.mood_distribution.map((e: any, i: number) => (
                    <Cell
                      key={i}
                      fill={e.label === selectedMood ? colors.accent.violetBright : colors.accent.violet}
                      opacity={selectedMood && e.label !== selectedMood ? 0.3 : 1}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </GraphContainer>

        <GraphContainer title="Vibe Distribution">
          <div style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dna.vibe_distribution} layout="vertical">
                <XAxis
                  type="number"
                  tick={{ fontSize: 9, fill: "var(--aion-text-faint)", fontFamily: "'JetBrains Mono', monospace" }}
                  axisLine={{ stroke: "rgba(255,255,255,0.04)" }}
                  tickLine={false}
                />
                <YAxis
                  dataKey="label"
                  type="category"
                  width={72}
                  tick={{ fontSize: 10, fill: "var(--aion-text-muted)" }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "var(--aion-overlay)",
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 6,
                    fontSize: 11,
                  }}
                />
                <Bar
                  dataKey="count"
                  radius={[0, 3, 3, 0]}
                  cursor="pointer"
                  onClick={(d: any) => onSelectVibe(d.label === selectedVibe ? null : d.label)}
                >
                  {dna.vibe_distribution.map((e: any, i: number) => (
                    <Cell
                      key={i}
                      fill={e.label === selectedVibe ? colors.accent.mineralBright : colors.accent.mineral}
                      opacity={selectedVibe && e.label !== selectedVibe ? 0.3 : 1}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </GraphContainer>
      </div>

      {/* ─── BPM × ENERGY CONSTELLATION ─── */}
      <GraphContainer title="BPM × Energy Map" meta={`${scatterPoints.length} tracks`}>
        <div style={{ height: 320 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart>
              <XAxis
                type="number"
                dataKey="bpm"
                name="BPM"
                domain={["dataMin - 5", "dataMax + 5"]}
                tick={{ fontSize: 9, fill: "var(--aion-text-faint)", fontFamily: "'JetBrains Mono', monospace" }}
                axisLine={{ stroke: "rgba(255,255,255,0.04)" }}
                tickLine={false}
              />
              <YAxis
                type="number"
                dataKey="energy"
                name="Energy"
                domain={[0, 1]}
                tick={{ fontSize: 9, fill: "var(--aion-text-faint)", fontFamily: "'JetBrains Mono', monospace" }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                cursor={{ strokeDasharray: "3 3", stroke: "rgba(255,255,255,0.08)" }}
                content={({ active, payload }: any) => {
                  if (!active || !payload?.[0]) return null;
                  const p = payload[0].payload;
                  return (
                    <div className="aion-tooltip">
                      <p className="font-medium text-aion-text">{p.title}</p>
                      <p className="text-aion-text-secondary">{p.artist}</p>
                      <p className="font-mono text-[11px] text-aion-text-muted mt-1">
                        {p.bpm} BPM · {p.energy?.toFixed(2)} · {p.camelot ?? "—"}
                      </p>
                      <p className="text-[11px] text-aion-text-faint mt-0.5">
                        {p.mood ?? "—"} · {p.vibe ?? "—"}
                      </p>
                    </div>
                  );
                }}
              />
              <Scatter
                data={scatterPoints}
                cursor="pointer"
                onClick={(p: any) => { if (p?.track_id) onSelectScatterTrack(p.track_id); }}
              >
                {scatterPoints.map((_: any, i: number) => (
                  <Cell
                    key={i}
                    fill={colors.graph.primary}
                    fillOpacity={0.6}
                    stroke={colors.graph.primary}
                    strokeOpacity={0.3}
                    r={3}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-1 text-[10px] text-aion-text-faint">
          Hover for details · Click to select track · Capped at 500 points
        </p>
      </GraphContainer>
    </div>
  );
}
