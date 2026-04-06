"""
Resampling analysis tools for temporal data.

Import as:

import src.temporal_analysis.resample_analysis as sresample
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

import langchain.tools as ltools
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import src.tools.input_tools as tinptool

_LOG = logging.getLogger(__name__)

_STAGE = "resample_analysis"

# Map from expected frequency hints to coarser resampling targets.
# Each value is an ordered list of (pandas offset alias, human label).
_COARSER_MAP: dict[str, list[tuple[str, str]]] = {
    "minutely": [("15min", "15-minute"), ("h", "hourly"), ("D", "daily")],
    "5-minutely": [("30min", "30-minute"), ("h", "hourly"), ("D", "daily")],
    "15-minutely": [("h", "hourly"), ("D", "daily")],
    "30-minutely": [("h", "hourly"), ("D", "daily")],
    "hourly": [("D", "daily"), ("W", "weekly")],
    "daily": [("W", "weekly"), ("MS", "monthly")],
    "weekly": [("MS", "monthly"), ("QS", "quarterly")],
    "monthly": [("QS", "quarterly"), ("YS", "yearly")],
    "quarterly": [("YS", "yearly")],
    "yearly": [("5YS", "5-yearly")],
}

# Fallback when the hint is unknown or missing.
_DEFAULT_COARSER: list[tuple[str, str]] = [("W", "weekly"), ("MS", "monthly")]


def _pick_coarser_frequencies(
    expected_frequency: str | None,
) -> list[tuple[str, str]]:
    """
    Select 2-3 coarser resampling frequencies based on the native frequency.

    :param expected_frequency: hint string produced by the ingest stage
    :return: list of ``(pandas_offset, label)`` tuples
    """
    if not expected_frequency:
        return _DEFAULT_COARSER

    key = expected_frequency.strip().lower().replace(" ", "").replace("-", "")
    # Try exact match first, then prefix match
    for k, v in _COARSER_MAP.items():
        if key == k.replace("-", ""):
            return v[:3]
    # Heuristic: look for keywords
    if "min" in key:
        return _COARSER_MAP.get("minutely", _DEFAULT_COARSER)
    if "hour" in key or key.startswith("h"):
        return _COARSER_MAP["hourly"]
    if "day" in key or key.startswith("d"):
        return _COARSER_MAP["daily"]
    if "week" in key or key.startswith("w"):
        return _COARSER_MAP["weekly"]
    if "month" in key or key.startswith("m"):
        return _COARSER_MAP["monthly"]

    return _DEFAULT_COARSER


@ltools.tool
def resample_and_plot(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any],
    target_cols: list[str],
    numeric_continuous_cols: list[str],
    expected_frequency: str | None,
) -> dict[str, Any]:
    """Resample the time series at coarser frequencies and plot comparisons.

    Given the native ``expected_frequency``, picks 2-3 coarser frequencies
    (e.g., hourly -> daily, weekly) and resamples the target / numeric
    columns using mean aggregation.  Produces a side-by-side comparison
    figure for each column and returns a summary report.

    :param path: dataset file path
    :param time_col: datetime column name
    :param winner_formatter: kwargs for ``pd.to_datetime``
    :param target_cols: target column(s)
    :param numeric_continuous_cols: numeric continuous columns
    :param expected_frequency: native frequency hint (e.g. ``"daily"``)
    :return: resampling report dict with frequencies, stats, and plot paths
    """
    df = tinptool.load_dataset(pathlib.Path(path))
    if df.empty:
        _LOG.warning("Empty dataset -- skipping resample analysis.")
        return {"frequencies": [], "stats": {}, "plot_paths": []}

    df[time_col] = pd.to_datetime(df[time_col], **(winner_formatter or {}))
    df = df.sort_values(time_col).reset_index(drop=True)
    df = df.set_index(time_col)

    plot_cols: list[str] = [c for c in (target_cols or []) if c and c in df.columns]
    if not plot_cols:
        plot_cols = [
            c for c in (numeric_continuous_cols or []) if c in df.columns
        ][:1]
    if not plot_cols:
        _LOG.warning("No plottable columns for resample analysis.")
        return {"frequencies": [], "stats": {}, "plot_paths": []}

    coarser = _pick_coarser_frequencies(expected_frequency)
    plot_paths: list[str] = []
    stats: dict[str, Any] = {}

    for col in plot_cols:
        col_stats: dict[str, Any] = {"native_count": int(df[col].dropna().shape[0])}
        n_freq = len(coarser)
        fig, axes = plt.subplots(1, n_freq + 1, figsize=(5 * (n_freq + 1), 4), squeeze=False)
        axes_row = axes[0]

        # Native
        native_series = df[col].dropna()
        axes_row[0].plot(native_series.index, native_series.values, linewidth=0.8)
        axes_row[0].set_title(f"Native ({expected_frequency or 'original'})")
        axes_row[0].set_ylabel(col)
        axes_row[0].tick_params(labelsize=7, axis="x", rotation=30)

        for i, (offset, label) in enumerate(coarser):
            try:
                resampled = df[[col]].resample(offset).mean().dropna()
            except Exception as exc:
                _LOG.warning("Resample failed for %s at %s: %s", col, offset, exc)
                axes_row[i + 1].set_title(f"{label} (error)")
                col_stats[label] = {"error": str(exc)}
                continue

            axes_row[i + 1].plot(
                resampled.index, resampled[col].values, linewidth=0.8,
            )
            axes_row[i + 1].set_title(f"{label} ({offset})")
            axes_row[i + 1].tick_params(labelsize=7, axis="x", rotation=30)

            col_stats[label] = {
                "offset": offset,
                "resampled_count": int(resampled.shape[0]),
                "mean": float(resampled[col].mean()) if not resampled.empty else None,
                "std": float(resampled[col].std()) if not resampled.empty else None,
            }

        fig.suptitle(f"Resample comparison -- {col}", fontsize=11)
        fig.tight_layout(rect=[0, 0, 1, 0.94])
        pp = tinptool.write_stage_plot(path, _STAGE, f"resample.{col}", fig)
        plt.close(fig)
        plot_paths.append(pp)
        stats[col] = col_stats

    report: dict[str, Any] = {
        "frequencies": [label for _, label in coarser],
        "stats": stats,
        "plot_paths": plot_paths,
    }

    tinptool.write_stage_trace(path, _STAGE, report)
    return report
