"""
Import as:

import src.multivariate.panel_compare as spanel
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

import langchain.tools as ltools
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as spstats

import src.tools.input_tools as tinptool

_LOG = logging.getLogger(__name__)
_STAGE = "panel_compare"
_MAX_ENTITIES = 20
_TOP_OVERLAY = 5


def _parse_and_sort(
    path: str, time_col: str, winner_formatter: dict[str, Any],
) -> pd.DataFrame:
    """Load dataset, parse the time column, and sort by time.

    :param path: dataset file path
    :param time_col: datetime column name
    :param winner_formatter: kwargs for ``pd.to_datetime``
    :return: sorted dataframe with parsed time column
    """
    df = tinptool.load_dataset(pathlib.Path(path))
    df[time_col] = pd.to_datetime(df[time_col], **winner_formatter)
    df = df.sort_values(time_col).reset_index(drop=True)
    return df


def _top_entities(df: pd.DataFrame, entity_col: str, n: int) -> list:
    """Return the top-n entities by row count.

    :param df: dataframe
    :param entity_col: entity column name
    :param n: number of top entities
    :return: list of entity values
    """
    counts = df[entity_col].value_counts()
    return counts.head(n).index.tolist()


@ltools.tool
def compare_panel_entities(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any],
    target_cols: list[str],
    numeric_continuous_cols: list[str],
    secondary_keys: list[str],
) -> dict[str, Any]:
    """Compare panel entities across target and numeric columns.

    For each key numeric column this function produces:
    * A boxplot of values grouped by entity (top 20 entities by row count).
    * A time-series overlay plot with top-5 entities in colour and the rest
      aggregated in light gray.
    * The coefficient of variation across entities per time step.
    * A Kruskal-Wallis H-test across entity groups.

    :param path: dataset file path
    :param time_col: datetime column name
    :param winner_formatter: kwargs for ``pd.to_datetime``
    :param target_cols: primary target column(s)
    :param numeric_continuous_cols: continuous numeric columns
    :param secondary_keys: entity / group key columns
    :return: per-column heterogeneity diagnostics with plots
    """
    if not secondary_keys:
        return {"error": "No secondary_keys provided; panel comparison skipped."}

    df = _parse_and_sort(path, time_col, winner_formatter)
    entity_col = secondary_keys[0]

    if entity_col not in df.columns:
        return {"error": f"Entity column '{entity_col}' not found in dataset."}

    unique_entities = df[entity_col].dropna().unique()
    entity_count = len(unique_entities)

    # Determine display entities (max 20, else top 20 by row count)
    if entity_count > _MAX_ENTITIES:
        display_entities = _top_entities(df, entity_col, _MAX_ENTITIES)
    else:
        display_entities = unique_entities.tolist()

    top5 = _top_entities(df, entity_col, _TOP_OVERLAY)

    cols_to_analyse = list(dict.fromkeys(target_cols + numeric_continuous_cols))
    cols_to_analyse = [c for c in cols_to_analyse if c in df.columns]

    if not cols_to_analyse:
        return {"error": "No valid numeric columns to analyse."}

    results: dict[str, Any] = {}
    plots: list[str] = []

    for col in cols_to_analyse:
        series = df[[entity_col, time_col, col]].dropna(subset=[col])
        if series.empty:
            continue

        # --- Boxplot by entity ---
        box_df = series[series[entity_col].isin(display_entities)]
        groups_for_box = [
            grp[col].values
            for _, grp in box_df.groupby(entity_col, sort=False)
        ]
        labels_for_box = [
            str(name)
            for name, _ in box_df.groupby(entity_col, sort=False)
        ]

        fig, ax = plt.subplots(figsize=(max(8, len(labels_for_box) * 0.5), 5))
        ax.boxplot(groups_for_box, labels=labels_for_box, vert=True)
        ax.set_title(f"{col} by {entity_col}")
        ax.set_xlabel(entity_col)
        ax.set_ylabel(col)
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        p = tinptool.write_stage_plot(path, _STAGE, f"boxplot_{col}", fig)
        plt.close(fig)
        plots.append(p)

        # --- Time-series overlay ---
        fig, ax = plt.subplots(figsize=(12, 5))
        for ent, grp in series.groupby(entity_col, sort=False):
            if ent in top5:
                ax.plot(grp[time_col], grp[col], label=str(ent), alpha=0.85)
            else:
                ax.plot(
                    grp[time_col], grp[col],
                    color="lightgray", alpha=0.3, linewidth=0.5,
                )
        ax.set_title(f"{col} — entity overlay")
        ax.set_xlabel(time_col)
        ax.set_ylabel(col)
        ax.legend(loc="best", fontsize="small")
        plt.tight_layout()
        p = tinptool.write_stage_plot(path, _STAGE, f"overlay_{col}", fig)
        plt.close(fig)
        plots.append(p)

        # --- Coefficient of variation across entities per time step ---
        grouped_time = series.groupby(time_col)[col]
        cv_per_step = grouped_time.std() / grouped_time.mean().replace(0, np.nan)
        cv_mean = float(cv_per_step.mean()) if not cv_per_step.empty else None
        cv_std = float(cv_per_step.std()) if not cv_per_step.empty else None

        # --- Kruskal-Wallis test ---
        entity_groups = [
            grp[col].dropna().values
            for _, grp in series.groupby(entity_col, sort=False)
            if len(grp[col].dropna()) > 0
        ]
        if len(entity_groups) >= 2:
            h_stat, p_val = spstats.kruskal(*entity_groups)
        else:
            h_stat, p_val = None, None

        results[col] = {
            "entity_count": int(entity_count),
            "kruskal_h": float(h_stat) if h_stat is not None else None,
            "kruskal_p": float(p_val) if p_val is not None else None,
            "significant": bool(p_val < 0.05) if p_val is not None else None,
            "cv_mean": cv_mean,
            "cv_std": cv_std,
            "top_entities": top5,
        }

    any_significant = any(
        v.get("significant") is True for v in results.values()
    )

    output = {
        **results,
        "panel_heterogeneity": any_significant,
        "plots": plots,
    }

    tinptool.write_stage_trace(path, _STAGE, output)
    return output
