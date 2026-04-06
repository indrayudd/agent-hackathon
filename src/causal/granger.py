"""
Import as:

import src.causal.granger as sgranger
"""

from __future__ import annotations

import logging
import pathlib
import re
from typing import Any

import numpy as np
import pandas as pd

import src.tools.input_tools as tinptool

_LOG = logging.getLogger(__name__)


def _trace_dir() -> pathlib.Path:
    """
    Return the trace root directory.

    :return: trace root path
    """
    return tinptool._trace_root()


def _done(state: dict, stage: str) -> list[str]:
    """
    Append a stage name to the done list.

    :param state: pipeline state
    :param stage: stage name to mark done
    :return: updated done list
    """
    return list(state.get("done", [])) + [stage]


def _numeric_cols(state: dict) -> list[str]:
    """
    Return the union of continuous and count numeric columns.

    :param state: pipeline state
    :return: list of numeric column names
    """
    return list(state.get("numeric_continuous_cols", [])
                + state.get("numeric_count_cols", []))


def _parse_frequency_to_periods(freq: str | None) -> int:
    """
    Convert an expected frequency string to a seasonal period estimate.

    :param freq: pandas frequency string (e.g. '1h', '1D', '7D')
    :return: estimated seasonal period (capped at 20)
    """
    if not freq:
        return 20

    freq = freq.strip()
    # Try to extract a numeric multiplier and unit
    match = re.match(r"(\d+)?([A-Za-z]+)", freq)
    if not match:
        return 20

    multiplier = int(match.group(1)) if match.group(1) else 1
    unit = match.group(2).upper()

    # Estimate seasonal period in terms of observations
    period_map = {
        "T": 60 // max(multiplier, 1),     # minutes -> hourly season
        "MIN": 60 // max(multiplier, 1),
        "H": 24 // max(multiplier, 1),      # hours -> daily season
        "D": 7 // max(multiplier, 1),        # days -> weekly season
        "W": 4,                               # weeks -> monthly
        "M": 12,                              # months -> yearly
        "MS": 12,
        "Q": 4,                               # quarters -> yearly
        "QS": 4,
        "A": 1,
        "AS": 1,
        "Y": 1,
        "YS": 1,
    }

    period = period_map.get(unit, 20)
    return max(1, min(period, 20))


def run_granger_causality(state: dict) -> dict:
    """
    Run pairwise Granger causality tests on numeric features.

    Only runs for multivariate datasets with at least 2 numeric features.
    Tests stationarity (ADF) first and differences non-stationary series.

    :param state: pipeline state
    :return: state update with granger_report, done
    """
    # ------------------------------------------------------------------
    # Gate
    # ------------------------------------------------------------------
    series_type = state.get("type", "")
    if series_type != "multivariate":
        _LOG.info("Granger causality skipped: type=%s (need multivariate).", series_type)
        return {"done": _done(state, "granger_skipped")}

    num_cols = _numeric_cols(state)
    if len(num_cols) < 2:
        _LOG.info("Granger causality skipped: fewer than 2 numeric features.")
        return {"done": _done(state, "granger_skipped")}

    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------
    path = state.get("quality_dataset_path") or state.get("standardized_dataset_path") or state["path"]
    df = pd.read_csv(path)

    available = [c for c in num_cols if c in df.columns]
    if len(available) < 2:
        _LOG.info("Granger causality skipped: fewer than 2 available numeric columns.")
        return {"done": _done(state, "granger_skipped")}

    data = df[available].dropna()
    if len(data) < 30:
        _LOG.info("Granger causality skipped: fewer than 30 non-null rows.")
        return {"done": _done(state, "granger_skipped")}

    # ------------------------------------------------------------------
    # Import statsmodels
    # ------------------------------------------------------------------
    try:
        from statsmodels.tsa.stattools import adfuller, grangercausalitytests
    except ImportError as exc:
        _LOG.warning("statsmodels not installed; skipping Granger causality. %s", exc)
        return {"done": _done(state, "granger_skipped")}

    # ------------------------------------------------------------------
    # Stationarity check + differencing
    # ------------------------------------------------------------------
    stationary_data = pd.DataFrame(index=data.index)
    differenced_cols: list[str] = []

    for col in available:
        series = data[col].dropna()
        if len(series) < 20:
            stationary_data[col] = data[col]
            continue
        try:
            adf_result = adfuller(series, autolag="AIC")
            p_value = adf_result[1]
        except Exception:
            p_value = 1.0

        if p_value < 0.05:
            stationary_data[col] = data[col]
        else:
            stationary_data[col] = data[col].diff()
            differenced_cols.append(col)

    stationary_data = stationary_data.dropna()
    if len(stationary_data) < 20:
        _LOG.info("Granger causality skipped: too few rows after differencing (%d).", len(stationary_data))
        return {"done": _done(state, "granger_skipped")}

    # ------------------------------------------------------------------
    # Max lag
    # ------------------------------------------------------------------
    freq = state.get("expected_frequency")
    seasonal_period = _parse_frequency_to_periods(freq)
    max_lag = min(seasonal_period, 20)
    # Ensure max_lag is feasible given data length
    max_lag = min(max_lag, len(stationary_data) // 3)
    max_lag = max(max_lag, 1)

    # ------------------------------------------------------------------
    # Pairwise Granger tests
    # ------------------------------------------------------------------
    significant_links: list[dict] = []

    for i, col_x in enumerate(available):
        for j, col_y in enumerate(available):
            if i == j:
                continue
            pair_data = stationary_data[[col_y, col_x]].dropna()
            if len(pair_data) < max_lag + 10:
                continue
            try:
                results = grangercausalitytests(
                    pair_data, maxlag=max_lag, verbose=False
                )
                # Find the best (lowest p-value) lag
                best_lag = None
                best_p = 1.0
                for lag, res in results.items():
                    # res is a tuple: (test_results_dict, ols_results)
                    test_dict = res[0]
                    # Use F-test p-value
                    f_p = test_dict["ssr_ftest"][1]
                    if f_p < best_p:
                        best_p = f_p
                        best_lag = lag

                if best_p < 0.05 and best_lag is not None:
                    significant_links.append({
                        "cause": col_x,
                        "effect": col_y,
                        "best_lag": int(best_lag),
                        "p_value": round(float(best_p), 6),
                        "differenced": col_x in differenced_cols or col_y in differenced_cols,
                    })
            except Exception as exc:
                _LOG.debug("Granger test failed for %s -> %s: %s", col_x, col_y, exc)
                continue

    # Sort by p-value
    significant_links.sort(key=lambda x: x["p_value"])

    # ------------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------------
    plot_path = ""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import networkx as nx

        G = nx.DiGraph()
        G.add_nodes_from(available)

        for link in significant_links:
            weight = max(0.5, 3.0 * (1.0 - link["p_value"]))
            G.add_edge(
                link["cause"], link["effect"],
                weight=weight,
                label=f"lag={link['best_lag']}\np={link['p_value']:.3f}",
            )

        fig, ax = plt.subplots(figsize=(10, 8))
        pos = nx.spring_layout(G, seed=42, k=2.0)
        nx.draw_networkx_nodes(G, pos, ax=ax, node_size=700, node_color="#E8F5E9")
        nx.draw_networkx_labels(G, pos, ax=ax, font_size=8)

        if G.edges():
            edges = list(G.edges())
            weights = [G[u][v].get("weight", 1.0) for u, v in edges]
            nx.draw_networkx_edges(
                G, pos, ax=ax,
                edgelist=edges,
                width=weights,
                edge_color="#4CAF50",
                arrows=True,
                arrowsize=15,
                connectionstyle="arc3,rad=0.1",
            )
            edge_labels = {(u, v): G[u][v]["label"] for u, v in edges}
            nx.draw_networkx_edge_labels(
                G, pos, edge_labels=edge_labels, ax=ax, font_size=6,
            )

        ax.set_title("Granger Causality Network")
        plt.tight_layout()

        trace_dir = _trace_dir()
        plot_file = trace_dir / "granger_causality.png"
        fig.savefig(str(plot_file), dpi=150)
        plt.close(fig)
        plot_path = str(plot_file)
        _LOG.info("Granger causality plot saved to %s.", plot_path)
    except Exception as exc:
        _LOG.warning("Granger visualization failed: %s", exc)

    report = {
        "significant_links": significant_links,
        "max_lag_tested": int(max_lag),
        "n_pairs_tested": len(available) * (len(available) - 1),
        "n_significant": len(significant_links),
        "differenced_columns": differenced_cols,
        "plot_path": plot_path,
    }

    # Trace
    tinptool.write_stage_trace(
        state["path"], "granger_causality",
        {"granger_report": report},
    )

    return {
        "granger_report": report,
        "done": _done(state, "granger_causality"),
    }
