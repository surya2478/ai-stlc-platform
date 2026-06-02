# STLC Automation Platform

**AI Agent–based End-to-End Software Test Life Cycle Automation**

A self-hosted, open-source QA command center that uses autonomous AI agents (LangGraph + LlamaIndex) to manage the complete STLC: requirement analysis, test planning, test case development, automated execution, defect reporting, and dashboard analytics.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│  Next.js 14 Frontend  (Tailwind + shadcn/ui)        │
│  Port 3000                                          │
└────────────────────┬────────────────────────────────┘
                     │ REST / JSON
┌────────────────────▼────────────────────────────────┐
│  FastAPI Backend                                    │
│  Port 8000  ·  /docs (Swagger)  ·  /redoc           │
│  ┌──────────────────────────────────────────────┐   │
│  │ Auth │ Projects │ Docs │ Agents │ Execution  │   │
│  │ Jira │ Tests    │ Defs │ Reports│ Approvals  │   │
│  └──────────────────────────────────────────────┘   │
└────┬──────────────────────┬──────────────────────┬──┘
     │ SQLAlchemy async      │ Celery tasks          │
┌────▼────┐          ┌──────▼──────┐         ┌──────▼──┐
│PostgreSQL│         │Redis Queue  │         │File     │
│+ pgvector│         │+ Result     │         │Storage  │
└──────────┘         └─────────────┘         └─────────┘
                            │
                 ┌──────────▼──────────┐
                 │  Celery Workers      │
                 │  LangGraph Agents    │
                 │  LlamaIndex RAG      │
                 └──────────┬──────────┘
                            │
              ┌─────────────▼─────────────┐
              │  LLM Providers (pluggable) │
              │  · Ollama (local)          │
              │  · OpenAI-compatible API   │
              └────────────────────────────┘
```

---

## Quick Start

### Prerequisites

- **Docker** 24+ and **Docker Compose** v2
- 8 GB RAM minimum (16 GB recommended for local LLMs)
- (Optional) [Ollama](https://ollama.com) installed locally for offline LLM support

### 1. Clone and configure

```bash
git clone <your-repo>
cd stlc-platform

# Copy and edit environment variables
cp .env.example .env
# Edit .env — at minimum set APP_SECRET_KEY to a random string
```

### 2. Start the platform

```bash
# Standard startup (uses OpenAI-compatible or Ollama via .env)
docker compose up --build

# With local Ollama service included
docker compose --profile ollama up --build
```

### 3. Access the platform

| Service | URL |
|---|---|
| **Frontend Dashboard** | http://localhost:3000 |
| **API (FastAPI)** | http://localhost:8000 |
| **API Docs (Swagger)** | http://localhost:8000/docs |
| **API Docs (ReDoc)** | http://localhost:8000/redoc |
| **PostgreSQL** | localhost:5432 |
| **Redis** | localhost:6379 |

### 4. First steps

1. Open http://localhost:3000
2. Register a user account at http://localhost:8000/docs → `POST /api/v1/users/register`
3. Create your first project
4. Upload a requirement document or connect Jira
5. Trigger the AI agent pipeline

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Description | Default |
|---|---|---|
| `APP_SECRET_KEY` | JWT signing secret — **change this** | `change-me` |
| `DEFAULT_LLM_PROVIDER` | `ollama` or `openai` | `ollama` |
| `DEFAULT_LLM_MODEL` | LLM model name | `llama3.1` |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://ollama:11434` |
| `OPENAI_API_KEY` | OpenAI / Groq / OpenRouter key | _(empty)_ |
| `OPENAI_BASE_URL` | OpenAI-compatible base URL | `https://api.openai.com/v1` |
| `JIRA_BASE_URL` | Your Jira instance URL | _(empty)_ |
| `JIRA_EMAIL` | Jira account email | _(empty)_ |
| `JIRA_API_TOKEN` | Jira API token | _(empty)_ |

---

## Project Structure

```
stlc-platform/
├── docker-compose.yml          # All services: db, redis, backend, worker, frontend, ollama
├── .env.example                # Environment variable template
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_initial_schema.py   # All 20 tables
│   └── app/
│       ├── main.py                     # FastAPI app entry point
│       ├── config.py                   # Pydantic settings
│       ├── database.py                 # SQLAlchemy async engine
│       ├── models/                     # 20 SQLAlchemy ORM models
│       ├── schemas/                    # Pydantic request/response schemas
│       ├── api/v1/endpoints/           # REST endpoint handlers
│       ├── repositories/               # DB access layer (repository pattern)
│       ├── services/                   # Business logic layer
│       ├── agents/                     # AI agent implementations (Phase 2+)
│       │   └── base/base_agent.py      # Abstract base class for all agents
│       ├── llm/provider.py             # Pluggable LLM provider (Ollama / OpenAI)
│       └── worker/                     # Celery background task queue
└── frontend/
    ├── Dockerfile
    ├── package.json                    # Next.js 14 + Tailwind + Recharts
    └── src/
        ├── app/
        │   ├── dashboard/              # Command center dashboard
        │   └── projects/               # Project list + creation
        ├── components/
        │   ├── layout/                 # Sidebar, Header
        │   └── dashboard/              # StatCard, charts, widgets
        └── lib/
            ├── api.ts                  # Axios API client
            └── utils.ts
```

---

## AI Agents (Phase 2+)

All 11 agents extend `BaseAgent` and are dispatched via Celery:

| # | Agent | Phase | Status |
|---|---|---|---|
| 1 | Requirement Intake Agent | Phase 2 | 🔜 Pending |
| 2 | Requirement Quality Agent | Phase 2 | 🔜 Pending |
| 3 | Test Planning Agent | Phase 3 | 🔜 Pending |
| 4 | Test Scenario Agent | Phase 3 | 🔜 Pending |
| 5 | Test Case Development Agent | Phase 3 | 🔜 Pending |
| 6 | Test Data Agent | Phase 3 | 🔜 Pending |
| 7 | Automation Script Agent | Phase 4 | 🔜 Pending |
| 8 | Test Execution Agent | Phase 5 | 🔜 Pending |
| 9 | Defect Analysis Agent | Phase 6 | 🔜 Pending |
| 10 | Jira Defect Agent | Phase 6 | 🔜 Pending |
| 11 | Test Reporting Agent | Phase 7 | 🔜 Pending |

---

## Implementation Roadmap

| Phase | Focus | Key Deliverables |
|---|---|---|
| **1** ✅ | Foundation | Docker, FastAPI skeleton, full DB schema, Next.js dashboard, LLM abstraction |
| **2** | Requirement Intake | File upload, PDF/DOCX extraction, Jira sync, Agents 1 & 2 |
| **3** | Test Generation | Agents 3–6, test case repository UI, approval workflow |
| **4** | Automation | Agent 7, Playwright/Pytest script generation, script repository UI |
| **5** | Execution Engine | Agent 8, Pytest/Playwright runner, Allure reports |
| **6** | Defect Management | Agents 9 & 10, Jira defect approval flow |
| **7** | Reporting | Agent 11, coverage dashboard, PDF/Excel export |
| **8** | Hardening | RBAC, audit logs, prompt injection protection, full Docker docs |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14, TypeScript, Tailwind CSS, shadcn/ui, Recharts, Lucide |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2 |
| Database | PostgreSQL 16 + pgvector |
| Cache/Queue | Redis 7, Celery 5 |
| AI Agents | LangGraph, LlamaIndex |
| LLMs | Ollama (local), OpenAI-compatible (pluggable) |
| Document Processing | PyMuPDF, python-docx, pandas, Unstructured.io |
| Test Automation | Playwright, Pytest, HTTPX, Allure |
| Auth | JWT (python-jose), bcrypt (passlib) |

---

## Development

### Run backend locally (without Docker)

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Start PostgreSQL and Redis (via Docker or locally)
docker compose up db redis -d

# Run migrations
alembic upgrade head

# Start API
uvicorn app.main:app --reload --port 8000
```

### Run frontend locally

```bash
cd frontend
npm install
npm run dev
```

---

## Human-in-the-Loop Approval Gates

The platform enforces human approval before any destructive or external action:

1. ✅ Approve interpreted requirements
2. ✅ Approve test plan
3. ✅ Approve test cases
4. ✅ Approve automation scripts
5. ✅ Approve test execution environment
6. ✅ **Approve Jira defect creation** (Jira defects are NEVER created without this)
7. ✅ Approve release report export

All approvals are stored in the `approval_actions` table for audit.

---

## Security

- No secrets hardcoded — all via environment variables
- JWT-based authentication
- Passwords hashed with bcrypt
- Jira API tokens encrypted at rest
- File upload validation (type + size limits)
- Prompt injection protection (Phase 8)
- Role-based access control (Phase 8)

---

## License

MIT — Free for personal and commercial use.
