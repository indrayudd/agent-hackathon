"""
Import as:

import src.multivariate.dimensionality as sdim
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

import langchain.tools as ltools
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

import src.tools.input_tools as tinptool

_LOG = logging.getLogger(__name__)
_STAGE = "dimensionality"


@ltools.tool
def run_dimensionality_scan(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any],
    numeric_continuous_cols: list[str],
) -> dict[str, Any]:
    """Run PCA-based dimensionality scan on numeric columns.

    Fits PCA on the available numeric continuous columns (after dropping NaN
    rows) and reports the number of components needed to explain 90 % and 95 %
    of total variance.  A scree plot with per-component explained variance bars
    and a cumulative variance line is saved as a trace plot.

    :param path: dataset file path
    :param time_col: datetime column name
    :param winner_formatter: kwargs for ``pd.to_datetime``
    :param numeric_continuous_cols: continuous numeric columns for PCA
    :return: variance diagnostics and plot paths
    """
    df = tinptool.load_dataset(pathlib.Path(path))
    df[time_col] = pd.to_datetime(df[time_col], **winner_formatter)

    valid_cols = [c for c in numeric_continuous_cols if c in df.columns]
    if len(valid_cols) < 3:
        return {
            "message": (
                f"Only {len(valid_cols)} numeric column(s) available; "
                "need at least 3 for PCA. Skipping dimensionality scan."
            ),
        }

    num_df = df[valid_cols].dropna()
    if len(num_df) < 3:
        return {"error": "Too few non-NaN rows for PCA."}

    # Standardise before PCA
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    X = scaler.fit_transform(num_df.values)

    n_components = min(len(valid_cols), len(num_df))
    pca = PCA(n_components=n_components)
    pca.fit(X)

    explained = pca.explained_variance_ratio_
    cumulative = np.cumsum(explained)

    n_90 = int(np.searchsorted(cumulative, 0.90) + 1)
    n_95 = int(np.searchsorted(cumulative, 0.95) + 1)
    top3_var = float(cumulative[min(2, len(cumulative) - 1)])

    # --- Scree plot ---
    plots: list[str] = []
    fig, ax1 = plt.subplots(figsize=(max(6, n_components * 0.4), 5))
    indices = np.arange(1, n_components + 1)

    ax1.bar(indices, explained, color="steelblue", alpha=0.8, label="Individual")
    ax1.set_xlabel("Principal Component")
    ax1.set_ylabel("Explained Variance Ratio")
    ax1.set_title("PCA Scree Plot")

    ax2 = ax1.twinx()
    ax2.plot(indices, cumulative, color="darkorange", marker="o", markersize=4, label="Cumulative")
    ax2.set_ylabel("Cumulative Variance")
    ax2.axhline(0.90, linestyle="--", color="red", linewidth=0.8, alpha=0.7)
    ax2.axhline(0.95, linestyle="--", color="darkred", linewidth=0.8, alpha=0.7)

    # Combine legends
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="center right")

    plt.tight_layout()
    p = tinptool.write_stage_plot(path, _STAGE, "scree_plot", fig)
    plt.close(fig)
    plots.append(p)

    output: dict[str, Any] = {
        "n_components_90": n_90,
        "n_components_95": n_95,
        "explained_variance_ratios": [float(v) for v in explained],
        "total_variance_explained_by_top3": top3_var,
        "plots": plots,
    }

    tinptool.write_stage_trace(path, _STAGE, output)
    return output
