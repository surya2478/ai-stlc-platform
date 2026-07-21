# P1-S1 Executive Overview UI Contract

## Document control

| Field | Value |
|---|---|
| Screen ID | UI-001 |
| Section | P1-S1 Command Centre Foundation |
| Screen name | Executive Overview |
| Gate status | MOCKUP_IN_REVIEW |
| Baseline | nxtQA AAF v1.0 FINAL, 21 July 2026 |
| Approval rule | Implementation starts only after the visual mockup and this UI contract are approved |

## Purpose

The Executive Overview is the Phase 1 command-centre landing screen. It must give delivery leaders, QA managers, automation engineers and auditors one governed view of the AAF lifecycle: requirement intake, test design, application discovery, automation readiness, execution and deterministic evidence.

This screen is not a marketing dashboard and must not hide risk behind vanity metrics. Every displayed status must be traceable to governed records, deterministic checks, approved assets or explicit blockers.

## Primary user outcomes

- Understand whether Phase 1 journey work is ready, blocked, executing, inconclusive or complete.
- See lifecycle progress from requirement through evidence without opening every module.
- Identify approvals waiting on humans versus work waiting on agents, jobs, environments or evidence.
- Detect mandatory blockers before automation execution starts.
- Navigate to the exact module screen that owns the issue or next action.

## Required layout

The screen must use the existing nxtQA enterprise shell and Autonomous Lab navigation patterns.

Required regions:

- Header with project, environment, release window, feature-flag status and last refresh time.
- KPI strip for Requirements, Test Cases, Discovery, Automation, Execution and Evidence.
- Lifecycle flow showing the six Phase 1 operating domains and their current state.
- Readiness and blocker panel with deterministic gate outcomes.
- Work queue panel for approvals, agent handoffs, paused work and failed jobs.
- Risk/evidence summary panel showing deterministic outcomes and inconclusive items.
- Activity timeline with recent governed events.
- Right-side action rail for allowed next actions.

## Required data inputs

| Data area | Required source contract |
|---|---|
| Project context | Current project, user permissions, environment, release or cycle |
| Feature flags | Master AAF/Lab flag and section sub-flags |
| Requirements | Requirement intake status, analysis status, traceability status |
| Test design | Generated cases, edited cases, approval status, coverage gaps |
| Discovery | Registered application, discovery sessions, application model maturity |
| Automation | Automation IR status, script generation status, validation status, approved asset status |
| Execution | Active, queued, blocked and completed execution runs |
| Evidence | Evidence quorum, missing mandatory evidence, deterministic pass/fail/inconclusive status |
| Governance | Human approvals, agent handoffs, policy violations, audit events |
| Environment | Readiness check, dependency health, AVD or runner capacity where available |

## KPI contract

Each KPI must include:

- Label.
- Count or percentage.
- Status: `NOT_STARTED`, `IN_PROGRESS`, `READY`, `APPROVAL_REQUIRED`, `BLOCKED`, `FAILED`, `INCONCLUSIVE`, `COMPLETE`.
- Link target.
- Source timestamp.
- Empty-state message.

KPI cards must not be calculated from client-side guesses. Backend responses must provide the normalized status and count.

## Lifecycle state contract

Lifecycle stages:

- Requirement Intelligence.
- Test Design.
- Application Discovery.
- Automation Studio.
- Execution.
- Evidence and Review.

Each stage must show:

- Current state.
- Owner type: `USER`, `AGENT`, `SYSTEM`, `APPROVER`.
- Next required action.
- Blocking reason, if any.
- Navigation target.

## Actions

Allowed primary actions depend on permission and status:

- Open Requirement Intake.
- Open Generated Test Cases.
- Open Application Registry.
- Open Automation Workspace.
- Open Live Execution Monitor.
- Open Execution Report and Evidence.
- Review approvals.
- Refresh status.

The screen must not expose execution, approval or publishing actions unless the user has the required permission and the deterministic gates allow the action.

## Guardrails

- Do not start automation from this overview if mandatory discovery, IR, validation or evidence policies are missing.
- Treat missing mandatory evidence as `INCONCLUSIVE`.
- Treat environment and AVD failures as `BLOCKED` or `ENVIRONMENT_FAILURE`, not application defects.
- Do not allow the same agent to generate and approve an asset.
- Do not show secrets, credentials or raw PII in dashboard panels.
- Do not show video as authoritative evidence; structured evidence remains authoritative.
- Do not hard-code taxonomy or application names in UI logic.

## Empty and error states

Required states:

- AAF feature flag disabled.
- No project selected.
- No Phase 1 journey started.
- Requirement intake present but not analyzed.
- Tests generated but not approved.
- Discovery missing.
- Automation IR generated but not validated.
- Execution blocked by environment readiness.
- Evidence incomplete.
- API permission denied.
- API failure with retry.

## API shape

Suggested endpoint:

`GET /api/v1/lab/command-centre/executive-overview?project_id={id}&environment={env}`

Response shape:

```json
{
  "project": {},
  "feature_flags": {},
  "summary": [],
  "lifecycle": [],
  "readiness_gates": [],
  "work_queue": [],
  "risk_evidence": {},
  "activity": [],
  "actions": []
}
```

The implementation may split this across domain APIs if the same contract is assembled in the frontend query layer without losing authorization, auditability or deterministic status ownership.

## Acceptance criteria

- Visual mockup approved by user.
- UI contract approved by user.
- Screen route and menu placement confirmed.
- Backend status source for each KPI defined.
- Feature-flag-disabled and no-project states designed.
- Permission-gated actions defined.
- Deterministic blockers and inconclusive evidence states visible.
- No implementation begins until this gate is approved.
