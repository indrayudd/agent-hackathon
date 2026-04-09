# Cleanup 9

This pass fixes the remaining frontend regressions and report UX issues found in live use.

## Goals

1. Simplify the Agent Actions pane.
2. Add a modal / expanded view for the full action timeline.
3. Remove noisy hypothesis-progress messaging from the chat sidebar.
4. Make story chapters read like a continuous statistical report instead of tiled cards.
5. Make key takeaways concise and point-based.
6. Link story sections to the relevant notebook plots.
7. Render LaTeX properly in story/report text.
8. Fix the notebook error-repair lifecycle so failed cells are visibly replaced rather than left behind.
9. Make investigation items in the left rail clickable and scroll the notebook to the relevant hypothesis section.
10. Preserve bottom-follow autoscroll through plot rendering and output growth.

## Workstreams

### 1. Story UX / content structure

- Reduce metadata clutter like `Chapter N`, `3 visuals`, etc.
- Replace chapter tiles with a more article-like continuous layout.
- Keep takeaway cards, but shorten and bullet them.
- Inline visuals into the narrative with clearer plot anchoring.
- Support LaTeX rendering in the story view.

### 2. Agent Actions UX

- Replace the current dense card stack with a minimal timeline summary.
- Add an explicit affordance to open the full action log in a modal.
- Keep click-through to notebook cells from the expanded timeline.

### 3. Chat cleanup

- Remove unnecessary hypothesis-progress chatter from the chat sidebar.
- Keep only genuinely user-relevant system messages.

### 4. Notebook error replacement cycle

- Failed code cells should go through a visible `oops -> remove/replace -> rerun` loop.
- The stale failed cell should not remain in the notebook after a successful fix.
- Agent Actions should still preserve the recovery trace.

### 5. Left-rail navigation

- Investigation items in the Explorer rail should be clickable.
- Clicking an investigation should switch to notebook view and scroll to its section.

## Verification

- Typecheck and focused lint.
- Live browser pass against a real `T1_slice.csv` session.
- Confirm:
  - story renders and switches correctly
  - chat stays clean during hypothesis analysis
  - error cells do not persist after repair
  - left-rail investigation items navigate correctly
  - autoscroll stays pinned to the bottom through plots and long outputs
