"""Main EDA agent loop — writes and executes cells in real time."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Callable

from src.agent.state import AgentState
from src.agent.goals import build_goal_checklist, EDAGoal
from src.agent import code_templates as ct
from src.agent.reasoning import decide_next_step, interpret_output

_LOG = logging.getLogger(__name__)


def run_agent(
    session_id: str,
    dataset_path: str,
    push_event: Callable[[str, dict], None],
):
    """
    Run the EDA agent loop.

    The agent writes notebook cells one at a time, executes them via the kernel,
    reads outputs, and decides what to do next. All actions are streamed as events.

    :param session_id: session identifier
    :param dataset_path: path to the uploaded dataset file
    :param push_event: callback to push streaming events to the frontend
    """
    from backend.services.kernel_manager import execute_code, shutdown_kernel

    state = AgentState(dataset_path=dataset_path, session_id=session_id)
    goals = build_goal_checklist()
    filename = os.path.basename(dataset_path)

    # Detect format from extension
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    fmt_map = {"csv": "csv", "tsv": "tsv", "xlsx": "xlsx", "xls": "xls",
               "json": "json", "jsonl": "json", "parquet": "parquet", "pq": "parquet"}
    file_format = fmt_map.get(ext, "csv")

    current_phase = ""

    def _think(content: str):
        push_event(session_id, {"type": "thinking", "content": content})
        time.sleep(0.1)

    def _write_and_run(code: str, cell_type: str = "code") -> tuple[list[dict], str | None]:
        """Write a cell, execute it, return (outputs, error)."""
        cell_id = state.next_cell_id()
        state.cell_phases[cell_id] = current_phase
        push_event(session_id, {
            "type": "cell_write",
            "cell_id": cell_id,
            "cell_type": cell_type,
            "source": code,
        })
        time.sleep(0.1)

        if cell_type == "markdown":
            return [], None

        push_event(session_id, {"type": "cell_executing", "cell_id": cell_id})
        outputs, error = execute_code(session_id, code)

        if error:
            push_event(session_id, {
                "type": "cell_error",
                "cell_id": cell_id,
                "error": error,
                "traceback": [o.get("traceback", []) for o in outputs if o.get("output_type") == "error"],
            })
        else:
            push_event(session_id, {
                "type": "cell_output",
                "cell_id": cell_id,
                "outputs": outputs,
            })

        time.sleep(0.05)
        return outputs, error

    def _transition(phase: str, message: str = ""):
        nonlocal current_phase
        if phase != current_phase:
            current_phase = phase
            push_event(session_id, {
                "type": "phase_transition",
                "phase": phase,
                "message": message,
            })
            # Write phase header as markdown cell with divider
            header = f"---\n\n## {phase}"
            if message:
                header += f"\n\n{message}"
            _write_and_run(header, "markdown")

    def _backtrack_and_fix(error: str, fix_code: str, reason: str):
        push_event(session_id, {"type": "backtrack", "reason": reason})
        time.sleep(0.2)
        return _write_and_run(fix_code)

    def _extract_output_text(outputs: list[dict]) -> str:
        """Extract readable text from cell outputs."""
        parts = []
        for o in outputs:
            text = o.get("text", "")
            if text:
                parts.append(text)
            data = o.get("data", {})
            if data.get("text/plain"):
                parts.append(str(data["text/plain"]))
            if data.get("image/png"):
                parts.append("[matplotlib plot generated]")
        return "\n".join(parts)

    def _extract_images(outputs: list[dict]) -> list[str]:
        """Extract base64 PNG images from cell outputs for vision analysis."""
        images = []
        for o in outputs:
            img = o.get("data", {}).get("image/png")
            if img:
                images.append(img)
        return images

    def _interpret_and_follow_up(
        outputs: list[dict],
        error: str | None,
        goal: EDAGoal,
        state: AgentState,
        goals: list[EDAGoal],
    ):
        """Interpret cell output via LLM and optionally run ONE follow-up."""
        if error:
            # Try to fix the error with LLM help
            _try_fix_error(error, goal, state, goals)
            return

        output_text = _extract_output_text(outputs)
        images = _extract_images(outputs)
        if not output_text.strip() and not images:
            return

        # Interpret what we learned — ONE finding per goal (overwrite, don't pile up)
        # Pass images so vision-capable models can analyze plots
        finding = interpret_output(output_text, goal.phase, images=images)
        if finding:
            # Use goal.name as key to prevent duplicates
            state.findings = [f for f in state.findings if f.get("goal") != goal.name]
            state.findings.append({"phase": goal.phase, "finding": finding, "goal": goal.name})

        # Check for ONE follow-up only (not 3) — must be genuinely surprising
        step = decide_next_step(
            state_summary=state.summarize(),
            last_output=output_text[:1500],
            current_phase=goal.phase,
            goals_remaining=[
                g.name for g in goals
                if g.name not in state.phases_completed and not g.should_skip(state)
            ],
            columns=state.columns,
        )

        if step["follow_up"] and step["code"]:
            _think(step["thinking"])
            fu_outputs, fu_error = _write_and_run(step["code"], step["cell_type"])
            if fu_error:
                _try_fix_error(fu_error, goal, state, goals)

    def _try_fix_error(error: str, goal: EDAGoal, state: AgentState, goals: list[EDAGoal]):
        """Ask LLM to fix a cell error, using actual column names."""
        step = decide_next_step(
            state_summary=state.summarize(),
            last_output="",
            current_phase=goal.phase,
            goals_remaining=[g.name for g in goals if g.name not in state.phases_completed],
            columns=state.columns,
            error_context=error,
        )
        if step["code"]:
            push_event(session_id, {"type": "backtrack", "reason": step["thinking"] or f"Fixing: {error[:100]}"})
            _write_and_run(step["code"], step["cell_type"])

    # ---- Title cell ----
    _write_and_run(
        f"# Exploratory Data Analysis: `{filename}`\n\n"
        f"Automated analysis powered by **AgenticEDA**.",
        "markdown",
    )

    # ---- Execute goals ----

    for goal in goals:
        if goal.should_skip(state):
            _LOG.info("Skipping goal: %s (condition met)", goal.name)
            continue

        _transition(goal.phase, goal.description)

        try:
            if goal.name == "load_dataset":
                _think(f"Loading {filename} ({file_format} format)...")
                outputs, error = _write_and_run(ct.load_dataset_code(filename, file_format))
                if error:
                    _think("Load failed. Trying with different encoding...")
                    outputs, error = _backtrack_and_fix(
                        error,
                        f'df = pd.read_csv("{filename}", encoding="latin-1", on_bad_lines="skip")\nprint(f"Loaded {{len(df)}} rows x {{len(df.columns)}} columns")\ndf.head()',
                        "CSV parse error — retrying with latin-1 encoding and skipping bad lines"
                    )
                if not error:
                    state.dataset_loaded = True
                    # Parse row/col count from output
                    for o in outputs:
                        text = o.get("text", "")
                        if "rows" in text and "columns" in text:
                            try:
                                parts = text.split()
                                for i, p in enumerate(parts):
                                    if p == "rows":
                                        state.row_count = int(parts[i - 1])
                                    if p == "columns":
                                        state.col_count = int(parts[i - 1])
                            except (ValueError, IndexError):
                                pass
                    # Get column names into state
                    col_outputs, _ = _write_and_run("print(list(df.columns))")
                    col_text = _extract_output_text(col_outputs)
                    if col_text.strip().startswith("["):
                        try:
                            import ast
                            state.columns = ast.literal_eval(col_text.strip())
                        except Exception:
                            pass
                    _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "inspect_dtypes":
                _think("Checking column types to identify datetime, numeric, and categorical columns...")
                outputs, error = _write_and_run(ct.inspect_dtypes_code())
                if not error:
                    # Parse dtypes from output
                    for o in outputs:
                        text = o.get("text", "")
                        for line in text.split("\n"):
                            parts = line.strip().split()
                            if len(parts) >= 2:
                                col_name = " ".join(parts[:-1])
                                dtype = parts[-1]
                                if col_name and dtype in ("float64", "int64", "object", "datetime64[ns]", "bool"):
                                    state.dtypes[col_name] = dtype
                                    if dtype in ("float64", "int64"):
                                        if col_name not in state.numeric_cols:
                                            state.numeric_cols.append(col_name)
                                    elif dtype == "object":
                                        if col_name not in state.categorical_cols:
                                            state.categorical_cols.append(col_name)
                    state.columns = list(state.dtypes.keys())
                    _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "inspect_describe":
                _think("Computing statistical summary for all columns...")
                outputs, error = _write_and_run(ct.inspect_describe_code())
                _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "parse_datetime":
                # Find datetime candidates from categorical columns
                candidates = [c for c in state.categorical_cols if any(
                    kw in c.lower() for kw in ["date", "time", "timestamp", "dt", "year"]
                )]
                if not candidates and state.categorical_cols:
                    candidates = state.categorical_cols[:1]  # try first object column

                if candidates:
                    col = candidates[0]
                    _think(f"'{col}' looks like a datetime column. Parsing it...")
                    outputs, error = _write_and_run(ct.parse_datetime_code(col))
                    if error:
                        _think(f"Standard parsing failed for '{col}'. Trying with mixed format...")
                        outputs, error = _backtrack_and_fix(
                            error,
                            f'df["{col}"] = pd.to_datetime(df["{col}"], errors="coerce", format="mixed")\nprint(f"Parsed with mixed format. NaT count: {{df[\'{col}\'].isna().sum()}}")\ndf = df.sort_values("{col}").reset_index(drop=True)',
                            f"DateTime parse failed — retrying with format='mixed'"
                        )
                    if not error:
                        state.time_col = col
                        state.add_finding("Data Cleaning", f"Parsed '{col}' as datetime")
                        # Remove from categoricals
                        if col in state.categorical_cols:
                            state.categorical_cols.remove(col)
                        _interpret_and_follow_up(outputs, error, goal, state, goals)
                else:
                    _think("No obvious datetime column found. Proceeding without time index.")

            elif goal.name == "check_missing":
                _think("Auditing missing values across all columns...")
                outputs, error = _write_and_run(ct.inspect_missing_code())
                _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "handle_missing":
                # Check if there are missing values by running a quick check
                outputs, _ = _write_and_run("missing_count = df.isnull().sum().sum()\nprint(f'Total missing: {missing_count}')")
                has_missing = False
                for o in outputs:
                    if "Total missing:" in o.get("text", "") and "Total missing: 0" not in o.get("text", ""):
                        has_missing = True

                if has_missing:
                    _think("There are missing values. I'll handle each column appropriately...")
                    for col in state.numeric_cols:
                        if state.time_col:
                            _write_and_run(ct.handle_missing_interpolate_code(col))
                        else:
                            _write_and_run(ct.handle_missing_ffill_code(col))
                    state.add_finding("Data Cleaning", "Handled missing values via interpolation/forward-fill")
                else:
                    _think("No missing values — data is clean!")

            elif goal.name == "distributions":
                _think(f"Plotting distributions for {len(state.numeric_cols)} numeric columns...")
                outputs, error = _write_and_run(ct.plot_distributions_code(state.numeric_cols))
                state.add_finding("Univariate Analysis", f"Plotted distributions for {len(state.numeric_cols)} columns")
                _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "time_series_plot":
                plot_cols = state.numeric_cols[:4] if state.numeric_cols else state.target_cols
                if plot_cols and state.time_col:
                    _think(f"Plotting time series for: {', '.join(plot_cols[:4])}...")
                    outputs, error = _write_and_run(ct.plot_time_series_code(state.time_col, plot_cols[:4]))
                    state.add_finding("Time Series", f"Plotted time series for {len(plot_cols[:4])} variables")
                    _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "seasonality":
                if state.numeric_cols and state.time_col:
                    col = state.numeric_cols[0]
                    _think(f"Checking for seasonal patterns in '{col}'...")
                    outputs, error = _write_and_run(ct.seasonality_code(state.time_col, col))
                    state.add_finding("Time Series", f"Checked seasonality for '{col}'")
                    _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "rolling_stats":
                if state.numeric_cols and state.time_col:
                    col = state.numeric_cols[0]
                    _think(f"Computing rolling statistics for '{col}' to detect trends and volatility...")
                    outputs, error = _write_and_run(ct.rolling_stats_code(state.time_col, col))
                    state.add_finding("Dynamics", f"Computed rolling stats for '{col}'")
                    _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "outlier_detection":
                if state.numeric_cols:
                    col = state.numeric_cols[0]
                    _think(f"Detecting outliers in '{col}' using IQR method...")
                    outputs, error = _write_and_run(ct.outlier_detection_code(col))
                    state.add_finding("Dynamics", f"Outlier detection on '{col}'")
                    _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "correlations":
                if len(state.numeric_cols) >= 2:
                    _think(f"Computing correlation matrix for {len(state.numeric_cols)} numeric columns...")
                    outputs, error = _write_and_run(ct.correlation_code(state.numeric_cols))
                    state.add_finding("Correlations", "Computed pairwise correlations")
                    _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "train_test_split":
                if state.time_col:
                    _think("Splitting data chronologically (80/20) for model readiness...")
                    outputs, error = _write_and_run(ct.train_test_split_code(state.time_col))
                    state.add_finding("Train/Test Split", "Chronological 80/20 split")
                    _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "summary":
                _think("Summarizing all findings...")
                _write_and_run(ct.summary_markdown(state.findings), "markdown")

            state.mark_phase_done(goal.phase)

        except Exception as exc:
            _LOG.exception("Goal '%s' failed: %s", goal.name, exc)
            _think(f"Error in {goal.name}: {exc}. Moving to next step...")
            state.add_error(goal.phase, str(exc), "skipped")

    # ---- Investigation Phase: Hypothesis-Driven Deep Dives ----
    from src.agent.hypothesis import generate_hypotheses
    from src.agent.subagent import run_subagent
    from src.agent.knowledge_graph import KnowledgeGraph

    kg = KnowledgeGraph()

    # Populate knowledge graph with pass 1 findings
    for f in state.findings:
        kg.add_fact(f.get("finding", ""), f.get("phase", ""), f.get("cell_id"))

    # Generate hypotheses from what we've learned
    _transition("Investigation Phase", "Generating hypotheses from initial findings...")
    # Write a prominent divider between pass-1 EDA and investigations
    findings_summary = "\n".join(f"- {f.get('finding', '')}" for f in state.findings if f.get('finding'))
    _write_and_run(
        "---\n\n"
        "# Deep-Dive Investigations\n\n"
        "The initial EDA is complete. The agent is now formulating and testing hypotheses "
        "based on what it discovered above.\n\n"
        "**Key findings so far:**\n\n"
        f"{findings_summary}",
        "markdown",
    )

    try:
        hypotheses = generate_hypotheses(
            columns=state.columns,
            numeric_cols=state.numeric_cols,
            time_col=state.time_col,
            findings=state.findings,
            row_count=state.row_count,
            col_count=state.col_count,
        )
        hypotheses = hypotheses[:1]  # Cap at 1 for demo speed
    except Exception as exc:
        _LOG.warning("Hypothesis generation failed: %s", exc)
        hypotheses = []

    if hypotheses:
        _think(f"Generated {len(hypotheses)} hypotheses to investigate.")
        push_event(session_id, {
            "type": "phase_transition",
            "phase": f"Investigating {len(hypotheses)} hypotheses",
        })

        cell_counter = [1000]  # subagents start at 1000 to avoid main agent collision

        for i, hyp in enumerate(hypotheses):
            _transition(
                f"Hypothesis {i+1}/{len(hypotheses)}: {hyp.title}",
                hyp.description,
            )
            # Prominent hypothesis header with context
            cols_str = ", ".join(f"`{c}`" for c in hyp.relevant_cols) if hyp.relevant_cols else "all columns"
            _write_and_run(
                f"---\n\n"
                f"## Hypothesis {i+1}: {hyp.title}\n\n"
                f"> {hyp.description}\n\n"
                f"**Relevant columns:** {cols_str}",
                "markdown",
            )

            push_event(session_id, {
                "type": "phase_transition",
                "phase": f"Hypothesis {i+1}/{len(hypotheses)}: {hyp.title}",
                "message": hyp.description,
                "notebook_id": hyp.id,
            })

            try:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(
                        run_subagent,
                        hypothesis_id=hyp.id,
                        hypothesis_title=hyp.title,
                        hypothesis_description=hyp.description,
                        relevant_cols=hyp.relevant_cols,
                        all_columns=state.columns,
                        time_col=state.time_col,
                        session_id=session_id,
                        push_event=push_event,
                        execute_code=execute_code,
                        cell_counter=cell_counter,
                        max_cells=4,
                    )
                    result = future.result(timeout=120)  # 2 min max per hypothesis

                kg.add_investigation(
                    hypothesis_id=hyp.id,
                    hypothesis_title=hyp.title,
                    finding=result.finding,
                    evidence_cells=result.cell_ids,
                    plot_cells=result.plot_cell_ids,
                    confidence=result.confidence,
                    sub_findings=result.sub_findings,
                )

                state.add_finding(f"Investigation: {hyp.title}", result.finding)

                # Write investigation conclusion as markdown
                conf_pct = int(result.confidence * 100)
                conf_label = "High" if conf_pct >= 70 else "Medium" if conf_pct >= 40 else "Low"
                _write_and_run(
                    f"### Finding\n\n"
                    f"{result.finding}\n\n"
                    f"**Confidence:** {conf_label} ({conf_pct}%)",
                    "markdown",
                )

            except concurrent.futures.TimeoutError:
                _LOG.warning("Subagent for %s timed out after 120s", hyp.id)
                _think(f"Investigation of '{hyp.title}' timed out. Moving on.")
            except Exception as exc:
                _LOG.warning("Subagent for %s failed: %s", hyp.id, exc)
                _think(f"Investigation of '{hyp.title}' encountered an error. Moving on.")

        state.cell_count = cell_counter[0]

    # Write conclusions
    _transition("Conclusions", "Synthesizing all findings...")
    conclusions = kg.get_top_conclusions(5)
    conclusion_items = "\n".join(f"1. {c}" for c in conclusions) if conclusions else "No conclusions drawn."
    _write_and_run(
        "---\n\n"
        "# Conclusions\n\n"
        f"{conclusion_items}\n\n"
        "---\n\n"
        "*This analysis was generated automatically by the AgenticEDA agent.*",
        "markdown",
    )

    # Store knowledge graph in state for story generation
    state.knowledge_graph = kg

    # ---- Done ----
    push_event(session_id, {
        "type": "complete",
        "summary": state.summarize(),
    })

    _LOG.info("Agent complete for session %s: %d phases, %d findings, %d hypotheses investigated",
              session_id, len(state.phases_completed), len(state.findings), len(hypotheses))

    return state
