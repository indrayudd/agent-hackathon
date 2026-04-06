# cleanup5.md — Fix remaining gaps

## 1. Chat-driven cells don't appear in notebook
- [x] Fix: stream WebSocket closes after pipeline completes. Chat pushes cell_write events but nobody receives them. Fix: keep the frontend stream WebSocket open indefinitely (not just during pipeline run), or have chat.py directly update notebookStore via a separate mechanism.
- [x] Simplest fix: after chat executes code, return the cell data in the REST response AND push to stream. Frontend useChat should append the cell to notebookStore directly from the response.

## 2. Chat shows too much — should be compact status only
- [x] Remove phase_transition messages from chat entirely — they're already shown in the notebook as markdown headers and in the progress bar
- [x] During pipeline run: chat shows ONLY "→ Starting EDA..." at start and "EDA complete!" at end
- [x] After pipeline: chat is purely conversational (user questions + agent answers)

## 3. Story plots placed contextually within sections
- [x] Update run.py story generation: associate each finding with the cell_id that produced it, and which cells have plots
- [x] Update StoryPane: instead of dumping all plots in a grid at the top, place each plot within its relevant section (match phase name)

## 4. Backend debug trace visible in chat during run
- [x] During pipeline run, push concise status messages to chat: "Loading dataset...", "Parsed 5 columns", "Found 7 outliers", "Plotting correlations..."
- [x] These should be SHORT one-liners, not the full thinking blocks

## 5. Stream stays open for chat-driven cells
- [x] Frontend useAgentStream: don't close on "complete" event, keep listening for chat-driven cell events
- [x] Backend stream.py: don't break the loop on "complete", keep polling until WebSocket disconnects
