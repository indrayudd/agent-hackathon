# Run Steering Design

## Goal

Add user guidance at two points in the AgenticEDA workflow:

- before a run starts, through an optional research direction on the upload page
- during an active run, through chat messages that are queued as steering and read by the agent at safe execution gaps

## Current Context

The upload page is implemented in `frontend/src/components/upload/DropZone.tsx`.
It uploads the dataset, calls `runEda()`, and navigates to the session page.
`runEda()` posts to `POST /run/{session_id}` with the run configuration.

The active run is launched by `backend/routers/run.py`, which creates a
background thread and calls `src.agent.eda_agent.run_agent()`.

The chat sidebar currently uses `frontend/src/hooks/useChat.ts` and
`POST /chat/{session_id}/message`. That flow is appropriate when the run is
idle because it answers questions, performs notebook actions, or starts a
follow-up investigation.

During active runs, user messages should not use that post-run chat path.
They should be queued as steering for the running agent.

## Reference Pattern

The reference project `/Users/indro/Projects/Claude Code Leak` uses a queue
pattern for mid-run agent messages:

- messages to a running agent are accepted immediately
- they are queued for delivery
- the running agent drains them at its next tool round
- the UI distinguishes queued delivery from delivered/read state

AgenticEDA should use the same concept, adapted to this app's notebook-first
UX. The user does not want an extra agent acknowledgement bubble. The visual
cues should be:

- the user's own chat bubble changing from queued to read
- subsequent generated notebook cells or subagent tabs reflecting the steering
- optional markdown acknowledgement cells when steering changes the run direction

## Product Behavior

### Upload Research Direction

The upload form gets an optional multiline text area labeled `Research direction`.
Example placeholder:

`Focus on downtime patterns, sensor drift, and anomalies before modeling.`

When the user clicks `Run EDA`, the frontend includes this value in the run
configuration as `research_direction`.

The backend stores it in the run state and passes it into `run_agent()`.

The agent uses this text as run context:

- include it in the initial notebook title/intro markdown
- include it in follow-up reasoning prompts
- include it in hypothesis generation context
- include it in subagent investigation prompts

If the field is blank, behavior is unchanged.

### Active-Run Steering

When `pipelineRunning` is true, the chat input treats user text as steering.
It does not call the normal chat endpoint.

The frontend:

- creates a user chat bubble immediately
- marks it as `Queued`
- calls `POST /run/{session_id}/steering`
- updates the bubble to `Read` when a `steering_read` stream event arrives
- does not create an agent response bubble for acknowledgement

When `pipelineRunning` is false, chat behavior remains unchanged:

- questions go to `POST /chat/{session_id}/message`
- current automatic hypothesis/investigation detection remains in place

### Backend Steering Queue

Add a small per-session queue service. It should be process-local like the
existing stream buffers and run registry.

Each steering item contains:

- `id`
- `session_id`
- `content`
- `created_at`
- `status`: `queued` or `read`
- `read_at`, optional

The queue API should provide:

- enqueue steering for a session
- drain queued items for a session
- inspect queued/read items for tests and optional debug
- clear a session queue when a session is deleted or a new run starts

### Agent Safe Gaps

The agent should drain steering only at safe gaps. Safe gaps are places where
the agent is between tool/cell operations and can adjust future decisions
without interrupting a currently running kernel cell.

Drain points:

- before each new EDA goal
- after each `_write_and_run()`
- before `decide_next_step()`
- before hypothesis generation
- before subagent dispatch

When the agent drains one or more steering messages:

- append them to `state.steering_notes`
- emit `steering_read` for each drained item
- emit a `thinking` event summarizing that steering has been incorporated
- write a short markdown cell before the next steered work when the steering
  materially affects direction

The markdown cell should be concise, for example:

`> Steering applied: Prioritize equipment A anomalies before correlations.`

### Prompt Integration

The agent should have a compact run guidance string:

- initial research direction, if any
- recent steering notes, newest last

This guidance should be passed into reasoning prompts in `src/agent/reasoning.py`
without replacing existing deterministic context.

Hypothesis generation should also receive the guidance so that deep
investigations can be biased toward the user's requested direction.

Subagent investigation prompts should include the relevant guidance so spawned
notebooks/cells visibly reflect the steering.

### Stream Events

Add stream events:

`steering_queued`

- optional; useful if enqueue happens through backend and the frontend wants
  server confirmation
- includes `message_id`, `content`, `status`

`steering_read`

- required
- emitted by the running agent when it drains the item
- includes `message_id`, `content`, `read_at`, and optionally `checkpoint`

`cell_write` may optionally include `steering_ids` when a cell was directly
influenced by steering. The first implementation can rely on the markdown
acknowledgement cell instead of per-cell metadata.

### Frontend Visual Design

Use existing chat styling. Do not add a new agent acknowledgement bubble.

For steering user messages:

- display the normal user bubble
- below the timestamp or next to it, show small status text:
  - `Queued`
  - `Read`
- while active run is in progress, input placeholder becomes
  `Steer the current run...`
- when idle, input placeholder remains `Ask about your data...`

The chat input must remain enabled during active runs unless a steering request
is actively being submitted. Current behavior disables only while `isTyping`;
that should not block steering during pipeline execution.

## Error Handling

If enqueue fails:

- keep the user's message visible
- mark it as `Failed`
- do not add an agent response bubble unless the existing chat error behavior is
  needed for idle chat

If the run completes before a queued steering message is read:

- the backend should leave it queued or mark it stale
- the frontend should stop showing active-run steering mode
- a future idle message should use the normal chat endpoint

The first implementation may leave unread messages as `Queued` after completion,
but should not crash or block report generation.

## Testing

Backend tests:

- steering service enqueues and drains FIFO
- draining marks items read
- run endpoint accepts `research_direction`
- `run_agent()` signature accepts `research_direction`
- agent state stores `research_direction` and `steering_notes`
- reasoning/hypothesis prompt builders include guidance when provided

Frontend verification:

- TypeScript build or lint should pass
- manual UI check should confirm upload textarea, active-run placeholder, and
  queued/read status rendering

## Out Of Scope

- interrupting a currently executing kernel cell
- replacing the existing idle chat investigation classifier
- persistent database-backed steering queues
- per-cell provenance UI beyond markdown acknowledgement cells
- multi-user conflict handling

