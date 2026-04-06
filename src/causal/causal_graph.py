"""
Import as:

import src.causal.causal_graph as scausal
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

import numpy as np
import pandas as pd

import src.tools.input_tools as tinptool

_LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_dataset(state: dict) -> pd.DataFrame:
    """
    Load the best-available dataset from state.

    :param state: pipeline state
    :return: loaded DataFrame
    """
    path = state.get("quality_dataset_path") or state.get("standardized_dataset_path") or state["path"]
    return pd.read_csv(path)


def _numeric_cols(state: dict) -> list[str]:
    """
    Return the union of continuous and count numeric columns.

    :param state: pipeline state
    :return: list of numeric column names
    """
    return list(state.get("numeric_continuous_cols", [])
                + state.get("numeric_count_cols", []))


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


# ---------------------------------------------------------------------------
# Edge-type constants used in FCI PAG adjacency matrices
#   1 = circle, 2 = arrowhead, 3 = tail
# ---------------------------------------------------------------------------

_EDGE_LABELS = {
    (2, 3): "directed",       # X --> Y
    (3, 2): "directed",       # X <-- Y (reversed)
    (2, 2): "bidirected",     # X <-> Y
    (1, 2): "partially_directed",
    (2, 1): "partially_directed",
    (1, 1): "undirected",
    (3, 3): "undirected",
    (1, 3): "semi_directed",
    (3, 1): "semi_directed",
}


def _extract_edges(adj: np.ndarray, nodes: list[str]) -> list[dict]:
    """
    Convert a PAG adjacency matrix to a list of edge dicts.

    :param adj: n x n adjacency matrix from FCI
    :param nodes: column names
    :return: list of edge dicts
    """
    edges: list[dict] = []
    n = len(nodes)
    seen: set[tuple[int, int]] = set()
    for i in range(n):
        for j in range(i + 1, n):
            if adj[i, j] == 0 and adj[j, i] == 0:
                continue
            mark_ij = int(adj[i, j])
            mark_ji = int(adj[j, i])
            edge_type = _EDGE_LABELS.get((mark_ij, mark_ji), "unknown")
            edges.append({
                "source": nodes[i],
                "target": nodes[j],
                "mark_source_to_target": mark_ij,
                "mark_target_to_source": mark_ji,
                "type": edge_type,
            })
    return edges


# ---------------------------------------------------------------------------
# Stage 1: Causal Graph Discovery
# ---------------------------------------------------------------------------

def run_causal_graph(state: dict) -> dict:
    """
    Run causal discovery using the FCI algorithm from causal-learn.

    Produces a PAG (partial ancestral graph) over numeric columns.

    :param state: pipeline state
    :return: state update with causal_graph, causal_graph_plot, done
    """
    num_cols = _numeric_cols(state)
    if len(num_cols) < 3:
        _LOG.info("Causal graph skipped: fewer than 3 numeric columns (%d).", len(num_cols))
        return {"done": _done(state, "causal_graph_skipped")}

    df = _load_dataset(state)
    if len(df) < 200:
        _LOG.info("Causal graph skipped: fewer than 200 rows (%d).", len(df))
        return {"done": _done(state, "causal_graph_skipped")}

    # Keep only numeric columns that exist in the dataset
    available = [c for c in num_cols if c in df.columns]
    if len(available) < 3:
        _LOG.info("Causal graph skipped: fewer than 3 available numeric columns.")
        return {"done": _done(state, "causal_graph_skipped")}

    data = df[available].dropna()
    if len(data) < 200:
        _LOG.info("Causal graph skipped: fewer than 200 non-null rows after dropna.")
        return {"done": _done(state, "causal_graph_skipped")}

    # ------------------------------------------------------------------
    # Pre-screen: remove functional dependencies (|corr| > 0.999)
    # ------------------------------------------------------------------
    corr = data.corr().abs()
    drop_cols: set[str] = set()
    for i, c1 in enumerate(available):
        if c1 in drop_cols:
            continue
        for c2 in available[i + 1:]:
            if c2 in drop_cols:
                continue
            if corr.loc[c1, c2] > 0.999:
                _LOG.info("Dropping %s (functionally dependent on %s).", c2, c1)
                drop_cols.add(c2)

    selected = [c for c in available if c not in drop_cols]
    if len(selected) < 3:
        _LOG.info("Causal graph skipped: fewer than 3 columns after removing functional dependencies.")
        return {"done": _done(state, "causal_graph_skipped")}

    data = data[selected].values

    # ------------------------------------------------------------------
    # Run FCI
    # ------------------------------------------------------------------
    try:
        from causallearn.search.ConstraintBased.FCI import fci
        from causallearn.utils.cit import fisherz
    except ImportError as exc:
        _LOG.warning("causal-learn not installed; skipping causal graph. %s", exc)
        return {"done": _done(state, "causal_graph_skipped")}

    try:
        g, edges_info = fci(data, fisherz, 0.05, verbose=False)
        adj = g.graph  # PAG adjacency matrix
    except Exception as exc:
        _LOG.error("FCI failed: %s", exc, exc_info=True)
        return {"done": _done(state, "causal_graph_error")}

    edge_list = _extract_edges(adj, selected)

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
        G.add_nodes_from(selected)

        color_map = {
            "directed": "#2196F3",
            "bidirected": "#F44336",
            "undirected": "#9E9E9E",
            "partially_directed": "#FF9800",
            "semi_directed": "#FF9800",
            "unknown": "#BDBDBD",
        }

        edge_colors: list[str] = []
        edge_styles: list[str] = []
        for e in edge_list:
            G.add_edge(e["source"], e["target"])
            edge_colors.append(color_map.get(e["type"], "#BDBDBD"))
            edge_styles.append("solid" if e["type"] == "directed" else "dashed")

        fig, ax = plt.subplots(figsize=(10, 8))
        pos = nx.spring_layout(G, seed=42, k=2.0)
        nx.draw_networkx_nodes(G, pos, ax=ax, node_size=700, node_color="#E3F2FD")
        nx.draw_networkx_labels(G, pos, ax=ax, font_size=8)
        for idx, (u, v) in enumerate(G.edges()):
            nx.draw_networkx_edges(
                G, pos, ax=ax,
                edgelist=[(u, v)],
                edge_color=edge_colors[idx],
                style=edge_styles[idx],
                arrows=True,
                arrowsize=15,
                width=2,
            )

        # Legend
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], color="#2196F3", lw=2, label="Directed"),
            Line2D([0], [0], color="#F44336", lw=2, linestyle="dashed", label="Bidirected"),
            Line2D([0], [0], color="#9E9E9E", lw=2, linestyle="dashed", label="Undirected"),
            Line2D([0], [0], color="#FF9800", lw=2, linestyle="dashed", label="Partial"),
        ]
        ax.legend(handles=legend_elements, loc="upper left")
        ax.set_title("Causal Graph (FCI / PAG)")
        plt.tight_layout()

        trace_dir = _trace_dir()
        plot_file = trace_dir / "causal_graph.png"
        fig.savefig(str(plot_file), dpi=150)
        plt.close(fig)
        plot_path = str(plot_file)
        _LOG.info("Causal graph plot saved to %s.", plot_path)
    except Exception as exc:
        _LOG.warning("Causal graph visualization failed: %s", exc)

    result = {
        "adjacency": adj.tolist(),
        "nodes": selected,
        "edge_types": edge_list,
    }

    # Trace
    tinptool.write_stage_trace(
        state["path"], "causal_graph",
        {"causal_graph": result, "plot_path": plot_path},
    )

    return {
        "causal_graph": result,
        "causal_graph_plot": plot_path,
        "done": _done(state, "causal_graph"),
    }


# ---------------------------------------------------------------------------
# Stage 2: Causal Classification
# ---------------------------------------------------------------------------

def _find_paths_in_pag(adj: list[list[int]], nodes: list[str],
                       source_idx: int, target_idx: int) -> list[list[str]]:
    """
    BFS over PAG adjacency to find directed paths from source to target.

    Only follows edges where the endpoint mark is an arrowhead (2) in
    the direction of traversal.

    :param adj: adjacency matrix as nested lists
    :param nodes: column names
    :param source_idx: index of source node
    :param target_idx: index of target node
    :return: list of paths (each path is a list of node names)
    """
    from collections import deque

    n = len(nodes)
    mat = np.array(adj)
    queue: deque[list[int]] = deque([[source_idx]])
    found: list[list[str]] = []

    while queue:
        path = queue.popleft()
        current = path[-1]
        if current == target_idx and len(path) > 1:
            found.append([nodes[i] for i in path])
            continue
        for nxt in range(n):
            if nxt in path:
                continue
            # Follow edge only if mark at nxt-side is arrowhead (2)
            if mat[current, nxt] != 0 and mat[current, nxt] in (2, 3):
                queue.append(path + [nxt])

    return found


def run_causal_classification(state: dict) -> dict:
    """
    Classify each variable as causal, non-causal, or ambiguous
    with respect to the target column(s).

    Uses the causal graph from `run_causal_graph` plus optional
    LLM reasoning over outlier anomalies.

    :param state: pipeline state
    :return: state update with causal_classifications, done
    """
    cg = state.get("causal_graph")
    if not cg or not cg.get("nodes"):
        _LOG.info("Causal classification skipped: no causal graph available.")
        return {"done": _done(state, "causal_classification_skipped")}

    nodes: list[str] = cg["nodes"]
    adj: list[list[int]] = cg["adjacency"]
    edge_list: list[dict] = cg.get("edge_types", [])

    target_cols = state.get("target_cols", [])
    if not target_cols:
        # Fallback: use last numeric column as target
        num_cols = _numeric_cols(state)
        target_cols = [num_cols[-1]] if num_cols else []

    # Build a set of bidirected-connected variables (ambiguous)
    bidirected_vars: set[str] = set()
    for e in edge_list:
        if e["type"] == "bidirected":
            bidirected_vars.add(e["source"])
            bidirected_vars.add(e["target"])

    classifications: list[dict] = []
    for var in nodes:
        if var in target_cols:
            continue

        # Check for directed path to any target
        var_idx = nodes.index(var)
        has_path = False
        best_path: list[str] = []
        for tgt in target_cols:
            if tgt not in nodes:
                continue
            tgt_idx = nodes.index(tgt)
            paths = _find_paths_in_pag(adj, nodes, var_idx, tgt_idx)
            if paths:
                has_path = True
                best_path = min(paths, key=len)
                break

        if has_path:
            classification = "causal"
            confidence = "high" if var not in bidirected_vars else "medium"
        elif var in bidirected_vars:
            classification = "ambiguous"
            confidence = "low"
        else:
            classification = "non-causal"
            confidence = "medium"

        classifications.append({
            "variable": var,
            "classification": classification,
            "path_to_target": best_path,
            "confidence": confidence,
        })

    # ------------------------------------------------------------------
    # Optional LLM enrichment: generate "why queries" from outlier report
    # ------------------------------------------------------------------
    outlier_report = state.get("outlier_report")
    if outlier_report and classifications:
        try:
            from src.config.config import get_agent_model, get_chat_model

            model = get_chat_model(model=get_agent_model())

            # Summarize top anomalies
            anomalies_summary = json.dumps(outlier_report, default=str)[:3000]
            causal_vars = [c["variable"] for c in classifications if c["classification"] == "causal"]

            if causal_vars:
                prompt = (
                    "Given these detected anomalies in a time-series dataset:\n"
                    f"{anomalies_summary}\n\n"
                    f"And these variables classified as causal: {causal_vars}\n\n"
                    "Generate 2-3 concise 'why queries' that an analyst should "
                    "investigate to understand the root causes. Return as a JSON list "
                    "of strings."
                )
                resp = model.invoke(prompt)
                why_text = resp.content if hasattr(resp, "content") else str(resp)
                # Try to parse as JSON
                try:
                    why_queries = json.loads(why_text)
                except (json.JSONDecodeError, TypeError):
                    why_queries = [why_text]

                # Attach why queries to the first causal classification
                for c in classifications:
                    if c["classification"] == "causal":
                        c["why_queries"] = why_queries
                        break
        except Exception as exc:
            _LOG.warning("LLM why-query generation failed: %s", exc)

    # Trace
    tinptool.write_stage_trace(
        state["path"], "causal_classification",
        {"causal_classifications": classifications},
    )

    return {
        "causal_classifications": classifications,
        "done": _done(state, "causal_classification"),
    }


# ---------------------------------------------------------------------------
# Stage 3: Responsibility Scoring
# ---------------------------------------------------------------------------

def run_responsibility_scoring(state: dict) -> dict:
    """
    Estimate each causal factor's responsibility via subgroup comparison.

    Splits data by the median of each causal factor, compares target means
    in the two halves, and ranks by relative effect size.

    :param state: pipeline state
    :return: state update with causal_responsibilities, done
    """
    classifications = state.get("causal_classifications", [])
    causal_factors = [c["variable"] for c in classifications if c.get("classification") == "causal"]

    if not causal_factors:
        _LOG.info("Responsibility scoring skipped: no causal factors found.")
        return {"done": _done(state, "responsibility_scoring_skipped")}

    target_cols = state.get("target_cols", [])
    if not target_cols:
        num_cols = _numeric_cols(state)
        target_cols = [num_cols[-1]] if num_cols else []
    if not target_cols:
        _LOG.info("Responsibility scoring skipped: no target column.")
        return {"done": _done(state, "responsibility_scoring_skipped")}

    target = target_cols[0]
    df = _load_dataset(state)

    if target not in df.columns:
        _LOG.warning("Target column %s not found in dataset.", target)
        return {"done": _done(state, "responsibility_scoring_skipped")}

    responsibilities: list[dict] = []
    global_mean = df[target].mean()
    global_std = df[target].std()
    if global_std == 0 or pd.isna(global_std):
        global_std = 1.0

    for factor in causal_factors:
        if factor not in df.columns:
            continue

        median_val = df[factor].median()
        low_group = df[df[factor] <= median_val][target]
        high_group = df[df[factor] > median_val][target]

        if len(low_group) < 5 or len(high_group) < 5:
            continue

        mean_low = low_group.mean()
        mean_high = high_group.mean()
        effect_size = (mean_high - mean_low) / global_std
        direction = "positive" if effect_size > 0 else "negative"

        responsibilities.append({
            "factor": factor,
            "responsibility_score": round(abs(effect_size), 4),
            "direction": direction,
            "effect_size": round(effect_size, 4),
            "mean_low_group": round(float(mean_low), 4),
            "mean_high_group": round(float(mean_high), 4),
            "n_low": int(len(low_group)),
            "n_high": int(len(high_group)),
        })

    # Sort by responsibility score descending
    responsibilities.sort(key=lambda x: x["responsibility_score"], reverse=True)

    # Normalize to relative scores summing to 1.0
    total = sum(r["responsibility_score"] for r in responsibilities)
    if total > 0:
        for r in responsibilities:
            r["responsibility_score_relative"] = round(r["responsibility_score"] / total, 4)

    # Trace
    tinptool.write_stage_trace(
        state["path"], "responsibility_scoring",
        {"causal_responsibilities": responsibilities},
    )

    return {
        "causal_responsibilities": responsibilities,
        "done": _done(state, "responsibility_scoring"),
    }
