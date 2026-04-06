"""
Import as:

import src.reporting.summary as rsummary
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pydantic

import src.config.config as cconf
import src.tools.input_tools as tinptool

_LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic model for structured LLM output
# ---------------------------------------------------------------------------

class DecisionSummary(pydantic.BaseModel):
    """
    Structured summary of all EDA decisions across the pipeline.
    """

    frequency_choice: str = pydantic.Field(
        description="What sampling frequency was used and why.",
    )
    missingness_strategy: str = pydantic.Field(
        description="How missing values were handled across the dataset.",
    )
    main_seasonalities: str = pydantic.Field(
        description="Detected seasonal patterns, or 'none detected'.",
    )
    anomaly_types: str = pydantic.Field(
        description="Types of anomalies found during analysis.",
    )
    stable_vs_drifting: str = pydantic.Field(
        description="Which features are stable vs drifting over time.",
    )
    problematic_entities: str = pydantic.Field(
        description="Entities or features flagged as problematic.",
    )
    causal_factors: str = pydantic.Field(
        description="Identified causal relationships (if Phase 8 ran).",
    )
    split_info: str = pydantic.Field(
        description="Train/test split dates and drift (if Phase 9 ran).",
    )
    modeling_recommendations: list[str] = pydantic.Field(
        description="List of recommended modeling approaches.",
    )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_prompt(state: dict) -> str:
    """
    Cherry-pick key state fields and build a concise LLM prompt.

    :param state: full pipeline state dict
    :return: prompt string
    """
    parts: list[str] = [
        "You are an expert time-series analyst. Given the following EDA "
        "pipeline results, produce a structured decision summary.\n",
    ]

    # Dataset basics
    series_type = state.get("type", "unknown")
    parts.append(f"Series type: {series_type}")
    parts.append(f"Expected frequency: {state.get('expected_frequency', 'not determined')}")

    # Seasonality
    if state.get("seasonality_detected") is not None:
        parts.append(f"Seasonality detected: {state.get('seasonality_detected')}")
    if state.get("seasonality_report"):
        parts.append(f"Seasonality report (summary): {json.dumps(state['seasonality_report'], default=str)[:2000]}")

    # Missingness
    if state.get("missingness_plan"):
        parts.append(f"Missingness plan: {json.dumps(state['missingness_plan'], default=str)[:2000]}")

    # Outliers
    if state.get("outlier_report"):
        parts.append(f"Outlier report: {json.dumps(state['outlier_report'], default=str)[:2000]}")

    # Correlations
    if state.get("correlation_report"):
        parts.append(f"Correlation report: {json.dumps(state['correlation_report'], default=str)[:2000]}")

    # Causal
    if state.get("causal_graph"):
        parts.append(f"Causal graph: {json.dumps(state['causal_graph'], default=str)[:2000]}")
    if state.get("granger_report"):
        parts.append(f"Granger report: {json.dumps(state['granger_report'], default=str)[:2000]}")

    # Stationarity
    if state.get("stationarity_report"):
        parts.append(f"Stationarity report: {json.dumps(state['stationarity_report'], default=str)[:2000]}")

    # Drift
    if state.get("drift_report"):
        parts.append(f"Drift report: {json.dumps(state['drift_report'], default=str)[:2000]}")

    # Top insights (limit to 5)
    insights = state.get("insights") or []
    if insights:
        top_5 = insights[:5]
        parts.append(f"Top insights: {json.dumps(top_5, default=str)[:2000]}")

    parts.append(
        "\nProduce a structured decision summary covering: frequency_choice, "
        "missingness_strategy, main_seasonalities, anomaly_types, "
        "stable_vs_drifting, problematic_entities, causal_factors, "
        "split_info, and modeling_recommendations."
    )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def run_decision_summary(state: dict) -> dict:
    """
    Generate a structured decision summary from the full pipeline state.

    :param state: CompositeState dict
    :return: dict with ``decision_summary`` and ``done``
    """
    _LOG.info("Phase 11.1 — generating decision summary")

    prompt = _build_prompt(state)

    # LLM call with structured output
    llm = cconf.get_chat_model(model=cconf.get_agent_model())
    structured_llm = llm.with_structured_output(DecisionSummary)

    try:
        result: DecisionSummary = structured_llm.invoke(prompt)
        summary_dict = result.model_dump()
    except Exception as exc:
        _LOG.warning("LLM structured output failed, using fallback: %s", exc)
        summary_dict = DecisionSummary(
            frequency_choice=state.get("expected_frequency", "unknown"),
            missingness_strategy="see missingness_plan in state",
            main_seasonalities="unknown — LLM call failed",
            anomaly_types="unknown — LLM call failed",
            stable_vs_drifting="unknown — LLM call failed",
            problematic_entities="unknown — LLM call failed",
            causal_factors="not available",
            split_info="not available",
            modeling_recommendations=["review pipeline outputs manually"],
        ).model_dump()

    # Write trace
    trace_dir = tinptool._trace_root()
    trace_path = trace_dir / "decision_summary.json"
    with open(trace_path, "w", encoding="utf-8") as fh:
        json.dump(summary_dict, fh, indent=2, default=str)
    _LOG.info("Decision summary trace written to %s", trace_path)

    done = list(state.get("done") or [])
    if "run_decision_summary" not in done:
        done.append("run_decision_summary")

    return {"decision_summary": summary_dict, "done": done}
