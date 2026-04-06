"""
Import as:

import src.dynamics.outlier_detection as soutlier
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

import langchain.tools as ltools
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pydantic

import src.tools.input_tools as tinptool

_LOG = logging.getLogger(__name__)

_MAX_OUTLIERS_PER_COL: int = 50
_CONTEXT_RADIUS: int = 5


class _TimeOutlierArgs(pydantic.BaseModel):
    """
    Store arguments for time-aware outlier detection.
    """

    model_config = pydantic.ConfigDict(extra="forbid")
    path: str
    time_col: str
    winner_formatter: dict[str, Any] | None = None
    target_cols: list[str] | None = None
    numeric_continuous_cols: list[str] | None = None


def _gather_columns(
    target_cols: list[str] | None,
    numeric_continuous_cols: list[str] | None,
) -> list[str]:
    """
    Merge target and numeric continuous column lists, preserving order and
    removing duplicates.

    :param target_cols: target columns
    :param numeric_continuous_cols: numeric continuous columns
    :return: deduplicated ordered column list
    """
    seen: set[str] = set()
    result: list[str] = []
    for col in (target_cols or []) + (numeric_continuous_cols or []):
        if col not in seen:
            seen.add(col)
            result.append(col)
    return result


def _extract_context(series: pd.Series, idx: int) -> tuple[list[float], list[float]]:
    """
    Extract up to ``_CONTEXT_RADIUS`` values before and after a given index.

    :param series: numeric series
    :param idx: position of the outlier
    :return: (context_before, context_after) as plain float lists
    """
    start_before = max(0, idx - _CONTEXT_RADIUS)
    end_after = min(len(series), idx + _CONTEXT_RADIUS + 1)

    before = series.iloc[start_before:idx].tolist()
    after = series.iloc[idx + 1 : end_after].tolist()

    # Convert to plain floats, replacing NaN with None
    before = [float(v) if pd.notna(v) else None for v in before]
    after = [float(v) if pd.notna(v) else None for v in after]
    return before, after


@ltools.tool(args_schema=_TimeOutlierArgs)
def detect_time_outliers(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any] | None = None,
    target_cols: list[str] | None = None,
    numeric_continuous_cols: list[str] | None = None,
) -> dict:
    """
    Detect temporal outliers in each target / numeric continuous column using
    an IQR-based method applied over a rolling window.

    The rolling window size is ``max(30, len(data) // 20)``.  For each
    position the rolling median and rolling IQR (Q3 - Q1) are computed.
    A value is flagged as an outlier when it deviates from the rolling median
    by more than 3 times the rolling IQR.  Outliers whose deviation exceeds
    5 times the rolling IQR are classified as ``spike``; the rest are labelled
    ``moderate_outlier``.

    Each outlier record includes a context window of 5 values before and
    after.  The outlier list per column is capped at the 50 most extreme
    deviations.

    A plot is produced per column showing the raw series with outlier points
    highlighted in red.

    :param path: dataset file path
    :param time_col: timestamp column name
    :param winner_formatter: kwargs forwarded to ``pd.to_datetime``
    :param target_cols: primary target columns to analyse
    :param numeric_continuous_cols: additional numeric columns to analyse
    :return: outlier summary dict keyed by column name
    """
    dataset_path = pathlib.Path(path)
    df = tinptool.load_dataset(dataset_path)
    fmt = winner_formatter or {}
    df[time_col] = pd.to_datetime(df[time_col], **fmt)
    df = df.sort_values(time_col).reset_index(drop=True)

    columns = _gather_columns(target_cols, numeric_continuous_cols)
    col_results: dict[str, Any] = {}
    plot_paths: list[str] = []

    for col in columns:
        if col not in df.columns:
            _LOG.warning("Column '%s' not found in dataset, skipping.", col)
            continue

        series = pd.to_numeric(df[col], errors="coerce")
        n_valid = int(series.notna().sum())

        if n_valid < 10:
            _LOG.warning(
                "Column '%s' has fewer than 10 valid points, skipping outlier detection.",
                col,
            )
            col_results[col] = {
                "n_outliers": 0,
                "outliers": [],
                "skipped": True,
                "reason": "insufficient_data",
            }
            continue

        window = max(30, len(series) // 20)
        effective_window = min(window, len(series))

        rolling_median = series.rolling(window=effective_window, min_periods=1, center=True).median()
        rolling_q1 = series.rolling(window=effective_window, min_periods=1, center=True).quantile(0.25)
        rolling_q3 = series.rolling(window=effective_window, min_periods=1, center=True).quantile(0.75)
        rolling_iqr = rolling_q3 - rolling_q1

        # Avoid zero IQR (constant regions): use a small epsilon
        rolling_iqr_safe = rolling_iqr.replace(0, np.nan)

        deviation = (series - rolling_median).abs()
        is_outlier = deviation > 3 * rolling_iqr_safe

        # Also require the value itself to be non-null
        is_outlier = is_outlier & series.notna()

        outlier_indices = series.index[is_outlier.fillna(False)].tolist()

        # Build outlier records
        records: list[dict[str, Any]] = []
        for idx in outlier_indices:
            val = float(series.iloc[idx])
            med = float(rolling_median.iloc[idx]) if pd.notna(rolling_median.iloc[idx]) else None
            iqr_val = float(rolling_iqr_safe.iloc[idx]) if pd.notna(rolling_iqr_safe.iloc[idx]) else None
            dev = float(deviation.iloc[idx])

            # Classify type
            if iqr_val is not None and iqr_val > 0 and dev > 5 * iqr_val:
                outlier_type = "spike"
            else:
                outlier_type = "moderate_outlier"

            ts = df[time_col].iloc[idx]
            context_before, context_after = _extract_context(series, idx)

            records.append({
                "timestamp": str(ts),
                "value": val,
                "rolling_median": med,
                "type": outlier_type,
                "deviation": dev,
                "context_before": context_before,
                "context_after": context_after,
            })

        # Cap to most extreme outliers
        if len(records) > _MAX_OUTLIERS_PER_COL:
            records.sort(key=lambda r: r["deviation"], reverse=True)
            records = records[:_MAX_OUTLIERS_PER_COL]

        col_results[col] = {
            "n_outliers": len(records),
            "outliers": records,
        }

        # --- Plot: raw series with outliers highlighted ---
        time_axis = df[time_col]
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(time_axis, series, linewidth=0.5, alpha=0.6, label="raw")

        if outlier_indices:
            outlier_times = time_axis.iloc[outlier_indices]
            outlier_vals = series.iloc[outlier_indices]
            ax.scatter(
                outlier_times,
                outlier_vals,
                color="red",
                s=18,
                zorder=5,
                label=f"outliers ({len(records)})",
            )

        ax.set_title(f"Time outliers (IQR): {col}")
        ax.set_xlabel(time_col)
        ax.set_ylabel(col)
        ax.legend(loc="upper left", fontsize=8)
        fig.tight_layout()

        plot_path = tinptool.write_stage_plot(path, "outlier_detection", col, fig)
        plt.close(fig)
        plot_paths.append(plot_path)

    result = {
        "columns": col_results,
        "plots": plot_paths,
    }
    tinptool.write_stage_trace(path, "outlier_detection", result)
    return result
