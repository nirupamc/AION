// AION Camelot Wheel — signature visual, redesigned
// 24 cells, A/B rings, track counts, hover/selected states, compatible neighbors

"use client";

import React, { useMemo, useState } from "react";
import { colors } from "../lib/tokens";

interface CamelotWheelProps {
  distribution: Array<{ label: string; count: number }>;
  selected?: string | null;
  onSelect: (code: string) => void;
  size?: number;
}

// All 24 Camelot codes in wheel order
const CAMELOT_CODES = [
  "1A","1B","2A","2B","3A","3B","4A","4B","5A","5B","6A","6B",
  "7A","7B","8A","8B","9A","9B","10A","10B","11A","11B","12A","12B",
];

// Compatible neighbors for each code
const COMPATIBLE: Record<string, string[]> = {
  "1A": ["1B","2A","12A"], "1B": ["1A","2B","12B"],
  "2A": ["2B","3A","1A"], "2B": ["2A","3B","1B"],
  "3A": ["3B","4A","2A"], "3B": ["3A","4B","2B"],
  "4A": ["4B","5A","3A"], "4B": ["4A","5B","3B"],
  "5A": ["5B","6A","4A"], "5B": ["5A","6B","4B"],
  "6A": ["6B","7A","5A"], "6B": ["6A","7B","5B"],
  "7A": ["7B","8A","6A"], "7B": ["7A","8B","6B"],
  "8A": ["8B","9A","7A"], "8B": ["8A","9B","7B"],
  "9A": ["9B","10A","8A"], "9B": ["9A","10B","8B"],
  "10A": ["10B","11A","9A"], "10B": ["10A","11B","9B"],
  "11A": ["11B","12A","10A"], "11B": ["11A","12B","10B"],
  "12A": ["12B","1A","11A"], "12B": ["12A","1B","11B"],
};

export function CamelotWheel({ distribution, selected, onSelect, size = 280 }: CamelotWheelProps) {
  const [hovered, setHovered] = useState<string | null>(null);
  const map = useMemo(() => new Map(distribution.map((d) => [d.label, d.count])), [distribution]);
  const max = Math.max(1, ...Array.from(map.values()));

  const cx = size / 2;
  const cy = size / 2;
  const outerR = size * 0.42;
  const midR = size * 0.28;
  const innerR = size * 0.16;

  const compatibleCodes = useMemo(() => {
    if (!selected) return new Set<string>();
    return new Set(COMPATIBLE[selected] ?? []);
  }, [selected]);

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="mx-auto block" style={{ maxWidth: size }}>
      {/* Subtle ring guides */}
      <circle cx={cx} cy={cy} r={outerR + 2} fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth={1} />
      <circle cx={cx} cy={cy} r={midR} fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth={1} />
      <circle cx={cx} cy={cy} r={innerR} fill="none" stroke="rgba(255,255,255,0.03)" strokeWidth={1} />

      {CAMELOT_CODES.map((code) => {
        const count = map.get(code) ?? 0;
        const intensity = count / max;
        const num = parseInt(code.slice(0, -1));
        const isA = code.endsWith("A");

        const a0 = ((num - 1) * 30 - 90) * (Math.PI / 180);
        const a1 = (num * 30 - 90) * (Math.PI / 180);
        const rI = isA ? innerR : midR;
        const rO = isA ? midR : outerR;

        const x0i = cx + rI * Math.cos(a0);
        const y0i = cy + rI * Math.sin(a0);
        const x1i = cx + rI * Math.cos(a1);
        const y1i = cy + rI * Math.sin(a1);
        const x0o = cx + rO * Math.cos(a0);
        const y0o = cy + rO * Math.sin(a0);
        const x1o = cx + rO * Math.cos(a1);
        const y1o = cy + rO * Math.sin(a1);

        const path = `M ${x0i} ${y0i} L ${x0o} ${y0o} A ${rO} ${rO} 0 0 1 ${x1o} ${y1o} L ${x1i} ${y1i} A ${rI} ${rI} 0 0 0 ${x0i} ${y0i} Z`;

        const isSelected = code === selected;
        const isCompatible = compatibleCodes.has(code);
        const isHovered = code === hovered;
        const isFaded = selected && !isSelected && !isCompatible;

        // Color logic — organic palette
        let fill: string;
        if (count === 0) {
          fill = "rgba(255,255,255,0.02)";
        } else if (isSelected) {
          fill = isA ? colors.accent.mossBright : colors.accent.mineralBright;
        } else if (isCompatible) {
          fill = isA ? colors.accent.moss : colors.accent.mineral;
        } else if (isFaded) {
          fill = isA
            ? `rgba(90,122,90,${0.05 + intensity * 0.1})`
            : `rgba(74,122,138,${0.05 + intensity * 0.1})`;
        } else {
          fill = isA
            ? `rgba(90,122,90,${0.12 + intensity * 0.55})`
            : `rgba(74,122,138,${0.12 + intensity * 0.55})`;
        }

        const opacity = isHovered ? 1 : isFaded ? 0.6 : 1;
        const strokeWidth = isSelected ? 1.5 : isCompatible ? 1 : 0.5;
        const stroke = isSelected
          ? "rgba(255,255,255,0.3)"
          : isCompatible
          ? "rgba(255,255,255,0.12)"
          : "rgba(255,255,255,0.04)";

        return (
          <g
            key={code}
            onClick={() => onSelect(code)}
            onMouseEnter={() => setHovered(code)}
            onMouseLeave={() => setHovered(null)}
            style={{ cursor: "pointer", opacity, transition: "opacity 120ms ease" }}
          >
            <path d={path} fill={fill} stroke={stroke} strokeWidth={strokeWidth} />
            {/* Count label for non-empty */}
            {count > 0 && (() => {
              const mid = (a0 + a1) / 2;
              const rMid = (rI + rO) / 2;
              const tx = cx + rMid * Math.cos(mid);
              const ty = cy + rMid * Math.sin(mid);
              return (
                <text
                  x={tx} y={ty}
                  textAnchor="middle" dominantBaseline="middle"
                  fontSize={9}
                  fontFamily="'JetBrains Mono', monospace"
                  fontWeight="500"
                  fill={isSelected ? "#fff" : "rgba(255,255,255,0.5)"}
                >
                  {count}
                </text>
              );
            })()}
          </g>
        );
      })}

      {/* Number labels around wheel */}
      {Array.from({ length: 12 }, (_, i) => {
        const num = i + 1;
        const angle = (num - 1) * 30 - 90;
        const rad = (angle + 15) * (Math.PI / 180);
        const r = outerR + 16;
        const x = cx + r * Math.cos(rad);
        const y = cy + r * Math.sin(rad);
        return (
          <text
            key={num}
            x={x} y={y}
            textAnchor="middle" dominantBaseline="middle"
            fontSize={10}
            fontFamily="'JetBrains Mono', monospace"
            fontWeight="500"
            fill="var(--aion-text-muted)"
          >
            {num}
          </text>
        );
      })}

      {/* Center */}
      <circle cx={cx} cy={cy} r={innerR - 4} fill="var(--aion-bg)" stroke="rgba(255,255,255,0.04)" strokeWidth={1} />
      <text
        x={cx} y={cy - 4}
        textAnchor="middle" dominantBaseline="middle"
        fontSize={9}
        fontFamily="'JetBrains Mono', monospace"
        fill="var(--aion-text-faint)"
      >
        A = minor
      </text>
      <text
        x={cx} y={cy + 6}
        textAnchor="middle" dominantBaseline="middle"
        fontSize={9}
        fontFamily="'JetBrains Mono', monospace"
        fill="var(--aion-text-faint)"
      >
        B = major
      </text>

      {/* Hover tooltip */}
      {hovered && (
        <g>
          <text
            x={cx} y={cy + 20}
            textAnchor="middle" dominantBaseline="middle"
            fontSize={10}
            fontFamily="'JetBrains Mono', monospace"
            fontWeight="600"
            fill="var(--aion-text)"
          >
            {hovered} — {map.get(hovered) ?? 0} tracks
          </text>
        </g>
      )}
    </svg>
  );
}
