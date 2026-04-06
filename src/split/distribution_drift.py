"""
Distribution-drift detection between chronological splits.

Import as:

import src.split.distribution_drift as sdrift
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

import langchain.tools as ltools
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

import src.tools.input_tools as tinptool

_LOG = logging.getLogger(__name__)

_STAGE = "distribution_drift"

# Thresholds
_PSI_THRESHOLD = 0.2
_KS_ALPHA = 0.05
_PSI_EPSILON = 1e-6
_PSI_BINS = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_and_sort(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any],
) -> pd.DataFrame:
    """Load dataset, parse the time column, and sort chronologically.

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


def _chronological_split(
    df: pd.DataFrame,
    time_col: str,
    train_frac: float,
    val_frac: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a sorted dataframe into train and test by timestamp quantiles.

    :param df: chronologically sorted dataframe
    :param time_col: datetime column name
    :param train_frac: training proportion
    :param val_frac: validation proportion
    :return: (train_df, test_df) tuple
    """
    train_end = df[time_col].quantile(train_frac)
    val_end = df[time_col].quantile(train_frac + val_frac)
    train_df = df[df[time_col] <= train_end].copy()
    test_df = df[df[time_col] > val_end].copy()
    return train_df, test_df


def _compute_psi(
    train_series: pd.Series,
    test_series: pd.Series,
    bins: int = _PSI_BINS,
) -> float:
    """Compute Population Stability Index between two distributions.

    Uses quantile-based binning on the training distribution.  Zero-proportion
    buckets are handled by adding a small epsilon before taking the log.

    :param train_series: training-set values (non-null)
    :param test_series: test-set values (non-null)
    :param bins: number of quantile buckets
    :return: PSI value
    """
    # Build quantile bin edges from train
    quantiles = np.linspace(0, 1, bins + 1)
    bin_edges = np.quantile(train_series, quantiles)
    # Ensure unique edges (handles low-cardinality data)
    bin_edges = np.unique(bin_edges)
    if len(bin_edges) < 2:
        return 0.0

    train_counts = np.histogram(train_series, bins=bin_edges)[0].astype(float)
    test_counts = np.histogram(test_series, bins=bin_edges)[0].astype(float)

    train_pct = train_counts / train_counts.sum()
    test_pct = test_counts / test_counts.sum()

    # Add epsilon to avoid log(0)
    train_pct = np.clip(train_pct, _PSI_EPSILON, None)
    test_pct = np.clip(test_pct, _PSI_EPSILON, None)

    psi = float(np.sum((test_pct - train_pct) * np.log(test_pct / train_pct)))
    return psi


# ---------------------------------------------------------------------------
# Tool: compare_split_distributions
# ---------------------------------------------------------------------------

@ltools.tool
def compare_split_distributions(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any],
    numeric_continuous_cols: list[str],
    train_frac: float = 0.7,
    val_frac: float = 0.15,
) -> dict[str, Any]:
    """Compare feature distributions between chronological train and test splits.

    For each numeric column the tool computes:
    * **KS test** -- two-sample Kolmogorov-Smirnov statistic and p-value.
    * **PSI** -- Population Stability Index using 10 quantile buckets.

    A feature is flagged as *drifted* when PSI > 0.2 **or** the KS test
    p-value < 0.05.  Overlaid histograms (train in blue, test in orange) are
    saved for every flagged feature.

    Edge cases:
    * Datasets with fewer than 10 rows fall back to an 80 / 20 split.
    * All-NaN columns are skipped.

    :param path: dataset file path
    :param time_col: datetime column name
    :param winner_formatter: kwargs for ``pd.to_datetime``
    :param numeric_continuous_cols: numeric continuous columns to compare
    :param train_frac: proportion of data for training (default 0.7)
    :param val_frac: proportion of data for validation (default 0.15)
    :return: dict with per-feature statistics, drift counts, and plot paths
    """
    df = _parse_and_sort(path, time_col, winner_formatter)
    if df.empty:
        _LOG.warning("Empty dataset; skipping distribution drift check.")
        return {
            "features": {},
            "n_drifted": 0,
            "drifted_features": [],
            "plots": [],
        }

    # Handle small datasets
    if len(df) < 10:
        _LOG.warning(
            "Dataset has only %d rows (< 10). Falling back to 80/20 split.",
            len(df),
        )
        train_frac = 0.8
        val_frac = 0.0

    train_df, test_df = _chronological_split(df, time_col, train_frac, val_frac)

    if train_df.empty or test_df.empty:
        _LOG.warning("One of the splits is empty; cannot compare distributions.")
        return {
            "features": {},
            "n_drifted": 0,
            "drifted_features": [],
            "plots": [],
        }

    features: dict[str, dict[str, Any]] = {}
    drifted_features: list[str] = []
    plot_paths: list[str] = []

    for col in numeric_continuous_cols:
        if col not in df.columns:
            continue

        train_vals = train_df[col].dropna()
        test_vals = test_df[col].dropna()

        # Skip all-NaN columns
        if train_vals.empty or test_vals.empty:
            _LOG.info("Skipping column %s: insufficient non-null values.", col)
            continue

        # KS test
        ks_stat, ks_pvalue = stats.ks_2samp(train_vals, test_vals)

        # PSI
        psi = _compute_psi(train_vals, test_vals)

        drifted = psi > _PSI_THRESHOLD or ks_pvalue < _KS_ALPHA

        features[col] = {
            "ks_statistic": round(float(ks_stat), 6),
            "ks_pvalue": round(float(ks_pvalue), 6),
            "psi": round(psi, 6),
            "drifted": drifted,
        }

        if drifted:
            drifted_features.append(col)

            # Plot overlaid histograms
            fig, ax = plt.subplots(figsize=(8, 4))
            combined = pd.concat([train_vals, test_vals])
            bin_edges = np.histogram_bin_edges(combined, bins=30)
            ax.hist(
                train_vals, bins=bin_edges, alpha=0.5,
                color="blue", label="Train", density=True,
            )
            ax.hist(
                test_vals, bins=bin_edges, alpha=0.5,
                color="orange", label="Test", density=True,
            )
            ax.set_title(
                f"{col} -- drift detected "
                f"(PSI={psi:.3f}, KS p={ks_pvalue:.3e})"
            )
            ax.set_xlabel(col)
            ax.set_ylabel("Density")
            ax.legend()
            fig.tight_layout()
            pp = tinptool.write_stage_plot(path, _STAGE, f"drift.{col}", fig)
            plt.close(fig)
            plot_paths.append(pp)

    payload: dict[str, Any] = {
        "features": features,
        "n_drifted": len(drifted_features),
        "drifted_features": drifted_features,
        "plots": plot_paths,
    }

    tinptool.write_stage_trace(path, _STAGE, payload)
    _LOG.info(
        "Distribution drift check complete: %d / %d features drifted.",
        len(drifted_features),
        len(features),
    )
    return payload
