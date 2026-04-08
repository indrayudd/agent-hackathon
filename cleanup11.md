# Cleanup 11: Error Correction Flow & Backtracking Messages

## Problems
1. Error cells with long tracebacks stay visible (the delete→rewrite flow has a race)
2. "Oops" messages in 4 places — unprofessional
3. Only 1 retry attempt; second failure silently abandoned with error cell left visible
4. No visual indication that a fix is being attempted (just "Oops" in activity log)
5. Traceback cells from Image 24 persist in the notebook view

## Root Cause Analysis
The cell_delete → cell_write flow should work, but:
- If the LLM fix attempt also fails, the error cell stays with its traceback forever
- The backtracking reason says "Oops" which looks unprofessional
- The `_try_fix_error` function only tries once — a second failure is silently caught

## Fixes

### Task 1: Professional backtracking messages (backend + frontend)
Replace all "Oops" with professional alternatives:
- Backend eda_agent.py: "Oops — retrying" → "Retrying with corrected code"
- Backend subagent.py: "Oops - fixing" → "Correcting error in investigation"
- Frontend useAgentStream.ts: "Oops:" → "Fixing:" and "Oops -" → "Correcting:"

### Task 2: Clear error cells on successful fix (frontend)
In notebookStore.ts, when overwriteCell or appendCell with markFixed is called,
ensure the previous error outputs are completely cleared — not just the error flag.

### Task 3: Second retry attempt (backend)
In eda_agent.py `_try_fix_error`, if the first fix fails, try ONE more time with
additional context about what went wrong. Max 3 total attempts (original + 2 fixes).

### Task 4: Error cell cleanup on final failure (frontend)
If a cell fails even after retries, collapse the traceback into a summary line
instead of showing the full stack trace. Show a "Cell failed" badge.
