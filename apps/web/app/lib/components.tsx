// AION reusable UI primitives — organic technical visual system

import React from "react";
import { scoreColor } from "./tokens";

/* ─── SectionLabel ─── */
export function SectionLabel({ children, className = "", color }: { children: React.ReactNode; className?: string; color?: string }) {
  return (
    <p className={`aion-section-label ${className}`} style={color ? { color } : undefined}>{children}</p>
  );
}

/* ─── MetricReadout — large technical number with label ─── */
export function MetricReadout({
  value,
  label,
  unit,
  color,
  size = "lg",
}: {
  value: string | number;
  label: string;
  unit?: string;
  color?: string;
  size?: "sm" | "md" | "lg" | "xl";
}) {
  const sizeClass = {
    sm: "text-lg",
    md: "text-2xl",
    lg: "text-3xl",
    xl: "text-5xl",
  }[size];
  return (
    <div>
      <SectionLabel>{label}</SectionLabel>
      <p className={`aion-metric ${sizeClass} mt-1`} style={color ? { color } : undefined}>
        {value}
        {unit && <span className="ml-1 text-sm text-aion-text-muted">{unit}</span>}
      </p>
    </div>
  );
}

/* ─── DataChip — compact metadata tag ─── */
export function DataChip({
  children,
  color,
  active = false,
  onClick,
}: {
  children: React.ReactNode;
  color?: string;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <span
      onClick={onClick}
      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-mono ${
        active ? "bg-white/10 text-aion-text" : "text-aion-text-secondary"
      } ${onClick ? "cursor-pointer hover:bg-white/5" : ""}`}
      style={color ? { color } : undefined}
    >
      {children}
    </span>
  );
}

/* ─── SignalBar — thin horizontal trace ─── */
export function SignalBar({
  value,
  max = 1,
  color = "var(--aion-moss)",
  height = 3,
  className = "",
}: {
  value: number;
  max?: number;
  color?: string;
  height?: number;
  className?: string;
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className={`aion-signal ${className}`} style={{ height }}>
      <div
        className="aion-signal-fill"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  );
}

/* ─── ScorePill — colored score ─── */
export function ScorePill({ score }: { score: number }) {
  return (
    <span
      className="aion-metric text-xs font-medium"
      style={{ color: scoreColor(score) }}
    >
      {score}
    </span>
  );
}

/* ─── InspectorGroup — section within track inspector ─── */
export function InspectorGroup({
  label,
  color = "var(--aion-text-muted)",
  children,
}: {
  label: string;
  color?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <SectionLabel color={color}>{label}</SectionLabel>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

/* ─── InspectorRow — key-value pair in inspector ─── */
export function InspectorRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 aion-hairline py-1.5">
      <span className="text-[11px] text-aion-text-muted shrink-0">{label}</span>
      <span className="text-right text-[13px] text-aion-text-secondary font-mono truncate">{children}</span>
    </div>
  );
}

/* ─── StatusDot — inline status indicator ─── */
export function StatusDot({ color, pulse = false }: { color: string; pulse?: boolean }) {
  return (
    <span className="relative inline-flex h-2 w-2 shrink-0">
      {pulse && (
        <span
          className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-40"
          style={{ background: color }}
        />
      )}
      <span
        className="relative inline-flex h-2 w-2 rounded-full"
        style={{ background: color }}
      />
    </span>
  );
}

/* ─── EmptyState — for missing enrichment ─── */
export function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="py-4 text-center">
      <p className="text-[11px] uppercase tracking-widest text-aion-text-faint">{children}</p>
    </div>
  );
}

/* ─── GraphContainer — wraps charts with consistent styling ─── */
export function GraphContainer({
  children,
  title,
  meta,
  className = "",
}: {
  children: React.ReactNode;
  title: string;
  meta?: string;
  className?: string;
}) {
  return (
    <div className={`relative ${className}`}>
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-xs font-medium text-aion-text-secondary">{title}</h3>
        {meta && <span className="text-[10px] text-aion-text-faint font-mono">{meta}</span>}
      </div>
      {children}
    </div>
  );
}
