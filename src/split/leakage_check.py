"""
Data-leakage validation tool.

Import as:

import src.split.leakage_check as sleak
"""

from __future__ import annotations

import logging
import pathlib
import re
from typing import Any

import langchain.tools as ltools
import numpy as np
import pandas as pd

import src.tools.input_tools as tinptool

_LOG = logging.getLogger(__name__)

_STAGE = "leakage_check"

# Regex patterns that hint at future-looking features
_FUTURE_PATTERNS = re.compile(
    r"(future|lead|next|fwd|forward|lookahead)", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_corr(s1: pd.Series, s2: pd.Series) -> float | None:
    """Compute Pearson correlation, returning None when it cannot be computed."""
    try:
        valid = s1.notna() & s2.notna()
        if valid.sum() < 3:
            return None
        r = s1[valid].corr(s2[valid])
        if pd.isna(r):
            return None
        return float(r)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tool: validate_no_leakage
# ---------------------------------------------------------------------------

@ltools.tool
def validate_no_leakage(
    path: str,
    time_col: str,
    winner_formatter: dict[str, Any],
    target_cols: list[str],
    numeric_continuous_cols: list[str],
) -> dict[str, Any]:
    """Validate that the dataset is free from common forms of data leakage.

    Three checks are performed:

    1. **Target leakage** -- any numeric column with |r| > 0.99 against a
       target is flagged as a suspiciously perfect predictor.
    2. **Temporal leakage** -- columns whose name matches future-looking
       patterns (``future``, ``lead``, ``next``, etc.) are flagged.  Also
       checks whether any column is perfectly correlated with a shifted
       (lag-1) target.
    3. **Scaling leakage** -- a reminder that scaling / normalisation should
       be fit on the training set only.

    :param path: dataset file path
    :param time_col: datetime column name
    :param winner_formatter: kwargs for ``pd.to_datetime``
    :param target_cols: target column(s) to check against
    :param numeric_continuous_cols: numeric continuous columns available
    :return: dict with a list of checks and an overall status
    """
    df = tinptool.load_dataset(pathlib.Path(path))
    if df.empty:
        _LOG.warning("Empty dataset; skipping leakage checks.")
        return {"checks": [], "overall": "pass"}

    df[time_col] = pd.to_datetime(df[time_col], **(winner_formatter or {}))
    df = df.sort_values(time_col).reset_index(drop=True)

    # Resolve valid target columns
    valid_targets = [c for c in (target_cols or []) if c and c in df.columns]
    if not valid_targets:
        _LOG.warning("No valid target columns found; leakage checks limited.")

    checks: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Check 1 -- Target leakage (perfect predictors)
    # ------------------------------------------------------------------
    target_leakage_flags: list[str] = []
    for tcol in valid_targets:
        for col in numeric_continuous_cols:
            if col == tcol or col not in df.columns:
                continue
            # Skip all-NaN columns
            if df[col].dropna().empty:
                continue
            r = _safe_corr(df[col], df[tcol])
            if r is not None and abs(r) > 0.99:
                target_leakage_flags.append(
                    f"{col} vs {tcol}: r={r:.4f}"
                )

    if target_leakage_flags:
        checks.append({
            "name": "target_leakage",
            "status": "fail",
            "details": (
                "Suspiciously perfect predictors found (|r| > 0.99): "
                + "; ".join(target_leakage_flags)
            ),
        })
    else:
        checks.append({
            "name": "target_leakage",
            "status": "pass",
            "details": "No numeric column has |r| > 0.99 with any target.",
        })

    # ------------------------------------------------------------------
    # Check 2 -- Temporal leakage
    # ------------------------------------------------------------------
    # 2a: Column-name heuristic
    name_flags = [c for c in df.columns if _FUTURE_PATTERNS.search(c)]

    # 2b: Shifted-target correlation
    shifted_flags: list[str] = []
    for tcol in valid_targets:
        if tcol not in df.columns:
            continue
        shifted_target = df[tcol].shift(-1)
        for col in numeric_continuous_cols:
            if col == tcol or col not in df.columns:
                continue
            if df[col].dropna().empty:
                continue
            r = _safe_corr(df[col], shifted_target)
            if r is not None and abs(r) > 0.99:
                shifted_flags.append(
                    f"{col} vs shifted({tcol}): r={r:.4f}"
                )

    temporal_issues = name_flags + shifted_flags
    if temporal_issues:
        details_parts: list[str] = []
        if name_flags:
            details_parts.append(
                f"Columns with future-looking names: {name_flags}"
            )
        if shifted_flags:
            details_parts.append(
                "Columns perfectly correlated with shifted target: "
                + "; ".join(shifted_flags)
            )
        checks.append({
            "name": "temporal_leakage",
            "status": "warn" if (name_flags and not shifted_flags) else "fail",
            "details": ". ".join(details_parts),
        })
    else:
        checks.append({
            "name": "temporal_leakage",
            "status": "pass",
            "details": (
                "No future-looking column names detected and no columns "
                "are perfectly correlated with a shifted target."
            ),
        })

    # ------------------------------------------------------------------
    # Check 3 -- Scaling leakage (advisory)
    # ------------------------------------------------------------------
    checks.append({
        "name": "scaling_leakage",
        "status": "pass",
        "details": (
            "Reminder: any scaling, normalisation, or encoding must be fit "
            "on the training split only and then applied to validation / test "
            "splits to avoid information leakage."
        ),
    })

    # ------------------------------------------------------------------
    # Overall status
    # ------------------------------------------------------------------
    statuses = [c["status"] for c in checks]
    if "fail" in statuses:
        overall = "fail"
    elif "warn" in statuses:
        overall = "warn"
    else:
        overall = "pass"

    payload: dict[str, Any] = {
        "checks": checks,
        "overall": overall,
    }

    tinptool.write_stage_trace(path, _STAGE, payload)
    _LOG.info("Leakage validation complete: overall=%s", overall)
    return payload
