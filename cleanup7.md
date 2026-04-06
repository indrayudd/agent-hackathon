# cleanup7.md — Per-Hypothesis Notebooks + Parallel Execution + Dedup Fix

## Problems
1. Duplicate cell_id keys crash React (cell_29, cell_30 etc appear twice)
2. All hypothesis investigations dump into one giant notebook — unnavigable
3. Subagent cell counters collide with main agent counter

## Solution: Notebook-per-Hypothesis Architecture

Each hypothesis investigation creates its OWN notebook (displayed as a sub-tab
or expandable section in the Files sidebar). The main notebook contains only
pass 1 (load, clean, plot, stats) + any chat-driven cells. Hypothesis notebooks
are linked from the main notebook and the story.

## Fixes

### 1. Deduplicate cells in notebookStore
- [x] Update `frontend/src/stores/notebookStore.ts` `appendCell`:
  reject cells with IDs that already exist in the array

### 2. Unique cell IDs per subagent
- [x] Update `src/agent/subagent.py`: prefix cell IDs with hypothesis ID
  e.g. `h3_cell_1` instead of `cell_29`

### 3. Separate notebooks per hypothesis
- [x] Update `src/agent/eda_agent.py`: subagent cells go to a separate
  stream channel (hypothesis-specific) so they don't pollute the main notebook
- [x] Each hypothesis pushes a `notebook_create` event with a notebook ID
- [x] Frontend: hypothesis notebooks shown as sub-items in Files sidebar

### 4. Main notebook stays clean
- [x] The main notebook only contains pass 1 goals + a "## Investigations"
  section with links/summaries to each hypothesis notebook
- [x] Chat-driven cells appear in the main notebook

### 5. Frontend: Files sidebar shows hypothesis notebooks
- [x] Each hypothesis notebook appears as a clickable item
- [x] Clicking switches the NotebookPane to show that hypothesis's cells
- [x] A "Main Notebook" item always exists at the top
