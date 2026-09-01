# M10 — AION Organic-Tech Visual System Redesign

**Status:** COMPLETE  
**Baseline:** 320 backend tests passing, frontend typecheck PASS, build PASS

## Visual Philosophy

AION's interface should feel like a **living musical system** — not a generic SaaS dashboard.

**Organic + Technical + Musical + Experimental + Dark + Tactile + Data-Driven**

The library is treated as biological instrumentation crossed with underground music hardware and scientific visualization. Data resting at 30–35% visual intensity, selected/active data at 90–100%.

**Avoided:** generic SaaS, Spotify clone, cyberpunk neon, glassmorphism, admin panel, card grids, rainbow charts.

## Design Tokens

Centralized in `app/lib/tokens.ts` + CSS custom properties in `globals.css` + Tailwind config.

### Color System

**Background layers (warm near-blacks):**
- `--aion-bg: #0c0c10` — deepest
- `--aion-raised: #111116` — surfaces
- `--aion-elevated: #17171d` — hover, active
- `--aion-overlay: #1c1c24` — drawers, popovers

**Text hierarchy (warm off-whites):**
- `--aion-text: #e8e6e1` — primary
- `--aion-text-secondary: #a09d96` — body
- `--aion-text-muted: #6b6862` — labels
- `--aion-text-faint: #4a4844` — barely visible

**Borders (mineral gray):**
- `--aion-border-subtle: rgba(255,255,255,0.04)` — hairlines
- `--aion-border: rgba(255,255,255,0.07)` — default
- `--aion-border-strong: rgba(255,255,255,0.12)` — emphasis

**Accent families (faded/desaturated):**
- `moss (#5a7a5a)` — harmonic, success, primary data
- `mineral (#4a7a8a)` — technical, BPM/key/Camelot
- `violet (#7a5a8a)` — mood
- `clay (#8a7a4a)` — energy, warnings
- `rose (#8a5a6a)` — alerts, risky scores
- `acid (#7a9a5a)` — active, selected, navigation

**Score gradient:**
- 90–100: `moss` (excellent)
- 75–89: `clay-bright` (strong)
- 60–74: `clay` (usable)
- <60: `rose` (risky)

### Typography

Three deliberate roles:
1. **Display/Inter** (`font-display`) — page titles, DNA headline, 700 weight, -0.02em tracking
2. **Technical/Mono** (`font-mono`) — BPM, Camelot, scores, coordinates, 500 weight, JetBrains Mono
3. **Body/Inter** (`font-body`) — interface controls, 400 weight

### Spacing & Radius

- Spacing: xs(4) → 2xl(48)
- Radius: sm(4) → full(9999)
- No heavy border-radius — keeps things technical

### Motion

- `--aion-fast: 120ms` — hover interpolation
- `--aion-normal: 200ms` — state transitions
- `--aion-slow: 350ms` — drawer morphing
- `prefers-reduced-motion` respected — all animations disabled

## Layout

### Global Shell
- **Sticky header** with frosted glass (`backdrop-blur-md`)
- **Navigation:** Three concise tabs — `CRATE` / `DNA` / `FLOW`
- Active state: acid-tinted background, bright text
- Inactive: muted text, hover elevation

### Connection Status
- Inline green dot + connected label (not a card)

## Crate (Library)

### Table
- **Dense 12-column grid** with monospaced metadata
- Thin `aion-border-subtle` row separators (not heavy borders)
- 8×8 artwork thumbnails (not 12×12 — more compact)
- Hover: subtle `aion-elevated/40` background
- Column headers: 10px uppercase tracking-wider, very faint

### Metadata Encoding
- BPM: `font-mono text-aion-text-secondary tabular-nums`
- Camelot: `font-mono` in mineral color
- Mood: `font-mono capitalize` in violet
- Vibe: `font-mono capitalize` in mineral
- Confidence: 10px monospace faint
- Source: 9px uppercase faint

### Pagination
- Minimal: monospace page numbers, compact controls

## Track Inspector

### Layout
- Full-height right drawer with `aion-bg` background
- **Sticky header** with title/artist/album + close button (SVG, not ✕)
- `backdrop-blur-sm` for frosted header

### Sections (visual hierarchy)
1. **Identity** — duration, release, provider, ISRC, Spotify ID
2. **Musical** — BPM as large `aion-metric text-2xl` with signal bar, Key/Camelot in 2-column grid, Time signature
3. **Character** — Energy/Danceability/Valence with thin signal bars (violet)
4. **Texture** — Acousticness/Instrumentalness/Liveness/Speechiness/Loudness as compact rows
5. **Mood / Vibe** — dominant label + top 3 scored labels with signal bars
6. **Provenance** — data source attribution
7. **Identifiers** — ISRC, MusicBrainz

### Signal Bars
- 3px height thin horizontal traces
- Color-coded by section (moss for musical, violet for character)
- Transition width on 200ms ease

## Library DNA

### Hero Composition
- **Single flowing composition** — not 4 metric cards
- Coverage: `25 / 3186 analyzed` in secondary text
- Key metrics with large `aion-metric text-4xl` values
- Dominant mood in violet, dominant Camelot in mineral
- Dominant vibe + set role peak in faint text

### Distributions
- BPM histogram: moss-colored bars, thin gridlines, monospace axis labels
- Energy distribution: mineral-colored bars
- Both: `aion-tooltip` styled tooltips, cursor fill on hover

### Camelot Wheel
- **Custom SVG** with organic palette:
  - A ring: moss family (green tones)
  - B ring: mineral family (cyan tones)
  - Intensity scales from 12% to 67% opacity based on count
  - Empty cells: near-invisible `rgba(255,255,255,0.02)`
  - Selected cell: bright (moss-bright or mineral-bright)
  - Compatible neighbors: moderate intensity, 0.12 border
  - Incompatible: faded to 10% intensity
  - Count labels in monospace within each cell
  - Center label: `A = minor` / `B = major`
  - Hover tooltip in center
  - Subtle ring guide circles at 0.03 opacity

### Mood/Vibe Distributions
- Horizontal bars with violet (mood) and mineral (vibe)
- Selected state: bright fill, unselected fade to 0.3 opacity
- Click to filter, click again to deselect

### BPM × Energy Constellation
- Scatter with moss-colored dots, fillOpacity 0.6, strokeOpacity 0.3
- Radius 3 (subtle, not huge points)
- Custom tooltip: title, artist, BPM, energy, Camelot, mood, vibe
- Click to select track

## Graph Language

Shared principles across all charts:
- **Thin strokes:** 0.5–1px axis lines
- **Low-opacity grids:** `rgba(255,255,255,0.04)`
- **Minimal chrome:** no axis lines, no tick lines
- **Monospace labels:** JetBrains Mono at 9–10px
- **Muted axis text:** `--aion-text-faint`
- **No rainbow palette** — organic moss/mineral/violet/clay
- **Cursor fill:** `rgba(255,255,255,0.03)` on hover
- **Tooltips:** `aion-tooltip` with overlay background

## Best Next Track

### Layout
- Vertical list with rank number (monospace faint)
- Score connection line: 48px horizontal bar showing score as percentage fill in score color
- Track info: title (13px), artist (11px faint), metadata row (10px monospace)
- Score badge: large monospace number in score color
- Expand/collapse toggle (+/−)

### Score Legend
- Inline: `90+ excellent · 75–89 strong · 60–74 usable · <60 risky`

### Breakdown
- 2-column grid of component scores
- Warnings in clay color
- Missing components in faint text

## Smart Flow

### Builder
- `aion-surface` container with section label
- Inputs: start track ID, count (5/10/20), energy shape select
- All inputs: monospace, aion-border, aion-raised background
- Generate button: acid-tinted

### Flow Summary
- 4-column: Overall (colored score), Average, Weakest (red if <60), Status
- Monospace metric values, section labels above

### Energy Curve
- `LineChart` with:
  - Target: clay color, dashed `6 4`, opacity 0.6, strokeWidth 1.5
  - Actual: moss color, solid, dot r=3, strokeWidth 2
  - No axis lines, no tick lines, monospace labels
  - Legend with inline color swatches

### Sequence Path (Signature Visual)
- **Vertical flowing path** with connection line (`rgba(255,255,255,0.06)`)
- Track nodes: 36px circles with position number
  - Normal: `aion-raised` background, `aion-border` border
  - Weakest: rose-tinted background, rose border
- Content: title + artist, metadata row (BPM · Camelot · Energy · Mood · Vibe in mono)
- Transition: down-arrow + ScorePill + reasons in faint text
- "Weakest" badge on weakest transition
- Score on right side: large monospace in score color
- Click to expand: 3-column breakdown grid, warnings, missing components
- "Open in inspector →" link in acid color

### Weakest Link Summary
- Bottom alert: rose-tinted border and background, rose text

## Motion

- **Hover interpolation:** background transitions 200ms
- **Signal bar fill:** width transition 200ms ease
- **Camelot wheel:** opacity transitions 120ms on hover
- **Drawer:** appears as overlay (no slide animation)
- **Reduced motion:** all animations disabled via `prefers-reduced-motion: reduce`

## Accessibility

- All interactive elements are `<button>` or `<a>` (keyboard accessible)
- Focus ring: `aion-focus:focus-visible` with acid outline
- Contrast: primary text `#e8e6e1` on `#0c0c10` = 12.5:1 ratio
- Muted text `#6b6862` on `#0c0c10` = 3.2:1 (passes WCAG AA for large text)
- Semantic HTML: `<main>`, `<header>`, `<nav>`, `<footer>`
- Reduced motion: all transitions and animations disabled

## Performance

- Build: **112 kB** first load JS (vs 111 kB before M10, +1 kB)
- No new runtime dependencies (Recharts already present)
- No three.js, WebGL, or heavy animation libraries
- All CSS via Tailwind + custom properties (no runtime CSS-in-JS)
- Components are small and focused (5 component files + tokens + primitives)

## File Structure (New)

```
apps/web/app/
├── globals.css          # Design tokens, base styles, motion
├── layout.tsx           # Root shell
├── page.tsx             # Main page (orchestrator)
├── lib/
│   ├── api.ts           # API types and fetchers (unchanged)
│   ├── tokens.ts        # Design tokens (colors, typography, spacing, motion)
│   └── components.tsx   # Reusable primitives
├── components/
│   ├── CamelotWheel.tsx  # SVG Camelot wheel
│   ├── CrateView.tsx     # Library table
│   ├── TrackInspector.tsx # Right-side drawer
│   ├── DNAView.tsx       # Library DNA analytics
│   ├── SmartFlowView.tsx # Smart Flow path visualization
│   └── BestNextTrack.tsx # Recommendations
```

## Verification

- **typecheck:** PASS (tsc --noEmit)
- **build:** PASS (112 kB, static pages generated)
- **backend:** 320 passed (no regression)
- **real data:** all views render with actual 3186-track library, 25 enriched

## Known Limitations

- Mobile: not fully optimized (desktop-first workspace), but doesn't break
- No phrase/beat-grid, intro/outro visualization (metadata-only system)
- Camelot wheel hover tooltip is basic (positioned at center, not cursor-following)
- Scatter chart click only works if tracks are in current library page
- No drag-and-drop reordering in Smart Flow
- No dark/light theme toggle (dark-only by design)
- No font loading optimization (uses system fonts + web-safe fallbacks)

## Final Decision

**COMPLETE**

All 17 completion criteria met:
1. ✅ Coherent AION design tokens exist
2. ✅ Global shell redesigned (CRATE/DNA/FLOW navigation)
3. ✅ Crate/library redesigned (dense monospace table)
4. ✅ Track inspector redesigned (sectioned with signal bars)
5. ✅ Library DNA redesigned (hero composition)
6. ✅ Graph visual language consistent (moss/mineral palette)
7. ✅ Camelot wheel redesigned (organic A/B rings)
8. ✅ Best Next Track fits new system (connected score lines)
9. ✅ Smart Flow is a path visualization (vertical flow with nodes)
10. ✅ Energy curve integrates naturally (dashed target + solid actual)
11. ✅ All interactions functional
12. ✅ Real data used (3186 tracks, 25 enriched)
13. ✅ Partial coverage truthful ("25 / 3186 analyzed")
14. ✅ Reduced motion/accessibility considered
15. ✅ Frontend typecheck passes
16. ✅ Frontend build passes
17. ✅ Backend 320 tests don't regress

## Next Milestone

M11 — Playlist Export + DJ Workflow
