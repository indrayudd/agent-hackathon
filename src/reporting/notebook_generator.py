"""
Import as:

import src.reporting.notebook_generator as rnotebook
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

import nbformat

import src.tools.input_tools as tinptool

_LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _md(source: str) -> nbformat.NotebookNode:
    """
    Create a markdown cell.

    :param source: markdown text
    :return: notebook markdown cell node
    """
    return nbformat.v4.new_markdown_cell(source)


def _code(source: str) -> nbformat.NotebookNode:
    """
    Create a code cell.

    :param source: Python code
    :return: notebook code cell node
    """
    return nbformat.v4.new_code_cell(source)


def _safe_json_snippet(obj: Any, *, max_len: int = 1500) -> str:
    """
    Return a JSON string safe for embedding in a markdown cell.

    :param obj: object to serialize
    :param max_len: max character length
    :return: truncated JSON string
    """
    text = json.dumps(obj, indent=2, default=str)
    if len(text) > max_len:
        text = text[:max_len] + "\n... (truncated)"
    return text


def _bullet_list(items: list[str]) -> str:
    """
    Format a list of strings as markdown bullet points.

    :param items: list of strings
    :return: markdown bullet list
    """
    return "\n".join(f"- {item}" for item in items)


# ---------------------------------------------------------------------------
# Per-phase cell builders
# ---------------------------------------------------------------------------

def _header_cells(state: dict) -> list[nbformat.NotebookNode]:
    """
    Build header markdown cell with dataset overview.

    :param state: pipeline state
    :return: list of notebook cells
    """
    name = state.get("original_filename", "dataset")
    series_type = state.get("type", "unknown")
    cols = state.get("cols") or []
    min_t = state.get("min_time", "N/A")
    max_t = state.get("max_time", "N/A")

    header = (
        f"# EDA Report: {name}\n\n"
        f"- **Data type**: {series_type}\n"
        f"- **Columns**: {len(cols)}\n"
        f"- **Time range**: {min_t} to {max_t}\n"
        f"- **Expected frequency**: {state.get('expected_frequency', 'N/A')}\n"
    )
    return [_md(header)]


def _setup_cells(state: dict) -> list[nbformat.NotebookNode]:
    """
    Build setup code cell for imports and data loading.

    :param state: pipeline state
    :return: list of notebook cells
    """
    dataset_path = state.get("quality_dataset_path") or state.get("path", "data.csv")
    code = (
        "import pandas as pd\n"
        "import numpy as np\n"
        "import matplotlib.pyplot as plt\n"
        "import warnings\n"
        "warnings.filterwarnings('ignore')\n"
        "\n"
        f"df = pd.read_csv(r\"{dataset_path}\")\n"
        "print(f\"Shape: {df.shape}\")\n"
        "df.head()"
    )
    return [_md("## Setup"), _code(code)]


def _phase_1_3_cells(state: dict) -> list[nbformat.NotebookNode]:
    """
    Phase 1-3: Data overview cells.

    :param state: pipeline state
    :return: list of notebook cells
    """
    cells: list[nbformat.NotebookNode] = []

    bullets: list[str] = []
    if state.get("has_missing_values") is not None:
        bullets.append(f"Missing values present: {state['has_missing_values']}")
    if state.get("type"):
        bullets.append(f"Series type: {state['type']}")
    if state.get("expected_frequency"):
        bullets.append(f"Frequency: {state['expected_frequency']}")
    if state.get("target_cols"):
        bullets.append(f"Target columns: {', '.join(state['target_cols'])}")

    md_text = "## Phases 1-3: Data Ingestion & Overview\n\n"
    if bullets:
        md_text += _bullet_list(bullets)
    cells.append(_md(md_text))

    time_col = state.get("time_col", "")
    parse_line = ""
    if time_col:
        parse_line = f"\ndf['{time_col}'] = pd.to_datetime(df['{time_col}'], errors='coerce')"

    cells.append(_code(
        f"df.describe(){parse_line}\n"
    ))
    cells.append(_code("df.info()"))

    return cells


def _phase_4_cells(state: dict) -> list[nbformat.NotebookNode]:
    """
    Phase 4: Temporal visualization cells.

    :param state: pipeline state
    :return: list of notebook cells, empty if phase did not run
    """
    if not state.get("seasonality_report") and not state.get("time_series_plots"):
        return []

    cells: list[nbformat.NotebookNode] = []
    bullets: list[str] = []
    if state.get("seasonality_detected") is not None:
        bullets.append(f"Seasonality detected: {state['seasonality_detected']}")
    sr = state.get("seasonality_report") or {}
    if sr:
        periods = sr.get("periods") or sr.get("detected_periods") or []
        if periods:
            bullets.append(f"Detected periods: {periods}")

    md_text = "## Phase 4: Temporal Visualization\n\n"
    if bullets:
        md_text += _bullet_list(bullets)
    cells.append(_md(md_text))

    time_col = state.get("time_col", "date")
    numeric_cols = state.get("numeric_cols") or state.get("numeric_val_cols") or []
    plot_cols = numeric_cols[:5]  # limit for readability

    if plot_cols:
        col_list = ", ".join(f"'{c}'" for c in plot_cols)
        cells.append(_code(
            f"fig, axes = plt.subplots(len([{col_list}]), 1, "
            f"figsize=(14, 3 * len([{col_list}])), sharex=True)\n"
            f"if not hasattr(axes, '__len__'):\n"
            f"    axes = [axes]\n"
            f"for ax, col in zip(axes, [{col_list}]):\n"
            f"    ax.plot(df['{time_col}'], df[col], linewidth=0.7)\n"
            f"    ax.set_ylabel(col)\n"
            f"plt.xlabel('{time_col}')\n"
            f"plt.tight_layout()\n"
            f"plt.show()"
        ))

    return cells


def _phase_5_cells(state: dict) -> list[nbformat.NotebookNode]:
    """
    Phase 5: Dynamics & rolling stats cells.

    :param state: pipeline state
    :return: list of notebook cells, empty if phase did not run
    """
    if not state.get("rolling_stats_report") and not state.get("outlier_report"):
        return []

    cells: list[nbformat.NotebookNode] = []
    bullets: list[str] = []
    if state.get("regime_shifts_detected") is not None:
        bullets.append(f"Regime shifts detected: {state['regime_shifts_detected']}")
    changepoints = state.get("changepoints") or []
    if changepoints:
        bullets.append(f"Changepoints found: {len(changepoints)}")

    md_text = "## Phase 5: Dynamics & Rolling Statistics\n\n"
    if bullets:
        md_text += _bullet_list(bullets)
    cells.append(_md(md_text))

    time_col = state.get("time_col", "date")
    numeric_cols = state.get("numeric_cols") or state.get("numeric_val_cols") or []
    first_col = numeric_cols[0] if numeric_cols else "value"

    cells.append(_code(
        f"window = 7\n"
        f"col = '{first_col}'\n"
        f"rolling_mean = df[col].rolling(window).mean()\n"
        f"rolling_std = df[col].rolling(window).std()\n"
        f"\n"
        f"fig, ax = plt.subplots(figsize=(14, 4))\n"
        f"ax.plot(df['{time_col}'], df[col], alpha=0.4, label='raw')\n"
        f"ax.plot(df['{time_col}'], rolling_mean, label=f'rolling mean (w={{window}})')\n"
        f"ax.fill_between(\n"
        f"    df['{time_col}'],\n"
        f"    rolling_mean - 2 * rolling_std,\n"
        f"    rolling_mean + 2 * rolling_std,\n"
        f"    alpha=0.15, label='+/- 2 std'\n"
        f")\n"
        f"ax.legend()\n"
        f"ax.set_title(f'Rolling statistics: {{col}}')\n"
        f"plt.tight_layout()\n"
        f"plt.show()"
    ))

    return cells


def _phase_6_cells(state: dict) -> list[nbformat.NotebookNode]:
    """
    Phase 6: Multivariate analysis cells.

    :param state: pipeline state
    :return: list of notebook cells, empty if phase did not run
    """
    if not state.get("correlation_report"):
        return []

    cells: list[nbformat.NotebookNode] = []
    md_text = "## Phase 6: Bivariate & Multivariate Analysis\n\n"
    cr = state.get("correlation_report") or {}
    if cr.get("redundant_pairs"):
        md_text += f"- Redundant pairs identified: {len(cr['redundant_pairs'])}\n"
    cells.append(_md(md_text))

    numeric_cols = state.get("numeric_cols") or state.get("numeric_val_cols") or []
    if numeric_cols:
        col_list = ", ".join(f"'{c}'" for c in numeric_cols[:15])
        cells.append(_code(
            f"import seaborn as sns\n"
            f"\n"
            f"subset = df[[{col_list}]].dropna()\n"
            f"corr = subset.corr()\n"
            f"fig, ax = plt.subplots(figsize=(10, 8))\n"
            f"sns.heatmap(corr, annot=True, fmt='.2f', cmap='coolwarm', ax=ax)\n"
            f"ax.set_title('Correlation Heatmap')\n"
            f"plt.tight_layout()\n"
            f"plt.show()"
        ))

    return cells


def _phase_7_cells(state: dict) -> list[nbformat.NotebookNode]:
    """
    Phase 7: Insight discovery cells.

    :param state: pipeline state
    :return: list of notebook cells, empty if phase did not run
    """
    insights = state.get("insights") or []
    if not insights:
        return []

    cells: list[nbformat.NotebookNode] = []
    top = insights[:10]
    bullets = []
    for i, ins in enumerate(top, 1):
        desc = ins.get("description") or ins.get("insight") or str(ins)
        score = ins.get("score", "")
        score_str = f" (score: {score})" if score else ""
        bullets.append(f"**{i}.** {desc}{score_str}")

    md_text = "## Phase 7: Insight Discovery\n\n" + "\n".join(bullets)
    cells.append(_md(md_text))

    cells.append(_code(
        "# Insights are generated by the pipeline; see the trace files for full detail.\n"
        "print('Top insights listed in the markdown cell above.')"
    ))

    return cells


def _phase_8_cells(state: dict) -> list[nbformat.NotebookNode]:
    """
    Phase 8: Causal analysis cells.

    :param state: pipeline state
    :return: list of notebook cells, empty if phase did not run
    """
    if not state.get("causal_graph") and not state.get("granger_report"):
        return []

    cells: list[nbformat.NotebookNode] = []
    bullets: list[str] = []
    classifications = state.get("causal_classifications") or []
    if classifications:
        bullets.append(f"Causal classifications: {len(classifications)} variables assessed")
    responsibilities = state.get("causal_responsibilities") or []
    if responsibilities:
        top_3 = responsibilities[:3]
        for r in top_3:
            factor = r.get("factor", "?")
            score = r.get("responsibility_score", "?")
            bullets.append(f"Factor '{factor}' responsibility score: {score}")

    md_text = "## Phase 8: Causal Analysis\n\n"
    if bullets:
        md_text += _bullet_list(bullets)
    cells.append(_md(md_text))

    # Show causal graph plot if available
    cg_plot = state.get("causal_graph_plot")
    if cg_plot:
        cells.append(_md(f"![Causal Graph]({cg_plot})"))

    cells.append(_code(
        "# Causal analysis results are generated by the pipeline.\n"
        "# See causal_graph and granger_report in the trace files for details.\n"
        "print('Causal findings summarized above.')"
    ))

    return cells


def _phase_9_cells(state: dict) -> list[nbformat.NotebookNode]:
    """
    Phase 9: Train/test split cells.

    :param state: pipeline state
    :return: list of notebook cells, empty if phase did not run
    """
    if not state.get("split_dates"):
        return []

    cells: list[nbformat.NotebookNode] = []
    split_dates = state.get("split_dates") or {}
    split_sizes = state.get("split_sizes") or {}
    bullets = [
        f"Train end: {split_dates.get('train_end', 'N/A')}",
        f"Validation end: {split_dates.get('val_end', 'N/A')}",
    ]
    if split_sizes:
        bullets.append(f"Split sizes: {split_sizes}")

    md_text = "## Phase 9: Train/Test Split\n\n" + _bullet_list(bullets)
    cells.append(_md(md_text))

    time_col = state.get("time_col", "date")
    train_end = split_dates.get("train_end", "")
    val_end = split_dates.get("val_end", "")

    if train_end:
        cells.append(_code(
            f"fig, ax = plt.subplots(figsize=(14, 3))\n"
            f"ax.axvline(pd.Timestamp('{train_end}'), color='red', "
            f"linestyle='--', label='train end')\n"
            + (f"ax.axvline(pd.Timestamp('{val_end}'), color='orange', "
               f"linestyle='--', label='val end')\n" if val_end else "")
            + f"ax.set_xlabel('{time_col}')\n"
            f"ax.legend()\n"
            f"ax.set_title('Split boundaries')\n"
            f"plt.tight_layout()\n"
            f"plt.show()"
        ))

    return cells


def _phase_10_cells(state: dict) -> list[nbformat.NotebookNode]:
    """
    Phase 10: Model readiness cells.

    :param state: pipeline state
    :return: list of notebook cells, empty if phase did not run
    """
    if not state.get("stationarity_report") and not state.get("feature_importance_report"):
        return []

    cells: list[nbformat.NotebookNode] = []
    bullets: list[str] = []

    sr = state.get("stationarity_report") or {}
    if sr:
        bullets.append(f"Stationarity tests completed")
    fi = state.get("feature_importance_report") or {}
    if fi:
        bullets.append("Feature importance screening completed")
    bf = state.get("baseline_features") or []
    if bf:
        bullets.append(f"Baseline features created: {len(bf)}")

    md_text = "## Phase 10: Model Readiness\n\n"
    if bullets:
        md_text += _bullet_list(bullets)
    cells.append(_md(md_text))

    # Stationarity summary
    if sr:
        cells.append(_code(
            f"stationarity = {_safe_json_snippet(sr, max_len=800)}\n"
            f"print('Stationarity report (truncated):')\n"
            f"for k, v in (stationarity if isinstance(stationarity, dict) else {{}}).items():\n"
            f"    print(f'  {{k}}: {{v}}')"
        ))

    # Feature importance plot
    if fi and fi.get("importances"):
        imp = fi["importances"]
        names = [str(x.get("feature", x.get("name", ""))) for x in imp[:15]]
        scores = [float(x.get("importance", x.get("score", 0))) for x in imp[:15]]
        cells.append(_code(
            f"names = {names}\n"
            f"scores = {scores}\n"
            f"fig, ax = plt.subplots(figsize=(10, 5))\n"
            f"ax.barh(names[::-1], scores[::-1])\n"
            f"ax.set_xlabel('Importance')\n"
            f"ax.set_title('Feature Importance (top 15)')\n"
            f"plt.tight_layout()\n"
            f"plt.show()"
        ))

    return cells


def _conclusion_cells(state: dict) -> list[nbformat.NotebookNode]:
    """
    Build conclusion markdown cell from decision summary.

    :param state: pipeline state
    :return: list of notebook cells
    """
    cells: list[nbformat.NotebookNode] = []
    ds = state.get("decision_summary") or {}

    md_text = "## Conclusions\n\n"
    if ds:
        for key in [
            "frequency_choice", "missingness_strategy", "main_seasonalities",
            "anomaly_types", "stable_vs_drifting", "problematic_entities",
            "causal_factors", "split_info",
        ]:
            val = ds.get(key)
            if val:
                label = key.replace("_", " ").title()
                md_text += f"- **{label}**: {val}\n"
        recs = ds.get("modeling_recommendations") or []
        if recs:
            md_text += "\n### Modeling Recommendations\n\n"
            md_text += _bullet_list(recs)
    else:
        md_text += "_No decision summary available. Run `run_decision_summary` first._"

    cells.append(_md(md_text))
    return cells


# ---------------------------------------------------------------------------
# Node function
# ---------------------------------------------------------------------------

def run_notebook_generation(state: dict) -> dict:
    """
    Generate a Jupyter notebook summarizing the full EDA pipeline run.

    :param state: CompositeState dict
    :return: dict with ``notebook_path`` and ``done``
    """
    _LOG.info("Phase 11.2 — generating EDA notebook")

    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }

    cells: list[nbformat.NotebookNode] = []
    cells.extend(_header_cells(state))
    cells.extend(_setup_cells(state))
    cells.extend(_phase_1_3_cells(state))
    cells.extend(_phase_4_cells(state))
    cells.extend(_phase_5_cells(state))
    cells.extend(_phase_6_cells(state))
    cells.extend(_phase_7_cells(state))
    cells.extend(_phase_8_cells(state))
    cells.extend(_phase_9_cells(state))
    cells.extend(_phase_10_cells(state))
    cells.extend(_conclusion_cells(state))

    nb.cells = cells

    # Determine output path
    dataset_name = state.get("original_filename", "dataset")
    # Strip extension for cleaner filename
    dataset_stem = pathlib.Path(dataset_name).stem
    trace_dir = tinptool._trace_root()
    output_path = trace_dir / f"{dataset_stem}.notebook.ipynb"

    with open(output_path, "w", encoding="utf-8") as fh:
        nbformat.write(nb, fh)
    _LOG.info("Notebook written to %s", output_path)

    done = list(state.get("done") or [])
    if "run_notebook_generation" not in done:
        done.append("run_notebook_generation")

    return {"notebook_path": str(output_path), "done": done}
