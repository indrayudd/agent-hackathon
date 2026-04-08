# Visualization Engine Roadmap

## Shipped

- [x] Ship the first D3 reinterpretation slice for report visuals that can be classified reliably from notebook outputs.
- [x] Expand the first classifier gate to cover clean `line`, `scatter`, `bar`, and `histogram` figures while rejecting unsafe Plotly layouts more intentionally.
- [x] Render supported Plotly-backed report figures with a bespoke D3 SVG chart instead of the notebook-native Plotly component.
- [x] Keep Plotly as the fallback for unsupported charts, mixed traces, and static images.
- [x] Preserve notebook source links and normalized display sizing metadata in the story report.
- [x] Add semantic plot hints on the backend so the report path can stop relying only on raw Plotly structure.
- [x] Polish the first D3 report renderer so the chart shell, typography, gridlines, hover state, and spacing feel report-native instead of notebook-derived.
- [x] Verify the TypeScript and Python compile paths after wiring the new renderer into the story flow.

## Engine Layers

### Layer 1: Semantic Routing

Turn backend plot metadata into the primary renderer signal.
- `chart_family`: what kind of chart the data actually represents
- `semantic_intent`: why the chart exists in the report
- axis roles: what each axis means in context
- confidence: how strongly the backend believes the interpretation

The renderer should use these hints first, then fall back to structural heuristics only when the semantic layer is missing or uncertain.

### Layer 2: Chart Grammar

Define a small report grammar that maps semantic intent to canonical chart forms.
- trend
- comparison
- distribution
- relationship
- residual / diagnostic
- matrix / correlation
- uncertainty / spread
- anomaly / outlier

This grammar should be able to express the existing D3 slice and the next statistical families without making the frontend infer everything from raw notebook payloads.

### Layer 3: Renderer Registry

Introduce an explicit registry that chooses between report-native renderers and safe fallbacks.
- D3 renderer for supported editorial chart forms
- Plotly fallback for complex but still interactive notebook figures
- static image fallback for raw PNG outputs

The registry should be deterministic, confidence-gated, and easy to extend as the engine learns new chart families.

### Layer 4: Fallback Policy

Keep the fallback policy strict and predictable.
- reject subplots, secondary axes, stacked/relative layouts, and other unsafe structures until explicitly supported
- keep static PNG notebook figures on the fallback path until there is a deliberate conversion strategy
- preserve source links and display metadata even when falling back

The goal is to avoid “guessing” a chart into the wrong visual form.

### Layer 5: Validation

Treat browser validation as a first-class engineering gate.
- validate against real sessions, not synthetic snapshots only
- verify wide and narrow viewport behavior
- verify hover, keyboard focus, and source-link interactions
- validate report figures on the `datasets/T1_slice.csv` ground truth session and any other representative sessions

Compile checks are necessary, but they are not sufficient for the visualization engine.

## Rollout Tracker

- [x] Make semantic routing authoritative in the backend story payloads.
- [x] Add a chart grammar layer that can translate semantics plus structure into renderer-ready specs.
- [x] Introduce a renderer registry so D3, Plotly, and image fallbacks are chosen centrally.
- [x] Expand the D3 engine beyond the first slice with the next chart families only when the chart grammar can describe them cleanly.
- [ ] Validate the engine against `datasets/T1_slice.csv` and at least one additional real session in a browser.
- [x] Keep the fallback policy strict until the next chart family is explicitly supported.

## TODO Landings

- [x] `src/reporting/plot_contract.py`: enrich the plot artifact contract with deterministic semantic hints and any chart families the report engine can support safely.
- [x] `backend/models/story.py`: keep the story payload schema aligned with the normalized plot contract.
- [x] `backend/routers/story.py`: keep rehydration and export paths aligned with the plot contract and renderer metadata.
- [x] `frontend/src/lib/reportViz.ts`: keep the structural classifier strict while teaching it the next chart families.
- [x] `frontend/src/lib/reportEngine.ts`: centralize semantic + structural renderer selection behind a registry and fallback policy.
- [x] `frontend/src/components/story/StoryPlotRenderer.tsx`: render the selected family once, then reuse it from every report surface.
- [x] `frontend/src/components/story/ReportD3Chart.tsx`: add new renderer families only after the grammar can describe them cleanly.
- [x] `frontend/src/components/story/StorySectionCard.tsx`: keep figure framing, captions, and source links consistent across all renderers.
- [x] `frontend/src/components/story/StoryPane.tsx`: preserve the same renderer choice in the sectioned story and raw plot fallback paths.

## Validation Notes

- [x] API-level validation against a T1-backed report fixture showed `scatter`, `line`, `histogram`, and `bar` plots routing to report-native D3 through the shared `viz_spec` contract.
- [x] Story-only sessions now prefer the `Story` tab instead of landing on an empty notebook shell.
- [ ] Stable browser validation is still pending because the current local Playwright/Next dev context is not hydrating the session page reliably under HMR.
