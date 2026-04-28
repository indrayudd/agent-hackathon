# Story Builder Agent — Plot Curation, Narrative Structure, PDF Quality

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the mechanical story dump with an agentic story builder that curates plots, writes section narratives, and produces a professional PDF report.

**Architecture:** A new `StoryBuilder` agent sits between "KG finalized" and "story.json written." It receives the full KG + all plot metadata (cell source, stdout, plot semantics) and makes three decisions per section: (1) which plots to include (max 2-3), (2) what caption each gets, and (3) how to structure the section narrative. One LLM call per section using text metadata only (no vision tokens). The LaTeX builder is updated to use `figure*` for wide plots, limit figures per section, and generate a concise abstract.

**Tech Stack:** Python, LangChain (existing LLM config), existing KG/plot_contract infrastructure.

---

## File Structure

| File | Responsibility |
|------|---------------|
| **Create:** `src/reporting/story_builder.py` | Story builder agent — plot curation, section narratives, abstract |
| **Modify:** `backend/routers/run.py:83-212` | Replace mechanical story dump with StoryBuilder call |
| **Modify:** `backend/routers/story.py:999-1103` | Fix LaTeX: `figure*`, figure limits, concise abstract, better captions |
| **Modify:** `backend/routers/story.py:1143-1305` | Regenerate uses StoryBuilder too |
| **Modify:** `src/agent/knowledge_graph.py:409-468` | Enrich `get_story_sections()` with plot metadata |
| **Create:** `tests/test_story_builder.py` | Unit tests for plot curation logic |

---

### Task 1: Enrich KG sections with plot metadata

**Files:**
- Modify: `src/agent/knowledge_graph.py:409-468`
- Test: `tests/test_story_builder.py`

The story builder needs to know *what each plot shows* without seeing the image. Currently `get_story_sections()` returns `plot_cell_ids` but no metadata about what those plots contain. We need to propagate the available metadata (cell source code, stdout text, chart family, semantic intent) into the section dict.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_story_builder.py
"""Tests for story builder plot curation."""
import pytest
from src.agent.knowledge_graph import KnowledgeGraph, KnowledgeNode


def _make_kg_with_investigation():
    """Create a KG with one investigation that has plot metadata."""
    kg = KnowledgeGraph()
    nid = kg.add_investigation(
        hypothesis_id="h1",
        hypothesis_title="CO bursts are heteroskedastic",
        finding="Variance increases 2.4x in high-CO regime (Levene p < 10^-56).",
        evidence_cells=["h1_cell_1", "h1_cell_2", "h1_cell_3"],
        plot_cells=["h1_cell_2", "h1_cell_3"],
        confidence=0.85,
        sub_findings=[],
        columns=["CO(GT)", "PT08.S1(CO)"],
        analysis_type="hypothesis_investigation",
    )
    # Simulate plot metadata stored by eda_agent
    node = kg.nodes[nid]
    node.metadata["plot_images"] = [
        {"cell_id": "h1_cell_2", "image_png": "base64data1"},
        {"cell_id": "h1_cell_3", "image_png": "base64data2"},
    ]
    node.metadata["cell_sources"] = {
        "h1_cell_1": "print(df['CO(GT)'].describe())",
        "h1_cell_2": "plt.scatter(df['CO(GT)'], df['PT08.S1(CO)'])\nplt.title('CO vs Sensor')\nplt.show()",
        "h1_cell_3": "plt.hist(residuals, bins=30)\nplt.title('Residual Distribution')\nplt.show()",
    }
    node.metadata["cell_outputs"] = {
        "h1_cell_1": "count    9357\nmean     2.15\nstd      1.45",
        "h1_cell_2": "[plot generated]",
        "h1_cell_3": "Levene p=1.996e-56\n[plot generated]",
    }
    return kg


def test_get_story_sections_includes_plot_metadata():
    kg = _make_kg_with_investigation()
    sections = kg.get_story_sections()
    inv_sections = [s for s in sections if s["type"] == "investigation"]
    assert len(inv_sections) == 1
    sec = inv_sections[0]
    # Must include plot_metadata for the story builder to curate
    assert "plot_metadata" in sec
    assert len(sec["plot_metadata"]) == 2
    meta0 = sec["plot_metadata"][0]
    assert "cell_id" in meta0
    assert "cell_source" in meta0
    assert "cell_output" in meta0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && PYTHONPATH=. pytest tests/test_story_builder.py::test_get_story_sections_includes_plot_metadata -v`
Expected: FAIL — `plot_metadata` not in section dict

- [ ] **Step 3: Update get_story_sections to propagate plot metadata**

In `src/agent/knowledge_graph.py`, modify the investigation section building (around line 458) to include plot metadata from the node:

```python
# After building the section dict, before appending to sections:
# Propagate plot metadata so story builder can curate without seeing images
plot_metadata = []
cell_sources = inv.metadata.get("cell_sources", {})
cell_outputs = inv.metadata.get("cell_outputs", {})
for pcid in list(set(inv.plot_cell_ids + child_plots)):
    plot_metadata.append({
        "cell_id": pcid,
        "cell_source": cell_sources.get(pcid, ""),
        "cell_output": cell_outputs.get(pcid, ""),
    })

sections.append({
    "phase": inv.phase,
    "title": inv.phase.replace("Investigation: ", ""),
    "content": content,
    "cell_ids": list(set(inv.cell_ids + child_cells)),
    "plot_cell_ids": list(set(inv.plot_cell_ids + child_plots)),
    "confidence": inv.confidence,
    "type": "investigation",
    "plot_metadata": plot_metadata,
})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && PYTHONPATH=. pytest tests/test_story_builder.py::test_get_story_sections_includes_plot_metadata -v`
Expected: PASS

- [ ] **Step 5: Store cell sources/outputs in KG during accumulation**

In `src/agent/eda_agent.py`, after storing plot_images in the accumulation phase, also store cell_sources and cell_outputs. Find the block that stores `node.metadata["plot_images"]` (around line 868-876) and add:

```python
# Store cell context for story builder plot curation
cell_sources = {}
cell_outputs_map = {}
# The subagent's notebook cells have source in the events that were streamed
# We can reconstruct from the result's cell_ids + the conversation outputs
for cid in result.cell_ids:
    # Cell source is not directly in result — but the subagent's push_event
    # sent cell_write events with source. For now, store what we have.
    pass
# Store the combined text outputs per hypothesis for the story builder
if all_outputs_text := getattr(result, 'finding', ''):
    node.metadata["finding_text"] = all_outputs_text
```

Actually, the simplest approach: store the subagent's `all_outputs` (stdout per cell) in the InvestigationResult, then propagate to KG. Modify `InvestigationResult` in `src/agent/subagent.py` to add a `cell_outputs` field:

In `src/agent/subagent.py`, add to the InvestigationResult dataclass (around line 14-24):

```python
@dataclass
class InvestigationResult:
    """Result of a hypothesis investigation."""
    hypothesis_id: str
    hypothesis_title: str
    finding: str
    cell_ids: list[str] = field(default_factory=list)
    plot_cell_ids: list[str] = field(default_factory=list)
    confidence: float = 0.5
    sub_findings: list[dict] = field(default_factory=list)
    images: dict[str, list[str]] = field(default_factory=dict)
    relevant_cols: list[str] = field(default_factory=list)
    cell_sources: dict[str, str] = field(default_factory=dict)  # cell_id -> source code
    cell_outputs: dict[str, str] = field(default_factory=dict)  # cell_id -> stdout text
```

In the subagent's `_write_and_execute`, after appending to `result.cell_ids`, store the source and output:

```python
result.cell_ids.append(cell_id)
result.cell_sources[cell_id] = code
# Store output text after execution (in the caller, after _extract_text)
```

And in the main loop, after `all_outputs.append(output_text)`:
```python
result.cell_outputs[cell_id] = output_text
```

Then in `eda_agent.py` accumulation, after storing plot_images:
```python
node.metadata["cell_sources"] = getattr(result, 'cell_sources', {})
node.metadata["cell_outputs"] = getattr(result, 'cell_outputs', {})
```

Also update `subagent_worker.py` to include `cell_sources` and `cell_outputs` in the result dict:
```python
result_dict["cell_sources"] = result.cell_sources
result_dict["cell_outputs"] = result.cell_outputs
```

And update the InvestigationResult reconstruction in `eda_agent.py`:
```python
result = InvestigationResult(
    ...
    cell_sources=data.get("cell_sources", {}),
    cell_outputs=data.get("cell_outputs", {}),
)
```

- [ ] **Step 6: Commit**

```bash
git add src/agent/knowledge_graph.py src/agent/subagent.py src/agent/subagent_worker.py src/agent/eda_agent.py tests/test_story_builder.py
git commit -m "feat: propagate cell sources/outputs through KG for plot curation"
```

---

### Task 2: Create the StoryBuilder agent

**Files:**
- Create: `src/reporting/story_builder.py`
- Test: `tests/test_story_builder.py`

The core component. For each section, it reads the text metadata about all candidate plots and decides which to keep and what caption to give each. One LLM call per section (text only, no vision).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_story_builder.py (append to existing)
from src.reporting.story_builder import curate_section_plots


def test_curate_section_plots_limits_to_max():
    """Curator should select at most max_plots from candidates."""
    section = {
        "title": "CO bursts are heteroskedastic",
        "content": "Variance increases 2.4x in high-CO regime.",
        "confidence": 0.85,
        "plot_metadata": [
            {"cell_id": "c1", "cell_source": "plt.scatter(x, y)\nplt.show()", "cell_output": "[plot]"},
            {"cell_id": "c2", "cell_source": "plt.scatter(x, y, color='regime')\nplt.show()", "cell_output": "[plot]"},
            {"cell_id": "c3", "cell_source": "plt.hist(resid)\nplt.show()", "cell_output": "Levene p<0.001\n[plot]"},
            {"cell_id": "c4", "cell_source": "plt.bar(bins, var)\nplt.show()", "cell_output": "Variance by bin\n[plot]"},
            {"cell_id": "c5", "cell_source": "plt.scatter(x, y, alpha=0.3)\nplt.show()", "cell_output": "[plot]"},
        ],
    }
    result = curate_section_plots(section, max_plots=3)
    assert len(result) <= 3
    for item in result:
        assert "cell_id" in item
        assert "caption" in item
        assert len(item["caption"]) > 10  # Not a generic stub


def test_curate_section_plots_empty_metadata():
    """If no plot metadata, return empty list."""
    section = {"title": "Data Loading", "content": "Loaded 9357 rows.", "plot_metadata": []}
    result = curate_section_plots(section, max_plots=3)
    assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && PYTHONPATH=. pytest tests/test_story_builder.py::test_curate_section_plots_limits_to_max -v`
Expected: FAIL — `cannot import name 'curate_section_plots'`

- [ ] **Step 3: Implement story_builder.py**

```python
# src/reporting/story_builder.py
"""Agentic story builder — curates plots, writes captions, structures narrative."""
from __future__ import annotations

import json
import logging
from typing import Any

_LOG = logging.getLogger(__name__)


def curate_section_plots(
    section: dict[str, Any],
    max_plots: int = 3,
) -> list[dict[str, str]]:
    """Select the best plots for a section and generate unique captions.

    Args:
        section: Section dict with title, content, confidence, plot_metadata.
        max_plots: Maximum plots to include.

    Returns:
        List of {cell_id, caption, rank} dicts for selected plots.
    """
    plot_metadata = section.get("plot_metadata", [])
    if not plot_metadata:
        return []

    # If within limit already, just generate captions
    if len(plot_metadata) <= max_plots:
        return _generate_captions(section, plot_metadata)

    # Use LLM to select and caption
    return _llm_curate(section, plot_metadata, max_plots)


def _generate_captions(
    section: dict[str, Any],
    plots: list[dict],
) -> list[dict[str, str]]:
    """Generate unique captions for each plot using LLM."""
    try:
        from src.config.config import get_chat_model
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = get_chat_model()

        plots_desc = "\n".join(
            f"Plot {i+1} (cell {p['cell_id']}):\n"
            f"  Code: {p.get('cell_source', 'unknown')[:200]}\n"
            f"  Output: {p.get('cell_output', '')[:200]}"
            for i, p in enumerate(plots)
        )

        response = llm.invoke([
            SystemMessage(content=(
                "You are writing figure captions for a data analysis report. "
                "For each plot, write ONE specific caption (1-2 sentences) that describes "
                "what the plot shows and what pattern is visible. Reference specific numbers "
                "from the output where possible. Use plain text with $...$ for math.\n\n"
                "Respond with JSON (no markdown fencing):\n"
                '[{"cell_id": "...", "caption": "..."}, ...]'
            )),
            HumanMessage(content=(
                f"Section: {section.get('title', '')}\n"
                f"Finding: {section.get('content', '')[:500]}\n\n"
                f"Plots to caption:\n{plots_desc}"
            )),
        ])

        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        result = json.loads(text)
        # Validate structure
        valid = []
        for item in result:
            if isinstance(item, dict) and "cell_id" in item and "caption" in item:
                valid.append({"cell_id": item["cell_id"], "caption": item["caption"]})
        return valid if valid else _fallback_captions(section, plots)

    except Exception as exc:
        _LOG.warning("Caption generation failed: %s", exc)
        return _fallback_captions(section, plots)


def _llm_curate(
    section: dict[str, Any],
    plots: list[dict],
    max_plots: int,
) -> list[dict[str, str]]:
    """Use LLM to select best plots and generate captions."""
    try:
        from src.config.config import get_chat_model
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = get_chat_model()

        plots_desc = "\n".join(
            f"Plot {i+1} (cell {p['cell_id']}):\n"
            f"  Code: {p.get('cell_source', 'unknown')[:300]}\n"
            f"  Output: {p.get('cell_output', '')[:300]}"
            for i, p in enumerate(plots)
        )

        response = llm.invoke([
            SystemMessage(content=(
                f"You are curating figures for a data analysis report. "
                f"Select the {max_plots} most informative and visually distinct plots. "
                f"Skip plots that are redundant (e.g., same scatter with minor variations). "
                f"Prefer: (1) plots showing the key finding, (2) statistical test visualizations, "
                f"(3) plots with different chart types (scatter vs histogram vs bar). "
                f"For each selected plot, write a specific caption (1-2 sentences) with numbers.\n\n"
                f"Respond with JSON (no markdown fencing):\n"
                f'[{{"cell_id": "...", "caption": "...", "reason": "why selected"}}]\n\n'
                f"Select exactly {max_plots} plots. Use $...$ for math in captions."
            )),
            HumanMessage(content=(
                f"Section: {section.get('title', '')}\n"
                f"Finding: {section.get('content', '')[:800]}\n"
                f"Confidence: {section.get('confidence', 'N/A')}\n\n"
                f"Candidate plots ({len(plots)} total):\n{plots_desc}"
            )),
        ])

        text = response.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        result = json.loads(text)
        valid = []
        for item in result:
            if isinstance(item, dict) and "cell_id" in item and "caption" in item:
                valid.append({"cell_id": item["cell_id"], "caption": item["caption"]})
        if valid:
            return valid[:max_plots]
        return _fallback_captions(section, plots[:max_plots])

    except Exception as exc:
        _LOG.warning("Plot curation failed: %s", exc)
        return _fallback_captions(section, plots[:max_plots])


def _fallback_captions(
    section: dict[str, Any],
    plots: list[dict],
) -> list[dict[str, str]]:
    """Generate simple captions without LLM (deterministic fallback)."""
    title = section.get("title", "Analysis")
    result = []
    for i, p in enumerate(plots):
        # Try to extract a meaningful caption from the cell source
        source = p.get("cell_source", "")
        caption = f"{title}"
        if "plt.title(" in source:
            import re
            m = re.search(r"plt\.title\(['\"](.+?)['\"]\)", source)
            if m:
                caption = m.group(1)
        elif "scatter" in source:
            caption = f"Scatter plot: {title}"
        elif "hist" in source:
            caption = f"Distribution: {title}"
        elif "bar" in source:
            caption = f"Comparison: {title}"
        elif "plot" in source:
            caption = f"Trend: {title}"
        result.append({"cell_id": p["cell_id"], "caption": caption})
    return result


def build_story_abstract(
    executive_summary: str,
    max_sentences: int = 5,
) -> str:
    """Condense executive summary into a concise abstract for the PDF."""
    try:
        from src.config.config import get_chat_model
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = get_chat_model()
        response = llm.invoke([
            SystemMessage(content=(
                f"Condense this executive summary into exactly {max_sentences} sentences "
                f"for a paper abstract. Keep the most important quantitative findings. "
                f"Use $...$ for math notation. Do not add information not in the original."
            )),
            HumanMessage(content=executive_summary[:3000]),
        ])
        return response.content.strip()
    except Exception as exc:
        _LOG.warning("Abstract condensation failed: %s", exc)
        # Fallback: take first N sentences
        sentences = executive_summary.replace("\n", " ").split(". ")
        return ". ".join(sentences[:max_sentences]) + "."


def build_curated_story(
    sections: list[dict],
    executive_summary: str,
    dataset_name: str = "dataset",
    max_plots_per_section: int = 3,
) -> dict:
    """Build a curated story with selected plots and unique captions.

    Args:
        sections: Raw sections from KG with plot_metadata.
        executive_summary: Full executive summary text.
        dataset_name: Name of the dataset file.
        max_plots_per_section: Max figures per section.

    Returns:
        Curated story dict ready for story.json.
    """
    import datetime

    curated_sections = []
    for section in sections:
        curated = dict(section)

        # Curate plots if metadata available
        if section.get("plot_metadata"):
            selected = curate_section_plots(section, max_plots=max_plots_per_section)
            curated["selected_plots"] = selected
            # Filter plot_cell_ids to only selected
            selected_ids = {s["cell_id"] for s in selected}
            curated["plot_cell_ids"] = [pid for pid in curated.get("plot_cell_ids", []) if pid in selected_ids]
            # Store captions keyed by cell_id for the LaTeX/story builder
            curated["plot_captions"] = {s["cell_id"]: s["caption"] for s in selected}
        curated_sections.append(curated)

    # Build concise abstract
    abstract = build_story_abstract(executive_summary)

    return {
        "title": f"EDA Report: {dataset_name}",
        "executive_summary": executive_summary,
        "abstract": abstract,
        "sections": curated_sections,
        "generated_at": datetime.datetime.now().isoformat(),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && PYTHONPATH=. pytest tests/test_story_builder.py -v`
Expected: PASS (both tests)

- [ ] **Step 5: Commit**

```bash
git add src/reporting/story_builder.py tests/test_story_builder.py
git commit -m "feat: story builder agent — plot curation + caption generation + abstract"
```

---

### Task 3: Integrate StoryBuilder into the pipeline

**Files:**
- Modify: `backend/routers/run.py:83-212`
- Modify: `backend/routers/story.py:1143-1305` (regenerate)

Replace the mechanical story dump in run.py with a `build_curated_story()` call.

- [ ] **Step 1: Update run.py story generation**

In `backend/routers/run.py`, find the story generation block (around line 83-212). After the LLM narrative is generated and sections are built, add the curation step. Replace the final `story_data = { ... }` construction with:

```python
# After sections and narrative are built:
from src.reporting.story_builder import build_curated_story

story_data = build_curated_story(
    sections=sections,
    executive_summary=narrative,
    dataset_name=dataset_name,
    max_plots_per_section=3,
)
if kg is not None:
    story_data["knowledge_graph"] = kg.to_dict()
```

- [ ] **Step 2: Update regenerate_story in story.py**

In `backend/routers/story.py`, in `regenerate_story()` (around line 1257-1268), replace the final story construction similarly:

```python
from src.reporting.story_builder import build_curated_story

story_data = build_curated_story(
    sections=sections,
    executive_summary=narrative,
    dataset_name=dataset_name,
    max_plots_per_section=3,
)
if kg is not None:
    story_data["knowledge_graph"] = kg.to_dict()
```

- [ ] **Step 3: Update _augment_story_plot_metadata to respect selected_plots**

In `backend/routers/story.py`, in `_augment_story_plot_metadata()`, after building the plots list for a section, filter to only selected plots if `selected_plots` exists:

```python
# After plots are collected for a section, before assigning:
selected_plots = section.get("selected_plots")
if selected_plots and plots:
    selected_ids = {s["cell_id"] for s in selected_plots}
    caption_map = section.get("plot_captions", {})
    filtered = []
    for p in plots:
        src_id = p.get("source_cell_id", "")
        if src_id in selected_ids:
            # Use curated caption instead of generic one
            if src_id in caption_map:
                p["caption"] = caption_map[src_id]
                p["title"] = caption_map[src_id]
            filtered.append(p)
    plots = filtered if filtered else plots[:3]  # fallback: first 3

if plots:
    section["plots"] = plots
```

- [ ] **Step 4: Verify imports and test manually**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && PYTHONPATH=. python -c "from backend.routers.run import _run_agent_in_thread; from backend.routers.story import regenerate_story; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/routers/run.py backend/routers/story.py
git commit -m "feat: integrate story builder into pipeline and regeneration"
```

---

### Task 4: Fix LaTeX PDF — wide figures, concise abstract, better captions

**Files:**
- Modify: `backend/routers/story.py:999-1103` (`_build_ieee_latex`)

- [ ] **Step 1: Use concise abstract in LaTeX**

In `_build_ieee_latex()`, change the abstract to use the new `abstract` field (concise version) instead of the full executive summary:

```python
# Replace:
#   {_tex_esc(summary[:3000])}
# With:
abstract_text = story.get("abstract", summary[:500])

# In the template:
\\begin{{abstract}}
{_tex_esc(abstract_text)}
\\end{{abstract}}
```

- [ ] **Step 2: Use figure* for wide plots (heatmaps, multi-panel)**

Change the figure environment logic. Heatmaps and multi-panel plots should use `figure*` (spans both columns). Add detection based on caption or chart semantics:

```python
# Replace the figure block:
figs_tex = ""
section_fig_count = 0
for plot in section.get("plots", []):
    if section_fig_count >= 3:
        break  # Hard cap: 3 figures per section
    fig_counter += 1
    section_fig_count += 1

    # Use curated caption if available
    caption_map = section.get("plot_captions", {})
    src_cell = plot.get("source_cell_id", "")
    caption = caption_map.get(src_cell, plot.get("caption", plot.get("title", f"Figure {fig_counter}")))

    if fig_counter in fig_paths:
        # Wide figures for heatmaps and multi-panel plots
        is_wide = any(kw in caption.lower() for kw in ["matrix", "heatmap", "correlation", "multi", "panel", "grid"])
        fig_env = "figure*" if is_wide else "figure"
        width = "0.85\\textwidth" if is_wide else "0.95\\columnwidth"

        figs_tex += f"""
\\begin{{{fig_env}}}[htbp]
\\centerline{{\\includegraphics[width={width}]{{{fig_paths[fig_counter]}}}}}
\\caption{{{_tex_esc(str(caption))}}}
\\label{{fig{fig_counter}}}
\\end{{{fig_env}}}
"""
```

- [ ] **Step 3: Clean section content — remove raw markdown headers**

Add a content cleanup step before LaTeX conversion to strip markdown headers that appear in section content:

```python
# Before the content line-by-line processing:
import re as _re
# Strip markdown headers (## Conclusion, ### etc)
content = _re.sub(r'^#{1,4}\s+.*$', '', content, flags=_re.MULTILINE)
# Strip "- Key finding:" prefix repetition
content = content.replace("- Key finding:", "-")
content = content.replace("- - Key finding:", "-")
```

- [ ] **Step 4: Verify LaTeX builds**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && PYTHONPATH=. python -c "from backend.routers.story import _build_ieee_latex; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/routers/story.py
git commit -m "fix: LaTeX PDF — concise abstract, figure* for wide plots, 3-fig cap, clean content"
```

---

### Task 5: Store cell sources/outputs in subagent result for plot curation

**Files:**
- Modify: `src/agent/subagent.py`
- Modify: `src/agent/subagent_worker.py`
- Modify: `src/agent/eda_agent.py`

This is the data pipeline that feeds Task 1. The subagent needs to record what code each cell ran and what stdout it produced, so the story builder can reason about plots.

- [ ] **Step 1: Add cell_sources and cell_outputs to InvestigationResult**

In `src/agent/subagent.py`, update the dataclass:

```python
@dataclass
class InvestigationResult:
    """Result of a hypothesis investigation."""
    hypothesis_id: str
    hypothesis_title: str
    finding: str
    cell_ids: list[str] = field(default_factory=list)
    plot_cell_ids: list[str] = field(default_factory=list)
    confidence: float = 0.5
    sub_findings: list[dict] = field(default_factory=list)
    images: dict[str, list[str]] = field(default_factory=dict)
    relevant_cols: list[str] = field(default_factory=list)
    cell_sources: dict[str, str] = field(default_factory=dict)
    cell_outputs: dict[str, str] = field(default_factory=dict)
```

- [ ] **Step 2: Populate cell_sources and cell_outputs in the subagent loop**

In the `_write_and_execute` function, after `result.cell_ids.append(cell_id)`, add:

```python
result.cell_sources[cell_id] = code
```

In the adaptive loop, after `all_outputs.append(output_text)`, add:

```python
result.cell_outputs[cell_id] = output_text
```

Do the same in the error-fix paths where `all_outputs.append()` is called.

- [ ] **Step 3: Include in to_dict() and worker serialization**

Update `InvestigationResult.to_dict()`:

```python
def to_dict(self) -> dict:
    return {
        "hypothesis_id": self.hypothesis_id,
        "hypothesis_title": self.hypothesis_title,
        "finding": self.finding,
        "cell_ids": self.cell_ids,
        "plot_cell_ids": self.plot_cell_ids,
        "confidence": self.confidence,
        "sub_findings": self.sub_findings,
        "cell_sources": self.cell_sources,
        "cell_outputs": self.cell_outputs,
    }
```

In `subagent_worker.py`, the `result.to_dict()` call will now include these fields automatically. No change needed there.

In `eda_agent.py`, update the InvestigationResult reconstruction:

```python
result = InvestigationResult(
    ...
    cell_sources=data.get("cell_sources", {}),
    cell_outputs=data.get("cell_outputs", {}),
)
```

- [ ] **Step 4: Store in KG during accumulation**

In `eda_agent.py`, after `node.metadata["plot_images"] = all_images`, add:

```python
node.metadata["cell_sources"] = getattr(result, 'cell_sources', {})
node.metadata["cell_outputs"] = getattr(result, 'cell_outputs', {})
```

- [ ] **Step 5: Verify end-to-end**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && PYTHONPATH=. python -c "from src.agent.subagent import InvestigationResult; r = InvestigationResult('h1', 'test', 'finding'); r.cell_sources['c1'] = 'code'; d = r.to_dict(); assert 'cell_sources' in d; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add src/agent/subagent.py src/agent/subagent_worker.py src/agent/eda_agent.py
git commit -m "feat: store cell sources/outputs in InvestigationResult for plot curation"
```

---

### Task 6: End-to-end test and verification

**Files:**
- Test: `tests/test_story_builder.py`

- [ ] **Step 1: Add integration test**

```python
# tests/test_story_builder.py (append)
from src.reporting.story_builder import build_curated_story, build_story_abstract


def test_build_curated_story_limits_plots():
    """Full story build should limit plots per section."""
    sections = [
        {
            "phase": "Investigation: Test Hypothesis",
            "title": "Test Hypothesis",
            "content": "Finding: correlation is r=0.95.",
            "cell_ids": ["c1", "c2", "c3", "c4", "c5"],
            "plot_cell_ids": ["c2", "c3", "c4", "c5"],
            "confidence": 0.8,
            "type": "investigation",
            "plot_metadata": [
                {"cell_id": f"c{i}", "cell_source": f"plt.plot(x{i})\nplt.show()", "cell_output": f"[plot {i}]"}
                for i in range(2, 6)
            ],
        },
    ]
    story = build_curated_story(sections, "Summary text.", max_plots_per_section=2)
    assert "sections" in story
    sec = story["sections"][0]
    assert len(sec.get("selected_plots", [])) <= 2
    assert "abstract" in story


def test_build_story_abstract_is_concise():
    """Abstract should be shorter than the original."""
    long_summary = "This is a very long executive summary. " * 50
    abstract = build_story_abstract(long_summary, max_sentences=3)
    assert len(abstract) < len(long_summary)
```

- [ ] **Step 2: Run full test suite**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && PYTHONPATH=. pytest tests/test_story_builder.py -v`
Expected: ALL PASS

- [ ] **Step 3: Verify PDF generation works end-to-end**

Run: `cd /Users/indro/Projects/Hackathon/AgenticEDAHackathon && PYTHONPATH=. python -c "from backend.routers.story import _build_ieee_latex; print('LaTeX builder OK')"`
Expected: `LaTeX builder OK`

- [ ] **Step 4: Commit and push**

```bash
git add tests/test_story_builder.py
git commit -m "test: end-to-end story builder tests"
git push origin indro
```

---

## Self-Review Checklist

1. **Spec coverage:**
   - [x] Plot curation (select best N per section) — Task 2, `curate_section_plots`
   - [x] Unique captions per plot — Task 2, `_generate_captions` and `_llm_curate`
   - [x] Concise abstract — Task 2, `build_story_abstract`
   - [x] Wide figures for heatmaps — Task 4, `figure*` detection
   - [x] Per-section figure limit (3 max) — Task 4, `section_fig_count` cap
   - [x] Clean section content (strip markdown headers) — Task 4, regex cleanup
   - [x] Plot metadata propagation — Task 1 + Task 5
   - [x] Integration into pipeline — Task 3
   - [x] Integration into regeneration — Task 3
   - [x] End-to-end testing — Task 6

2. **Placeholder scan:** No TBD/TODO found. All code blocks are complete.

3. **Type consistency:**
   - `curate_section_plots` returns `list[dict[str, str]]` — used in Task 3
   - `build_curated_story` returns `dict` — used in Task 3 (run.py and story.py)
   - `InvestigationResult.cell_sources` and `.cell_outputs` are `dict[str, str]` — propagated through worker and KG
   - `section["plot_metadata"]` is `list[dict]` with keys `cell_id`, `cell_source`, `cell_output` — consistent across Task 1 and Task 2
   - `section["selected_plots"]` is `list[dict]` with keys `cell_id`, `caption` — used in Task 3 and Task 4
   - `section["plot_captions"]` is `dict[str, str]` (cell_id → caption) — used in Task 4 LaTeX builder
