"""LLM-powered reasoning for the EDA agent."""
from __future__ import annotations

import json
import logging

_LOG = logging.getLogger(__name__)


def decide_next_step(
    state_summary: str,
    last_output: str,
    current_phase: str,
    goals_remaining: list[str],
    columns: list[str] | None = None,
    error_context: str | None = None,
) -> dict:
    """
    Ask the LLM what code to write next based on what we just observed.

    :param columns: actual DataFrame column names (prevents hallucination)
    :param error_context: if set, the last cell errored — this is the error message
    """
    try:
        from src.config.config import get_chat_model
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = get_chat_model()

        col_list = ", ".join(f'"{c}"' for c in (columns or []))

        if error_context:
            system = f"""You are fixing a Python error in a Jupyter notebook EDA.
The last cell failed. Write corrected code.

AVAILABLE COLUMNS (use ONLY these): [{col_list}]

Rules:
- Fix the specific error shown below
- Use ONLY column names from the list above — do NOT invent column names
- The variable `df` is already loaded
- Keep the fix focused on the error
- If the corrected cell includes a plot, also emit emit_plot_spec(...) so the
  hidden report spec stays aligned with the visible chart

Respond with EXACTLY this JSON (no markdown fencing):
{{"thinking": "what went wrong and how I'm fixing it", "code": "corrected python code", "cell_type": "code", "phase": "{current_phase}", "follow_up": false}}"""

            human = f"Error:\n{error_context}\n\nState:\n{state_summary}"
        else:
            system = f"""You are an expert data analyst doing EDA in a Jupyter notebook.
Decide if a follow-up investigation cell is needed.

AVAILABLE COLUMNS (use ONLY these): [{col_list}]

Rules:
- ONLY write a follow-up if the output reveals something GENUINELY SURPRISING worth investigating
- Good follow-ups: "bimodal distribution → check if two modes are different time periods",
  "outlier spike → zoom into that time window", "unexpected correlation → test if spurious"
- BAD follow-ups: re-running df.head(), df.info(), df.describe(), or re-summarizing what we already see
- NEVER re-describe the data. If you learned what you need, set follow_up=false
- Use ONLY column names from the list above
- Most of the time, follow_up should be FALSE — only set true for real surprises
- If you do generate a plot, also emit emit_plot_spec(...) with the hidden
  chart spec (family, intent, axis roles, and series/matrix data).

Respond with EXACTLY this JSON (no markdown fencing):
{{"thinking": "brief reasoning", "code": "python code or empty", "cell_type": "code", "phase": "{current_phase}", "follow_up": false}}"""

            human = f"""State: {state_summary}

Last output (truncated):
{last_output[:1500]}

Phase: {current_phase}
Goals remaining: {', '.join(goals_remaining)}

Is there a specific hypothesis worth testing with a NEW cell? Usually no."""

        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])

        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        result = json.loads(text)
        return {
            "thinking": result.get("thinking", ""),
            "code": result.get("code", ""),
            "cell_type": result.get("cell_type", "code"),
            "phase": result.get("phase", current_phase),
            "follow_up": result.get("follow_up", False),
        }
    except Exception as exc:
        _LOG.warning("LLM reasoning failed: %s", exc)
        return {
            "thinking": "",
            "code": "",
            "cell_type": "code",
            "phase": current_phase,
            "follow_up": False,
        }


def interpret_output(output_text: str, phase: str, images: list[str] | None = None) -> str:
    """Ask the LLM to summarize what we learned, including any plot images."""
    if not output_text.strip() and not images:
        return ""
    try:
        from src.config.config import get_chat_model
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = get_chat_model()

        # Build message content — include images if available (vision-capable models)
        content_parts: list[dict] = []
        content_parts.append({
            "type": "text",
            "text": f"Phase: {phase}\nOutput:\n{output_text[:1500]}",
        })
        if images:
            for img_b64 in images[:2]:  # max 2 images to keep token usage reasonable
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "low"},
                })

        response = llm.invoke([
            SystemMessage(content="Write ONE concise sentence about the key finding from this output. If there are plots, describe what visual patterns you see (trends, clusters, outliers, distributions). Be specific with numbers. Do NOT repeat things like 'the dataset loaded' — only report genuinely informative findings."),
            HumanMessage(content=f"Phase: {phase}\nOutput:\n{output_text[:1500]}"),
        ])
        return response.content.strip()
    except Exception:
        return ""
