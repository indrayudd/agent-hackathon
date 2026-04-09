# Cleanup 8 — Frontend Polish & Story Overhaul

## 1. Chat → Agent Actions: Move error/fix messages out of chat
- [x] In `useAgentStream.ts`, stop pushing "Error: ...", "Attempting fix...", "Backtracking: ..." messages to `chatStore`. Instead, route them exclusively to `notebookStore.setAgentActivity()` so they appear in the Agent Actions timeline on the left sidebar.
- [x] Keep only genuine conversational messages in chat (user questions, agent answers, "EDA complete" final message).
- [ ] In `AgentActivityBadge.tsx`, ensure error/fix/backtrack entries render with clear red/amber styling and appropriate icons (`error`, `build`, `replay`).

## 2. Failed cells: overwrite instead of accumulate
- [x] In `notebookStore.ts`, added `overwriteCell(id, source)` action that replaces cell source and clears outputs/error. Added `fixedCellIds` Set for tracking recently-fixed cells.
- [x] Intermediary markdown cells like "Attempting fix..." or "Backtracking..." are now filtered out in `appendCell` — they belong in Agent Actions only.
- [x] If a cell is overwritten after a fix, a green "Fixed" badge appears and fades after 2 seconds (CSS `animate-fade-out`).

## 3. Auto-scroll: ensure the very bottom is visible
- [x] In `NotebookPane.tsx`, `bottomRef` moved outside `max-w-4xl` container with `h-32` spacer div. Uses `block: "end"` scroll.
- [x] Added `scroll-padding-bottom: 8rem` to the scroll container.
- [x] Auto-scroll now triggers on `latestThinking` changes too, with smart detection (only scrolls if user is near bottom within 200px).

## 4. Story Mode: Executive Summary as structured insights, not wall of text
- [x] In `StoryPane.tsx`, executive summary now parsed into bullet-point insight cards in a 2-column grid, with auto-generated Material Symbol icons based on keywords.
- [x] Story sections flow as coherent narrative with inline visualizations.
- [ ] Backend story generator prompt could be updated to return structured bullet points (currently frontend parses prose into bullets).

## 5. Story Mode: Interactive visualizations with Plotly
- [x] Installed `react-plotly.js` and `plotly.js-dist-min` in the frontend.
- [x] Created `InteractivePlot.tsx` component with dynamic import, transparent backgrounds, responsive config.
- [x] `CellOutput.tsx` detects `application/vnd.plotly.v1+json` MIME type and renders interactive Plotly charts (priority over PNG).
- [x] `StoryPane.tsx` prefers Plotly JSON data over static PNGs when rendering section plots.
- [ ] Backend EDA agent: emit `application/vnd.plotly.v1+json` output alongside `image/png` for each visualization cell.
- [ ] Backend story endpoint: optionally produce summary Plotly specs for story-specific plots.
- [x] Added TypeScript type declarations for plotly modules (`src/types/plotly.d.ts`).
