"""
Import as:

import src.insights.meta_insight as smeta
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

import numpy as np
import pandas as pd
import scipy.stats as spstats
from langchain_core.messages import HumanMessage

import src.config.config as cconf
import src.tools.input_tools as tinptool

_LOG = logging.getLogger(__name__)

_MAX_DRILL_DEPTH = 3


# ---------------------------------------------------------------------------
# Meta-insight helpers
# ---------------------------------------------------------------------------


def _check_commonness(
    df: pd.DataFrame,
    insight: dict,
    dimensions: list[str],
) -> dict:
    """
    Check whether an insight pattern holds across other dimension values.

    :param df: dataset
    :param insight: single insight dict from insight_mining
    :param dimensions: all available dimension columns
    :return: commonness analysis dict
    """
    dim = insight.get("dimension", "")
    meas = insight.get("measure", "")
    insight_type = insight.get("type", "")

    if dim not in df.columns or meas not in df.columns:
        return {"common": False, "exceptions": [], "surprise": 0.0}

    grouped = df.groupby(dim)[meas]
    group_means = grouped.mean()

    if len(group_means) < 2:
        return {"common": False, "exceptions": [], "surprise": 0.0}

    overall_mean = df[meas].mean()
    overall_std = df[meas].std()
    if overall_std == 0 or np.isnan(overall_std):
        overall_std = 1.0

    # determine which values conform and which are exceptions
    deviations = {}
    for val, mean_val in group_means.items():
        z = (mean_val - overall_mean) / overall_std
        deviations[str(val)] = float(z)

    # the "common" pattern is the majority direction
    positive_count = sum(1 for z in deviations.values() if z > 0)
    negative_count = sum(1 for z in deviations.values() if z <= 0)
    majority_positive = positive_count >= negative_count

    exceptions = []
    conforming = []
    for val, z in deviations.items():
        is_conforming = (z > 0) == majority_positive
        if not is_conforming and abs(z) > 0.5:
            exceptions.append({"value": val, "z_score": z})
        else:
            conforming.append({"value": val, "z_score": z})

    # surprise = how much exceptions deviate from common pattern
    if exceptions:
        surprise = float(np.mean([abs(e["z_score"]) for e in exceptions]))
        surprise = min(surprise / 3.0, 1.0)
    else:
        surprise = 0.0

    common = len(conforming) > len(exceptions)

    return {
        "common": common,
        "conforming_count": len(conforming),
        "exception_count": len(exceptions),
        "exceptions": exceptions,
        "surprise": surprise,
        "majority_direction": "above_mean" if majority_positive else "below_mean",
    }


def _synthesize_meta_descriptions(meta_insights: list[dict]) -> list[dict]:
    """
    Use an LLM to produce 'most X show Y, EXCEPT Z' sentences.

    :param meta_insights: list of meta-insight dicts
    :return: same list with description field populated
    """
    if not meta_insights:
        return meta_insights

    summaries = []
    for i, mi in enumerate(meta_insights):
        summaries.append(
            f"{i+1}. dimension={mi['dimension']} | measure={mi['measure']} | "
            f"type={mi['type']} | conforming={mi['commonness']['conforming_count']} | "
            f"exceptions={json.dumps(mi['commonness']['exceptions'], default=str)} | "
            f"majority_direction={mi['commonness'].get('majority_direction', 'unknown')}"
        )

    prompt = (
        "You are an EDA meta-insight narrator. For each numbered meta-insight below, "
        "write one concise sentence in the pattern: 'Most [dimension values] show "
        "[pattern], EXCEPT [exception values] which [deviation].' "
        "Return ONLY a JSON array of strings, one per meta-insight, in the same order."
        "\n\n" + "\n".join(summaries)
    )

    try:
        llm = cconf.get_chat_model(model=cconf.get_agent_model())
        response = llm.invoke([HumanMessage(content=prompt)])
        descriptions = json.loads(response.content)
        if isinstance(descriptions, list) and len(descriptions) == len(meta_insights):
            for mi, desc in zip(meta_insights, descriptions):
                mi["description"] = str(desc)
            return meta_insights
    except Exception as exc:
        _LOG.warning("LLM meta-insight description generation failed: %s", exc)

    # fallback descriptions
    for mi in meta_insights:
        exc_vals = ", ".join(e["value"] for e in mi["commonness"]["exceptions"][:3])
        mi["description"] = (
            f"Most {mi['dimension']} values show a consistent {mi['type']} pattern "
            f"for {mi['measure']}, EXCEPT {exc_vals or 'none'}."
        )
    return meta_insights


# ---------------------------------------------------------------------------
# run_meta_insights
# ---------------------------------------------------------------------------


def run_meta_insights(state: dict) -> dict:
    """
    Identify commonness/exception patterns across the top insights.

    For each top insight from insight mining, checks whether the pattern
    holds across dimension values and identifies exceptions that break
    the pattern.

    :param state: pipeline composite state dict
    :return: state update with ``meta_insights`` and ``done``
    """
    # gate: skip for single series with no categorical dimensions
    dimensions = list(
        dict.fromkeys(
            state.get("categorical_feature_cols", [])
            + state.get("secondary_keys", [])
            + state.get("binary_flag_cols", [])
        )
    )
    if state.get("type") == "single" and not dimensions:
        _LOG.info("Single series with no dimensions; skipping meta-insights.")
        return {
            "meta_insights": [],
            "done": state.get("done", []) + ["meta_insights"],
        }

    insights = state.get("insights", [])
    if not insights:
        _LOG.info("No insights available; skipping meta-insights.")
        return {
            "meta_insights": [],
            "done": state.get("done", []) + ["meta_insights"],
        }

    # load dataset
    dataset_path = state.get("standardized_dataset_path") or state.get(
        "quality_dataset_path", ""
    )
    if not dataset_path:
        return {
            "meta_insights": [],
            "done": state.get("done", []) + ["meta_insights"],
        }

    df = tinptool.load_dataset(pathlib.Path(dataset_path))

    meta_insights: list[dict] = []
    for insight in insights:
        commonness = _check_commonness(df, insight, dimensions)
        if not commonness["exceptions"]:
            continue  # no exceptions = not interesting as meta-insight
        meta_insights.append(
            {
                "type": insight.get("type", ""),
                "dimension": insight.get("dimension", ""),
                "measure": insight.get("measure", ""),
                "parent_score": insight.get("score", 0.0),
                "commonness": commonness,
                "description": "",
            }
        )

    # LLM descriptions
    meta_insights = _synthesize_meta_descriptions(meta_insights)

    # trace
    trace_payload = {
        "insights_evaluated": len(insights),
        "meta_insights_found": len(meta_insights),
        "meta_insights": meta_insights,
    }
    try:
        tinptool.write_stage_trace(
            state.get("path", dataset_path), "meta_insights", trace_payload
        )
    except Exception as exc:
        _LOG.warning("Failed to write meta_insights trace: %s", exc)

    return {
        "meta_insights": meta_insights,
        "done": state.get("done", []) + ["meta_insights"],
    }


# ---------------------------------------------------------------------------
# Simplified insight mining for drill-down
# ---------------------------------------------------------------------------


def _simplified_insight_mining(
    df_subset: pd.DataFrame,
    dimensions: list[str],
    measures: list[str],
    numeric_cols: list[str],
) -> list[dict]:
    """
    Run a simplified insight scan on a filtered data subset.

    :param df_subset: filtered dataframe
    :param dimensions: dimension columns to consider
    :param measures: measure columns to consider
    :param numeric_cols: all numeric columns
    :return: list of insight dicts (top 3)
    """
    # inline import to avoid circular dependency
    from src.insights.insight_miner import _compute_insight

    results: list[dict] = []
    for dim in dimensions:
        if dim not in df_subset.columns:
            continue
        n_unique = df_subset[dim].nunique(dropna=True)
        if n_unique < 2 or n_unique > 200:
            continue
        for meas in measures:
            if meas not in df_subset.columns:
                continue
            insight = _compute_insight(df_subset, dim, meas, numeric_cols)
            if insight is not None and insight["score"] > 0.0:
                results.append(insight)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:3]


# ---------------------------------------------------------------------------
# run_drill_down
# ---------------------------------------------------------------------------


def run_drill_down(state: dict) -> dict:
    """
    Recursively drill into exception subgroups to find explaining dimensions.

    For each exception identified in meta_insights, filters the dataset to
    that subgroup and re-runs a simplified insight mining to find explaining
    dimensions, chaining up to depth 3.

    :param state: pipeline composite state dict
    :return: state update with ``drill_down_findings`` and ``done``
    """
    meta_insights = state.get("meta_insights", [])

    # gate: skip if no meta_insights with exceptions
    has_exceptions = any(
        mi.get("commonness", {}).get("exceptions")
        for mi in meta_insights
    )
    if not has_exceptions:
        _LOG.info("No meta-insights with exceptions; skipping drill-down.")
        return {
            "drill_down_findings": [],
            "done": state.get("done", []) + ["drill_down"],
        }

    # load dataset
    dataset_path = state.get("standardized_dataset_path") or state.get(
        "quality_dataset_path", ""
    )
    if not dataset_path:
        return {
            "drill_down_findings": [],
            "done": state.get("done", []) + ["drill_down"],
        }

    df = tinptool.load_dataset(pathlib.Path(dataset_path))

    dimensions = list(
        dict.fromkeys(
            state.get("categorical_feature_cols", [])
            + state.get("secondary_keys", [])
            + state.get("binary_flag_cols", [])
        )
    )
    measures = list(
        dict.fromkeys(
            state.get("numeric_continuous_cols", [])
            + state.get("numeric_count_cols", [])
        )
    )
    dimensions = [c for c in dimensions if c in df.columns]
    measures = [m for m in measures if m in df.columns]
    all_numeric_cols = list(dict.fromkeys(measures))

    findings: list[dict] = []

    for mi in meta_insights:
        exceptions = mi.get("commonness", {}).get("exceptions", [])
        dim = mi.get("dimension", "")
        meas = mi.get("measure", "")

        if not exceptions or dim not in df.columns:
            continue

        for exc in exceptions[:5]:  # cap to avoid combinatorial blowup
            exc_value = exc.get("value", "")
            # filter dataset to the exception subgroup
            df_sub = df[df[dim].astype(str) == str(exc_value)]
            if df_sub.empty or len(df_sub) < 5:
                continue

            # remaining dimensions (exclude current)
            other_dims = [d for d in dimensions if d != dim]
            if not other_dims:
                continue

            # recursive drill-down up to _MAX_DRILL_DEPTH
            chain: list[dict] = []
            current_df = df_sub
            used_dims = {dim}

            for depth in range(_MAX_DRILL_DEPTH):
                available_dims = [d for d in other_dims if d not in used_dims]
                if not available_dims or len(current_df) < 5:
                    break

                sub_insights = _simplified_insight_mining(
                    current_df, available_dims, measures, all_numeric_cols
                )
                if not sub_insights:
                    break

                best = sub_insights[0]
                chain.append(
                    {
                        "depth": depth + 1,
                        "explaining_dimension": best["dimension"],
                        "explaining_measure": best["measure"],
                        "insight_type": best["type"],
                        "score": best["score"],
                        "detail": best["detail"],
                    }
                )

                # narrow further for next depth
                used_dims.add(best["dimension"])
                best_dim = best["dimension"]
                if best_dim in current_df.columns:
                    # filter to the most interesting subgroup of the explaining dim
                    group_means = current_df.groupby(best_dim)[best["measure"]].mean()
                    if len(group_means) > 0:
                        extreme_val = group_means.idxmax()
                        current_df = current_df[current_df[best_dim] == extreme_val]

            if chain:
                findings.append(
                    {
                        "source_dimension": dim,
                        "source_measure": meas,
                        "exception_value": exc_value,
                        "drill_chain": chain,
                    }
                )

    # trace
    trace_payload = {
        "meta_insights_with_exceptions": sum(
            1
            for mi in meta_insights
            if mi.get("commonness", {}).get("exceptions")
        ),
        "findings_count": len(findings),
        "findings": findings,
    }
    try:
        tinptool.write_stage_trace(
            state.get("path", dataset_path), "drill_down", trace_payload
        )
    except Exception as exc:
        _LOG.warning("Failed to write drill_down trace: %s", exc)

    return {
        "drill_down_findings": findings,
        "done": state.get("done", []) + ["drill_down"],
    }
