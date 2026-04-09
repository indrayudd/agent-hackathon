# Plan 9: Sidebar Agents, Per-Notebook Traces, Tab Performance, IEEE PDF Export, Regenerate

## Features

### F1: Sidebar INVESTIGATIONS → "Agents" section matching tab bar
- Rename "INVESTIGATIONS" to "AGENTS" in sidebar
- Show "Main" + "Agent 1", "Agent 2" etc. matching the tab bar IDs
- Clicking opens the relevant notebook tab (not scroll to cell)

### F2: Full Jupyter notebook functionality
- All notebooks (main + agent) should support: run cell, add cell, edit cell, delete cell, reorder
- Agent notebooks should be interactive post-completion (user can add/edit cells)

### F3: Per-notebook activity traces
- Agent Actions panel shows trace for the ACTIVE notebook tab
- Main tab: shows orchestrator trace (spawn agent, loop events, conclusions)
- Agent tabs: shows that agent's cells, thinking, errors
- Full timeline groups by notebook with expandable sections per agent
- "EDA complete" shown only once, not per-parallel-agent
- Clear loop demarcation in timeline

### F4: Tab switching performance
- Investigate current approach (already using CSS display:none — good)
- Add lazy rendering for inactive notebook cell content (only render visible cells)
- Memoize heavy story components

### F5: IEEE-style PDF export
- Click "Export PDF" → spinner → background processing → download
- Generate LaTeX-style IEEE two-column report with:
  - Title, authors, abstract (executive summary)
  - Sections from KG/story
  - Figures with captions and references
  - Conclusions
- Render via WeasyPrint with IEEE CSS stylesheet
- Disable button with spinner until ready

### F6: Markdown export
- Same content as PDF but as clean markdown
- Include image references as data URIs or file paths

### F7: Regenerate button (replaces Refresh)
- Rename "Refresh" → "Regenerate"
- On click: re-read all notebooks (main + agent), extract new insights, update KG, regenerate story
- Picks up manual cell edits and chat-driven changes

## Implementation Order

1. F1 (sidebar) + F3 (per-notebook traces) — tightly coupled, do together
2. F7 (regenerate) — small backend change
3. F4 (tab performance) — frontend optimization
4. F5+F6 (PDF/Markdown export) — biggest piece, backend + frontend
5. F2 (full notebook features) — verify existing, patch gaps
