"""Subagent runner — investigates a single hypothesis with code cells."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

_LOG = logging.getLogger(__name__)


@dataclass
class InvestigationResult:
    """Result of a hypothesis investigation."""
    hypothesis_id: str
    hypothesis_title: str
    finding: str
    cell_ids: list[str] = field(default_factory=list)
    plot_cell_ids: list[str] = field(default_factory=list)
    confidence: float = 0.5
    sub_findings: list[dict] = field(default_factory=list)
    images: dict[str, list[str]] = field(default_factory=dict)  # cell_id -> [base64 png]
    relevant_cols: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "hypothesis_title": self.hypothesis_title,
            "finding": self.finding,
            "cell_ids": self.cell_ids,
            "plot_cell_ids": self.plot_cell_ids,
            "confidence": self.confidence,
            "sub_findings": self.sub_findings,
        }


def run_subagent(
    hypothesis_id: str,
    hypothesis_title: str,
    hypothesis_description: str,
    relevant_cols: list[str],
    all_columns: list[str],
    time_col: str | None,
    session_id: str,
    push_event: Callable[[str, dict], None],
    execute_code: Callable[[str, str, int], tuple[list[dict], str | None]],
    cell_counter: list[int],  # mutable counter [current_count]
    max_cells: int = 5,
    kernel_id: str | None = None,
    notebook_id: str = "main",
    kg_context: str = "",
) -> InvestigationResult:
    """
    Investigate a hypothesis by writing and executing notebook cells.

    :param hypothesis_id: unique ID for this hypothesis
    :param hypothesis_title: short title
    :param hypothesis_description: what to investigate
    :param relevant_cols: columns relevant to this hypothesis
    :param all_columns: all available column names
    :param time_col: time column name (or None)
    :param session_id: session for kernel execution
    :param push_event: callback to stream events to frontend
    :param execute_code: callback to execute code in kernel
    :param cell_counter: shared mutable counter for cell IDs
    :param max_cells: maximum cells this subagent can write
    """
    result = InvestigationResult(
        hypothesis_id=hypothesis_id,
        hypothesis_title=hypothesis_title,
        finding="",
    )
    result.relevant_cols = relevant_cols

    col_list = ", ".join(f'"{c}"' for c in all_columns)
    relevant_str = ", ".join(f'"{c}"' for c in relevant_cols)

    def _next_cell_id() -> str:
        cell_counter[0] += 1
        return f"{hypothesis_id}_cell_{cell_counter[0]}"

    def _write_and_execute(
        code: str,
        cell_type: str = "code",
        *,
        cell_id: str | None = None,
        overwrite: bool = False,
    ) -> tuple[str, list[dict], str | None]:
        """Write a cell, execute it, stream events, return (cell_id, outputs, error)."""
        cell_id = cell_id or _next_cell_id()
        replacement = overwrite and cell_id is not None
        if replacement:
            push_event(session_id, {"type": "cell_delete", "cell_id": cell_id})
            time.sleep(0.05)
        push_event(session_id, {
            "type": "cell_write",
            "cell_id": cell_id,
            "cell_type": cell_type,
            "source": code,
            "overwrite": replacement,
            "notebook_id": notebook_id,
        })
        time.sleep(0.05)

        if cell_type == "markdown":
            return cell_id, [], None

        push_event(session_id, {"type": "cell_executing", "cell_id": cell_id, "notebook_id": notebook_id})
        exec_id = kernel_id if kernel_id else session_id
        outputs, error = execute_code(exec_id, code, 60, cell_id=cell_id)

        if error:
            push_event(session_id, {
                "type": "cell_error", "cell_id": cell_id, "error": error,
                "notebook_id": notebook_id,
            })
        else:
            push_event(session_id, {
                "type": "cell_output", "cell_id": cell_id, "outputs": outputs,
                "notebook_id": notebook_id,
            })
            # Check if outputs contain plots
            for o in outputs:
                data = o.get("data", {})
                if data.get("image/png") or data.get("application/vnd.plotly.v1+json"):
                    result.plot_cell_ids.append(cell_id)
                    break
            # Extract images for vision analysis by main agent
            for o in outputs:
                img = o.get("data", {}).get("image/png")
                if img:
                    result.images.setdefault(cell_id, []).append(img)

        result.cell_ids.append(cell_id)
        time.sleep(0.05)
        return cell_id, outputs, error

    def _extract_text(outputs: list[dict]) -> str:
        parts = []
        for o in outputs:
            if o.get("text"):
                parts.append(o["text"])
            if o.get("data", {}).get("text/plain"):
                parts.append(str(o["data"]["text/plain"]))
            if o.get("data", {}).get("image/png"):
                parts.append("[plot generated]")
        return "\n".join(parts)

    # --- Adaptive investigation loop ---
    try:
        from src.config.config import get_chat_model
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = get_chat_model()

        system_prompt = f"""You are investigating a data hypothesis step by step. You write ONE Python code cell at a time, see its output, then decide the next step.

Available columns: [{col_list}]
Relevant columns: [{relevant_str}]
Time column: {time_col or 'none'}
Variable `df` is already loaded.

{f"Previous findings from other investigations (build on these, don't repeat):" + chr(10) + kg_context if kg_context else ""}

Rules:
- Write ONE code cell per response
- Use ONLY columns from the available list
- Include matplotlib plots where relevant (always plt.show())
- When plotting, also call emit_plot_spec(...) with chart_family, semantic_intent, axis roles
- Print findings clearly with numbers
- Include statistical tests where appropriate (scipy.stats)
- A good investigation has: (1) data prep, (2) visualization, (3) statistical test, (4) conclusion print

Respond with JSON (no markdown fencing):
{{"code": "python code for ONE cell", "reasoning": "why this step", "done": false}}

Set "done": true when you have enough evidence to conclude. When done, set "code" to a final print statement summarizing the key finding."""

        conversation: list = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Hypothesis: {hypothesis_title}\nDescription: {hypothesis_description}\n\nGenerate the first analysis step."),
        ]

        all_outputs: list[str] = []
        cells_executed = 0

        for step in range(max_cells):
            push_event(session_id, {
                "type": "thinking",
                "content": f"Investigation step {step+1}/{max_cells} for: {hypothesis_title}" + (
                    f" (last: {all_outputs[-1][:60]}...)" if all_outputs else ""
                ),
                "notebook_id": notebook_id,
            })

            # Ask LLM for next cell
            try:
                step_response = llm.invoke(conversation)
                step_text = step_response.content.strip()
                if step_text.startswith("```"):
                    step_text = step_text.split("\n", 1)[1] if "\n" in step_text else step_text[3:]
                    if step_text.endswith("```"):
                        step_text = step_text[:-3]
                    step_text = step_text.strip()

                step_data = json.loads(step_text)
                code = step_data.get("code", "")
                reasoning = step_data.get("reasoning", "")
                is_done = step_data.get("done", False)
            except Exception as exc:
                _LOG.warning("Subagent step %d LLM failed: %s", step+1, exc)
                break

            if not code:
                break

            # Execute the cell
            cell_id, outputs, error = _write_and_execute(code)
            cells_executed += 1

            if not error:
                output_text = _extract_text(outputs)
                all_outputs.append(output_text)

                # Build feedback for LLM including text + image descriptions
                feedback = f"Cell {step+1} output:\n{output_text[:1000]}"
                has_plot = any(
                    o.get("data", {}).get("image/png")
                    for o in outputs
                )
                if has_plot:
                    feedback += "\n[A matplotlib plot was generated]"

                # Add assistant response + output to conversation
                conversation.append(step_response)
                if is_done:
                    break
                conversation.append(HumanMessage(content=f"{feedback}\n\nWhat should the next analysis step be? (step {step+2}/{max_cells})"))
            else:
                # Try to fix the error
                try:
                    context_str = "\n".join(all_outputs[-3:]) if all_outputs else "No previous outputs."
                    fix_response = llm.invoke([
                        SystemMessage(content=f"Fix this Python error. Available columns: [{col_list}]. Previous outputs:\n{context_str}\n\nRespond with ONLY corrected code."),
                        HumanMessage(content=f"Error: {error}\nOriginal code:\n{code}"),
                    ])
                    fixed_code = fix_response.content.strip()
                    if fixed_code.startswith("```"):
                        fixed_code = fixed_code.split("\n", 1)[1] if "\n" in fixed_code else fixed_code[3:]
                        if fixed_code.endswith("```"):
                            fixed_code = fixed_code[:-3]
                        fixed_code = fixed_code.strip()
                    push_event(session_id, {
                        "type": "backtrack",
                        "reason": f"Correcting: {error[:100]}",
                        "cell_id": cell_id,
                        "notebook_id": notebook_id,
                    })
                    _, fix_outputs, fix_error = _write_and_execute(
                        fixed_code, cell_id=cell_id, overwrite=True,
                    )
                    if not fix_error:
                        output_text = _extract_text(fix_outputs)
                        all_outputs.append(output_text)
                        conversation.append(step_response)
                        conversation.append(HumanMessage(content=f"Cell {step+1} output (after fix):\n{output_text[:1000]}\n\nWhat next? (step {step+2}/{max_cells})"))
                except Exception as fix_exc:
                    _LOG.warning("Subagent error fix failed: %s", fix_exc)

        # Ensure at least one plot was generated — inject if not
        has_any_plot = bool(result.plot_cell_ids)
        if not has_any_plot and relevant_cols and cells_executed < max_cells:
            col = relevant_cols[0]
            if len(relevant_cols) >= 2:
                col2 = relevant_cols[1]
                plot_code = (
                    f'fig, ax = plt.subplots(figsize=(10, 6))\n'
                    f'ax.scatter(df["{col}"].dropna(), df["{col2}"].dropna(), alpha=0.5, s=20)\n'
                    f'ax.set_xlabel("{col}")\nax.set_ylabel("{col2}")\n'
                    f'ax.set_title("{hypothesis_title}")\nplt.tight_layout()\nplt.show()'
                )
            else:
                plot_code = (
                    f'fig, ax = plt.subplots(figsize=(10, 6))\n'
                    f'ax.hist(df["{col}"].dropna(), bins=30, edgecolor="black", alpha=0.7)\n'
                    f'ax.set_xlabel("{col}")\nax.set_title("{hypothesis_title}")\n'
                    f'plt.tight_layout()\nplt.show()'
                )
            _write_and_execute(plot_code)

    except Exception as exc:
        _LOG.warning("Subagent adaptive loop failed: %s", exc)
        # Fallback: basic analysis
        if relevant_cols and not all_outputs:
            col = relevant_cols[0]
            _write_and_execute(f'print(df["{col}"].describe())')
            all_outputs.append(f"Described {col}")

    # --- Synthesize conclusion with vision ---
    combined_output = "\n---\n".join(all_outputs[:5])
    try:
        from src.config.config import get_chat_model
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = get_chat_model()

        # Build multimodal content with text + plot images
        content_parts = [
            {"type": "text", "text": (
                f"Hypothesis: {hypothesis_title}\n\n"
                f"Evidence from {len(all_outputs)} analysis steps:\n{combined_output[:3000]}"
            )}
        ]
        # Add up to 3 plot images for vision analysis
        img_count = 0
        for cell_id, imgs in result.images.items():
            for img_b64 in imgs:
                if img_count >= 3:
                    break
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "high"},
                })
                img_count += 1
            if img_count >= 3:
                break

        conclusion_response = llm.invoke([
            SystemMessage(content=(
                "You are concluding a data investigation. Based on the text evidence AND any plots shown, "
                "write ONE specific, quantitative sentence about what was found. Include numbers. "
                "If the hypothesis was confirmed, say so with evidence. If refuted, say so. "
                "If plots are shown, reference what you see in them."
            )),
            HumanMessage(content=content_parts),
        ])
        result.finding = conclusion_response.content.strip()

        # Extract p-values from outputs for confidence scoring
        from src.agent.knowledge_graph import compute_finding_confidence, extract_p_values
        all_text = combined_output
        p_vals = extract_p_values(all_text)
        min_p = min(p_vals) if p_vals else None

        # Try to extract sample size
        import re
        n_match = re.search(r'(?:n|N|rows|observations)\s*[=:]\s*([0-9,]+)', all_text)
        sample_n = int(n_match.group(1).replace(',', '')) if n_match else 100

        result.confidence = compute_finding_confidence(
            has_p_value=bool(p_vals),
            p_value=min_p,
            sample_size=sample_n,
            num_evidence_lines=len(all_outputs),
            has_visual_confirmation=img_count > 0,
            confirmed_by_multiple_methods=len(p_vals) > 1,
        )

    except Exception as exc:
        _LOG.warning("Conclusion synthesis failed: %s", exc)
        if all_outputs:
            result.finding = f"Investigation of '{hypothesis_title}' produced {len(all_outputs)} analysis steps."
        else:
            result.finding = f"Could not investigate '{hypothesis_title}' due to errors."
        result.confidence = 0.15

    _LOG.info("Subagent %s complete: %s (confidence=%.2f)",
              hypothesis_id, result.finding[:80], result.confidence)
    return result
