"""Integration tests for the master pipeline and branching gates."""
from __future__ import annotations

import pytest


def test_pipeline_compiles():
    """The master pipeline should compile without error."""
    from src.pipeline import compile_pipeline
    compiled = compile_pipeline()
    assert compiled is not None
    assert type(compiled).__name__ == "CompiledStateGraph"


def test_state_schema_importable():
    """CompositeState should be importable and have key fields."""
    from src.tools.state_schema import CompositeState
    hints = CompositeState.__annotations__
    for field in ["path", "done", "type", "insights", "causal_graph",
                  "notebook_path", "story_path", "session_id"]:
        assert field in hints, f"Missing field: {field}"


def test_all_phase_modules_import():
    """Every phase module should import without error."""
    import src.insights.insight_miner
    import src.insights.meta_insight
    import src.causal.causal_graph
    import src.causal.granger
    import src.model_readiness.stationarity
    import src.model_readiness.baseline_features
    import src.model_readiness.feature_importance
    import src.reporting.summary
    import src.reporting.notebook_generator
    import src.reporting.story_generator
    import src.temporal_analysis.plot_time_series
    import src.temporal_analysis.seasonality
    import src.dynamics.rolling_stats
    import src.dynamics.changepoints
    import src.multivariate.correlation
    import src.split.temporal_split


def test_insight_causal_gate_panel_data():
    """Panel data with categoricals should trigger Phase 7."""
    from src.pipeline import _insight_causal_gate
    state = {
        "type": "multiple",
        "numeric_continuous_cols": ["revenue"],
        "numeric_count_cols": [],
        "categorical_feature_cols": ["store_id"],
        "secondary_keys": ["store_id"],
    }
    targets = _insight_causal_gate(state)
    assert "phase_7_insights" in targets


def test_insight_causal_gate_multivariate():
    """Multivariate data with 3+ numeric cols should trigger Phase 8."""
    from src.pipeline import _insight_causal_gate
    state = {
        "type": "multivariate",
        "numeric_continuous_cols": ["temp", "pressure", "humidity"],
        "numeric_count_cols": ["events"],
        "categorical_feature_cols": [],
        "secondary_keys": [],
    }
    targets = _insight_causal_gate(state)
    assert "phase_8_causal" in targets


def test_insight_causal_gate_skip():
    """Single series with no dimensions should skip to fan-in."""
    from src.pipeline import _insight_causal_gate
    state = {
        "type": "single",
        "numeric_continuous_cols": ["value"],
        "numeric_count_cols": [],
        "categorical_feature_cols": [],
        "secondary_keys": [],
    }
    targets = _insight_causal_gate(state)
    assert targets == ["phase_78_skip"]


def test_modeling_gate_with_targets():
    """Should route to Phase 10 when target columns exist."""
    from src.pipeline import _modeling_gate
    assert _modeling_gate({"target_cols": ["revenue"]}) == "phase_10_stationarity"


def test_modeling_gate_without_targets():
    """Should skip Phase 10 when no target columns."""
    from src.pipeline import _modeling_gate
    assert _modeling_gate({"target_cols": []}) == "skip_modeling"
    assert _modeling_gate({}) == "skip_modeling"


def test_phase6_gate_panel():
    from src.pipeline import _phase6_gate
    state = {"type": "multiple", "numeric_continuous_cols": ["a", "b"]}
    assert _phase6_gate(state) == "phase_6_panel"


def test_phase6_gate_multivariate():
    from src.pipeline import _phase6_gate
    state = {"type": "multivariate", "numeric_continuous_cols": ["a", "b"]}
    assert _phase6_gate(state) == "phase_6_multivariate"


def test_phase6_gate_single():
    from src.pipeline import _phase6_gate
    state = {"type": "single", "numeric_continuous_cols": ["a"]}
    assert _phase6_gate(state) == "phase_6_skip"
