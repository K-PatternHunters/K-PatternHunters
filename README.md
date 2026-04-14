# Customer Behavior Agent

> Automated e-commerce behavior pattern analysis pipeline powered by LangGraph + OpenAI, with auto-generated PPT reporting.

## Overview

This monorepo contains a full-stack AI agent system that:
1. Ingests weekly GA4 e-commerce log data into MongoDB
2. Runs a multi-agent LangGraph pipeline (schema mapping → funnel / cohort / journey / performance / anomaly / prediction → insight → PPT)
3. Delivers an auto-generated PowerPoint report via a Vue.js dashboard

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vue.js (Vite) |
| Backend | FastAPI + Celery |
| AI Orchestration | LangGraph (langchain v1.0+) |
| LLM | OpenAI API |
| Database | MongoDB |
| Vector DB | Qdrant (RAG) |
| PPT Generation | python-pptx |
| Containerization | Docker Compose |

## Quick Start

```bash
# 1. Clone & enter the repo
git clone <repo-url>
cd customer-behavior-agent

# 2. Set up environment variables
cp .env.example .env
# Edit .env with your API keys

# 3. Start all services
docker compose up --build

# 4. (Optional) Import GA4 sample data
docker compose exec backend python /app/data/sample/import_ga4_sample.py
```

- Frontend: http://localhost:5173
- Backend API docs: http://localhost:8000/docs
- Qdrant dashboard: http://localhost:6333/dashboard

## Repository Structure

```
customer-behavior-agent/
├── docker-compose.yml
├── .env.example
├── frontend/          # Vue.js dashboard
├── backend/           # FastAPI + LangGraph agents
└── data/              # Sample data import scripts
```

## Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | Production-ready, protected |
| `develop` | Integration branch |
| `feature/<name>` | Feature development |
| `fix/<name>` | Bug fixes |
| `chore/<name>` | Tooling / config changes |

See [CONTRIBUTING.md](./CONTRIBUTING.md) for full contribution guidelines.
