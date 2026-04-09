# Plan 11: Citations, Autonomous Loops, Chat Investigations, Regen Detection, Scroll Fix

## F1: Cell Citations in Story
Story sections already have `cell_ids`. Render them as clickable "[Cell N]" links that switch to notebook tab and scroll to the cell. Add to story section cards where findings reference specific cells.

## F2: Autonomous Loop Count with Reasoning Modes
Replace fixed `max_loops` with a reasoning mode selector:
- **Quick (1 loop)**: Fast pass, minimal investigation
- **Standard (2 loops)**: Default, moderate depth
- **Deep (up to 5 loops)**: Agent decides when to stop via convergence check

Convergence check: if loop N produced no new findings with confidence > 0.5 that loop N-1 didn't already have, stop.

## F3: Chat Investigation with Streaming Animation
When chat triggers an investigation, show the same step-by-step notebook animation as the main agent. The subagent already pushes cell_write/cell_output events. Fix: route these to a dedicated notebook tab ("Chat Investigation") and show the process live. Main agent can optionally spawn subagents if the question is complex enough.

## F4: Regenerate Button "Changes Detected" Annotation
Track when notebook cells change after story was generated. Show green border + "Changes detected!" text on the Regenerate button. Clear when regeneration completes.

## F5: Scroll Position Persistence on Refresh
Save scroll positions to sessionStorage (not just in-memory ref). On page load, restore from sessionStorage. No scroll-to-top animation.

## Implementation Order
1. F5 (scroll fix) — smallest, most annoying bug
2. F4 (regen detection) — small frontend state
3. F1 (citations) — frontend story rendering
4. F2 (autonomous loops) — backend + frontend config
5. F3 (chat streaming) — most complex
