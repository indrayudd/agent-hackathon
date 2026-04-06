"""
Import as:

import src.insights.insight_miner as sinsight
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_TOP_K = 10

_WEIGHTS = {
    "trend_strength": 0.30,
    "outlier_severity": 0.20,
    "dominance_score": 0.20,
    "unevenness": 0.15,
    "max_correlation": 0.15,
}


# ---------------------------------------------------------------------------
# Sub-score helpers
# ---------------------------------------------------------------------------


def _safe_kendalltau(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """
    Compute Kendall's tau, returning (0, 1) on degenerate input.

    :param x: first array
    :param y: second array
    :return: (tau, p_value)
    """
    if len(x) < 3 or np.std(y) == 0:
        return 0.0, 1.0
    try:
        tau, p = spstats.kendalltau(x, y)
        if np.isnan(tau):
            return 0.0, 1.0
        return float(tau), float(p)
    except Exception:
        return 0.0, 1.0


def _trend_score(group_means: pd.Series) -> dict:
    """
    Mann-Kendall proxy via Kendall tau of measure means vs integer position.

    :param group_means: measure mean per dimension value, ordered by value
    :return: trend detail dict
    """
    if len(group_means) < 3:
        return {"tau": 0.0, "p_value": 1.0, "strength": 0.0}
    positions = np.arange(len(group_means), dtype=float)
    tau, p = _safe_kendalltau(positions, group_means.values.astype(float))
    strength = abs(tau) * (1 - p)
    return {"tau": float(tau), "p_value": float(p), "strength": float(strength)}


def _modified_z_scores(values: np.ndarray) -> np.ndarray:
    """
    Compute modified Z-scores using median and MAD.

    :param values: 1-d numeric array
    :return: modified Z-scores
    """
    med = np.nanmedian(values)
    mad = np.nanmedian(np.abs(values - med))
    if mad == 0:
        return np.zeros_like(values, dtype=float)
    return 0.6745 * (values - med) / mad


def _outlier_score(group_means: pd.Series, *, top_k: int = 3) -> dict:
    """
    Identify outlier dimension values by modified Z-score.

    :param group_means: measure mean per dimension value
    :param top_k: number of top outliers to flag
    :return: outlier detail dict
    """
    if len(group_means) < 3:
        return {"severity": 0.0, "outlier_values": []}
    z = _modified_z_scores(group_means.values.astype(float))
    abs_z = np.abs(z)
    severity = float(np.max(abs_z)) if len(abs_z) > 0 else 0.0
    # normalize severity to [0, 1]
    severity_norm = min(severity / 3.5, 1.0)
    top_idx = np.argsort(abs_z)[::-1][:top_k]
    outlier_values = [
        {"value": str(group_means.index[i]), "z_score": float(z[i])}
        for i in top_idx
        if abs_z[i] > 1.5
    ]
    return {"severity": float(severity_norm), "outlier_values": outlier_values}


def _dominance_score(group_sums: pd.Series) -> dict:
    """
    Compute the share of the top-1 dimension value.

    :param group_sums: measure sum per dimension value
    :return: dominance detail dict
    """
    total = group_sums.sum()
    if total == 0 or len(group_sums) == 0:
        return {"score": 0.0, "top_value": None, "share": 0.0}
    top_value = group_sums.idxmax()
    share = float(group_sums.max() / total)
    # dominance is interesting when one value dominates disproportionately
    n = len(group_sums)
    baseline = 1.0 / n if n > 0 else 1.0
    score = max(0.0, share - baseline) / (1.0 - baseline) if baseline < 1.0 else 0.0
    return {"score": float(score), "top_value": str(top_value), "share": float(share)}


def _evenness_score(group_sums: pd.Series) -> dict:
    """
    Compute Shannon entropy across dimension values.

    :param group_sums: measure sum per dimension value
    :return: evenness detail dict
    """
    total = group_sums.sum()
    if total == 0 or len(group_sums) < 2:
        return {"entropy": 0.0, "max_entropy": 0.0, "evenness": 1.0}
    proportions = group_sums.values.astype(float) / total
    proportions = proportions[proportions > 0]
    entropy = float(spstats.entropy(proportions))
    max_entropy = float(np.log(len(group_sums)))
    evenness = entropy / max_entropy if max_entropy > 0 else 1.0
    return {
        "entropy": float(entropy),
        "max_entropy": float(max_entropy),
        "evenness": float(evenness),
    }


def _correlation_score(
    df: pd.DataFrame,
    dimension: str,
    measure: str,
    numeric_cols: list[str],
) -> dict:
    """
    Pearson correlation of measure with other numeric columns within dim slices.

    :param df: dataset
    :param dimension: dimension column
    :param measure: measure column
    :param numeric_cols: all numeric column names
    :return: correlation detail dict
    """
    other_numerics = [c for c in numeric_cols if c != measure and c != dimension]
    if not other_numerics:
        return {"max_correlation": 0.0, "best_partner": None}
    best_corr = 0.0
    best_partner = None
    for col in other_numerics[:20]:  # cap to avoid slowness
        try:
            valid = df[[measure, col]].dropna()
            if len(valid) < 5:
                continue
            r, _ = spstats.pearsonr(valid[measure].values, valid[col].values)
            if np.isnan(r):
                continue
            if abs(r) > best_corr:
                best_corr = abs(r)
                best_partner = col
        except Exception:
            continue
    return {"max_correlation": float(best_corr), "best_partner": best_partner}


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------


def _compute_insight(
    df: pd.DataFrame,
    dimension: str,
    measure: str,
    numeric_cols: list[str],
) -> dict | None:
    """
    Compute all sub-scores for one (dimension, measure) pair.

    :param df: dataset
    :param dimension: dimension column name
    :param measure: measure column name
    :param numeric_cols: all numeric column names
    :return: insight dict or None if pair is degenerate
    """
    if dimension not in df.columns or measure not in df.columns:
        return None

    col_data = df[[dimension, measure]].dropna(subset=[measure])
    if col_data.empty:
        return None

    grouped = col_data.groupby(dimension)[measure]
    group_means = grouped.mean()
    group_sums = grouped.sum()

    # skip single-value dimensions
    if len(group_means) < 2:
        return None

    trend = _trend_score(group_means)
    outlier = _outlier_score(group_means)
    dominance = _dominance_score(group_sums)
    evenness = _evenness_score(group_sums)
    correlation = _correlation_score(df, dimension, measure, numeric_cols)

    # composite interestingness
    composite = (
        _WEIGHTS["trend_strength"] * trend["strength"]
        + _WEIGHTS["outlier_severity"] * outlier["severity"]
        + _WEIGHTS["dominance_score"] * dominance["score"]
        + _WEIGHTS["unevenness"] * (1.0 - evenness["evenness"])
        + _WEIGHTS["max_correlation"] * correlation["max_correlation"]
    )

    # determine dominant insight type
    sub_scores = {
        "trend": trend["strength"],
        "outlier": outlier["severity"],
        "dominance": dominance["score"],
        "evenness": 1.0 - evenness["evenness"],
        "correlation": correlation["max_correlation"],
    }
    dominant_type = max(sub_scores, key=sub_scores.get)

    return {
        "type": dominant_type,
        "dimension": dimension,
        "measure": measure,
        "score": float(composite),
        "detail": {
            "trend": trend,
            "outlier": outlier,
            "dominance": dominance,
            "evenness": evenness,
            "correlation": correlation,
        },
        "description": "",  # filled in by LLM later
    }


# ---------------------------------------------------------------------------
# LLM description generation
# ---------------------------------------------------------------------------


def _generate_descriptions(insights: list[dict]) -> list[dict]:
    """
    Use an LLM to produce natural-language descriptions for the top insights.

    :param insights: list of insight dicts (description field empty)
    :return: same list with description fields populated
    """
    if not insights:
        return insights

    summaries = []
    for i, ins in enumerate(insights):
        summaries.append(
            f"{i+1}. type={ins['type']} | dim={ins['dimension']} | "
            f"measure={ins['measure']} | score={ins['score']:.3f} | "
            f"detail={json.dumps(ins['detail'], default=str)}"
        )
    prompt = (
        "You are an EDA insight narrator. For each numbered insight below, write "
        "one concise plain-English sentence explaining what the pattern means for "
        "a data analyst. Return ONLY a JSON array of strings, one per insight, in "
        "the same order.\n\n" + "\n".join(summaries)
    )

    try:
        llm = cconf.get_chat_model(model=cconf.get_agent_model())
        response = llm.invoke([HumanMessage(content=prompt)])
        descriptions = json.loads(response.content)
        if isinstance(descriptions, list) and len(descriptions) == len(insights):
            for ins, desc in zip(insights, descriptions):
                ins["description"] = str(desc)
            return insights
    except Exception as exc:
        _LOG.warning("LLM description generation failed: %s", exc)

    # fallback: generate template descriptions
    for ins in insights:
        ins["description"] = (
            f"A {ins['type']} pattern was detected for {ins['measure']} "
            f"across {ins['dimension']} (interestingness {ins['score']:.2f})."
        )
    return insights


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_insight_mining(state: dict) -> dict:
    """
    Discover and rank the most interesting (dimension, measure) insights.

    Reads the quality-handled (or standardized) dataset, evaluates all
    (dimension, measure) pairs across five insight types, ranks them by
    a composite interestingness score, and annotates the top-K with
    LLM-generated descriptions.

    :param state: pipeline composite state dict
    :return: state update with ``insights`` and ``done``
    """
    # ----- resolve dataset path -------------------------------------------
    dataset_path = state.get("standardized_dataset_path") or state.get(
        "quality_dataset_path", ""
    )
    if not dataset_path:
        _LOG.warning("No dataset path found in state; skipping insight mining.")
        return {
            "insights": [],
            "done": state.get("done", []) + ["insight_mining"],
        }

    df = tinptool.load_dataset(pathlib.Path(dataset_path))

    # ----- identify dimension and measure columns -------------------------
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

    # filter to columns that actually exist in the dataframe
    dimensions = [c for c in dimensions if c in df.columns]
    measures = [m for m in measures if m in df.columns]

    if not dimensions or not measures:
        _LOG.info("No valid dimension/measure pairs; returning empty insights.")
        return {
            "insights": [],
            "done": state.get("done", []) + ["insight_mining"],
        }

    all_numeric_cols = list(
        dict.fromkeys(
            state.get("numeric_continuous_cols", [])
            + state.get("numeric_count_cols", [])
        )
    )

    # ----- compute insights for every pair --------------------------------
    raw_insights: list[dict] = []
    for dim in dimensions:
        n_unique = df[dim].nunique(dropna=True)
        # skip dimensions with too many or too few unique values
        if n_unique < 2 or n_unique > 200:
            continue
        for meas in measures:
            insight = _compute_insight(df, dim, meas, all_numeric_cols)
            if insight is not None and insight["score"] > 0.0:
                raw_insights.append(insight)

    # ----- rank and select top-K ------------------------------------------
    raw_insights.sort(key=lambda x: x["score"], reverse=True)
    top_insights = raw_insights[:_DEFAULT_TOP_K]

    # ----- LLM descriptions -----------------------------------------------
    top_insights = _generate_descriptions(top_insights)

    # ----- trace -----------------------------------------------------------
    trace_payload = {
        "dimensions_considered": dimensions,
        "measures_considered": measures,
        "total_pairs_evaluated": len(raw_insights),
        "top_k": len(top_insights),
        "insights": top_insights,
    }
    try:
        tinptool.write_stage_trace(
            state.get("path", dataset_path), "insight_mining", trace_payload
        )
    except Exception as exc:
        _LOG.warning("Failed to write insight_mining trace: %s", exc)

    return {
        "insights": top_insights,
        "done": state.get("done", []) + ["insight_mining"],
    }
