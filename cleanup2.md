# cleanup2.md — UX Polish: Status, Chat-as-Log, Scroll, Execution Indicators

## Issues from user testing

1. **No completion indicator** — user doesn't know when agent is done
2. **Story tab infinite loading** — story never gets generated/saved, 404 forever
3. **No intermediate reasoning visible** — thinking blocks exist but aren't surfacing in chat
4. **Chat sidebar should double as activity log** — show what the LLM is doing in real time, ending with "EDA complete" when done
5. **No execution indicators on cells** — can't tell which cells were run vs not
6. **Markdown cells render raw** — `\n` showing literally, not as newlines
7. **Code cell scroll traps cursor** — scrolling inside a Monaco editor cell doesn't propagate to the page when the cell's scroll reaches its end

---

## Fix 1: Chat sidebar as live activity log

The chat sidebar should show agent activity in real time during the run:
- Each `thinking` event → agent message in chat: "Thinking: {content}"
- Each `phase_transition` → agent message: "Starting {phase}..."
- Each `cell_write` (code) → agent message: "Writing code: {first line}..."
- Each `cell_error` → agent message: "Error encountered: {error}. Fixing..."
- Each `backtrack` → agent message: "Backtracking: {reason}"
- `complete` → agent message: "EDA complete! {summary}. Switch to the Story tab to see the narrative report."

- [x] Update `frontend/src/hooks/useAgentStream.ts`:
  - On each event, also push a message to chatStore via `addAgentMessage()`
  - `thinking` → type "text", content is the thinking text
  - `phase_transition` → type "text", content: "**{phase}**: {message}"
  - `cell_write` for code → type "cell_ref", content: "Writing: `{source first 60 chars}...`", cell_id set
  - `cell_error` → type "text", content: "Error: {error}. Attempting fix..."
  - `backtrack` → type "text", content: "Backtracking: {reason}"
  - `complete` → type "text", content: "EDA complete! {summary}"
  - DON'T flood chat — skip `cell_executing` and `cell_output` events (too noisy)

- [x] Update `frontend/src/components/chat/ChatSidebar.tsx`:
  - Remove the hardcoded welcome message on mount
  - The first message should come from the agent stream naturally

---

## Fix 2: Completion indicator + story generation

- [x] Update `backend/routers/run.py` (`_run_agent_in_thread`):
  - After agent completes, generate a simple story JSON from agent state findings
  - Write it to `sessions/{id}/story.json`
  - Structure: `{title, executive_summary, sections: [{phase, title, content, plots, insights}], generated_at}`
  - This is deterministic (no LLM needed) — just format the findings

- [x] Update `frontend/src/hooks/useAgentStream.ts`:
  - On `complete` event, set `pipelineRunning = false`
  - Wait 500ms then fetch story (give backend time to write it)

- [x] Update `frontend/src/components/story/StoryPane.tsx`:
  - If story fetch returns 404 AND pipeline is not running, show "No story yet. Run EDA first." instead of infinite spinner
  - If pipeline is running, show "Generating... please wait"
  - Add a retry button

---

## Fix 3: Cell execution indicators

- [x] Update `frontend/src/components/notebook/NotebookCell.tsx`:
  - Cells that have been executed (have outputs or execution_count != null) get a green left border + filled execution count badge `[1]:`
  - Cells that have NOT been executed get a gray left border + empty badge `[ ]:`
  - When `cell.executing` is true: pulsing blue border + spinner in the badge area
  - The execution count should increment: first executed cell = `[1]:`, second = `[2]:`, etc.

- [x] Update `frontend/src/stores/notebookStore.ts`:
  - Track `executionCounter: number` (increments each time a cell finishes executing)
  - When `cell_output` arrives, set that cell's `execution_count = ++executionCounter`

---

## Fix 4: Markdown cell rendering

- [x] Update `frontend/src/components/notebook/NotebookCell.tsx`:
  - For markdown cells in VIEW mode: replace literal `\n` in source with actual newlines before rendering with react-markdown
  - Ensure markdown cells render as formatted text, not raw source with escape sequences

---

## Fix 5: Code cell scroll propagation

- [x] Update `frontend/src/components/notebook/CodeEditor.tsx`:
  - Set Monaco option `scrollBeyondLastLine: false` (already set)
  - Set `overviewRulerLanes: 0` to remove overview ruler
  - Set `scrollbar: { alwaysConsumeMouseWheel: false }` — THIS is the key fix. When false, Monaco passes scroll events to the parent when it reaches the top/bottom of its content.

---

## Fix 6: Summary markdown cell formatting

- [x] Update `src/agent/code_templates.py`:
  - `summary_markdown()`: use real newlines in the returned string, not `\\n`
  - Other templates: ensure markdown cells use real newlines

---

## Implementation order

All fixes are independent — implement in parallel.
