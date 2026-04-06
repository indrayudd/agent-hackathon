"""Hypothesis generator — formulates investigation questions from initial EDA findings."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

_LOG = logging.getLogger(__name__)


@dataclass
class Hypothesis:
    """A single investigation hypothesis."""
    id: str
    title: str
    description: str
    priority: int  # 1 = highest
    relevant_cols: list[str] = field(default_factory=list)
    eda_rules: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "relevant_cols": self.relevant_cols,
            "eda_rules": self.eda_rules,
        }


def generate_hypotheses(
    columns: list[str],
    numeric_cols: list[str],
    time_col: str | None,
    findings: list[dict],
    row_count: int,
    col_count: int,
) -> list[Hypothesis]:
    """
    Use the LLM to generate investigation hypotheses from initial EDA findings.

    Returns up to 10 ranked hypotheses.
    """
    findings_text = "\n".join(
        f"- [{f.get('phase', '')}] {f.get('finding', '')}" for f in findings
    )

    prompt = f"""You are an expert data analyst. Based on these initial EDA findings,
generate up to 10 hypotheses worth investigating further.

Dataset: {row_count} rows x {col_count} cols
Columns: {', '.join(columns[:20])}
Numeric columns: {', '.join(numeric_cols[:15])}
Time column: {time_col or 'none'}

Initial findings:
{findings_text}

For each hypothesis, consider:
- Unexpected correlations that need deeper analysis
- Anomalies/outliers that need explanation (are they clustered? regime-dependent?)
- Seasonal patterns to decompose (multiple seasonalities? changing over time?)
- Possible causal relationships between variables
- Non-linear relationships hidden by linear correlation
- Feature interactions worth exploring
- Distribution characteristics that affect modeling

Respond with a JSON array (no markdown fencing):
[{{"id": "h1", "title": "short title", "description": "what to investigate and why", "priority": 1, "relevant_cols": ["col1", "col2"], "eda_rules": [25, 27]}}]

Rules:
- Maximum 10 hypotheses
- Priority 1 = most important
- eda_rules = which EDA rules from the rulebook this addresses
- Use ONLY column names from the list above
- Each hypothesis should be SPECIFIC and TESTABLE with code
- Don't include vague hypotheses like "explore the data more"
"""

    try:
        from src.config.config import get_chat_model
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = get_chat_model()
        response = llm.invoke([
            SystemMessage(content="You generate specific, testable data analysis hypotheses. Always respond with valid JSON."),
            HumanMessage(content=prompt),
        ])

        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        raw = json.loads(text)
        hypotheses = []
        for h in raw[:10]:
            hypotheses.append(Hypothesis(
                id=h.get("id", f"h{len(hypotheses)+1}"),
                title=h.get("title", ""),
                description=h.get("description", ""),
                priority=h.get("priority", len(hypotheses)+1),
                relevant_cols=h.get("relevant_cols", []),
                eda_rules=h.get("eda_rules", []),
            ))

        hypotheses.sort(key=lambda h: h.priority)
        _LOG.info("Generated %d hypotheses", len(hypotheses))
        return hypotheses

    except Exception as exc:
        _LOG.warning("Hypothesis generation failed: %s", exc)
        # Fallback: generate basic hypotheses from findings
        fallback = []
        if numeric_cols and len(numeric_cols) >= 2:
            fallback.append(Hypothesis(
                id="h1",
                title=f"Relationship between {numeric_cols[0]} and {numeric_cols[1]}",
                description=f"Investigate the nature of the relationship between {numeric_cols[0]} and {numeric_cols[1]} — is it linear, polynomial, or regime-dependent?",
                priority=1,
                relevant_cols=numeric_cols[:2],
                eda_rules=[25, 26],
            ))
        if time_col and numeric_cols:
            fallback.append(Hypothesis(
                id="h2",
                title=f"Temporal patterns in {numeric_cols[0]}",
                description=f"Check if {numeric_cols[0]} has trends, regime changes, or seasonality beyond what was detected in the initial pass.",
                priority=2,
                relevant_cols=[numeric_cols[0]],
                eda_rules=[14, 18, 21],
            ))
        return fallback


def hypothesis_from_user_question(
    question: str,
    columns: list[str],
    numeric_cols: list[str],
    time_col: str | None,
) -> Hypothesis | None:
    """Convert a user's chat question into a formal Hypothesis."""
    try:
        from src.config.config import get_chat_model
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = get_chat_model()
        response = llm.invoke([
            SystemMessage(content=f"""Convert the user's question into a testable data hypothesis.
Available columns: {', '.join(columns[:20])}
Time column: {time_col or 'none'}

Respond with JSON (no markdown):
{{"id": "user_h1", "title": "short title", "description": "what to test", "relevant_cols": ["col1"], "eda_rules": []}}

If the question is NOT a hypothesis (just a chat question), respond with: {{"id": null}}"""),
            HumanMessage(content=question),
        ])

        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)
        if not data.get("id"):
            return None

        return Hypothesis(
            id=data["id"],
            title=data.get("title", question[:50]),
            description=data.get("description", question),
            priority=1,
            relevant_cols=data.get("relevant_cols", []),
            eda_rules=data.get("eda_rules", []),
        )
    except Exception:
        return None
