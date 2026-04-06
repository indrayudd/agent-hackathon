"""
Phase 10 - Feature importance screening via LightGBM + permutation importance.

Import as:

    from src.model_readiness.feature_importance import run_feature_importance
"""

import json
import logging
import pathlib
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.tools.input_tools import _trace_root, load_dataset

logger = logging.getLogger(__name__)

_TOP_K = 20
_MIN_FEATURES_GATE = 10


# ------------------------------------------------------------------
# main
# ------------------------------------------------------------------

def run_feature_importance(state: dict) -> dict:
    """
    Train a LightGBM model and compute permutation importance.

    Gate: skips entirely when total feature count <= 10.

    :param state: pipeline composite state dict
    :return: state update dict
    """
    done: list[str] = list(state.get("done", []))

    # ----- resolve dataset -----
    ds_path = state.get("feature_dataset_path") or state.get("quality_dataset_path") or state.get("path")
    if not ds_path:
        return {
            "feature_importance_report": {"error": "No dataset path found", "rankings": []},
            "done": done + ["feature_importance"],
        }

    df = load_dataset(pathlib.Path(ds_path))

    # ----- identify target -----
    target_cols: list[str] = list(state.get("target_cols", []))
    continuous_cols: list[str] = list(state.get("numeric_continuous_cols", []))
    target_col: str | None = None
    if target_cols:
        target_col = target_cols[0]
    elif continuous_cols:
        target_col = continuous_cols[0]
    else:
        # fallback: first numeric column
        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        target_col = num_cols[0] if num_cols else None

    if target_col is None or target_col not in df.columns:
        return {
            "feature_importance_report": {"error": "No suitable target column found", "rankings": []},
            "done": done + ["feature_importance"],
        }

    # ----- prepare X, y -----
    time_col = state.get("time_col")
    exclude = {target_col}
    if time_col:
        exclude.add(time_col)
    # also exclude entity columns
    for ec in state.get("secondary_keys", []):
        exclude.add(ec)

    feature_cols = [c for c in df.columns if c not in exclude and pd.api.types.is_numeric_dtype(df[c])]

    # ----- gate: skip if too few features -----
    if len(feature_cols) <= _MIN_FEATURES_GATE:
        return {
            "feature_importance_report": {
                "rankings": [],
                "skipped": True,
                "reason": f"Only {len(feature_cols)} features (<= {_MIN_FEATURES_GATE}); screening not needed.",
                "target_used": target_col,
                "n_features_screened": len(feature_cols),
            },
            "done": done + ["feature_importance"],
        }

    # ----- drop rows where target is NaN, fill feature NaNs -----
    mask = df[target_col].notna()
    df = df.loc[mask].copy()
    if len(df) < 50:
        return {
            "feature_importance_report": {
                "error": f"Too few rows ({len(df)}) after dropping NaN target",
                "rankings": [],
            },
            "done": done + ["feature_importance"],
        }

    y = df[target_col].values
    X = df[feature_cols].fillna(0)

    # ----- chronological 80/20 split -----
    split_dates = state.get("split_dates", {})
    train_end = split_dates.get("train_end")

    if train_end and time_col and time_col in df.columns:
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
        train_mask = df[time_col] <= pd.Timestamp(train_end)
        X_train, X_test = X.loc[train_mask], X.loc[~train_mask]
        y_train, y_test = y[train_mask.values], y[~train_mask.values]
    else:
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

    if len(X_test) < 10 or len(X_train) < 10:
        return {
            "feature_importance_report": {
                "error": "Train or test split too small for importance screening",
                "rankings": [],
            },
            "done": done + ["feature_importance"],
        }

    # ----- train LightGBM -----
    try:
        import lightgbm as lgb
    except ImportError:
        return {
            "feature_importance_report": {"error": "lightgbm not installed", "rankings": []},
            "done": done + ["feature_importance"],
        }

    model = lgb.LGBMRegressor(
        n_estimators=100,
        max_depth=5,
        random_state=42,
        verbosity=-1,
    )
    model.fit(X_train, y_train)

    # ----- permutation importance -----
    from sklearn.inspection import permutation_importance

    perm_result = permutation_importance(
        model, X_test, y_test,
        n_repeats=10,
        random_state=42,
    )

    importances = perm_result.importances_mean
    indices = np.argsort(importances)[::-1]

    rankings: list[dict] = []
    for rank, idx in enumerate(indices, start=1):
        rankings.append({
            "rank": rank,
            "feature": feature_cols[idx],
            "importance_mean": float(importances[idx]),
            "importance_std": float(perm_result.importances_std[idx]),
        })

    # ----- plot top-K -----
    top_k = rankings[:_TOP_K]
    fig, ax = plt.subplots(figsize=(8, max(4, len(top_k) * 0.35)))
    names = [r["feature"] for r in reversed(top_k)]
    vals = [r["importance_mean"] for r in reversed(top_k)]
    stds = [r["importance_std"] for r in reversed(top_k)]
    ax.barh(names, vals, xerr=stds, color="#4c72b0", edgecolor="white")
    ax.set_xlabel("Permutation Importance (decrease in score)")
    ax.set_title(f"Top-{len(top_k)} Feature Importance (target={target_col})")
    plt.tight_layout()

    plot_path = _trace_root() / "feature_importance.png"
    fig.savefig(plot_path, dpi=120)
    plt.close(fig)
    logger.info("Feature importance plot saved to %s", plot_path)

    # ----- trace -----
    report = {
        "rankings": rankings,
        "plot_path": str(plot_path),
        "target_used": target_col,
        "n_features_screened": len(feature_cols),
    }
    trace_path = _trace_root() / "feature_importance_report.json"
    trace_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    return {
        "feature_importance_report": report,
        "done": done + ["feature_importance"],
    }
