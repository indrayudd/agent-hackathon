"""
Import as:

import src.ingest.infer_structure as sinferstruct
"""

from __future__ import annotations

import argparse
import logging
import re
from typing import TypedDict

import langgraph.graph as lgraph
import langchain_openai
import pydantic

import src.config.config as cconf
import src.ingest.infer_type as sinfert
import src.tools.input_tools as tinptool

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exogenous-column name patterns (P.1)
# ---------------------------------------------------------------------------

_EXOGENOUS_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?i)^is_"),
    re.compile(r"(?i)holiday"),
    re.compile(r"(?i)temperature"),
    re.compile(r"(?i)price"),
    re.compile(r"(?i)day_of_week"),
    re.compile(r"(?i)\bdow\b"),
    re.compile(r"(?i)\bmonth\b"),
    re.compile(r"(?i)\bhour\b"),
    re.compile(r"(?i)weather"),
    re.compile(r"(?i)event"),
    re.compile(r"(?i)promo"),
    re.compile(r"(?i)discount"),
]


def _matches_exogenous_pattern(col: str) -> bool:
    """
    Check whether a column name matches any known exogenous pattern.

    :param col: column name
    :return: True if exogenous pattern matches
    """
    for pattern in _EXOGENOUS_PATTERNS:
        if pattern.search(col):
            return True
    return False


# ---------------------------------------------------------------------------
# Pydantic schema for LLM structured output (P.1)
# ---------------------------------------------------------------------------

class ColumnClassification(pydantic.BaseModel):
    """
    LLM-produced classification of columns into target vs covariate roles.
    """

    target_cols: list[str] = pydantic.Field(
        default_factory=list,
        description=(
            "Columns that represent the primary outcome / dependent variable(s) "
            "the analyst would want to forecast or explain. Leave empty if no "
            "clear target can be identified (unsupervised path)."
        ),
    )
    covariate_cols: list[str] = pydantic.Field(
        default_factory=list,
        description=(
            "All remaining non-key columns that serve as features / predictors / "
            "independent variables."
        ),
    )
    reasoning: str = pydantic.Field(
        default="",
        description="Brief explanation of the classification decision.",
    )


def _classify_target_covariate(
    cols: list[str],
    metadata: dict,
    primary_key: str,
    secondary_keys: list[str],
) -> ColumnClassification:
    """
    Use a lightweight LLM gate to classify columns as target vs covariate.

    The LLM receives column names together with their data profiles and returns
    a structured ``ColumnClassification``.  If no clear target is identifiable
    the ``target_cols`` list is left empty (unsupervised path).

    :param cols: all column names in the dataset
    :param metadata: per-column profile dicts (from ``_build_column_profiles``)
    :param primary_key: primary key / time column name
    :param secondary_keys: entity key column names
    :return: structured classification result
    """
    excluded = {primary_key, *(secondary_keys or [])}
    feature_cols = [c for c in cols if c not in excluded]

    # Build a concise profile summary for the prompt
    profile_lines: list[str] = []
    for col in feature_cols:
        prof = metadata.get(col, {})
        line = (
            f"- {col}: dtype={prof.get('dtype', '?')}, "
            f"n_unique={prof.get('n_unique', '?')}, "
            f"numeric={prof.get('is_numeric_like', '?')}, "
            f"binary={prof.get('is_binary_like', '?')}, "
            f"sample_values={prof.get('sample_values', [])}"
        )
        profile_lines.append(line)

    prompt = (
        "You are classifying columns of a tabular time-series dataset into "
        "**target** (outcome / dependent variable) vs **covariate** (feature / "
        "independent variable).\n\n"
        f"Primary key (time axis): {primary_key}\n"
        f"Entity keys: {secondary_keys or 'none'}\n\n"
        "Feature columns and their profiles:\n"
        + "\n".join(profile_lines)
        + "\n\n"
        "Rules:\n"
        "1. If a single numeric continuous column clearly represents the main "
        "   measured quantity (e.g. sales, revenue, demand, count, value), "
        "   classify it as target.\n"
        "2. All other feature columns are covariates.\n"
        "3. If no column stands out as a clear target, leave target_cols empty.\n"
        "4. Do NOT include the primary key or entity keys in either list.\n"
    )

    llm = cconf.get_chat_model(model=cconf.get_gate_model())
    structured_llm = llm.with_structured_output(ColumnClassification)
    result: ColumnClassification = structured_llm.invoke(prompt)
    return result


class FeatureStructureState(TypedDict):
    """
    Store inferred semantic feature groupings.
    """

    numeric_continuous_cols: list[str]
    numeric_count_cols: list[str]
    binary_flag_cols: list[str]
    categorical_feature_cols: list[str]
    known_exogenous_cols: list[str]
    target_cols: list[str]
    covariate_cols: list[str]


class CompositeState(TypedDict):
    """
    Store graph state for feature-structure inference.
    """

    path: str
    done: list[str]
    has_header: bool
    has_missing_values: bool
    error: str
    info: str
    cols: list[str]
    temporal_cols: list[str]
    numeric_val_cols: list[str]
    categorical_val_cols: list[str]
    bad_rows: list[dict]
    metadata: dict
    time_col: str
    candidates: list[dict]
    winner_formatter: dict
    entity_col: str | None
    numeric_cols: list[str]
    nonnegative_cols: list[str]
    jump_mult: float
    report: dict
    summary: str
    flag: str
    type: str
    primary_key: str
    secondary_keys: list[str]
    numeric_continuous_cols: list[str]
    numeric_count_cols: list[str]
    binary_flag_cols: list[str]
    categorical_feature_cols: list[str]
    known_exogenous_cols: list[str]
    target_cols: list[str]
    covariate_cols: list[str]


def call_infer_type(state: CompositeState) -> dict:
    """
    Run the sequential pipeline up to series-type inference.

    :param state: graph state
    :return: composite payload from infer_type
    """
    payload = sinfert.run_infer_type(state["path"])
    return payload


def infer_structure(state: CompositeState) -> dict:
    """
    Infer semantic feature roles for EDA deterministically from observed column
    behavior.

    :param state: graph state
    :return: inferred feature groupings
    """
    feature_bucket_report = tinptool.infer_feature_buckets.invoke(
        {
            "path": state["path"],
            "time_col": state["primary_key"],
            "secondary_keys": state["secondary_keys"],
        }
    )
    # ------------------------------------------------------------------
    # P.1  LLM gate: classify target vs covariate columns
    # ------------------------------------------------------------------
    column_profiles = feature_bucket_report.get("column_profiles", {})
    all_feature_cols = (
        feature_bucket_report["numeric_continuous_cols"]
        + feature_bucket_report["numeric_count_cols"]
        + feature_bucket_report["binary_flag_cols"]
        + feature_bucket_report["categorical_feature_cols"]
    )

    classification = _classify_target_covariate(
        cols=state.get("cols", all_feature_cols),
        metadata=state.get("metadata", column_profiles),
        primary_key=state["primary_key"],
        secondary_keys=state["secondary_keys"],
    )

    target_cols = classification.target_cols
    # Covariates = everything the LLM said + anything it missed
    llm_covariate_set = set(classification.covariate_cols)
    covariate_cols = list(
        llm_covariate_set
        | (set(all_feature_cols) - set(target_cols) - llm_covariate_set)
    )

    # ------------------------------------------------------------------
    # P.1  Detect known exogenous columns by name pattern matching
    # ------------------------------------------------------------------
    known_exogenous_cols = [
        c for c in covariate_cols if _matches_exogenous_pattern(c)
    ]

    _LOG.info(
        "P.1 classification — targets=%s, covariates=%d, exogenous=%s, reasoning=%s",
        target_cols,
        len(covariate_cols),
        known_exogenous_cols,
        classification.reasoning,
    )

    trace_payload = {
        "primary_key": state["primary_key"],
        "secondary_keys": state["secondary_keys"],
        "series_type": state["type"],
        "feature_bucket_report": feature_bucket_report,
        "target_covariate_classification": {
            "target_cols": target_cols,
            "covariate_cols": covariate_cols,
            "known_exogenous_cols": known_exogenous_cols,
            "reasoning": classification.reasoning,
        },
    }
    tinptool.write_stage_trace(state["path"], "infer_structure", trace_payload)
    payload = {
        "numeric_continuous_cols": feature_bucket_report["numeric_continuous_cols"],
        "numeric_count_cols": feature_bucket_report["numeric_count_cols"],
        "binary_flag_cols": feature_bucket_report["binary_flag_cols"],
        "categorical_feature_cols": feature_bucket_report["categorical_feature_cols"],
        "known_exogenous_cols": known_exogenous_cols,
        "target_cols": target_cols,
        "covariate_cols": covariate_cols,
    }
    return payload


feature_structure = lgraph.StateGraph(CompositeState)
feature_structure.add_node("infer_type_pipeline", call_infer_type)
feature_structure.add_node("infer_structure", infer_structure)
feature_structure.add_edge(lgraph.START, "infer_type_pipeline")
feature_structure.add_edge("infer_type_pipeline", "infer_structure")
feature_structure.add_edge("infer_structure", lgraph.END)
graph = feature_structure.compile()


def run_infer_structure(path: str) -> dict:
    """
    Execute feature-structure inference end to end.

    :param path: dataset path
    :return: full composite graph payload
    """
    init_state: CompositeState = {
        "path": path,
        "done": [],
        "has_header": True,
        "has_missing_values": False,
        "error": "",
        "info": "",
        "cols": [],
        "temporal_cols": [],
        "numeric_val_cols": [],
        "categorical_val_cols": [],
        "bad_rows": [],
        "metadata": {},
        "time_col": "",
        "candidates": [],
        "winner_formatter": {},
        "entity_col": None,
        "numeric_cols": [],
        "nonnegative_cols": [],
        "jump_mult": 20.0,
        "report": {},
        "summary": "",
        "flag": "",
        "type": "",
        "primary_key": "",
        "secondary_keys": [],
        "numeric_continuous_cols": [],
        "numeric_count_cols": [],
        "binary_flag_cols": [],
        "categorical_feature_cols": [],
        "known_exogenous_cols": [],
        "target_cols": [],
        "covariate_cols": [],
    }
    out = graph.invoke(init_state)
    payload: CompositeState = out
    _LOG.info("Feature structure output: %s", payload)
    return payload


def _parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    :return: parsed arguments
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        required=True,
        help="Path to dataset file.",
    )
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    args = _parse_args()
    run_infer_structure(args.path)
