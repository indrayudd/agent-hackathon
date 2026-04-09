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
    max_subagents: int = 3,
    max_loops: int = 2,
    loop_timeout: int = 180,
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
    last_code_cell_id: str | None = None

    def _think(content: str):
        push_event(session_id, {"type": "thinking", "content": content, "notebook_id": "main"})
        time.sleep(0.02)

    def _write_and_run(
        code: str,
        cell_type: str = "code",
        *,
        cell_id: str | None = None,
        overwrite: bool = False,
    ) -> tuple[str, list[dict], str | None]:
        """Write or overwrite a cell, execute it, return (cell_id, outputs, error)."""
        nonlocal last_code_cell_id
        target_cell_id = cell_id or state.next_cell_id()
        state.cell_phases[target_cell_id] = current_phase
        replacement = overwrite and cell_id is not None
        if replacement:
            push_event(session_id, {"type": "cell_delete", "cell_id": target_cell_id})
            time.sleep(0.05)
        push_event(session_id, {
            "type": "cell_write",
            "cell_id": target_cell_id,
            "cell_type": cell_type,
            "source": code,
            "overwrite": replacement,
            "notebook_id": "main",
        })
        time.sleep(0.02)

        if cell_type == "markdown":
            state.register_cell(target_cell_id, "markdown", code, notebook_id="main")
            return target_cell_id, [], None

        last_code_cell_id = target_cell_id
        push_event(session_id, {"type": "cell_executing", "cell_id": target_cell_id})
        outputs, error = execute_code(session_id, code, cell_id=target_cell_id)

        if error:
            push_event(session_id, {
                "type": "cell_error",
                "cell_id": target_cell_id,
                "error": error,
                "traceback": [o.get("traceback", []) for o in outputs if o.get("output_type") == "error"],
                "notebook_id": "main",
            })
        else:
            push_event(session_id, {
                "type": "cell_output",
                "cell_id": target_cell_id,
                "outputs": outputs,
                "notebook_id": "main",
            })

        state.register_cell(target_cell_id, "code", code, outputs, notebook_id="main")
        time.sleep(0.05)
        return target_cell_id, outputs, error

    def _transition(phase: str, message: str = "", *, render_cell: bool = True):
        nonlocal current_phase
        if phase != current_phase:
            current_phase = phase
            push_event(session_id, {
                "type": "phase_transition",
                "phase": phase,
                "message": message,
            })
            if render_cell:
                # Write phase header as markdown cell with divider
                header = f"---\n\n## {phase}"
                if message:
                    header += f"\n\n{message}"
                _write_and_run(header, "markdown")

    def _backtrack_and_fix(error: str, fix_code: str, reason: str, failed_cell_id: str):
        push_event(session_id, {"type": "backtrack", "reason": reason, "cell_id": failed_cell_id})
        time.sleep(0.02)
        return _write_and_run(fix_code, cell_id=failed_cell_id, overwrite=True)

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
            _, fu_outputs, fu_error = _write_and_run(step["code"], step["cell_type"])
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
        failed_cell_id = last_code_cell_id

        def _skip_cell(reason: str):
            """Remove the failed cell and replace with a markdown skip note."""
            if not failed_cell_id:
                return
            push_event(session_id, {"type": "cell_delete", "cell_id": failed_cell_id})
            time.sleep(0.05)
            _write_and_run(
                f"> **Skipped step** — `{reason[:150]}`",
                "markdown",
                cell_id=failed_cell_id,
                overwrite=True,
            )

        if not step["code"] or not failed_cell_id:
            # LLM couldn't produce a fix — skip the cell
            if failed_cell_id:
                state.add_error(current_phase, error, "No fix generated")
                _skip_cell(error)
            return

        # Attempt 1: first fix
        _, _, fix_error1 = _backtrack_and_fix(
            error,
            step["code"],
            step["thinking"] or f"Retrying with corrected code: {error[:100]}",
            failed_cell_id,
        )
        if not fix_error1:
            return  # Fixed!

        # Attempt 2: second fix with both errors as context
        _think("Second attempt also failed, trying alternative approach")
        second_fix = decide_next_step(
            state_summary=state.summarize(),
            last_output="",
            current_phase=goal.phase,
            goals_remaining=[g.name for g in goals if g.name not in state.phases_completed],
            columns=state.columns,
            error_context=f"Original error: {error}\nFirst fix error: {fix_error1}",
        )
        if not second_fix or not second_fix.get("code"):
            state.add_error(current_phase, error, "No alternative fix found")
            _skip_cell(error)
            return

        _, _, fix_error2 = _backtrack_and_fix(
            fix_error1,
            second_fix["code"],
            f"Alternative fix attempt: {fix_error1[:80]}",
            failed_cell_id,
        )
        if not fix_error2:
            return  # Fixed on second attempt!

        # All attempts exhausted — skip the cell
        state.add_error(current_phase, error, "Failed after 3 attempts")
        _skip_cell(error)

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
                failed_cell_id, outputs, error = _write_and_run(ct.load_dataset_code(filename, file_format))
                if error:
                    _think("Load failed. Trying with different encoding...")
                    _, outputs, error = _backtrack_and_fix(
                        error,
                        f'df = pd.read_csv("{filename}", encoding="latin-1", on_bad_lines="skip")\nprint(f"Loaded {{len(df)}} rows x {{len(df.columns)}} columns")\ndf.head()',
                        "CSV parse error — retrying with latin-1 encoding and skipping bad lines",
                        failed_cell_id,
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
                    _, col_outputs, _ = _write_and_run("print(list(df.columns))")
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
                _, outputs, error = _write_and_run(ct.inspect_dtypes_code())
                if not error:
                    # Parse dtypes from output
                    for o in outputs:
                        text = o.get("text", "")
                        for line in text.split("\n"):
                            parts = line.strip().split()
                            if len(parts) >= 2:
                                col_name = " ".join(parts[:-1])
                                dtype = parts[-1]
                                # Skip pandas metadata lines like "dtype: object"
                                if col_name.lower().rstrip(":") in ("dtype", "length", "name"):
                                    continue
                                if col_name and dtype in ("float64", "int64", "object", "datetime64[ns]", "bool", "str"):
                                    state.dtypes[col_name] = dtype
                                    if dtype in ("float64", "int64"):
                                        if col_name not in state.numeric_cols:
                                            state.numeric_cols.append(col_name)
                                    elif dtype in ("object", "str"):
                                        if col_name not in state.categorical_cols:
                                            state.categorical_cols.append(col_name)
                    state.columns = list(state.dtypes.keys())
                    _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "inspect_describe":
                _think("Computing statistical summary for all columns...")
                _, outputs, error = _write_and_run(ct.inspect_describe_code())
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
                    failed_cell_id, outputs, error = _write_and_run(ct.parse_datetime_code(col))
                    if error:
                        _think(f"Standard parsing failed for '{col}'. Trying with mixed format...")
                        _, outputs, error = _backtrack_and_fix(
                            error,
                            f'df["{col}"] = pd.to_datetime(df["{col}"], errors="coerce", format="mixed")\nprint(f"Parsed with mixed format. NaT count: {{df[\'{col}\'].isna().sum()}}")\ndf = df.sort_values("{col}").reset_index(drop=True)',
                            f"DateTime parse failed — retrying with format='mixed'",
                            failed_cell_id,
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
                _, outputs, error = _write_and_run(ct.inspect_missing_code())
                _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "handle_missing":
                # Check if there are missing values by running a quick check
                _, outputs, _ = _write_and_run("missing_count = df.isnull().sum().sum()\nprint(f'Total missing: {missing_count}')")
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
                _, outputs, error = _write_and_run(ct.plot_distributions_code(state.numeric_cols))
                state.add_finding("Univariate Analysis", f"Plotted distributions for {len(state.numeric_cols)} columns")
                _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "time_series_plot":
                plot_cols = state.numeric_cols[:4] if state.numeric_cols else state.target_cols
                if plot_cols and state.time_col:
                    _think(f"Plotting time series for: {', '.join(plot_cols[:4])}...")
                    _, outputs, error = _write_and_run(ct.plot_time_series_code(state.time_col, plot_cols[:4]))
                    state.add_finding("Time Series", f"Plotted time series for {len(plot_cols[:4])} variables")
                    _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "seasonality":
                if state.numeric_cols and state.time_col:
                    col = state.numeric_cols[0]
                    _think(f"Checking for seasonal patterns in '{col}'...")
                    _, outputs, error = _write_and_run(ct.seasonality_code(state.time_col, col))
                    state.add_finding("Time Series", f"Checked seasonality for '{col}'")
                    _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "rolling_stats":
                if state.numeric_cols and state.time_col:
                    col = state.numeric_cols[0]
                    _think(f"Computing rolling statistics for '{col}' to detect trends and volatility...")
                    _, outputs, error = _write_and_run(ct.rolling_stats_code(state.time_col, col))
                    state.add_finding("Dynamics", f"Computed rolling stats for '{col}'")
                    _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "outlier_detection":
                if state.numeric_cols:
                    col = state.numeric_cols[0]
                    _think(f"Detecting outliers in '{col}' using IQR method...")
                    _, outputs, error = _write_and_run(ct.outlier_detection_code(col))
                    state.add_finding("Dynamics", f"Outlier detection on '{col}'")
                    _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "correlations":
                if len(state.numeric_cols) >= 2:
                    _think(f"Computing correlation matrix for {len(state.numeric_cols)} numeric columns...")
                    _, outputs, error = _write_and_run(ct.correlation_code(state.numeric_cols))
                    state.add_finding("Correlations", "Computed pairwise correlations")
                    _interpret_and_follow_up(outputs, error, goal, state, goals)

            elif goal.name == "train_test_split":
                if state.time_col:
                    _think("Splitting data chronologically (80/20) for model readiness...")
                    _, outputs, error = _write_and_run(ct.train_test_split_code(state.time_col))
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

    # ---- Investigation Phase: Multi-Loop Hypothesis-Driven Deep Dives ----
    from src.agent.hypothesis import generate_hypotheses
    from src.agent.subagent import run_subagent, InvestigationResult
    from src.agent.knowledge_graph import KnowledgeGraph, KGEdge
    from backend.services.kernel_pool import KernelPoolManager

    kg = KnowledgeGraph()
    pool = KernelPoolManager()

    # Populate knowledge graph with pass 1 findings
    for f in state.findings:
        kg.add_fact(f.get("finding", ""), f.get("phase", ""), f.get("cell_id"))

    # Save dataset checkpoint for subagent kernels
    try:
        _write_and_run(
            "import os; os.makedirs('.cache', exist_ok=True)\n"
            "df.to_parquet('.cache/df_clean.parquet', index=True)\n"
            "print('Dataset checkpoint saved')"
        )
    except Exception as exc:
        _LOG.warning("Dataset checkpoint failed: %s", exc)

    # Get session dir for subagent preamble
    from backend.services.session_manager import get_session_dir
    session_dir = str(get_session_dir(session_id) / "uploads")

    # Verify checkpoint exists
    import pathlib
    cache_path = pathlib.Path(session_dir) / ".cache" / "df_clean.parquet"
    parquet_available = cache_path.exists()
    if not parquet_available:
        _LOG.warning("Dataset checkpoint not found at %s — subagents will use main kernel", cache_path)

    _transition("Investigation Phase", "Generating hypotheses from initial findings...", render_cell=False)
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

    cell_counters = []  # Track for final cell_count update

    _LOG.info("Starting investigation loops: max_loops=%d, max_subagents=%d, columns=%s",
              max_loops, max_subagents, state.columns[:5])

    for loop_num in range(1, max_loops + 1):
        state.loop_count = loop_num
        _LOG.info("=== LOOP %d/%d START === columns=%d, findings=%d",
                  loop_num, max_loops, len(state.columns), len(state.findings))

        push_event(session_id, {
            "type": "loop_start",
            "loop_number": loop_num,
            "total_loops": max_loops,
        })

        _transition(
            f"Investigation Loop {loop_num}/{max_loops}",
            f"Generating hypotheses for loop {loop_num}...",
            render_cell=False,
        )

        # Generate hypotheses using KG context
        try:
            kg_context = kg.get_context_for_hypothesis_generation()
            hypotheses = generate_hypotheses(
                columns=state.columns,
                numeric_cols=state.numeric_cols,
                time_col=state.time_col,
                findings=state.findings,
                row_count=state.row_count,
                col_count=state.col_count,
                kg_context=kg_context,
            )

            # Deduplicate against KG
            novel = []
            for hyp in hypotheses:
                existing = kg.find_similar_hypothesis(hyp, threshold=0.5)
                if existing and existing.confidence > 0.6:
                    _think(f"Skipping '{hyp.title}' - already investigated (confidence: {existing.confidence:.0%})")
                    continue
                novel.append(hyp)
                if len(novel) >= max_subagents:
                    break

            hypotheses = novel
        except Exception as exc:
            _LOG.exception("Hypothesis generation failed in loop %d: %s", loop_num, exc)
            _think(f"Hypothesis generation failed: {exc}")
            hypotheses = []

        if not hypotheses:
            _think("No novel hypotheses remain. Moving to report generation.")
            push_event(session_id, {"type": "loop_complete", "loop_number": loop_num})
            break

        _think(f"Loop {loop_num}: investigating {len(hypotheses)} hypotheses in parallel.")

        _write_and_run(
            f"---\n\n## Investigation Loop {loop_num}\n\n"
            f"Testing {len(hypotheses)} hypothesis(es).",
            "markdown",
        )

        # Write waiting cell in main notebook
        waiting_cell_id = state.next_cell_id()
        hyp_list = "\n".join(f"- **{h.title}**" for h in hypotheses)
        _write_and_run(
            f"---\n\n### Dispatched {len(hypotheses)} Subagents — Loop {loop_num}\n\n"
            f"Investigating in parallel:\n{hyp_list}\n\n"
            f"*Waiting for results...*",
            "markdown",
        )

        push_event(session_id, {
            "type": "subagents_dispatched",
            "notebook_id": "main",
            "loop_number": loop_num,
            "count": len(hypotheses),
            "hypothesis_ids": [h.id for h in hypotheses],
            "titles": [h.title for h in hypotheses],
        })

        # Allocate subagent kernels for parallel execution
        sub_kernel_ids = [None] * len(hypotheses)
        if parquet_available:
            try:
                sub_kernel_ids = pool.allocate_subagent_kernels(session_id, len(hypotheses))
                for kid in sub_kernel_ids:
                    pool.inject_dataset_preamble(kid, session_dir)
            except Exception as exc:
                _LOG.warning("Kernel allocation/preamble failed: %s — falling back to main kernel", exc)
                try:
                    pool.shutdown_subagent_kernels(session_id)
                except Exception:
                    pass
                sub_kernel_ids = [None] * len(hypotheses)
        else:
            _think("Using main kernel for investigations (no parquet checkpoint).")

        # Run subagents via ThreadPoolExecutor
        import concurrent.futures
        loop_cell_counters = [[1000 + loop_num * 1000 + i * 100] for i in range(len(hypotheses))]
        cell_counters.extend(loop_cell_counters)
        results: list[InvestigationResult] = []

        actual_workers = len(hypotheses) if any(k is not None for k in sub_kernel_ids) else 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(actual_workers, 1)) as executor:
            futures = {}
            for i, (hyp, kid) in enumerate(zip(hypotheses, sub_kernel_ids)):
                notebook_id = f"investigation_{hyp.id}"

                cols_str = ", ".join(f"`{c}`" for c in hyp.relevant_cols) if hyp.relevant_cols else "all columns"
                _write_and_run(
                    f"---\n\n### Hypothesis {i+1}: {hyp.title}\n\n"
                    f"> {hyp.description}\n\n"
                    f"**Relevant columns:** {cols_str}",
                    "markdown",
                )

                push_event(session_id, {
                    "type": "subagent_start",
                    "hypothesis_id": hyp.id,
                    "notebook_id": notebook_id,
                    "title": hyp.title,
                })
                push_event(session_id, {
                    "type": "phase_transition",
                    "phase": f"Hypothesis {i+1}/{len(hypotheses)}: {hyp.title}",
                    "message": hyp.description,
                    "notebook_id": notebook_id,
                })

                future = executor.submit(
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
                    cell_counter=loop_cell_counters[i],
                    max_cells=4,
                    kernel_id=kid,
                    notebook_id=notebook_id,
                )
                futures[future] = (hyp, notebook_id)

            try:
                for future in concurrent.futures.as_completed(futures, timeout=loop_timeout):
                    hyp, notebook_id = futures[future]
                    try:
                        result = future.result(timeout=10)
                        results.append(result)
                        state.subagent_run_count += 1

                        push_event(session_id, {
                            "type": "subagent_complete",
                            "hypothesis_id": hyp.id,
                            "notebook_id": notebook_id,
                            "finding": result.finding,
                            "confidence": result.confidence,
                        })
                    except (concurrent.futures.TimeoutError, Exception) as exc:
                        _LOG.warning("Subagent for %s failed: %s", hyp.id, exc)
                        push_event(session_id, {"type": "subagent_timeout", "hypothesis_id": hyp.id})
                        _think(f"Investigation of '{hyp.title}' failed or timed out. Moving on.")
            except concurrent.futures.TimeoutError:
                _LOG.warning("Investigation loop %d timed out after %ds", loop_num, loop_timeout)
                _think(f"Loop {loop_num} timed out. Collecting partial results.")

        # Shutdown subagent kernels after this loop
        try:
            pool.shutdown_subagent_kernels(session_id)
        except Exception:
            pass

        if not results:
            _think(f"Loop {loop_num}: all investigations failed. Stopping.")
            push_event(session_id, {"type": "loop_complete", "loop_number": loop_num})
            break

        # Write compilation summary in main notebook
        compilation = f"---\n\n### Loop {loop_num} Results — {len(results)} Investigation(s)\n\n"
        for result in results:
            conf_pct = int(result.confidence * 100)
            conf_label = "High" if conf_pct >= 70 else "Medium" if conf_pct >= 40 else "Low"
            compilation += f"**{result.hypothesis_title}** ({conf_label} {conf_pct}%)\n"
            compilation += f"> {result.finding}\n\n"
        _write_and_run(compilation, "markdown")

        push_event(session_id, {
            "type": "subagents_returned",
            "notebook_id": "main",
            "loop_number": loop_num,
            "results_count": len(results),
        })

        # Ingest results into KG
        for result in results:
            nid = kg.add_investigation(
                hypothesis_id=result.hypothesis_id,
                hypothesis_title=result.hypothesis_title,
                finding=result.finding,
                evidence_cells=result.cell_ids,
                plot_cells=result.plot_cell_ids,
                confidence=result.confidence,
                sub_findings=result.sub_findings,
                columns=getattr(result, 'relevant_cols', []) or [],
                analysis_type="hypothesis_investigation",
                loop_number=loop_num,
            )
            state.add_finding(f"Investigation: {result.hypothesis_title}", result.finding)

            # Vision analysis of subagent plots
            for cell_id, images in getattr(result, 'images', {}).items():
                if images:
                    try:
                        visual_finding = interpret_output(
                            f"Plot from hypothesis: {result.hypothesis_title}",
                            f"Investigation: {result.hypothesis_title}",
                            images=images[:2],
                        )
                        if visual_finding:
                            vis_id = kg.add_fact(
                                visual_finding,
                                f"Visual: {result.hypothesis_title}",
                                metadata={"type": "visual_insight"},
                            )
                            kg.nodes[vis_id].type = "visual_insight"
                            kg.add_edge(KGEdge(source_id=vis_id, target_id=nid, type="supports"))
                    except Exception:
                        pass

            # Store raw plot images in KG metadata for story generation
            all_images = []
            for cell_id, imgs in getattr(result, 'images', {}).items():
                for img in imgs:
                    all_images.append({"cell_id": cell_id, "image_png": img})
            if all_images:
                node = kg.nodes.get(nid)
                if node:
                    node.metadata["plot_images"] = all_images

            # Write finding as markdown
            conf_pct = int(result.confidence * 100)
            conf_label = "High" if conf_pct >= 70 else "Medium" if conf_pct >= 40 else "Low"
            _write_and_run(
                f"### Finding: {result.hypothesis_title}\n\n"
                f"{result.finding}\n\n"
                f"**Confidence:** {conf_label} ({conf_pct}%)",
                "markdown",
            )

        push_event(session_id, {"type": "loop_complete", "loop_number": loop_num})

    # Update cell count from all subagent counters
    if cell_counters:
        state.cell_count = max(state.cell_count, *(cc[0] for cc in cell_counters))

    # Write conclusions
    _transition("Conclusions", "Synthesizing all findings...", render_cell=False)
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
