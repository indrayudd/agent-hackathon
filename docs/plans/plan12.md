# Plan 12: True Agentic Ingestion + Regeneration Fix + Chat→KG Pipeline

## Problem Statement

The system has critical information loss at every boundary. Subagents are blind executors, the main agent sees summaries not raw data, chat investigations don't feed back to the KG, and story regeneration produces broken output.

## Fixes Required

### F1: Fix Story Regeneration (CRITICAL — currently produces broken output)
The regenerate endpoint (`/story/{session_id}/regenerate` in story.py) re-reads the notebook but produces a malformed story. It needs to:
- Re-read the existing KG from story.json
- Re-read ALL notebooks (main + agent)
- Rebuild sections properly with plot artifacts
- Generate new executive summary via LLM
- Preserve investigation sections from the KG

### F2: Subagent Adaptive Execution (see own outputs, act on them)
Currently subagents plan all cells upfront and execute blind. Change to:
- Plan 2 cells initially
- After executing each cell, feed the output back to the LLM
- LLM decides what to do next (up to max_cells)
- Each cell builds on what the previous cell found
- Subagent sees ALL its own outputs (text + images) between cells
- This makes subagents truly agentic, not just script runners

### F3: Main Agent Sees ALL Subagent Plots (no 3-image limit)
Currently `images[:2]` or `images[:3]` caps vision analysis. Remove limits:
- Main agent vision-analyzes every plot from every subagent
- Update thinking line: "Analyzing plot {n}/{total} from {hypothesis}..."
- Each vision analysis result stored as a visual_insight node in KG

### F4: Chat Investigation → KG Pipeline
Chat investigations currently update story.json but NOT the in-memory KG. Fix:
- After chat subagent completes, add result to `_session_kgs[session_id]`
- Create conclusion + evidence nodes
- Store plot images in KG metadata
- This means subsequent chat questions benefit from prior chat investigations

### F5: Chat Investigation Flow Through Main Notebook
When user asks for investigation in chat:
1. Write "Investigating: {question}" cell in main notebook
2. Spawn subagent in dedicated tab
3. After subagent completes, write compilation cell in main notebook with finding + confidence
4. Add to KG
This creates a traceable audit trail in the main notebook.

### F6: Subagent↔Main Agent Context Bridge
Pass the main agent's KG context summary to subagents so they know what's already been discovered:
- Subagent prompt includes: "Previous findings: {kg_context}"
- Subagent can reference prior findings in its analysis
- This enables cross-investigation awareness without spawning sub-subagents

### F7: Change Detection Robustness
Current detection is fragile (cell count based, triggers on stream replay). Fix:
- Track a content hash (hash of all cell sources) instead of just count
- Only compare after pipeline is fully complete (not during streaming)
- Clear flag properly on regeneration

## Implementation Order

1. F1 (regeneration fix) — critical, broken right now
2. F7 (change detection) — quick robustness fix
3. F4 (chat→KG) — important for information flow
4. F5 (chat through main notebook) — audit trail
5. F3 (remove image limits) — simple cap removal
6. F6 (context bridge) — subagent prompt enhancement
7. F2 (adaptive subagent) — biggest refactor, most impactful
