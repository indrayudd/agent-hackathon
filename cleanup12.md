# Cleanup 12: Notebook Tabs Visibility + Design System Icons + Investigation Plots in Story

## Issues

### 1. Notebook tabs hidden/clipped
The tab bar (`NotebookTabs.tsx`) is barely visible in the main view. It only fully reveals when clicking an investigation tab. Root cause: the tab container uses `overflow-x-auto` and emoji icons, and sits in a flex column that can squeeze it.

### 2. Icons don't match design system
Tabs use emoji (📋, 🔍, ⏳, ✅) but the rest of the app uses Material Symbols (`material-symbols-outlined`). Per design.md "Neural Slate" system, all icons should be Material Symbols.

### 3. Investigation plots not in story
Subagent cells produce matplotlib plots but those cells aren't in the main `notebook.ipynb`. Story generation reads plots from `notebook.ipynb` only, so investigation plots are missing from the report. Fix: attach subagent plot images directly to story sections via the KG.

## Fixes

### Fix 1: NotebookTabs visibility + design
- Remove emoji icons, use Material Symbols: `description` (main), `science` (investigation)
- Status icons: `schedule` (running), `check_circle` (complete), `timer_off` (timeout)
- Add `min-h-[40px]` and `shrink-0` to prevent flex collapse
- Ensure proper z-index and border styling per design.md

### Fix 2: Investigation plots → story
- In eda_agent.py, after subagent results return, store base64 plot images in the KG investigation node metadata
- In run.py story generation, for investigation sections, extract plot images from KG metadata and create plot artifacts directly (bypass notebook.ipynb lookup for investigation cells)
