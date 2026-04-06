"""
Raw time-series visualisation tools.

Import as:

import src.temporal_analysis.plot_time_series as stsplot
"""

from __future__ import annotations

import logging
import math
import pathlib
import random
from typing import Any

import langchain.tools as ltools
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import src.tools.input_tools as tinptool

_LOG = logging.getLogger(__name__)

_STAGE = "time_series"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_and_sort(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any],
) -> pd.DataFrame:
    """
    Load dataset, parse the time column, and sort chronologically.

    :param path: dataset file path
    :param time_col: name of the datetime column
    :param winner_formatter: kwargs forwarded to ``pd.to_datetime``
    :return: sorted dataframe with parsed time column
    """
    df = tinptool.load_dataset(pathlib.Path(path))
    if df.empty:
        return df
    df[time_col] = pd.to_datetime(df[time_col], **(winner_formatter or {}))
    df = df.sort_values(time_col).reset_index(drop=True)
    return df


def _resolve_plot_cols(
    target_cols: list[str],
    numeric_continuous_cols: list[str],
) -> list[str]:
    """
    Return the columns to plot, falling back to the first numeric column
    when no target is specified.

    :param target_cols: explicit target column(s)
    :param numeric_continuous_cols: available numeric columns
    :return: list of column names to visualise
    """
    cols = [c for c in (target_cols or []) if c]
    if not cols:
        cols = numeric_continuous_cols[:1] if numeric_continuous_cols else []
    return cols


# ---------------------------------------------------------------------------
# Tool: plot_raw_time_series
# ---------------------------------------------------------------------------

@ltools.tool
def plot_raw_time_series(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any],
    target_cols: list[str],
    numeric_continuous_cols: list[str],
    secondary_keys: list[str],
    type: str,
) -> list[str]:
    """Plot raw time-series line charts.

    Produces three flavours depending on context:
    * **single** -- one line plot per target / numeric column.
    * **multivariate** -- small-multiples grid (max 4x4) for numeric columns.
    * **multiple** (panel) -- overlay top-5 entities by row count with the
      remaining entities drawn in light gray.

    :param path: dataset file path
    :param time_col: datetime column name
    :param winner_formatter: kwargs for ``pd.to_datetime``
    :param target_cols: target column(s) to plot
    :param numeric_continuous_cols: numeric continuous columns available
    :param secondary_keys: entity / group key columns
    :param type: ``"single"`` or ``"multiple"`` (panel mode)
    :return: list of saved plot file paths
    """
    df = _parse_and_sort(path, time_col, winner_formatter)
    if df.empty or len(df) < 2:
        _LOG.warning("Dataset too small for time-series plots (%d rows).", len(df))
        return []

    plot_cols = _resolve_plot_cols(target_cols, numeric_continuous_cols)
    if not plot_cols:
        _LOG.warning("No plottable columns found.")
        return []

    plot_paths: list[str] = []

    # ------------------------------------------------------------------
    # Panel mode: overlay entities
    # ------------------------------------------------------------------
    if type == "multiple" and secondary_keys:
        entity_col = secondary_keys[0]
        if entity_col in df.columns:
            entity_counts = df[entity_col].value_counts()
            top_entities = entity_counts.head(5).index.tolist()

            for col in plot_cols:
                if col not in df.columns:
                    continue
                fig, ax = plt.subplots(figsize=(12, 5))
                # Background entities
                other_entities = [e for e in entity_counts.index if e not in top_entities]
                for ent in other_entities:
                    subset = df[df[entity_col] == ent]
                    ax.plot(
                        subset[time_col], subset[col],
                        color="lightgray", alpha=0.4, linewidth=0.5,
                    )
                # Top entities
                palette = plt.cm.tab10.colors  # type: ignore[attr-defined]
                for idx, ent in enumerate(top_entities):
                    subset = df[df[entity_col] == ent]
                    ax.plot(
                        subset[time_col], subset[col],
                        color=palette[idx % len(palette)],
                        linewidth=1.2, label=str(ent),
                    )
                ax.set_title(f"{col} by {entity_col} (top 5)")
                ax.set_xlabel(time_col)
                ax.set_ylabel(col)
                ax.legend(fontsize=8, loc="best")
                fig.tight_layout()
                pp = tinptool.write_stage_plot(path, _STAGE, f"panel.{col}", fig)
                plt.close(fig)
                plot_paths.append(pp)

            return plot_paths

    # ------------------------------------------------------------------
    # Multivariate small-multiples
    # ------------------------------------------------------------------
    multi_cols = [c for c in numeric_continuous_cols if c in df.columns]
    if len(multi_cols) > 1:
        n = min(len(multi_cols), 16)  # cap at 4x4
        ncols = min(4, n)
        nrows = math.ceil(n / ncols)
        fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3 * nrows), squeeze=False)
        for idx, col in enumerate(multi_cols[:n]):
            r, c = divmod(idx, ncols)
            ax = axes[r][c]
            ax.plot(df[time_col], df[col], linewidth=0.8)
            ax.set_title(col, fontsize=9)
            ax.tick_params(labelsize=7)
        # Hide unused axes
        for idx in range(n, nrows * ncols):
            r, c = divmod(idx, ncols)
            axes[r][c].set_visible(False)
        fig.suptitle("Multivariate time series", fontsize=11)
        fig.tight_layout(rect=[0, 0, 1, 0.96])
        pp = tinptool.write_stage_plot(path, _STAGE, "multivariate_grid", fig)
        plt.close(fig)
        plot_paths.append(pp)

    # ------------------------------------------------------------------
    # Single-series line plots (always produced for each target)
    # ------------------------------------------------------------------
    for col in plot_cols:
        if col not in df.columns:
            continue
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(df[time_col], df[col], linewidth=0.9)
        ax.set_title(f"{col} over time")
        ax.set_xlabel(time_col)
        ax.set_ylabel(col)
        fig.tight_layout()
        pp = tinptool.write_stage_plot(path, _STAGE, f"single.{col}", fig)
        plt.close(fig)
        plot_paths.append(pp)

    return plot_paths


# ---------------------------------------------------------------------------
# Tool: plot_zoom_windows
# ---------------------------------------------------------------------------

@ltools.tool
def plot_zoom_windows(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any],
    target_cols: list[str],
    numeric_continuous_cols: list[str],
) -> list[str]:
    """Plot zoomed-in windows of the time series.

    Automatically selects three windows for closer inspection:
    * last 10 % of the data (recent behaviour),
    * a random 5 % mid-section (typical behaviour),
    * first 5 % of the data (initial behaviour).

    :param path: dataset file path
    :param time_col: datetime column name
    :param winner_formatter: kwargs for ``pd.to_datetime``
    :param target_cols: target column(s) to plot
    :param numeric_continuous_cols: numeric continuous columns available
    :return: list of saved plot file paths
    """
    df = _parse_and_sort(path, time_col, winner_formatter)
    if df.empty or len(df) < 10:
        _LOG.warning("Dataset too small for zoom windows (%d rows).", len(df))
        return []

    plot_cols = _resolve_plot_cols(target_cols, numeric_continuous_cols)
    if not plot_cols:
        return []

    n = len(df)
    windows: list[tuple[str, int, int]] = [
        ("last_10pct", max(0, n - n // 10), n),
        ("first_5pct", 0, max(1, n // 20)),
    ]
    # Random mid-section
    mid_len = max(1, n // 20)
    mid_start_lo = n // 4
    mid_start_hi = max(mid_start_lo + 1, 3 * n // 4 - mid_len)
    mid_start = random.randint(mid_start_lo, mid_start_hi)
    windows.append(("mid_5pct", mid_start, min(n, mid_start + mid_len)))

    plot_paths: list[str] = []
    for col in plot_cols:
        if col not in df.columns:
            continue
        for label, start, end in windows:
            chunk = df.iloc[start:end]
            if chunk.empty:
                continue
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(chunk[time_col], chunk[col], linewidth=0.9)
            ax.set_title(f"{col} -- zoom: {label} (rows {start}-{end})")
            ax.set_xlabel(time_col)
            ax.set_ylabel(col)
            fig.tight_layout()
            pp = tinptool.write_stage_plot(path, _STAGE, f"zoom.{col}.{label}", fig)
            plt.close(fig)
            plot_paths.append(pp)

    return plot_paths
