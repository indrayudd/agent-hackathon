"""
Import as:

import src.dynamics.changepoints as schangepoints
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


class _ChangepointArgs(pydantic.BaseModel):
    """
    Store arguments for changepoint detection.
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


@ltools.tool(args_schema=_ChangepointArgs)
def detect_changepoints(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any] | None = None,
    target_cols: list[str] | None = None,
    numeric_continuous_cols: list[str] | None = None,
) -> dict:
    """
    Detect structural changepoints in each target / numeric continuous column
    using the PELT algorithm with an RBF cost model from the ``ruptures``
    library.

    For every detected breakpoint the function records the index, the
    corresponding timestamp, and the mean value of the segment immediately
    before and after the break.  A plot is produced per column showing the raw
    series with vertical red dashed lines at each changepoint.

    If the ``ruptures`` library is not installed the function returns a
    diagnostic report noting its absence instead of raising an error.

    :param path: dataset file path
    :param time_col: timestamp column name
    :param winner_formatter: kwargs forwarded to ``pd.to_datetime``
    :param target_cols: primary target columns to analyse
    :param numeric_continuous_cols: additional numeric columns to analyse
    :return: changepoint summary dict keyed by column name
    """
    try:
        import ruptures  # noqa: F811
    except ImportError:
        msg = (
            "The 'ruptures' library is not installed. "
            "Install it with: pip install ruptures"
        )
        _LOG.warning(msg)
        result: dict[str, Any] = {
            "error": msg,
            "ruptures_available": False,
            "plots": [],
        }
        tinptool.write_stage_trace(path, "changepoints", result)
        return result

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
        valid_mask = series.notna()
        n_valid = int(valid_mask.sum())

        if n_valid < 10:
            _LOG.warning(
                "Column '%s' has fewer than 10 valid points, skipping changepoint detection.",
                col,
            )
            col_results[col] = {"skipped": True, "reason": "insufficient_data"}
            continue

        # Fill internal NaNs with forward fill for ruptures (requires contiguous signal)
        signal = series.fillna(method="ffill").fillna(method="bfill").values.astype(float)

        algo = ruptures.Pelt(model="rbf").fit(signal)
        try:
            breakpoints = algo.predict(pen=10)
        except Exception as exc:
            _LOG.warning("PELT failed for column '%s': %s", col, exc)
            col_results[col] = {"skipped": True, "reason": str(exc)}
            continue

        # ruptures returns the last index (len) as a sentinel; remove it
        breakpoints = [bp for bp in breakpoints if bp < len(signal)]

        changepoint_records: list[dict[str, Any]] = []
        for bp_idx in breakpoints:
            timestamp = df[time_col].iloc[bp_idx] if bp_idx < len(df) else None

            # Segment means: before and after the breakpoint
            seg_before = signal[max(0, bp_idx - 20) : bp_idx]
            seg_after = signal[bp_idx : min(len(signal), bp_idx + 20)]

            value_before_mean = float(np.nanmean(seg_before)) if len(seg_before) > 0 else None
            value_after_mean = float(np.nanmean(seg_after)) if len(seg_after) > 0 else None

            changepoint_records.append({
                "index": int(bp_idx),
                "timestamp": str(timestamp) if timestamp is not None else None,
                "value_before_mean": value_before_mean,
                "value_after_mean": value_after_mean,
            })

        col_results[col] = changepoint_records

        # --- Plot: raw series with changepoint lines ---
        time_axis = df[time_col]
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(time_axis, series, linewidth=0.6, alpha=0.7, label="raw")
        for rec in changepoint_records:
            bp_idx = rec["index"]
            if bp_idx < len(time_axis):
                ax.axvline(
                    x=time_axis.iloc[bp_idx],
                    color="red",
                    linestyle="--",
                    linewidth=0.9,
                    alpha=0.8,
                )
        ax.set_title(f"Changepoints (PELT): {col}")
        ax.set_xlabel(time_col)
        ax.set_ylabel(col)
        ax.legend(loc="upper left", fontsize=8)
        fig.tight_layout()

        plot_path = tinptool.write_stage_plot(path, "changepoints", col, fig)
        plt.close(fig)
        plot_paths.append(plot_path)

    result = {
        "columns": col_results,
        "ruptures_available": True,
        "plots": plot_paths,
    }
    tinptool.write_stage_trace(path, "changepoints", result)
    return result
