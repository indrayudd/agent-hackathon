"""
Seasonality detection and decomposition tools.

Import as:

import src.temporal_analysis.seasonality as sseason
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

import langchain.tools as ltools
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as sp_stats

import src.tools.input_tools as tinptool

_LOG = logging.getLogger(__name__)

_STAGE = "seasonality"

# Significance threshold for Kruskal-Wallis tests.
_ALPHA = 0.05

# Groupings to extract and test.
_TIME_GROUPINGS: list[tuple[str, str]] = [
    ("hour_of_day", "hour"),
    ("day_of_week", "dayofweek"),
    ("month", "month"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_time_features(
    df: pd.DataFrame,
    time_col: str,
) -> pd.DataFrame:
    """
    Derive calendar features from the parsed time column.

    :param df: dataframe with parsed datetime column
    :param time_col: name of the datetime column
    :return: dataframe augmented with hour_of_day, day_of_week, month
    """
    ts = df[time_col]
    df = df.copy()
    df["hour_of_day"] = ts.dt.hour
    df["day_of_week"] = ts.dt.dayofweek
    df["month"] = ts.dt.month
    return df


def _kruskal_test(
    series: pd.Series,
    groups: pd.Series,
) -> tuple[float, bool]:
    """
    Run a Kruskal-Wallis H-test across groups.

    :param series: values
    :param groups: group labels (same length)
    :return: (p_value, is_significant)
    """
    grouped: dict[Any, list[float]] = {}
    for val, grp in zip(series, groups):
        if pd.isna(val) or pd.isna(grp):
            continue
        grouped.setdefault(grp, []).append(float(val))

    # Need at least 2 groups with data
    samples = [v for v in grouped.values() if len(v) >= 1]
    if len(samples) < 2:
        return 1.0, False

    try:
        stat, p = sp_stats.kruskal(*samples)
    except Exception:
        return 1.0, False

    return float(p), p < _ALPHA


# ---------------------------------------------------------------------------
# Tool: detect_seasonality
# ---------------------------------------------------------------------------

@ltools.tool
def detect_seasonality(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any],
    target_cols: list[str],
    numeric_continuous_cols: list[str],
) -> dict[str, Any]:
    """Detect seasonal patterns via calendar-grouping tests.

    Extracts hour-of-day, day-of-week, and month from the time column,
    then for each target / numeric column computes group means and runs a
    Kruskal-Wallis test to assess whether the distribution differs
    significantly across time groups.

    Produces grouped bar / line seasonal sub-series plots.

    :param path: dataset file path
    :param time_col: datetime column name
    :param winner_formatter: kwargs for ``pd.to_datetime``
    :param target_cols: target column(s)
    :param numeric_continuous_cols: numeric continuous columns
    :return: seasonality report dict
    """
    df = tinptool.load_dataset(pathlib.Path(path))
    if df.empty:
        _LOG.warning("Empty dataset -- skipping seasonality detection.")
        return {"seasonality_detected": False, "columns": {}, "plot_paths": []}

    df[time_col] = pd.to_datetime(df[time_col], **(winner_formatter or {}))
    df = df.sort_values(time_col).reset_index(drop=True)
    df = _extract_time_features(df, time_col)

    plot_cols: list[str] = [c for c in (target_cols or []) if c and c in df.columns]
    if not plot_cols:
        plot_cols = [c for c in (numeric_continuous_cols or []) if c in df.columns][:4]
    if not plot_cols:
        _LOG.warning("No columns available for seasonality analysis.")
        return {"seasonality_detected": False, "columns": {}, "plot_paths": []}

    report_cols: dict[str, Any] = {}
    plot_paths: list[str] = []
    any_significant = False

    for col in plot_cols:
        if col not in df.columns:
            continue

        col_report: dict[str, Any] = {}

        for grouping_name, _ in _TIME_GROUPINGS:
            if grouping_name not in df.columns:
                continue
            grp = df.groupby(grouping_name)[col]
            means = grp.mean()
            stds = grp.std().fillna(0)
            p_val, sig = _kruskal_test(df[col], df[grouping_name])

            col_report[grouping_name] = {
                "p_value": p_val,
                "significant": sig,
                "means": {str(k): float(v) for k, v in means.items()},
            }
            if sig:
                any_significant = True

            # Plot seasonal subseries
            fig, ax = plt.subplots(figsize=(8, 4))
            x = means.index.astype(int)
            ax.bar(x, means.values, yerr=stds.values, capsize=3, alpha=0.7)
            ax.set_title(
                f"{col} by {grouping_name}"
                f" (p={p_val:.4f}, {'significant' if sig else 'ns'})"
            )
            ax.set_xlabel(grouping_name)
            ax.set_ylabel(f"mean {col}")
            fig.tight_layout()
            pp = tinptool.write_stage_plot(
                path, _STAGE, f"seasonal.{col}.{grouping_name}", fig,
            )
            plt.close(fig)
            plot_paths.append(pp)

        report_cols[col] = col_report

    report: dict[str, Any] = {
        "seasonality_detected": any_significant,
        "columns": report_cols,
        "plot_paths": plot_paths,
    }
    tinptool.write_stage_trace(path, _STAGE, report)
    return report


# ---------------------------------------------------------------------------
# Tool: decompose_series
# ---------------------------------------------------------------------------

def _infer_period(expected_frequency: str | None) -> int:
    """
    Map a frequency label to a seasonal period suitable for STL / seasonal_decompose.

    :param expected_frequency: frequency hint string
    :return: integer period
    """
    if not expected_frequency:
        return 7  # sensible default

    key = expected_frequency.strip().lower()
    if "hour" in key:
        return 24
    if "day" in key:
        return 7
    if "week" in key:
        return 52
    if "month" in key:
        return 12
    if "quarter" in key:
        return 4
    if "min" in key:
        return 60
    return 7


@ltools.tool
def decompose_series(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any],
    target_cols: list[str],
    expected_frequency: str | None,
) -> dict[str, Any]:
    """Decompose the time series into trend, seasonal, and residual components.

    Uses ``statsmodels.tsa.seasonal.STL`` when available, falling back to
    ``seasonal_decompose``.  Also tests the residual for normality via the
    Shapiro-Wilk test (on a sample of up to 5000 points).

    :param path: dataset file path
    :param time_col: datetime column name
    :param winner_formatter: kwargs for ``pd.to_datetime``
    :param target_cols: target column(s) to decompose
    :param expected_frequency: native frequency hint
    :return: decomposition report dict
    """
    df = tinptool.load_dataset(pathlib.Path(path))
    if df.empty:
        _LOG.warning("Empty dataset -- skipping decomposition.")
        return {"decompositions": {}, "plot_paths": []}

    df[time_col] = pd.to_datetime(df[time_col], **(winner_formatter or {}))
    df = df.sort_values(time_col).reset_index(drop=True)

    plot_cols: list[str] = [c for c in (target_cols or []) if c and c in df.columns]
    if not plot_cols:
        _LOG.warning("No target columns for decomposition.")
        return {"decompositions": {}, "plot_paths": []}

    period = _infer_period(expected_frequency)
    decompositions: dict[str, Any] = {}
    plot_paths: list[str] = []

    for col in plot_cols:
        series = df.set_index(time_col)[col].dropna()
        if len(series) < 2 * period:
            _LOG.warning(
                "Series '%s' too short (%d) for period %d; skipping.",
                col, len(series), period,
            )
            decompositions[col] = {"error": "series_too_short", "period": period}
            continue

        # Attempt STL first, fall back to seasonal_decompose
        result = None
        method_used = "unknown"
        try:
            from statsmodels.tsa.seasonal import STL

            stl = STL(series, period=period, robust=True)
            result = stl.fit()
            method_used = "STL"
        except Exception as stl_err:
            _LOG.info("STL failed (%s), trying seasonal_decompose.", stl_err)
            try:
                from statsmodels.tsa.seasonal import seasonal_decompose

                result = seasonal_decompose(
                    series, model="additive", period=period, extrapolate_trend="freq",
                )
                method_used = "seasonal_decompose"
            except Exception as sd_err:
                _LOG.warning("Decomposition failed for '%s': %s", col, sd_err)
                decompositions[col] = {"error": str(sd_err)}
                continue

        # Residual normality test
        resid = result.resid.dropna()
        shapiro_p: float | None = None
        if len(resid) > 3:
            sample = resid.values
            if len(sample) > 5000:
                rng = np.random.default_rng(42)
                sample = rng.choice(sample, size=5000, replace=False)
            try:
                _, shapiro_p = sp_stats.shapiro(sample)
            except Exception:
                shapiro_p = None

        decompositions[col] = {
            "method": method_used,
            "period": period,
            "residual_shapiro_p": shapiro_p,
            "residual_normal": (shapiro_p is not None and shapiro_p >= _ALPHA),
        }

        # Plot: 4-panel (observed, trend, seasonal, residual)
        fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
        components = [
            ("Observed", series),
            ("Trend", result.trend),
            ("Seasonal", result.seasonal),
            ("Residual", result.resid),
        ]
        for ax, (title, data) in zip(axes, components):
            data_clean = data.dropna()
            ax.plot(data_clean.index, data_clean.values, linewidth=0.8)
            ax.set_ylabel(title, fontsize=9)
            ax.tick_params(labelsize=7)
        axes[0].set_title(
            f"Decomposition of {col} ({method_used}, period={period})",
            fontsize=11,
        )
        fig.tight_layout()
        pp = tinptool.write_stage_plot(path, _STAGE, f"decompose.{col}", fig)
        plt.close(fig)
        plot_paths.append(pp)

    report: dict[str, Any] = {
        "decompositions": decompositions,
        "plot_paths": plot_paths,
    }
    tinptool.write_stage_trace(path, f"{_STAGE}_decompose", report)
    return report
