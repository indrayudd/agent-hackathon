"""
Phase 10 - Baseline feature engineering (calendar + lags + rolling).

Import as:

    from src.model_readiness.baseline_features import run_baseline_features
"""

import json
import logging
import pathlib
import re
from typing import Any

import numpy as np
import pandas as pd

from src.tools.input_tools import _trace_root, load_dataset

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# frequency helpers
# ------------------------------------------------------------------

_FREQ_TO_PERIODS: dict[str, int] = {
    # maps expected_frequency string to approximate periods-per-day
    # used to scale lag / rolling window sizes
}


def _freq_periods_per_day(freq: str | None) -> float:
    """Estimate how many observations fall in one day for the given freq."""
    if not freq:
        return 1.0
    freq = freq.strip().lower()
    # parse pandas offset-style strings like '1h', '15min', '1D'
    match = re.match(r"(\d*)\s*(min|t|h|d|w|m|ms|s)", freq)
    if not match:
        return 1.0
    num = int(match.group(1)) if match.group(1) else 1
    unit = match.group(2)
    minutes_map = {"min": 1, "t": 1, "s": 1 / 60, "ms": 1 / 60_000, "h": 60, "d": 1440, "w": 10080, "m": 43200}
    mins_per_obs = num * minutes_map.get(unit, 1440)
    return 1440 / mins_per_obs if mins_per_obs > 0 else 1.0


def _lag_windows(ppd: float) -> list[int]:
    """Return lag sizes (in observation steps) for 1-day, 7-day, 14-day."""
    base = max(1, round(ppd))
    return [base, base * 7, base * 14]


def _rolling_windows(ppd: float) -> dict[str, int]:
    """Return rolling window sizes for 7-day and 30-day."""
    base = max(1, round(ppd))
    return {
        "rolling_mean_7": base * 7,
        "rolling_std_7": base * 7,
        "rolling_mean_30": base * 30,
    }


# ------------------------------------------------------------------
# main
# ------------------------------------------------------------------

def run_baseline_features(state: dict) -> dict:
    """
    Generate calendar, lag, and rolling features for the dataset.

    Lag features are shifted by 1 extra step to avoid off-by-one
    leakage (value at time t uses only data from t-1 or earlier).

    :param state: pipeline composite state dict
    :return: state update dict
    """
    done: list[str] = list(state.get("done", []))

    # ----- resolve dataset -----
    ds_path = state.get("standardized_dataset_path") or state.get("quality_dataset_path") or state.get("path")
    if not ds_path:
        return {
            "baseline_features": [],
            "feature_dataset_path": "",
            "done": done + ["baseline_features"],
        }

    df = load_dataset(pathlib.Path(ds_path))

    # ----- parse time column as index -----
    time_col = state.get("time_col")
    if not time_col or time_col not in df.columns:
        # fallback: first temporal column
        temporal_cols = state.get("temporal_cols", [])
        time_col = temporal_cols[0] if temporal_cols else None

    if time_col and time_col in df.columns:
        df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
        df = df.sort_values(time_col).reset_index(drop=True)
        dt_index = df[time_col]
    else:
        dt_index = None

    # ----- identify numeric columns for lag/rolling -----
    target_cols: list[str] = list(state.get("target_cols", []))
    continuous_cols: list[str] = list(state.get("numeric_continuous_cols", []))
    numeric_cols = list(dict.fromkeys(target_cols + continuous_cols))
    if not numeric_cols:
        numeric_cols = [c for c in df.select_dtypes(include=[np.number]).columns if c != time_col]

    new_feature_names: list[str] = []
    expected_freq = state.get("expected_frequency")
    ppd = _freq_periods_per_day(expected_freq)

    # ----- calendar features -----
    if dt_index is not None:
        calendar_map = {
            "hour": dt_index.dt.hour,
            "day_of_week": dt_index.dt.dayofweek,
            "month": dt_index.dt.month,
            "day_of_month": dt_index.dt.day,
            "is_weekend": dt_index.dt.dayofweek.isin([5, 6]).astype(int),
        }
        for feat_name, feat_series in calendar_map.items():
            df[feat_name] = feat_series.values
            new_feature_names.append(feat_name)

    # ----- lag features -----
    lag_sizes = _lag_windows(ppd)
    lag_labels = ["lag_1", "lag_7", "lag_14"]

    for col in numeric_cols:
        if col not in df.columns:
            continue
        for lag_size, label in zip(lag_sizes, lag_labels):
            feat_name = f"{col}_{label}"
            # shift by lag_size + 1 to guarantee no same-timestep leakage
            df[feat_name] = df[col].shift(lag_size + 1)
            new_feature_names.append(feat_name)

    # ----- rolling features -----
    rolling_specs = _rolling_windows(ppd)

    for col in numeric_cols:
        if col not in df.columns:
            continue
        for feat_name_suffix, window in rolling_specs.items():
            feat_name = f"{col}_{feat_name_suffix}"
            if "std" in feat_name_suffix:
                rolling_vals = df[col].shift(1).rolling(window=window, min_periods=1).std()
            else:
                rolling_vals = df[col].shift(1).rolling(window=window, min_periods=1).mean()
            df[feat_name] = rolling_vals
            new_feature_names.append(feat_name)

    # ----- save -----
    dataset_name = pathlib.Path(ds_path).stem
    out_path = _trace_root() / f"{dataset_name}.features.csv"
    df.to_csv(out_path, index=False)
    logger.info("Feature-engineered dataset saved to %s", out_path)

    # ----- trace -----
    trace = {
        "n_original_cols": len(df.columns) - len(new_feature_names),
        "n_new_features": len(new_feature_names),
        "new_features": new_feature_names,
        "feature_dataset_path": str(out_path),
        "expected_frequency": expected_freq,
        "periods_per_day": ppd,
    }
    trace_path = _trace_root() / "baseline_features_trace.json"
    trace_path.write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")

    return {
        "baseline_features": new_feature_names,
        "feature_dataset_path": str(out_path),
        "done": done + ["baseline_features"],
    }
