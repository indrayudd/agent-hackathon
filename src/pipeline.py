"""
Master LangGraph pipeline wiring all EDA phases.

Phases 1-3 are sequential (always run).
Phases 4-5 are sequential (always run for time-series).
Phase 6 branches conditionally on data structure.
Phases 7-8 branch conditionally based on data profile.
Phase 9 always runs.
Phase 10 is conditional on modeling intent.
Phase 11 always runs last.

Import as:

    import src.pipeline as spipe
"""

from __future__ import annotations

import logging
from typing import Any

import langgraph.graph as lgraph

from src.tools.state_schema import CompositeState

# -- Phase 1-3 (existing stages, path-based) --------------------------------
import src.ingest.handle_inputs as shainp
import src.ingest.format_datetime as sfordat
import src.ingest.infer_type as sinfert
import src.ingest.infer_structure as sinferstruct
import src.ingest.compute_temporal_stats as sctstats
import src.ingest.integrity as sinteg
import src.quality_handling.audit_missingness as sauditmiss
import src.quality_handling.handle_missingness as shandlemiss
import src.quality_handling.standardize as sstandard
import src.univariate_analysis.univariate_metrics_plotting as sunivar
import src.univariate_analysis.test_transforms as stransforms

# -- Phase 4: Temporal Visualization (Person A) ------------------------------
import src.temporal_analysis.plot_time_series as splotts
import src.temporal_analysis.resample_analysis as sresample
import src.temporal_analysis.seasonality as sseason
import src.temporal_analysis.event_overlay as sevent

# -- Phase 5: Dynamics & Rolling (Person A) ----------------------------------
import src.dynamics.rolling_stats as srolling
import src.dynamics.changepoints as schangept
import src.dynamics.outlier_detection as soutlier

# -- Phase 6: Multivariate (Person A) ---------------------------------------
import src.multivariate.panel_compare as spanelcmp
import src.multivariate.correlation as scorr
import src.multivariate.lag_analysis as slaganalysis
import src.multivariate.dimensionality as sdim

# -- Phase 7: Insight Discovery (Person B) -----------------------------------
import src.insights.insight_miner as sinsight
import src.insights.meta_insight as smeta

# -- Phase 8: Causal Analysis (Person B) ------------------------------------
import src.causal.causal_graph as scausal
import src.causal.granger as sgranger

# -- Phase 9: Train/Test Split (Person A) -----------------------------------
import src.split.temporal_split as ssplit
import src.split.leakage_check as sleakage
import src.split.distribution_drift as sdrift

# -- Phase 10: Model Readiness (Person B) -----------------------------------
import src.model_readiness.stationarity as sstation
import src.model_readiness.baseline_features as sbasefeat
import src.model_readiness.feature_importance as sfeatimpt

# -- Phase 11: Reporting (Person B) -----------------------------------------
import src.reporting.summary as ssummary
import src.reporting.notebook_generator as snotebook
import src.reporting.story_generator as sstory

_LOG = logging.getLogger(__name__)


# ============================================================================
# Helpers — extract common args from state for Person A's functions
# ============================================================================

def _common_args(state: dict) -> dict[str, Any]:
    """Extract the (path, time_col, winner_formatter) triple from state."""
    return {
        "path": state["path"],
        "time_col": state.get("time_col", ""),
        "winner_formatter": state.get("winner_formatter", {}),
    }


# ============================================================================
# Merge helper — LangGraph StateGraph(dict) replaces state wholesale,
# so every node must return the FULL state with updates merged in.
# ============================================================================

def _merge(state: dict, updates: dict, stage_name: str) -> dict:
    """Merge stage updates into the running state."""
    out = dict(state)
    out.update(updates)
    out["done"] = list(state.get("done", [])) + [stage_name]
    return out


# ============================================================================
# Phase 1-3 node wrappers (path-based stages)
# ============================================================================

def _node_input_handler(state: dict) -> dict:
    result = shainp.run_input_handler(state["path"])
    return _merge(state, result, "input")


def _node_date_formatter(state: dict) -> dict:
    result = sfordat.run_date_formatter(state["path"])
    return _merge(state, result, "format")


def _node_infer_type(state: dict) -> dict:
    result = sinfert.run_infer_type(state["path"])
    return _merge(state, result, "infer_type")


def _node_infer_structure(state: dict) -> dict:
    result = sinferstruct.run_infer_structure(state["path"])
    return _merge(state, result, "infer_structure")


def _node_temporal_stats(state: dict) -> dict:
    result = sctstats.run_compute_temporal_stats(state["path"])
    return _merge(state, result, "compute_temporal_stats")


def _node_integrity(state: dict) -> dict:
    result = sinteg.run_integrity(state["path"])
    return _merge(state, result, "integrity")


def _node_audit_missingness(state: dict) -> dict:
    result = sauditmiss.run_audit_missingness(state["path"])
    return _merge(state, result, "audit_missingness")


def _node_handle_missingness(state: dict) -> dict:
    result = shandlemiss.run_handle_missingness(state["path"])
    return _merge(state, result, "handle_missingness")


def _node_standardize(state: dict) -> dict:
    result = sstandard.run_standardize(state["path"])
    return _merge(state, result, "standardize")


def _node_univariate(state: dict) -> dict:
    result = sunivar.run_univariate_metrics_plotting(state["path"])
    return _merge(state, result, "univariate_metrics_plotting")


def _node_transforms(state: dict) -> dict:
    result = stransforms.run_test_transforms(state["path"])
    return _merge(state, result, "test_transforms")


# ============================================================================
# Phase 4: Temporal Visualization (Person A)
# ============================================================================

def _node_plot_time_series(state: dict) -> dict:
    ca = _common_args(state)
    plots = splotts.plot_raw_time_series.invoke({
        **ca,
        "target_cols": state.get("target_cols", []),
        "numeric_continuous_cols": state.get("numeric_continuous_cols", []),
        "secondary_keys": state.get("secondary_keys", []),
        "type": state.get("type", "single"),
    })
    return _merge(state, {
        "time_series_plots": plots if isinstance(plots, list) else [str(plots)],
    }, "plot_time_series")


def _node_zoom_windows(state: dict) -> dict:
    ca = _common_args(state)
    plots = splotts.plot_zoom_windows.invoke({
        **ca,
        "target_cols": state.get("target_cols", []),
        "numeric_continuous_cols": state.get("numeric_continuous_cols", []),
    })
    return _merge(state, {
        "zoom_plots": plots if isinstance(plots, list) else [str(plots)],
    }, "zoom_windows")


def _node_resample(state: dict) -> dict:
    ca = _common_args(state)
    result = sresample.resample_and_plot.invoke({
        **ca,
        "target_cols": state.get("target_cols", []),
        "numeric_continuous_cols": state.get("numeric_continuous_cols", []),
        "expected_frequency": state.get("expected_frequency"),
    })
    return _merge(state, {"resampling_report": result}, "resample")


def _node_seasonality(state: dict) -> dict:
    ca = _common_args(state)
    result = sseason.detect_seasonality.invoke({
        **ca,
        "target_cols": state.get("target_cols", []),
        "numeric_continuous_cols": state.get("numeric_continuous_cols", []),
    })
    detected = bool(result.get("detected_periods"))
    return _merge(state, {
        "seasonality_report": result,
        "seasonality_detected": detected,
    }, "seasonality")


def _node_decomposition(state: dict) -> dict:
    if not state.get("seasonality_detected", False):
        return dict(state)
    ca = _common_args(state)
    result = sseason.decompose_series.invoke({
        **ca,
        "target_cols": state.get("target_cols", []),
        "expected_frequency": state.get("expected_frequency"),
    })
    return _merge(state, {"decomposition_report": result}, "decomposition")


# ============================================================================
# Phase 5: Dynamics & Rolling (Person A)
# ============================================================================

def _node_rolling_stats(state: dict) -> dict:
    ca = _common_args(state)
    result = srolling.compute_rolling_stats.invoke({
        **ca,
        "target_cols": state.get("target_cols", []),
        "numeric_continuous_cols": state.get("numeric_continuous_cols", []),
        "expected_frequency": state.get("expected_frequency"),
    })
    return _merge(state, {"rolling_stats_report": result}, "rolling_stats")


def _node_changepoints(state: dict) -> dict:
    ca = _common_args(state)
    result = schangept.detect_changepoints.invoke({
        **ca,
        "target_cols": state.get("target_cols", []),
        "numeric_continuous_cols": state.get("numeric_continuous_cols", []),
    })
    changepoints_list = result.get("changepoints", [])
    return _merge(state, {
        "changepoints": changepoints_list,
        "regime_shifts_detected": len(changepoints_list) > 0,
    }, "changepoints")


def _node_outlier_detection(state: dict) -> dict:
    ca = _common_args(state)
    result = soutlier.detect_time_outliers.invoke({
        **ca,
        "target_cols": state.get("target_cols", []),
        "numeric_continuous_cols": state.get("numeric_continuous_cols", []),
    })
    return _merge(state, {"outlier_report": result}, "outlier_detection")


# ============================================================================
# Phase 6: Multivariate (Person A) — conditional branching
# ============================================================================

def _node_panel_compare(state: dict) -> dict:
    ca = _common_args(state)
    target_cols = state.get("target_cols", [])
    entity_col = state.get("entity_col")
    if not entity_col or not target_cols:
        return dict(state)
    result = spanelcmp.compare_panel_entities.invoke({
        **ca,
        "target_cols": target_cols,
        "numeric_continuous_cols": state.get("numeric_continuous_cols", []),
        "secondary_keys": state.get("secondary_keys", []),
    })
    return _merge(state, {
        "panel_comparison_report": result,
        "panel_heterogeneity": result.get("heterogeneity_significant", False),
    }, "panel_compare")


def _node_correlation(state: dict) -> dict:
    ca = _common_args(state)
    numeric_cols = state.get("numeric_continuous_cols", [])
    if len(numeric_cols) < 2:
        return dict(state)
    result = scorr.compute_correlations.invoke({
        **ca,
        "numeric_continuous_cols": numeric_cols,
    })
    return _merge(state, {"correlation_report": result}, "correlation")


def _node_lag_analysis(state: dict) -> dict:
    ca = _common_args(state)
    target_cols = state.get("target_cols", [])
    numeric_cols = state.get("numeric_continuous_cols", [])
    result = slaganalysis.compute_lag_relationships.invoke({
        **ca,
        "target_cols": target_cols,
        "numeric_continuous_cols": numeric_cols,
        "expected_frequency": state.get("expected_frequency"),
    })
    return _merge(state, {"lag_report": result}, "lag_analysis")


def _node_dimensionality(state: dict) -> dict:
    numeric_cols = state.get("numeric_continuous_cols", [])
    if len(numeric_cols) <= 15:
        return dict(state)
    ca = _common_args(state)
    result = sdim.run_dimensionality_scan.invoke({
        **ca,
        "numeric_continuous_cols": numeric_cols,
    })
    return _merge(state, {"dimensionality_report": result}, "dimensionality")


def _phase6_gate(state: dict) -> str:
    """Route to the right Phase 6 sub-path based on data structure."""
    series_type = state.get("type", "single")
    if series_type == "multiple":
        return "phase_6_panel"
    numeric_cols = state.get("numeric_continuous_cols", [])
    if len(numeric_cols) >= 2:
        return "phase_6_multivariate"
    return "phase_6_skip"


# ============================================================================
# Phase 7-8 nodes (Person B — already take state dict)
# ============================================================================

def _node_insight_mining(state: dict) -> dict:
    result = sinsight.run_insight_mining(state)
    out = dict(state)
    out.update(result)
    return out


def _node_meta_insights(state: dict) -> dict:
    result = smeta.run_meta_insights(state)
    out = dict(state)
    out.update(result)
    return out


def _node_drill_down(state: dict) -> dict:
    result = smeta.run_drill_down(state)
    out = dict(state)
    out.update(result)
    return out


def _node_causal_graph(state: dict) -> dict:
    result = scausal.run_causal_graph(state)
    out = dict(state)
    out.update(result)
    return out


def _node_causal_classification(state: dict) -> dict:
    result = scausal.run_causal_classification(state)
    out = dict(state)
    out.update(result)
    return out


def _node_responsibility(state: dict) -> dict:
    result = scausal.run_responsibility_scoring(state)
    out = dict(state)
    out.update(result)
    return out


def _node_granger(state: dict) -> dict:
    result = sgranger.run_granger_causality(state)
    out = dict(state)
    out.update(result)
    return out


# ============================================================================
# Phase 9: Train/Test Split (Person A)
# ============================================================================

def _node_temporal_split(state: dict) -> dict:
    ca = _common_args(state)
    result = ssplit.apply_temporal_split.invoke({
        **ca,
        "secondary_keys": state.get("secondary_keys", []),
    })
    return _merge(state, {
        "split_dates": result.get("split_dates", {}),
        "split_sizes": result.get("split_sizes", {}),
    }, "temporal_split")


def _node_leakage_check(state: dict) -> dict:
    ca = _common_args(state)
    target_cols = state.get("target_cols", [])
    numeric_cols = state.get("numeric_continuous_cols", [])
    if not target_cols:
        return dict(state)
    result = sleakage.validate_no_leakage.invoke({
        **ca,
        "target_cols": target_cols,
        "numeric_continuous_cols": numeric_cols,
    })
    return _merge(state, {"leakage_report": result}, "leakage_check")


def _node_drift_check(state: dict) -> dict:
    ca = _common_args(state)
    numeric_cols = state.get("numeric_continuous_cols", [])
    result = sdrift.compare_split_distributions.invoke({
        **ca,
        "numeric_continuous_cols": numeric_cols,
    })
    return _merge(state, {"drift_report": result}, "drift_check")


# ============================================================================
# Phase 10-11 nodes (Person B — already take state dict)
# ============================================================================

def _node_stationarity(state: dict) -> dict:
    result = sstation.run_stationarity_tests(state)
    out = dict(state)
    out.update(result)
    return out


def _node_baseline_features(state: dict) -> dict:
    result = sbasefeat.run_baseline_features(state)
    out = dict(state)
    out.update(result)
    return out


def _node_feature_importance(state: dict) -> dict:
    result = sfeatimpt.run_feature_importance(state)
    out = dict(state)
    out.update(result)
    return out


def _node_decision_summary(state: dict) -> dict:
    result = ssummary.run_decision_summary(state)
    out = dict(state)
    out.update(result)
    return out


def _node_notebook_gen(state: dict) -> dict:
    result = snotebook.run_notebook_generation(state)
    out = dict(state)
    out.update(result)
    return out


def _node_story_gen(state: dict) -> dict:
    result = sstory.run_story_generation(state)
    out = dict(state)
    out.update(result)
    return out


# ============================================================================
# Branching gates
# ============================================================================

def _insight_causal_gate(state: dict) -> list[str]:
    """Decide which of Phase 7/8 to run based on data profile."""
    targets: list[str] = []
    numeric_features = state.get("numeric_continuous_cols", []) + state.get(
        "numeric_count_cols", []
    )
    categorical_dims = state.get("categorical_feature_cols", [])
    secondary_keys = state.get("secondary_keys", [])
    has_dimensions = len(categorical_dims) > 0 or len(secondary_keys) > 0

    if has_dimensions and len(numeric_features) >= 1:
        targets.append("phase_7_insights")

    if len(numeric_features) >= 3:
        targets.append("phase_8_causal")

    if not targets:
        targets.append("phase_78_skip")

    return targets


def _modeling_gate(state: dict) -> str:
    """Decide whether to run Phase 10 (model readiness)."""
    target_cols = state.get("target_cols", [])
    if not target_cols:
        return "skip_modeling"
    return "phase_10_stationarity"


# ============================================================================
# No-op nodes
# ============================================================================

def _fan_in(state: dict) -> dict:
    return dict(state)


def _skip(state: dict) -> dict:
    return dict(state)


# ============================================================================
# Build the master pipeline graph
# ============================================================================

def build_pipeline() -> lgraph.StateGraph:
    """
    Construct the master EDA pipeline as a LangGraph StateGraph.

    :return: StateGraph (call .compile() to get runnable)
    """
    graph = lgraph.StateGraph(CompositeState)

    # -- Phase 1-3: Ingest + Quality + Univariate (sequential) ---------------
    graph.add_node("phase_1_input", _node_input_handler)
    graph.add_node("phase_1_format", _node_date_formatter)
    graph.add_node("phase_1_infer_type", _node_infer_type)
    graph.add_node("phase_1_infer_structure", _node_infer_structure)
    graph.add_node("phase_1_temporal_stats", _node_temporal_stats)
    graph.add_node("phase_1_integrity", _node_integrity)
    graph.add_node("phase_2_audit_miss", _node_audit_missingness)
    graph.add_node("phase_2_handle_miss", _node_handle_missingness)
    graph.add_node("phase_2_standardize", _node_standardize)
    graph.add_node("phase_3_univariate", _node_univariate)
    graph.add_node("phase_3_transforms", _node_transforms)

    graph.add_edge(lgraph.START, "phase_1_input")
    graph.add_edge("phase_1_input", "phase_1_format")
    graph.add_edge("phase_1_format", "phase_1_infer_type")
    graph.add_edge("phase_1_infer_type", "phase_1_infer_structure")
    graph.add_edge("phase_1_infer_structure", "phase_1_temporal_stats")
    graph.add_edge("phase_1_temporal_stats", "phase_1_integrity")
    graph.add_edge("phase_1_integrity", "phase_2_audit_miss")
    graph.add_edge("phase_2_audit_miss", "phase_2_handle_miss")
    graph.add_edge("phase_2_handle_miss", "phase_2_standardize")
    graph.add_edge("phase_2_standardize", "phase_3_univariate")
    graph.add_edge("phase_3_univariate", "phase_3_transforms")

    # -- Phase 4: Temporal Visualization (sequential) -------------------------
    graph.add_node("phase_4_plot_ts", _node_plot_time_series)
    graph.add_node("phase_4_zoom", _node_zoom_windows)
    graph.add_node("phase_4_resample", _node_resample)
    graph.add_node("phase_4_seasonality", _node_seasonality)
    graph.add_node("phase_4_decompose", _node_decomposition)

    graph.add_edge("phase_3_transforms", "phase_4_plot_ts")
    graph.add_edge("phase_4_plot_ts", "phase_4_zoom")
    graph.add_edge("phase_4_zoom", "phase_4_resample")
    graph.add_edge("phase_4_resample", "phase_4_seasonality")
    graph.add_edge("phase_4_seasonality", "phase_4_decompose")

    # -- Phase 5: Dynamics (sequential) ---------------------------------------
    graph.add_node("phase_5_rolling", _node_rolling_stats)
    graph.add_node("phase_5_changepoints", _node_changepoints)
    graph.add_node("phase_5_outliers", _node_outlier_detection)

    graph.add_edge("phase_4_decompose", "phase_5_rolling")
    graph.add_edge("phase_5_rolling", "phase_5_changepoints")
    graph.add_edge("phase_5_changepoints", "phase_5_outliers")

    # -- Phase 6: Multivariate (conditional on data structure) ----------------
    graph.add_node("phase_6_panel", _node_panel_compare)
    graph.add_node("phase_6_multivariate", _node_correlation)
    graph.add_node("phase_6_lag", _node_lag_analysis)
    graph.add_node("phase_6_dim", _node_dimensionality)
    graph.add_node("phase_6_skip", _skip)

    graph.add_conditional_edges(
        "phase_5_outliers",
        _phase6_gate,
        {
            "phase_6_panel": "phase_6_panel",
            "phase_6_multivariate": "phase_6_multivariate",
            "phase_6_skip": "phase_6_skip",
        },
    )
    # Panel path: panel compare -> correlation -> lag
    graph.add_edge("phase_6_panel", "phase_6_multivariate")
    graph.add_edge("phase_6_multivariate", "phase_6_lag")
    graph.add_edge("phase_6_lag", "phase_6_dim")

    # Fan-in from Phase 6 paths
    graph.add_node("phase_6_fan_in", _fan_in)
    graph.add_edge("phase_6_dim", "phase_6_fan_in")
    graph.add_edge("phase_6_skip", "phase_6_fan_in")

    # -- Phases 7-8: Insight + Causal (conditional, can run in parallel) ------
    graph.add_node("insight_causal_gate", _skip)
    graph.add_edge("phase_6_fan_in", "insight_causal_gate")

    graph.add_node("phase_7_insights", _node_insight_mining)
    graph.add_node("phase_7_meta", _node_meta_insights)
    graph.add_node("phase_7_drill", _node_drill_down)
    graph.add_edge("phase_7_insights", "phase_7_meta")
    graph.add_edge("phase_7_meta", "phase_7_drill")

    graph.add_node("phase_8_causal", _node_causal_graph)
    graph.add_node("phase_8_classify", _node_causal_classification)
    graph.add_node("phase_8_responsibility", _node_responsibility)
    graph.add_node("phase_8_granger", _node_granger)
    graph.add_edge("phase_8_causal", "phase_8_classify")
    graph.add_edge("phase_8_classify", "phase_8_responsibility")
    graph.add_edge("phase_8_responsibility", "phase_8_granger")

    graph.add_node("phase_78_skip", _skip)

    graph.add_conditional_edges(
        "insight_causal_gate",
        _insight_causal_gate,
        {
            "phase_7_insights": "phase_7_insights",
            "phase_8_causal": "phase_8_causal",
            "phase_78_skip": "phase_78_fan_in",
        },
    )

    graph.add_node("phase_78_fan_in", _fan_in)
    graph.add_edge("phase_7_drill", "phase_78_fan_in")
    graph.add_edge("phase_8_granger", "phase_78_fan_in")
    graph.add_edge("phase_78_skip", "phase_78_fan_in")

    # -- Phase 9: Train/Test Split --------------------------------------------
    graph.add_node("phase_9_split", _node_temporal_split)
    graph.add_node("phase_9_leakage", _node_leakage_check)
    graph.add_node("phase_9_drift", _node_drift_check)

    graph.add_edge("phase_78_fan_in", "phase_9_split")
    graph.add_edge("phase_9_split", "phase_9_leakage")
    graph.add_edge("phase_9_leakage", "phase_9_drift")

    # -- Modeling gate --------------------------------------------------------
    graph.add_conditional_edges(
        "phase_9_drift",
        _modeling_gate,
        {
            "phase_10_stationarity": "phase_10_stationarity",
            "skip_modeling": "phase_11_summary",
        },
    )

    # -- Phase 10: Model Readiness --------------------------------------------
    graph.add_node("phase_10_stationarity", _node_stationarity)
    graph.add_node("phase_10_features", _node_baseline_features)
    graph.add_node("phase_10_importance", _node_feature_importance)
    graph.add_edge("phase_10_stationarity", "phase_10_features")
    graph.add_edge("phase_10_features", "phase_10_importance")
    graph.add_edge("phase_10_importance", "phase_11_summary")

    # -- Phase 11: Reporting --------------------------------------------------
    graph.add_node("phase_11_summary", _node_decision_summary)
    graph.add_node("phase_11_notebook", _node_notebook_gen)
    graph.add_node("phase_11_story", _node_story_gen)
    graph.add_edge("phase_11_summary", "phase_11_notebook")
    graph.add_edge("phase_11_notebook", "phase_11_story")
    graph.add_edge("phase_11_story", lgraph.END)

    return graph


def compile_pipeline():
    """
    Build and compile the master pipeline.

    :return: compiled runnable graph
    """
    graph = build_pipeline()
    return graph.compile()


def run_pipeline(path: str, *, session_id: str = "default") -> dict:
    """
    Execute the full EDA pipeline on a dataset.

    :param path: path to the dataset file
    :param session_id: unique session identifier
    :return: final composite state
    """
    compiled = compile_pipeline()
    init_state = {
        "path": path,
        "session_id": session_id,
        "done": [],
    }
    _LOG.info("Starting pipeline for %s (session=%s)", path, session_id)
    result = compiled.invoke(init_state)
    _LOG.info("Pipeline complete. Phases run: %s", result.get("done", []))
    return result
