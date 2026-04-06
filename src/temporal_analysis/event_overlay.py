"""
Event-overlay visualisation tools.

Import as:

import src.temporal_analysis.event_overlay as sevtoverlay
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

_STAGE = "event_overlay"


def _is_binary(series: pd.Series) -> bool:
    """
    Check whether a series contains only binary (0/1) values.

    :param series: input series
    :return: True if values are limited to {0, 1}
    """
    unique = set(series.dropna().unique())
    return unique.issubset({0, 1, 0.0, 1.0, True, False})


def _contiguous_spans(
    mask: pd.Series,
    time_index: pd.Series,
) -> list[tuple[Any, Any]]:
    """
    Find contiguous True spans and return ``(start, end)`` time pairs.

    :param mask: boolean series aligned with time_index
    :param time_index: datetime series of equal length
    :return: list of (start_time, end_time) tuples
    """
    spans: list[tuple[Any, Any]] = []
    in_span = False
    start = None
    for t, v in zip(time_index, mask):
        if v and not in_span:
            start = t
            in_span = True
        elif not v and in_span:
            spans.append((start, t))
            in_span = False
    if in_span and start is not None:
        spans.append((start, time_index.iloc[-1]))
    return spans


@ltools.tool
def overlay_events(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any],
    target_cols: list[str],
    known_exogenous_cols: list[str],
) -> list[str]:
    """Overlay binary event indicators on a target time-series line plot.

    For each column in ``known_exogenous_cols`` that is binary (0/1), draws
    vertical shaded spans where the value equals 1, overlaid on a line
    chart of each target column.

    :param path: dataset file path
    :param time_col: datetime column name
    :param winner_formatter: kwargs for ``pd.to_datetime``
    :param target_cols: target column(s) to plot
    :param known_exogenous_cols: exogenous indicator columns to evaluate
    :return: list of saved plot file paths
    """
    df = tinptool.load_dataset(pathlib.Path(path))
    if df.empty:
        _LOG.warning("Empty dataset -- skipping event overlay.")
        return []

    df[time_col] = pd.to_datetime(df[time_col], **(winner_formatter or {}))
    df = df.sort_values(time_col).reset_index(drop=True)

    # Resolve target columns
    plot_targets: list[str] = [c for c in (target_cols or []) if c and c in df.columns]
    if not plot_targets:
        _LOG.warning("No target columns for event overlay.")
        return []

    # Filter to binary exogenous columns
    binary_exo: list[str] = []
    for col in (known_exogenous_cols or []):
        if col in df.columns and _is_binary(df[col]):
            binary_exo.append(col)

    if not binary_exo:
        _LOG.info("No binary exogenous columns found; nothing to overlay.")
        return []

    plot_paths: list[str] = []
    palette = plt.cm.Set2.colors  # type: ignore[attr-defined]

    for target in plot_targets:
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(df[time_col], df[target], linewidth=0.9, color="black", label=target)

        for idx, exo in enumerate(binary_exo):
            mask = df[exo].fillna(0).astype(bool)
            spans = _contiguous_spans(mask, df[time_col])
            color = palette[idx % len(palette)]
            for i, (s, e) in enumerate(spans):
                ax.axvspan(
                    s, e,
                    alpha=0.25,
                    color=color,
                    label=exo if i == 0 else None,
                )

        ax.set_title(f"{target} with event overlays")
        ax.set_xlabel(time_col)
        ax.set_ylabel(target)
        ax.legend(fontsize=8, loc="best")
        fig.tight_layout()
        pp = tinptool.write_stage_plot(path, _STAGE, f"events.{target}", fig)
        plt.close(fig)
        plot_paths.append(pp)

    tinptool.write_stage_trace(path, _STAGE, {"target_cols": plot_targets, "binary_exo_cols": binary_exo, "plot_paths": plot_paths})
    return plot_paths


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------

def run_temporal_analysis(path: str) -> dict[str, Any]:
    """
    Execute the full temporal analysis suite.

    This function is intended to be called from the master pipeline.  It
    does **not** build a StateGraph -- the individual tool functions are
    invoked directly so they can also be called independently by an agent.

    :param path: dataset file path
    :return: combined temporal analysis report
    """
    _LOG.info("run_temporal_analysis is a placeholder entry-point. "
              "Individual tools should be invoked from the master pipeline.")
    return {
        "tools": [
            "plot_raw_time_series",
            "plot_zoom_windows",
            "resample_and_plot",
            "detect_seasonality",
            "decompose_series",
            "overlay_events",
        ],
        "note": "Invoke each tool with the required arguments from the pipeline state.",
    }
