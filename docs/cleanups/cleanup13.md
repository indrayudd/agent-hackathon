# Cleanup 13: Recycle Subagent Tabs + Fix Top Bar Phase + True Parallelism

## Issues

### 1. Tabs accumulate across loops
With 2 loops × 2 subagents, 4 investigation tabs appear. User wants N fixed tabs ("Agent 1", "Agent 2") that get recycled each loop, with clear loop demarcation inside each tab.

### 2. Top bar shows hypothesis names during parallel execution
The spinner shows "Hypothesis 2/2: Outliers correspond to..." which is misleading since execution is parallel. Should show "Investigation Loop 1/2" only.

### 3. True parallelism
`ThreadPoolExecutor` uses threads (GIL). However, since subagent work is I/O-bound (kernel execution via IPC, LLM API calls), the GIL is released during these operations and threads DO run in true parallel. `ProcessPoolExecutor` won't work because `push_event` and `execute_code` callbacks aren't picklable. ThreadPoolExecutor is the correct choice — just document this.

## Fixes

### Fix 1: Recycle N fixed tabs
**Backend (`eda_agent.py`):**
- Change `notebook_id` from `f"investigation_{hyp.id}"` to `f"agent_{i+1}"` (where i is the subagent index 0..N-1)
- Each loop reuses the same N notebook IDs
- Before each loop, push a `"notebook_clear"` event for each agent tab so the frontend clears old cells
- Each loop's cells in a tab start with a markdown divider: `"## Loop {loop_num}: {hyp.title}"`

**Frontend (`notebookStore.ts`):**
- Add `clearNotebookCells(id)` method
- On `notebook_clear` event, wipe cells for that notebook

**Frontend (`useAgentStream.ts`):**
- Handle `notebook_clear` event
- On `subagent_start`, update the tab title (don't create new tab if it exists, just rename)

**Frontend (`NotebookTabs.tsx`):**
- Show tab as "Agent 1", "Agent 2" etc. with the current hypothesis title as subtitle

### Fix 2: Top bar shows loop phase only
**Backend (`eda_agent.py`):**
- Remove the per-hypothesis `phase_transition` event (line 636-641)
- The loop-level phase transition at line 530 already sets "Investigation Loop 1/2"
- Keep `subagent_start` events (they drive tab status, not the top bar)

### Fix 3: Document parallelism choice
Add a comment in eda_agent.py explaining why ThreadPoolExecutor is correct for I/O-bound kernel+LLM work.
