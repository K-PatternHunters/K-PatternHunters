# Contributing Guide

Thank you for contributing to **customer-behavior-agent**! Please read this guide before opening a PR.

---

## Branch Strategy

```
main          ← production-ready, protected (no direct push)
  └─ develop  ← integration branch, PR target for features
       ├─ feature/<short-name>   e.g. feature/funnel-agent
       ├─ fix/<short-name>       e.g. fix/qdrant-connection
       └─ chore/<short-name>     e.g. chore/update-deps
```

- **Always branch off `develop`**, not `main`.
- `main` ← `develop` merges are done by maintainers after QA.

---

## Workflow

```bash
# 1. Sync with develop before branching
git checkout develop && git pull origin develop

# 2. Create your branch
git checkout -b feature/my-feature

# 3. Commit with conventional commits (see below)
git commit -m "feat(funnel-agent): add session segmentation logic"

# 4. Push and open a PR targeting develop
git push origin feature/my-feature
```

---

## Commit Message Convention

Follow **Conventional Commits** (`type(scope): description`):

| Type | When to use |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `chore` | Tooling, deps, config |
| `refactor` | Code change without behavior change |
| `docs` | Documentation only |
| `test` | Adding or fixing tests |
| `ci` | CI/CD workflow changes |

**Scope examples:** `frontend`, `backend`, `funnel-agent`, `docker`, `rag`, `ppt`

```
feat(cohort-agent): implement 30-day retention matrix
fix(qdrant): handle connection timeout on startup
chore(deps): bump langchain to latest
```

---

## Pull Request Rules

1. **One PR per issue** — keep PRs focused and small.
2. **Target `develop`**, never `main` directly.
3. Fill in the PR template completely.
4. At least **1 reviewer approval** required before merge.
5. CI must be green (lint + Docker build).
6. **No `.env` or secrets** — the CI will fail and the PR will be blocked.
7. Squash-merge preferred to keep `develop` history clean.

---

## Local Development Setup

```bash
# Clone
git clone <repo-url> && cd customer-behavior-agent

# Environment
cp .env.example .env   # fill in your API keys

# Start all services
docker compose up --build

# Backend only (faster iteration)
docker compose up mongodb qdrant redis
cd backend && uvicorn main:app --reload

# Frontend only
cd frontend && npm install && npm run dev
```

---

## Code Style

### Python (backend/)
- Formatter: **black** (line length 88)
- Linter: **ruff**
- All new files must have a **one-line module docstring** at the top.

### JavaScript (frontend/)
- Formatter: **Prettier**
- Linter: **ESLint** (Vue 3 recommended)
- All new `.js` files must have a **one-line comment** describing the file.

---

## Questions?

Open a [GitHub Discussion](../../discussions) or ping in the team Slack channel.
