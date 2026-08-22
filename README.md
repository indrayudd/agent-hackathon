# AgenticEDA

Autonomous exploratory data analysis powered by multi-loop parallel subagents. Upload a dataset, get a live notebook with investigations, a narrative story report, and a chat agent to drill deeper.

## What it does

- **Upload & go**: CSV, Excel, JSON, Parquet, log files — drop a file and hit Run
- **Multi-loop investigation**: N parallel subagents per loop, M loops with convergence detection
- **Vision-in-the-loop**: subagents see their own plots (multimodal feedback) and reason about visual patterns
- **Knowledge graph**: findings accumulate across loops with confidence scoring, cross-referencing, and contradiction detection
- **Live notebook**: cells stream in real-time, can be executed against the session kernel, and preserve outputs across refreshes
- **Narrative story**: LLM-synthesized report with executive summary, investigation sections, plot galleries, and cross-notebook cell citations
- **Chat investigations**: ask follow-up questions that spawn background subagents, show complete/failed/timeout status, update the KG, and append to the story
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
3. **Parallel investigation**: N subagent processes spawn, each with its own kernel connection. Each subagent runs an adaptive loop (up to 5 cells), seeing previous stdout + plots at every step. Failed or timed-out investigations are reported without blocking the rest of the run
4. **Conclusion synthesis**: each subagent produces a vision-aware conclusion (single multimodal LLM call with all plots)
5. **Accumulation**: main agent collects results, ingests into KG, writes to notebook with progress bar
6. **Loop**: repeat with new hypotheses informed by prior findings. Stop on convergence
7. **Final synthesis**: LLM cross-references all findings, flags contradictions, writes numbered conclusions
8. **Story generation**: KG sections + executive summary + plot artifacts → story.json → web view + PDF

## Prerequisites

- Python 3.12 recommended
- Node.js 22 recommended for the frontend
- An LLM API key for the provider selected in `.env`
- Optional: Docker and Docker Compose for containerized runs

## Environment setup

Create a root `.env` file before starting the backend. The backend loads this file automatically.

Linux:

```bash
cp .env.example .env
```

macOS:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Windows Command Prompt:

```bat
copy .env.example .env
```

Minimum OpenAI configuration:

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-5.4-nano-2026-03-17
LLM_TIMEOUT=60
LLM_MAX_RETRIES=2
OPENAI_API_KEY=sk-...
```

Supported provider values and required keys:

| `LLM_PROVIDER` | Required env vars |
| --- | --- |
| `openai` | `OPENAI_API_KEY` |
| `anthropic` | `ANTHROPIC_API_KEY` |
| `google`, `gemini`, `google_genai` | `GOOGLE_API_KEY` |
| `openai_compatible` | `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY` |
| `azure_openai_v1` | `AZURE_OPENAI_BASE_URL`, `AZURE_OPENAI_API_KEY` |

Optional model controls:

```env
LLM_TEMP=0.2
EDA_AGENT_MODEL=gpt-5.4-nano-2026-03-17
EDA_GATE_MODEL=gpt-5.4-nano-2026-03-17
EDA_SUBAGENT_MODEL=gpt-5.4-nano-2026-03-17
```

Frontend API configuration is usually not needed for local development. When the frontend runs on `localhost:3000`, it automatically calls `http://localhost:8000/api`.

Set this only when the backend API is somewhere else:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

For local frontend development, put `NEXT_PUBLIC_API_URL` in `frontend/.env.local` or export it in the shell before running `npm run dev`.

## Run locally

Start the backend from the repo root.

Linux:

```bash
python3 -m pip install -r requirements.txt
PYTHONPATH=. uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

macOS:

```bash
python3 -m pip install -r requirements.txt
PYTHONPATH=. uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

Windows PowerShell:

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH="."
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

Windows Command Prompt:

```bat
python -m pip install -r requirements.txt
set PYTHONPATH=.
uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

Start the frontend in a second terminal:

Linux:

```bash
cd frontend
npm install
npm run dev
```

macOS:

```bash
cd frontend
npm install
npm run dev
```

Windows PowerShell:

```powershell
cd frontend
npm install
npm run dev
```

Windows Command Prompt:

```bat
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`, upload a dataset, configure subagents/loops/depth, and click Run EDA.

## Run with Docker

The Docker Compose setup reads backend environment variables from the root `.env` file.

Linux:

```bash
cp .env.example .env
# edit .env and add your provider API key
docker compose up --build
```

macOS:

```bash
cp .env.example .env
# edit .env and add your provider API key
docker compose up --build
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
# edit .env and add your provider API key
docker compose up --build
```

Windows Command Prompt:

```bat
copy .env.example .env
REM edit .env and add your provider API key
docker compose up --build
```

The nginx service exposes the app on `http://localhost` by default.

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
│   ├── chat.py               # Chat + hypothesis investigation events/status
│   ├── notebook.py           # Notebook fetch/patch persistence with output normalization
│   ├── kernel.py             # Session kernel status and code-cell execution
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
