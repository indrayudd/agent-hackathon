# Plan 14: Execution Plan View in Chat Sidebar

## Overview

Add a persistent "Execution Plan" card at the top of the chat sidebar that shows the agent's high-level goals as a vertical stepper. Completed goals are struck through, the current goal pulses, and upcoming goals are dimmed. This is distinct from Agent Actions (granular cell-level steps) — the plan shows only the overarching phases.

## Design Reference

From the mockup, the plan card sits inside the chat sidebar above the message history:

- **Container**: `bg-surface-container-lowest border border-outline-variant/10 rounded-2xl shadow-sm`
- **Header**: `list_alt` icon + "EXECUTION PLAN" label in primary color, uppercase, `font-headline font-bold text-xs tracking-widest`
- **Steps**: vertical stepper with connecting lines between circles
  - **Completed**: solid `bg-primary` circle with white `check` icon, text is `line-through text-on-surface-variant/60`
  - **Current**: `bg-primary/10` circle with `ring-2 ring-primary` and inner `animate-pulse` dot, text is `font-bold text-on-surface`
  - **Upcoming**: `border-2 border-outline-variant/30` empty circle, text is `opacity-50 text-on-surface-variant`
  - **Connector lines**: completed = `bg-primary`, current/upcoming = `bg-outline-variant/20`
  - Step label: `text-[11px] font-bold`

## Data Flow

### Backend

The backend already has a `goals` list (`src/agent/goals.py`) with `name`, `phase`, and `description` for each EDA goal. The agent iterates through these and calls `state.mark_phase_done(goal.phase)` after each completes. We need to:

1. **New stream event `plan_update`**: Emitted whenever the plan state changes (goal started, completed, or skipped). Payload:

```json
{
  "type": "plan_update",
  "goals": [
    { "name": "load_dataset", "phase": "Data Loading", "description": "Load the dataset and display first rows", "status": "complete" },
    { "name": "inspect_dtypes", "phase": "Data Loading", "description": "Show column types and shape", "status": "complete" },
    { "name": "distributions", "phase": "Univariate Analysis", "description": "Plot distributions of numeric columns", "status": "current" },
    { "name": "correlations", "phase": "Correlations", "description": "Compute correlation matrix", "status": "upcoming" },
    ...
  ]
}
```

- `status` values: `"complete"`, `"current"`, `"skipped"`, `"upcoming"`

2. **Emit points** in `eda_agent.py`:
   - After `build_goal_checklist()` — emit initial plan with all goals as `"upcoming"`
   - At the start of each goal iteration (before `_transition()`) — mark it `"current"`, previous as `"complete"` or `"skipped"`
   - After `state.mark_phase_done()` — mark that goal `"complete"`
   - When a goal is skipped via `goal.should_skip()` — mark it `"skipped"` (skipped goals are hidden from the UI or shown dimmed with a skip icon)
   - At investigation phase start — add a synthetic `"investigation"` goal as `"current"`
   - At `"complete"` event — mark all remaining as `"complete"`

3. **Collapse to phases**: The goals list has many sub-goals per phase. The plan view should show **unique phases only** (Data Loading, Data Cleaning, Univariate Analysis, Time Series, Dynamics, Correlations, Train/Test Split, Investigation, Summary). Derive phase status from its constituent goals: phase is `"complete"` when all its goals are complete/skipped, `"current"` when any goal is current, otherwise `"upcoming"`.

4. **Helper function** `_build_plan_payload(goals, state, current_goal_name)` in `eda_agent.py`:
   - Iterates goals, groups by phase
   - Returns list of `{ phase, status }` dicts
   - Called at each emit point

### Frontend

#### New store fields in `notebookStore.ts`

```typescript
interface PlanStep {
  phase: string;
  status: "complete" | "current" | "skipped" | "upcoming";
}

// Add to NotebookState:
planSteps: PlanStep[];
setPlanSteps: (steps: PlanStep[]) => void;
```

Reset `planSteps` to `[]` in `resetForNewSession`.

#### Stream handler in `useAgentStream.ts`

```typescript
case "plan_update": {
  // Collapse goals to unique phases
  const phases: PlanStep[] = [];
  const seen = new Set<string>();
  for (const g of data.goals || []) {
    if (seen.has(g.phase)) {
      // Upgrade phase status: current > complete > skipped > upcoming
      const existing = phases.find(p => p.phase === g.phase);
      if (existing && g.status === "current") existing.status = "current";
    } else {
      seen.add(g.phase);
      phases.push({ phase: g.phase, status: g.status });
    }
  }
  store.setPlanSteps(phases);
  break;
}
```

**Alternative**: Do the phase collapsing on the backend side so the frontend just stores whatever arrives. Simpler. Preferred approach.

#### New component: `ExecutionPlan.tsx`

Location: `frontend/src/components/chat/ExecutionPlan.tsx`

Props: none (reads from `useNotebookStore` directly via the hook).

Renders:
- Only visible when `planSteps.length > 0`
- Card container matching the mockup design
- Vertical stepper with the three visual states (complete/current/upcoming)
- Skipped goals are hidden entirely (they were conditionally skipped, not relevant to user)

```tsx
export default function ExecutionPlan() {
  const planSteps = useNotebookStore((s) => s.planSteps);
  if (planSteps.length === 0) return null;

  // Filter out skipped steps
  const visibleSteps = planSteps.filter(s => s.status !== "skipped");

  return (
    <div className="p-4 bg-surface-container-lowest border border-outline-variant/10 rounded-2xl shadow-sm space-y-4 mb-4">
      {/* Header */}
      <div className="flex items-center gap-2 text-primary">
        <span className="material-symbols-outlined text-[18px]">list_alt</span>
        <span className="font-headline font-bold text-xs uppercase tracking-widest">Execution Plan</span>
      </div>

      {/* Steps */}
      <div className="space-y-0">
        {visibleSteps.map((step, i) => {
          const isLast = i === visibleSteps.length - 1;
          return (
            <div key={step.phase} className="flex gap-3">
              <div className="flex flex-col items-center">
                {/* Circle */}
                {step.status === "complete" ? (
                  <div className="w-5 h-5 rounded-full bg-primary flex items-center justify-center">
                    <span className="material-symbols-outlined text-[14px] text-white">check</span>
                  </div>
                ) : step.status === "current" ? (
                  <div className="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center ring-2 ring-primary">
                    <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                  </div>
                ) : (
                  <div className="w-5 h-5 rounded-full border-2 border-outline-variant/30 bg-transparent" />
                )}
                {/* Connector line */}
                {!isLast && (
                  <div className={`w-0.5 h-6 ${
                    step.status === "complete" ? "bg-primary" : "bg-outline-variant/20"
                  }`} />
                )}
              </div>
              {/* Label */}
              <div className="pt-0.5">
                <p className={`text-[11px] font-bold ${
                  step.status === "complete"
                    ? "text-on-surface-variant/60 line-through"
                    : step.status === "current"
                    ? "text-on-surface"
                    : "text-on-surface-variant opacity-50"
                }`}>
                  {step.phase}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

#### Integration in `ChatSidebar.tsx`

Place `<ExecutionPlan />` at the top of the scrollable messages area, before the chat messages:

```tsx
<div className="flex-1 overflow-y-auto p-4 space-y-6">
  <ExecutionPlan />
  {/* ...existing messages... */}
</div>
```

### Persistence / Reload

When a user refreshes the page, the WebSocket reconnects but the plan state is lost. Two options:

- **Option A (simple)**: Add a `/api/plan/{session_id}` REST endpoint that returns the current plan state from `AgentState`. The session page fetches it on mount alongside existing status checks.
- **Option B**: Reconstruct from the activity log on reconnect. Less reliable.

**Go with Option A.** Add to `backend/routers/run.py`:

```python
@router.get("/plan/{session_id}")
async def get_plan(session_id: str):
    state = _get_state(session_id)
    if not state:
        return {"goals": []}
    return {"goals": _build_plan_payload(state)}
```

Frontend fetches this on page load (in the session page `useEffect`) and calls `setPlanSteps()`.

## Files to Modify

| File | Change |
|------|--------|
| `src/agent/eda_agent.py` | Add `_build_plan_payload()` helper. Emit `plan_update` events at goal start/complete/skip/investigation start/complete. |
| `backend/routers/run.py` | Add `GET /plan/{session_id}` endpoint. Store plan state in session state dict. |
| `frontend/src/stores/notebookStore.ts` | Add `planSteps: PlanStep[]` and `setPlanSteps()`. Reset in `resetForNewSession`. |
| `frontend/src/hooks/useAgentStream.ts` | Handle `plan_update` event type. |
| `frontend/src/components/chat/ExecutionPlan.tsx` | **New file** — the plan stepper component. |
| `frontend/src/components/chat/ChatSidebar.tsx` | Import and render `<ExecutionPlan />` at top of messages area. |
| `frontend/src/app/session/[id]/page.tsx` | Fetch `/plan/{session_id}` on mount and hydrate store. |

## Implementation Order

1. Backend: `_build_plan_payload()` helper + `plan_update` event emission in `eda_agent.py`
2. Backend: REST endpoint `GET /plan/{session_id}`
3. Frontend: Store additions (`planSteps`, `setPlanSteps`)
4. Frontend: `useAgentStream.ts` — handle `plan_update`
5. Frontend: `ExecutionPlan.tsx` component
6. Frontend: `ChatSidebar.tsx` — integrate component
7. Frontend: Session page — fetch plan on mount
8. Test end-to-end with a dataset upload

## Edge Cases

- **All goals skipped**: Plan card hidden (no visible steps)
- **Investigation phase**: Synthetic "Deep Investigation" step added after all structured goals
- **Chat-triggered investigations**: Don't update the main plan (they're separate)
- **Multiple loops**: Investigation step stays `"current"` through all loops, only completes at the `"complete"` event
- **Error/timeout in goal**: Goal still marked complete (agent moved past it), error details are in Agent Actions not the plan
