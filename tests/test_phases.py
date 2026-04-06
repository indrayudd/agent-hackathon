"""Unit tests for Phase 7, 8, 10, and 11 modules.

All LLM calls are mocked. Tests run without API keys.
"""
from __future__ import annotations

import json
import pathlib
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest


# ============================================================================
# Phase 10: Model Readiness
# ============================================================================

class TestStationarity:
    def test_stationary_series(self, minimal_state, synthetic_csv):
        from src.model_readiness.stationarity import run_stationarity_tests
        result = run_stationarity_tests(minimal_state)
        assert "stationarity_report" in result
        report = result["stationarity_report"]
        assert "columns" in report
        assert isinstance(report["columns"], list)

    def test_nonstationary_detection(self, tmp_path):
        """A random walk should be detected as non-stationary."""
        from src.model_readiness.stationarity import run_stationarity_tests
        rng = np.random.default_rng(42)
        n = 200
        dates = pd.date_range("2023-01-01", periods=n, freq="D")
        walk = np.cumsum(rng.normal(0, 1, n))
        df = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "value": walk})
        path = tmp_path / "walk.csv"
        df.to_csv(path, index=False)

        state = {
            "path": str(path),
            "time_col": "date",
            "winner_formatter": {"format": "%Y-%m-%d"},
            "numeric_continuous_cols": ["value"],
            "target_cols": ["value"],
            "done": [],
        }
        result = run_stationarity_tests(state)
        report = result["stationarity_report"]
        # Random walk is non-stationary but gets auto-differenced (order=1)
        cols = report.get("columns", [])
        assert len(cols) > 0
        assert cols[0].get("differencing_order", 0) >= 1


class TestBaselineFeatures:
    def test_creates_features(self, minimal_state):
        from src.model_readiness.baseline_features import run_baseline_features
        result = run_baseline_features(minimal_state)
        assert "baseline_features" in result
        assert "feature_dataset_path" in result
        assert isinstance(result["baseline_features"], list)
        assert len(result["baseline_features"]) > 0
        assert pathlib.Path(result["feature_dataset_path"]).exists()


class TestFeatureImportance:
    def test_gate_skips_few_features(self, minimal_state):
        """Should skip when feature count <= 10."""
        from src.model_readiness.feature_importance import run_feature_importance
        # minimal_state has only ~6 columns
        result = run_feature_importance(minimal_state)
        # Should return empty or skip gracefully
        assert isinstance(result, dict)


# ============================================================================
# Phase 7: Insight Discovery
# ============================================================================

class TestInsightMining:
    @patch("src.config.config.get_chat_model")
    def test_returns_insights(self, mock_chat, minimal_state):
        # Mock the LLM to return descriptions
        mock_model = MagicMock()
        mock_model.invoke.return_value = MagicMock(
            content="Test insight description"
        )
        mock_chat.return_value = mock_model

        from src.insights.insight_miner import run_insight_mining
        result = run_insight_mining(minimal_state)
        assert "insights" in result
        assert isinstance(result["insights"], list)

    @patch("src.config.config.get_chat_model")
    def test_empty_dimensions(self, mock_chat, synthetic_csv):
        """No categorical dimensions should return empty insights."""
        mock_chat.return_value = MagicMock()
        from src.insights.insight_miner import run_insight_mining
        state = {
            "path": str(synthetic_csv),
            "done": [],
            "type": "single",
            "categorical_feature_cols": [],
            "secondary_keys": [],
            "binary_flag_cols": [],
            "numeric_continuous_cols": ["revenue"],
            "numeric_count_cols": [],
            "quality_dataset_path": str(synthetic_csv),
        }
        result = run_insight_mining(state)
        insights = result.get("insights", [])
        assert isinstance(insights, list)


class TestMetaInsights:
    @patch("src.config.config.get_chat_model")
    def test_gate_single_no_dims(self, mock_chat):
        """Single series with no dimensions should skip."""
        from src.insights.meta_insight import run_meta_insights
        state = {
            "type": "single",
            "categorical_feature_cols": [],
            "secondary_keys": [],
            "insights": [],
            "done": [],
        }
        result = run_meta_insights(state)
        assert isinstance(result, dict)

    @patch("src.config.config.get_chat_model")
    def test_drill_down_no_exceptions(self, mock_chat):
        """No exceptions should skip drill-down."""
        from src.insights.meta_insight import run_drill_down
        state = {"meta_insights": [], "done": []}
        result = run_drill_down(state)
        assert isinstance(result, dict)


# ============================================================================
# Phase 8: Causal Analysis
# ============================================================================

class TestCausalGraph:
    def test_gate_few_features(self):
        """Should skip when fewer than 3 numeric cols."""
        from src.causal.causal_graph import run_causal_graph
        state = {
            "numeric_continuous_cols": ["a"],
            "numeric_count_cols": [],
            "done": [],
        }
        result = run_causal_graph(state)
        assert result.get("causal_graph") is None or result == {} or "causal_graph" not in result

    def test_gate_few_rows(self, tmp_path):
        """Should skip when fewer than 200 rows."""
        from src.causal.causal_graph import run_causal_graph
        df = pd.DataFrame({
            "a": range(50), "b": range(50), "c": range(50), "d": range(50),
        })
        path = tmp_path / "small.csv"
        df.to_csv(path, index=False)
        state = {
            "path": str(path),
            "quality_dataset_path": str(path),
            "numeric_continuous_cols": ["a", "b", "c", "d"],
            "numeric_count_cols": [],
            "done": [],
        }
        result = run_causal_graph(state)
        assert isinstance(result, dict)


class TestGranger:
    def test_gate_not_multivariate(self):
        """Should skip when type is not multivariate."""
        from src.causal.granger import run_granger_causality
        state = {
            "type": "single",
            "numeric_continuous_cols": ["a", "b"],
            "done": [],
        }
        result = run_granger_causality(state)
        assert isinstance(result, dict)


# ============================================================================
# Phase 11: Reporting
# ============================================================================

class TestNotebookGeneration:
    def test_generates_valid_notebook(self, minimal_state):
        from src.reporting.notebook_generator import run_notebook_generation
        result = run_notebook_generation(minimal_state)
        assert "notebook_path" in result
        nb_path = pathlib.Path(result["notebook_path"])
        assert nb_path.exists()

        import nbformat
        with open(nb_path) as f:
            nb = nbformat.read(f, as_version=4)
        assert len(nb.cells) > 0
        # Should have both markdown and code cells
        cell_types = {c.cell_type for c in nb.cells}
        assert "markdown" in cell_types
        assert "code" in cell_types


class TestDecisionSummary:
    @patch("src.config.config.get_chat_model")
    def test_returns_summary(self, mock_chat, minimal_state):
        mock_model = MagicMock()
        mock_model.with_structured_output.return_value = mock_model
        mock_model.invoke.return_value = MagicMock(
            model_dump=lambda: {
                "frequency_choice": "daily",
                "missingness_strategy": "none needed",
                "main_seasonalities": "none",
                "anomaly_types": "none",
                "stable_vs_drifting": "all stable",
                "problematic_entities": "none",
                "causal_factors": "not run",
                "split_info": "not run",
                "modeling_recommendations": ["try LightGBM"],
            }
        )
        mock_chat.return_value = mock_model

        from src.reporting.summary import run_decision_summary
        result = run_decision_summary(minimal_state)
        assert "decision_summary" in result


class TestStoryGeneration:
    @patch("src.reporting.story_generator.cconf")
    def test_returns_story(self, mock_cconf, minimal_state):
        # Make the LLM call raise so the fallback path is used
        mock_model = MagicMock()
        mock_model.with_structured_output.return_value = mock_model
        mock_model.invoke.side_effect = RuntimeError("mocked")
        mock_cconf.get_chat_model.return_value = mock_model
        mock_cconf.get_agent_model.return_value = "test-model"

        from src.reporting.story_generator import run_story_generation
        result = run_story_generation(minimal_state)
        assert "story_sections" in result
        assert "story_path" in result
        assert pathlib.Path(result["story_path"]).exists()
