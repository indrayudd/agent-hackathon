# Cleanup 7: Multi-Notebook Orchestrator with Subagent Isolation

## Problem Statement

1. **Loop 2 never runs** — The LLM stop condition at the end of loop 1 returns "STOP" prematurely. For small datasets the LLM thinks 2 conclusions are "sufficient understanding."

2. **No notebook isolation** — All cells (main EDA + all investigations) dump into one flat `cells[]` array. No visual separation between orchestrator work and each subagent's work.

3. **No "waiting for subagents" state** — The main agent should show it's waiting while subagents run, then compile results when they return — like Claude Code's subagent pattern.

## Target Architecture

```
Main Orchestrator Notebook (always visible, "main" tab)
  ├─ Initial EDA cells (load, dtypes, distributions, etc.)
  ├─ "⏳ Dispatched 2 subagents for Loop 1..." [waiting state cell]
  ├─ "✅ Subagent results compiled" [compilation summary cell]
  ├─ Main agent follow-up analysis cells  
  ├─ "⏳ Dispatched 2 subagents for Loop 2..." [waiting state cell]
  ├─ "✅ Subagent results compiled" [compilation summary cell]
  └─ Conclusions

Investigation: Wind vs Power  (separate tab, own cells)
  ├─ Hypothesis description markdown
  ├─ Analysis code cells (scatter, regression, etc.)
  └─ Finding + confidence markdown

Investigation: Outlier Regimes  (separate tab, own cells)
  ├─ Hypothesis description markdown
  ├─ Analysis code cells
  └─ Finding + confidence markdown
```

## Spec

### Backend Changes

#### 1. Remove LLM Stop Condition (eda_agent.py)
Delete the "Should we investigate further?" LLM call at the end of each loop. Always run all M loops unless:
- No novel hypotheses exist (already handles this with `if not hypotheses: break`)
- All subagents failed (already handles with `if not results: break`)

#### 2. Add notebook_id="main" to All Main Agent Events (eda_agent.py)
Currently only subagent cells include `notebook_id`. Add `"notebook_id": "main"` to every `push_event` call in `_write_and_run()` and `_think()`.

#### 3. Waiting + Compilation Cells in Main Notebook (eda_agent.py)
Before dispatching subagents:
```python
_write_and_run(f"⏳ **Dispatched {len(hypotheses)} subagents** for Investigation Loop {loop_num}...\n\nWaiting for results.", "markdown")
```

After all subagents return, write a compilation summary:
```python
compilation = "## 📋 Loop {loop_num} Results\n\n"
for result in results:
    compilation += f"### {result.hypothesis_title}\n"
    compilation += f"**Finding:** {result.finding}\n"
    compilation += f"**Confidence:** {result.confidence:.0%}\n\n"
_write_and_run(compilation, "markdown")
```

#### 4. New Events: subagents_dispatched / subagents_returned
```python
push_event(session_id, {
    "type": "subagents_dispatched",
    "loop_number": loop_num,
    "count": len(hypotheses),
    "hypothesis_ids": [h.id for h in hypotheses],
})
# ... after gather ...
push_event(session_id, {
    "type": "subagents_returned",
    "loop_number": loop_num,
    "results_count": len(results),
})
```

#### 5. Save Per-Notebook .ipynb Files (run.py)
After agent completes, save:
- `notebook.ipynb` — main orchestrator cells only (notebook_id == "main" or no notebook_id)
- `notebooks/investigation_{id}.ipynb` — per investigation

### Frontend Changes

#### 6. Multi-Notebook Store (notebookStore.ts)
Replace `cells: Cell[]` with:
```typescript
notebooks: Record<string, { id: string; title: string; cells: Cell[]; status: "idle" | "running" | "complete" }>;
activeNotebookId: string; // "main" by default
```

Keep backward compat by computing a flat `cells` getter from `notebooks["main"].cells`.

Add methods:
- `ensureNotebook(id, title)` — create notebook entry if not exists
- `appendCellToNotebook(notebookId, cell)` — add cell to specific notebook
- `setActiveNotebook(id)` — switch active tab
- `setNotebookStatus(id, status)` — update running/complete

#### 7. Event Routing (useAgentStream.ts)
Route `cell_write`, `cell_output`, `cell_error`, `cell_executing` events to the notebook identified by `data.notebook_id || "main"`.

Handle new events:
- `subagent_start` → `ensureNotebook(notebook_id, title)` + `setNotebookStatus(notebook_id, "running")`
- `subagent_complete` → `setNotebookStatus(notebook_id, "complete")`
- `subagents_dispatched` → show waiting indicator on main notebook
- `subagents_returned` → clear waiting indicator

#### 8. Notebook Tabs UI (new NotebookTabs component)
Tab bar between the toolbar and the cell list:
```
[📋 Main] [🔍 Wind vs Power ✅] [🔍 Outlier Regimes 🔄]
```
- Main tab always first, always present
- Investigation tabs appear as subagents start
- Badge: 🔄 running, ✅ complete, ⏱ timeout
- Clicking a tab sets `activeNotebookId` and renders only that notebook's cells

## Implementation Order

1. Backend: Remove LLM stop condition + add notebook_id to main events + waiting/compilation cells + new event types
2. Frontend: Multi-notebook store refactor  
3. Frontend: Event routing by notebook_id
4. Frontend: Notebook tabs UI
5. Backend: Per-notebook .ipynb saving
6. Integration test via Playwright
