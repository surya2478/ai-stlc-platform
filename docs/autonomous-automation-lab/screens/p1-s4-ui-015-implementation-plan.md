# P1-S4 UI-015 Live Discovery Session — Implementation Plan & Tracker

| Field | Value |
|---|---|
| Screen ID | UI-015 |
| Contract | `docs/autonomous-automation-lab/screens/p1-s4-ui-015-live-discovery-session-ui-contract.md` |
| Status | Planned — Phase 1 not started |
| Plan approved | 2026-07-23 |

## Context

The UI-015 contract asks for a governed live discovery workspace: select an application/
environment, choose Guided User / Free User-Action / Supervised Agent-Driven recording, pass a
readiness gate, observe and control a real browser session with pause/resume/checkpoint/emergency
stop, capture structured evidence (DOM, elements, network, console, screenshots), and publish a
draft Application Model. Before writing code, this plan sizes the work honestly against what
exists in the codebase today and splits it into independently shippable phases.

## Research findings (what's real vs. what must be built)

Two research passes (reading the discovery agent, MCP session, readiness service, locator map,
`AgentRun`/Celery dispatch, the `MCPConnection`/`capability_resolver` pair shipped for Test
Automation Classification, Playwright AI Studio, `ExecutionRun`, and Grounded Automation PoC, plus
a full-codebase search for any WebSocket/SSE/push infrastructure) established:

| Capability | Status | Approach |
|---|---|---|
| Playwright-via-MCP browser transport | Real (`backend/app/agents/automation/mcp_session.py`) | Reuse subprocess lifecycle, host allowlist, PII masking as library code |
| Readiness gate | Real, generic (`backend/app/services/automation_runner/readiness.py`) | Reuse as-is; add one new check function |
| Locator confidence/knowledge base | Real but narrow (`backend/app/models/locator_map.py`, single `fallback_locator` string) | Reuse for committed elements; extend for ranked alternatives in Phase 4 |
| MCP connection registry / capability resolution | Real (`backend/app/services/test_classification/capability_resolver.py`) | Reuse directly for Validation Adapters/MCPs and the new readiness check |
| Idempotent command dispatch / audit-action pattern | Real (`agent_run_service.derive_idempotency_key`, `approval_service.create_approval_action`) | Reuse directly for session commands |
| Persisted 12-state session state machine | **Does not exist** (`AgentRun.status` is a flat 5-value enum) | New `DiscoverySession` state machine |
| True mid-task pause/resume of a live run | **No precedent anywhere** — the only existing control primitive is `celery_app.control.revoke(terminate=True)` (a kill); Grounded Automation PoC's "pause" is actually "task stops at a boundary, a new task relaunches" | Formalize that exact pattern deliberately (see below) |
| Live browser preview (video/CDP/streaming) | **Does not exist** — zero WebSocket/SSE anywhere in this codebase | Use the contract's own sanctioned fallback: poll the latest captured screenshot with an explicit "Latest capture — not live" label (Section 11.2) |

### Pause/resume design

A dedicated Celery task holds one `MCPSession` open and runs a step loop: perform one action →
persist it + a screenshot → re-read `DiscoverySession.pending_command` from the DB → act on it.
Same "DB is source of truth, worker polls it" pattern already used by `agent_tasks.py`'s
cancel-check and Grounded Automation PoC's reconciliation, just checked every step instead of once
at the end.

- **Pause**: persist a `DiscoveryCheckpoint`, set status `PAUSED`, close the `MCPSession` cleanly,
  task exits. Tool access is inherently revoked because the subprocess is gone.
- **Resume**: dispatch a *new* task that runs resume-state validation (Section 12), offers only
  backend-approved recovery options, reopens a fresh `MCPSession`, continues from the checkpoint.
- **Emergency stop**: same as pause but skips graceful teardown — best-effort immediate kill,
  checkpoint marked non-resumable.

This never holds a Celery worker slot idle waiting on a live command and needs no new pub/sub or
WebSocket infrastructure — it's a strict reading of the contract's own state machine, not a
corner cut.

## Phasing

- **Phase 1** (this tracker's checklist below) — Guided User Recording only.
- **Phase 2** — Free User-Action Recording mode.
- **Phase 3** — Supervised Agent-Driven Recording mode.
- **Phase 4** — Live MCP validator invocation, full Network/Console capture, ranked fallback
  locators, resume-state classification refinement, real Application Model Draft once UI-016 exists.

---

## Phase 1 checklist — Guided User Recording

### Backend

- [ ] `backend/app/models/discovery_session.py` — `DiscoverySession`, `DiscoveryAction`,
      `DiscoveryCheckpoint`, `DiscoveryCapture`, `DiscoverySessionEvent`
- [ ] Migration `041_discovery_sessions.py` (additive, reversible, verified against real Postgres
      up/down, watch the 63-char identifier limit)
- [ ] `backend/app/services/discovery/session_service.py` — create/list/detail, Section 3.1
      eligibility validation, idempotent command issuance
- [ ] `backend/app/services/discovery/readiness_check.py` — existing `readiness.py` + new
      validator/MCP connectivity check (Section 7 #14)
- [ ] `backend/app/services/discovery/capture_service.py` — step-loop body (action → evidence →
      command check)
- [ ] `backend/app/services/discovery/resume_validation_service.py` — Section 12 state
      classification
- [ ] `backend/app/worker/tasks/discovery_tasks.py` — dedicated Celery task, not routed through
      the generic `AGENT_REGISTRY`
- [ ] `backend/app/api/v1/endpoints/discovery.py` — endpoints listed below, flag-gated
      (`discovery_sessions_enabled`), `discovery.*` RBAC permissions
- [ ] Router registration + permission wiring (`rbac_service.py`, `router.py`)
- [ ] Backend tests: state-transition matrix, idempotent commands, checkpoint-before-pause
      invariant, readiness blocking, permission/project isolation, migration up/down

Endpoints:

```
POST /discovery/sessions
GET  /discovery/sessions
GET  /discovery/sessions/{id}
GET  /discovery/sessions/eligible-test-cases
POST /discovery/sessions/{id}/readiness
POST /discovery/sessions/{id}/commands
GET  /discovery/sessions/{id}/actions
POST /discovery/sessions/{id}/actions/{aid}/correct
GET  /discovery/sessions/{id}/checkpoints
GET  /discovery/sessions/{id}/captures/{cid}
POST /discovery/sessions/{id}/complete
POST /discovery/sessions/{id}/cancel
GET  /discovery/sessions/{id}/activity
```

### Frontend

- [ ] Route: extend `/automation` shell with `?view=discovery&application=&environment=`
- [ ] Header: project/application/environment/mode/Test Context selectors (full interactive
      selector per Section 6.1 — chips, `Change`, lock-after-start), session ID, live state badge
- [ ] Persistent readiness strip with per-check cards + score gauge
- [ ] Left panel: Guided-mode step plan
- [ ] Center panel: polled "latest capture" screenshot view with explicit not-live labeling
- [ ] Right inspector tabs: Live State, Elements, Evidence, Activity, Notes (System Validations
      tab present but explicitly read-only/status-only, labeled pending Phase 4)
- [ ] Validation Adapters/MCPs status strip (reuses `/api/v1/mcp-connections`, read-only,
      `Configure` deep link)
- [ ] Session history table + filters (Section 14)
- [ ] Polling via TanStack Query `refetchInterval`, modeled on `groundedPoc.ts`
- [ ] Wire UI-014's disabled "Start Discovery" button (`ApplicationInspector.tsx`) to this route
- [ ] Frontend verification: typecheck/lint/build, live browser walkthrough (create session,
      step through capture, pause, resume, complete) with flag on and off

---

## Deferred / backlog (Phases 2-4)

- [ ] Free User-Action Recording mode
- [ ] Supervised Agent-Driven Recording mode (approve/modify/skip/manual-control/rollback loop)
- [ ] System Validations tab actually invoking validator MCPs mid-session
- [ ] Full Network/API and Console/Timing capture
- [ ] Multi-strategy ranked fallback locators (`locator_map` schema extension)
- [ ] Resume-state auto-classification refinement (data-changed/application-restarted heuristics)
- [ ] Real Application Model Draft creation/versioning once UI-016 exists
- [ ] UI-017 API & Network Explorer handoff
- [ ] Session action editing UI polish (drag-reorder, bulk include/exclude)
- [ ] Mobile/Appium and UiPath adapters (stay maturity-labeled `UNSUPPORTED` until real adapters exist)

## Verification summary

- Backend: full state-transition coverage, idempotency, checkpoint invariant, readiness gate,
  permissions, project isolation, migration up/down against real Postgres.
- Frontend: typecheck/lint/build clean, authenticated live browser walkthrough on real project
  data with the feature flag both on and off, matching how UI-014 and Test Automation
  Classification were verified.
