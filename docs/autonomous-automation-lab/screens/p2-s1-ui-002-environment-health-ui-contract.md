# P2-S1 UI-002 Environment Health UI Contract

| Field | Value |
|---|---|
| Screen ID | UI-002 |
| Phase | Phase 2 - Enterprise Core |
| Section | P2-S1 Operational Command Centre |
| Screen name | Environment Health |
| Parent area | Command Centre |
| Proposed route | `/command-centre/environment-health?project=3` or `/autonomous-lab/environment-health?project=3` |
| Primary baseline | Existing application shell, sidebar, top project selector, Jira sync badge, white card layout, blue/emerald/amber/red/violet status palette |
| Implementation status | `CONTRACT_DRAFT_PENDING_REFERENCE_IMAGE` |

## 1. Purpose

Environment Health gives QA leads, release managers, automation engineers and platform admins a governed operational view of whether the automation ecosystem is ready to execute tests.

The screen must show service health, environment readiness, dependency status, authentication/capacity blockers, recent incidents and safe audited recovery actions before users move into AVD Operations or Live Executions.

## 2. Placement and navigation

UI-002 belongs under the Command Centre / Operational Command Centre area, not under Requirements or Test Planning.

Recommended left navigation:

- Dashboard
- Command Centre
  - Executive Overview
  - Environment Health
  - AVD Operations
  - Live Executions

If the current sidebar keeps Command Centre as a single menu item, UI-002 should either become a sub-view/tab inside Command Centre or a child item under Command Centre once nested navigation is enabled.

## 3. Required screen structure

### 3.1 Header

Must include:

- Breadcrumb: `e& STLC / Command Centre / Environment Health`
- Page title: `Environment Health`
- Screen badge: `P2-S1 UI-002`
- Subtitle: `Operational readiness across environments, services, dependencies, capacity and execution prerequisites.`
- Project selector inherited from shell
- Jira sync badge inherited from shell
- Last refreshed timestamp
- `Refresh` action
- Optional `Export Health Report` action

### 3.2 KPI cards

Top KPI row must fit one line at desktop width and follow the existing compact card style.

Required cards:

1. **Overall Health**
   - Value example: `Healthy`
   - Status badge: `Healthy`, `Degraded`, `Unavailable`, `Maintenance`, `Unknown`
   - Secondary text: impacted services count

2. **Execution Readiness**
   - Value example: `Ready with Warnings`
   - Status badge: `READY`, `READY_WITH_WARNINGS`, `NOT_READY`, `READINESS_UNKNOWN`
   - Secondary text: gate pass count

3. **Service Dependencies**
   - Value example: `12 / 14`
   - Secondary text: healthy dependencies
   - Badge if any dependency failure exists

4. **Environment Capacity**
   - Value example: `76%`
   - Secondary text: current utilization
   - Capacity warning badge if above threshold

5. **Authentication Health**
   - Value example: `Compliant`
   - Secondary text: token/session status
   - Badge if authentication failures exist

6. **Open Incidents**
   - Value example: `3`
   - Secondary text: active operational blockers
   - Critical/high count indicator

### 3.3 Environment readiness matrix

Primary mid-page section.

Must show environment-by-environment readiness:

Columns:

- Environment
- Type / Use
- Health status
- Readiness status
- AVD availability
- Queue depth
- Avg wait
- Active executions
- Failed dependency
- Last checked
- Next action

Expected rows:

- QA AVD
- SIT
- UAT
- Pre-Prod
- Production-like / Regression

Health statuses must support:

- `HEALTHY`
- `DEGRADED`
- `UNAVAILABLE`
- `MAINTENANCE`
- `UNKNOWN`
- `DEPENDENCY_FAILURE`
- `AUTHENTICATION_FAILURE`
- `CAPACITY_EXHAUSTED`

Readiness statuses must support:

- `READY`
- `READY_WITH_WARNINGS`
- `NOT_READY`
- `READINESS_UNKNOWN`

### 3.4 Service dependency health

Card or table showing platform and test execution dependencies.

Required dependencies:

- Jira sync
- Requirements service
- Test planning service
- Test case generation service
- Automation service
- Playwright runner
- AVD broker
- Test data service
- Evidence store
- Artifact storage
- Notification service
- AI model gateway
- RAG / knowledge index
- Secrets / authentication provider

Each dependency must show:

- Current status
- Latency or response time
- Error rate
- Last successful check
- Impacted downstream capability
- Owner / support group
- Next action

### 3.5 Health timeline

Must show recent health events in chronological form.

Fields:

- Timestamp
- Event type
- Environment
- Service
- Severity
- Description
- Detected by
- Current state

Example events:

- AVD pool capacity crossed 80%
- Jira sync recovered
- Evidence upload latency degraded
- Authentication token refresh failed
- Playwright runner node unavailable

### 3.6 Readiness gates

Governed gate panel showing whether execution can proceed.

Required gates:

- Environment reachable
- AVD pool available
- Test data available
- Application endpoints reachable
- Authentication valid
- Automation runner healthy
- Evidence capture enabled
- Required permissions granted
- No critical incidents
- Capacity within threshold

Each gate must show:

- Pass / warning / fail state
- Evidence timestamp
- Blocking reason when failed
- Owner
- Remediation action

### 3.7 Capacity and queue overview

Must visualize current capacity and workload pressure.

Required metrics:

- Total AVDs
- Available AVDs
- Busy AVDs
- Offline AVDs
- Queue depth
- Average wait time
- Longest waiting job
- Active executions
- Capacity threshold

Recommended layout:

- Compact utilization ring/bar
- Queue summary cards
- Framework/environment capacity breakdown

### 3.8 Right-side inspector drawer

Selecting an environment, service dependency, gate or incident opens a right-side contextual drawer.

Drawer tabs:

- Overview
- Dependencies
- Incidents
- Audit

Required drawer content:

- Selected environment/service name
- Current health and readiness
- Impact summary
- Failed checks
- Downstream impact
- Recent events
- Responsible owner
- Audit history
- Authorized actions

### 3.9 Actions

Actions must be permission-aware and audited.

Required actions:

- Refresh health
- Re-run readiness checks
- Open AVD Operations
- Open Live Executions
- Create incident
- Acknowledge warning
- Put environment in maintenance
- Remove maintenance
- Retry failed dependency check
- Export health report

Dangerous actions such as maintenance mode must require confirmation in implementation.

## 4. Filters and tabs

Required filters:

- Environment
- Health status
- Readiness status
- Service type
- Severity
- Owner
- Time window

Recommended tabs:

- All
- Healthy
- Degraded
- Blocked
- Maintenance
- Incidents

## 5. Data contract

The implementation may start with governed deterministic mock data if backend endpoints are not ready, but the UI must be shaped for real API integration.

Expected entities:

```ts
type EnvironmentHealthStatus =
  | "HEALTHY"
  | "DEGRADED"
  | "UNAVAILABLE"
  | "MAINTENANCE"
  | "UNKNOWN"
  | "DEPENDENCY_FAILURE"
  | "AUTHENTICATION_FAILURE"
  | "CAPACITY_EXHAUSTED";

type EnvironmentReadinessStatus =
  | "READY"
  | "READY_WITH_WARNINGS"
  | "NOT_READY"
  | "READINESS_UNKNOWN";

type EnvironmentHealthRecord = {
  id: string;
  projectId: number;
  environmentName: string;
  environmentType: string;
  healthStatus: EnvironmentHealthStatus;
  readinessStatus: EnvironmentReadinessStatus;
  avdTotal: number;
  avdAvailable: number;
  avdBusy: number;
  avdOffline: number;
  queueDepth: number;
  averageWaitMinutes: number;
  activeExecutions: number;
  failedDependency?: string;
  lastCheckedAt: string;
  owner: string;
};
```

## 6. Authorization and audit requirements

The UI must not expose operational controls as simple cosmetic buttons.

Controls must respect permissions:

- View environment health
- Re-run readiness checks
- Manage maintenance state
- Acknowledge incidents
- Create incidents
- Export health reports

All actions must capture:

- Actor
- Project
- Environment/service
- Action
- Previous state
- New state
- Timestamp
- Result

## 7. Visual and UX requirements

Must match the existing application:

- Dark navy left sidebar
- White content background
- Rounded white cards
- Blue primary actions
- Emerald success states
- Amber warning states
- Red failure states
- Violet AI/automation accents where needed
- Compact card/table density
- Right-side inspector pattern matching UI-007 to UI-011

Desktop layout must fit the major sections without excessive vertical gaps.

The top KPI row and readiness matrix should be visible without requiring immediate scrolling on a 1920x1080 screen.

## 8. Empty, loading and error states

Required states:

- Loading skeleton for KPI cards and matrix
- No environments configured
- Health service unavailable
- Partial data unavailable
- Permission denied for operational actions
- Stale health data warning
- Dependency timeout warning

## 9. Acceptance criteria

- UI-002 is reachable from Command Centre navigation.
- Header, KPIs, readiness matrix, dependency health, readiness gates, capacity overview and inspector are present.
- All health/readiness statuses listed in the tracker are represented.
- Actions are permission-aware and visibly audited.
- Selecting an environment/service/gate updates the right-side inspector.
- Layout matches the approved visual style used by UI-001 and UI-006 to UI-011.
- TypeScript passes.
- No duplicate dashboard route override is introduced.
- UI contract and reference image are stored in `docs/autonomous-automation-lab/screens`.

## 10. Reference image requirement

Implementation must not begin until the reference image for UI-002 Environment Health is provided and approved.

Expected image file:

`docs/autonomous-automation-lab/screens/Environment_Health.png`

After reference image approval, this contract status should move from:

`CONTRACT_DRAFT_PENDING_REFERENCE_IMAGE`

to:

`REFERENCE_IMAGE_APPROVED_READY_FOR_IMPLEMENTATION`

