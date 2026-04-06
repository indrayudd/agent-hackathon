"""
Phase 10 - Stationarity testing (ADF + KPSS) with auto-differencing.

Import as:

    from src.model_readiness.stationarity import run_stationarity_tests
"""

import json
import logging
import pathlib
import warnings
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller, kpss

from src.tools.input_tools import _trace_root, load_dataset

logger = logging.getLogger(__name__)

_SIGNIFICANCE = 0.05


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def _adf_test(series: pd.Series) -> dict:
    """Run Augmented Dickey-Fuller test, return stat + p-value."""
    try:
        result = adfuller(series.dropna(), autolag="AIC")
        return {"adf_stat": float(result[0]), "adf_pvalue": float(result[1])}
    except Exception as exc:
        logger.warning("ADF test failed: %s", exc)
        return {"adf_stat": None, "adf_pvalue": None}


def _kpss_test(series: pd.Series) -> dict:
    """Run KPSS test (level stationarity), return stat + p-value."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            stat, pvalue, _lags, _crit = kpss(series.dropna(), regression="c", nlags="auto")
        return {"kpss_stat": float(stat), "kpss_pvalue": float(pvalue)}
    except Exception as exc:
        logger.warning("KPSS test failed: %s", exc)
        return {"kpss_stat": None, "kpss_pvalue": None}


def _is_stationary(adf_p: float | None, kpss_p: float | None) -> bool:
    """
    Consensus rule:
    - ADF rejects null (p < 0.05) => evidence of stationarity
    - KPSS fails to reject null (p >= 0.05) => evidence of stationarity
    Both must agree for us to call it stationary.
    """
    if adf_p is None or kpss_p is None:
        return False
    return adf_p < _SIGNIFICANCE and kpss_p >= _SIGNIFICANCE


def _is_non_stationary_both(adf_p: float | None, kpss_p: float | None) -> bool:
    """True when both tests agree the series is non-stationary."""
    if adf_p is None or kpss_p is None:
        return False
    return adf_p >= _SIGNIFICANCE and kpss_p < _SIGNIFICANCE


# ------------------------------------------------------------------
# main
# ------------------------------------------------------------------

def run_stationarity_tests(state: dict) -> dict:
    """
    Run ADF + KPSS stationarity tests on each numeric target/continuous
    column.  Auto-difference (first order) if both tests flag
    non-stationarity and re-test.

    :param state: pipeline composite state dict
    :return: state update dict
    """
    done: list[str] = list(state.get("done", []))

    # ----- resolve dataset path -----
    ds_path = state.get("standardized_dataset_path") or state.get("quality_dataset_path") or state.get("path")
    if not ds_path:
        return {
            "stationarity_report": {"columns": [], "any_non_stationary": False, "error": "No dataset path found"},
            "done": done + ["stationarity"],
        }

    df = load_dataset(pathlib.Path(ds_path))

    # ----- identify columns to test -----
    target_cols: list[str] = list(state.get("target_cols", []))
    continuous_cols: list[str] = list(state.get("numeric_continuous_cols", []))
    cols_to_test = list(dict.fromkeys(target_cols + continuous_cols))  # deduplicated, order preserved

    if not cols_to_test:
        # fallback: all numeric columns
        cols_to_test = [c for c in df.select_dtypes(include=[np.number]).columns]

    if not cols_to_test:
        return {
            "stationarity_report": {"columns": [], "any_non_stationary": False, "error": "No numeric columns found"},
            "done": done + ["stationarity"],
        }

    # ----- run tests -----
    results: list[dict] = []
    any_non_stationary = False
    min_rows = 30  # need enough data for meaningful tests

    for col in cols_to_test:
        if col not in df.columns:
            continue

        series = df[col].dropna()
        if len(series) < min_rows:
            results.append({
                "column": col,
                "adf_stat": None, "adf_pvalue": None,
                "kpss_stat": None, "kpss_pvalue": None,
                "is_stationary": None,
                "differencing_order": 0,
                "note": f"Skipped: only {len(series)} non-null rows (need >= {min_rows})",
            })
            continue

        adf = _adf_test(series)
        kpss_res = _kpss_test(series)
        stationary = _is_stationary(adf["adf_pvalue"], kpss_res["kpss_pvalue"])
        diff_order = 0

        # auto-difference if both tests agree non-stationary
        if _is_non_stationary_both(adf["adf_pvalue"], kpss_res["kpss_pvalue"]):
            diff_series = series.diff().dropna()
            if len(diff_series) >= min_rows:
                adf = _adf_test(diff_series)
                kpss_res = _kpss_test(diff_series)
                stationary = _is_stationary(adf["adf_pvalue"], kpss_res["kpss_pvalue"])
                diff_order = 1

        if not stationary:
            any_non_stationary = True

        results.append({
            "column": col,
            "adf_stat": adf["adf_stat"],
            "adf_pvalue": adf["adf_pvalue"],
            "kpss_stat": kpss_res["kpss_stat"],
            "kpss_pvalue": kpss_res["kpss_pvalue"],
            "is_stationary": stationary,
            "differencing_order": diff_order,
        })

    report = {"columns": results, "any_non_stationary": any_non_stationary}

    # ----- write trace -----
    trace_path = _trace_root() / "stationarity_report.json"
    trace_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    logger.info("Stationarity trace written to %s", trace_path)

    return {
        "stationarity_report": report,
        "done": done + ["stationarity"],
    }
