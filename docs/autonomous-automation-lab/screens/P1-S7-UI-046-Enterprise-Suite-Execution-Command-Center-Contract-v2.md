# P1-S7 — UI-046
# Live Execution Monitor — Enterprise Suite Execution Command Center
## UI/UX and Functional Contract — Version 2.0

| Field | Value |
|---|---|
| Platform | nxtQA STLC Platform |
| Repository | `D:\AI\Projects\stlc-platform` |
| Screen ID | UI-046 |
| Display name | Suite Execution Command Center |
| Parent area | Automation → Execution |
| Route | `/automation/executions/{runId}/live` |
| Predecessor | Published Automation Suite Snapshot / readiness confirmation |
| Successor | UI-052 Execution Report and Evidence |
| Primary entity | Execution Run |
| Scope | One active, governed automation suite execution |

---

## 1. Purpose

UI-046 is the operational command center for one automation suite run. It must enable an authorized user to:

- understand suite progress in less than five seconds;
- distinguish completed results from active lifecycle states;
- identify failed, blocked, inconclusive, running and queued tests immediately;
- filter and locate any test in a large suite;
- inspect the selected test case, current step, assertions and evidence without leaving the run;
- understand runner capacity, queue pressure and environment readiness;
- pause scheduling, resume, stop gracefully, cancel or emergency-stop with explicit semantics;
- retain the exact immutable suite, script, configuration, environment and data context;
- open the finalized report when the run reaches a terminal state.

The screen does not plan releases, edit suites, heal scripts or provide historical analytics.

---

## 2. Enterprise information architecture

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Global shell / breadcrumb / suite identity / run metadata / controls         │
├──────────────────────────────────────────────────────────────────────────────┤
│ Suite progress + interactive status counts + parallel/queue/readiness        │
├───────────────┬────────────────────────────────────────┬─────────────────────┤
│ Suite tree &  │ Virtualized test execution matrix      │ Selected test       │
│ saved filters │                                        │ inspector           │
├───────────────┴────────────────────────────────────────┴─────────────────────┤
│ Live operations bar: workers, event stream, evidence, health, last update    │
└──────────────────────────────────────────────────────────────────────────────┘
```

The suite context must never disappear when a user drills into a test or step.

---

## 2.1 Reference-image reconciliation and scoped-slice boundary

Recorded 30 July 2026, before implementation. The reference image, this
contract text and the live application disagree in the places below. Each
resolution is stated so no divergence is silently absorbed.

### 2.1.1 Shell and navigation — image is a mock, live shell wins

The image shows a different application shell: a flat `WORKSPACE` / `MANAGE`
sidebar (Overview, Requirements, Test Design, Discovery, Automation, Test Data,
Execution, Reports, Settings), an `nQ / nxtQA / STLC PLATFORM` logo block, and a
user card pinned bottom-left. The live application
([`Sidebar.tsx`](../../../frontend/src/components/layout/Sidebar.tsx)) has
grouped navigation with different labels, and a header carrying the breadcrumb,
project selector and Jira-sync chip.

**Resolution.** The image is read as a specification of the *content region*
only — the progress strip, three-panel body and bottom operations bar. The
existing shell, nav, spacing, typography and colour system are preserved
unchanged, per delivery rule 4. The image is not treated as a request to
redesign navigation.

### 2.1.2 Screen title — deliberate deviation from Section 3

Section 3 requires the screen title `Suite Execution Command Center`. The image
instead uses the suite name as the H1 (`Postpaid Order-to-Activation
Regression`) with a `LIVE` pill beside it.

**Resolution.** The image is followed: an operator arriving at this screen needs
to identify *which run they are looking at*, not what the screen is called. The
screen name is carried by the breadcrumb (`Automation / Execution / Live`, as
Section 3 also requires) and the document title. This is a conscious deviation
from Section 3's wording, not an oversight.

### 2.1.3 The `P1-S7 · UI-046 · LIVE EXECUTION` eyebrow is not shipped

That line in the image is specification annotation — internal tracker
identifiers have no meaning to an operator and appear nowhere else in the
product. It is dropped. The breadcrumb replaces it.

### 2.1.4 Header fields the image omits

The image header carries suite snapshot version, run ID, environment, framework
mix and elapsed time. Section 3 additionally requires release/execution
purpose, application scope, trigger source, triggered-by, start time, lifecycle
badge and the live-connection badge.

**Resolution.** Section 3 is implemented in full. Fields beyond the image's five
move into a run-details popover behind the existing `⋮` control rather than
crowding the header band.

### 2.1.5 Progress rail

Section 4.1 requires a horizontal rail segmented by final result. The image
shows a single-colour rail plus a completion donut.

**Resolution.** The rail is segmented per the contract; the donut is kept
because it is the five-second anchor Section 1 asks for. Both are driven by the
same reconciled counts.

The image's counts reconcile exactly under Section 4.3
(`126 + 4 + 2 + 3 + 8 + 61 = 204`), and `Skipped` is correctly absent at zero.

### 2.1.6 "Live application view" is a last-captured frame, not a live feed

The inspector pane labelled `LIVE APPLICATION VIEW` in the image implies a
streaming view of the browser. Playwright captures screenshots as per-step
attachments; there is no live frame transport in this platform.

**Resolution.** The pane renders the most recently captured screenshot with its
capture timestamp and is labelled as last-captured. A placeholder with a stated
reason shows when no frame has been captured yet. A simulated live feed would
violate delivery rule 6.

### 2.1.7 Transport — Section 11's WS/SSE becomes polling

Section 11 lists `WS/SSE /stream`. The platform has **no** WebSocket or SSE
infrastructure. Both existing live screens deliberately poll a database state
machine instead; the reasoning is recorded in
[`discovery_session.py`](../../../backend/app/models/discovery_session.py) and
UI-019 follows it.

**Resolution.** `GET /events?after={sequence}` is the transport, polled on an
interval, backed by a monotonic per-run event sequence so reconnection cannot
lose or duplicate events (Section 14.8). The `/stream` endpoint is **not**
implemented rather than shipped as a fake. Consequently the bottom bar's
latency indicator reports measured poll lag, and the connection badge
(`LIVE` / `DELAYED` / `RECONNECTING` / `OFFLINE SNAPSHOT`) is derived from the
last successful poll and the age of the newest backend event.

### 2.1.8 Frameworks in the image that cannot be dispatched

The image shows Katalon, Appium and Selenium members. Only Playwright and
pytest runners exist
([`dispatcher.py`](../../../backend/app/services/automation_runner/dispatcher.py)).

**Resolution.** The Framework column renders whatever the immutable snapshot
declares, but a member whose framework has no registered runner is classified
`BLOCKED` with that exact reason. It is never reported as passing, and no
framework is faked.

### 2.1.9 Device sessions

The image's `Sessions 6 web · 2 mobile` implies an AVD/device fleet. There is no
AVD fleet in Phase 1 — that is P2-S1. The bottom bar reports real worker and
browser-session counts only; the mobile split is omitted rather than shown as a
zero.

### 2.1.10 Illustrative data

The suite name, 204 members, `TC-POA-*` identifiers, `AVD-07`, `EXE-2026-0730-001`
and every count in the image are illustrative. Nothing from the image is seeded,
hardcoded or used as a fallback.

### 2.1.11 Route and entry point

The contract route `/automation/executions/{runId}/live` is accepted: it nests
under the existing `/automation` route and inherits its shell, so delivery rule 5
holds and no duplicate top-level page is created. The entry point is the
Automation Workspace suite's Executions tab — currently honestly disabled — not a
new sidebar item.

### 2.1.12 Scoped-slice boundary

Delivered under a one-week bound, agreed with the user on 30 July 2026, which
also carried an explicit override of delivery rule 2 to take P1-S7 before P1-S6.

**In scope.** Suite-to-execution dispatch over the published snapshot; the
five-way readiness gate as a hard precondition; sequenced persisted events with
correlation IDs and cursor polling; all eight outcome states in the model and
database constraints; evidence the demo journey actually produces — screenshot,
log, trace, API/network and console; minimum-present evidence quorum; pause,
resume, stop gracefully and cancel now with backend acknowledgement and
optimistic concurrency; count reconciliation; URL-reflected filters; Section 13
keyboard and reduced-motion behaviour; cursor pagination and row windowing for
Section 14.13.

**Deferred, rendered visibly disabled with the reason stated in the UI.** DOM
evidence; accessibility evidence; telecom-backend event evidence; video
evidence; evidence-quorum policy beyond minimum-present; emergency stop, which
needs the project/global kill path belonging to P2-S1; and full
requirement-to-defect lineage, which belongs to UI-052.

All eight outcome states land in the schema now even though the deferred
evidence types cannot yet produce two of them, because retrofitting a check
constraint over live execution rows is materially harder than getting the
vocabulary right once.

---

## 3. Header and execution identity

Required content:

- Breadcrumb: `Automation / Execution / Live`.
- Screen title: `Suite Execution Command Center`.
- Suite name and immutable snapshot version.
- Run ID with copy action.
- Release or execution purpose, when supplied by the suite snapshot.
- Environment and application scope.
- Framework mix: Playwright, Katalon, Appium, Selenium or mixed.
- Trigger source: user, schedule, CI/CD or API.
- Triggered by.
- Start time and elapsed time.
- Current lifecycle badge.
- Live connection badge: `LIVE`, `RECONNECTING`, `DELAYED`, `OFFLINE SNAPSHOT`.
- Primary action determined by state.
- Secondary execution controls in a clearly labelled control group.

### 3.1 Primary action

| Run state | Primary action |
|---|---|
| BLOCKED_BEFORE_START | Review blocker |
| QUEUED | View queue position |
| RUNNING | Pause after current test |
| PAUSED | Resume execution |
| STOP_REQUESTED | View stop progress |
| Terminal | Open execution report |

### 3.2 Secondary controls

- Stop gracefully.
- Cancel now.
- Emergency stop.
- Download live logs.
- View execution contract.
- View audit trail.

A destructive action requires reason entry and confirmation. The UI must wait for backend acknowledgement before changing the lifecycle badge.

---

## 4. Suite progress and status command strip

The summary strip is the main visual anchor.

### 4.1 Required elements

- Overall suite completion percentage.
- Completed test count / total count.
- Horizontal progress rail segmented by final result.
- Interactive status cards:
  - Passed
  - Failed
  - Inconclusive
  - Blocked
  - Running
  - Queued
  - Skipped, when non-zero
- Parallel runners in use / allowed.
- Queue depth.
- Evidence captured / mandatory evidence expected.
- Environment readiness indicator.
- Plain-English operational message.

### 4.2 Interaction

Selecting a status card filters the central matrix and visually marks the filter as active. Multiple status cards may be selected. `Clear filters` restores the complete suite.

### 4.3 Count reconciliation

```text
Total = Final results + Active lifecycle items + Queued/Pending items
```

The API must provide a reconciliation flag. If counts do not reconcile, display `Status data delayed` rather than showing a false total.

---

## 5. Left panel — suite structure and saved views

Width: 260–300px, collapsible but not hidden by default.

### 5.1 Content

- Search by Test Case ID, objective, application or error text.
- Saved views:
  - All tests
  - Needs attention
  - Running now
  - Failed or inconclusive
  - Blocked by dependency
  - High / very critical
- Suite hierarchy:
  - suite folder / business journey;
  - application or channel grouping;
  - test case count;
  - live progress count;
  - worst active status.
- Framework filter.
- Application filter.
- Priority filter.

### 5.2 Hierarchy example

```text
Postpaid Order-to-Activation Suite v7.4
├── Customer and Account        38 / 38 complete
├── Order Capture               27 / 46 complete
│   ├── CRM Web                 18 / 28 complete
│   └── Dealer Portal            9 / 18 complete
├── Billing                      8 / 31 complete
├── Provisioning                 0 / 44 complete
└── Notification                 0 / 45 complete
```

Selecting a node filters the central matrix without changing the run.

---

## 6. Center panel — virtualized test execution matrix

This is the primary work surface and must support thousands of rows.

### 6.1 Required columns

| Column | Purpose |
|---|---|
| Order | Suite execution sequence / dependency order |
| Test Case | ID and concise objective |
| Journey / Application | Business and system context |
| Priority | Very Critical, Critical, High, Medium, Low |
| Framework | Playwright, Katalon, Appium, Selenium |
| Runner | Worker/device/browser identity |
| Lifecycle | Queued, Starting, Running, Paused, Completed, etc. |
| Result | Pending, Pass, Fail, Inconclusive, Blocked, Skipped |
| Step progress | e.g. `6 / 14` with compact progress rail |
| Attempt | Current attempt / total attempts |
| Duration | Live or final duration |
| Evidence | Captured / required count |
| Attention | Error, dependency or policy indicator |

### 6.2 Row behaviour

- Single click selects the test and updates the right inspector.
- Double click opens a full test-run detail drawer, not a new browser page.
- Running row receives a restrained blue highlight and animated progress indicator.
- Failed, inconclusive and blocked rows show the exact reason in a tooltip and inspector.
- Table header and Test Case column remain sticky.
- Sort is allowed only where it does not imply a change to execution order.
- The original suite order is always recoverable with `Reset order`.

### 6.3 Bulk actions

No bulk result editing is permitted. During a live run, allowed bulk actions are limited to filtering, copying identifiers and exporting the visible list.

---

## 7. Right panel — selected test inspector

Width: 360–420px. The inspector changes context without leaving the suite.

### 7.1 Test identity

- Test Case ID and objective.
- Requirement / journey link.
- Automation Asset ID and approved version.
- Framework and repository commit / artifact hash.
- Environment and test-data binding.
- Lifecycle and result shown separately.
- Attempt and retry reason.

### 7.2 Current execution

- Current step number / total.
- Step action and expected result.
- Actual action state.
- Step elapsed time.
- Current application/page/screen.
- Runner, browser/device and session ID.
- Live screenshot or trace preview where supported.

### 7.3 Assertion summary

- Mandatory assertions passed / total.
- Failed assertion with expected and actual value.
- Pending assertion count.
- Assertion source: UI, API, DB, OMS, billing, provisioning or network.

### 7.4 Evidence summary

- Evidence captured / mandatory count.
- Screenshot, video, trace, log, API, database and telecom backend artifacts.
- Evidence quorum status.
- `Open evidence drawer` action.

### 7.5 Live event timeline

The latest events are shown in reverse chronological order with timestamps:

- step started;
- assertion evaluated;
- evidence stored;
- retry started;
- runner warning;
- result finalized.

---

## 8. Bottom live operations bar

Always visible and compact.

Required indicators:

- Parallel workers: active / capacity.
- Queued items.
- Browser/device sessions.
- Environment health.
- Evidence upload queue.
- Event stream latency.
- Last backend event time.
- Auto-scroll state.

Selecting an indicator opens a focused popover; it must not navigate away from the run.

---

## 9. Execution control semantics

### 9.1 Pause after current test

- Prevent dispatch of new test cases after current safe boundaries.
- Do not claim to suspend an arbitrary in-flight browser command.
- Persist reason and checkpoint.
- Current test cases either complete or follow framework-specific safe-stop rules.

### 9.2 Resume

- Continue dispatch from the next eligible item.
- An interrupted test creates a new immutable attempt if rerun is required.
- Previous attempt and evidence remain unchanged.

### 9.3 Stop gracefully

- Complete current safe unit.
- Dispatch no new work.
- Finalize available results and evidence.
- Final lifecycle: `STOPPED` unless a stronger terminal classification is already valid.

### 9.4 Cancel now

- Terminate runners and queued work.
- Release devices and reserved test data.
- Retain partial evidence.
- Final lifecycle: `CANCELLED`.

### 9.5 Emergency stop

- Permission controlled.
- Invokes project/global kill path.
- Requires reason and audit.
- Must show affected runners and cleanup result.

---

## 10. Empty, delayed and error states

### No events yet

`The run is ready. Waiting for the first runner event.`

### Reconnecting

Show last known data with a visible stale-data timestamp. Do not zero counts.

### Delayed stream

`Live updates are delayed by 18 seconds. Execution continues in the backend.`

### Runner/system error

Separate the infrastructure lifecycle error from the test result. A system error must not become an application FAIL automatically.

### Large-suite loading

Render skeleton rows only for missing pages. Preserve loaded status counts and selected test context.

---

## 11. API contract summary

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/automation/executions/{runId}` | Run identity, state and immutable contract summary |
| GET | `/api/automation/executions/{runId}/summary` | Reconciled status counts and suite progress |
| GET | `/api/automation/executions/{runId}/items` | Cursor-paginated test execution matrix |
| GET | `/api/automation/executions/{runId}/items/{itemId}` | Selected test details |
| GET | `/api/automation/executions/{runId}/items/{itemId}/steps` | Step and assertion timeline |
| GET | `/api/automation/executions/{runId}/items/{itemId}/evidence` | Evidence metadata |
| GET | `/api/automation/executions/{runId}/events?after={sequence}` | Missed live events |
| WS/SSE | `/api/automation/executions/{runId}/stream` | Live ordered event stream |
| POST | `/api/automation/executions/{runId}/controls` | Pause, resume, stop, cancel, emergency stop |

### Control request

```json
{
  "action": "PAUSE_AFTER_CURRENT",
  "reason": "CRM maintenance window started",
  "expectedRunVersion": 37
}
```

### Control response

```json
{
  "commandId": "CMD-10482",
  "accepted": true,
  "currentState": "PAUSE_REQUESTED",
  "runVersion": 38
}
```

---

## 12. URL state

The following filters must be reflected in the query string:

- selected test item;
- status filters;
- suite folder;
- application;
- framework;
- priority;
- search term.

A copied link must reopen the same filtered view subject to permissions.

---

## 13. Accessibility and keyboard behaviour

- `j/k` or arrow keys move through visible test rows when the matrix is focused.
- `Enter` opens selected details.
- `Esc` closes drawer/popover.
- Status chips have accessible labels containing status and count.
- Animated running indicators respect reduced-motion preferences.
- Destructive controls require keyboard-accessible confirmation.

---

## 14. Acceptance criteria

1. The screen shows suite, run and immutable snapshot identity.
2. Suite progress and every status count reconcile with the backend.
3. Lifecycle and result are presented separately.
4. Selecting a status card filters the matrix.
5. Search and filters work on large suites and persist in the URL.
6. The suite tree, matrix and inspector preserve a single run context.
7. Selecting a test displays real steps, assertions and evidence.
8. Live events reconnect without losing or duplicating events.
9. Pause, resume, stop, cancel and emergency stop wait for backend acknowledgement.
10. Partial evidence remains visible after stop, cancel or system error.
11. No test is marked PASS because only the UI step succeeded.
12. Missing mandatory evidence remains visible and can lead to INCONCLUSIVE.
13. The screen remains usable with 10,000 test items.
14. Secrets and sensitive test data are masked.
15. Terminal completion exposes `Open execution report` and routes to UI-052.
