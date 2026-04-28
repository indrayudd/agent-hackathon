# Run Steering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional initial research direction and active-run steering messages that are queued, read at safe agent gaps, and reflected in notebook/subagent output.

**Architecture:** Add a small process-local steering queue service behind `POST /run/{session_id}/steering`. The frontend routes chat input to this endpoint while `pipelineRunning` is true and updates message status from stream events. The agent drains queued steering at safe boundaries and incorporates guidance into reasoning, hypothesis generation, and subagent prompts.

**Tech Stack:** FastAPI, Pydantic, Python dataclasses, pytest, Next.js, React, Zustand, TypeScript.

---

## File Structure

- `backend/services/steering_service.py`: new process-local FIFO queue with enqueue/drain/read state.
- `backend/routers/run.py`: extend run config, steering endpoint, queue lifecycle, and thread args.
- `backend/routers/stream.py`: no structural change expected, but new events flow through existing `push_event`.
- `backend/services/session_manager.py`: clear steering queue on delete if imported safely from router/service layer.
- `src/agent/state.py`: store `research_direction`, `steering_notes`, and consumed steering IDs.
- `src/agent/eda_agent.py`: accept `research_direction`, drain steering at safe gaps, emit `steering_read`, write steering acknowledgement markdown cells, and pass guidance to reasoning/hypothesis/subagents.
- `src/agent/reasoning.py`: accept optional guidance in `decide_next_step()`.
- `src/agent/hypothesis.py`: accept optional guidance in `generate_hypotheses()`.
- `src/agent/subagent.py`: accept optional guidance in `run_subagent()` and include it in the investigation prompt.
- `frontend/src/lib/types.ts`: add steering chat metadata statuses.
- `frontend/src/lib/api.ts`: add `research_direction` to `runEda()` config and add `sendSteering()`.
- `frontend/src/stores/chatStore.ts`: allow user messages with meta and status updates.
- `frontend/src/hooks/useChat.ts`: route active-run messages to steering instead of idle chat.
- `frontend/src/hooks/useAgentStream.ts`: handle `steering_read`.
- `frontend/src/components/upload/DropZone.tsx`: add research direction textarea.
- `frontend/src/components/chat/ChatInput.tsx`: active-run placeholder and steering-friendly disabled state.
- `frontend/src/components/chat/ChatMessage.tsx`: render queued/read/failed steering status in existing style.
- `tests/test_steering_service.py`: new unit tests for queue behavior.
- `tests/test_orchestrator.py`: extend signature/state tests.

---

### Task 1: Backend Steering Queue And API

**Files:**
- Create: `backend/services/steering_service.py`
- Modify: `backend/routers/run.py`
- Modify: `backend/services/session_manager.py`
- Test: `tests/test_steering_service.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write failing tests for steering queue FIFO/read behavior**

Add `tests/test_steering_service.py`:

```python
from backend.services.steering_service import (
    clear_steering,
    drain_steering,
    enqueue_steering,
    get_steering_items,
)


def test_enqueue_and_drain_steering_fifo():
    clear_steering("s1")

    first = enqueue_steering("s1", "focus on anomalies")
    second = enqueue_steering("s1", "compare weekends")

    assert first["status"] == "queued"
    assert second["status"] == "queued"

    drained = drain_steering("s1")

    assert [item["content"] for item in drained] == [
        "focus on anomalies",
        "compare weekends",
    ]
    assert all(item["status"] == "read" for item in drained)
    assert all(item["read_at"] for item in drained)
    assert drain_steering("s1") == []


def test_get_steering_items_returns_read_and_queued_items():
    clear_steering("s2")

    first = enqueue_steering("s2", "first")
    enqueue_steering("s2", "second")
    drain_steering("s2", limit=1)

    items = get_steering_items("s2")

    assert [item["id"] for item in items] == [first["id"], items[1]["id"]]
    assert [item["status"] for item in items] == ["read", "queued"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_steering_service.py -q
```

Expected: FAIL because `backend.services.steering_service` does not exist.

- [ ] **Step 3: Implement steering service**

Create `backend/services/steering_service.py`:

```python
"""Process-local steering queue for active AgenticEDA runs."""
from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

_LOCK = Lock()
_QUEUES: dict[str, list[dict]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def enqueue_steering(session_id: str, content: str, message_id: str | None = None) -> dict:
    """Append a steering message to a session queue."""
    item = {
        "id": message_id or str(uuid4()),
        "session_id": session_id,
        "content": content,
        "created_at": _now(),
        "status": "queued",
        "read_at": None,
    }
    with _LOCK:
        _QUEUES.setdefault(session_id, []).append(item)
        return dict(item)


def drain_steering(session_id: str, limit: int | None = None) -> list[dict]:
    """Mark queued steering messages as read and return them in FIFO order."""
    with _LOCK:
        items = _QUEUES.get(session_id, [])
        queued = [item for item in items if item.get("status") == "queued"]
        if limit is not None:
            queued = queued[:limit]
        read_at = _now()
        drained: list[dict] = []
        for item in queued:
            item["status"] = "read"
            item["read_at"] = read_at
            drained.append(dict(item))
        return drained


def get_steering_items(session_id: str) -> list[dict]:
    """Return all steering items for a session."""
    with _LOCK:
        return [dict(item) for item in _QUEUES.get(session_id, [])]


def clear_steering(session_id: str) -> None:
    """Remove all steering items for a session."""
    with _LOCK:
        _QUEUES.pop(session_id, None)
```

- [ ] **Step 4: Run steering service tests**

Run:

```bash
pytest tests/test_steering_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Write failing API/config tests**

Append to `tests/test_orchestrator.py`:

```python
class TestSteeringIntegration(unittest.TestCase):
    def test_run_config_accepts_research_direction(self):
        from backend.routers.run import RunConfig

        config = RunConfig(research_direction="focus on churn")

        assert config.research_direction == "focus on churn"

    def test_run_agent_accepts_research_direction(self):
        from src.agent.eda_agent import run_agent

        sig = inspect.signature(run_agent)

        assert "research_direction" in sig.parameters
        assert sig.parameters["research_direction"].default is None
```

- [ ] **Step 6: Run tests to verify they fail**

Run:

```bash
pytest tests/test_orchestrator.py::TestSteeringIntegration -q
```

Expected: FAIL because `RunConfig` and `run_agent()` do not yet include `research_direction`.

- [ ] **Step 7: Extend run router with research direction and steering endpoint**

Modify `backend/routers/run.py`:

```python
class RunConfig(BaseModel):
    max_subagents: int = 3
    max_loops: int = 2
    loop_timeout: int = 300
    seed: int | None = None
    research_direction: str | None = None


class SteeringRequest(BaseModel):
    content: str
    message_id: str | None = None
```

Import steering service:

```python
from backend.services.steering_service import (
    clear_steering,
    enqueue_steering,
    get_steering_items,
)
```

In `run_pipeline()`, clear old steering before starting the thread and pass the direction:

```python
    clear_steering(session_id)
```

Add to thread kwargs:

```python
            "research_direction": config.research_direction,
```

Extend `_run_agent_in_thread()` signature and `run_agent()` call with `research_direction`.

Add endpoint:

```python
@router.post("/run/{session_id}/steering")
async def enqueue_run_steering(session_id: str, req: SteeringRequest):
    """Queue user steering for a currently running agent."""
    try:
        get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")

    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Steering content is required")

    item = enqueue_steering(session_id, req.content.strip(), req.message_id)
    push_event(session_id, {
        "type": "steering_queued",
        "message_id": item["id"],
        "content": item["content"],
        "status": item["status"],
    })
    return item


@router.get("/run/{session_id}/steering")
async def get_run_steering(session_id: str):
    """Return steering queue state for debug/UI recovery."""
    try:
        get_session_dir(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"items": get_steering_items(session_id)}
```

- [ ] **Step 8: Clear steering on session deletion**

Modify `backend/services/session_manager.py` inside `delete_session()` before `shutil.rmtree(session_dir)`:

```python
    try:
        from backend.services.steering_service import clear_steering
        clear_steering(session_id)
    except Exception:
        pass
```

- [ ] **Step 9: Run backend tests**

Run:

```bash
pytest tests/test_steering_service.py tests/test_orchestrator.py::TestSteeringIntegration -q
```

Expected: PASS.

---

### Task 2: Agent Guidance And Safe-Gap Draining

**Files:**
- Modify: `src/agent/state.py`
- Modify: `src/agent/eda_agent.py`
- Modify: `src/agent/reasoning.py`
- Modify: `src/agent/hypothesis.py`
- Modify: `src/agent/subagent.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: Write failing state/signature tests**

Append to `tests/test_orchestrator.py`:

```python
class TestSteeringAgentState(unittest.TestCase):
    def test_agent_state_has_steering_fields(self):
        from src.agent.state import AgentState

        state = AgentState(
            dataset_path="/tmp/test.csv",
            session_id="test",
            research_direction="focus on downtime",
        )

        assert state.research_direction == "focus on downtime"
        assert state.steering_notes == []
        assert state.consumed_steering_ids == []

    def test_reasoning_accepts_guidance(self):
        from src.agent.reasoning import decide_next_step

        sig = inspect.signature(decide_next_step)

        assert "run_guidance" in sig.parameters

    def test_hypothesis_generation_accepts_guidance(self):
        from src.agent.hypothesis import generate_hypotheses

        sig = inspect.signature(generate_hypotheses)

        assert "run_guidance" in sig.parameters

    def test_subagent_accepts_guidance(self):
        from src.agent.subagent import run_subagent

        sig = inspect.signature(run_subagent)

        assert "run_guidance" in sig.parameters
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_orchestrator.py::TestSteeringAgentState -q
```

Expected: FAIL because the new fields/signatures do not exist.

- [ ] **Step 3: Add state fields**

Modify `src/agent/state.py`:

```python
    research_direction: str | None = None
    steering_notes: list[dict] = field(default_factory=list)
    consumed_steering_ids: list[str] = field(default_factory=list)
```

Add method:

```python
    def run_guidance(self) -> str:
        parts: list[str] = []
        if self.research_direction:
            parts.append(f"Initial research direction: {self.research_direction}")
        if self.steering_notes:
            notes = "\n".join(
                f"- {item.get('content', '')}" for item in self.steering_notes[-5:]
            )
            parts.append(f"Recent user steering:\n{notes}")
        return "\n\n".join(parts)
```

- [ ] **Step 4: Extend reasoning and hypothesis signatures**

Modify `src/agent/reasoning.py`:

```python
def decide_next_step(..., run_guidance: str = "") -> dict:
```

In both error and non-error human prompts, include:

```python
guidance_section = f"\n\nUser guidance for this run:\n{run_guidance}" if run_guidance.strip() else ""
```

Append `guidance_section` to the human content.

Modify `src/agent/hypothesis.py`:

```python
def generate_hypotheses(..., kg_context: str = "", run_guidance: str = "") -> list[Hypothesis]:
```

Include in prompt when present:

```python
guidance_section = f"\n\nUser guidance for this run:\n{run_guidance}\n" if run_guidance.strip() else ""
```

Place it before `For each hypothesis, consider:`.

- [ ] **Step 5: Extend subagent signature and prompt**

Modify `src/agent/subagent.py` `run_subagent()` signature:

```python
    run_guidance: str = "",
```

In the adaptive investigation system prompt, include:

```python
guidance_section = f"\n\nUser guidance for this investigation:\n{run_guidance}" if run_guidance.strip() else ""
```

Append it to the prompt that tells the subagent what to investigate.

- [ ] **Step 6: Extend `run_agent()` and add safe-gap drain helper**

Modify `src/agent/eda_agent.py` signature:

```python
    research_direction: str | None = None,
```

Construct state:

```python
    state = AgentState(
        dataset_path=dataset_path,
        session_id=session_id,
        research_direction=research_direction.strip() if research_direction else None,
    )
```

Add helper inside `run_agent()`:

```python
    def _drain_steering(checkpoint: str, *, acknowledge: bool = True) -> list[dict]:
        try:
            from backend.services.steering_service import drain_steering
            items = drain_steering(session_id)
        except Exception as exc:
            _LOG.warning("Steering drain failed at %s: %s", checkpoint, exc)
            return []

        for item in items:
            state.steering_notes.append(item)
            state.consumed_steering_ids.append(item["id"])
            push_event(session_id, {
                "type": "steering_read",
                "message_id": item["id"],
                "content": item["content"],
                "read_at": item.get("read_at"),
                "checkpoint": checkpoint,
            })

        if items and acknowledge:
            joined = "; ".join(item["content"] for item in items)
            _think(f"Steering incorporated: {joined[:180]}")
            _write_and_run(
                f"> Steering applied: {joined[:240]}",
                "markdown",
            )
        return items
```

Use `state.run_guidance()` when calling `decide_next_step()` and `generate_hypotheses()`.

Call `_drain_steering()`:

```python
        _drain_steering(f"before_goal:{goal.name}")
```

before each goal's transition.

Call after `_write_and_run()` returns by adding it near the end of `_write_and_run()` after registering the cell:

```python
        _drain_steering(f"after_cell:{target_cell_id}", acknowledge=False)
```

Call before `decide_next_step()` in `_interpret_and_follow_up()`:

```python
        _drain_steering(f"before_followup:{goal.name}")
```

- [ ] **Step 7: Pass guidance into hypothesis generation and subagents**

Find calls to `generate_hypotheses()` in `src/agent/eda_agent.py` and pass:

```python
run_guidance=state.run_guidance()
```

Find calls to `run_subagent()` and pass:

```python
run_guidance=state.run_guidance()
```

- [ ] **Step 8: Update title markdown**

In the initial title cell source, append this when present:

```python
        + (
            f"\n\n**Research direction:** {state.research_direction}"
            if state.research_direction else ""
        )
```

- [ ] **Step 9: Run agent steering tests**

Run:

```bash
pytest tests/test_orchestrator.py::TestSteeringAgentState tests/test_orchestrator.py::TestRunAgentSignature -q
```

Expected: PASS.

---

### Task 3: Frontend Upload Direction And Steering Chat

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/stores/chatStore.ts`
- Modify: `frontend/src/hooks/useChat.ts`
- Modify: `frontend/src/hooks/useAgentStream.ts`
- Modify: `frontend/src/components/upload/DropZone.tsx`
- Modify: `frontend/src/components/chat/ChatInput.tsx`
- Modify: `frontend/src/components/chat/ChatMessage.tsx`

- [ ] **Step 1: Run baseline frontend check**

Run:

```bash
cd frontend && npm run lint
```

Expected: record current status. If lint already fails for unrelated reasons, note the failures and still run it again after changes.

- [ ] **Step 2: Extend frontend types**

Modify `frontend/src/lib/types.ts`:

```typescript
export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  content: string;
  type: "text" | "cell_ref" | "action";
  cell_id?: string;
  meta?: {
    kind?: "investigation" | "action" | "info" | "steering";
    notebook_id?: string;
    hypothesis_id?: string;
    title?: string;
    status?: "started" | "running" | "complete" | "failed" | "timeout" | "queued" | "read";
    confidence?: number;
  };
  timestamp: string;
}
```

- [ ] **Step 3: Add API helpers**

Modify `frontend/src/lib/api.ts`:

```typescript
export async function runEda(
  sessionId: string,
  config?: {
    max_subagents?: number;
    max_loops?: number;
    loop_timeout?: number;
    seed?: number;
    research_direction?: string;
  },
): Promise<RunResponse> {
```

Add:

```typescript
export interface SteeringResponse {
  id: string;
  session_id: string;
  content: string;
  created_at: string;
  status: "queued" | "read";
  read_at?: string | null;
}

export async function sendSteering(
  sessionId: string,
  content: string,
  messageId: string,
): Promise<SteeringResponse> {
  const res = await fetch(`${API_BASE}/run/${sessionId}/steering`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, message_id: messageId }),
  });
  if (!res.ok) {
    throw new Error(`Steering failed: ${await readError(res)}`);
  }
  return res.json();
}
```

- [ ] **Step 4: Extend chat store**

Modify `frontend/src/stores/chatStore.ts`:

```typescript
  addUserMessage: (content: string, meta?: ChatMessage["meta"]) => string;
  updateMessageMeta: (id: string, meta: Partial<NonNullable<ChatMessage["meta"]>>) => void;
```

Implementation:

```typescript
  addUserMessage: (content, meta) => {
    const id = uuidv4();
    const msg: ChatMessage = {
      id,
      role: "user",
      content,
      type: "text",
      meta,
      timestamp: new Date().toISOString(),
    };
    set((s) => ({ messages: [...s.messages, msg] }));
    return id;
  },
  updateMessageMeta: (id, meta) =>
    set((s) => ({
      messages: s.messages.map((msg) =>
        msg.id === id ? { ...msg, meta: { ...(msg.meta || {}), ...meta } } : msg,
      ),
    })),
```

- [ ] **Step 5: Route active-run chat to steering**

Modify `frontend/src/hooks/useChat.ts`:

```typescript
import { sendSteering } from "@/lib/api";
```

At the start of `sendMessage`:

```typescript
      const notebookState = useNotebookStore.getState();
      if (notebookState.pipelineRunning) {
        const id = useChatStore.getState().addUserMessage(content, {
          kind: "steering",
          status: "queued",
        });
        try {
          await sendSteering(sessionId, content, id);
        } catch {
          useChatStore.getState().updateMessageMeta(id, {
            kind: "steering",
            status: "failed",
          });
        }
        return;
      }
```

Remove duplicate `addUserMessage()` from `ChatInput` to avoid double user bubbles. `ChatInput` should only call `onSend(trimmed)`.

- [ ] **Step 6: Handle stream events**

Modify `frontend/src/hooks/useAgentStream.ts` stream type union:

```typescript
  | { type: "steering_queued"; message_id: string; content?: string; status?: "queued" }
  | { type: "steering_read"; message_id: string; content?: string; read_at?: string; checkpoint?: string }
```

Add switch cases:

```typescript
          case "steering_queued":
            if (data.message_id) {
              chat.updateMessageMeta(data.message_id, { kind: "steering", status: "queued" });
            }
            break;

          case "steering_read":
            if (data.message_id) {
              chat.updateMessageMeta(data.message_id, { kind: "steering", status: "read" });
            }
            break;
```

- [ ] **Step 7: Add upload research direction textarea**

Modify `frontend/src/components/upload/DropZone.tsx`:

```typescript
  const [researchDirection, setResearchDirection] = useState("");
```

In `runEda()` config:

```typescript
        research_direction: researchDirection.trim() || undefined,
```

Add textarea in the configuration panel:

```tsx
          <label className="mt-4 flex flex-col gap-1 text-sm text-on-surface-variant font-body">
            Research direction (optional)
            <textarea
              value={researchDirection}
              onChange={(e) => setResearchDirection(e.target.value)}
              rows={3}
              placeholder="Focus the analysis on anomalies, temporal shifts, operational risks, or a specific business question."
              className="px-3 py-2 rounded border border-outline-variant bg-surface text-on-surface font-body resize-none"
            />
          </label>
```

- [ ] **Step 8: Update chat input behavior**

Modify `frontend/src/components/chat/ChatInput.tsx`:

- remove `addUserMessage` usage
- allow active-run steering while not currently submitting
- set placeholder from `pipelineRunning`

The submit function should be:

```typescript
  const submit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isTyping) return;
    onSend(trimmed);
    setValue("");
  }, [value, isTyping, onSend]);
```

Use placeholder:

```tsx
placeholder={pipelineRunning ? "Steer the current run..." : "Ask about your data..."}
```

- [ ] **Step 9: Render steering status**

Modify `frontend/src/components/chat/ChatMessage.tsx`:

```typescript
  const isSteering = message.meta?.kind === "steering";
```

In the user bubble footer:

```tsx
        <div className={`mt-1 flex items-center justify-end gap-2 text-[10px] ${isUser ? "text-white/60" : "text-on-surface-variant"}`}>
          <span>{new Date(message.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
          {isUser && isSteering && (
            <span className="inline-flex items-center gap-1">
              <span className={`h-1.5 w-1.5 rounded-full ${message.meta?.status === "read" ? "bg-emerald-200" : message.meta?.status === "failed" ? "bg-red-200" : "bg-white/60 animate-pulse"}`} />
              {message.meta?.status === "read" ? "Read" : message.meta?.status === "failed" ? "Failed" : "Queued"}
            </span>
          )}
        </div>
```

Replace the existing timestamp `<p>` with this footer.

- [ ] **Step 10: Run frontend check**

Run:

```bash
cd frontend && npm run lint
```

Expected: PASS, or only pre-existing unrelated lint failures documented from Step 1.

---

### Task 4: Integration Verification

**Files:**
- Modify only if needed: files touched by Tasks 1-3

- [ ] **Step 1: Run targeted backend tests**

Run:

```bash
pytest tests/test_steering_service.py tests/test_orchestrator.py tests/test_chat_completion_event.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend lint/build check**

Run:

```bash
cd frontend && npm run lint
```

Expected: PASS, or document pre-existing failures.

- [ ] **Step 3: Run smoke import check**

Run:

```bash
python - <<'PY'
from backend.services.steering_service import enqueue_steering, drain_steering, clear_steering
from src.agent.eda_agent import run_agent
from src.agent.state import AgentState

clear_steering("smoke")
item = enqueue_steering("smoke", "focus on anomalies", "msg1")
assert item["id"] == "msg1"
assert drain_steering("smoke")[0]["status"] == "read"
state = AgentState(dataset_path="/tmp/data.csv", session_id="smoke", research_direction="direction")
assert "direction" in state.run_guidance()
assert callable(run_agent)
print("smoke ok")
PY
```

Expected: prints `smoke ok`.

- [ ] **Step 4: Manual browser check**

Start the app if needed:

```bash
cd frontend && npm run dev
```

Verify:

- upload page shows optional research direction textarea
- active run chat placeholder says `Steer the current run...`
- steering user bubble shows `Queued`
- when backend emits `steering_read`, the same bubble changes to `Read`

