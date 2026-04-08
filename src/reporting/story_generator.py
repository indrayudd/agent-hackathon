"""
Import as:

import src.reporting.story_generator as rstory
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

import pydantic

import src.config.config as cconf
import src.tools.input_tools as tinptool
from src.reporting.plot_contract import normalize_plot_artifacts

_LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models for structured LLM output
# ---------------------------------------------------------------------------

class StorySection(pydantic.BaseModel):
    """
    One section of the narrative story.
    """

    title: str = pydantic.Field(
        description="Section title.",
    )
    prose: str = pydantic.Field(
        description="Narrative paragraph(s) for this section.",
    )
    plots: list[str] = pydantic.Field(
        default_factory=list,
        description="Paths to the most informative plot PNGs for this section.",
    )
    insight_cards: list[dict] = pydantic.Field(
        default_factory=list,
        description="Insight cards: {type, description, confidence, rule_ref}.",
    )


class Story(pydantic.BaseModel):
    """
    Full narrative story output.
    """

    executive_summary: str = pydantic.Field(
        description="A concise executive summary of the entire EDA.",
    )
    sections: list[StorySection] = pydantic.Field(
        description="Ordered narrative sections.",
    )
    recommendations: list[str] = pydantic.Field(
        description="Actionable recommendations for the data scientist.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_plot_paths(state: dict) -> list[str]:
    """
    Gather available plot paths from state for the LLM to reference.

    :param state: pipeline state
    :return: deduplicated list of plot paths
    """
    paths: list[str] = []

    for key in ("time_series_plots", "zoom_plots"):
        for p in (state.get(key) or []):
            paths.append(str(p))

    if state.get("causal_graph_plot"):
        paths.append(str(state["causal_graph_plot"]))

    # Extract plot paths from report dicts
    for report_key in (
        "resampling_report", "seasonality_report", "decomposition_report",
        "rolling_stats_report", "outlier_report", "correlation_report",
        "dimensionality_report", "univariate_report", "panel_comparison_report",
        "feature_importance_report",
    ):
        report = state.get(report_key) or {}
        if isinstance(report, dict):
            for v in report.values():
                if isinstance(v, str) and v.endswith(".png"):
                    paths.append(v)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str) and item.endswith(".png"):
                            paths.append(item)
                        elif isinstance(item, dict):
                            for dv in item.values():
                                if isinstance(dv, str) and dv.endswith(".png"):
                                    paths.append(dv)

    return list(dict.fromkeys(paths))  # deduplicate preserving order


def _build_story_prompt(state: dict, available_plots: list[str]) -> str:
    """
    Build a detailed prompt for narrative story generation.

    :param state: pipeline state
    :param available_plots: list of available plot paths
    :return: prompt string
    """
    parts: list[str] = [
        "You are an expert data storyteller. Given the following EDA pipeline "
        "results, produce a compelling narrative that a data scientist can "
        "present to stakeholders.\n",
    ]

    # Dataset overview
    parts.append("### Dataset Overview")
    parts.append(f"- Type: {state.get('type', 'unknown')}")
    parts.append(f"- Frequency: {state.get('expected_frequency', 'not determined')}")
    parts.append(f"- Columns: {len(state.get('cols') or [])}")
    parts.append(f"- Time range: {state.get('min_time', 'N/A')} to {state.get('max_time', 'N/A')}")
    if state.get("target_cols"):
        parts.append(f"- Targets: {', '.join(state['target_cols'])}")

    # Phase findings
    if state.get("missingness_plan"):
        parts.append(f"\n### Missingness Handling\n{json.dumps(state['missingness_plan'], default=str)[:1500]}")

    if state.get("seasonality_detected") is not None:
        parts.append(f"\n### Seasonality\n- Detected: {state['seasonality_detected']}")
        if state.get("seasonality_report"):
            parts.append(json.dumps(state["seasonality_report"], default=str)[:1000])

    if state.get("outlier_report"):
        parts.append(f"\n### Outliers\n{json.dumps(state['outlier_report'], default=str)[:1000]}")

    if state.get("correlation_report"):
        parts.append(f"\n### Correlations\n{json.dumps(state['correlation_report'], default=str)[:1000]}")

    # Top insights
    insights = state.get("insights") or []
    if insights:
        top_5 = insights[:5]
        parts.append(f"\n### Top Insights\n{json.dumps(top_5, default=str)[:1500]}")

    # Causal findings
    if state.get("causal_graph") or state.get("granger_report"):
        parts.append("\n### Causal Findings")
        if state.get("causal_graph"):
            parts.append(json.dumps(state["causal_graph"], default=str)[:1000])
        if state.get("causal_responsibilities"):
            parts.append(f"Responsibilities: {json.dumps(state['causal_responsibilities'][:5], default=str)}")

    # Model readiness
    if state.get("stationarity_report") or state.get("feature_importance_report"):
        parts.append("\n### Model Readiness")
        if state.get("stationarity_report"):
            parts.append(f"Stationarity: {json.dumps(state['stationarity_report'], default=str)[:800]}")
        if state.get("feature_importance_report"):
            parts.append(f"Feature importance: {json.dumps(state['feature_importance_report'], default=str)[:800]}")

    # Decision summary
    if state.get("decision_summary"):
        parts.append(f"\n### Decision Summary\n{json.dumps(state['decision_summary'], default=str)[:1500]}")

    # Available plots
    if available_plots:
        parts.append(f"\n### Available Plots (choose the most informative for each section)")
        parts.append("\n".join(f"- {p}" for p in available_plots[:30]))

    parts.append(
        "\nProduce a structured story with: executive_summary, "
        "sections (each with title, prose, plots from the available list, "
        "and insight_cards), and recommendations."
    )

    return "\n".join(parts)


def _story_to_markdown(story: Story) -> str:
    """
    Convert a Story model to a Markdown document.

    :param story: Story pydantic model
    :return: markdown string
    """
    lines: list[str] = [
        "# EDA Story Report\n",
        "## Executive Summary\n",
        story.executive_summary + "\n",
    ]

    for section in story.sections:
        lines.append(f"\n## {section.title}\n")
        lines.append(section.prose + "\n")

        if section.plots:
            lines.append("\n**Key Visualizations:**\n")
            for plot in section.plots:
                if isinstance(plot, dict):
                    source = str(plot.get("source") or plot.get("payload") or "")
                else:
                    source = str(plot)
                lines.append(f"![{section.title}]({source})\n")

        if section.insight_cards:
            lines.append("\n**Insights:**\n")
            for card in section.insight_cards:
                desc = card.get("description", str(card))
                itype = card.get("type", "")
                conf = card.get("confidence", "")
                label = f"[{itype}]" if itype else ""
                conf_str = f" (confidence: {conf})" if conf else ""
                lines.append(f"- {label} {desc}{conf_str}\n")

    if story.recommendations:
        lines.append("\n## Recommendations\n")
        for rec in story.recommendations:
            lines.append(f"- {rec}\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def run_story_generation(state: dict) -> dict:
    """
    Generate a narrative story from the full pipeline state.

    :param state: CompositeState dict
    :return: dict with ``story_path``, ``story_sections``, and ``done``
    """
    _LOG.info("Phase 11.3 — generating EDA story")

    available_plots = _collect_plot_paths(state)
    prompt = _build_story_prompt(state, available_plots)

    # LLM call with structured output
    llm = cconf.get_chat_model(model=cconf.get_agent_model())
    structured_llm = llm.with_structured_output(Story)

    try:
        story: Story = structured_llm.invoke(prompt)
    except Exception as exc:
        _LOG.warning("LLM story generation failed, using fallback: %s", exc)
        story = Story(
            executive_summary=(
                "Automated EDA pipeline completed. Please review the "
                "individual phase reports and trace files for detailed findings."
            ),
            sections=[
                StorySection(
                    title="Pipeline Overview",
                    prose=(
                        f"The dataset ({state.get('original_filename', 'unknown')}) "
                        f"was processed through the EDA pipeline. "
                        f"Series type: {state.get('type', 'unknown')}. "
                        f"Frequency: {state.get('expected_frequency', 'unknown')}."
                    ),
                    plots=available_plots[:3],
                    insight_cards=[],
                ),
            ],
            recommendations=["Review individual phase trace files for detailed results."],
        )

    # Write outputs
    trace_dir = tinptool._trace_root()
    story_dict = story.model_dump()
    for section in story_dict.get("sections", []):
        section["plots"] = normalize_plot_artifacts(
            section.get("plots") or [],
            title=section.get("title", ""),
            caption=section.get("subtitle", ""),
        )

    # JSON output
    json_path = trace_dir / "story.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(story_dict, fh, indent=2, default=str)

    # Markdown output
    md_path = trace_dir / "story.md"
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(_story_to_markdown(story))

    _LOG.info("Story written to %s and %s", json_path, md_path)

    # Build section dicts for state
    section_dicts = [s.model_dump() for s in story.sections]

    done = list(state.get("done") or [])
    if "run_story_generation" not in done:
        done.append("run_story_generation")

    return {
        "story_path": str(json_path),
        "story_sections": section_dicts,
        "done": done,
    }
