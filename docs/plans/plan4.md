# Plan 4: Hidden Plot-Spec Emitter and Report D3 Bridge

## Goal

Separate notebook plotting from report rendering cleanly:

- the notebook should keep showing normal exploratory visuals to the user
- the analysis runtime should also emit hidden structured chart specs
- the backend should normalize and persist those specs
- the story/report layer should render bespoke D3 visuals from those specs

This avoids reverse-engineering PNGs and gives the report engine a semantic source of truth.

## Architecture

### 1. Notebook display output

Analysis cells are still free to render visible charts in the notebook:

- `matplotlib`
- `plotly`
- mixed text + plots

This output is for exploration and debugging, not the final report visual language.

### 2. Hidden plot-spec emission

The runtime now supports a hidden sidecar emission path:

- analysis code can call `emit_plot_spec(...)` explicitly
- the kernel also wraps `plt.show()` so common matplotlib charts still produce a structured fallback spec even if the code forgot to emit one manually

These specs are written to:

- `sessions/<session_id>/plot_specs.jsonl`

Each emitted record should include:

- `cell_id`
- `kind`
- `mime_type`
- `chart_family`
- `semantic_intent`
- axis roles
- structured `source`
- optional display hints

### 3. Backend plot contract

The backend is responsible for turning raw notebook outputs plus hidden sidecar specs into one normalized artifact contract.

Core responsibilities:

- load hidden specs from `plot_specs.jsonl`
- associate them with notebook cell ids
- prefer structured specs over raw PNG fallback when both exist
- attach `viz_spec` metadata for the report engine

Key files:

- [plot_contract.py](/Users/indro/Projects/Hackathon/AgenticEDAHackathon/src/reporting/plot_contract.py)
- [run.py](/Users/indro/Projects/Hackathon/AgenticEDAHackathon/backend/routers/run.py)
- [story.py](/Users/indro/Projects/Hackathon/AgenticEDAHackathon/backend/routers/story.py)

### 4. Report rendering bridge

The story/report UI should not render notebook visuals directly when a structured spec is available.

Instead:

- backend returns normalized plot artifacts
- frontend resolves each artifact through the visualization engine
- supported chart families go through bespoke D3 renderers
- unsupported families fall back safely to Plotly or image rendering

Key frontend files:

- [reportViz.ts](/Users/indro/Projects/Hackathon/AgenticEDAHackathon/frontend/src/lib/reportViz.ts)
- [reportEngine.ts](/Users/indro/Projects/Hackathon/AgenticEDAHackathon/frontend/src/lib/reportEngine.ts)
- [StoryPlotRenderer.tsx](/Users/indro/Projects/Hackathon/AgenticEDAHackathon/frontend/src/components/story/StoryPlotRenderer.tsx)
- [ReportD3Chart.tsx](/Users/indro/Projects/Hackathon/AgenticEDAHackathon/frontend/src/components/story/ReportD3Chart.tsx)

## Current Behavior

Implemented now:

- visible notebook plots remain unchanged
- hidden specs can be emitted explicitly with `emit_plot_spec(...)`
- matplotlib fallback extraction runs automatically on `plt.show()`
- story/report can resolve supported specs to `report_d3`

Grounded proof:

- a plain matplotlib scatter now produces a hidden spec without manual emission
- a T1-backed smoke plot from [T1_slice.csv](/Users/indro/Projects/Hackathon/AgenticEDAHackathon/datasets/T1_slice.csv) resolves to `viz_spec.renderer = report_d3`

## Deliverables

- [x] Inject hidden `emit_plot_spec(...)` support into the kernel runtime
- [x] Persist hidden plot specs into `plot_specs.jsonl`
- [x] Add matplotlib fallback extraction at `plt.show()`
- [x] Normalize hidden specs into backend plot artifacts
- [x] Feed normalized artifacts into the story/report renderer
- [x] Route supported artifacts into bespoke D3 rendering
- [ ] Expand fallback extraction beyond common line/scatter/bar/histogram/heatmap cases
- [ ] Improve semantic inference for multi-series and statistical diagnostic charts
- [ ] Validate end-to-end on full real agent runs, not only smoke cells
- [ ] Remove remaining notebook-image fallbacks from hypothesis sections where structured specs can be produced instead

## Design Rule

Keep this separation strict:

- notebook output is the exploratory surface
- hidden `plot_spec` is the report source of truth

The report should become increasingly independent of notebook rendering details over time.
