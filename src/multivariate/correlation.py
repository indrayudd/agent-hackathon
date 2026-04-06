"""
Import as:

import src.multivariate.correlation as scorr
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
_STAGE = "correlation"


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


@ltools.tool
def compute_correlations(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any],
    numeric_continuous_cols: list[str],
) -> dict[str, Any]:
    """Compute Pearson and Spearman correlation matrices and detect redundancy.

    Analyses include:
    * Full Pearson and Spearman correlation matrices.
    * Redundant pair detection (|Pearson r| > 0.95).
    * Windowed correlation stability: the data is split into three equal time
      windows and Pearson correlation is computed per window. Pairs whose
      correlation sign flips across windows are flagged.
    * A heatmap of the Pearson correlation matrix.

    :param path: dataset file path
    :param time_col: datetime column name
    :param winner_formatter: kwargs for ``pd.to_datetime``
    :param numeric_continuous_cols: continuous numeric columns to correlate
    :return: correlation matrices, redundant pairs, sign-flip pairs, and plots
    """
    if len(numeric_continuous_cols) < 2:
        return {"error": "Need at least 2 numeric columns for correlation analysis."}

    df = _parse_and_sort(path, time_col, winner_formatter)
    num_df = df[numeric_continuous_cols].dropna()

    if len(num_df) < 3:
        return {"error": "Too few non-NaN rows for correlation analysis."}

    # --- Pearson and Spearman ---
    pearson = num_df.corr(method="pearson")
    spearman = num_df.corr(method="spearman")

    # --- Redundant pairs ---
    redundant_pairs: list[dict[str, Any]] = []
    cols = pearson.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = pearson.iloc[i, j]
            if abs(r) > 0.95:
                redundant_pairs.append({
                    "col1": cols[i],
                    "col2": cols[j],
                    "pearson_r": float(r),
                })

    # --- Windowed correlation ---
    df_sorted = df.sort_values(time_col).reset_index(drop=True)
    n = len(df_sorted)
    window_size = max(1, n // 3)
    windows = [
        df_sorted.iloc[:window_size],
        df_sorted.iloc[window_size:2 * window_size],
        df_sorted.iloc[2 * window_size:],
    ]

    window_corrs: list[pd.DataFrame] = []
    for w in windows:
        w_num = w[numeric_continuous_cols].dropna()
        if len(w_num) >= 3:
            window_corrs.append(w_num.corr(method="pearson"))
        else:
            window_corrs.append(pd.DataFrame(
                np.nan, index=numeric_continuous_cols, columns=numeric_continuous_cols,
            ))

    sign_flip_pairs: list[dict[str, Any]] = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            w_vals = [
                float(wc.loc[cols[i], cols[j]])
                if cols[i] in wc.index and cols[j] in wc.columns
                else np.nan
                for wc in window_corrs
            ]
            valid = [v for v in w_vals if not np.isnan(v)]
            if len(valid) >= 2:
                signs = [np.sign(v) for v in valid if v != 0.0]
                if len(set(signs)) > 1:
                    sign_flip_pairs.append({
                        "col1": cols[i],
                        "col2": cols[j],
                        "window_correlations": w_vals,
                    })

    # --- Heatmap ---
    plots: list[str] = []
    n_cols = len(cols)
    fig, ax = plt.subplots(figsize=(max(6, n_cols * 0.6), max(5, n_cols * 0.5)))

    try:
        import seaborn as sns
        sns.heatmap(
            pearson, annot=(n_cols <= 15), fmt=".2f" if n_cols <= 15 else "",
            cmap="RdBu_r", center=0, vmin=-1, vmax=1, ax=ax,
        )
    except ImportError:
        im = ax.imshow(pearson.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
        ax.set_xticks(range(n_cols))
        ax.set_yticks(range(n_cols))
        ax.set_xticklabels(cols, rotation=45, ha="right")
        ax.set_yticklabels(cols)
        plt.colorbar(im, ax=ax)
        if n_cols <= 15:
            for ii in range(n_cols):
                for jj in range(n_cols):
                    ax.text(
                        jj, ii, f"{pearson.values[ii, jj]:.2f}",
                        ha="center", va="center", fontsize=7,
                    )

    ax.set_title("Pearson Correlation Matrix")
    plt.tight_layout()
    p = tinptool.write_stage_plot(path, _STAGE, "pearson_heatmap", fig)
    plt.close(fig)
    plots.append(p)

    output: dict[str, Any] = {
        "pearson_matrix": pearson.to_dict(),
        "spearman_matrix": spearman.to_dict(),
        "redundant_pairs": redundant_pairs,
        "sign_flip_pairs": sign_flip_pairs,
        "plots": plots,
    }

    tinptool.write_stage_trace(path, _STAGE, output)
    return output


@ltools.tool
def compute_mutual_information(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any],
    numeric_continuous_cols: list[str],
    target_cols: list[str],
) -> dict[str, Any]:
    """Compute mutual information between targets and numeric features.

    For each target column the function computes MI scores with every other
    numeric column using ``sklearn.feature_selection.mutual_info_regression``.
    MI rankings are compared with Pearson correlation rankings and features
    with a rank difference greater than 3 are flagged as discrepant.

    :param path: dataset file path
    :param time_col: datetime column name
    :param winner_formatter: kwargs for ``pd.to_datetime``
    :param numeric_continuous_cols: continuous numeric columns
    :param target_cols: target column(s) to analyse
    :return: MI scores, Pearson comparisons, and discrepancy flags per target
    """
    from sklearn.feature_selection import mutual_info_regression

    df = _parse_and_sort(path, time_col, winner_formatter)

    results: dict[str, Any] = {}
    all_discrepant: list[str] = []

    for target in target_cols:
        if target not in df.columns:
            continue

        features = [c for c in numeric_continuous_cols if c != target and c in df.columns]
        if not features:
            continue

        sub = df[[target] + features].dropna()
        if len(sub) < 10:
            continue

        X = sub[features].values
        y = sub[target].values

        mi_scores = mutual_info_regression(X, y, random_state=42)

        # Pearson correlations
        pearson_r = sub[features].corrwith(sub[target]).values

        # Build rankings
        mi_order = np.argsort(-mi_scores)
        mi_ranks = np.empty_like(mi_order)
        mi_ranks[mi_order] = np.arange(len(features))

        pearson_abs = np.abs(pearson_r)
        pearson_order = np.argsort(-pearson_abs)
        pearson_ranks = np.empty_like(pearson_order)
        pearson_ranks[pearson_order] = np.arange(len(features))

        target_result: dict[str, Any] = {}
        for idx, feat in enumerate(features):
            rank_diff = abs(int(mi_ranks[idx]) - int(pearson_ranks[idx]))
            is_discrepant = rank_diff > 3
            if is_discrepant:
                all_discrepant.append(feat)
            target_result[feat] = {
                "mi_score": float(mi_scores[idx]),
                "pearson_r": float(pearson_r[idx]),
                "mi_rank": int(mi_ranks[idx]),
                "pearson_rank": int(pearson_ranks[idx]),
                "discrepancy": is_discrepant,
            }

        results[target] = target_result

    output: dict[str, Any] = {
        **results,
        "discrepant_features": list(set(all_discrepant)),
    }

    tinptool.write_stage_trace(path, "mutual_information", output)
    return output
