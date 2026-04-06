"""
Consolidated pipeline state schema.

Every phase reads from and writes to a single CompositeState TypedDict.
Each field documents which phase produces it. Both Person A and Person B
add fields here; neither deletes fields owned by the other.

Import as:

    from src.tools.state_schema import CompositeState
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


# ---------------------------------------------------------------------------
# Phase 1 — Ingest & Parse (Rules 1-6)
# Owner: existing code (handle_inputs, format_datetime, infer_type,
#        infer_structure, compute_temporal_stats, integrity)
# ---------------------------------------------------------------------------

class CompositeState(TypedDict, total=False):
    """
    Master state flowing through the LangGraph pipeline.

    ``total=False`` means every field is optional — stages populate them
    progressively as the pipeline executes.
    """

    # -- Stage 1: handle_inputs -----------------------------------------
    path: str
    """Path to the source dataset file."""

    done: list[str]
    """List of completed stage names."""

    has_header: bool
    """Whether the dataset has a valid header row."""

    has_missing_values: bool
    """Whether any missing values were detected."""

    error: str
    """Error message from validation (empty if clean)."""

    info: str
    """Informational message from validation."""

    cols: list[str]
    """All column names in the dataset."""

    temporal_cols: list[str]
    """Columns identified as temporal / datetime."""

    numeric_val_cols: list[str]
    """Columns identified as numeric values."""

    categorical_val_cols: list[str]
    """Columns identified as categorical values."""

    bad_rows: list[dict]
    """Rows that failed validation (row_index, csv_row_number, reasons, etc.)."""

    # -- Stage 2: format_datetime ---------------------------------------
    time_col: str
    """Selected primary temporal column name."""

    candidates: list[dict]
    """Datetime parser candidates evaluated during format detection."""

    winner_formatter: dict
    """Winning datetime format configuration."""

    # -- Stage 3: infer_type --------------------------------------------
    metadata: dict
    """Per-column metadata profiles from input_tools."""

    numeric_cols: list[str]
    """Numeric columns (alias of numeric_val_cols after type inference)."""

    nonnegative_cols: list[str]
    """Columns constrained to non-negative values."""

    jump_mult: float
    """Multiplier threshold for impossible-jump detection (default 20.0)."""

    type: Literal["single", "multiple", "multivariate"]
    """Inferred series structure: single / multiple (panel) / multivariate."""

    primary_key: str
    """Primary key column (the time axis)."""

    secondary_keys: list[str]
    """Entity identifier columns for panel data."""

    entity_col: str | None
    """First secondary key shortcut (None for non-panel data)."""

    # -- Stage 4: infer_structure ---------------------------------------
    numeric_continuous_cols: list[str]
    """Continuous numeric feature columns."""

    numeric_count_cols: list[str]
    """Count-like numeric feature columns."""

    binary_flag_cols: list[str]
    """Binary 0/1 flag columns."""

    categorical_feature_cols: list[str]
    """Categorical feature columns."""

    known_exogenous_cols: list[str]
    """Columns matching known exogenous patterns (holiday, price, etc.)."""

    target_cols: list[str]
    """Target / outcome columns (populated by P.1 LLM gate)."""

    covariate_cols: list[str]
    """Covariate columns (populated by P.1 LLM gate)."""

    # -- Stage 5: compute_temporal_stats --------------------------------
    n_nat_time: int
    """Count of NaT / missing timestamps."""

    min_time: str | None
    """Earliest timestamp (ISO string)."""

    max_time: str | None
    """Latest timestamp (ISO string)."""

    typical_delta_mode: str | None
    """Mode of consecutive timestamp deltas."""

    typical_delta_median: str | None
    """Median of consecutive timestamp deltas."""

    expected_frequency: str | None
    """Inferred sampling frequency (e.g. '1h', '1D')."""

    dominant_frequency_fraction: float
    """Fraction of deltas matching the dominant frequency."""

    is_irregular_sampling: bool
    """True if sampling is irregular."""

    resampling_decision: str
    """Recommended resampling action."""

    coverage_summary: dict
    """Overall temporal coverage statistics."""

    coverage_per_entity: list[dict]
    """Per-entity temporal coverage details."""

    # -- Stage 6: integrity ---------------------------------------------
    report: dict
    """Integrity report (summary stats + issues list)."""

    summary: str
    """Human-readable integrity summary (LLM-generated)."""

    flag: str
    """Go / no-go flag from integrity check ('yes' / 'no')."""

    # -------------------------------------------------------------------
    # Phase 2 — Data Quality (Rules 7-10)
    # -------------------------------------------------------------------

    # -- Stage 7: audit_missingness -------------------------------------
    missingness_report: dict
    """Detailed missingness audit (value + timestamp missingness)."""

    # -- Stage 8: handle_missingness ------------------------------------
    missingness_plan: dict
    """Per-column missingness handling plan (strategy + reasons)."""

    missingness_handling_report: dict
    """Execution report for missingness handling."""

    quality_dataset_path: str
    """Path to the quality-handled dataset CSV."""

    # -- Stage 9: standardize -------------------------------------------
    standardization_profile: dict
    """Per-column scale and tail behavior profile."""

    standardization_gate: dict
    """Dataset-level gate: {should_standardize, reason}."""

    standardization_plan: dict
    """Per-column standardization decisions."""

    standardization_report: dict
    """Transformation execution report."""

    standardized_dataset_path: str
    """Path to the standardized dataset CSV."""

    # -------------------------------------------------------------------
    # Phase 3 — Univariate Analysis (Rules 11-13)
    # -------------------------------------------------------------------

    # -- Stage 10: univariate_metrics_plotting --------------------------
    univariate_report: dict
    """Per-feature univariate summaries and plot paths."""

    # -- Stage 11: test_transforms --------------------------------------
    transform_test_report: dict
    """Comparative transform testing results per column."""

    # ===================================================================
    # PHASES 4-11 — New fields added by Plan 1 (Person A) and
    #               Plan 2 (Person B).
    # ===================================================================

    # -------------------------------------------------------------------
    # Phase 4 — Temporal Visualization (Rules 14-19)  [Person A]
    # -------------------------------------------------------------------

    time_series_plots: list[str]
    """Paths to raw time-series plot PNGs."""

    zoom_plots: list[str]
    """Paths to zoom-window plot PNGs."""

    resampling_report: dict
    """Multi-grain resampling results and plot paths."""

    seasonality_report: dict
    """Seasonality detection results (periods, p-values, plots)."""

    seasonality_detected: bool
    """True if at least one significant seasonal pattern was found."""

    decomposition_report: dict
    """STL decomposition results (conditional on seasonality_detected)."""

    # -------------------------------------------------------------------
    # Phase 5 — Dynamics & Rolling (Rules 20-22)  [Person A]
    # -------------------------------------------------------------------

    rolling_stats_report: dict
    """Rolling statistics results (windows, bands, plots)."""

    changepoints: list[dict]
    """Detected changepoint locations with metadata."""

    regime_shifts_detected: bool
    """True if significant regime shifts were found."""

    outlier_report: dict
    """Time-event outlier detection results."""

    # -------------------------------------------------------------------
    # Phase 6 — Bivariate & Multivariate (Rules 23-28)  [Person A]
    # -------------------------------------------------------------------

    panel_comparison_report: dict
    """Panel entity comparison results (boxplots, CV, tests)."""

    panel_heterogeneity: bool
    """True if statistically significant entity-level differences exist."""

    correlation_report: dict
    """Pearson + Spearman correlation matrices, redundancy flags."""

    mutual_info_report: dict
    """Mutual information scores and ranking comparison."""

    lag_report: dict
    """ACF/PACF and cross-correlation lag analysis results."""

    dimensionality_report: dict
    """PCA / UMAP dimensionality reduction results."""

    # -------------------------------------------------------------------
    # Phase 7 — Insight Discovery (Rules 29-31)  [Person B]
    # -------------------------------------------------------------------

    insights: list[dict]
    """Top-K ranked insights with type, score, description, mini-chart data."""

    meta_insights: list[dict]
    """Commonness/exception patterns across subgroups."""

    drill_down_findings: list[dict]
    """Recursive drill-down explanations for exceptions."""

    # -------------------------------------------------------------------
    # Phase 8 — Causal Analysis (Rules 32-35)  [Person B]
    # -------------------------------------------------------------------

    causal_graph: dict
    """PAG adjacency matrix + edge types from causal discovery."""

    causal_graph_plot: str
    """Path to causal graph visualization PNG."""

    causal_classifications: list[dict]
    """Per-variable causal vs non-causal classifications."""

    causal_responsibilities: list[dict]
    """Ranked (factor, responsibility_score, direction) tuples."""

    granger_report: dict
    """Pairwise Granger causality test results."""

    # -------------------------------------------------------------------
    # Phase 9 — Train/Test Split (Rules 36-39)  [Person A]
    # -------------------------------------------------------------------

    split_dates: dict
    """Chronological cutoff dates {train_end, val_end}."""

    split_sizes: dict
    """Row counts per split {train, val, test}."""

    cv_strategy: dict
    """Selected cross-validation strategy and parameters."""

    leakage_report: dict
    """Target / temporal / group leakage validation results."""

    drift_report: dict
    """KS test + PSI per feature across train/test splits."""

    # -------------------------------------------------------------------
    # Phase 10 — Model Readiness (Rules 40-43)  [Person B]
    # -------------------------------------------------------------------

    stationarity_report: dict
    """ADF + KPSS test results, differencing actions."""

    cointegration_report: dict
    """Johansen test results for non-stationary pairs."""

    baseline_features: list[str]
    """Names of generated baseline features (calendar + lags + rolling)."""

    feature_dataset_path: str
    """Path to the feature-engineered dataset."""

    feature_importance_report: dict
    """Permutation importance rankings from LightGBM screen."""

    # -------------------------------------------------------------------
    # Phase 11 — Reporting & Story (Rules 44-47)  [Person B]
    # -------------------------------------------------------------------

    decision_summary: dict
    """Structured JSON summary of all EDA decisions (Rule 44)."""

    notebook_path: str
    """Path to the generated .ipynb notebook."""

    story_path: str
    """Path to the generated story JSON / Markdown."""

    story_sections: list[dict]
    """Structured story sections for frontend rendering."""

    # -------------------------------------------------------------------
    # Versioning  [Person B]
    # -------------------------------------------------------------------

    version_count: int
    """Total number of version snapshots created."""

    current_version: int
    """Currently active version number."""

    # -------------------------------------------------------------------
    # Pipeline metadata
    # -------------------------------------------------------------------

    session_id: str
    """Unique session identifier (set by backend on upload)."""

    source_format: str
    """Original file format (csv, xlsx, json, parquet, log, etc.)."""

    original_filename: str
    """Original uploaded filename."""

    load_warnings: list[str]
    """Warnings generated during file loading."""
