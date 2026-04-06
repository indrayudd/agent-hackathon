"""
Import as:

import src.multivariate.lag_analysis as slag
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
_STAGE = "lag_analysis"
_MAX_LAG_CAP = 40
_CROSS_CORR_RANGE = 20


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


def _cross_correlation(x: np.ndarray, y: np.ndarray, max_lag: int) -> dict[int, float]:
    """Compute normalised cross-correlation at integer lags.

    :param x: first series (reference)
    :param y: second series (shifted)
    :param max_lag: maximum lag magnitude
    :return: mapping from lag to correlation value
    """
    n = len(x)
    x = x - np.nanmean(x)
    y = y - np.nanmean(y)
    sx = np.nanstd(x)
    sy = np.nanstd(y)
    if sx == 0 or sy == 0:
        return {}
    result: dict[int, float] = {}
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            x_slice = x[:n - lag] if lag > 0 else x
            y_slice = y[lag:] if lag > 0 else y
        else:
            x_slice = x[-lag:]
            y_slice = y[:n + lag]
        if len(x_slice) < 3:
            continue
        r = float(np.nanmean(x_slice * y_slice) / (sx * sy))
        result[lag] = r
    return result


@ltools.tool
def compute_lag_relationships(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any],
    target_cols: list[str],
    numeric_continuous_cols: list[str],
    expected_frequency: str,
) -> dict[str, Any]:
    """Analyse autocorrelation, partial autocorrelation, and cross-correlations.

    For each target column this function computes:
    * ACF and PACF (via statsmodels when available, otherwise skipped with a
      graceful message).
    * Cross-correlation with every other numeric covariate at lags -20 to +20.

    Significant ACF/PACF lags are those outside the +/-1.96/sqrt(n) band.

    :param path: dataset file path
    :param time_col: datetime column name
    :param winner_formatter: kwargs for ``pd.to_datetime``
    :param target_cols: target column(s) to analyse
    :param numeric_continuous_cols: continuous numeric columns
    :param expected_frequency: expected sampling frequency string
    :return: ACF/PACF significant lags, cross-correlation best lags, and plots
    """
    df = _parse_and_sort(path, time_col, winner_formatter)
    plots: list[str] = []
    results: dict[str, Any] = {}

    # Check for statsmodels availability
    try:
        from statsmodels.tsa.stattools import acf as sm_acf, pacf as sm_pacf
        has_statsmodels = True
    except ImportError:
        has_statsmodels = False
        _LOG.warning("statsmodels not installed; ACF/PACF computation skipped.")

    for target in target_cols:
        if target not in df.columns:
            continue

        series = df[target].dropna()
        n = len(series)
        if n < 10:
            results[target] = {"error": f"Too few observations ({n}) for lag analysis."}
            continue

        max_lag = min(_MAX_LAG_CAP, n // 4)
        threshold = 1.96 / np.sqrt(n)
        target_result: dict[str, Any] = {}

        # --- ACF / PACF ---
        if has_statsmodels:
            acf_vals = sm_acf(series.values, nlags=max_lag, fft=True)
            try:
                pacf_vals = sm_pacf(series.values, nlags=max_lag)
            except Exception:
                pacf_vals = np.full(max_lag + 1, np.nan)

            acf_sig = [
                int(lag) for lag in range(1, len(acf_vals))
                if abs(acf_vals[lag]) > threshold
            ]
            pacf_sig = [
                int(lag) for lag in range(1, len(pacf_vals))
                if not np.isnan(pacf_vals[lag]) and abs(pacf_vals[lag]) > threshold
            ]

            target_result["acf_significant_lags"] = acf_sig
            target_result["pacf_significant_lags"] = pacf_sig

            # Plot ACF
            fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
            lags = np.arange(len(acf_vals))
            axes[0].bar(lags, acf_vals, width=0.4, color="steelblue")
            axes[0].axhline(threshold, linestyle="--", color="red", linewidth=0.8)
            axes[0].axhline(-threshold, linestyle="--", color="red", linewidth=0.8)
            axes[0].set_title(f"ACF — {target}")
            axes[0].set_ylabel("ACF")

            pacf_lags = np.arange(len(pacf_vals))
            axes[1].bar(pacf_lags, pacf_vals, width=0.4, color="darkorange")
            axes[1].axhline(threshold, linestyle="--", color="red", linewidth=0.8)
            axes[1].axhline(-threshold, linestyle="--", color="red", linewidth=0.8)
            axes[1].set_title(f"PACF — {target}")
            axes[1].set_xlabel("Lag")
            axes[1].set_ylabel("PACF")

            plt.tight_layout()
            p = tinptool.write_stage_plot(path, _STAGE, f"acf_pacf_{target}", fig)
            plt.close(fig)
            plots.append(p)
        else:
            target_result["acf_significant_lags"] = []
            target_result["pacf_significant_lags"] = []
            target_result["statsmodels_warning"] = (
                "statsmodels is not installed; ACF/PACF could not be computed."
            )

        # --- Cross-correlations ---
        covariates = [
            c for c in numeric_continuous_cols
            if c != target and c in df.columns
        ]
        cross_results: dict[str, Any] = {}

        for cov in covariates:
            paired = df[[target, cov]].dropna()
            if len(paired) < 10:
                continue

            x = paired[target].values.astype(float)
            y = paired[cov].values.astype(float)
            cc = _cross_correlation(x, y, _CROSS_CORR_RANGE)
            if not cc:
                continue

            best_lag = max(cc, key=lambda k: abs(cc[k]))
            best_corr = cc[best_lag]
            cross_results[cov] = {
                "best_lag": int(best_lag),
                "best_correlation": float(best_corr),
                "direction": "positive" if best_corr > 0 else "negative",
            }

        target_result["cross_correlations"] = cross_results
        results[target] = target_result

    output: dict[str, Any] = {
        **results,
        "plots": plots,
    }

    tinptool.write_stage_trace(path, _STAGE, output)
    return output
