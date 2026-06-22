# Architecture Baseline

Audit date: 2026-06-10

Scope: repository baseline, deployment hygiene, security posture, agent architecture, RBAC, and remaining gaps.

## Executive Summary

The platform is a full-stack STLC automation system with a Next.js frontend, FastAPI backend, PostgreSQL, Redis, Celery, and AI-agent services. The current codebase includes authenticated business APIs, project membership RBAC, approval audit records, structured LLM validation, Celery dispatch paths, document upload hardening, and a user-management screen.

The frontend is suitable for Vercel deployment when pointed at an externally hosted backend. The backend is not Vercel-native because it requires FastAPI, PostgreSQL, Redis, Celery workers, file storage, and migrations.

## Repository Inventory

Top-level files and folders:

- `.env.example` - safe environment template.
- `.gitignore` - excludes local env files, dependencies, caches, and build output.
- `.dockerignore` - root Docker hygiene.
- `docker-compose.yml` - local full-stack orchestration.
- `README.md` - current setup and deployment guide.
- `IMPLEMENTATION_AUDIT.md` - implementation change log.
- `ARCHITECTURE_BASELINE.md` - this baseline.
- `backend/` - FastAPI, database, agents, workers, tests.
- `frontend/` - Next.js frontend.
- `scripts/` - utility scripts.

Backend inventory:

- Models: 20 files under `backend/app/models`.
- Schemas: 12 files under `backend/app/schemas`.
- Routers: 13 files under `backend/app/api/v1/endpoints`.
- Agents: 17 files under `backend/app/agents`.
- Services: 14 files under `backend/app/services`.
- Celery task files: 3 files under `backend/app/worker/tasks`.
- Tests: authorization, RBAC, user management, agents, document upload, LLM resilience, display IDs, and route registration.

Frontend inventory:

- Pages: 13 route pages under `frontend/src/app`.
- Shared layout: sidebar, header, providers.
- API client: `frontend/src/lib/api.ts`.
- Vercel config: `frontend/vercel.json`.

Runtime inventory:

- PostgreSQL with pgvector image.
- Redis.
- FastAPI backend.
- Celery worker.
- Next.js frontend.
- Optional Ollama service.

## Endpoint Authentication Baseline

Unauthenticated endpoints:

- Health/liveness/readiness endpoints.
- User registration.
- User token/login.

Business endpoints:

- Use `CurrentUser`.
- Enforce project access or explicit project permission.
- Do not use unauthenticated `OptionalUser`.

Optional-user scan:

- `OptionalUser` alias not present.
- No `current_user.id if current_user else 1` fallback found.
- `get_current_user` still accepts an optional token internally so `require_user` can return `401`; this is not a business endpoint bypass.

## RBAC Baseline

Global/admin model:

- Platform admins and superusers can administer users and projects.
- Public registration cannot create admins or superusers.
- The last active platform admin is protected from deactivation/demotion.

Project RBAC:

- Project memberships define project-scoped roles.
- Backend authorization loads permissions from the database, not only from JWT claims.
- Read access uses `view_project`.
- Mutation and workflow actions use explicit permissions.

Representative permissions:

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

## Simulated And Demo Code

Known simulated/local-only areas:

- Jira push creates simulated Jira defect records when simulation mode is enabled.
- Real test execution is controlled by `REAL_TEST_EXECUTION`; local default is false.
- Local dev user seeding is disabled by default and requires explicit env variables.
- Frontend local dev auto-auth is disabled by default and requires explicit env variables.
- Automation agent may generate placeholder code if LLM output is incomplete.

## Secrets And Credentials Audit

Safe template:

- `.env.example` uses placeholders and empty secret values.
- `.env` and `.env.*` are ignored except `.env.example`.

Tracked local defaults:

- `docker-compose.yml` contains local-only Postgres defaults for Docker Compose.
- `backend/app/config.py` contains local fallback defaults for development runtime.
- No real API keys, Jira tokens, private keys, or cloud credentials were found by pattern scan.

Required operator action:

- Never commit `.env`.
- Replace `APP_SECRET_KEY` before staging or production.
- Store Vercel and backend production secrets in platform secret managers.

## Docker And Git Hygiene

Current hygiene:

- `.gitignore` excludes local env files, dependency folders, build output, caches, and logs.
- Root `.dockerignore` excludes Git metadata, env files, generated output, caches, and private handover document.
- `backend/.dockerignore` excludes Python caches, env files, storage, and logs.
- `frontend/.dockerignore` excludes Node modules, Next build output, env files, coverage, and logs.

## Vercel Readiness

Frontend:

- Deploy `frontend/` as the Vercel root directory.
- Set `NEXT_PUBLIC_API_URL` to the deployed backend URL.
- Keep `NEXT_PUBLIC_ENABLE_DEV_AUTH=false`.

Backend:

- Must be deployed separately.
- Requires PostgreSQL, Redis, persistent file storage, and a Celery worker.
- Must include the Vercel frontend URL in `ALLOWED_ORIGINS`.

## Gap Analysis Against 10 Design Principles

P01 - End-to-end STLC traceability: Mostly implemented through project-scoped artifacts and display IDs. Remaining gap: deeper cross-artifact traceability reports.

P02 - Human approval gates: Implemented for key artifacts with immutable approval actions. Remaining gap: broader audit event coverage outside approvals.

P03 - Complete audit trail: Partially implemented through approval actions and agent runs/logs. Remaining gap: universal audit log for every mutation.

P04 - Agent accountability: Agent runs, logs, status, and errors are modeled. Remaining gap: richer provenance for every generated artifact.

P05 - Secure-by-default authentication: Business endpoints require `CurrentUser`. Remaining gap: refresh tokens/session management.

P06 - Least-privilege access: Project roles and permission checks are implemented. Remaining gap: more granular edit permissions may be needed as workflows mature.

P07 - Backend-enforced authorization: Implemented through project access and permission helpers.

P08 - Production-safe AI integration: Structured output validation and retry/circuit breaker behavior exist. Remaining gap: prompt-injection scanning and provider-specific policy controls.

P09 - Telecom-scale design: Indexed memberships and project-scoped constraints exist. Remaining gap: pagination and query tuning for very large portfolios.

P10 - Deployment portability: Docker Compose works locally; frontend is Vercel-ready. Remaining gap: production backend deployment manifests are not included.

## Gap Analysis Against 14 Engineering Rules

R01 - No unauthenticated business APIs: Implemented.

R02 - No optional-user business logic: Implemented.

R03 - No fallback user IDs: Implemented.

R04 - Every entity-by-id route checks project scope: Mostly implemented. Continue adding tests as new routes are added.

R05 - Every mutation uses explicit permission checks: Implemented for representative STLC workflows. Continue expanding if new permissions are introduced.

R06 - Immutable approvals: Implemented for approve/reject flows.

R07 - DB-safe artifact IDs: Implemented with project-scoped uniqueness and row-id-backed display IDs.

R08 - Background work for expensive agents/extraction: Celery dispatch paths implemented; local synchronous path remains behind local settings.

R09 - Streamed and validated uploads: Implemented for supported document types.

R10 - Structured LLM output validation: Implemented with Pydantic schemas.

R11 - LLM retry/backoff/circuit breaker: Implemented in provider layer.

R12 - No real secrets in repo: No real secrets found; local placeholders and Docker defaults remain documented.

R13 - GitHub hygiene: Improved with ignore files, safe env template, and updated README.

R14 - Vercel readiness: Frontend is ready for Vercel when configured with an external backend URL.

## Recommended Next Steps

1. Add production backend deployment templates for the chosen host.
2. Add universal audit events for all create/update/delete actions.
3. Add refresh token support and token rotation.
4. Add CI workflow for backend tests and frontend build.
5. Add prompt-injection detection around uploaded documents and agent inputs.
6. Replace simulated Jira push and test execution when production integrations are selected.
