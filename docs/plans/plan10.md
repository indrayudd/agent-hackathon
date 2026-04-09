# Plan 10: Iron-Clad Agent Logic — Vision Loop, Confidence Scoring, KG Activation, Error Transparency

## Overview

Fix every information loss point, activate dead KG features, implement real confidence scoring, make the vision loop actually work, and add proper error logging throughout.

## Fixes

### F1: Subagent Conclusion LLM Gets Plot Images (NOT just text)
**Problem:** `_extract_text()` replaces images with `[plot generated]`. The conclusion synthesis LLM never sees the actual charts.
**Fix:** Pass images to the conclusion LLM as vision content (same pattern as `interpret_output`).
- In `subagent.py`, collect images during execution
- In the conclusion synthesis call, pass images as multimodal content alongside text

### F2: Real Confidence Scoring
**Problem:** `confidence = 0.3 + 0.15 * len(outputs)` is meaningless.
**Fix:** Implement composite confidence based on:
- Statistical test presence (p-value) — 35%
- Sample size adequacy — 25%
- Evidence convergence (# independent lines) — 20%
- Visual confirmation — 10%
- Multi-method confirmation — 10%

Extract p-values from subagent text outputs via regex. Count evidence lines from sub_findings. Track visual confirmation from vision analysis.

### F3: Vision Analysis with Structured Prompts + Logging
**Problem:** Vision analysis silently fails, no logging, generic prompts.
**Fix:**
- Structured JSON prompt asking: "does visual support finding?", "anomalies?", "confidence?"
- Log every vision call (success/failure/skipped)
- Update thinking line: "Analyzing plot from {hypothesis}..."
- Store visual_confidence from LLM response in KG node

### F4: Activate Dead KG Methods
**Problem:** `reinforce()`, `supersede()`, `loop_number` queries never called.
**Fix:**
- Call `reinforce()` when a later finding supports an earlier one (same columns)
- Call `supersede()` when loop 2 refines a loop 1 finding on same hypothesis
- Use `loop_number` in story section grouping
- Wire `get_context_for_chat()` into the chat agent's LLM prompt

### F5: Replace All Silent Exception Swallows with Logging
**Problem:** 5+ `except: pass` blocks hide real errors.
**Fix:** Replace every bare `except: pass` with `except Exception as exc: _LOG.warning(...)`.

### F6: Subagent Adaptive Execution (See Own Outputs)
**Problem:** Subagent plans all cells upfront, executes blind.
**Fix:** After each cell execution, append the output summary to a running context. The next cell's error recovery (if needed) gets this context. The conclusion synthesis gets the full chain.

### F7: KG Persistence Across Server Restarts
**Problem:** KG is in-memory only (`_session_kgs` dict).
**Fix:** On chat endpoint access, if KG not in memory, load from `story.json`.

### F8: Executive Summary Gets KG Context
**Problem:** Summary LLM gets flat text, no graph structure.
**Fix:** Include `kg.get_context_for_hypothesis_generation()` in the executive summary prompt.

## Implementation Order (with TODO checkboxes)

### Wave 1: Core Logic Fixes
- [ ] F2: Confidence scoring function in `knowledge_graph.py`
- [ ] F1: Subagent conclusion sees images
- [ ] F3: Structured vision analysis with logging
- [ ] F5: Replace all silent exception swallows

### Wave 2: KG Activation
- [ ] F4: Wire reinforce/supersede/context_for_chat
- [ ] F7: KG persistence from story.json
- [ ] F8: Executive summary KG context

### Wave 3: Subagent Intelligence
- [ ] F6: Adaptive execution with running context
