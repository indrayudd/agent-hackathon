"""
Temporal train / validation / test splitting tool.

Import as:

import src.split.temporal_split as ssplit
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

import langchain.tools as ltools
import pandas as pd

import src.tools.input_tools as tinptool

_LOG = logging.getLogger(__name__)

_STAGE = "split"


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


# ---------------------------------------------------------------------------
# Tool: apply_temporal_split
# ---------------------------------------------------------------------------

@ltools.tool
def apply_temporal_split(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any],
    secondary_keys: list[str],
    train_frac: float = 0.7,
    val_frac: float = 0.15,
) -> dict[str, Any]:
    """Apply a chronological train / validation / test split to a time-series dataset.

    The split is performed globally (same cutoff timestamps for all entities in
    panel data) to avoid temporal leakage.  Each row receives a ``split`` column
    with values ``"train"``, ``"val"``, or ``"test"``.

    Edge cases:
    * If the dataset has fewer than 10 rows the fractions fall back to an
      80 / 20 train / test split (no validation set).

    :param path: dataset file path
    :param time_col: datetime column name
    :param winner_formatter: kwargs for ``pd.to_datetime``
    :param secondary_keys: entity / group key columns (panel data)
    :param train_frac: proportion of data for training (default 0.7)
    :param val_frac: proportion of data for validation (default 0.15)
    :return: dict with split dates, sizes, and saved dataset paths
    """
    df = _parse_and_sort(path, time_col, winner_formatter)
    if df.empty:
        _LOG.warning("Empty dataset; nothing to split.")
        return {
            "split_dates": {"train_end": None, "val_end": None},
            "split_sizes": {"train": 0, "val": 0, "test": 0},
            "train_path": None,
            "val_path": None,
            "test_path": None,
        }

    # Edge case: very small dataset
    if len(df) < 10:
        _LOG.warning(
            "Dataset has only %d rows (< 10). Falling back to 80/20 "
            "train/test split with no validation set.",
            len(df),
        )
        train_frac = 0.8
        val_frac = 0.0

    # Compute cutoff timestamps using quantiles on the time column
    train_end = df[time_col].quantile(train_frac)
    val_end = df[time_col].quantile(train_frac + val_frac)

    # Assign split labels
    conditions = [
        df[time_col] <= train_end,
        (df[time_col] > train_end) & (df[time_col] <= val_end),
    ]
    choices = ["train", "val"]
    df["split"] = "test"  # default
    for cond, label in zip(conditions, choices):
        df.loc[cond, "split"] = label

    train_df = df[df["split"] == "train"].copy()
    val_df = df[df["split"] == "val"].copy()
    test_df = df[df["split"] == "test"].copy()

    # Persist split datasets
    train_path = tinptool.write_stage_dataset(path, "split_train", train_df)
    val_path = tinptool.write_stage_dataset(path, "split_val", val_df) if len(val_df) > 0 else None
    test_path = tinptool.write_stage_dataset(path, "split_test", test_df)

    payload: dict[str, Any] = {
        "split_dates": {
            "train_end": str(train_end),
            "val_end": str(val_end) if val_frac > 0 else None,
        },
        "split_sizes": {
            "train": len(train_df),
            "val": len(val_df),
            "test": len(test_df),
        },
        "train_path": train_path,
        "val_path": val_path,
        "test_path": test_path,
    }

    tinptool.write_stage_trace(path, _STAGE, payload)

    _LOG.info(
        "Temporal split complete: train=%d, val=%d, test=%d",
        len(train_df),
        len(val_df),
        len(test_df),
    )
    return payload
