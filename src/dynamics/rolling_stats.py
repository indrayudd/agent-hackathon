"""
Import as:

import src.dynamics.rolling_stats as srolling
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

_WINDOW_MAP: dict[str, list[int]] = {
    "hourly": [24, 168, 720],
    "daily": [7, 30, 90],
    "weekly": [4, 13, 52],
    "monthly": [3, 6, 12],
}
_DEFAULT_WINDOWS: list[int] = [7, 30, 90]


class _RollingStatsArgs(pydantic.BaseModel):
    """
    Store arguments for rolling statistics computation.
    """

    model_config = pydantic.ConfigDict(extra="forbid")
    path: str
    time_col: str
    winner_formatter: dict[str, Any] | None = None
    target_cols: list[str] | None = None
    numeric_continuous_cols: list[str] | None = None
    expected_frequency: str | None = None


def _select_windows(expected_frequency: str | None) -> list[int]:
    """
    Choose rolling window sizes based on the expected sampling frequency.

    :param expected_frequency: frequency label such as 'daily', 'hourly', etc.
    :return: list of three window sizes (small, medium, large)
    """
    if expected_frequency is None:
        return list(_DEFAULT_WINDOWS)
    key = expected_frequency.strip().lower()
    return list(_WINDOW_MAP.get(key, _DEFAULT_WINDOWS))


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


@ltools.tool(args_schema=_RollingStatsArgs)
def compute_rolling_stats(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any] | None = None,
    target_cols: list[str] | None = None,
    numeric_continuous_cols: list[str] | None = None,
    expected_frequency: str | None = None,
) -> dict:
    """
    Compute rolling mean, standard deviation, min, and max for each
    target / numeric continuous column across multiple window sizes derived
    from the expected sampling frequency.

    For each column the function also produces a plot showing the raw series,
    the rolling mean at the middle window size, and a shaded +/-1 std band.

    A rolling variance ratio (max rolling std / min rolling std across windows)
    is computed; when it exceeds 2.0 the flag ``regime_shifts_suspected`` is
    set to True.

    :param path: dataset file path
    :param time_col: timestamp column name
    :param winner_formatter: kwargs forwarded to ``pd.to_datetime``
    :param target_cols: primary target columns to analyse
    :param numeric_continuous_cols: additional numeric columns to analyse
    :param expected_frequency: sampling cadence label (hourly/daily/weekly/monthly)
    :return: rolling statistics summary dict
    """
    dataset_path = pathlib.Path(path)
    df = tinptool.load_dataset(dataset_path)
    fmt = winner_formatter or {}
    df[time_col] = pd.to_datetime(df[time_col], **fmt)
    df = df.sort_values(time_col).reset_index(drop=True)

    windows = _select_windows(expected_frequency)
    columns = _gather_columns(target_cols, numeric_continuous_cols)
    mid_window = windows[len(windows) // 2]

    columns_report: dict[str, Any] = {}
    plot_paths: list[str] = []
    global_max_std: float = 0.0
    global_min_std: float = float("inf")

    for col in columns:
        if col not in df.columns:
            _LOG.warning("Column '%s' not found in dataset, skipping.", col)
            continue

        series = pd.to_numeric(df[col], errors="coerce")

        if series.dropna().shape[0] < 3:
            _LOG.warning(
                "Column '%s' has fewer than 3 non-null values, skipping.", col,
            )
            columns_report[col] = {"skipped": True, "reason": "insufficient_data"}
            continue

        col_stats: dict[str, Any] = {}
        for w in windows:
            effective_w = min(w, len(series))
            if effective_w < 2:
                col_stats[str(w)] = {"skipped": True, "reason": "window_too_large"}
                continue

            r_mean = series.rolling(window=effective_w, min_periods=1).mean()
            r_std = series.rolling(window=effective_w, min_periods=1).std()
            r_min = series.rolling(window=effective_w, min_periods=1).min()
            r_max = series.rolling(window=effective_w, min_periods=1).max()

            mean_of_means = float(r_mean.mean()) if not r_mean.isna().all() else None
            std_of_stds = float(r_std.mean()) if not r_std.isna().all() else None
            mean_of_mins = float(r_min.mean()) if not r_min.isna().all() else None
            mean_of_maxs = float(r_max.mean()) if not r_max.isna().all() else None

            col_stats[str(w)] = {
                "mean_of_means": mean_of_means,
                "std_of_stds": std_of_stds,
                "mean_of_mins": mean_of_mins,
                "mean_of_maxs": mean_of_maxs,
            }

            # Track global std extremes for variance ratio
            valid_std = r_std.dropna()
            if not valid_std.empty:
                col_max_std = float(valid_std.max())
                col_min_std = float(valid_std[valid_std > 0].min()) if (valid_std > 0).any() else 0.0
                global_max_std = max(global_max_std, col_max_std)
                if col_min_std > 0:
                    global_min_std = min(global_min_std, col_min_std)

        columns_report[col] = col_stats

        # --- Plot: raw series + rolling mean + +/-1 std band (middle window) ---
        effective_mid = min(mid_window, len(series))
        if effective_mid >= 2:
            r_mean_mid = series.rolling(window=effective_mid, min_periods=1).mean()
            r_std_mid = series.rolling(window=effective_mid, min_periods=1).std()
            time_axis = df[time_col]

            fig, ax = plt.subplots(figsize=(12, 4))
            ax.plot(time_axis, series, linewidth=0.5, alpha=0.6, label="raw")
            ax.plot(time_axis, r_mean_mid, linewidth=1.2, label=f"rolling mean (w={effective_mid})")
            ax.fill_between(
                time_axis,
                r_mean_mid - r_std_mid,
                r_mean_mid + r_std_mid,
                alpha=0.2,
                label="\u00b11 std band",
            )
            ax.set_title(f"Rolling stats: {col}")
            ax.set_xlabel(time_col)
            ax.set_ylabel(col)
            ax.legend(loc="upper left", fontsize=8)
            fig.tight_layout()

            plot_path = tinptool.write_stage_plot(path, "rolling_stats", col, fig)
            plt.close(fig)
            plot_paths.append(plot_path)

    # Compute rolling variance ratio
    if global_min_std > 0 and global_min_std != float("inf"):
        rolling_variance_ratio = round(global_max_std / global_min_std, 4)
    else:
        rolling_variance_ratio = None

    regime_shifts_suspected = (
        rolling_variance_ratio is not None and rolling_variance_ratio > 2.0
    )

    result = {
        "columns": columns_report,
        "rolling_variance_ratio": rolling_variance_ratio,
        "regime_shifts_suspected": regime_shifts_suspected,
        "plots": plot_paths,
    }

    tinptool.write_stage_trace(path, "rolling_stats", result)
    return result
