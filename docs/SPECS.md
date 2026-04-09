# AgenticEDA — Implementation Specification

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   FRONTEND — Custom Web App (Next.js / React)               │
│                                                                             │
│ ┌──────────┐ ┌──────────────────────────────────────┐ ┌──────────────────┐ │
│ │           │ │  [Notebook]  [Story]          [⏱ Hx] │ │                  │ │
│ │Collapsible│ │ ┌──────────────────────────────────┐ │ │  Chat Interface  │ │
│ │  Files    │ │ │                                  │ │ │                  │ │
│ │           │ │ │  Center pane (tabbed):           │ │ │  - Natural lang  │ │
│ │- Uploaded │ │ │  Notebook tab: Colab-like editor │ │ │    questions     │ │
│ │  datasets │ │ │  Story tab: narrative insights   │ │ │  - "Why is X?"  │ │
│ │- Generated│ │ │                                  │ │ │  - "Drill into Y"│ │
│ │  notebooks│ │ │  History: version snapshots      │ │ │  - Agent replies │ │
│ │- Exports  │ │ │                                  │ │ │    with refs to  │ │
│ │           │ │ └──────────────────────────────────┘ │ │    notebook cells│ │
│ └──────────┘ └──────────────────────────────────────┘ └──────────────────┘ │
│   ← (collapsible)              ▲                            (collapsible) → │
└─────────────────────────────────┼───────────────────────────────────────────┘
                                  │ WebSocket + REST
┌─────────────────────────────────▼───────────────────────────────────────────┐
│                    BACKEND — FastAPI (Python)                                │
│                                                                             │
│  /api/upload          — receive dataset (CSV/Excel/JSON/log/Mongo export)   │
│  /api/run             — trigger LangGraph pipeline                          │
│  /api/stream          — WS: phase progress + live cell output               │
│  /api/kernel/*        — proxy to Jupyter Kernel Gateway                     │
│  /api/notebook/{id}   — fetch/update generated .ipynb                       │
│  /api/story/{id}      — fetch story JSON, regenerate, export as PDF         │
│  /api/history/{id}    — list/restore version snapshots                      │
│  /api/chat/{id}       — WS: conversational agent for follow-up questions    │
│  /api/session/{id}    — session state (dataset metadata, run status)        │
└──────────────┬──────────────────────┬───────────────────────────────────────┘
               │                      │
┌──────────────▼────────────┐  ┌──────▼──────────────────────────────────────┐
│   LANGGRAPH PIPELINE      │  │  CHAT AGENT (LangGraph ReAct)              │
│   Phase 1-11 (EDA_RULES)  │  │  - Reads CompositeState + notebook         │
│   Deterministic + LLM     │  │  - Can re-run specific phases              │
│   Conditional branching   │  │  - Answers "why" questions via causal graph │
│   Produces: notebook +    │  │  - Suggests next steps                     │
│   story + traces          │  │  - Can insert new cells into notebook      │
└──────────────┬────────────┘  └─────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────────────┐
│              KERNEL — Jupyter Kernel Gateway                                │
│  - Executes user-edited cells in an isolated Python kernel                  │
│  - Separate from agent: agent generates, kernel executes                    │
└──────────────┬──────────────────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────────────────┐
│              OUTPUT LAYER (per session)                                     │
│  sessions/{id}/traces/        — JSON diagnostics, plot PNGs                │
│  sessions/{id}/datasets/      — intermediate CSVs                          │
│  sessions/{id}/notebook.ipynb — generated + user-edited notebook           │
│  sessions/{id}/story.json     — structured story (derived from notebook)   │
│  sessions/{id}/history/       — version snapshots (notebook + story pairs) │
│  sessions/{id}/uploads/       — original uploaded files                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Target user**: Analysts (data/business) who know how to work with an ipynb
and want insights from their data. They may or may not want to model afterward.

**Backend framework**: LangChain / LangGraph (or DeepAgents when agent-level
abstractions are needed). All orchestration uses LangGraph StateGraphs.
LLM gates use `create_react_agent` or direct `ChatModel` calls with
structured Pydantic output. Deterministic tools use `@tool` decorators
from `langchain_core.tools`.

**Frontend framework**: Next.js (React) + Tailwind CSS. See Section 8 for
full frontend specification.

---

## 2. Current Implementation Status

### Fully Implemented (Stages 1-11, maps to EDA_RULES Phases 1-3)

| Stage | File | EDA Rules | Status |
|-------|------|-----------|--------|
| 1. Input validation | `ingest/handle_inputs.py` | Rules 1-2 | Done |
| 2. Datetime parsing | `ingest/format_datetime.py` | Rule 1 | Done |
| 3. Series type inference | `ingest/infer_type.py` | Rule 3 | Done |
| 4. Feature bucketing | `ingest/infer_structure.py` | Rule 4 | Done |
| 5. Temporal stats | `ingest/compute_temporal_stats.py` | Rules 5-6 | Done |
| 6. Integrity checks | `ingest/integrity.py` | Rule 2 | Done |
| 7. Missingness audit | `quality_handling/audit_missingness.py` | Rule 7 | Done |
| 8. Missingness handling | `quality_handling/handle_missingness.py` | Rule 8 | Done |
| 9. Standardization | `quality_handling/standardize.py` | Rule 9 | Done |
| 10. Univariate metrics | `univariate_analysis/univariate_metrics_plotting.py` | Rules 11-12 | Done |
| 11. Transform testing | `univariate_analysis/test_transforms.py` | Rule 13 | Done |

### Known TODOs in Existing Code
- Composite entity keys: only first element of `secondary_keys` used in integrity
- `known_exogenous_cols`, `target_cols`, `covariate_cols` fields exist in state but are never populated
- Timestamp reindexing: gaps are reported but missing timestamps are not inserted
- Some stages hardcode `model="gpt-4.1"` — should use config

### Not Yet Implemented (maps to EDA_RULES Phases 4-11)

| Phase | EDA Rules | Priority | Estimated Complexity |
|-------|-----------|----------|---------------------|
| 4. Temporal visualization | 14-19 | HIGH | Medium |
| 5. Dynamics & rolling | 20-22 | HIGH | Medium |
| 6. Bivariate/multivariate | 23-28 | HIGH | High |
| 7. Insight discovery | 29-31 | MEDIUM | High |
| 8. Causal analysis | 32-35 | MEDIUM | High |
| 9. Train/test splitting | 36-39 | HIGH | Low-Medium |
| 10. Model readiness | 40-43 | MEDIUM | Medium |
| 11. Wrap-up & reporting | 44-47 | HIGH | Medium |

---

## 3. Implementation Plan — Actionable Steps

Each step below is an atomic unit of work. Dependencies are noted.

### 3.1 Prerequisite: Fix Existing TODOs + Robust Ingestion

**STEP P.1** — Populate `target_cols` and `covariate_cols` in state.
- File: `ingest/infer_structure.py`
- Add an LLM gate after `infer_feature_buckets()` that looks at column names,
  data profiles, and user-provided hints to classify target vs covariates.
- If no target is identifiable, leave empty (unsupervised EDA path).
- Add `known_exogenous_cols` detection: match column names against a dictionary
  of known exogenous patterns (holiday, temperature, price, is_*, day_of_week).

**STEP P.2** — Support composite entity keys in integrity.
- File: `ingest/integrity.py`
- Replace `state["secondary_keys"][0]` with a tuple-based groupby across all
  secondary keys.

**STEP P.3** — Centralize model configuration.
- File: `config/config.py`
- Remove all hardcoded `model="gpt-4.1"` references.
- Add `get_gate_model()` and `get_agent_model()` helpers that read from config.

**STEP P.4** — Timestamp reindexing in missingness handling.
- File: `quality_handling/handle_missingness.py` + `tools/input_tools.py`
- After value imputation, optionally reindex to a regular grid based on
  `expected_frequency` from stage 5. Insert NaN rows for missing timestamps.
- Gate: only reindex if `is_irregular_sampling` is False and coverage < 95%.

**STEP P.5** — Robust multi-format ingestion.
- New file: `src/ingest/file_loader.py`
- Replace the current CSV-only `load_dataset()` with a universal loader:
  - **CSV**: `pd.read_csv()` with encoding detection (`chardet`) and delimiter
    sniffing
  - **Excel** (.xlsx, .xls): `pd.read_excel()`, handle multi-sheet workbooks
    (let user pick sheet, or default to first; show sheet names in frontend)
  - **JSON**: `pd.read_json()` for flat/records-oriented; `pd.json_normalize()`
    for nested JSON (detect nesting depth, flatten with dot-separated keys)
  - **NDJSON / JSON Lines** (.jsonl): line-by-line `pd.read_json(lines=True)`
  - **Parquet**: `pd.read_parquet()`
  - **Log files** (.log, .txt): regex-based parser with LLM-assisted format
    detection. Agent inspects first 20 lines, proposes a regex/grok pattern,
    extracts structured columns. Falls back to timestamp + message if no
    pattern found.
  - **MongoDB exports** (BSON dump / mongoexport JSON): detect MongoDB-style
    `$date`, `$oid` wrappers, unwrap to native types, flatten nested documents
    via `json_normalize()`
  - **TSV**: detected via delimiter sniffing (same path as CSV)
- All loaders produce a normalized `pd.DataFrame` + metadata dict:
  `{ source_format, original_filename, sheet_name (if Excel), encoding,
     row_count, col_count, load_warnings[] }`
- The rest of the pipeline (Stage 1+) is format-agnostic — it only sees the
  DataFrame.
- Add `openpyxl`, `chardet`, `pyarrow` to requirements.

### 3.2 Phase 4: Temporal Visualization (Rules 14-19)

**STEP 4.1** — Raw time series plots (Rule 14)
- New file: `src/temporal_analysis/plot_time_series.py`
- Deterministic tool: `plot_raw_time_series()`
  - Single series: single line plot of target(s)
  - Multivariate: small multiples grid (max 4x4, paginate if more)
  - Panel: overlay top-5 entities by volume, rest as light gray background
- Output: PNG files in `traces/{dataset}.time_series/`
- State update: `time_series_plots: List[str]` (paths)

**STEP 4.2** — Window zoom plots (Rule 15)
- Same file as 4.1
- Deterministic tool: `plot_zoom_windows()`
  - Auto-select 3 windows: last 10% of data, a random 5% window, the window
    around the largest spike detected in rule 22 (or random if not yet run)
  - Each window is a separate plot
- Output: PNG files

**STEP 4.3** — Multi-grain resampling (Rule 17)
- New file: `src/temporal_analysis/resample_analysis.py`
- Deterministic tool: `resample_and_plot()`
  - Resample target column(s) at 2-3 coarser frequencies
  - Aggregation method: sum for counts, mean for continuous, max for peaks
  - Side-by-side plots of native vs resampled
- State update: `resampling_report: dict`

**STEP 4.4** — Seasonality detection (Rule 18)
- New file: `src/temporal_analysis/seasonality.py`
- Deterministic tool: `detect_seasonality()`
  - Group by hour-of-day, day-of-week, month; compute mean + std per group
  - Statistical test: Kruskal-Wallis H-test per grouping to confirm significance
  - Plot: seasonal subseries plots
- State update: `seasonality_report: dict` with detected periods and p-values
- State update: `seasonality_detected: bool`

**STEP 4.5** — STL decomposition (Rule 19, conditional)
- Same file as 4.4
- Deterministic tool: `decompose_series()`
  - Use `statsmodels.tsa.seasonal.STL`
  - Plot: trend, seasonal, residual components
  - Compute residual normality (Shapiro-Wilk on residuals sample)
- Gate node: only run if `seasonality_detected == True`
- State update: `decomposition_report: dict`

**STEP 4.6** — Event/regime marking (Rule 16, conditional)
- New file: `src/temporal_analysis/event_overlay.py`
- Tool: `overlay_events()`
  - If `known_exogenous_cols` contains binary event flags, plot vertical spans
  - If user provides an event calendar (future: via frontend), overlay those
- Gate: only run if event columns detected or user-supplied

### 3.3 Phase 5: Dynamics & Rolling (Rules 20-22)

**STEP 5.1** — Rolling statistics (Rule 20)
- New file: `src/dynamics/rolling_stats.py`
- Deterministic tool: `compute_rolling_stats()`
  - Window sizes: auto-select based on frequency (e.g., 7/30/90 for daily)
  - Compute: mean, std, min, max per window
  - Plot: rolling mean + rolling std bands over raw series
- State update: `rolling_stats_report: dict`

**STEP 5.2** — Changepoint detection (Rule 21, conditional)
- New file: `src/dynamics/changepoints.py`
- Deterministic tool: `detect_changepoints()`
  - Use `ruptures` library (PELT algorithm with RBF kernel)
  - Output: list of changepoint indices/timestamps + confidence
  - Plot: raw series with vertical lines at changepoints
- Gate node: rolling variance ratio > 2x across windows
- State update: `changepoints: List[dict]`, `regime_shifts_detected: bool`

**STEP 5.3** — Outlier detection as time events (Rule 22)
- New file: `src/dynamics/outlier_detection.py`
- Deterministic tool: `detect_time_outliers()`
  - Method 1: Z-score on STL residuals (if decomposition was run)
  - Method 2: IQR-based on rolling windows (always available)
  - For each outlier: record timestamp, value, context window (5 points before/after)
  - LLM gate: classify outliers as spike/level-shift/plateau/variance-change
- State update: `outlier_report: dict`
- Dependencies: benefits from step 4.5 (decomposition) but not required

### 3.4 Phase 6: Bivariate & Multivariate (Rules 23-28)

**STEP 6.1** — Panel group comparison (Rules 23-24)
- New file: `src/multivariate/panel_compare.py`
- Deterministic tool: `compare_panel_entities()`
  - Per-entity boxplots of target variable
  - Per-entity time series overlay (top entities + aggregate)
  - Coefficient of variation across entities per time step
  - Kruskal-Wallis test across entity groups
- Gate: only run if `type == "multiple"`
- State update: `panel_comparison_report: dict`, `panel_heterogeneity: bool`

**STEP 6.2** — Correlation analysis (Rule 25)
- New file: `src/multivariate/correlation.py`
- Deterministic tool: `compute_correlations()`
  - Pearson + Spearman correlation matrices (full dataset)
  - Windowed correlation: split into 3-5 equal time windows, compute per-window
  - Flag: |r| > 0.95 pairs (redundant), sign-flip pairs across windows
  - Plot: heatmap of correlation matrix
- Gate: only run if >= 2 numeric features
- State update: `correlation_report: dict`

**STEP 6.3** — Mutual information (Rule 26, conditional)
- Same file as 6.2
- Tool: `compute_mutual_information()`
  - Use `sklearn.feature_selection.mutual_info_regression`
  - Compare MI ranking vs Pearson ranking; flag discrepancies
- Gate: domain flag or scatter-plot analysis suggests non-linearity
- State update: `mutual_info_report: dict`

**STEP 6.4** — Lag analysis (Rule 27)
- New file: `src/multivariate/lag_analysis.py`
- Deterministic tool: `compute_lag_relationships()`
  - ACF/PACF for target series (up to lag = 2 * seasonal_period or 40)
  - Cross-correlation between target and each covariate
  - Report: significant lag orders, lead/lag relationships
  - Plot: ACF/PACF plots, cross-correlation plots
- State update: `lag_report: dict`

**STEP 6.5** — Dimensionality reduction (Rule 28, conditional)
- New file: `src/multivariate/dimensionality.py`
- Deterministic tool: `run_dimensionality_scan()`
  - PCA: compute explained variance ratios, scree plot
  - If clusters suspected: UMAP 2D projection colored by entity/time-regime
- Gate: feature_count > 15
- State update: `dimensionality_report: dict`

### 3.5 Phase 7: Insight Discovery (Rules 29-31)

**STEP 7.1** — Automated insight mining (Rule 29)
- New file: `src/insights/insight_miner.py`
- Deterministic + LLM tool: `mine_insights()`
  - For each (dimension, measure) pair:
    - Compute: trend score (Mann-Kendall), outlier score (modified Z), dominance
      (top-1 share), evenness (entropy), correlation (with other measures)
  - Rank all insights by composite interestingness score
  - Top-K insights (K=10 default) returned with scores and mini-charts
- LLM role: generate natural-language descriptions of top insights
- State update: `insights: List[dict]`

**STEP 7.2** — MetaInsight: commonness/exception discovery (Rule 30)
- Same file or `src/insights/meta_insight.py`
- For each top insight from 7.1 that involves a dimension:
  - Check if the pattern holds across other values of the dimension (commonness)
  - Identify values where the pattern breaks (exceptions)
  - Score: how surprising is the exception vs the commonness?
- LLM role: synthesize structured knowledge sentences
- Gate: panel data or >= 3 values in the breakdown dimension
- State update: `meta_insights: List[dict]`

**STEP 7.3** — Drill-down on exceptions (Rule 31)
- Tool: `drill_down_exception()`
  - For each exception from 7.2, filter to that subgroup
  - Re-run insight mining on the filtered subset
  - Find the explaining dimension (which attribute accounts for the deviation)
  - Chain up to depth 3
- LLM role: decide which exceptions are worth drilling into, synthesize findings
- State update: `drill_down_findings: List[dict]`

### 3.6 Phase 8: Causal Analysis (Rules 32-35)

**STEP 8.1** — Causal graph discovery (Rule 32)
- New file: `src/causal/causal_graph.py`
- Library: `causal-learn` (Python package for causal discovery)
- Deterministic tool: `discover_causal_graph()`
  - Pre-screen: detect functional dependencies (FDs) and exclude them
  - Run FCI algorithm (handles latent confounders) on remaining variables
  - Output: partial ancestral graph (PAG) as adjacency matrix + edge types
  - Plot: DAG/PAG visualization using networkx/graphviz
- Gate: >= 3 features AND >= 200 rows
- State update: `causal_graph: dict`, `causal_graph_plot: str`

**STEP 8.2** — Causal vs non-causal classification (Rule 33)
- Same file
- Tool: `classify_explanations()`
  - Given a target variable and a context dimension, walk the causal graph
  - Classify each variable as: causal (ancestor of target), non-causal (d-separated
    or descendant), or ambiguous (bidirected edge)
  - LLM role: generate "why query" from top anomalies/exceptions, then classify
- State update: `causal_classifications: List[dict]`

**STEP 8.3** — Responsibility scoring (Rule 34)
- Tool: `compute_responsibility()`
  - For each causal factor, estimate counterfactual effect size
  - Method: interventional estimation via do-calculus approximation or
    simple subgroup comparison (practical proxy)
  - Output: ranked list of (factor, responsibility_score, direction)
- State update: `causal_responsibilities: List[dict]`

**STEP 8.4** — Granger causality (Rule 35)
- New file: `src/causal/granger.py`
- Deterministic tool: `test_granger_causality()`
  - Use `statsmodels.tsa.stattools.grangercausalitytests`
  - Pairwise tests for all numeric feature pairs
  - Max lag: min(seasonal_period, 20)
  - Report: significant links (p < 0.05) with lag order and direction
  - Plot: Granger causality network (directed graph)
- Gate: multivariate time series, stationarity confirmed or differenced
- State update: `granger_report: dict`

### 3.7 Phase 9: Train/Test Split (Rules 36-39)

**STEP 9.1** — Temporal split (Rule 36)
- New file: `src/split/temporal_split.py`
- Deterministic tool: `apply_temporal_split()`
  - Compute cutoff dates: train ends at 70th percentile timestamp, val at 85th,
    test is remainder (configurable)
  - For panel data: same cutoff across all entities
  - Write: train.csv, val.csv, test.csv to traces/
  - Add `split` column to the quality dataset
- State update: `split_dates: dict`, `split_sizes: dict`

**STEP 9.2** — CV strategy selection (Rule 37)
- Same file
- LLM gate: `select_cv_strategy()`
  - Input: data structure, row count, seasonality info
  - Output: one of [expanding_window, sliding_window, grouped_ts_cv, stratified_kfold]
  - Record parameters (n_splits, gap, window size)
- State update: `cv_strategy: dict`

**STEP 9.3** — Leakage validation (Rule 38)
- New file: `src/split/leakage_check.py`
- Deterministic tool: `validate_no_leakage()`
  - Check 1: no target-derived features in covariates (correlation with target > 0.99)
  - Check 2: lag/rolling features don't peek into future (verify index alignment)
  - Check 3: scaling fitted only on train split
  - Report: pass/fail per check with details
- State update: `leakage_report: dict`

**STEP 9.4** — Train/test distribution comparison (Rule 39)
- New file: `src/split/distribution_drift.py`
- Deterministic tool: `compare_split_distributions()`
  - Per feature: KS test (train vs test), PSI (population stability index)
  - Plot: overlaid histograms for features with significant drift (p < 0.05)
  - Flag: features with PSI > 0.2 (significant drift)
- State update: `drift_report: dict`

### 3.8 Phase 10: Model Readiness (Rules 40-43)

**STEP 10.1** — Stationarity tests (Rule 40)
- New file: `src/model_readiness/stationarity.py`
- Deterministic tool: `test_stationarity()`
  - ADF test + KPSS test on target and key covariates
  - If non-stationary: apply first differencing, re-test
  - If seasonal non-stationary: apply seasonal differencing
  - Report: original + differenced test results
- Gate: downstream modeling planned
- State update: `stationarity_report: dict`

**STEP 10.2** — Cointegration tests (Rule 41)
- Same file
- Tool: `test_cointegration()`
  - Johansen test on pairs of non-stationary series
  - Report: cointegrated pairs with rank and trace statistics
- Gate: >= 2 non-stationary series
- State update: `cointegration_report: dict`

**STEP 10.3** — Baseline feature engineering (Rule 42)
- New file: `src/model_readiness/baseline_features.py`
- Deterministic tool: `create_baseline_features()`
  - Calendar: hour, day_of_week, month, is_weekend, is_holiday (if calendar available)
  - Lags: target lags at [1, seasonal_period, 2*seasonal_period]
  - Rolling: rolling mean/std at [7, 30] (or frequency-appropriate windows)
  - Verify: no off-by-one (lag_1 at time t uses value at t-1, not t)
- State update: `baseline_features: List[str]`, `feature_dataset_path: str`

**STEP 10.4** — Feature importance screening (Rule 43)
- New file: `src/model_readiness/feature_importance.py`
- Deterministic tool: `screen_feature_importance()`
  - Train a quick LightGBM/RandomForest on train split
  - Compute: permutation importance (or built-in feature importance)
  - Rank features, drop those with importance < 1% of max
  - Plot: horizontal bar chart of feature importances
- Gate: feature_count > 10
- State update: `feature_importance_report: dict`

### 3.9 Phase 11: Wrap-Up & Reporting (Rules 44-47)

**STEP 11.1** — Decision summary (Rule 44)
- New file: `src/reporting/summary.py`
- LLM tool: `generate_decision_summary()`
  - Input: full CompositeState
  - Output: structured JSON with decisions for each category
  - LLM synthesizes findings into actionable recommendations
- State update: `decision_summary: dict`

**STEP 11.2** — Notebook generation (Rule 45)
- New file: `src/reporting/notebook_generator.py`
- Deterministic tool: `generate_notebook()`
  - Use `nbformat` to create a Jupyter notebook
  - One section per executed phase, with:
    - Markdown cell: phase title + what was found
    - Code cell: reproducible code that produces the same plots/metrics
    - Output cells: inline plots from traces/
  - The notebook is RUNNABLE — user can re-execute and modify
- Output: `traces/{dataset}_eda.ipynb`
- State update: `notebook_path: str`

**STEP 11.3** — Story generation (Rule 46)
- New file: `src/reporting/story_generator.py`
- LLM + deterministic tool: `generate_story()`
  - The "Story" is a narrative document DERIVED from the notebook. It reads the
    notebook's cell outputs (metrics, plots, insights) and synthesizes them into
    a structured, readable narrative aimed at analysts and stakeholders.
  - Structure: executive summary -> per-phase sections -> decision recommendations
  - Each section: natural-language findings, inline plots (referenced from traces/),
    insight provenance (which rule, which subset, confidence/p-value)
  - The story is regenerable: when the user edits the notebook and confirms changes,
    the backend re-runs `generate_story()` against the updated notebook state.
  - Export targets: PDF (via `weasyprint`), Markdown
- Output: `sessions/{id}/story.json` (structured, for frontend rendering),
  `sessions/{id}/story.md` (flat markdown for export)
- State update: `story_path: str`

**STEP 11.4** — Version history system
- New file: `src/reporting/versioning.py`
- Tool: `create_version_snapshot(session_id, trigger)`
  - Saves a snapshot of the current notebook + story state as a version.
  - Snapshot contents: notebook.ipynb (full), story.json, CompositeState summary,
    timestamp, trigger description (e.g., "initial generation", "user confirmed
    edits", "chat-driven re-analysis").
  - Stored in `sessions/{id}/history/v{n}/`
  - Version metadata index: `sessions/{id}/history/versions.json`
- Tool: `list_versions(session_id)` — returns version list with timestamps and
  triggers
- Tool: `restore_version(session_id, version_id)` — restores notebook + story
  from a snapshot (current state is auto-snapshotted before restore)
- Automatic snapshot triggers:
  1. After initial pipeline run completes
  2. When user clicks "Confirm Changes" after editing the notebook
  3. When chat agent modifies the notebook
- State update: `version_count: int`, `current_version: int`

---

## 4. LangGraph Pipeline Architecture

### Graph Topology

```
                    ┌──────────────────┐
                    │   START          │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Phase 1: Ingest │  (Stages 1-6, existing)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Phase 2: Quality│  (Stages 7-9, existing)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Phase 3: Univ.  │  (Stages 10-11, existing)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Phase 4: Temporal│  (NEW: Steps 4.1-4.6)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Phase 5: Dynamics│  (NEW: Steps 5.1-5.3)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────────────┐
                    │  BRANCHING GATE           │
                    │  reads: type, feature_ct, │
                    │  row_count, covariates    │
                    └──┬─────┬──────┬──────┬───┘
                       │     │      │      │
              ┌────────▼┐ ┌─▼────┐ │  ┌───▼──────┐
              │Phase 6  │ │Phase7│ │  │Phase 8   │
              │Bivar/MV │ │Insght│ │  │Causal    │
              └────┬────┘ └──┬───┘ │  └───┬──────┘
                   │         │     │      │
                   └─────────┴─────┴──────┘
                             │
                    ┌────────▼─────────┐
                    │  Phase 9: Split  │  (NEW: Steps 9.1-9.4)
                    └────────┬─────────┘
                             │
                    ┌────────▼──────────────┐
                    │  MODELING GATE        │
                    │  reads: modeling_planned
                    └────┬───────────┬──────┘
                         │           │
                ┌────────▼────┐      │ (skip)
                │Phase 10:    │      │
                │Model Ready  │      │
                └────────┬────┘      │
                         │           │
                         └─────┬─────┘
                               │
                    ┌──────────▼───────┐
                    │  Phase 11: Report│  (NEW: Steps 11.1-11.4)
                    └──────────┬───────┘
                               │
                    ┌──────────▼───────┐
                    │      END         │
                    └──────────────────┘
```

### Implementing Conditional Branching in LangGraph

Each gate is a **conditional edge** in the StateGraph:

```python
def branching_gate(state: CompositeState) -> list[str]:
    """Returns list of phase node names to execute."""
    branches = []
    if state["type"] == "multiple":
        branches.append("phase_6_panel")
    if len(state.get("numeric_continuous_cols", [])) >= 2:
        branches.append("phase_6_correlation")
    if _has_dimensions(state):
        branches.append("phase_7_insights")
    if (len(state.get("numeric_continuous_cols", [])) >= 3
            and state.get("row_count", 0) >= 200):
        branches.append("phase_8_causal")
    if not branches:
        branches.append("phase_9_split")  # skip to split
    return branches
```

Phases 6, 7, 8 can run as **parallel branches** via LangGraph's `Send` API
(fan-out, fan-in before Phase 9).

### State Schema Extension

Add these fields to `CompositeState`:

```python
# Phase 4
time_series_plots: list[str]
resampling_report: dict
seasonality_report: dict
seasonality_detected: bool
decomposition_report: dict

# Phase 5
rolling_stats_report: dict
changepoints: list[dict]
regime_shifts_detected: bool
outlier_report: dict

# Phase 6
panel_comparison_report: dict
panel_heterogeneity: bool
correlation_report: dict
mutual_info_report: dict
lag_report: dict
dimensionality_report: dict

# Phase 7
insights: list[dict]
meta_insights: list[dict]
drill_down_findings: list[dict]

# Phase 8
causal_graph: dict
causal_classifications: list[dict]
causal_responsibilities: list[dict]
granger_report: dict

# Phase 9
split_dates: dict
split_sizes: dict
cv_strategy: dict
leakage_report: dict
drift_report: dict

# Phase 10
stationarity_report: dict
cointegration_report: dict
baseline_features: list[str]
feature_dataset_path: str
feature_importance_report: dict

# Phase 11
decision_summary: dict
notebook_path: str
report_path: str
changelog_path: str
```

---

## 5. New Dependencies

Add to `requirements.txt`:

```
# Robust ingestion (P.5)
openpyxl>=3.1             # Excel (.xlsx) support
chardet>=5.0              # Encoding detection for CSV/TSV
pyarrow>=14.0             # Parquet support

# Phase 4: Temporal
statsmodels>=0.14         # STL decomposition, seasonal tests

# Phase 5: Dynamics
ruptures>=1.1             # Changepoint detection (PELT, BOCPD)

# Phase 6: Multivariate
scikit-learn>=1.3         # Mutual information, PCA, UMAP preprocessing
umap-learn>=0.5           # UMAP projections (optional)

# Phase 8: Causal
causal-learn>=0.1         # PC, FCI, GES causal discovery algorithms
networkx>=3.0             # Graph representation and visualization

# Phase 10: Model readiness
lightgbm>=4.0             # Quick baseline model for feature importance

# Phase 11: Story + versioning
nbformat>=5.9             # Notebook generation (likely already present)
nbclient>=0.8             # Notebook execution
weasyprint>=62            # PDF export from HTML/Markdown

# Backend server
fastapi>=0.115
uvicorn[standard]>=0.30
python-multipart>=0.0.9   # File upload handling
websockets>=12.0          # WebSocket support

# Kernel management
jupyter-kernel-gateway>=3.0

# Markdown rendering for PDF
markdown>=3.6
```

---

## 6. File Organization

```
src/
├── main.py
├── config/
│   ├── config.py                  # FIX: centralize model refs
│   └── .env
├── tools/
│   ├── input_tools.py             # Existing deterministic tools
│   └── state_schema.py            # CompositeState TypedDict (shared)
├── ingest/                        # Existing (Phases 1-2)
│   ├── handle_inputs.py
│   ├── file_loader.py             # NEW: multi-format loader (P.5)
│   ├── format_datetime.py
│   ├── infer_type.py
│   ├── infer_structure.py         # FIX: populate target/covariate cols
│   ├── compute_temporal_stats.py
│   └── integrity.py               # FIX: composite keys
├── quality_handling/              # Existing (Phase 2)
│   ├── audit_missingness.py
│   ├── handle_missingness.py      # FIX: timestamp reindexing
│   └── standardize.py
├── univariate_analysis/           # Existing (Phase 3)
│   ├── univariate_metrics_plotting.py
│   └── test_transforms.py
├── temporal_analysis/             # NEW (Phase 4)
│   ├── __init__.py
│   ├── plot_time_series.py        # Steps 4.1, 4.2
│   ├── resample_analysis.py       # Step 4.3
│   ├── seasonality.py             # Steps 4.4, 4.5
│   └── event_overlay.py           # Step 4.6
├── dynamics/                      # NEW (Phase 5)
│   ├── __init__.py
│   ├── rolling_stats.py           # Step 5.1
│   ├── changepoints.py            # Step 5.2
│   └── outlier_detection.py       # Step 5.3
├── multivariate/                  # NEW (Phase 6)
│   ├── __init__.py
│   ├── panel_compare.py           # Step 6.1
│   ├── correlation.py             # Steps 6.2, 6.3
│   ├── lag_analysis.py            # Step 6.4
│   └── dimensionality.py          # Step 6.5
├── insights/                      # NEW (Phase 7)
│   ├── __init__.py
│   ├── insight_miner.py           # Step 7.1
│   └── meta_insight.py            # Steps 7.2, 7.3
├── causal/                        # NEW (Phase 8)
│   ├── __init__.py
│   ├── causal_graph.py            # Steps 8.1, 8.2, 8.3
│   └── granger.py                 # Step 8.4
├── split/                         # NEW (Phase 9)
│   ├── __init__.py
│   ├── temporal_split.py          # Steps 9.1, 9.2
│   ├── leakage_check.py           # Step 9.3
│   └── distribution_drift.py      # Step 9.4
├── model_readiness/               # NEW (Phase 10)
│   ├── __init__.py
│   ├── stationarity.py            # Steps 10.1, 10.2
│   ├── baseline_features.py       # Step 10.3
│   └── feature_importance.py      # Step 10.4
├── reporting/                     # NEW (Phase 11)
│   ├── __init__.py
│   ├── summary.py                 # Step 11.1
│   ├── notebook_generator.py      # Step 11.2
│   ├── story_generator.py         # Step 11.3 (Story, not Report)
│   └── versioning.py              # Step 11.4 (History snapshots)
├── chat/                          # NEW (Chat agent)
│   ├── __init__.py
│   └── chat_agent.py             # Conversational follow-up agent
└── pipeline.py                    # Master LangGraph wiring (all phases)

backend/                           # NEW (FastAPI server)
├── app.py                         # FastAPI app, CORS, lifespan
├── routers/
│   ├── session.py                 # upload, session CRUD
│   ├── run.py                     # trigger pipeline
│   ├── stream.py                  # WS: agent progress
│   ├── kernel.py                  # WS proxy to kernel gateway
│   ├── notebook.py                # notebook CRUD
│   ├── story.py                   # story fetch/regenerate/export
│   ├── history.py                 # version list/restore
│   └── chat.py                    # WS: conversational agent
├── models/                        # Pydantic request/response models
│   ├── session.py
│   ├── story.py
│   └── history.py
└── services/
    ├── session_manager.py         # Session lifecycle + file storage
    ├── kernel_manager.py          # Kernel start/stop/proxy
    ├── story_service.py           # Story regeneration + PDF export
    └── history_service.py         # Version snapshot CRUD

frontend/                          # NEW (Next.js app)
├── app/
│   ├── layout.tsx                 # 3-column layout shell
│   ├── page.tsx                   # Landing / upload
│   └── session/[id]/page.tsx      # Workspace (tabbed center + chat)
├── components/
│   ├── sidebar/
│   │   ├── FileSidebar.tsx        # Left: collapsible file tree
│   │   └── FileItem.tsx
│   ├── notebook/
│   │   ├── NotebookPane.tsx       # Center tab: notebook editor
│   │   ├── NotebookCell.tsx
│   │   ├── CodeEditor.tsx         # Monaco wrapper
│   │   ├── CellOutput.tsx
│   │   └── CellToolbar.tsx
│   ├── story/
│   │   ├── StoryPane.tsx          # Center tab: narrative view
│   │   ├── StorySection.tsx
│   │   ├── InsightCard.tsx
│   │   └── ExportDialog.tsx
│   ├── history/
│   │   ├── HistoryPanel.tsx       # Version list overlay
│   │   └── VersionItem.tsx
│   ├── chat/
│   │   ├── ChatSidebar.tsx        # Right: chat interface
│   │   ├── ChatMessage.tsx
│   │   └── ChatInput.tsx
│   ├── layout/
│   │   ├── ThreeColumnLayout.tsx
│   │   ├── TabBar.tsx             # Notebook | Story | History toggle
│   │   └── ProgressOverlay.tsx
│   └── upload/
│       ├── DropZone.tsx
│       └── DataPreview.tsx
├── hooks/
│   ├── useAgentStream.ts
│   ├── useKernel.ts
│   ├── useChat.ts
│   ├── useHistory.ts
│   └── useSession.ts
├── stores/
│   ├── sessionStore.ts
│   ├── notebookStore.ts
│   ├── storyStore.ts
│   ├── chatStore.ts
│   └── kernelStore.ts
└── lib/
    ├── api.ts
    ├── kernelProtocol.ts
    ├── notebookModel.ts
    ├── diffEngine.ts
    └── types.ts
```

---

## 7. Implementation Priority & Sequencing

### Sprint 1: Foundation (complete existing gaps + temporal)
1. Steps P.1-P.4 (fix existing TODOs)
2. Steps 4.1-4.4 (temporal visualization + seasonality)
3. Steps 5.1, 5.3 (rolling stats + outlier detection)
4. Step 9.1 (temporal split — needed early for leakage checks)

### Sprint 2: Multivariate + Insights
1. Steps 6.1-6.2, 6.4 (panel comparison, correlation, lag analysis)
2. Steps 4.5-4.6 (decomposition, event overlay)
3. Steps 7.1-7.2 (insight mining, meta-insights)
4. Step 9.3 (leakage validation)

### Sprint 3: Causal + Model Readiness
1. Steps 8.1-8.3 (causal graph + classification + responsibility)
2. Steps 8.4 (Granger causality)
3. Steps 10.1-10.4 (stationarity, features, importance)
4. Steps 9.2, 9.4 (CV strategy, distribution drift)

### Sprint 4: Reporting + Frontend Integration
1. Steps 11.1-11.4 (summary, notebook gen, report gen, changelog)
2. Steps 5.2, 6.3, 6.5, 7.3 (conditional steps: changepoints, MI, dim reduction, drill-down)
3. Frontend integration (see Section 8)

---

## 8. Frontend Specification — Custom Web App

### 8.1 Decision

**Custom web app** using Next.js (React) + Tailwind CSS.

Three-column layout matching the wireframe: collapsible file sidebar (left),
tabbed center pane (Notebook / Story, with History toggle), and collapsible
chat interface (right).

### 8.2 Core UX Flow

```
1. LANDING
   Full-screen drop zone. User drags dataset(s) onto it.
   Accepted formats: CSV, Excel, JSON, NDJSON, Parquet, log files, MongoDB exports.
   Frontend shows: file name, size, first-5-row preview, detected columns.
   For Excel: sheet selector dropdown.
   User clicks "Run EDA" -> navigates to workspace.

2. WORKSPACE — 3-COLUMN LAYOUT
   ┌──────────┬────────────────────────────┬──────────────┐
   │  Files   │  [Notebook] [Story]  [⏱]  │    Chat      │
   │ (left)   │     Center pane            │   (right)    │
   │collapsible│    (tabbed)               │ collapsible  │
   └──────────┴────────────────────────────┴──────────────┘

   LEFT SIDEBAR — Collapsible file tree:
   - Uploaded datasets (click to view/re-run)
   - Generated notebooks (per dataset)
   - Exported stories (PDFs)
   - Back arrow: returns to landing page

   CENTER PANE — Tab bar: [Notebook] [Story] + [⏱ History]
   - Notebook tab (default): Google-Colab-like editor. Cells appear
     pre-run as agent generates them. User can edit and re-run.
   - Story tab: narrative insights derived FROM the notebook. Auto-generated
     on pipeline completion. Read-only unless regenerated.
   - History button (⏱): opens version list overlay. Click any version to
     restore that snapshot of notebook + story.

   RIGHT SIDEBAR — Chat interface:
   - Conversational agent for follow-up questions
   - "Why is feature X trending?" -> agent answers citing notebook cells
   - "Drill into entity Y" -> agent inserts new cells into notebook
   - "Re-run with different parameters" -> agent modifies and re-executes
   - Chat history persists per session

3. DURING AGENT RUN
   Center pane shows Notebook tab with progress overlay (phase badges).
   Cells appear incrementally as each phase completes (already executed,
   with outputs). Chat sidebar shows agent status messages.

4. AFTER COMPLETION
   Notebook tab: full EDA notebook, all cells pre-run with outputs.
   Story tab: structured narrative derived from notebook outputs.
   User can freely switch between tabs.

5. USER EDITS NOTEBOOK
   User modifies cells, adds new cells, re-runs them via Shift+Enter.
   A "Confirm Changes" button appears in the tab bar when edits are detected.
   On confirm:
     - A version snapshot is saved (notebook + story at this point)
     - Story is regenerated from the updated notebook state
     - Story tab auto-updates; previous version accessible via History

6. CHAT-DRIVEN ANALYSIS
   User asks a question in the chat sidebar.
   Chat agent can:
     - Answer from existing state/notebook (no mutation)
     - Insert new cells into the notebook (e.g., new plot, new test)
     - Re-run specific phases with different parameters
   Each chat-driven mutation triggers a version snapshot.

7. HISTORY
   History overlay shows a timeline of versions:
     v1: "Initial EDA run" — Apr 4, 14:00
     v2: "User edited: changed log transform on revenue" — Apr 4, 14:23
     v3: "Chat: added Granger test for temperature→demand" — Apr 4, 14:45
   Click any version -> restore notebook + story to that state.
   Current state is auto-snapshotted before restore.

8. EXPORT
   Story tab has an export bar: [Download PDF] [Download Markdown]
   PDF is rendered server-side (weasyprint) from the story content.
   Notebook is also downloadable as .ipynb from the file sidebar.
```

### 8.3 Layout Detail

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Back                                                         │
├──────────┬──────────────────────────────────────┬───────────────┤
│          │  [Notebook]  [Story]           [⏱]   │               │
│  FILES   │ ┌──────────────────────────────────┐ │    CHAT       │
│          │ │                                  │ │               │
│ dataset1 │ │   Active tab content:            │ │  User: Why is │
│  .csv    │ │                                  │ │  revenue      │
│ dataset2 │ │   Notebook: code cells + outputs │ │  dropping?    │
│  .xlsx   │ │     — OR —                       │ │               │
│          │ │   Story: narrative + plots        │ │  Agent: Based │
│ notebook │ │     — OR —                       │ │  on the trend │
│  .ipynb  │ │   History: version timeline       │ │  analysis...  │
│          │ │                                  │ │               │
│ story    │ │                                  │ │  [input box]  │
│  .pdf    │ └──────────────────────────────────┘ │               │
│          │  [Confirm Changes]  (when dirty)     │               │
├──────────┴──────────────────────────────────────┴───────────────┤
│  status bar: "Phase 4/11 — Temporal Analysis"  │ kernel: idle   │
└─────────────────────────────────────────────────────────────────┘

Left sidebar:  ~200px, collapsible to icon rail
Center pane:   flex-grow (fills remaining space)
Right sidebar: ~320px, collapsible to icon rail
```

### 8.4 Notebook Tab — Implementation Detail

Custom React component (NOT embedded JupyterLab):

**Cell rendering:**
- Each cell is a `NotebookCell` with modes: `code` and `markdown`.
- Code cells use **Monaco Editor** (`@monaco-editor/react`) with Python syntax,
  auto-indent, and basic completion.
- Markdown cells use `react-markdown` with `remark-gfm`.
- Cell outputs rendered by `CellOutput`:
  - `text/plain`, `text/html`: rendered directly
  - `image/png`: base64 `<img>` tag
  - `application/vnd.plotly.v1+json`: `react-plotly.js`
  - `stderr`: red-tinted monospace block
  - `traceback`: ANSI-colored with `ansi-to-html`

**Cell execution:**
- Shift+Enter sends `execute_request` to kernel via WebSocket proxy.
- IOPub messages captured and rendered in real-time.
- `useKernel` hook manages connection, routing, and FIFO execution queue.

**Cell operations:**
- Add cell above/below (code or markdown)
- Delete cell, Move up/down
- Run cell / Run all cells / Clear output

**Dirty state tracking:**
- When user edits any cell (source or adds/deletes cells), notebook enters
  "dirty" state. A "Confirm Changes" button appears.
- On confirm: `POST /api/notebook/{id}/confirm` -> triggers version snapshot +
  story regeneration.

### 8.5 Story Tab — Implementation Detail

The Story is a **narrative document derived from the notebook**, not a parallel
report. It is generated by the LLM reading the notebook's cell outputs and
synthesizing a readable narrative.

**Structure:**
```
Story Tab
├── Title + metadata (dataset, run date, version)
├── Executive Summary (2-3 sentence overview of key findings)
├── Phase sections (auto-generated, flowing prose):
│   ├── "Data Profile" (from phases 1-3)
│   ├── "Temporal Patterns" (from phase 4)
│   ├── "Anomalies & Dynamics" (from phase 5)
│   ├── "Relationships" (from phases 6-8)
│   ├── "Data Readiness" (from phases 9-10)
│   └── "Recommendations" (from phase 11)
├── Inline plots (key charts from notebook, not all)
├── Insight cards (interactive, expandable)
└── Export bar: [Download PDF] [Download Markdown]
```

**Regeneration flow:**
1. User edits notebook and clicks "Confirm Changes"
2. Backend snapshots current state as a version
3. Backend calls `generate_story()` with updated notebook
4. Story tab updates. Sections that changed are highlighted briefly.
5. Previous story accessible via History.

### 8.6 History Panel

Triggered by the ⏱ button in the tab bar. Opens as an overlay or replaces
the center pane content (like Google Docs version history).

**Version list:**
```
┌────────────────────────────────────────────┐
│  Version History                      [✕]  │
├────────────────────────────────────────────┤
│  ● v3 (current)                            │
│    "Chat: added Granger causality test"    │
│    Apr 4, 2026 14:45                       │
│                                            │
│  ○ v2                          [Restore]   │
│    "User edited: log transform on revenue" │
│    Apr 4, 2026 14:23                       │
│                                            │
│  ○ v1                          [Restore]   │
│    "Initial EDA run"                       │
│    Apr 4, 2026 14:00                       │
└────────────────────────────────────────────┘
```

**Restore:** clicking "Restore" snapshots the current state first, then loads
the selected version's notebook + story into the workspace.

### 8.7 Chat Sidebar — Implementation Detail

Right sidebar with a conversational interface.

**Architecture:**
- Frontend: `ChatSidebar` component with `ChatMessage` list + `ChatInput`.
- Backend: `WS /api/chat/{session_id}` connects to a LangGraph ReAct agent.
- The chat agent has access to:
  - Full `CompositeState` (read-only): all metrics, reports, findings
  - Notebook content (read): can reference specific cells
  - Notebook mutation tools: `insert_cell(position, code)`, `modify_cell(id, code)`
  - Phase re-run tools: `rerun_phase(phase_id, params)` (subset of pipeline)
  - Causal query tools: `explain_why(target, context)` (uses Phase 8 graph)

**Chat message types:**
- `user`: plain text question
- `agent_text`: narrative answer
- `agent_cell_ref`: answer that references a notebook cell (clickable link
  that scrolls-to and highlights the cell in notebook tab)
- `agent_action`: "I've added a new cell to the notebook" / "I've re-run
  Phase 5 with window_size=14" (with undo button)

**Implementation:**
- `useChat` hook manages WebSocket to `/api/chat/{session_id}`
- `chatStore` (Zustand): message history, typing indicator, pending actions
- Chat persists per session (stored server-side alongside notebook/story)

### 8.8 Kernel Management

The frontend does NOT run Python. All code execution happens server-side via
Jupyter Kernel Gateway.

**Architecture:**
```
Browser (NotebookPane)
    │
    │  WebSocket: ws://backend/api/kernel/{session_id}/channels
    │
    ▼
FastAPI backend
    │
    │  Proxies to Jupyter Kernel Gateway (one kernel per session)
    │
    ▼
Jupyter Kernel Gateway (jupyter_kernel_gateway or jupyter-server)
    │
    ▼
IPython kernel (isolated per session)
    - Working directory: /sessions/{session_id}/
    - Pre-loaded: dataset path, pandas, matplotlib, etc.
```

**Kernel lifecycle:**
1. On session creation (`POST /api/upload`), backend starts a new kernel.
2. Agent-generated cells are NOT executed via the kernel — the agent runs its
   own pipeline server-side and produces code strings + pre-computed outputs.
3. The frontend displays cells with pre-computed outputs from traces/.
4. When the user runs a cell, the frontend sends `execute_request` through the
   kernel WebSocket proxy.
5. Kernel shuts down on session deletion or idle timeout (30 min default).

### 8.9 Backend API Specification

```
POST   /api/upload
       Body: multipart/form-data (file + optional config)
       Accepts: CSV, Excel, JSON, NDJSON, Parquet, log, MongoDB export
       Returns: { session_id, dataset_preview, detected_columns, source_format }

POST   /api/run/{session_id}
       Triggers the LangGraph pipeline. Returns: 202 Accepted

WS     /api/stream/{session_id}
       Server sends JSON messages:
         { type: "phase_start", phase: "temporal", step: "4.1" }
         { type: "cell_ready", cell_id, cell_type, source, output }
         { type: "phase_complete", phase, findings: [...] }
         { type: "pipeline_complete", story_url, notebook_url }

GET    /api/notebook/{session_id}
       Returns: full notebook as nbformat JSON

PATCH  /api/notebook/{session_id}
       Body: { cells: [...] }  (full cell array after user edits)

POST   /api/notebook/{session_id}/confirm
       Triggers: version snapshot + story regeneration
       Returns: { version_id, story_url }

GET    /api/story/{session_id}?format=json|md|pdf
       format=json: structured story (for React rendering)
       format=md:   markdown string
       format=pdf:  binary PDF

POST   /api/story/{session_id}/regenerate
       Re-derives story from current notebook state
       Returns: { version_id }

GET    /api/history/{session_id}
       Returns: list of version snapshots with timestamps + triggers

POST   /api/history/{session_id}/restore/{version_id}
       Auto-snapshots current state, then restores selected version
       Returns: { new_version_id, restored_version_id }

WS     /api/chat/{session_id}
       Bidirectional: user messages -> agent responses
       Agent can emit: text, cell_ref, cell_insert, phase_rerun

WS     /api/kernel/{session_id}/channels
       Proxied Jupyter kernel WebSocket (shell, iopub, stdin)

DELETE /api/session/{session_id}
       Tears down kernel, cleans up session files

GET    /api/sessions
       Returns: list of active sessions with metadata
```

### 8.10 Frontend Dependencies

```json
{
  "dependencies": {
    "next": "^15",
    "react": "^19",
    "tailwindcss": "^4",
    "@monaco-editor/react": "^4",
    "react-markdown": "^9",
    "remark-gfm": "^4",
    "react-dropzone": "^14",
    "react-plotly.js": "^2",
    "plotly.js": "^2",
    "ansi-to-html": "^0.7",
    "zustand": "^5",
    "uuid": "^10"
  }
}
```

**State management**: Zustand stores:
- `sessionStore`: active session ID, session list, upload state
- `notebookStore`: cells array, execution queue, dirty flag, baseline snapshots
- `storyStore`: story JSON, current version, loading state
- `chatStore`: message history, typing indicator, pending actions
- `kernelStore`: connection status, busy/idle, execution count

### 8.11 Key Architecture Decisions

**Notebook as Output, Not as Runtime:**
The agent generates the notebook as an artifact (server-side via nbformat),
NOT by running inside a notebook. The frontend displays pre-computed outputs
and lets the user re-execute/edit via a separate kernel.

**Story is derived, not parallel:**
The story is generated AFTER the notebook is complete, by reading the notebook's
outputs and synthesizing a narrative. It is not a second output track — it's a
view of the notebook. When the notebook changes, the story is regenerated.

**Version-based change tracking (not changelog diffs):**
Instead of tracking individual cell diffs, the system takes full snapshots.
Each snapshot = notebook + story + timestamp + trigger description. This is
simpler, more reliable, and gives the user a familiar "version history" UX
(like Google Docs) instead of a cryptic diff log.

**One kernel per session:**
Each session gets its own IPython kernel, pre-seeded with the dataset path
and common imports. Isolated, garbage-collected on idle timeout.

**Chat agent has mutation powers:**
The chat agent can insert cells and re-run phases, not just answer questions.
Every mutation triggers a version snapshot so the user can always undo.
