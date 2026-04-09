# Plan 8: Agentic EDA — Multi-Subagent Loop Architecture + Knowledge Graph + Performance Overhaul

## Status: SPEC

---

## 1. Problem Statement

The current system runs a single-threaded, single-kernel EDA pipeline: 13 sequential goals → one batch of 3 hypotheses (investigated serially with `max_workers=1`) → one story. This creates several critical issues:

| Issue | Impact |
|---|---|
| **Notebook gets stuck after chat investigation** | `phase_transition` event sets `pipelineRunning=true` but no `complete` event is ever pushed from chat.py |
| **Vision loop is broken** | `interpret_output()` builds image content parts but passes only text to the LLM — plots are never analyzed |
| **Knowledge graph is write-only** | KG is populated but never queried for deduplication, chat context, or hypothesis generation |
| **No hypothesis caching** | Identical investigations re-run if user asks overlapping questions |
| **Everything is sequential** | 40-100+ LLM calls in series; `ThreadPoolExecutor(max_workers=1)` defeats parallelism |
| **~2-3 min runtime** | Sequential LLM calls (30-50s) + matplotlib rendering (40-60s) + 9s artificial sleep |
| **Single investigation loop** | Hypotheses generated once; no iterative deepening based on what subagents discover |

### Target Architecture (User Vision)

```
Upload dataset → Main agent does initial EDA in main notebook
  → Spawns N subagents into N hypothesis notebooks (parallel)
  → All notebooks run until annotated complete OR timeout
  → Main agent ingests subagent plots/findings, updates KG
  → Main agent does its own follow-up coding/plotting in main notebook
  → If EDA done → generate story from KG
  → If not done → Loop 2: spawn N subagents again with new hypotheses
  → Repeat up to M loops (user-configurable)
```

User-configurable parameters on upload page:
- **Max subagents per loop** (N): default 3, range 1-6
- **Max loops** (M): default 2, range 1-5

---

## 2. Architecture Overview

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     FRONTEND (Next.js)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │ Upload   │  │ Main     │  │ Sub-agent │  │ Chat       │  │
│  │ Config   │  │ Notebook │  │ Notebooks │  │ Sidebar    │  │
│  │ (N, M)   │  │ Tab      │  │ Tabs      │  │            │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘  │
│        │              │             │              │         │
│        └──────────────┴─────────────┴──────────────┘        │
│                          │ WebSocket                         │
└──────────────────────────┼───────────────────────────────────┘
                           │
┌──────────────────────────┼───────────────────────────────────┐
│                    BACKEND (FastAPI)                          │
│                          │                                    │
│  ┌───────────────────────▼────────────────────────────────┐  │
│  │              Orchestrator (Main Agent)                   │  │
│  │  - Runs initial EDA in main kernel                      │  │
│  │  - Generates hypotheses from KG                         │  │
│  │  - Dispatches subagents to kernel pool                  │  │
│  │  - Ingests subagent results + plots (vision)            │  │
│  │  - Decides: another loop or generate story              │  │
│  └────────┬──────────┬──────────┬─────────────────────────┘  │
│           │          │          │                              │
│  ┌────────▼──┐ ┌────▼────┐ ┌──▼────────┐                    │
│  │ Subagent  │ │Subagent │ │ Subagent  │  (up to N)         │
│  │ Kernel 1  │ │Kernel 2 │ │ Kernel N  │                    │
│  │ Notebook 1│ │Notebook2│ │ NotebookN │                    │
│  └─────┬─────┘ └────┬────┘ └─────┬─────┘                    │
│        │            │             │                           │
│  ┌─────▼────────────▼─────────────▼──────────────────────┐   │
│  │              Knowledge Graph Engine                    │   │
│  │  - Typed nodes (finding, hypothesis, evidence, plot)   │   │
│  │  - Typed edges (supports, contradicts, derived_from)   │   │
│  │  - Query: "what do I know about X?"                    │   │
│  │  - Dedup: hash(columns + analysis_type + params)       │   │
│  │  - Confidence scoring with evidence accumulation       │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐   │
│  │              Kernel Pool Manager                       │   │
│  │  - 1 main kernel (persistent)                          │   │
│  │  - N subagent kernels (created per loop, recycled)     │   │
│  │  - Shared dataset access via session dir               │   │
│  │  - Independent execution, no cross-kernel state        │   │
│  └───────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
```

### 2.2 Execution Timeline (2 loops, 3 subagents)

```
Time ──────────────────────────────────────────────────────────►

Main Agent:  [===Initial EDA (13 goals)===]
                                           ╲
                                            [Generate hypotheses from KG]
                                                     │
Loop 1:                              Subagent-1 ─────[H1 investigation]────┐
                                     Subagent-2 ─────[H2 investigation]────┤ parallel
                                     Subagent-3 ─────[H3 investigation]────┘
                                                                           │
Main Agent:                                    [Ingest results + vision]───┤
                                               [Own follow-up analysis]────┤
                                               [Update KG]────────────────┤
                                               [Decide: done? no]─────────┘
                                                     │
Loop 2:                              Subagent-1 ─────[H4 investigation]────┐
                                     Subagent-2 ─────[H5 investigation]────┤ parallel
                                     Subagent-3 ─────[H6 investigation]────┘
                                                                           │
Main Agent:                                    [Ingest results + vision]───┤
                                               [Decide: done? yes]─────────┘
                                                     │
Story:                                         [Generate from KG]──────────►
```

---

## 3. Knowledge Graph Redesign

### 3.1 Current State (Write-Only)

The existing `KnowledgeGraph` class (`src/agent/knowledge_graph.py`, 177 lines) accumulates `KnowledgeNode` objects with `type`, `text`, `phase`, `confidence`, and `children`. It has `add_fact()`, `add_investigation()`, `get_story_sections()`, and `get_top_conclusions()`. It is never queried before generating hypotheses, never consulted by the chat agent, and has no deduplication.

### 3.2 New Design

Inspired by patterns from `agentmemory` (typed graph with temporal edges, deduplication, hybrid search) and Karpathy's LLM wiki (persistent, queryable, compounding knowledge).

#### Node Types

```python
@dataclass
class KGNode:
    id: str                          # uuid
    type: NodeType                   # enum below
    text: str                        # human-readable description
    metadata: dict                   # type-specific (see below)
    source_cells: list[str]          # cell IDs that produced this
    source_plots: list[str]          # plot cell IDs (base64 or spec)
    confidence: float                # 0.0-1.0
    created_at: float                # timestamp
    loop_number: int                 # which loop produced this (0 = initial EDA)
    superseded_by: str | None        # node ID if superseded
    is_latest: bool                  # False if superseded

class NodeType(str, Enum):
    SCHEMA_FACT = "schema_fact"            # column types, shape, dtypes
    DATA_QUALITY = "data_quality"          # missing values, outliers, anomalies
    DISTRIBUTION = "distribution"          # distribution shape findings
    CORRELATION = "correlation"            # pairwise relationships
    TEMPORAL_PATTERN = "temporal_pattern"  # trends, seasonality, changepoints
    HYPOTHESIS = "hypothesis"              # generated hypothesis (not yet tested)
    EVIDENCE = "evidence"                  # cell output supporting/refuting hypothesis
    CONCLUSION = "conclusion"              # synthesized finding from investigation
    VISUAL_INSIGHT = "visual_insight"      # finding from vision analysis of a plot
    USER_QUESTION = "user_question"        # question from chat
```

#### Edge Types

```python
@dataclass
class KGEdge:
    source_id: str
    target_id: str
    type: EdgeType
    weight: float                    # 0.0-1.0
    metadata: dict                   # e.g. p_value, correlation_strength
    created_at: float

class EdgeType(str, Enum):
    SUPPORTS = "supports"            # evidence → conclusion
    CONTRADICTS = "contradicts"      # evidence → conclusion (negative)
    DERIVED_FROM = "derived_from"    # conclusion → finding it builds on
    TESTED_BY = "tested_by"          # hypothesis → investigation that tested it
    VISUALIZED_BY = "visualized_by"  # finding → plot that shows it
    CORRELATES_WITH = "correlates_with"  # column → column
    SUPERSEDES = "supersedes"        # new finding → old finding
    REQUIRES = "requires"            # hypothesis → prerequisite finding
    SPAWNED = "spawned"              # finding → hypothesis it inspired
```

#### Query Interface

```python
class KnowledgeGraph:
    # --- Existing (keep) ---
    def add_fact(self, ...) -> str: ...
    def add_investigation(self, ...) -> str: ...
    def get_story_sections(self) -> list[dict]: ...
    def get_top_conclusions(self, n) -> list[KGNode]: ...

    # --- New: Query ---
    def query_by_columns(self, columns: list[str]) -> list[KGNode]:
        """Find all findings involving these columns."""

    def query_by_type(self, node_type: NodeType) -> list[KGNode]:
        """Find all nodes of a given type."""

    def get_evidence_chain(self, conclusion_id: str) -> list[KGNode]:
        """Traverse SUPPORTS/CONTRADICTS edges back to raw evidence."""

    def summarize_known(self, topic: str) -> str:
        """LLM-assisted: 'What do I already know about {topic}?'
        Searches nodes by text similarity, returns synthesis."""

    # --- New: Deduplication ---
    def find_similar_hypothesis(self, hypothesis: Hypothesis, threshold=0.85) -> KGNode | None:
        """Check if a hypothesis overlaps with an existing one.
        Uses column overlap + text similarity."""

    def investigation_hash(self, columns: list[str], analysis_type: str) -> str:
        """SHA-256 hash for dedup. Returns existing node ID if match found."""

    # --- New: Supersession ---
    def supersede(self, old_id: str, new_node: KGNode) -> None:
        """Mark old node superseded, link via SUPERSEDES edge."""

    # --- New: Context for LLM ---
    def get_context_for_hypothesis_generation(self) -> str:
        """Return structured summary of all current knowledge for LLM prompt.
        Grouped by type, includes confidence, avoids token bloat."""

    def get_context_for_chat(self, question: str) -> str:
        """Return relevant KG context for answering a chat question.
        Searches by column names and text similarity."""

    # --- New: Confidence ---
    def reinforce(self, node_id: str, new_evidence_id: str) -> None:
        """Increase confidence when additional evidence supports a finding.
        confidence = min(0.99, confidence + 0.1 * (1 - confidence))"""

    def decay_confidence(self, node_id: str, factor=0.05) -> None:
        """Decrease confidence when contradicting evidence appears."""
```

#### Deduplication Strategy

Before any subagent investigation begins:

```python
def should_investigate(kg: KnowledgeGraph, hypothesis: Hypothesis) -> bool:
    # 1. Check exact hash match (columns + analysis type)
    existing = kg.investigation_hash(hypothesis.relevant_cols, hypothesis.description)
    if existing:
        return False  # Already investigated

    # 2. Check fuzzy match (>85% column overlap + similar description)
    similar = kg.find_similar_hypothesis(hypothesis, threshold=0.85)
    if similar and similar.confidence > 0.7:
        return False  # Sufficiently answered by prior work

    return True
```

#### Confidence Scoring

Replace the naive `0.3 + 0.15 * len(outputs)` with evidence-based scoring:

```python
def compute_confidence(evidence_nodes: list[KGNode], has_visual: bool) -> float:
    base = 0.3
    # Statistical evidence
    for e in evidence_nodes:
        p_value = e.metadata.get("p_value")
        if p_value is not None:
            base += 0.2 * (1 - p_value)  # lower p → higher confidence
        else:
            base += 0.05  # non-statistical evidence adds less
    # Visual confirmation
    if has_visual:
        base += 0.1
    # Multiple independent lines of evidence
    if len(evidence_nodes) >= 3:
        base += 0.1
    return min(0.99, base)
```

---

## 4. Kernel Pool Manager

### 4.1 Current State

One kernel per session (`_kernels[session_id]`). Subagents share the main kernel, executing cells sequentially. No parallelism possible.

### 4.2 New Design

```python
class KernelPoolManager:
    """Manages a pool of Jupyter kernels for parallel subagent execution."""

    def __init__(self):
        self._main_kernels: dict[str, KernelManager] = {}      # session_id → main kernel
        self._sub_kernels: dict[str, list[KernelManager]] = {}  # session_id → [sub kernels]
        self._kernel_lock = threading.Lock()

    async def get_main_kernel(self, session_id: str) -> KernelClient:
        """Get or create the persistent main kernel for a session."""

    async def allocate_subagent_kernels(self, session_id: str, n: int) -> list[str]:
        """Create N fresh kernels for parallel subagent execution.
        Returns list of kernel_ids like '{session_id}_sub_{i}'.
        Each kernel gets:
          - Same cwd as main kernel (access to uploaded dataset)
          - Same injected imports (pandas, numpy, matplotlib, emit_plot_spec)
          - Own independent namespace (no shared state with main)
        """

    async def execute_on_subkernel(self, kernel_id: str, code: str, timeout=60) -> tuple[list, str|None]:
        """Execute code on a specific subagent kernel."""

    async def shutdown_subagent_kernels(self, session_id: str) -> None:
        """Shutdown all subagent kernels for a session (between loops or on completion)."""

    async def shutdown_all(self, session_id: str) -> None:
        """Shutdown main + all sub kernels (session cleanup)."""
```

### 4.3 Subagent Kernel Lifecycle

```
Loop start:
  allocate_subagent_kernels(session_id, N)  → creates N kernels
  Each subagent gets its own kernel_id
  Subagents run in parallel via asyncio.gather() or ThreadPoolExecutor(max_workers=N)

Loop end:
  Collect all outputs from all sub-kernels
  shutdown_subagent_kernels(session_id)  → reclaim resources

Next loop:
  allocate_subagent_kernels(session_id, N)  → fresh kernels
```

Each subagent kernel needs to load the dataset independently. To avoid N redundant CSV parses, the main agent can save a pickle/parquet checkpoint:

```python
# Main kernel (after initial load):
df.to_parquet(f"{session_dir}/.cache/df_clean.parquet")

# Each subagent kernel (injected preamble):
import pandas as pd
df = pd.read_parquet(".cache/df_clean.parquet")
```

---

## 5. Orchestrator (Main Agent) Redesign

### 5.1 New `run_agent()` Flow

```python
async def run_agent(
    session_id: str,
    dataset_path: str,
    push_event: Callable,
    max_subagents: int = 3,       # user-configurable N
    max_loops: int = 2,           # user-configurable M
    loop_timeout: int = 180,      # seconds per loop
):
    state = AgentState()
    kg = KnowledgeGraph()
    pool = KernelPoolManager()

    # ── Phase 1: Initial EDA (main kernel, same as today) ──
    main_kernel = await pool.get_main_kernel(session_id)
    await _run_initial_eda(state, kg, main_kernel, push_event)
    # Saves df_clean.parquet for subagents

    # ── Phase 2: Iterative hypothesis loops ──
    for loop_num in range(1, max_loops + 1):
        push_event(session_id, {
            "type": "phase_transition",
            "phase": f"Investigation Loop {loop_num}/{max_loops}"
        })

        # 2a. Generate hypotheses from KG (not just flat findings)
        context = kg.get_context_for_hypothesis_generation()
        hypotheses = generate_hypotheses_from_kg(context, state)

        # 2b. Deduplicate against KG
        novel_hypotheses = [
            h for h in hypotheses
            if should_investigate(kg, h)
        ][:max_subagents]

        if not novel_hypotheses:
            push_event(session_id, {"type": "thinking", "content": "No novel hypotheses remain. EDA complete."})
            break

        # 2c. Allocate N subagent kernels
        sub_kernel_ids = await pool.allocate_subagent_kernels(session_id, len(novel_hypotheses))

        # 2d. Run subagents in parallel
        results = await _run_subagents_parallel(
            novel_hypotheses, sub_kernel_ids, state, push_event,
            timeout=loop_timeout
        )

        # 2e. Shutdown subagent kernels
        await pool.shutdown_subagent_kernels(session_id)

        # 2f. Ingest results into KG (with vision analysis of plots)
        for result in results:
            await _ingest_subagent_result(result, kg, state, push_event)

        # 2g. Main agent follow-up in main kernel
        await _main_agent_followup(state, kg, main_kernel, push_event)

        # 2h. Decide: continue or stop?
        if _should_stop_investigating(kg, loop_num, max_loops):
            break

    # ── Phase 3: Story generation from KG ──
    story = await _generate_story_from_kg(kg, state, push_event)

    push_event(session_id, {"type": "complete"})
    return state, kg, story
```

### 5.2 Parallel Subagent Execution

```python
async def _run_subagents_parallel(
    hypotheses: list[Hypothesis],
    kernel_ids: list[str],
    state: AgentState,
    push_event: Callable,
    timeout: int = 180,
) -> list[InvestigationResult]:
    """Run N subagents in parallel, each in its own kernel and notebook."""

    async def _run_one(hypothesis, kernel_id):
        notebook_id = f"investigation_{hypothesis.id}"
        push_event(session_id, {
            "type": "subagent_start",
            "hypothesis_id": hypothesis.id,
            "notebook_id": notebook_id,
            "title": hypothesis.title,
        })
        try:
            result = await run_subagent(
                hypothesis=hypothesis,
                kernel_id=kernel_id,
                notebook_id=notebook_id,
                state=state,
                push_event=push_event,
                timeout=timeout,
            )
            push_event(session_id, {
                "type": "subagent_complete",
                "hypothesis_id": hypothesis.id,
                "notebook_id": notebook_id,
                "finding": result.finding,
                "confidence": result.confidence,
            })
            return result
        except asyncio.TimeoutError:
            push_event(session_id, {
                "type": "subagent_timeout",
                "hypothesis_id": hypothesis.id,
            })
            return InvestigationResult(
                hypothesis_id=hypothesis.id,
                finding="Investigation timed out",
                confidence=0.1,
            )

    results = await asyncio.gather(
        *[_run_one(h, kid) for h, kid in zip(hypotheses, kernel_ids)],
        return_exceptions=True,
    )
    return [r for r in results if isinstance(r, InvestigationResult)]
```

### 5.3 Vision-Enabled Result Ingestion

When the main agent ingests subagent results, it must **see** the plots:

```python
async def _ingest_subagent_result(
    result: InvestigationResult,
    kg: KnowledgeGraph,
    state: AgentState,
    push_event: Callable,
):
    # 1. Add conclusion to KG
    conclusion_id = kg.add_conclusion(
        text=result.finding,
        confidence=result.confidence,
        source_cells=result.cell_ids,
        source_plots=result.plot_cell_ids,
        loop_number=result.loop_number,
        hypothesis_id=result.hypothesis_id,
    )

    # 2. Vision analysis of subagent plots
    for plot_cell_id in result.plot_cell_ids:
        images = result.get_images_for_cell(plot_cell_id)
        if images:
            visual_finding = await _vision_analyze_plot(
                images=images,
                context=f"Hypothesis: {result.hypothesis_title}\nFinding: {result.finding}",
            )
            insight_id = kg.add_node(KGNode(
                type=NodeType.VISUAL_INSIGHT,
                text=visual_finding,
                source_plots=[plot_cell_id],
                confidence=0.6,  # visual insights start at moderate confidence
            ))
            kg.add_edge(KGEdge(
                source_id=insight_id,
                target_id=conclusion_id,
                type=EdgeType.SUPPORTS,
                weight=0.7,
            ))

    # 3. Link evidence chain
    for evidence_text in result.sub_findings:
        ev_id = kg.add_node(KGNode(
            type=NodeType.EVIDENCE,
            text=evidence_text,
            source_cells=result.cell_ids,
        ))
        kg.add_edge(KGEdge(
            source_id=ev_id,
            target_id=conclusion_id,
            type=EdgeType.SUPPORTS,
        ))
```

### 5.4 Stop Condition

```python
def _should_stop_investigating(kg: KnowledgeGraph, loop_num: int, max_loops: int) -> bool:
    """Decide whether to continue investigating or generate the report."""

    # Hard stop: reached max loops
    if loop_num >= max_loops:
        return True

    # Soft stop: ask LLM with KG context
    context = kg.get_context_for_hypothesis_generation()
    conclusions = kg.get_top_conclusions(10)

    prompt = f"""Based on the current state of knowledge about this dataset:

{context}

Top conclusions so far:
{chr(10).join(f'- {c.text} (confidence: {c.confidence:.2f})' for c in conclusions)}

Should we investigate further, or do we have sufficient understanding?
Reply CONTINUE or STOP with a one-sentence reason."""

    response = llm.invoke([HumanMessage(content=prompt)])
    return "STOP" in response.content.upper()
```

---

## 6. Fix: Vision Analysis Loop

### 6.1 Current Bug

In `reasoning.py:interpret_output()`, `content_parts` is built with images but the `HumanMessage` only receives text:

```python
# CURRENT (broken):
response = llm.invoke([
    SystemMessage(content="..."),
    HumanMessage(content=f"Phase: {phase}\nOutput:\n{output_text[:1500]}"),  # images ignored
])
```

### 6.2 Fix

```python
def interpret_output(output_text: str, phase: str, images: list[str] | None = None) -> str:
    system = SystemMessage(content="Write ONE concise sentence summarizing the key finding...")

    content_parts = [{"type": "text", "text": f"Phase: {phase}\nOutput:\n{output_text[:1500]}"}]

    if images:
        for img_b64 in images[:2]:
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "low"},
            })

    human = HumanMessage(content=content_parts)  # USE content_parts, not plain text
    response = llm.invoke([system, human])
    return response.content.strip()
```

### 6.3 Vision in Subagent

Currently subagent records `plot_cell_ids` but never analyzes plots. The new ingestion flow (Section 5.3) handles this by running vision analysis when the main agent collects subagent results.

---

## 7. Fix: Notebook Stuck After Chat Investigation

### 7.1 Root Cause

`/backend/routers/chat.py` → `_run_hypothesis_investigation()` pushes `phase_transition` (which sets `pipelineRunning=true`) but never pushes `complete`. The frontend stays in "Analyzing" forever.

### 7.2 Fix

At the end of `_run_hypothesis_investigation()`, push a completion event:

```python
# In chat.py, at the end of _run_hypothesis_investigation():
push_event(session_id, {
    "type": "chat_investigation_complete",
    "hypothesis_id": hypothesis.id,
    "finding": result.finding,
})
```

In the frontend `useAgentStream.ts`, handle the new event:

```typescript
case "chat_investigation_complete":
    store.setPipelineRunning(false);
    break;
```

Also add a safety net: when the chat REST response returns successfully, the `useChat` hook should always clear `pipelineRunning`:

```typescript
// In useChat.ts, after receiving response:
useNotebookStore.getState().setPipelineRunning(false);
```

---

## 8. Frontend Changes

### 8.1 Upload Page — Configuration Panel

Add configuration controls to the upload/landing page (`frontend/src/app/page.tsx` or `DropZone.tsx`):

```
┌──────────────────────────────────────────┐
│           Upload Your Dataset            │
│                                          │
│  ┌──────────────────────────────────┐    │
│  │  📁 Drop CSV, Excel, JSON...    │    │
│  └──────────────────────────────────┘    │
│                                          │
│  ─── Agent Configuration ───             │
│                                          │
│  Subagents per loop    [▼ 3 ]  (1-6)    │
│  Max investigation     [▼ 2 ]  (1-5)    │
│  loops                                   │
│                                          │
│  [ ▶ Run EDA ]                           │
└──────────────────────────────────────────┘
```

These values are sent as query params or body fields in the `POST /api/run/{session_id}` request and passed through to `run_agent()`.

### 8.2 Session Page — Subagent Notebook Tabs

The notebook pane currently shows one notebook. With parallel subagents, each hypothesis investigation runs in its own notebook. The UI needs:

```
┌─────────────────────────────────────────────┐
│ [Main Notebook] [H1: Wind vs Power] [H2:..] │
│─────────────────────────────────────────────│
│                                              │
│  Cell 1: ...                                 │
│  Cell 2: ...                                 │
│                                              │
└──────────────────────────────────────────────┘
```

- Main notebook tab is always present
- Subagent notebook tabs appear dynamically when `subagent_start` events arrive
- Each tab shows its own cell stream (filtered by `notebook_id`)
- Tabs show status badges: running/complete/timeout
- Completed investigation tabs become read-only

### 8.3 Event Stream Changes

New event types to support multi-notebook parallel execution:

```typescript
type AgentEvent =
    // ... existing events ...
    | { type: "subagent_start"; hypothesis_id: string; notebook_id: string; title: string }
    | { type: "subagent_complete"; hypothesis_id: string; notebook_id: string; finding: string; confidence: number }
    | { type: "subagent_timeout"; hypothesis_id: string }
    | { type: "loop_start"; loop_number: number; total_loops: number }
    | { type: "loop_complete"; loop_number: number }
    | { type: "chat_investigation_complete"; hypothesis_id: string; finding: string }
    // cell events now carry notebook_id:
    | { type: "cell_write"; notebook_id: string; cell_id: string; code: string }
    | { type: "cell_output"; notebook_id: string; cell_id: string; outputs: any[] }
```

### 8.4 Notebook Store Changes

The Zustand notebook store needs to support multiple notebooks:

```typescript
interface NotebookStore {
    // Current (single notebook):
    // cells: Cell[];

    // New (multi-notebook):
    notebooks: Record<string, Notebook>;  // notebook_id → Notebook
    activeNotebookId: string;

    // Each Notebook has its own cells, status, etc.
    appendCell(notebookId: string, cell: Cell): void;
    updateCellOutputs(notebookId: string, cellId: string, outputs: any[]): void;
    setNotebookComplete(notebookId: string): void;
}
```

### 8.5 Investigation Explorer (Left Sidebar)

The left sidebar currently shows a flat list of investigations. Redesign to show the loop structure:

```
▼ INVESTIGATION LOOP 1
    ├─ ✅ Hypothesis 1/3: Wind speed correlation    (0.87)
    ├─ ✅ Hypothesis 2/3: Outlier regime detection   (0.72)
    └─ ⏱ Hypothesis 3/3: Seasonal decomposition    (timeout)

▼ INVESTIGATION LOOP 2
    ├─ 🔄 Hypothesis 1/2: Power curve nonlinearity
    └─ 🔄 Hypothesis 2/2: Direction-dependent efficiency
```

---

## 9. Performance Optimizations

### 9.1 Parallel LLM Calls

Many LLM calls during initial EDA are independent and can be parallelized:

```python
# Current: sequential interpret + decide per goal
finding = interpret_output(output_text, phase, images)
follow_up = decide_next_step(state, output_text, finding)

# New: parallel where possible (e.g., batch all post-goal interpretations)
# Group independent goals and run their LLM calls concurrently
```

Hypothesis generation and subagent plan generation are inherently parallel once we have multiple kernels.

### 9.2 Response Caching

Add an LRU cache on LLM calls keyed by prompt hash:

```python
from functools import lru_cache
import hashlib

_response_cache: dict[str, str] = {}

def cached_llm_call(prompt_text: str, **kwargs) -> str:
    key = hashlib.sha256(prompt_text.encode()).hexdigest()[:16]
    if key in _response_cache:
        return _response_cache[key]
    response = llm.invoke(...)
    _response_cache[key] = response.content
    return response.content
```

Note: only cache deterministic calls (interpretation, not code generation).

### 9.3 Remove Artificial Delays

Remove or reduce the `await asyncio.sleep(0.3)` calls in `eda_agent.py` (lines 50, 66, 74, 99, 121). These add ~9s per run. If needed for UI streaming, use a smaller delay (0.05s) or debounce on the frontend.

### 9.4 Dataset Checkpoint

Save cleaned dataframe as parquet after initial load so subagent kernels don't re-parse CSV:

```python
# After goal "handle_missing" completes:
df.to_parquet(f"{session_dir}/.cache/df_clean.parquet", index=True)
```

### 9.5 Kernel Timeout Tuning

Instead of a flat 60s timeout for all cells, use cell-type-aware timeouts:

| Cell type | Timeout |
|---|---|
| Data loading | 30s |
| Statistical computation | 20s |
| Plot generation | 30s |
| Simple inspection | 10s |

---

## 10. Chat Agent Integration with KG

### 10.1 Current State

Chat agent receives a flat `findings` list via `ChatContext.get_summary()`. No KG access.

### 10.2 New Design

```python
class ChatContext:
    def __init__(self, state: dict, kg: KnowledgeGraph):
        self.state = state
        self.kg = kg

    def get_summary(self, question: str | None = None) -> str:
        parts = []

        # Always include: schema facts, data quality
        schema = self.kg.query_by_type(NodeType.SCHEMA_FACT)
        parts.append("Dataset: " + "; ".join(n.text for n in schema[:5]))

        if question:
            # Targeted context: query KG for relevant findings
            relevant = self.kg.get_context_for_chat(question)
            parts.append(f"Relevant findings:\n{relevant}")
        else:
            # General context: top conclusions
            conclusions = self.kg.get_top_conclusions(5)
            parts.append("Key findings:\n" + "\n".join(
                f"- {c.text} (confidence: {c.confidence:.2f})" for c in conclusions
            ))

        return "\n\n".join(parts)
```

### 10.3 Chat Deduplication

Before running a chat-triggered investigation:

```python
async def handle_chat_hypothesis(session_id, question, kg):
    hypothesis = hypothesis_from_user_question(question, ...)

    if hypothesis.id is None:
        return None  # Not a testable hypothesis

    # CHECK KG FIRST
    existing = kg.find_similar_hypothesis(hypothesis)
    if existing and existing.confidence > 0.6:
        return {
            "type": "cached_answer",
            "finding": existing.text,
            "confidence": existing.confidence,
            "evidence": kg.get_evidence_chain(existing.id),
            "message": f"This was already investigated (confidence: {existing.confidence:.0%}): {existing.text}"
        }

    # Only run new investigation if not already answered
    result = await _run_hypothesis_investigation(...)
    kg.add_investigation(result)
    return result
```

---

## 11. Story Generation from KG

### 11.1 Current State

Story is generated from flat findings list + KG sections. Narrative is a single LLM call.

### 11.2 New Design

The KG now has rich structure: evidence chains, confidence scores, visual insights, supersession history. Story generation should leverage this:

```python
async def generate_story_from_kg(kg: KnowledgeGraph, state: AgentState) -> dict:
    sections = []

    # Section 1: Dataset Overview (from SCHEMA_FACT nodes)
    schema_facts = kg.query_by_type(NodeType.SCHEMA_FACT)
    sections.append({
        "title": "Dataset Overview",
        "findings": [f.text for f in schema_facts],
        "plots": [],
    })

    # Section 2: Data Quality (from DATA_QUALITY nodes)
    quality = kg.query_by_type(NodeType.DATA_QUALITY)
    sections.append({
        "title": "Data Quality Assessment",
        "findings": [f.text for f in quality],
        "confidence": mean([f.confidence for f in quality]) if quality else 0,
    })

    # Section 3+: One section per investigated hypothesis
    conclusions = kg.query_by_type(NodeType.CONCLUSION)
    for conclusion in sorted(conclusions, key=lambda c: -c.confidence):
        evidence_chain = kg.get_evidence_chain(conclusion.id)
        visual_insights = [
            e for e in evidence_chain
            if e.type == NodeType.VISUAL_INSIGHT
        ]
        sections.append({
            "title": f"Investigation: {conclusion.metadata.get('hypothesis_title', 'Unknown')}",
            "conclusion": conclusion.text,
            "confidence": conclusion.confidence,
            "evidence": [e.text for e in evidence_chain],
            "visual_insights": [v.text for v in visual_insights],
            "plots": conclusion.source_plots,
            "loop_number": conclusion.loop_number,
        })

    # Final section: Executive summary (LLM synthesis of top conclusions)
    narrative = await _generate_narrative(kg.get_top_conclusions(10))

    return {
        "sections": sections,
        "narrative": narrative,
        "knowledge_graph": kg.to_json(),
        "metadata": {
            "total_loops": state.loop_count,
            "total_hypotheses_tested": len(conclusions),
            "total_subagent_runs": state.subagent_run_count,
        }
    }
```

---

## 12. API Changes

### 12.1 Run Endpoint

```python
# POST /api/run/{session_id}
# Body:
{
    "max_subagents": 3,    # N (1-6)
    "max_loops": 2,        # M (1-5)
    "loop_timeout": 180    # seconds per loop
}
```

### 12.2 New Endpoints

```python
# GET /api/run/{session_id}/kg
# Returns the knowledge graph as JSON for frontend visualization (optional)

# GET /api/run/{session_id}/notebooks
# Returns list of all notebooks (main + subagent) with their status
```

### 12.3 Session State File Changes

```
sessions/{session_id}/
  uploads/
    dataset.csv
  .cache/
    df_clean.parquet          # NEW: checkpoint for subagent kernels
  notebooks/
    main.ipynb                # Main agent notebook
    investigation_h1.ipynb    # NEW: subagent notebook per hypothesis
    investigation_h2.ipynb
    ...
  knowledge_graph.json        # NEW: persisted KG
  agent_state.json
  story.json
  status.json
  plot_specs.jsonl
```

---

## 13. Implementation Order

### Phase A: Critical Bug Fixes (can ship independently)

| Task | Files | Effort |
|---|---|---|
| A1. Fix stuck notebook: push `chat_investigation_complete` event | `backend/routers/chat.py`, `frontend/src/hooks/useAgentStream.ts` | S |
| A2. Fix vision loop: pass `content_parts` to `HumanMessage` | `src/agent/reasoning.py` | XS |
| A3. Remove/reduce artificial `sleep()` delays | `src/agent/eda_agent.py` | XS |

### Phase B: Knowledge Graph Overhaul

| Task | Files | Effort |
|---|---|---|
| B1. Redesign `KnowledgeGraph` class with typed nodes, edges, query interface | `src/agent/knowledge_graph.py` | L |
| B2. Add deduplication (hash + fuzzy match) | `src/agent/knowledge_graph.py` | M |
| B3. Wire KG into hypothesis generation (`get_context_for_hypothesis_generation`) | `src/agent/hypothesis.py`, `src/agent/eda_agent.py` | M |
| B4. Wire KG into chat agent (`get_context_for_chat`) | `src/chat/chat_agent.py`, `backend/routers/chat.py` | M |
| B5. Add evidence-based confidence scoring | `src/agent/knowledge_graph.py`, `src/agent/subagent.py` | M |
| B6. Add supersession support | `src/agent/knowledge_graph.py` | S |
| B7. Persist KG to `knowledge_graph.json` between runs | `backend/routers/run.py` | S |

### Phase C: Kernel Pool + Parallel Subagents

| Task | Files | Effort |
|---|---|---|
| C1. Implement `KernelPoolManager` with multi-kernel support | `backend/services/kernel_pool.py` (new) | L |
| C2. Add dataset checkpoint (parquet) after initial EDA | `src/agent/eda_agent.py`, `src/agent/code_templates.py` | S |
| C3. Refactor `run_subagent()` to accept `kernel_id` parameter | `src/agent/subagent.py` | M |
| C4. Implement parallel subagent execution with `asyncio.gather` | `src/agent/eda_agent.py` | L |
| C5. Add per-subagent notebook tracking (separate cell registries) | `src/agent/state.py`, `src/agent/subagent.py` | M |

### Phase D: Multi-Loop Orchestrator

| Task | Files | Effort |
|---|---|---|
| D1. Refactor `run_agent()` into loop-based orchestrator | `src/agent/eda_agent.py` | L |
| D2. Implement main-agent follow-up phase (post-subagent analysis) | `src/agent/eda_agent.py` | M |
| D3. Implement stop condition (LLM-assisted + hard limit) | `src/agent/eda_agent.py` | S |
| D4. Vision-enabled subagent result ingestion | `src/agent/eda_agent.py` | M |

### Phase E: Frontend Changes

| Task | Files | Effort |
|---|---|---|
| E1. Upload page: add N/M configuration controls | `frontend/src/app/page.tsx`, `frontend/src/components/upload/DropZone.tsx` | S |
| E2. Multi-notebook store (notebooks by ID) | `frontend/src/stores/notebookStore.ts` | M |
| E3. Subagent notebook tabs in NotebookPane | `frontend/src/components/notebook/NotebookPane.tsx` | M |
| E4. New event types in `useAgentStream` | `frontend/src/hooks/useAgentStream.ts` | M |
| E5. Investigation explorer with loop structure | `frontend/src/components/layout/ExplorerSidebar.tsx` | M |
| E6. Pass N/M config in run API call | `frontend/src/lib/api.ts` | XS |

### Phase F: Story Generation Upgrade

| Task | Files | Effort |
|---|---|---|
| F1. Story generation from enriched KG (evidence chains, visual insights) | `backend/routers/story.py`, `backend/routers/run.py` | L |
| F2. Per-investigation sections with confidence + evidence | `backend/routers/story.py` | M |

---

## 14. Migration Strategy

### Breaking Changes

The multi-kernel architecture is a significant refactor. To avoid breaking the working single-kernel flow:

1. **Phase A** ships independently — pure bug fixes, no architectural changes
2. **Phase B** is additive — new KG methods, old methods still work
3. **Phase C-D** is the big bang — `run_agent()` signature changes, kernel management changes
4. **Phase E** can be developed in parallel with C-D using mock events

### Feature Flag Approach

During development, support both paths:

```python
# In run.py:
if config.get("multi_loop_enabled", False):
    await run_agent_v2(session_id, dataset_path, push_event, max_subagents, max_loops)
else:
    await run_agent(session_id, dataset_path, push_event)  # existing flow
```

Remove the flag once v2 is stable.

### Testing Strategy

- **Unit tests** for KG query methods (dedup, evidence chains, confidence)
- **Integration tests** for kernel pool (spin up 3 kernels, execute in parallel, collect outputs)
- **End-to-end test**: upload CSV → 2 loops × 3 subagents → story generated with KG data
- **Regression test**: ensure single-kernel flow still works under feature flag

---

## 15. Risk Assessment

| Risk | Mitigation |
|---|---|
| N parallel kernels exhaust memory | Limit N to 6; shutdown subagent kernels between loops; monitor RSS |
| Subagent generates unsafe code | Same sandboxing as today; timeout per cell; error recovery |
| KG grows unbounded in long sessions | Cap at 200 nodes; consolidate old evidence into summaries |
| Vision API calls add latency | Batch images; use `detail: "low"` (already in code); limit to 2 images per analysis |
| LLM decides to loop forever | Hard cap at M loops; per-loop timeout; total session timeout |
| Frontend overwhelmed by N notebook streams | Virtual scrolling per notebook; only render active tab |
| Race conditions in parallel kernel execution | Each subagent has isolated kernel; no shared mutable state; KG updates happen in main thread after gather |

---

## Appendix A: Reference Repos & Patterns Used

Cloned to `reference_repos/` (gitignored):

| Source | Key Pattern Adopted |
|---|---|
| `agentmemory` (rohitg00) | Typed graph nodes/edges, temporal versioning, deduplication via SHA-256, confidence with reinforcement/decay, evidence chain traversal |
| `llm-wiki` (MehmetGoekce) | L1/L2 knowledge tiers (schema facts = L1, findings = L2), page type taxonomy, lint rules for graph health |
| Karpathy gist | Wiki-as-compounding-knowledge-base, ingest/query/lint lifecycle, "good answers filed back as new pages" |
| rohitg00 gist (v2) | Supersession over overwriting, consolidation tiers (working → episodic → semantic), confidence decay curves |

### Appendix B: LLM Call Count Estimate (New Architecture)

| Phase | Calls (current) | Calls (new) | Notes |
|---|---|---|---|
| Initial EDA (13 goals) | ~26 (interpret + decide per goal) | ~15 (batch independent, skip trivial) | Parallelize where possible |
| Hypothesis generation | 1 | 1 | Now uses KG context |
| Subagent per hypothesis (×N) | ~6 each (plan + fixes + conclusion) | ~6 each | Same per-agent, but N run in parallel |
| Vision analysis of subagent plots | 0 | ~N×2 | New: main agent analyzes plots |
| Main agent follow-up | 0 | ~2-3 | New: post-loop analysis |
| Stop decision | 0 | 1 per loop | New: continue/stop |
| Story generation | 1 | 1 | Enhanced with KG data |
| **Total (2 loops, 3 subagents)** | **~45** | **~55** | More calls but many parallel; net wall-clock time lower |
