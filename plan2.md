# Plan 2 — Intelligence, Story, Chat & History

**Owner**: Person B
**Scope**: Insight discovery, causal analysis, model readiness, the story/
versioning pipeline, the chat agent, master LangGraph wiring, and the story
tab + chat sidebar + history panel on the frontend.

---

**What you DON'T touch** (Person A owns these):
- `src/temporal_analysis/`, `src/dynamics/`, `src/multivariate/`, `src/split/`
- `src/ingest/file_loader.py`
- `backend/routers/session.py`, `backend/routers/kernel.py`, `backend/routers/notebook.py`
- `backend/services/session_manager.py`, `backend/services/kernel_manager.py`
- `frontend/components/notebook/`, `frontend/components/upload/`, `frontend/components/sidebar/`
- `frontend/hooks/useKernel.ts`, `frontend/stores/notebookStore.ts`, `frontend/stores/kernelStore.ts`
- `frontend/lib/kernelProtocol.ts`, `frontend/lib/notebookModel.ts`

**Shared interfaces** (coordinate with Person A):
- `CompositeState` in `src/tools/state_schema.py` — both add fields, neither deletes
- `frontend/app/session/[id]/page.tsx` — you own story tab, chat sidebar, history panel; they own notebook tab + file sidebar
- `frontend/app/layout.tsx` — scaffolded by Person A; you plug in your components
- `backend/app.py` — created by Person A; you add your routers via `include_router()`
- `frontend/lib/diffEngine.ts` — you implement; Person A's notebook confirm flow calls it

---

## Phase 0: Your Backend Foundation

### Routers
- [x] Create `backend/routers/stream.py` — `WS /api/stream/{id}` for agent pipeline progress events
- [x] Create `backend/routers/story.py` — `GET /api/story/{id}?format=json|md|pdf`, `POST /api/story/{id}/regenerate`
- [x] Create `backend/routers/history.py` — `GET /api/history/{id}`, `POST /api/history/{id}/restore/{version_id}`
- [x] Create `backend/routers/chat.py` — `WS /api/chat/{id}` bidirectional chat agent

### Models
- [x] Create `backend/models/story.py` — Pydantic: `StorySection`, `InsightCard`, `StoryExportRequest`
- [x] Create `backend/models/history.py` — Pydantic: `VersionSnapshot`, `VersionList`, `RestoreResponse`

### Services
- [x] Create `backend/services/story_service.py`:
  - [x] `generate_story(session_id)` — calls `src/reporting/story_generator.py`, writes story.json + story.md
  - [x] `export_pdf(session_id)` — markdown -> HTML -> PDF via weasyprint
  - [x] `regenerate_story(session_id)` — re-derives story from current notebook state
- [x] Create `backend/services/history_service.py`:
  - [x] `create_snapshot(session_id, trigger)` — copies notebook.ipynb + story.json to `history/v{n}/`
  - [x] `list_versions(session_id)` — returns version metadata from `history/versions.json`
  - [x] `restore_version(session_id, version_id)` — snapshots current, then overwrites from selected version

---

## Phase 0: Agent Orchestration (Master Pipeline)

### Pipeline wiring
- [x] Create `src/pipeline.py` — master LangGraph StateGraph connecting ALL phases:
  - [x] Sequential: Phase 1 (ingest) -> Phase 2 (quality) -> Phase 3 (univariate) -> Phase 4 (temporal) -> Phase 5 (dynamics)
  - [x] Branching gate after Phase 5: conditionally fan-out to Phase 6 / 7 / 8
  - [x] Fan-in before Phase 9 (split)
  - [x] Modeling gate after Phase 9: conditionally run Phase 10
  - [x] Phase 11 (story gen + notebook gen) always runs last
- [x] Implement `branching_gate(state) -> list[str]`:
  ```python
  if type == "multiple": -> phase_6_panel
  if numeric_features >= 2: -> phase_6_correlation
  if has_dimensions: -> phase_7_insights
  if features >= 3 and rows >= 200: -> phase_8_causal
  ```
- [x] Implement `modeling_gate(state) -> str`: skip Phase 10 if no target or user opts out
- [x] Wire fan-out/fan-in for phases 6+7+8 using LangGraph `Send` API
- [x] Implement streaming callback: on each node completion, push progress event to stream WebSocket

### State schema
- [x] Extract `CompositeState` into `src/tools/state_schema.py` (consolidate from scattered TypedDicts)
- [x] Add all Phase 7, 8, 10, 11 fields
- [x] Coordinate with Person A for their Phase 4, 5, 6, 9 fields

---

## Phase P: Prerequisites

### P.1 — Target/covariate classification
- [x] File: `src/ingest/infer_structure.py`
- [x] Add LLM gate after `infer_feature_buckets()`: classify columns as target vs covariate from names + profiles
- [x] If no target identifiable, leave empty (unsupervised EDA path)
- [x] Add `known_exogenous_cols` detection: match names against pattern dictionary (holiday, temperature, price, is_*, day_of_week)

### P.3 — Centralize model config
- [x] File: `src/config/config.py`
- [x] Remove all hardcoded `model="gpt-4.1"` across codebase
- [x] Add `get_gate_model()` and `get_agent_model()` helpers reading from env/config

---

## Phase 7: Insight Discovery

### 7.1 — Automated insight mining (Rule 29)
- [x] Create `src/insights/__init__.py`
- [x] Create `src/insights/insight_miner.py`
- [x] Implement `mine_insights()`:
  - [x] For each (dimension, measure) pair:
    - [x] Trend: Mann-Kendall (tau + p-value)
    - [x] Outlier: modified Z-score, flag top-k per dimension value
    - [x] Dominance: top-1 share of total
    - [x] Evenness: entropy across dimension values
    - [x] Correlation: Pearson with other measures within slices
  - [x] Composite interestingness score, rank, return top-K (default 10) with mini-chart data
- [x] LLM: generate natural-language descriptions of top insights
- [x] Add `insights: list[dict]` to CompositeState

### 7.2 — MetaInsight: commonness/exception (Rule 30)
- [x] Create `src/insights/meta_insight.py`
- [x] Implement `discover_meta_insights()`:
  - [x] For each top insight: check if pattern holds across other dimension values (commonness)
  - [x] Identify values that break the pattern (exceptions)
  - [x] Score: surprise = deviation from commonness distribution
- [x] LLM: synthesize "most X show Y, EXCEPT Z" sentences
- [x] Gate: panel data OR >= 3 values in breakdown dimension
- [x] Add `meta_insights: list[dict]`

### 7.3 — Drill-down on exceptions (Rule 31)
- [x] Implement `drill_down_exception()` in `meta_insight.py`:
  - [x] Filter dataset to exception subgroup, re-run insight mining
  - [x] Find explaining dimension, chain up to depth 3
- [x] LLM: decide which exceptions to drill, synthesize findings
- [x] Add `drill_down_findings: list[dict]`

---

## Phase 8: Causal Analysis

### 8.1 — Causal graph discovery (Rule 32)
- [x] Create `src/causal/__init__.py`
- [x] Create `src/causal/causal_graph.py`
- [x] Implement `discover_causal_graph()` using `causal-learn`:
  - [x] Pre-screen: detect FDs, exclude
  - [x] Run FCI on remaining variables
  - [x] Output: PAG adjacency matrix + edge types
  - [x] Plot: networkx + matplotlib visualization
- [x] Gate: >= 3 features AND >= 200 rows
- [x] Add `causal_graph: dict`, `causal_graph_plot: str`

### 8.2 — Causal vs non-causal classification (Rule 33)
- [x] Implement `classify_explanations()`:
  - [x] Walk causal graph: classify each variable as causal/non-causal/ambiguous
  - [x] LLM: generate "why queries" from top anomalies, then classify
- [x] Gate: causal graph exists AND anomalies identified
- [x] Add `causal_classifications: list[dict]`

### 8.3 — Responsibility scoring (Rule 34)
- [x] Implement `compute_responsibility()`:
  - [x] Counterfactual effect estimation via subgroup comparison
  - [x] Output: ranked (factor, responsibility_score, direction)
- [x] Gate: causal factors identified
- [x] Add `causal_responsibilities: list[dict]`

### 8.4 — Granger causality (Rule 35)
- [x] Create `src/causal/granger.py`
- [x] Implement `test_granger_causality()`:
  - [x] `statsmodels.tsa.stattools.grangercausalitytests` pairwise
  - [x] Max lag: min(seasonal_period, 20)
  - [x] Significant links (p < 0.05) with lag order + direction
  - [x] Plot: directed graph via networkx
- [x] Gate: multivariate + stationarity confirmed/differenced
- [x] Add `granger_report: dict`

---

## Phase 10: Model Readiness

### 10.1 — Stationarity tests (Rule 40)
- [x] Create `src/model_readiness/__init__.py`, `src/model_readiness/stationarity.py`
- [x] Implement `test_stationarity()`: ADF + KPSS, auto-difference if non-stationary
- [x] Gate: modeling_gate passes
- [x] Add `stationarity_report: dict`

### 10.2 — Cointegration (Rule 41)
- [x] Implement `test_cointegration()`: Johansen test on non-stationary pairs
- [x] Gate: >= 2 non-stationary series
- [x] Add `cointegration_report: dict`

### 10.3 — Baseline features (Rule 42)
- [x] Create `src/model_readiness/baseline_features.py`
- [x] Implement `create_baseline_features()`: calendar + lags + rolling stats, verify no off-by-one
- [x] Add `baseline_features: list[str]`, `feature_dataset_path: str`

### 10.4 — Feature importance (Rule 43)
- [x] Create `src/model_readiness/feature_importance.py`
- [x] Implement `screen_feature_importance()`: LightGBM, permutation importance, bar chart
- [x] Gate: feature_count > 10
- [x] Fallback: 80/20 in-place split if Person A's Phase 9 hasn't run
- [x] Add `feature_importance_report: dict`

---

## Phase 11: Story, Notebook Generation & Versioning

### 11.1 — Decision summary (Rule 44)
- [x] Create `src/reporting/__init__.py`, `src/reporting/summary.py`
- [x] Implement LLM tool `generate_decision_summary()`: structured JSON from full CompositeState
- [x] Add `decision_summary: dict`

### 11.2 — Notebook generation (Rule 45)
- [x] Create `src/reporting/notebook_generator.py`
- [x] Implement `generate_notebook()`:
  - [x] Use `nbformat` to build notebook
  - [x] Per phase: markdown cell (findings) + code cell (reproducible) + pre-computed outputs
  - [x] Header cell: dataset path, run timestamp, agent config
  - [x] Must be RUNNABLE end-to-end
- [x] Output: `sessions/{id}/notebook.ipynb`
- [x] Add `notebook_path: str`

### 11.3 — Story generation (Rule 46)
- [x] Create `src/reporting/story_generator.py`
- [x] Implement `generate_story()`:
  - [x] LLM reads notebook cell outputs + CompositeState
  - [x] Synthesizes narrative: executive summary -> per-phase sections -> recommendations
  - [x] Selects key plots (not all) for inline display
  - [x] Generates insight cards with provenance (rule, subset, confidence)
  - [x] Outputs structured JSON (for frontend) + flat Markdown (for export)
- [x] Output: `sessions/{id}/story.json`, `sessions/{id}/story.md`
- [x] Add `story_path: str`

### 11.4 — Version history system
- [x] Create `src/reporting/versioning.py`
- [x] Implement `create_version_snapshot(session_id, trigger)`:
  - [x] Save: notebook.ipynb + story.json + CompositeState summary + timestamp + trigger
  - [x] Store in `sessions/{id}/history/v{n}/`
  - [x] Update index: `sessions/{id}/history/versions.json`
- [x] Implement `list_versions(session_id)` — version list with timestamps + triggers
- [x] Implement `restore_version(session_id, version_id)` — auto-snapshot current, then restore
- [x] Automatic triggers: after pipeline run, on "Confirm Changes", on chat-driven mutation
- [x] Add `version_count: int`, `current_version: int`

---

## Chat Agent

- [x] Create `src/chat/__init__.py`
- [x] Create `src/chat/chat_agent.py`
- [x] Implement LangGraph ReAct agent with tools:
  - [x] `read_state(key)` — read any CompositeState field
  - [x] `read_notebook_cell(cell_id)` — read cell source + output
  - [x] `search_findings(query)` — semantic search over insights/story
  - [x] `insert_cell(position, code, markdown)` — add cell to notebook
  - [x] `modify_cell(cell_id, new_code)` — edit existing cell
  - [x] `rerun_phase(phase_id, params)` — re-run a specific phase of the pipeline
  - [x] `explain_why(target, context)` — query the causal graph (Phase 8)
- [x] System prompt: "You are an EDA assistant. The user has run an analysis on {dataset}. Help them understand findings, drill deeper, and refine the analysis. You can modify the notebook and re-run phases."
- [x] Every mutation (insert/modify/rerun) triggers a version snapshot
- [x] Wire to `backend/routers/chat.py` WebSocket

---

## Frontend: Story Tab

- [x] Create `frontend/components/story/StoryPane.tsx` — scrollable narrative with export bar
- [x] Create `frontend/components/story/StorySection.tsx` — collapsible section: title, prose, inline plots
- [x] Create `frontend/components/story/InsightCard.tsx` — type badge, description, mini-chart, provenance
- [x] Create `frontend/components/story/ExportDialog.tsx` — format picker (PDF/Markdown), download
- [x] Create `frontend/stores/storyStore.ts` (Zustand) — story JSON, current version, loading/error
- [x] Wire: on tab switch to Story -> load from `/api/story/{id}?format=json`
- [x] Wire: after "Confirm Changes" or chat mutation -> story auto-refreshes (poll or push via stream)

## Frontend: History Panel

- [x] Create `frontend/components/history/HistoryPanel.tsx` — version timeline overlay, restore buttons
- [x] Create `frontend/components/history/VersionItem.tsx` — version number, trigger description, timestamp, [Restore] button
- [x] Create `frontend/hooks/useHistory.ts` — fetch versions from `/api/history/{id}`, restore via POST
- [x] Wire: ⏱ button in TabBar opens HistoryPanel as overlay on center pane
- [x] Wire: Restore -> `POST /api/history/{id}/restore/{version}` -> reload notebook + story

## Frontend: Chat Sidebar

- [x] Create `frontend/components/chat/ChatSidebar.tsx` — collapsible right panel, message list + input
- [x] Create `frontend/components/chat/ChatMessage.tsx` — renders message types:
  - [x] `user`: plain text bubble
  - [x] `agent_text`: narrative answer
  - [x] `agent_cell_ref`: clickable link that scrolls to notebook cell (emits event to notebookStore)
  - [x] `agent_action`: "Added cell #15" / "Re-ran Phase 5" with [Undo] button
- [x] Create `frontend/components/chat/ChatInput.tsx` — text input + send button, Ctrl+Enter to send
- [x] Create `frontend/hooks/useChat.ts` — WS to `/api/chat/{id}`, message send/receive
- [x] Create `frontend/stores/chatStore.ts` (Zustand) — message history, typing indicator, pending actions
- [x] Wire: chat actions that mutate notebook -> update notebookStore (shared action) -> trigger version snapshot

## Frontend: Agent Streaming

- [x] Create `frontend/hooks/useAgentStream.ts` — WS to `/api/stream/{id}`, handle message types:
  - [x] `phase_start` -> update ProgressOverlay with current phase name
  - [x] `cell_ready` -> append cell to Person A's notebookStore (via shared store action)
  - [x] `phase_complete` -> update progress badges
  - [x] `pipeline_complete` -> dismiss overlay, load story into storyStore, mark notebook as clean

## Frontend: Diff Engine

- [x] Create `frontend/lib/diffEngine.ts`:
  - [x] `compare(baselineOutput, currentOutput)` -> list of diffs
  - [x] Numeric: parse numbers, flag changes > 5% relative
  - [x] Text: flag if insight text changed (fuzzy match)
  - [x] Plot: flag if base64 changed (hash comparison)
- [x] Called by Person A's notebook confirm flow; results passed to story regeneration

---

## Integration Tests

- [x] Full pipeline: upload CSV -> all 11 phases run -> notebook + story + v1 snapshot produced
- [x] Branching: single-series dataset -> phases 6 (panel) and 7 skipped correctly
- [x] Branching: panel dataset with 5+ entities -> phase 6 + 7 run, MetaInsight finds commonness/exceptions
- [x] Causal: 5+ features, 500+ rows -> causal graph produced, at least one classification
- [x] Granger: multivariate stationary series -> significant links detected
- [x] Story: generated story has executive summary + per-phase sections + inline plots + insight cards
- [x] Story regen: edit notebook cell, confirm -> story updates, old version in history
- [x] History: restore v1 -> current state auto-snapshotted, workspace shows v1 content
- [x] Chat: "Why is revenue dropping?" -> agent answers with cell references
- [x] Chat: "Add a Granger test for temperature" -> agent inserts cell, version snapshot created
- [x] Chat: [Undo] button on action message -> restores previous version
- [x] Export: PDF download produces valid PDF with plots; MD download is well-formatted
- [x] Streaming: during run, phase badges progress in real-time, cells appear incrementally
- [x] Notebook .ipynb: download from file sidebar, opens in JupyterLab, runs without errors
