# Cleanup 14: Sync Story Pane spinner with Execution Plan

## Problem

When clicking the Story tab before the report is generated, a hardcoded spinner at `frontend/src/components/story/StoryPane.tsx:358-386` shows four steps that progress on a timer (`retryCount`):

1. "Building sections from knowledge graph" (retryCount >= 1)
2. "Curating plots and generating captions" (retryCount >= 3)
3. "Writing executive summary" (retryCount >= 5)
4. "Finalizing report" (retryCount >= 7/9)

These steps are fake — they advance on a polling timer, not actual backend progress. Meanwhile, the Execution Plan in the chat sidebar shows real progress via `plan_update` stream events, including a "Report Generation" phase with actual sub-items.

This creates a mismatch: the Execution Plan may show "Report Generation" as complete while the Story spinner still shows "Finalizing report" with a loading indicator.

## Fix

Replace the hardcoded story spinner steps with data from `planSteps` in `notebookStore`, or at minimum tie the Story pane's display to `pipelineRunning` and the plan's "Report Generation" status.

### Option A: Use planSteps directly (preferred)

In `StoryPane.tsx`, read `planSteps` from the notebook store and derive the story generation progress from the "Report Generation" step's status/details instead of the `retryCount` timer.

```tsx
const planSteps = useNotebookStore((s) => s.planSteps);
const reportStep = planSteps.find((s) => s.phase === "Report Generation");
const reportDone = reportStep?.status === "complete";
```

- If `reportStep` exists and is `"current"`, show the spinner with real sub-items from `reportStep.details`
- If `reportStep` is `"complete"`, stop spinning and either show the story or show "Loading story..."
- Fall back to the current timer-based display if `planSteps` is empty (e.g., page reloaded mid-generation)

### Option B: Simpler — just hide the fake steps

Remove the four hardcoded steps entirely and show a single spinner with "Generating story report..." until the story JSON arrives. Less informative but at least not misleading.

## Files to modify

| File | Change |
|------|--------|
| `frontend/src/components/story/StoryPane.tsx` | Lines 358-386: Replace hardcoded progress steps with planSteps-driven display |

## Scope

Small — purely frontend, one component, ~20 lines changed.
