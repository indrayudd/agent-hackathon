# AgenticEDA

Autonomous exploratory data analysis for analysts. Upload a dataset, get a runnable notebook with insights, a narrative story, and a chat agent to drill deeper.

## What it does

- **Robust ingestion**: CSV, Excel, JSON, Parquet, log files, MongoDB exports
- **11-phase EDA pipeline**: ingest, quality, univariate, temporal, dynamics, multivariate, insight discovery, causal analysis, train/test split, model readiness, reporting
- **Conditional branching**: the agent decides which phases to run based on your data's structure
- **Causal analysis**: discovers causal graphs and distinguishes causal from correlational explanations
- **Insight mining**: finds trends, outliers, commonness/exception patterns across dimensions
- **Notebook output**: reproducible, editable Jupyter notebook with pre-computed results
- **Story output**: LLM-synthesized narrative derived from the notebook, exportable as PDF
- **Version history**: Google-Docs-style snapshots every time you edit and confirm
- **Chat agent**: ask follow-up questions, insert new analyses, re-run phases with different parameters

## Architecture

```
Frontend (Next.js)          Backend (FastAPI)           Pipeline (LangGraph)
┌──────────┬───────┐       ┌──────────────────┐       ┌──────────────────┐
│Files│Note-│ Chat  │  WS   │ Session, Kernel, │       │ 11 phases with   │
│bar  │book/│ side- │◄─────►│ Story, History,  │◄─────►│ conditional      │
│     │Story│ bar   │  REST │ Chat, Stream     │       │ branching + LLM  │
└─────┴─────┴───────┘       └──────────────────┘       │ decision gates   │
                                                        └──────────────────┘
```

See [SPECS.md](SPECS.md) for the full implementation specification.

## Current status

**Implemented** (pipeline stages 1-11):
- Ingest: input validation, datetime parsing, series type inference, feature bucketing, temporal stats, integrity checks
- Quality: missingness audit + handling, optional standardization
- Univariate: summary statistics, distribution plots, transform testing

**Not yet implemented**: temporal visualization, dynamics, multivariate analysis, insight discovery, causal analysis, train/test splitting, model readiness, story generation, chat agent, frontend.

See [plan1.md](plan1.md) and [plan2.md](plan2.md) for the two orthogonal implementation tracks.

## Running the existing pipeline

```bash
pip install -r requirements.txt

python -m src.main --mode integrity --path datasets/T1_slice.csv
```

`--mode` runs up to and including that stage. Options: `input`, `format`, `infer_type`, `infer_structure`, `compute_temporal_stats`, `integrity`, `audit_missingness`, `handle_missingness`, `standardize`, `univariate_metrics_plotting`, `test_transforms`.

## Project structure

```
src/                    # Pipeline source (LangGraph + deterministic tools)
├── ingest/             # Phases 1-2: parsing, typing, integrity
├── quality_handling/   # Phase 2: missingness, standardization
├── univariate_analysis/# Phase 3: stats, distributions, transforms
├── config/             # LLM provider configuration
└── tools/              # Shared deterministic tool library

datasets/               # Sample test datasets
SPECS.md                # Full implementation specification
EDA_RULES.txt           # 47-rule EDA rulebook
plan1.md                # Implementation plan: analysis + notebook + ingestion
plan2.md                # Implementation plan: intelligence + story + chat
```

## Tech stack

- **Pipeline**: LangChain, LangGraph, Python
- **Frontend**: Next.js, React, Tailwind CSS, Monaco Editor
- **Backend**: FastAPI, Jupyter Kernel Gateway
- **LLM**: configurable (OpenAI, Anthropic, Google)
