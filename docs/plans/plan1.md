# Plan 1 — Analysis Pipeline, Ingestion & Notebook Experience

**Owner**: Person A
**Scope**: Robust multi-format ingestion, all new analysis phases (temporal,
dynamics, multivariate, train/test split), the FastAPI + kernel backbone, and
the notebook tab + file sidebar + kernel integration on the frontend.

---

**What you DON'T touch** (Person B owns these):
- `src/insights/`, `src/causal/`, `src/model_readiness/`, `src/reporting/`, `src/chat/`
- `src/pipeline.py` (Person B wires the master graph)
- `backend/routers/stream.py`, `backend/routers/story.py`, `backend/routers/history.py`, `backend/routers/chat.py`
- `backend/services/story_service.py`, `backend/services/history_service.py`
- `frontend/components/story/`, `frontend/components/history/`, `frontend/components/chat/`
- `frontend/hooks/useAgentStream.ts`, `frontend/hooks/useChat.ts`, `frontend/hooks/useHistory.ts`
- `frontend/stores/storyStore.ts`, `frontend/stores/chatStore.ts`

**Shared interfaces** (coordinate with Person B):
- `CompositeState` in `src/tools/state_schema.py` — both add fields, neither deletes
- `frontend/app/session/[id]/page.tsx` — you own notebook tab + file sidebar; they own story tab + chat sidebar + history
- `frontend/app/layout.tsx` — you scaffold it; they plug in their components
- `backend/app.py` — you create the FastAPI app; they add their routers via `include_router()`

---

## Phase 0: Backend Scaffold

- [x] Create `backend/app.py` — FastAPI app with CORS, lifespan, static mount for sessions/
- [x] Create `backend/routers/__init__.py`
- [x] Create `backend/routers/session.py` — `POST /api/upload` (multi-format), `GET /api/sessions`, `DELETE /api/session/{id}`
- [x] Create `backend/routers/notebook.py` — `GET /api/notebook/{id}`, `PATCH /api/notebook/{id}`, `POST /api/notebook/{id}/confirm`
- [x] Create `backend/routers/run.py` — `POST /api/run/{id}` triggers pipeline (hands off to Person B's stream.py for progress)
- [x] Create `backend/models/session.py` — Pydantic: `Session`, `DatasetPreview`, `UploadResponse`
- [x] Create `backend/services/session_manager.py` — session store, dataset file storage in `sessions/{id}/uploads/`, cleanup

## Phase 0: Frontend Scaffold

- [x] Initialize Next.js project in `frontend/` with Tailwind, TypeScript
- [x] Create `frontend/app/layout.tsx` — 3-column shell: left sidebar slot, center content, right sidebar slot
- [x] Create `frontend/app/page.tsx` — landing page (full-screen drop zone)
- [x] Create `frontend/app/session/[id]/page.tsx` — workspace with `ThreeColumnLayout`, `TabBar`, component slots
- [x] Create `frontend/components/layout/ThreeColumnLayout.tsx` — collapsible left (200px) + flex center + collapsible right (320px)
- [x] Create `frontend/components/layout/TabBar.tsx` — [Notebook] [Story] [⏱] toggle, "Confirm Changes" button (shows when dirty)
- [x] Create `frontend/components/layout/ProgressOverlay.tsx` — phase badges + spinner during agent run
- [x] Create `frontend/lib/api.ts` — typed REST client
- [x] Create `frontend/lib/types.ts` — `Session`, `Cell`, `CellOutput`, `NotebookModel`, `StorySection`, `Version`, `ChatMessage`
- [x] Create `frontend/stores/sessionStore.ts` (Zustand) — active session, session list, upload state

## Phase 0: Upload Flow

- [x] Create `frontend/components/upload/DropZone.tsx` — drag-drop with react-dropzone, accepts CSV/Excel/JSON/Parquet/log
- [x] Create `frontend/components/upload/DataPreview.tsx` — first-5-rows table, column types, sheet selector (for Excel)
- [x] Wire: drop -> upload to `/api/upload` -> preview -> "Run EDA" -> navigate to `/session/{id}`

## Phase 0: File Sidebar

- [x] Create `frontend/components/sidebar/FileSidebar.tsx` — collapsible left panel, file tree
- [x] Create `frontend/components/sidebar/FileItem.tsx` — icon + name, click to select/view
- [x] Contents: uploaded files (datasets), generated notebook (.ipynb download), exported stories (.pdf)
- [x] Back arrow at top: returns to landing page

## Phase 0: Kernel Management

- [x] Create `backend/services/kernel_manager.py` — start/stop/track kernels per session via Kernel Gateway REST API
- [x] Create `backend/routers/kernel.py` — `WS /api/kernel/{id}/channels` (WebSocket proxy to kernel)
- [x] Kernel lifecycle: start on first cell execution, idle timeout shutdown (30 min)
- [x] Pre-seed kernel: inject dataset path, `import pandas, numpy, matplotlib`

---

## Phase P: Prerequisites

### P.2 — Composite entity keys
- [x] File: `src/ingest/integrity.py` — replace `secondary_keys[0]` with tuple-based groupby across all secondary keys

### P.4 — Timestamp reindexing
- [x] File: `src/quality_handling/handle_missingness.py` + `src/tools/input_tools.py`
- [x] After value imputation, optionally reindex to regular grid based on `expected_frequency`
- [x] Gate: `is_irregular_sampling == False` and coverage < 95%

### P.5 — Robust multi-format ingestion
- [x] Create `src/ingest/file_loader.py`
- [x] **CSV**: `pd.read_csv()` with `chardet` encoding detection + delimiter sniffing
- [x] **Excel** (.xlsx, .xls): `pd.read_excel()` via openpyxl, handle multi-sheet (return sheet names for frontend selection)
- [x] **JSON**: `pd.read_json()` for flat; `pd.json_normalize()` for nested (detect nesting depth, flatten with dot-separated keys)
- [x] **NDJSON / JSON Lines** (.jsonl): `pd.read_json(lines=True)`
- [x] **Parquet**: `pd.read_parquet()` via pyarrow
- [x] **Log files** (.log, .txt): regex detection on first 20 lines; extract structured columns; fallback: timestamp + message
- [x] **MongoDB exports**: detect `$date`, `$oid` wrappers, unwrap to native types, flatten nested docs
- [x] **TSV**: detected via delimiter sniffing (same path as CSV)
- [x] All loaders return normalized `pd.DataFrame` + metadata dict `{ source_format, original_filename, sheet_name, encoding, row_count, col_count, load_warnings[] }`
- [x] Update `backend/routers/session.py` upload endpoint to use `file_loader.py`
- [ ] Add `openpyxl`, `chardet`, `pyarrow` to requirements.txt

---

## Phase 4: Temporal Visualization

### 4.1 — Raw time series plots (Rule 14)
- [x] Create `src/temporal_analysis/__init__.py`
- [x] Create `src/temporal_analysis/plot_time_series.py`
- [x] Implement `plot_raw_time_series()`:
  - [x] Single series: line plot of target(s)
  - [x] Multivariate: small multiples grid (max 4x4)
  - [x] Panel: overlay top-5 entities, rest as light gray
- [x] Output PNGs to `sessions/{id}/traces/`
- [x] Add `time_series_plots: list[str]` to CompositeState

### 4.2 — Zoom window plots (Rule 15)
- [x] Implement `plot_zoom_windows()`: auto-select 3 windows (last 10%, random 5%, spike window)
- [x] Add `zoom_plots: list[str]` to CompositeState

### 4.3 — Multi-grain resampling (Rule 17)
- [x] Create `src/temporal_analysis/resample_analysis.py`
- [x] Implement `resample_and_plot()`: resample at 2-3 coarser frequencies, side-by-side plots
- [x] Add `resampling_report: dict`

### 4.4 — Seasonality detection (Rule 18)
- [x] Create `src/temporal_analysis/seasonality.py`
- [x] Implement `detect_seasonality()`: group-by averages + Kruskal-Wallis per grouping + subseries plots
- [x] Add `seasonality_report: dict`, `seasonality_detected: bool`

### 4.5 — STL decomposition (Rule 19, conditional)
- [x] Implement `decompose_series()` in `seasonality.py` using `statsmodels.tsa.seasonal.STL`
- [x] Gate: `seasonality_detected == True`
- [x] Add `decomposition_report: dict`

### 4.6 — Event overlay (Rule 16, conditional)
- [x] Create `src/temporal_analysis/event_overlay.py`
- [x] Implement `overlay_events()`: vertical spans for binary event columns
- [x] Gate: event columns detected in `known_exogenous_cols`

---

## Phase 5: Dynamics & Rolling

### 5.1 — Rolling statistics (Rule 20)
- [x] Create `src/dynamics/__init__.py`, `src/dynamics/rolling_stats.py`
- [x] Implement `compute_rolling_stats()`: auto-select windows (7/30/90 for daily), compute mean/std/min/max, plot rolling bands
- [x] Add `rolling_stats_report: dict`

### 5.2 — Changepoint detection (Rule 21, conditional)
- [x] Create `src/dynamics/changepoints.py`
- [x] Implement `detect_changepoints()` using `ruptures` (PELT + RBF)
- [x] Gate: rolling variance ratio > 2x
- [x] Add `changepoints: list[dict]`, `regime_shifts_detected: bool`

### 5.3 — Outlier detection (Rule 22)
- [x] Create `src/dynamics/outlier_detection.py`
- [x] Implement `detect_time_outliers()`:
  - [x] Z-score on STL residuals (if available)
  - [x] IQR-based on rolling windows (always)
  - [x] Per outlier: timestamp, value, 5-pt context window
  - [x] LLM gate: classify as spike/level-shift/plateau/variance-change
- [x] Add `outlier_report: dict`

---

## Phase 6: Bivariate & Multivariate

### 6.1 — Panel group comparison (Rules 23-24)
- [x] Create `src/multivariate/__init__.py`, `src/multivariate/panel_compare.py`
- [x] Implement `compare_panel_entities()`: per-entity boxplots, overlay, CV, Kruskal-Wallis
- [x] Gate: `type == "multiple"`
- [x] Add `panel_comparison_report: dict`, `panel_heterogeneity: bool`

### 6.2 — Correlation analysis (Rule 25)
- [x] Create `src/multivariate/correlation.py`
- [x] Implement `compute_correlations()`: Pearson + Spearman matrices, windowed, flag redundant + sign-flips, heatmap
- [x] Gate: >= 2 numeric features
- [x] Add `correlation_report: dict`

### 6.3 — Mutual information (Rule 26, conditional)
- [x] Implement `compute_mutual_information()` in `correlation.py`
- [x] Gate: non-linear relationships suspected
- [x] Add `mutual_info_report: dict`

### 6.4 — Lag analysis (Rule 27)
- [x] Create `src/multivariate/lag_analysis.py`
- [x] Implement `compute_lag_relationships()`: ACF/PACF, cross-correlation, significant lags
- [x] Add `lag_report: dict`

### 6.5 — Dimensionality reduction (Rule 28, conditional)
- [x] Create `src/multivariate/dimensionality.py`
- [x] Implement `run_dimensionality_scan()`: PCA + scree plot, optional UMAP
- [x] Gate: feature_count > 15
- [x] Add `dimensionality_report: dict`

---

## Phase 9: Train/Test Split

### 9.1 — Temporal split (Rule 36)
- [x] Create `src/split/__init__.py`, `src/split/temporal_split.py`
- [x] Implement `apply_temporal_split()`: chronological cutoffs (70/85/100), same across entities, write CSVs
- [x] Add `split_dates: dict`, `split_sizes: dict`

### 9.2 — CV strategy selection (Rule 37)
- [x] Implement LLM gate `select_cv_strategy()`: expanding_window | sliding_window | grouped_ts_cv | stratified_kfold
- [x] Add `cv_strategy: dict`

### 9.3 — Leakage validation (Rule 38)
- [x] Create `src/split/leakage_check.py`
- [x] Implement `validate_no_leakage()`: target leakage, temporal leakage, group leakage checks
- [x] Add `leakage_report: dict`

### 9.4 — Distribution drift (Rule 39)
- [x] Create `src/split/distribution_drift.py`
- [x] Implement `compare_split_distributions()`: KS test + PSI per feature, overlaid histograms for drifted features
- [x] Add `drift_report: dict`

---

## Frontend: Notebook Tab & Kernel

### Notebook components
- [x] Create `frontend/components/notebook/NotebookPane.tsx` — scrollable cell list, "Run All" toolbar
- [x] Create `frontend/components/notebook/NotebookCell.tsx` — cell wrapper: toolbar + editor + output
- [x] Create `frontend/components/notebook/CodeEditor.tsx` — Monaco editor, Python syntax, Shift+Enter to run
- [x] Create `frontend/components/notebook/CellOutput.tsx` — render text/plain, text/html, image/png, plotly, stderr, traceback
- [x] Create `frontend/components/notebook/CellToolbar.tsx` — Run, Delete, Move Up/Down, cell type toggle

### Notebook model & state
- [x] Create `frontend/lib/notebookModel.ts` — Cell CRUD, nbformat serialization, load from API
- [x] Create `frontend/stores/notebookStore.ts` (Zustand) — cells, execution queue, dirty flag, baseline snapshots
- [x] Dirty tracking: compare current cells to last-confirmed state; show "Confirm Changes" when dirty

### Kernel integration
- [x] Create `frontend/lib/kernelProtocol.ts` — Jupyter WS message types + helpers
- [x] Create `frontend/hooks/useKernel.ts` — WS to `/api/kernel/{id}/channels`, execute cell, FIFO queue
- [x] Create `frontend/stores/kernelStore.ts` — connection status, busy/idle, execution count

### Wiring
- [x] In `session/[id]/page.tsx`: render notebook tab content via `<NotebookPane />` when Notebook tab is active
- [x] In `session/[id]/page.tsx`: render `<FileSidebar />` in left slot of `ThreeColumnLayout`
- [x] Wire: "Run EDA" -> `POST /api/run/{id}` -> progress overlay -> cells arrive from Person B's stream hook -> append to notebookStore
- [x] Wire: "Confirm Changes" button -> `POST /api/notebook/{id}/confirm` -> triggers version snapshot + story regen (Person B's endpoints)

---

## Integration Tests

- [x] Upload CSV -> preview shows -> "Run EDA" -> workspace loads with notebook tab
- [x] Upload Excel with 3 sheets -> sheet selector appears -> user picks -> correct sheet loaded
- [x] Upload nested JSON -> flattened to columns with dot-separated keys
- [x] Upload log file -> LLM detects format -> structured columns extracted
- [x] Kernel: edit cell -> Shift+Enter -> output updates in CellOutput
- [x] Panel dataset -> phases 4-6 all produce expected outputs (entity overlays, correlation heatmap, etc.)
- [x] Temporal split -> train/val/test CSVs written with correct boundaries
- [x] Seasonality: dataset with known daily+weekly -> rules 18-19 detect both
- [x] File sidebar: shows uploaded files + generated notebook + exported story
- [x] Dirty state: edit a cell -> "Confirm Changes" appears -> click -> button disappears
