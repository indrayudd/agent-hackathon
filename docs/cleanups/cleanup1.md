# cleanup1.md — Real-Time Streaming Agent Overhaul

## Problem

The current architecture runs the entire pipeline silently in a background thread,
generates a notebook after the fact, then streams pre-built cells to the frontend.
The user sees nothing for 2+ minutes, then gets a wall of cells.

## Goal

The user watches the agent work in real time — like pair-programming with a data
scientist. The agent writes a cell, runs it, reads the output, thinks about what
to do next, writes the next cell, and so on. Errors, backtracking, and reasoning
are all visible. The notebook IS the pipeline — not a report generated after.

## Architecture Change

```
BEFORE:                              AFTER:
Pipeline (silent)                    Agent Loop (visible)
  -> run all phases                    -> write cell to frontend
  -> generate notebook                 -> execute cell via kernel
  -> stream cells post-hoc            -> read output
                                       -> stream thinking/reasoning
                                       -> decide next cell
                                       -> repeat until EDA goals met
```

---

## 1. Streaming Protocol Redesign

### WebSocket message types (backend -> frontend)

- [x] Define `AgentEvent` union type with these variants:
  - [x] `thinking` — agent's intermediate reasoning (displayed as a subtle status bar or collapsible thinking block above the next cell)
    ```json
    {"type": "thinking", "content": "The dataset has 5 columns. I see a datetime column 'Date/Time'. Let me parse it and check for issues..."}
    ```
  - [x] `cell_write` — agent is writing a new cell (appears in notebook with a typing indicator)
    ```json
    {"type": "cell_write", "cell_id": "c1", "cell_type": "code", "source": "import pandas as pd\ndf = pd.read_csv('data.csv')\ndf.head()"}
    ```
  - [x] `cell_executing` — cell is being executed (spinner appears on the cell)
    ```json
    {"type": "cell_executing", "cell_id": "c1"}
    ```
  - [x] `cell_output` — execution result (output renders under the cell)
    ```json
    {"type": "cell_output", "cell_id": "c1", "outputs": [...]}
    ```
  - [x] `cell_error` — execution produced an error (cell gets red border, agent will backtrack)
    ```json
    {"type": "cell_error", "cell_id": "c1", "error": "KeyError: 'date'", "traceback": [...]}
    ```
  - [x] `cell_update` — agent revises a cell it already wrote (source updates in-place)
    ```json
    {"type": "cell_update", "cell_id": "c1", "source": "df = pd.read_csv('data.csv', parse_dates=['Date/Time'])"}
    ```
  - [x] `phase_transition` — agent moves to a new EDA phase (shown as a section header / divider in notebook)
    ```json
    {"type": "phase_transition", "phase": "Seasonality Analysis", "message": "Now checking for seasonal patterns..."}
    ```
  - [x] `backtrack` — agent is fixing an error or revising a decision
    ```json
    {"type": "backtrack", "reason": "The datetime parse failed on row 45. Adding errors='coerce' and inspecting bad rows..."}
    ```
  - [x] `complete` — agent is done
    ```json
    {"type": "complete", "summary": "EDA complete. Found 3 seasonal patterns, 2 outliers, strong correlation between wind speed and power output."}
    ```

- [x] Create `backend/models/events.py` with Pydantic models for all event types
- [x] Update `backend/routers/stream.py` to use the new event types

---

## 2. Agent Loop (replaces the current pipeline)

### Core concept: the agent IS a code-writing loop

- [x] Create `src/agent/eda_agent.py` — the main agent loop:
  ```
  while not goals_met:
      1. Look at current state (what has been done, what outputs exist)
      2. Decide what to do next (emit "thinking" event)
      3. Write a code cell (emit "cell_write" event)
      4. Execute the cell via kernel (emit "cell_executing" event)
      5. Read the output (emit "cell_output" event)
      6. If error: emit "backtrack", write fix cell, go to step 4
      7. Update state with new findings
      8. Check if EDA goals are met
  ```

- [x] The agent uses an LLM to decide:
  - What code to write next (based on EDA_RULES.txt goals + current state)
  - How to interpret outputs (what did we learn?)
  - Whether to backtrack (did something go wrong?)
  - When EDA is complete (are all goals met?)

- [x] The agent's "memory" is the notebook itself — it can read back any cell's output

- [x] Create `src/agent/__init__.py`

### Agent state tracking

- [x] Create `src/agent/state.py` — tracks:
  - [x] `dataset_path` — path to uploaded file
  - [x] `dataset_info` — columns, dtypes, row count (discovered during ingestion)
  - [x] `time_col` — identified time column
  - [x] `target_cols` — identified target columns
  - [x] `findings` — list of discoveries (one per cell that produced insight)
  - [x] `errors_encountered` — list of errors and how they were resolved
  - [x] `phases_completed` — which EDA phases are done
  - [x] `goals_remaining` — what still needs to be checked
  - [x] `cell_history` — ordered list of (cell_id, source, output_summary)

### Agent goals (derived from EDA_RULES.txt)

- [x] Create `src/agent/goals.py` — ordered checklist the agent works through:
  - [x] `load_and_inspect` — load data, show head/shape/dtypes/info
  - [x] `clean_datetime` — parse time column, handle bad rows
  - [x] `check_integrity` — duplicates, missing values, impossible values
  - [x] `handle_missing` — impute or drop, show before/after
  - [x] `univariate_stats` — describe(), distribution plots for each numeric col
  - [x] `time_series_plots` — plot raw series, zoom windows
  - [x] `seasonality` — check for seasonal patterns
  - [x] `rolling_dynamics` — rolling stats, changepoints, outliers
  - [x] `correlations` — pairwise correlations, heatmap
  - [x] `lag_analysis` — ACF/PACF if time series
  - [x] `train_test_split` — temporal split, distribution drift check
  - [x] `summary` — final summary of all findings
  - [x] Each goal has: `name`, `description`, `check_fn` (did it succeed?), `skip_condition`

---

## 3. Kernel Integration (real cell execution)

### Replace the mock kernel with a real one

- [x] Create `backend/services/kernel_manager.py` (rewrite):
  - [x] On session creation, start a real IPython kernel subprocess (using `jupyter_client`)
  - [x] The kernel's working directory is the session's upload directory
  - [x] Pre-inject: `import pandas as pd, numpy as np, matplotlib.pyplot as plt, warnings; warnings.filterwarnings('ignore'); %matplotlib inline`
  - [x] Provide `execute_code(session_id, code) -> (outputs, error)` function
  - [x] Capture stdout, stderr, display_data (images), execute_result
  - [x] Return structured outputs matching the `CellOutput` type
  - [x] Handle execution timeout (60s default)
  - [x] Kernel shutdown on session cleanup

- [x] Update `backend/routers/kernel.py`:
  - [x] Real `execute` endpoint: `POST /api/kernel/{session_id}/execute` — takes code string, returns outputs
  - [x] The agent loop calls this directly (not via WebSocket — that's for user cell execution later)

- [x] The frontend does NOT need to manage kernel WebSocket for agent-generated cells — the agent runs cells server-side and streams the results. The kernel WebSocket is only needed when the USER manually runs a cell after the agent is done.

---

## 4. Ingestion Overhaul (visible in notebook)

### The agent's first cells ARE the ingestion

- [x] The agent starts by writing cells that the user can see:
  ```python
  # Cell 1 (markdown): "## Loading Dataset"
  # Cell 2 (code):
  import pandas as pd
  df = pd.read_csv("/path/to/uploaded/file.csv")
  print(f"Loaded {len(df)} rows, {len(df.columns)} columns")
  df.head()
  ```
  ```python
  # Cell 3 (code):
  df.info()
  ```
  ```python
  # Cell 4 (code):
  df.describe()
  ```

- [x] If the agent sees parsing issues in the output, it writes fix cells:
  ```python
  # Cell 5 (thinking): "I see the 'Date/Time' column is object type. Let me parse it..."
  # Cell 6 (code):
  df['Date/Time'] = pd.to_datetime(df['Date/Time'], errors='coerce')
  n_bad = df['Date/Time'].isna().sum()
  print(f"Parsed datetime. {n_bad} unparseable rows (NaT)")
  df[df['Date/Time'].isna()] if n_bad > 0 else "All rows parsed successfully"
  ```

- [x] The deterministic tools from `src/tools/input_tools.py` become CODE GENERATORS — instead of running analysis internally, they generate the Python code string that the agent puts in a cell

- [x] Create `src/agent/code_templates.py`:
  - [x] `load_dataset_code(path, format)` — returns code string for loading
  - [x] `inspect_data_code()` — returns code for df.head(), df.info(), df.describe()
  - [x] `parse_datetime_code(col, format_args)` — returns code for datetime parsing
  - [x] `check_missing_code()` — returns code for missing value audit
  - [x] `handle_missing_code(strategy_per_col)` — returns code for imputation
  - [x] `plot_time_series_code(time_col, value_cols)` — returns code for line plots
  - [x] `seasonality_code(time_col, value_col)` — returns code for seasonal analysis
  - [x] `correlation_code(numeric_cols)` — returns code for correlation matrix + heatmap
  - [x] `rolling_stats_code(col, windows)` — returns code for rolling statistics
  - [x] `outlier_detection_code(col)` — returns code for outlier flagging
  - [x] `train_test_split_code(time_col, ratio)` — returns code for temporal split
  - [x] `summary_code()` — returns code for final summary markdown

- [x] Each template returns CLEAN, READABLE Python code that a human would write — not library calls. The notebook should look like something a skilled analyst wrote.

---

## 5. Backend Run Router Rewrite

- [x] Rewrite `backend/routers/run.py`:
  - [x] `POST /api/run/{session_id}` starts the agent loop in a background thread
  - [x] The agent loop pushes events to the stream buffer (from `stream.py`)
  - [x] Each event is immediately available to the frontend via the stream WebSocket

- [x] The agent loop pseudocode:
  ```python
  async def run_agent(session_id, dataset_path):
      kernel = get_or_create_kernel(session_id)
      state = AgentState(dataset_path)
      goals = build_goal_checklist(state)
      
      push_event(session_id, {"type": "phase_transition", "phase": "Data Loading"})
      
      for goal in goals:
          if goal.should_skip(state):
              continue
          
          push_event(session_id, {"type": "thinking", "content": goal.thinking_prompt(state)})
          
          code = goal.generate_code(state)
          cell_id = new_cell_id()
          
          push_event(session_id, {"type": "cell_write", "cell_id": cell_id, "cell_type": "code", "source": code})
          push_event(session_id, {"type": "cell_executing", "cell_id": cell_id})
          
          outputs, error = kernel.execute(code)
          
          if error:
              push_event(session_id, {"type": "cell_error", "cell_id": cell_id, "error": error})
              push_event(session_id, {"type": "backtrack", "reason": f"Error: {error}. Fixing..."})
              fix_code = goal.generate_fix(state, error)
              # ... write and execute fix cell
          else:
              push_event(session_id, {"type": "cell_output", "cell_id": cell_id, "outputs": outputs})
              state.update_from_output(goal, outputs)
      
      push_event(session_id, {"type": "complete", "summary": state.summarize()})
  ```

---

## 6. Frontend Streaming Overhaul

### NotebookPane becomes a live view of the agent's work

- [x] Update `useAgentStream.ts` to handle all new event types:
  - [x] `thinking` → show a collapsible "thinking" block above the next cell (light purple/gray background, italic text, with a brain/thought icon)
  - [x] `cell_write` → append a new cell to the notebook with the source code, show a subtle "writing..." animation
  - [x] `cell_executing` → show a spinner/pulsing border on the cell being executed
  - [x] `cell_output` → render outputs under the cell (same as current CellOutput)
  - [x] `cell_error` → render error output with red border, show "Agent is fixing..." message
  - [x] `cell_update` → update the source of an existing cell (animate the change briefly)
  - [x] `phase_transition` → insert a markdown cell with the phase title as a section header
  - [x] `backtrack` → show a yellow "backtracking" notification that auto-dismisses after the fix is applied
  - [x] `complete` → show a green "EDA Complete" banner, enable the Story tab

- [x] Update `notebookStore.ts`:
  - [x] Add `appendCellWithContent(cell: Cell)` — appends a fully-formed cell
  - [x] Add `setCellExecuting(cell_id: string, executing: boolean)` — toggles spinner state
  - [x] Add `setCellError(cell_id: string, error: string | null)` — toggles error state
  - [x] Add cell state fields: `executing: boolean`, `error: string | null`, `thinking: string | null`

- [x] Update `NotebookCell.tsx`:
  - [x] Show thinking block above cell when `cell.thinking` is set
  - [x] Show spinner overlay when `cell.executing` is true
  - [x] Show red left border + error output when `cell.error` is set
  - [x] Smooth scroll into view when a new cell is added (auto-follow mode)

- [x] Update `NotebookPane.tsx`:
  - [x] Add "auto-follow" toggle — when on (default during agent run), auto-scrolls to the latest cell
  - [x] Show phase transition headers as special markdown cells with a colored left border
  - [x] Show a progress indicator: "Phase 3 of 12: Checking for missing values..."

### Thinking blocks UI

- [x] Create `frontend/src/components/notebook/ThinkingBlock.tsx`:
  - [x] Collapsible block with a subtle background (light gray or light purple)
  - [x] Shows agent's reasoning text in italic
  - [x] Small brain/thought icon on the left
  - [x] Click to expand/collapse
  - [x] Auto-collapses when the next cell is written (to save space)
  - [x] Example: "I see 3 columns with missing values. Wind Direction has 2% missing — I'll forward-fill since it's a slowly-changing measurement. The other columns are complete."

---

## 7. Robust Ingestion Engine

### The ingestion must not silently fail

- [x] Create `src/agent/ingestion.py` — the first phase of the agent:
  - [x] Step 1: Load the file with appropriate reader (CSV/Excel/JSON/etc.)
    - Generate cell: `df = pd.read_csv(path)` (or appropriate reader)
    - Execute and check output
    - If load fails: try alternative encodings, delimiters, skip bad rows
  - [x] Step 2: Initial inspection
    - Generate cell: `print(df.shape); display(df.head()); display(df.dtypes)`
    - Parse output to build column inventory
  - [x] Step 3: Identify time column
    - Look for datetime-like columns in the dtypes/values
    - Generate cell to parse: `df['col'] = pd.to_datetime(df['col'], errors='coerce')`
    - Check how many parsed vs NaT
    - If > 5% NaT: investigate bad rows, try different formats, show the bad values
  - [x] Step 4: Clean up column names
    - If columns have spaces/special chars, rename them
    - Generate cell: `df.columns = [c.strip().replace(' ', '_') for c in df.columns]`
  - [x] Step 5: Type coercion
    - Identify numeric columns stored as strings
    - Generate cell: `df['col'] = pd.to_numeric(df['col'], errors='coerce')`
  - [x] Step 6: Handle bad rows
    - Show the bad rows to the user (in a cell output)
    - Drop or flag them (with explanation in a thinking block)
  - [x] Step 7: Missing value audit
    - Generate cell: `df.isnull().sum()` with a bar chart of missingness
    - Decide imputation strategy per column (thinking block explains why)
  - [x] Step 8: Save cleaned dataset
    - Generate cell: `df.to_csv('cleaned_data.csv', index=False)`
    - All subsequent analysis uses the cleaned DataFrame

- [x] Each step emits thinking events explaining WHY decisions are made
- [x] Each step handles errors gracefully — if something fails, the agent tries an alternative and shows both the error and the fix

---

## 8. Story Generation (post-agent)

- [x] After the agent loop completes, generate the story from the notebook cells and their outputs
- [x] The story is now a SUMMARY of what the agent did — not a parallel document
- [x] Each finding in the story links back to the specific cell that produced it
- [x] Keep the current story generation logic but feed it the actual notebook cell outputs instead of CompositeState fields

---

## 9. Migration Path

### What to keep
- [x] All deterministic analysis functions (tools/input_tools.py) — use them as CODE GENERATORS inside code_templates.py
- [x] The existing LangGraph pipeline phases as a GOAL CHECKLIST for the agent (not as the execution engine)
- [x] Frontend components (NotebookPane, CellOutput, StoryPane, ChatSidebar, etc.) — update, don't rewrite
- [x] Backend routers and services — update, don't rewrite

### What to replace
- [x] `src/pipeline.py` — replaced by `src/agent/eda_agent.py` (the pipeline becomes the agent's goal list, not the executor)
- [x] `backend/routers/run.py` — rewritten to start the agent loop instead of the pipeline
- [x] `backend/routers/stream.py` — updated with new event types
- [x] `frontend/src/hooks/useAgentStream.ts` — updated to handle new event types
- [x] `frontend/src/hooks/useKernel.ts` — replaced by real kernel integration (server-side execution for agent, WebSocket for user)

### What to add
- [x] `src/agent/` — new directory: eda_agent.py, state.py, goals.py, code_templates.py, ingestion.py
- [x] `backend/models/events.py` — new event types
- [x] `backend/services/kernel_manager.py` — rewrite with real kernel execution
- [x] `frontend/src/components/notebook/ThinkingBlock.tsx` — new component

---

## 10. Implementation Order

### Sprint A: Kernel + Streaming Foundation
- [x] Rewrite `backend/services/kernel_manager.py` with real IPython kernel execution
- [x] Create `backend/models/events.py` with all event types
- [x] Update `backend/routers/stream.py` with new event protocol
- [x] Test: can execute Python code server-side and get structured outputs

### Sprint B: Agent Loop Core
- [x] Create `src/agent/__init__.py`, `src/agent/state.py`, `src/agent/goals.py`
- [x] Create `src/agent/code_templates.py` with first 5 templates (load, inspect, datetime, missing, describe)
- [x] Create `src/agent/eda_agent.py` with the main loop
- [x] Create `src/agent/ingestion.py` with the robust ingestion sequence
- [x] Test: agent can load a CSV, inspect it, parse datetime, all visible as events

### Sprint C: Full EDA Goals
- [x] Add remaining code templates (plots, seasonality, correlation, rolling, split, summary)
- [x] Add LLM decision-making for ambiguous steps (which imputation strategy, which columns to focus on)
- [x] Add backtracking logic (cell errors → generate fix → retry)
- [x] Test: agent completes full EDA on T1_slice.csv and FREDtest.csv

### Sprint D: Frontend Streaming
- [x] Update `useAgentStream.ts` for all new event types
- [x] Update `notebookStore.ts` with executing/error/thinking state
- [x] Create `ThinkingBlock.tsx`
- [x] Update `NotebookCell.tsx` with spinner, error border, thinking
- [x] Update `NotebookPane.tsx` with auto-follow and progress indicator
- [x] Test: upload file → watch agent work in real time in the browser

### Sprint E: Polish + Story
- [x] Update story generation to use notebook cell outputs
- [x] Update chat agent to reference specific cells
- [x] Error handling: if agent gets stuck, show a "retry" or "skip" button
- [x] Performance: stream events with minimal latency
- [x] Test: full flow on 3+ different datasets (CSV, Excel, JSON)
