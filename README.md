#AI Test Automation System

AI-assisted Software Test Life Cycle automation for requirements, planning, test cases, automation scripts, execution analysis, defect triage, reporting, approvals, and project-level RBAC.

## Architecture

- Frontend: Next.js 14, TypeScript, Tailwind CSS.
- Backend: FastAPI, SQLAlchemy async, Alembic.
- Data: PostgreSQL with pgvector image for future semantic search.
- Queue: Redis plus Celery worker.
- Agents: Requirement intake, quality review, test planning, scenario generation, test case generation, automation generation, execution analysis, defect analysis, and reporting.
- Auth: JWT login with backend-enforced project membership and RBAC.

The frontend can be deployed to Vercel. The backend, database, Redis, file storage, and Celery worker must be deployed to a backend-capable host such as Render, Railway, Fly.io, Azure Container Apps, AWS ECS, or a VM/Kubernetes environment.

## Repository Layout

```text
stlc-platform/
  backend/                 FastAPI app, models, schemas, services, agents, Celery tasks
  frontend/                Next.js app for the STLC command center
  docker-compose.yml       Local full-stack runtime
  .env.example             Safe environment template
  ARCHITECTURE_BASELINE.md Baseline inventory and audit
  IMPLEMENTATION_AUDIT.md  Implementation change log
```

## Safe Local Setup

1. Copy the environment template.

```bash
cp .env.example .env
```

2. Edit `.env`.

Set `APP_SECRET_KEY` to a long random value. Keep provider and Jira secrets empty unless you are actively testing those integrations.

3. Optional local admin seed.

Dev seeding is disabled by default. To seed a local admin, set these values only in your private `.env`:

```env
DEV_SEED_USER_ENABLED=true
DEV_SEED_USER_EMAIL=your-local-admin@example.com
DEV_SEED_USER_PASSWORD=replace-with-a-local-password
```

4. Start the full stack.

```bash
docker compose up --build
```

5. Open the app.

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

## Authentication

Business endpoints require authentication. Use the login page at `/login`, or register a user through the API docs and then sign in. Platform admins can create users and assign project roles from `/users`.

Public registration always creates a normal non-superuser account. Admin and superuser creation is protected by platform-admin endpoints.

## RBAC Summary

Project authorization is enforced in the backend. Key permissions include:

- `view_project`
- `manage_project`
- `approve_requirements`
- `approve_test_plans`
- `approve_test_cases`
- `generate_automation`
- `execute_tests`
- `raise_defects`
- `push_defects_to_jira`
- `approve_release_report`
- `view_audit_logs`

The UI uses token claims for display, but backend authorization is always loaded from the database.

## Vercel Frontend Deployment

Deploy only the `frontend/` directory to Vercel.

Vercel project settings:

- Root Directory: `frontend`
- Framework Preset: Next.js
- Build Command: `npm run build`
- Install Command: `npm install`

Required Vercel environment variables:

```env
NEXT_PUBLIC_API_URL=https://your-backend.example.com
NEXT_PUBLIC_ENABLE_DEV_AUTH=false
```

Your backend must allow the Vercel origin in `ALLOWED_ORIGINS`.

Example backend setting:

```env
ALLOWED_ORIGINS=https://your-vercel-app.vercel.app
```

## Backend Deployment Notes

The backend requires:

- PostgreSQL database
- Redis broker/result backend
- Persistent file storage mounted at `FILE_STORAGE_PATH`
- One FastAPI web process
- One Celery worker process
- Alembic migrations before startup

Production backend settings should include:

```env
APP_ENV=production
APP_DEBUG=false
APP_SECRET_KEY=replace-with-a-long-random-secret
DATABASE_URL=postgresql://user:password@host:5432/database
REDIS_URL=redis://host:6379/0
RUN_AGENTS_SYNCHRONOUSLY=false
DEV_SEED_USER_ENABLED=false
```
Production deployment: nxtqa.com

## GitHub Hygiene

- `.env` and `.env.*` are ignored.
- `.env.example` contains safe placeholders only.
- Docker build contexts exclude secrets, caches, dependencies, and build output.
- Do not commit real LLM keys, Jira tokens, local database dumps, generated uploads, or private documents.

## Validation

Common checks:

```bash
cd backend
python -m compileall app tests
python -m pytest

cd ../frontend
npm run lint
npm run build
```

With Docker Compose:

```bash
docker compose exec -T backend python -m compileall app tests
docker compose exec -T backend python -m pytest
docker compose exec -T frontend npm run lint
docker compose exec -T frontend npm run build
```
