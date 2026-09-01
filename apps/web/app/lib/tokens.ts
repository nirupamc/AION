// AION Design Tokens — Organic Technical Visual System
// Central token definitions. Use these in Tailwind config and components.

export const colors = {
  // Background layers — warm near-blacks
  bg: {
    base: "#0c0c10",       // deepest background
    raised: "#111116",     // surfaces
    elevated: "#17171d",   // hover, active regions
    overlay: "#1c1c24",    // popovers, drawers
  },

  // Borders — mineral gray, very low opacity
  border: {
    subtle: "rgba(255,255,255,0.04)",
    default: "rgba(255,255,255,0.07)",
    strong: "rgba(255,255,255,0.12)",
    focus: "rgba(255,255,255,0.18)",
  },

  // Text hierarchy — warm off-whites
  text: {
    primary: "#e8e6e1",    // headings, important
    secondary: "#a09d96",  // body, descriptions
    muted: "#6b6862",      // labels, captions
    faint: "#4a4844",      // barely visible
  },

  // Accent families — faded/desaturated
  accent: {
    moss: "#5a7a5a",       // harmonic, success
    mossBright: "#7aaa6a",
    mineral: "#4a7a8a",    // technical, data
    mineralBright: "#6aaabb",
    violet: "#7a5a8a",     // mood
    violetBright: "#9a7aaa",
    clay: "#8a7a4a",       // energy, warnings
    clayBright: "#bba85a",
    rose: "#8a5a6a",       // alerts
    roseBright: "#bb7a8a",
    acid: "#7a9a5a",       // active, selected
    acidBright: "#9abb6a",
  },

  // Graph colors — muted, organic
  graph: {
    primary: "#5a7a5a",    // moss — main data
    secondary: "#4a7a8a",  // mineral — secondary
    tertiary: "#7a5a8a",   // violet — tertiary
    quaternary: "#8a7a4a", // clay — quaternary
    grid: "rgba(255,255,255,0.04)",
    axis: "#6b6862",
    dot: "#5a7a5a",
    dotHover: "#9abb6a",
    line: "#5a7a5a",
    lineTarget: "#8a7a4a",
  },

  // Semantic states
  state: {
    success: "#5a7a5a",
    successBright: "#7aaa6a",
    warning: "#8a7a4a",
    warningBright: "#bba85a",
    error: "#8a5a5a",
    errorBright: "#bb7a7a",
    info: "#4a7a8a",
  },

  // Score gradient — for transition/compatibility scores
  score: {
    excellent: "#5a7a5a",  // 90-100
    strong: "#7a8a4a",     // 75-89
    usable: "#8a7a4a",     // 60-74
    risky: "#8a5a5a",      // <60
  },
} as const;

export const typography = {
  // Editorial / display — page titles, DNA headline
  display: {
    fontFamily: "'Inter', system-ui, sans-serif",
    fontWeight: "700",
    letterSpacing: "-0.02em",
  },
  // Technical / mono — BPM, Camelot, scores, coordinates
  mono: {
    fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace",
    fontWeight: "500",
    letterSpacing: "0",
  },
  // Readable sans — body, controls
  body: {
    fontFamily: "'Inter', system-ui, sans-serif",
    fontWeight: "400",
    letterSpacing: "0",
  },
} as const;

export const spacing = {
  xs: "0.25rem",
  sm: "0.5rem",
  md: "1rem",
  lg: "1.5rem",
  xl: "2rem",
  "2xl": "3rem",
} as const;

export const radius = {
  sm: "4px",
  md: "6px",
  lg: "8px",
  xl: "12px",
  full: "9999px",
} as const;

export const motion = {
  fast: "120ms",
  normal: "200ms",
  slow: "350ms",
  slower: "500ms",
} as const;

// Score color helper
export function scoreColor(score: number): string {
  if (score >= 90) return colors.score.excellent;
  if (score >= 75) return colors.score.strong;
  if (score >= 60) return colors.score.usable;
  return colors.score.risky;
}

// Score label helper
export function scoreLabel(score: number): string {
  if (score >= 90) return "excellent";
  if (score >= 75) return "strong";
  if (score >= 60) return "usable";
  return "risky";
}

// Intensity for data visualization (30% resting, 100% selected)
export function dataIntensity(active: boolean): number {
  return active ? 1 : 0.35;
}
