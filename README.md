# AgenticEDA

Autonomous exploratory data analysis powered by multi-loop parallel subagents. Upload a dataset, get a live notebook with investigations, a narrative story report, and a chat agent to drill deeper.

## What it does

- **Upload & go**: CSV, Excel, JSON, Parquet, log files — drop a file and hit Run
- **Multi-loop investigation**: N parallel subagents per loop, M loops with convergence detection
- **Vision-in-the-loop**: subagents see their own plots (multimodal feedback) and reason about visual patterns
- **Knowledge graph**: findings accumulate across loops with confidence scoring, cross-referencing, and contradiction detection
- **Live notebook**: cells stream in real-time with per-agent tabs, activity timeline, and progress tracking
- **Narrative story**: LLM-synthesized report with executive summary, investigation sections, plot galleries, and cross-notebook cell citations
- **Chat investigations**: ask follow-up questions that spawn background subagents, update the KG, and append to the story
- **Export**: PDF (IEEE format via LaTeX/tectonic) and Markdown

## Architecture

```
Frontend (Next.js)              Backend (FastAPI)              Agent (Python)
┌────────────────────┐         ┌───────────────────┐         ┌──────────────────────┐
│ Notebook (multi-tab)│   WS   │ Session, Kernel,  │         │ Main agent loop      │
│ Story + KaTeX math │◄──────►│ Stream, Story,    │◄───────►│   ├─ Initial EDA      │
│ Chat sidebar       │  REST  │ Chat, Run, History│         │   ├─ Hypothesis gen   │
│ Agent activity log │         │ Kernel pool mgr   │         │   ├─ N subagents (mp) │
│ Progress bar       │         │                   │         │   ├─ KG accumulation  │
└────────────────────┘         └───────────────────┘         │   └─ LLM conclusions  │
                                                              └──────────────────────┘
```

## How it works

1. **Initial EDA**: data loading, quality checks, correlations, time series analysis — each cell output is interpreted via multimodal LLM (text + plots)
2. **Hypothesis generation**: LLM proposes hypotheses based on findings, deduplicates against KG
3. **Parallel investigation**: N subagent processes spawn, each with its own kernel connection. Each subagent runs an adaptive loop (up to 5 cells), seeing previous stdout + plots at every step
4. **Conclusion synthesis**: each subagent produces a vision-aware conclusion (single multimodal LLM call with all plots)
5. **Accumulation**: main agent collects results, ingests into KG, writes to notebook with progress bar
6. **Loop**: repeat with new hypotheses informed by prior findings. Stop on convergence
7. **Final synthesis**: LLM cross-references all findings, flags contradictions, writes numbered conclusions
8. **Story generation**: KG sections + executive summary + plot artifacts → story.json → web view + PDF

## Running

```bash
# Backend
pip install -r requirements.txt
PYTHONPATH=. uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend && npm install && npm run dev
```

Open `http://localhost:3000`, upload a CSV, configure subagents/loops/depth, and click Run EDA.

### Environment variables

```
LLM_PROVIDER=openai          # openai, anthropic, google, openai_compatible
LLM_MODEL=gpt-5.4-nano-2026-03-17
LLM_TIMEOUT=60
LLM_MAX_RETRIES=2
EDA_SUBAGENT_MODEL=...       # optional: faster model for subagent code gen
OPENAI_API_KEY=...
```

## Project structure

```
src/
├── agent/
│   ├── eda_agent.py          # Main orchestrator (multi-loop, multiprocess dispatch)
│   ├── subagent.py           # Adaptive investigation loop (vision-in-the-loop)
│   ├── subagent_worker.py    # Process-safe worker (kernel connection via file)
│   ├── hypothesis.py         # Hypothesis generation + dedup
│   ├── knowledge_graph.py    # Typed nodes/edges, confidence scoring, persistence
│   ├── reasoning.py          # LLM interpretation (multimodal) + next-step decisions
│   └── state.py              # Agent state management
├── config/config.py          # LLM provider configuration
├── reporting/                # Story generation, versioning, plot contracts
└── chat/                     # Chat agent builder

backend/
├── routers/
│   ├── run.py                # Pipeline execution (background thread)
│   ├── chat.py               # Chat + hypothesis investigation (background process)
│   ├── story.py              # Story fetch, regenerate, PDF/Markdown export
│   ├── stream.py             # WebSocket event streaming
│   └── session.py            # Upload, session management
└── services/
    ├── kernel_manager.py     # IPython kernel lifecycle + cross-process execution
    └── kernel_pool.py        # Multi-kernel allocation for parallel subagents

frontend/src/
├── stores/                   # Zustand (notebook, story, chat, session)
├── hooks/                    # useAgentStream (WS event routing), useChat, useKernel
├── components/
│   ├── notebook/             # NotebookPane, NotebookCell, CellOutput, ThinkingBlock
│   ├── story/                # StoryPane, StorySectionCard (KaTeX + cross-notebook citations)
│   ├── chat/                 # ChatSidebar, ChatInput
│   └── layout/               # AgentActivityBadge, NotebookTabs
└── app/session/[id]/page.tsx # Main session page

docs/
├── SPECS.md                  # Original specification
├── design.md                 # Architecture design notes
├── plans/                    # Implementation plans (plan1-12)
└── cleanups/                 # Cleanup/refactor plans (cleanup1-13)
```

## Tech stack

- **Agent**: Python, LangChain, multiprocessing
- **Backend**: FastAPI, Jupyter kernel client, WebSocket streaming
- **Frontend**: Next.js, React, Zustand, Tailwind CSS, KaTeX, react-markdown
- **LLM**: configurable (OpenAI, Anthropic, Google)
- **PDF**: tectonic (LaTeX) with IEEEtran document class
