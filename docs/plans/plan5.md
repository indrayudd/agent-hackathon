# Plan 5: State-of-the-Art D3 Visualization Engine for Story Tab

## Current State

The D3 engine (`ReportD3Chart.tsx`) supports only **4 chart types**: scatter, line, bar, histogram.
It rejects: heatmaps, box plots, violin plots, horizontal bars, stacked bars, area charts, filled regions, error bars, multi-subplot layouts, annotations, and any figure with >8 traces or mixed trace types.

The classification gate (`reportViz.ts:classifyPlotlyFigure`) has a **zero-tolerance policy** — one unsupported feature in ANY trace and the entire figure falls back to Plotly (1MB bundle) or static image.

## Data Reality (from 208 specs across 13 sessions)

| Trace Type | Count | % | D3 Support |
|---|---|---|---|
| scatter (markers) | 35 | 34% | ✅ |
| scatter (lines) | 24 | 23% | ✅ |
| histogram | 44 | 42% | ✅ |
| heatmap | 14 | 13% | ❌ → Plotly fallback |
| bar | 7 | 7% | ✅ |
| box/violin | 0 data, 12 metadata | — | ❌ → image fallback |

84% of figures are single-trace. All axes are linear. No log/date/polar in actual data.

## Architecture Decisions

| Decision | Choice | Why |
|---|---|---|
| DOM ownership | React JSX, D3 for math only | Already correct; React 19 compatible |
| SVG vs Canvas | SVG | Report quality, a11y, <10K points |
| Color palette | Tableau10 (colorblind-safe) | Current 6-color palette insufficient |
| Axis rendering | JSX `<text>` (no d3.axis) | Better a11y and styling control |
| Transitions | CSS transitions on SVG | Simpler than D3 transitions in React |

## Implementation Tasks

### Task 1: Expand Chart Type Support in ReportD3Chart.tsx
**Files**: `ReportD3Chart.tsx`

Add rendering branches for:
- **Heatmap**: `d3.scaleSequential` with diverging/sequential colorscales, cell annotations, color legend bar
- **Box plot**: Whiskers, IQR box, median line, outlier circles. Compute stats with `d3.quantile()`
- **Violin plot**: `d3.bin()` + symmetric `d3.area()` with `curveCatmullRom`
- **Horizontal bar**: Swap x/y scales, band on Y, linear on X
- **Stacked bar**: `d3.stack()` generator
- **Area chart**: `d3.area()` with gradient fill (already partial for single-series line)

### Task 2: Relax Classification Gate in reportViz.ts
**Files**: `reportViz.ts`

- Add `D3_SUPPORTED_KINDS`: `"heatmap"`, `"box"`, `"violin"`
- `classifyTrace()`: Return valid classifications for heatmap, box, violin (not null)
- `isSimplePlotlyLayout()`: Allow `barmode: "stack"` and horizontal bars
- `classifyPlotlyFigure()`: Allow mixed trace types for box+scatter (outliers overlay)
- Raise `MAX_SUPPORTED_TRACES` from 8 to 16

### Task 3: Visual Quality Overhaul
**Files**: `ReportD3Chart.tsx`

- **Palette**: Switch to `schemeTableau10` (10 colorblind-safe colors)
- **Smart tick formatting**: Auto-detect SI notation vs decimal vs scientific based on value range
- **Responsive margins**: Scale with chart dimensions instead of fixed 48/30/64/68
- **Cursor-following tooltip**: Track pointer position, flip near edges
- **Interactive legend**: Click to toggle series visibility
- **CSS transitions**: Smooth opacity/size changes on hover (not instant)
- **Debounced ResizeObserver**: Use rAF to avoid resize thrashing
- **Responsive tick count**: `Math.max(3, Math.floor(innerWidth / 80))`

### Task 4: Heatmap Color Legend Component
**Files**: `ReportD3Chart.tsx`

Dedicated color legend bar for heatmaps:
- Gradient SVG `<linearGradient>` with stops from colorscale
- Min/max labels at ends
- Positioned at right margin of chart

## Agent Assignment

- **Agent A**: Task 1 + Task 4 (chart types + heatmap legend) — `ReportD3Chart.tsx`
- **Agent B**: Task 2 (classification gate) — `reportViz.ts`
- **Agent C**: Task 3 (visual quality) — `ReportD3Chart.tsx` visual layer

Note: Agent A and C both touch ReportD3Chart.tsx so they must run sequentially (A first, then C patches on top).
Run Agent B in parallel with Agent A.
