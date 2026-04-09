# Agentic EDA v2: Multi-Loop Parallel Subagent Architecture

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the single-threaded sequential EDA agent into a multi-loop orchestrator that spawns N parallel subagents per loop, maintains a queryable knowledge graph, and uses vision to analyze all produced plots.

**Architecture:** The main agent runs initial EDA in a main kernel, then enters a loop: generate hypotheses from KG -> deduplicate -> dispatch N subagents (each in its own kernel) -> ingest results with vision analysis -> main agent follow-up -> decide continue/stop. User configures max subagents (N) and max loops (M) on the upload page.

**Tech Stack:** Python 3.14, FastAPI, jupyter_client, LangChain (OpenAI/Anthropic/Google), Next.js, Zustand, TypeScript

---

## File Map

### New files
- `backend/services/kernel_pool.py` — Multi-kernel pool manager (allocate/execute/shutdown subagent kernels)
- `tests/test_knowledge_graph.py` — Tests for new KG query/dedup/confidence
- `tests/test_kernel_pool.py` — Tests for kernel pool allocation and parallel execution
- `tests/test_orchestrator.py` — Tests for multi-loop orchestrator logic

### Modified files
- `src/agent/knowledge_graph.py` — Add typed edges, query interface, dedup, confidence scoring
- `src/agent/reasoning.py:131-134` — Fix vision loop (pass content_parts to HumanMessage)
- `backend/routers/chat.py:246-321` — Fix stuck notebook (push completion event), add KG dedup
- `src/agent/eda_agent.py` — Refactor into multi-loop orchestrator accepting N/M params
- `src/agent/subagent.py` — Accept kernel_id param, track images for vision ingestion
- `src/agent/hypothesis.py` — Accept KG context for generation, add dedup check
- `src/agent/state.py` — Add loop_count, subagent_run_count, multi-notebook tracking
- `src/chat/chat_agent.py` — Wire KG into ChatContext
- `backend/routers/run.py` — Accept N/M params, pass to agent, save KG
- `backend/routers/stream.py` — No changes needed (events already generic)
- `frontend/src/components/upload/DropZone.tsx` — Add N/M config controls
- `frontend/src/lib/api.ts` — Pass N/M in runEda call
- `frontend/src/hooks/useAgentStream.ts` — Handle new event types, fix stuck state
- `frontend/src/stores/notebookStore.ts` — Multi-notebook support (notebooks by ID)
- `frontend/src/app/session/[id]/page.tsx` — Subagent notebook tabs

---

## Task 1: Fix Vision Loop (reasoning.py)

**Files:**
- Modify: `src/agent/reasoning.py:131-134`
- Test: `tests/test_reasoning_vision.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_reasoning_vision.py`:

```python
"""Test that interpret_output passes images to the LLM."""
import unittest
from unittest.mock import patch, MagicMock


class TestInterpretOutputVision(unittest.TestCase):
    @patch("src.agent.reasoning.get_chat_model")
    def test_images_passed_to_llm(self, mock_get_model):
        """When images are provided, HumanMessage should contain image_url parts."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Found bimodal distribution"
        mock_llm.invoke.return_value = mock_response
        mock_get_model.return_value = mock_llm

        from src.agent.reasoning import interpret_output

        result = interpret_output(
            output_text="some stats output",
            phase="distributions",
            images=["base64encodedimage"],
        )

        # Check the HumanMessage content is a list (multimodal), not a string
        call_args = mock_llm.invoke.call_args[0][0]
        human_msg = call_args[1]  # second message
        assert isinstance(human_msg.content, list), (
            f"Expected list content for multimodal, got {type(human_msg.content)}"
        )
        # Should have text part + image part
        assert len(human_msg.content) == 2
        assert human_msg.content[0]["type"] == "text"
        assert human_msg.content[1]["type"] == "image_url"
        assert "base64encodedimage" in human_msg.content[1]["image_url"]["url"]
        assert result == "Found bimodal distribution"

    @patch("src.agent.reasoning.get_chat_model")
    def test_no_images_uses_plain_text(self, mock_get_model):
        """When no images, HumanMessage should still work (list with one text part)."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Found 12% missing values"
        mock_llm.invoke.return_value = mock_response
        mock_get_model.return_value = mock_llm

        from src.agent.reasoning import interpret_output

        result = interpret_output(
            output_text="Missing: 12%",
            phase="check_missing",
            images=None,
        )

        call_args = mock_llm.invoke.call_args[0][0]
        human_msg = call_args[1]
        # With no images, content should be a list with just the text part
        assert isinstance(human_msg.content, list)
        assert len(human_msg.content) == 1
        assert human_msg.content[0]["type"] == "text"
        assert result == "Found 12% missing values"


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && python -m pytest tests/test_reasoning_vision.py -v`
Expected: FAIL — `test_images_passed_to_llm` fails because current code passes plain string, not list

- [ ] **Step 3: Fix the vision bug**

In `src/agent/reasoning.py`, replace lines 131-134:

```python
        response = llm.invoke([
            SystemMessage(content="Write ONE concise sentence about the key finding from this output. If there are plots, describe what visual patterns you see (trends, clusters, outliers, distributions). Be specific with numbers. Do NOT repeat things like 'the dataset loaded' — only report genuinely informative findings."),
            HumanMessage(content=f"Phase: {phase}\nOutput:\n{output_text[:1500]}"),
        ])
```

With:

```python
        response = llm.invoke([
            SystemMessage(content="Write ONE concise sentence about the key finding from this output. If there are plots, describe what visual patterns you see (trends, clusters, outliers, distributions). Be specific with numbers. Do NOT repeat things like 'the dataset loaded' — only report genuinely informative findings."),
            HumanMessage(content=content_parts),
        ])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && python -m pytest tests/test_reasoning_vision.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_reasoning_vision.py src/agent/reasoning.py
git commit -m "fix: pass images to LLM in interpret_output (vision loop was broken)"
```

---

## Task 2: Fix Stuck Notebook After Chat Investigation

**Files:**
- Modify: `backend/routers/chat.py:246-321`
- Modify: `frontend/src/hooks/useAgentStream.ts:9-21,152-153`
- Test: `tests/test_chat_completion_event.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_chat_completion_event.py`:

```python
"""Test that chat hypothesis investigation pushes a completion event."""
import unittest
from unittest.mock import patch, MagicMock, call


class TestChatCompletionEvent(unittest.TestCase):
    @patch("backend.routers.chat.run_subagent")
    @patch("backend.routers.chat.push_event")
    @patch("backend.routers.chat.execute_code")
    @patch("backend.routers.chat.is_kernel_alive", return_value=True)
    def test_investigation_pushes_completion_event(self, mock_alive, mock_exec, mock_push, mock_subagent):
        """After hypothesis investigation completes, a completion event must be pushed."""
        from src.agent.subagent import InvestigationResult

        mock_subagent.return_value = InvestigationResult(
            hypothesis_id="h1",
            hypothesis_title="Test hypothesis",
            finding="Found something",
            confidence=0.8,
        )

        from src.agent.hypothesis import Hypothesis

        hyp = Hypothesis(id="h1", title="Test hypothesis", description="Test", priority=1)

        from backend.routers.chat import _run_hypothesis_investigation

        state = {"columns": ["a", "b"], "numeric_cols": ["a"], "time_col": None}
        result = _run_hypothesis_investigation("test_session", state, hyp, "test question")

        # Check that a completion event was pushed (any event with type containing "complete")
        pushed_events = [c[0][1] for c in mock_push.call_args_list]
        completion_events = [e for e in pushed_events if "complete" in e.get("type", "")]
        assert len(completion_events) >= 1, (
            f"Expected at least one completion event, got events: {[e['type'] for e in pushed_events]}"
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && python -m pytest tests/test_chat_completion_event.py -v`
Expected: FAIL — no completion event is pushed

- [ ] **Step 3: Add completion event to chat.py**

In `backend/routers/chat.py`, add completion event at two points in `_run_hypothesis_investigation`:

After line 305 (after story update try/except block), before the return on line 307, add:

```python
        # Signal notebook that investigation is complete
        push_event(session_id, {
            "type": "chat_investigation_complete",
            "hypothesis_id": hyp.id,
            "finding": result.finding,
            "confidence": result.confidence,
        })
```

In the except block on line 314, before the return on line 316, add:

```python
        push_event(session_id, {
            "type": "chat_investigation_complete",
            "hypothesis_id": hyp.id if hasattr(hyp, 'id') else "unknown",
            "finding": f"Investigation failed: {exc}",
            "confidence": 0.0,
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && python -m pytest tests/test_chat_completion_event.py -v`
Expected: PASS

- [ ] **Step 5: Update frontend event handler**

In `frontend/src/hooks/useAgentStream.ts`, add `chat_investigation_complete` to the StreamEvent type union (after line 21):

```typescript
  | { type: "chat_investigation_complete"; hypothesis_id?: string; finding?: string; confidence?: number }
```

Add handler case in the switch statement (after the `backtrack` case, before `complete`):

```typescript
          case "chat_investigation_complete":
            store.setPipelineRunning(false);
            store.setCurrentPhase("");
            store.setLatestThinking("");
            store.setAgentActivity("complete", `Investigation complete: ${data.finding || ""}`);
            break;
```

- [ ] **Step 6: Commit**

```bash
git add backend/routers/chat.py frontend/src/hooks/useAgentStream.ts tests/test_chat_completion_event.py
git commit -m "fix: push completion event after chat hypothesis investigation (fixes stuck notebook)"
```

---

## Task 3: Knowledge Graph Redesign — Typed Nodes, Edges, Query Interface

**Files:**
- Modify: `src/agent/knowledge_graph.py` (full rewrite preserving existing API)
- Test: `tests/test_knowledge_graph.py`

- [ ] **Step 1: Write tests for new KG features**

Create `tests/test_knowledge_graph.py`:

```python
"""Tests for the redesigned knowledge graph."""
import unittest


class TestKnowledgeGraphNodes(unittest.TestCase):
    def test_add_fact_returns_id(self):
        from src.agent.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph()
        nid = kg.add_fact("12% missing in col_a", "Data Cleaning", "cell_1")
        assert nid.startswith("fact_")
        assert kg.nodes[nid].text == "12% missing in col_a"

    def test_add_investigation_creates_evidence_chain(self):
        from src.agent.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph()
        nid = kg.add_investigation(
            hypothesis_id="h1",
            hypothesis_title="Wind correlation",
            finding="Wind speed correlates with power (r=0.87)",
            evidence_cells=["c1", "c2"],
            plot_cells=["c2"],
            confidence=0.85,
            sub_findings=[{"finding": "Scatter shows linear trend", "cell_ids": ["c1"]}],
        )
        assert nid.startswith("inv_")
        node = kg.nodes[nid]
        assert node.confidence == 0.85
        assert len(node.children) == 1
        # Evidence child should exist
        child = kg.nodes[node.children[0]]
        assert child.type == "evidence"

    def test_backward_compat_get_story_sections(self):
        from src.agent.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.add_fact("Dataset has 100 rows", "Data Loading", "c1")
        kg.add_investigation("h1", "Test", "Found nothing", ["c2"], [], 0.5)
        sections = kg.get_story_sections()
        assert isinstance(sections, list)
        assert any(s["type"] == "initial" for s in sections)
        assert any(s["type"] == "investigation" for s in sections)

    def test_backward_compat_get_top_conclusions(self):
        from src.agent.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.add_investigation("h1", "A", "Finding A", [], [], 0.9)
        kg.add_investigation("h2", "B", "Finding B", [], [], 0.7)
        top = kg.get_top_conclusions(1)
        assert len(top) == 1
        assert top[0] == "Finding A"


class TestKnowledgeGraphEdges(unittest.TestCase):
    def test_add_edge(self):
        from src.agent.knowledge_graph import KnowledgeGraph, KGEdge
        kg = KnowledgeGraph()
        n1 = kg.add_fact("Fact 1", "Loading")
        n2 = kg.add_fact("Fact 2", "Loading")
        kg.add_edge(KGEdge(source_id=n1, target_id=n2, type="derived_from"))
        assert len(kg.edges) == 1
        assert kg.edges[0].source_id == n1

    def test_get_evidence_chain(self):
        from src.agent.knowledge_graph import KnowledgeGraph, KGEdge
        kg = KnowledgeGraph()
        ev1 = kg.add_fact("Evidence 1", "Analysis")
        ev2 = kg.add_fact("Evidence 2", "Analysis")
        conclusion = kg.add_investigation("h1", "H1", "Conclusion", [], [], 0.8)
        kg.add_edge(KGEdge(source_id=ev1, target_id=conclusion, type="supports"))
        kg.add_edge(KGEdge(source_id=ev2, target_id=conclusion, type="supports"))
        chain = kg.get_evidence_chain(conclusion)
        assert len(chain) == 2


class TestKnowledgeGraphQuery(unittest.TestCase):
    def test_query_by_columns(self):
        from src.agent.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.add_fact("wind_speed has 5% missing", "Cleaning", metadata={"columns": ["wind_speed"]})
        kg.add_fact("power has 0% missing", "Cleaning", metadata={"columns": ["power"]})
        results = kg.query_by_columns(["wind_speed"])
        assert len(results) == 1
        assert "wind_speed" in results[0].text

    def test_query_by_type(self):
        from src.agent.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.add_fact("A fact", "Loading")
        kg.add_investigation("h1", "H1", "A conclusion", [], [], 0.8)
        facts = kg.query_by_type("fact")
        assert len(facts) == 1
        conclusions = kg.query_by_type("conclusion")
        assert len(conclusions) == 1


class TestKnowledgeGraphDedup(unittest.TestCase):
    def test_investigation_hash_detects_duplicate(self):
        from src.agent.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.add_investigation(
            "h1", "Wind vs Power", "They correlate",
            [], [], 0.8,
            metadata={"columns": ["wind_speed", "power"], "analysis_type": "correlation"},
        )
        # Same columns + analysis type should be detected as duplicate
        existing = kg.find_duplicate_investigation(["wind_speed", "power"], "correlation")
        assert existing is not None

    def test_no_false_duplicate(self):
        from src.agent.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.add_investigation(
            "h1", "Wind vs Power", "They correlate",
            [], [], 0.8,
            metadata={"columns": ["wind_speed", "power"], "analysis_type": "correlation"},
        )
        existing = kg.find_duplicate_investigation(["temperature"], "distribution")
        assert existing is None

    def test_find_similar_hypothesis(self):
        from src.agent.knowledge_graph import KnowledgeGraph
        from src.agent.hypothesis import Hypothesis
        kg = KnowledgeGraph()
        kg.add_investigation(
            "h1", "Wind speed vs power correlation", "They correlate r=0.87",
            [], [], 0.85,
            metadata={"columns": ["wind_speed", "power"], "analysis_type": "correlation"},
        )
        # Similar hypothesis (same columns, similar title)
        hyp = Hypothesis(
            id="h2", title="Relationship between wind speed and power",
            description="Test", priority=1, relevant_cols=["wind_speed", "power"],
        )
        result = kg.find_similar_hypothesis(hyp, threshold=0.5)
        assert result is not None


class TestKnowledgeGraphConfidence(unittest.TestCase):
    def test_reinforce_increases_confidence(self):
        from src.agent.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph()
        nid = kg.add_investigation("h1", "H1", "Finding", [], [], 0.5)
        old_conf = kg.nodes[nid].confidence
        kg.reinforce(nid)
        assert kg.nodes[nid].confidence > old_conf

    def test_reinforce_caps_at_099(self):
        from src.agent.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph()
        nid = kg.add_investigation("h1", "H1", "Finding", [], [], 0.98)
        for _ in range(10):
            kg.reinforce(nid)
        assert kg.nodes[nid].confidence <= 0.99


class TestKnowledgeGraphContext(unittest.TestCase):
    def test_get_context_for_hypothesis_generation(self):
        from src.agent.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.add_fact("100 rows loaded", "Data Loading")
        kg.add_fact("wind_speed is float64", "Data Loading")
        kg.add_investigation("h1", "Wind test", "Wind is important", [], [], 0.8)
        context = kg.get_context_for_hypothesis_generation()
        assert "100 rows" in context
        assert "Wind is important" in context

    def test_get_context_for_chat(self):
        from src.agent.knowledge_graph import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.add_fact("wind_speed has 5% missing", "Cleaning", metadata={"columns": ["wind_speed"]})
        kg.add_fact("power is normally distributed", "Analysis", metadata={"columns": ["power"]})
        context = kg.get_context_for_chat("tell me about wind speed")
        assert "wind_speed" in context


class TestKnowledgeGraphSerialization(unittest.TestCase):
    def test_roundtrip(self):
        from src.agent.knowledge_graph import KnowledgeGraph, KGEdge
        kg = KnowledgeGraph()
        f1 = kg.add_fact("Fact 1", "Loading")
        inv1 = kg.add_investigation("h1", "H1", "Conclusion", [], [], 0.8)
        kg.add_edge(KGEdge(source_id=f1, target_id=inv1, type="supports"))
        data = kg.to_dict()
        kg2 = KnowledgeGraph.from_dict(data)
        assert len(kg2.nodes) == len(kg.nodes)
        assert len(kg2.edges) == len(kg.edges)
        assert kg2.get_top_conclusions(1) == kg.get_top_conclusions(1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && python -m pytest tests/test_knowledge_graph.py -v`
Expected: FAIL — new methods don't exist yet

- [ ] **Step 3: Implement the redesigned KnowledgeGraph**

Replace `src/agent/knowledge_graph.py` with:

```python
"""Knowledge graph for accumulating EDA findings with evidence chains."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

_LOG = logging.getLogger(__name__)


@dataclass
class KnowledgeNode:
    """A single node in the knowledge graph."""
    id: str
    type: str  # "fact", "hypothesis", "evidence", "conclusion", "visual_insight"
    text: str
    phase: str = ""
    cell_ids: list[str] = field(default_factory=list)
    plot_cell_ids: list[str] = field(default_factory=list)
    confidence: float = 1.0
    hypothesis_id: str | None = None
    children: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    loop_number: int = 0
    superseded_by: str | None = None
    is_latest: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "text": self.text,
            "phase": self.phase,
            "cell_ids": self.cell_ids,
            "plot_cell_ids": self.plot_cell_ids,
            "confidence": self.confidence,
            "hypothesis_id": self.hypothesis_id,
            "children": self.children,
            "metadata": self.metadata,
            "loop_number": self.loop_number,
            "superseded_by": self.superseded_by,
            "is_latest": self.is_latest,
        }


@dataclass
class KGEdge:
    """A typed edge between two nodes."""
    source_id: str
    target_id: str
    type: str  # "supports", "contradicts", "derived_from", "tested_by", "visualized_by", "supersedes"
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "type": self.type,
            "weight": self.weight,
            "metadata": self.metadata,
        }


class KnowledgeGraph:
    """Accumulates findings from all phases and investigations with query support."""

    def __init__(self):
        self.nodes: dict[str, KnowledgeNode] = {}
        self.edges: list[KGEdge] = []
        self._counter = 0

    def _next_id(self, prefix: str = "n") -> str:
        self._counter += 1
        return f"{prefix}_{self._counter}"

    # ── Mutation ──

    def add_fact(self, text: str, phase: str, cell_id: str | None = None,
                 metadata: dict | None = None) -> str:
        nid = self._next_id("fact")
        self.nodes[nid] = KnowledgeNode(
            id=nid, type="fact", text=text, phase=phase,
            cell_ids=[cell_id] if cell_id else [],
            metadata=metadata or {},
        )
        return nid

    def add_investigation(
        self,
        hypothesis_id: str,
        hypothesis_title: str,
        finding: str,
        evidence_cells: list[str],
        plot_cells: list[str],
        confidence: float = 0.8,
        sub_findings: list[dict] | None = None,
        metadata: dict | None = None,
        loop_number: int = 0,
    ) -> str:
        nid = self._next_id("inv")
        node = KnowledgeNode(
            id=nid, type="conclusion", text=finding,
            phase=f"Investigation: {hypothesis_title}",
            cell_ids=evidence_cells, plot_cell_ids=plot_cells,
            confidence=confidence, hypothesis_id=hypothesis_id,
            metadata=metadata or {},
            loop_number=loop_number,
        )

        if sub_findings:
            for sf in sub_findings:
                child_id = self._next_id("sub")
                self.nodes[child_id] = KnowledgeNode(
                    id=child_id, type="evidence", text=sf.get("finding", ""),
                    phase=node.phase,
                    cell_ids=sf.get("cell_ids", []),
                    plot_cell_ids=sf.get("plot_cells", []),
                    confidence=sf.get("confidence", 0.7),
                    hypothesis_id=hypothesis_id,
                )
                node.children.append(child_id)
                self.edges.append(KGEdge(
                    source_id=child_id, target_id=nid, type="supports",
                ))

        self.nodes[nid] = node
        return nid

    def add_edge(self, edge: KGEdge) -> None:
        self.edges.append(edge)

    def reinforce(self, node_id: str) -> None:
        node = self.nodes.get(node_id)
        if node:
            node.confidence = min(0.99, node.confidence + 0.1 * (1 - node.confidence))

    def supersede(self, old_id: str, new_id: str) -> None:
        old = self.nodes.get(old_id)
        if old:
            old.superseded_by = new_id
            old.is_latest = False
            self.edges.append(KGEdge(source_id=new_id, target_id=old_id, type="supersedes"))

    # ── Query ──

    def query_by_type(self, node_type: str) -> list[KnowledgeNode]:
        return [n for n in self.nodes.values() if n.type == node_type and n.is_latest]

    def query_by_columns(self, columns: list[str]) -> list[KnowledgeNode]:
        col_set = set(c.lower() for c in columns)
        results = []
        for node in self.nodes.values():
            if not node.is_latest:
                continue
            node_cols = set(c.lower() for c in node.metadata.get("columns", []))
            if node_cols & col_set:
                results.append(node)
            elif any(c.lower() in node.text.lower() for c in columns):
                results.append(node)
        return results

    def get_evidence_chain(self, conclusion_id: str) -> list[KnowledgeNode]:
        evidence_ids = set()
        for edge in self.edges:
            if edge.target_id == conclusion_id and edge.type in ("supports", "contradicts"):
                evidence_ids.add(edge.source_id)
        return [self.nodes[nid] for nid in evidence_ids if nid in self.nodes]

    # ── Deduplication ──

    def _investigation_hash(self, columns: list[str], analysis_type: str) -> str:
        key = "|".join(sorted(c.lower() for c in columns)) + "|" + analysis_type.lower()
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def find_duplicate_investigation(self, columns: list[str], analysis_type: str) -> KnowledgeNode | None:
        target_hash = self._investigation_hash(columns, analysis_type)
        for node in self.nodes.values():
            if node.type != "conclusion" or not node.is_latest:
                continue
            node_cols = node.metadata.get("columns", [])
            node_type = node.metadata.get("analysis_type", "")
            if node_cols and node_type:
                if self._investigation_hash(node_cols, node_type) == target_hash:
                    return node
        return None

    def find_similar_hypothesis(self, hypothesis, threshold: float = 0.5) -> KnowledgeNode | None:
        """Find an existing conclusion that overlaps with this hypothesis."""
        hyp_cols = set(c.lower() for c in (hypothesis.relevant_cols or []))
        if not hyp_cols:
            return None
        best_match = None
        best_overlap = 0.0
        for node in self.nodes.values():
            if node.type != "conclusion" or not node.is_latest:
                continue
            node_cols = set(c.lower() for c in node.metadata.get("columns", []))
            if not node_cols:
                # Fallback: check relevant_cols from hypothesis_id matching
                continue
            overlap = len(hyp_cols & node_cols) / max(len(hyp_cols | node_cols), 1)
            if overlap > best_overlap:
                best_overlap = overlap
                best_match = node
        if best_overlap >= threshold:
            return best_match
        return None

    # ── Context generation ──

    def get_context_for_hypothesis_generation(self) -> str:
        parts = []
        facts = self.query_by_type("fact")
        if facts:
            parts.append("Known facts:")
            for f in facts[:15]:
                parts.append(f"  - {f.text}")

        conclusions = self.query_by_type("conclusion")
        if conclusions:
            parts.append("\nPrevious investigation conclusions:")
            for c in sorted(conclusions, key=lambda n: -n.confidence)[:10]:
                parts.append(f"  - [{c.confidence:.0%}] {c.text}")

        visual = self.query_by_type("visual_insight")
        if visual:
            parts.append("\nVisual insights from plots:")
            for v in visual[:5]:
                parts.append(f"  - {v.text}")

        return "\n".join(parts)

    def get_context_for_chat(self, question: str) -> str:
        words = set(question.lower().split())
        scored = []
        for node in self.nodes.values():
            if not node.is_latest:
                continue
            node_words = set(node.text.lower().split())
            overlap = len(words & node_words)
            # Also check column metadata
            node_cols = node.metadata.get("columns", [])
            col_overlap = sum(1 for c in node_cols if c.lower() in question.lower())
            score = overlap + col_overlap * 3
            if score > 0:
                scored.append((score, node))
        scored.sort(key=lambda x: -x[0])
        parts = []
        for _, node in scored[:8]:
            confidence_str = f" [{node.confidence:.0%}]" if node.type == "conclusion" else ""
            parts.append(f"- [{node.phase}]{confidence_str} {node.text}")
        return "\n".join(parts) if parts else "No relevant findings."

    # ── Backward-compatible API ──

    def get_story_sections(self) -> list[dict]:
        phase_nodes: dict[str, list[KnowledgeNode]] = {}
        for node in self.nodes.values():
            if not node.is_latest:
                continue
            phase_nodes.setdefault(node.phase, []).append(node)

        sections = []
        for phase in ["Data Loading", "Data Cleaning", "Univariate Analysis",
                       "Time Series", "Dynamics", "Correlations", "Train/Test Split"]:
            nodes = phase_nodes.get(phase, [])
            if not nodes:
                continue
            all_cells = []
            all_plots = []
            findings = []
            for n in nodes:
                findings.append(n.text)
                all_cells.extend(n.cell_ids)
                all_plots.extend(n.plot_cell_ids)
            sections.append({
                "phase": phase,
                "title": phase,
                "content": "\n".join(f"- {f}" for f in findings),
                "cell_ids": list(set(all_cells)),
                "plot_cell_ids": list(set(all_plots)),
                "type": "initial",
            })

        investigations = [n for n in self.nodes.values() if n.type == "conclusion" and n.is_latest]
        investigations.sort(key=lambda n: n.confidence, reverse=True)

        for inv in investigations:
            children_text = []
            child_cells = []
            child_plots = []
            for child_id in inv.children:
                child = self.nodes.get(child_id)
                if child:
                    children_text.append(f"  - {child.text}")
                    child_cells.extend(child.cell_ids)
                    child_plots.extend(child.plot_cell_ids)

            content = inv.text
            if children_text:
                content += "\n\nSupporting evidence:\n" + "\n".join(children_text)

            sections.append({
                "phase": inv.phase,
                "title": inv.phase.replace("Investigation: ", ""),
                "content": content,
                "cell_ids": list(set(inv.cell_ids + child_cells)),
                "plot_cell_ids": list(set(inv.plot_cell_ids + child_plots)),
                "confidence": inv.confidence,
                "type": "investigation",
            })

        return sections

    def get_top_conclusions(self, n: int = 5) -> list[str]:
        conclusions = [
            node for node in self.nodes.values()
            if node.type == "conclusion" and node.is_latest
        ]
        conclusions.sort(key=lambda n: n.confidence, reverse=True)
        return [c.text for c in conclusions[:n]]

    # ── Serialization ──

    def to_dict(self) -> dict:
        return {
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict) -> KnowledgeGraph:
        kg = cls()
        for nid, nd in data.get("nodes", {}).items():
            kg.nodes[nid] = KnowledgeNode(**nd)
            kg._counter = max(kg._counter, int(nid.split("_")[-1]) if "_" in nid else 0)
        for ed in data.get("edges", []):
            kg.edges.append(KGEdge(**ed))
        return kg
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && python -m pytest tests/test_knowledge_graph.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent/knowledge_graph.py tests/test_knowledge_graph.py
git commit -m "feat: redesign knowledge graph with typed edges, query, dedup, confidence"
```

---

## Task 4: Kernel Pool Manager

**Files:**
- Create: `backend/services/kernel_pool.py`
- Test: `tests/test_kernel_pool.py`

- [ ] **Step 1: Write tests**

Create `tests/test_kernel_pool.py`:

```python
"""Tests for the kernel pool manager."""
import unittest
from unittest.mock import patch, MagicMock


class TestKernelPoolManager(unittest.TestCase):
    def test_get_main_kernel_creates_once(self):
        from backend.services.kernel_pool import KernelPoolManager
        pool = KernelPoolManager()
        with patch("backend.services.kernel_pool.get_or_create_kernel") as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client
            k1 = pool.get_main_kernel("session1")
            k2 = pool.get_main_kernel("session1")
            # Should only create once
            mock_create.assert_called_once_with("session1")

    def test_allocate_subagent_kernels(self):
        from backend.services.kernel_pool import KernelPoolManager
        pool = KernelPoolManager()
        with patch("backend.services.kernel_pool.get_or_create_kernel") as mock_create:
            mock_create.return_value = MagicMock()
            kernel_ids = pool.allocate_subagent_kernels("session1", 3)
            assert len(kernel_ids) == 3
            assert all(kid.startswith("session1_sub_") for kid in kernel_ids)
            assert mock_create.call_count == 3

    def test_execute_on_subkernel(self):
        from backend.services.kernel_pool import KernelPoolManager
        pool = KernelPoolManager()
        with patch("backend.services.kernel_pool.get_or_create_kernel") as mock_create:
            mock_create.return_value = MagicMock()
            pool.allocate_subagent_kernels("session1", 1)
        with patch("backend.services.kernel_pool.execute_code") as mock_exec:
            mock_exec.return_value = ([{"text": "ok"}], None)
            outputs, error = pool.execute_on_subkernel("session1_sub_0", "print('hi')")
            assert error is None
            assert outputs[0]["text"] == "ok"

    def test_shutdown_subagent_kernels(self):
        from backend.services.kernel_pool import KernelPoolManager
        pool = KernelPoolManager()
        with patch("backend.services.kernel_pool.get_or_create_kernel") as mock_create:
            mock_create.return_value = MagicMock()
            pool.allocate_subagent_kernels("session1", 2)
        with patch("backend.services.kernel_pool.shutdown_kernel") as mock_shutdown:
            pool.shutdown_subagent_kernels("session1")
            assert mock_shutdown.call_count == 2
            # Subkernels should be gone
            assert "session1" not in pool._sub_kernels or len(pool._sub_kernels["session1"]) == 0


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && python -m pytest tests/test_kernel_pool.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement KernelPoolManager**

Create `backend/services/kernel_pool.py`:

```python
"""Kernel pool manager for parallel subagent execution."""
from __future__ import annotations

import logging
import threading

from backend.services.kernel_manager import (
    get_or_create_kernel,
    execute_code,
    shutdown_kernel,
)

_LOG = logging.getLogger(__name__)


class KernelPoolManager:
    """Manages a main kernel + N subagent kernels per session."""

    def __init__(self):
        self._main_kernels: dict[str, object] = {}  # session_id -> client
        self._sub_kernels: dict[str, list[str]] = {}  # session_id -> [kernel_ids]
        self._lock = threading.Lock()

    def get_main_kernel(self, session_id: str) -> object:
        with self._lock:
            if session_id not in self._main_kernels:
                self._main_kernels[session_id] = get_or_create_kernel(session_id)
            return self._main_kernels[session_id]

    def allocate_subagent_kernels(self, session_id: str, n: int) -> list[str]:
        kernel_ids = []
        with self._lock:
            self._sub_kernels.setdefault(session_id, [])
        for i in range(n):
            kid = f"{session_id}_sub_{i}"
            get_or_create_kernel(kid)
            with self._lock:
                self._sub_kernels[session_id].append(kid)
            kernel_ids.append(kid)
            _LOG.info("Allocated subagent kernel: %s", kid)
        return kernel_ids

    def execute_on_subkernel(
        self, kernel_id: str, code: str, timeout: int = 60, cell_id: str | None = None,
    ) -> tuple[list, str | None]:
        return execute_code(kernel_id, code, timeout=timeout, cell_id=cell_id)

    def inject_dataset_preamble(self, kernel_id: str, session_dir: str) -> None:
        """Load the cached parquet into a subagent kernel."""
        code = (
            "import pandas as pd\nimport numpy as np\n"
            "import matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\n"
            f"df = pd.read_parquet('{session_dir}/.cache/df_clean.parquet')\n"
            f"print(f'Loaded {{len(df)}} rows x {{len(df.columns)}} cols')"
        )
        execute_code(kernel_id, code, timeout=15)

    def shutdown_subagent_kernels(self, session_id: str) -> None:
        with self._lock:
            kernel_ids = self._sub_kernels.pop(session_id, [])
        for kid in kernel_ids:
            try:
                shutdown_kernel(kid)
                _LOG.info("Shutdown subagent kernel: %s", kid)
            except Exception as exc:
                _LOG.warning("Failed to shutdown %s: %s", kid, exc)

    def shutdown_all(self, session_id: str) -> None:
        self.shutdown_subagent_kernels(session_id)
        with self._lock:
            self._main_kernels.pop(session_id, None)
        try:
            shutdown_kernel(session_id)
        except Exception:
            pass
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && python -m pytest tests/test_kernel_pool.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/kernel_pool.py tests/test_kernel_pool.py
git commit -m "feat: add kernel pool manager for parallel subagent execution"
```

---

## Task 5: Wire KG Into Hypothesis Generation & Chat

**Files:**
- Modify: `src/agent/hypothesis.py:32-81` (add KG context param)
- Modify: `src/chat/chat_agent.py:13-58` (use KG in ChatContext)
- Modify: `backend/routers/chat.py:246-321` (dedup before investigating)
- Modify: `backend/routers/run.py:188-208` (pass KG to chat state)

- [ ] **Step 1: Update hypothesis generation to accept KG context**

In `src/agent/hypothesis.py`, modify `generate_hypotheses` signature (line 32) to accept optional KG context:

```python
def generate_hypotheses(
    columns: list[str],
    numeric_cols: list[str],
    time_col: str | None,
    findings: list[dict],
    row_count: int,
    col_count: int,
    kg_context: str = "",
) -> list[Hypothesis]:
```

In the prompt (line 49), after the `Initial findings:` block, add:

```python
    kg_section = ""
    if kg_context:
        kg_section = f"""

Previous investigation results (do NOT re-investigate these):
{kg_context}

IMPORTANT: Generate NOVEL hypotheses that are NOT already covered above.
"""
```

And insert `{kg_section}` into the prompt string after `{findings_text}`.

- [ ] **Step 2: Update ChatContext to use KG**

In `src/chat/chat_agent.py`, modify `ChatContext.__init__` to accept KG:

```python
class ChatContext:
    def __init__(self, session_id: str, state: dict | None = None, kg=None):
        self.session_id = session_id
        self.state = state or {}
        self.kg = kg
```

Modify `get_summary` to use KG when available:

```python
    def get_summary(self, question: str | None = None) -> str:
        parts = []
        rc = self.state.get("row_count", 0)
        cc = self.state.get("col_count", 0)
        tc = self.state.get("time_col")
        nc = self.state.get("numeric_cols", [])
        parts.append(f"Dataset: {rc} rows x {cc} cols.")
        if tc:
            parts.append(f"Time column: {tc}")
        if nc:
            parts.append(f"Numeric columns: {', '.join(nc[:10])}")
        phases = self.state.get("phases_completed", [])
        if phases:
            parts.append(f"Phases completed: {', '.join(phases)}")

        if self.kg and question:
            context = self.kg.get_context_for_chat(question)
            parts.append(f"\nRelevant findings:\n{context}")
        elif self.kg:
            conclusions = self.kg.get_top_conclusions(5)
            if conclusions:
                parts.append("\nTop conclusions:")
                for c in conclusions:
                    parts.append(f"  - {c}")
        else:
            findings = self.state.get("findings") or self.state.get("insights") or []
            if findings:
                parts.append("Key findings:")
                for f in findings:
                    if isinstance(f, dict):
                        parts.append(f"  - [{f.get('phase', '')}] {f.get('finding', f.get('description', ''))}")
                    else:
                        parts.append(f"  - {f}")

        ds = self.state.get("decision_summary", {})
        if isinstance(ds, dict) and ds.get("summary"):
            parts.append(f"Summary: {ds['summary'][:500]}")
        return "\n".join(parts) if parts else "No analysis results available yet."
```

- [ ] **Step 3: Add KG dedup to chat investigation**

In `backend/routers/chat.py`, at the top of `_run_hypothesis_investigation` (line 246), after imports, add dedup check:

```python
    # Check KG for existing answer before investigating
    kg = _session_kgs.get(session_id)
    if kg is not None:
        existing = kg.find_similar_hypothesis(hyp, threshold=0.5)
        if existing and existing.confidence > 0.6:
            return {
                "role": "agent",
                "type": "text",
                "content": (
                    f"**Previously investigated:** {existing.phase.replace('Investigation: ', '')}\n\n"
                    f"{existing.text}\n\n"
                    f"*Confidence: {existing.confidence:.0%}* (from earlier investigation)"
                ),
                "action_code": None,
            }
```

Add a new module-level dict and setter near line 18:

```python
_session_kgs: dict[str, object] = {}

def set_session_kg(session_id: str, kg) -> None:
    _session_kgs[session_id] = kg
```

- [ ] **Step 4: Pass KG from run.py to chat state**

In `backend/routers/run.py`, after line 203 (`set_session_state(session_id, chat_state)`), add:

```python
            if kg is not None:
                from backend.routers.chat import set_session_kg
                set_session_kg(session_id, kg)
```

- [ ] **Step 5: Commit**

```bash
git add src/agent/hypothesis.py src/chat/chat_agent.py backend/routers/chat.py backend/routers/run.py
git commit -m "feat: wire knowledge graph into hypothesis generation and chat agent"
```

---

## Task 6: Refactor Subagent to Accept kernel_id and Track Images

**Files:**
- Modify: `src/agent/subagent.py`

- [ ] **Step 1: Add kernel_id parameter and image tracking**

Modify `run_subagent` signature to accept optional `kernel_id` and return images:

Add `kernel_id: str | None = None` to the function signature (after `session_id`).

Add `notebook_id: str = "main"` parameter too.

In `InvestigationResult`, add a new field:

```python
    images: dict[str, list[str]] = field(default_factory=dict)  # cell_id -> [base64 png]
```

In `_write_and_execute`, when collecting outputs, also extract images:

After line 118 (the plot detection block), add:

```python
            # Extract images for vision analysis
            for o in outputs:
                img = o.get("data", {}).get("image/png")
                if img:
                    result.images.setdefault(cell_id, []).append(img)
```

If `kernel_id` is provided, use it for execution:

In `_write_and_execute`, change line 103 from:

```python
        outputs, error = execute_code(session_id, code, 60, cell_id=cell_id)
```

To:

```python
        exec_id = kernel_id or session_id
        outputs, error = execute_code(exec_id, code, 60, cell_id=cell_id)
```

Add `notebook_id` to pushed events (cell_write, cell_executing, cell_output, cell_error) by including `"notebook_id": notebook_id` in each event dict.

- [ ] **Step 2: Commit**

```bash
git add src/agent/subagent.py
git commit -m "feat: subagent accepts kernel_id for parallel execution, tracks images"
```

---

## Task 7: Refactor eda_agent.py Into Multi-Loop Orchestrator

**Files:**
- Modify: `src/agent/eda_agent.py`
- Modify: `src/agent/state.py`

- [ ] **Step 1: Add new fields to AgentState**

In `src/agent/state.py`, add after line 38:

```python
    loop_count: int = 0
    subagent_run_count: int = 0
    max_subagents: int = 3
    max_loops: int = 2
```

- [ ] **Step 2: Refactor run_agent to accept config and run loops**

In `src/agent/eda_agent.py`, modify the `run_agent` signature (line 18) to:

```python
def run_agent(
    session_id: str,
    dataset_path: str,
    push_event: Callable[[str, dict], None],
    max_subagents: int = 3,
    max_loops: int = 2,
    loop_timeout: int = 180,
):
```

Replace the investigation section (lines 459-577) with the multi-loop orchestrator:

```python
    # ---- Investigation Phase: Multi-Loop Hypothesis-Driven Deep Dives ----
    from src.agent.hypothesis import generate_hypotheses
    from src.agent.subagent import run_subagent, InvestigationResult
    from src.agent.knowledge_graph import KnowledgeGraph
    from backend.services.kernel_pool import KernelPoolManager

    kg = KnowledgeGraph()
    pool = KernelPoolManager()

    # Populate knowledge graph with pass 1 findings
    for f in state.findings:
        kg.add_fact(f.get("finding", ""), f.get("phase", ""), f.get("cell_id"))

    # Save dataset checkpoint for subagent kernels
    try:
        _write_and_run(
            f"import os; os.makedirs('.cache', exist_ok=True)\n"
            f"df.to_parquet('.cache/df_clean.parquet', index=True)\n"
            f"print('Dataset checkpoint saved')"
        )
    except Exception:
        pass

    # Get session dir for subagent preamble
    from backend.services.session_manager import get_session_dir
    session_dir = str(get_session_dir(session_id) / "uploads")

    findings_summary = "\n".join(f"- {f.get('finding', '')}" for f in state.findings if f.get('finding'))
    _write_and_run(
        "---\n\n"
        "# Deep-Dive Investigations\n\n"
        "The initial EDA is complete. The agent is now formulating and testing hypotheses "
        "based on what it discovered above.\n\n"
        "**Key findings so far:**\n\n"
        f"{findings_summary}",
        "markdown",
    )

    for loop_num in range(1, max_loops + 1):
        state.loop_count = loop_num
        _transition(
            f"Investigation Loop {loop_num}/{max_loops}",
            f"Generating hypotheses for loop {loop_num}...",
            render_cell=False,
        )

        push_event(session_id, {
            "type": "loop_start",
            "loop_number": loop_num,
            "total_loops": max_loops,
        })

        # Generate hypotheses using KG context
        try:
            kg_context = kg.get_context_for_hypothesis_generation()
            hypotheses = generate_hypotheses(
                columns=state.columns,
                numeric_cols=state.numeric_cols,
                time_col=state.time_col,
                findings=state.findings,
                row_count=state.row_count,
                col_count=state.col_count,
                kg_context=kg_context,
            )

            # Deduplicate against KG
            novel = []
            for hyp in hypotheses:
                existing = kg.find_similar_hypothesis(hyp, threshold=0.5)
                if existing and existing.confidence > 0.6:
                    _think(f"Skipping '{hyp.title}' — already investigated (confidence: {existing.confidence:.0%})")
                    continue
                novel.append(hyp)
                if len(novel) >= max_subagents:
                    break

            hypotheses = novel
        except Exception as exc:
            _LOG.warning("Hypothesis generation failed in loop %d: %s", loop_num, exc)
            hypotheses = []

        if not hypotheses:
            _think("No novel hypotheses remain. Moving to report generation.")
            push_event(session_id, {"type": "loop_complete", "loop_number": loop_num})
            break

        _think(f"Loop {loop_num}: investigating {len(hypotheses)} hypotheses in parallel.")

        _write_and_run(
            f"---\n\n## Investigation Loop {loop_num}\n\n"
            f"Testing {len(hypotheses)} hypothesis(es) in parallel.",
            "markdown",
        )

        # Allocate subagent kernels
        try:
            sub_kernel_ids = pool.allocate_subagent_kernels(session_id, len(hypotheses))
            # Inject dataset into each subagent kernel
            for kid in sub_kernel_ids:
                pool.inject_dataset_preamble(kid, session_dir)
        except Exception as exc:
            _LOG.warning("Kernel allocation failed: %s — falling back to sequential", exc)
            sub_kernel_ids = [None] * len(hypotheses)  # Fall back to main kernel

        # Run subagents in parallel via ThreadPoolExecutor
        import concurrent.futures
        cell_counters = [[1000 + i * 100] for i in range(len(hypotheses))]
        results: list[InvestigationResult] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(len(hypotheses), 1)) as executor:
            futures = {}
            for i, (hyp, kid) in enumerate(zip(hypotheses, sub_kernel_ids)):
                notebook_id = f"investigation_{hyp.id}"
                _write_and_run(
                    f"---\n\n### Hypothesis {i+1}: {hyp.title}\n\n> {hyp.description}",
                    "markdown",
                )
                push_event(session_id, {
                    "type": "subagent_start",
                    "hypothesis_id": hyp.id,
                    "notebook_id": notebook_id,
                    "title": hyp.title,
                })
                push_event(session_id, {
                    "type": "phase_transition",
                    "phase": f"Hypothesis {i+1}/{len(hypotheses)}: {hyp.title}",
                    "message": hyp.description,
                    "notebook_id": notebook_id,
                })
                future = executor.submit(
                    run_subagent,
                    hypothesis_id=hyp.id,
                    hypothesis_title=hyp.title,
                    hypothesis_description=hyp.description,
                    relevant_cols=hyp.relevant_cols,
                    all_columns=state.columns,
                    time_col=state.time_col,
                    session_id=session_id,
                    push_event=push_event,
                    execute_code=execute_code,
                    cell_counter=cell_counters[i],
                    max_cells=4,
                    kernel_id=kid,
                    notebook_id=notebook_id,
                )
                futures[future] = (hyp, notebook_id)

            for future in concurrent.futures.as_completed(futures, timeout=loop_timeout):
                hyp, notebook_id = futures[future]
                try:
                    result = future.result(timeout=10)
                    results.append(result)
                    state.subagent_run_count += 1

                    push_event(session_id, {
                        "type": "subagent_complete",
                        "hypothesis_id": hyp.id,
                        "notebook_id": notebook_id,
                        "finding": result.finding,
                        "confidence": result.confidence,
                    })
                except concurrent.futures.TimeoutError:
                    _LOG.warning("Subagent for %s timed out", hyp.id)
                    push_event(session_id, {
                        "type": "subagent_timeout",
                        "hypothesis_id": hyp.id,
                    })
                except Exception as exc:
                    _LOG.warning("Subagent for %s failed: %s", hyp.id, exc)

        # Shutdown subagent kernels
        pool.shutdown_subagent_kernels(session_id)

        # Ingest results into KG with vision analysis
        for result in results:
            inv_metadata = {
                "columns": result.relevant_cols if hasattr(result, 'relevant_cols') else [],
                "analysis_type": "hypothesis_investigation",
            }
            nid = kg.add_investigation(
                hypothesis_id=result.hypothesis_id,
                hypothesis_title=result.hypothesis_title,
                finding=result.finding,
                evidence_cells=result.cell_ids,
                plot_cells=result.plot_cell_ids,
                confidence=result.confidence,
                sub_findings=result.sub_findings,
                metadata=inv_metadata,
                loop_number=loop_num,
            )
            state.add_finding(f"Investigation: {result.hypothesis_title}", result.finding)

            # Vision analysis of subagent plots
            for cell_id, images in getattr(result, 'images', {}).items():
                if images:
                    try:
                        visual_finding = interpret_output(
                            f"Plot from hypothesis investigation: {result.hypothesis_title}",
                            f"Investigation: {result.hypothesis_title}",
                            images=images[:2],
                        )
                        if visual_finding:
                            from src.agent.knowledge_graph import KGEdge
                            vis_id = kg.add_fact(
                                visual_finding,
                                f"Visual: {result.hypothesis_title}",
                                metadata={"type": "visual_insight"},
                            )
                            kg.nodes[vis_id].type = "visual_insight"
                            kg.add_edge(KGEdge(source_id=vis_id, target_id=nid, type="supports"))
                    except Exception:
                        pass

            # Write conclusion
            conf_pct = int(result.confidence * 100)
            conf_label = "High" if conf_pct >= 70 else "Medium" if conf_pct >= 40 else "Low"
            _write_and_run(
                f"### Finding: {result.hypothesis_title}\n\n"
                f"{result.finding}\n\n"
                f"**Confidence:** {conf_label} ({conf_pct}%)",
                "markdown",
            )

        push_event(session_id, {"type": "loop_complete", "loop_number": loop_num})

        # Check stop condition (skip on last loop)
        if loop_num < max_loops and results:
            try:
                from src.config.config import get_chat_model
                from langchain_core.messages import SystemMessage, HumanMessage
                llm = get_chat_model()
                context = kg.get_context_for_hypothesis_generation()
                conclusions = kg.get_top_conclusions(10)
                stop_prompt = (
                    f"Based on the current knowledge about this dataset:\n\n{context}\n\n"
                    f"Top conclusions:\n" +
                    "\n".join(f"- {c}" for c in conclusions) +
                    "\n\nShould we investigate further or do we have sufficient understanding? "
                    "Reply CONTINUE or STOP with a one-sentence reason."
                )
                resp = llm.invoke([HumanMessage(content=stop_prompt)])
                if "STOP" in resp.content.upper():
                    _think(f"Agent decided to stop: {resp.content.strip()}")
                    break
            except Exception:
                pass  # Continue on error

    state.cell_count = max(state.cell_count, *(cc[0] for cc in cell_counters)) if cell_counters else state.cell_count
```

- [ ] **Step 3: Update run_agent to pass max_subagents and max_loops**

In `backend/routers/run.py`, modify `run_pipeline` (line 225) to accept body params:

```python
from pydantic import BaseModel

class RunConfig(BaseModel):
    max_subagents: int = 3
    max_loops: int = 2
    loop_timeout: int = 180

@router.post("/run/{session_id}", status_code=202)
async def run_pipeline(session_id: str, config: RunConfig = RunConfig()):
```

Pass them to `_run_agent_in_thread`:

```python
    thread = threading.Thread(
        target=_run_agent_in_thread,
        args=(session_id, dataset_path, session_dir),
        kwargs={
            "max_subagents": config.max_subagents,
            "max_loops": config.max_loops,
            "loop_timeout": config.loop_timeout,
        },
        daemon=True,
    )
```

Update `_run_agent_in_thread` signature:

```python
def _run_agent_in_thread(session_id: str, dataset_path: str, session_dir: pathlib.Path,
                         max_subagents: int = 3, max_loops: int = 2, loop_timeout: int = 180):
```

And the `run_agent` call inside it:

```python
        state = run_agent(
            session_id=session_id,
            dataset_path=dataset_path,
            push_event=push_event,
            max_subagents=max_subagents,
            max_loops=max_loops,
            loop_timeout=loop_timeout,
        )
```

- [ ] **Step 4: Commit**

```bash
git add src/agent/eda_agent.py src/agent/state.py backend/routers/run.py
git commit -m "feat: multi-loop orchestrator with parallel subagents and vision ingestion"
```

---

## Task 8: Frontend — Upload Config + New Event Types

**Files:**
- Modify: `frontend/src/components/upload/DropZone.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/hooks/useAgentStream.ts`

- [ ] **Step 1: Add config controls to DropZone**

In `frontend/src/components/upload/DropZone.tsx`, add state variables after `const [error, setError]` (line 28):

```typescript
  const [maxSubagents, setMaxSubagents] = useState(3);
  const [maxLoops, setMaxLoops] = useState(2);
```

Change the `runEda` call in `handleRun` (line 47) to:

```typescript
      runEda(data.session_id, { max_subagents: maxSubagents, max_loops: maxLoops }).catch(() => {});
```

Add config UI after the dropzone div (after line 80), before the error display:

```tsx
      {file && (
        <div className="w-full border border-outline-variant rounded-lg p-4 bg-surface-container-lowest">
          <p className="text-sm font-medium text-on-surface mb-3 font-body">Agent Configuration</p>
          <div className="flex gap-6">
            <label className="flex flex-col gap-1 text-sm text-on-surface-variant font-body">
              Subagents per loop
              <select
                value={maxSubagents}
                onChange={(e) => setMaxSubagents(Number(e.target.value))}
                className="px-3 py-1.5 rounded border border-outline-variant bg-surface text-on-surface font-body"
              >
                {[1, 2, 3, 4, 5, 6].map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm text-on-surface-variant font-body">
              Max investigation loops
              <select
                value={maxLoops}
                onChange={(e) => setMaxLoops(Number(e.target.value))}
                className="px-3 py-1.5 rounded border border-outline-variant bg-surface text-on-surface font-body"
              >
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </label>
          </div>
        </div>
      )}
```

- [ ] **Step 2: Update api.ts runEda**

In `frontend/src/lib/api.ts`, modify `runEda` (line 62):

```typescript
export async function runEda(
  sessionId: string,
  config?: { max_subagents?: number; max_loops?: number; loop_timeout?: number },
): Promise<RunResponse> {
  const res = await fetch(`${API_BASE}/run/${sessionId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config || {}),
  });
  return res.json();
}
```

- [ ] **Step 3: Add new event types to useAgentStream**

In `frontend/src/hooks/useAgentStream.ts`, add to the StreamEvent union (after line 21):

```typescript
  | { type: "subagent_start"; hypothesis_id?: string; notebook_id?: string; title?: string }
  | { type: "subagent_complete"; hypothesis_id?: string; notebook_id?: string; finding?: string; confidence?: number }
  | { type: "subagent_timeout"; hypothesis_id?: string }
  | { type: "loop_start"; loop_number?: number; total_loops?: number }
  | { type: "loop_complete"; loop_number?: number }
  | { type: "chat_investigation_complete"; hypothesis_id?: string; finding?: string; confidence?: number }
```

Add handlers in the switch statement (before the `complete` case):

```typescript
          case "subagent_start":
            store.setAgentActivity("thinking", `Starting investigation: ${data.title || ""}`, {
              hypothesisId: data.hypothesis_id,
            });
            if (data.notebook_id && data.title) {
              store.addHypothesisGroup(data.notebook_id, data.title);
            }
            break;

          case "subagent_complete":
            store.setAgentActivity("complete", `Investigation complete: ${data.finding?.slice(0, 80) || ""}`, {
              hypothesisId: data.hypothesis_id,
            });
            break;

          case "subagent_timeout":
            store.setAgentActivity("fixing", `Investigation timed out`, {
              hypothesisId: data.hypothesis_id,
            });
            break;

          case "loop_start":
            store.setCurrentPhase(`Investigation Loop ${data.loop_number || 1}/${data.total_loops || 1}`);
            break;

          case "loop_complete":
            store.setAgentActivity("thinking", `Loop ${data.loop_number} complete, analyzing results...`);
            break;

          case "chat_investigation_complete":
            store.setPipelineRunning(false);
            store.setCurrentPhase("");
            store.setLatestThinking("");
            store.setAgentActivity("complete", `Investigation complete: ${data.finding || ""}`);
            break;
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/upload/DropZone.tsx frontend/src/lib/api.ts frontend/src/hooks/useAgentStream.ts
git commit -m "feat: upload config panel (N subagents, M loops) + new streaming events"
```

---

## Task 9: Reduce Artificial Delays

**Files:**
- Modify: `src/agent/eda_agent.py` (multiple sleep calls)

- [ ] **Step 1: Replace sleep(0.1) and sleep(0.2) with sleep(0.02)**

In `src/agent/eda_agent.py`, find and replace all `time.sleep(0.1)` with `time.sleep(0.02)` and all `time.sleep(0.2)` with `time.sleep(0.02)`. Keep `time.sleep(0.05)` as-is (those are in subagent.py and are already short).

Lines to change:
- Line 50: `time.sleep(0.1)` -> `time.sleep(0.02)`
- Line 74: `time.sleep(0.1)` -> `time.sleep(0.02)`
- Line 99: `time.sleep(0.05)` -> keep as-is
- Line 120: `time.sleep(0.2)` -> `time.sleep(0.02)`
- Line 66: `time.sleep(0.05)` -> keep as-is

- [ ] **Step 2: Commit**

```bash
git add src/agent/eda_agent.py
git commit -m "perf: reduce artificial sleep delays from 100-200ms to 20ms"
```

---

## Task 10: Integration Smoke Test

**Files:**
- Create: `tests/test_orchestrator.py`

- [ ] **Step 1: Write integration test**

Create `tests/test_orchestrator.py`:

```python
"""Smoke test for the multi-loop orchestrator."""
import unittest
from unittest.mock import patch, MagicMock


class TestOrchestratorConfig(unittest.TestCase):
    def test_run_agent_accepts_new_params(self):
        """Verify run_agent accepts max_subagents and max_loops."""
        import inspect
        from src.agent.eda_agent import run_agent
        sig = inspect.signature(run_agent)
        assert "max_subagents" in sig.parameters
        assert "max_loops" in sig.parameters
        assert "loop_timeout" in sig.parameters
        assert sig.parameters["max_subagents"].default == 3
        assert sig.parameters["max_loops"].default == 2

    def test_state_has_loop_fields(self):
        from src.agent.state import AgentState
        state = AgentState(dataset_path="/tmp/test.csv", session_id="test")
        assert hasattr(state, "loop_count")
        assert hasattr(state, "subagent_run_count")
        assert hasattr(state, "max_subagents")
        assert hasattr(state, "max_loops")

    def test_kg_imported_in_eda_agent(self):
        """The KG should be used in the investigation phase."""
        import ast
        with open("src/agent/eda_agent.py") as f:
            source = f.read()
        assert "KnowledgeGraph" in source
        assert "get_context_for_hypothesis_generation" in source
        assert "find_similar_hypothesis" in source

    def test_subagent_accepts_kernel_id(self):
        import inspect
        from src.agent.subagent import run_subagent
        sig = inspect.signature(run_subagent)
        assert "kernel_id" in sig.parameters


class TestRunEndpointConfig(unittest.TestCase):
    def test_run_endpoint_accepts_config(self):
        """The run endpoint should accept max_subagents and max_loops."""
        import ast
        with open("backend/routers/run.py") as f:
            source = f.read()
        assert "max_subagents" in source
        assert "max_loops" in source


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run all tests**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && python -m pytest tests/ -v --ignore=tests/test_pipeline_integration.py --ignore=tests/test_phases.py -x`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_orchestrator.py
git commit -m "test: add orchestrator smoke tests for multi-loop architecture"
```

---

## Execution Notes

**Task dependencies:**
- Tasks 1-2 are independent bug fixes — can run in parallel
- Task 3 (KG redesign) is a prerequisite for Tasks 5 and 7
- Task 4 (kernel pool) is a prerequisite for Task 7
- Task 5 (wire KG) depends on Task 3
- Task 6 (subagent refactor) can run after Task 4
- Task 7 (orchestrator) depends on Tasks 3, 4, 5, 6
- Task 8 (frontend) can run in parallel with Tasks 4-7
- Task 9 (delays) is independent
- Task 10 (smoke test) runs last

**Parallel execution plan:**
- Wave 1: Tasks 1, 2, 8, 9 (all independent)
- Wave 2: Tasks 3, 4 (both independent)
- Wave 3: Tasks 5, 6 (depend on 3, 4 respectively)
- Wave 4: Task 7 (depends on 3, 4, 5, 6)
- Wave 5: Task 10 (smoke test)
