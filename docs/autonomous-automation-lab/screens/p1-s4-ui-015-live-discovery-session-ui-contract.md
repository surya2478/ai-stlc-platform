# P1-S4 UI-015 Live Discovery Session UI Contract

## Document control

| Field | Value |
|---|---|
| Screen ID | UI-015 |
| Phase | Phase 1 - Foundation |
| Section | P1-S4 Application Discovery |
| Screen name | Live Discovery Session |
| Parent area | Application Discovery |
| Proposed route | `/automation?project={projectId}&view=discovery&application={applicationId}&environment={environment}` |
| Contextual entry | UI-014 Application Registry, UI-012 Journey Graph, UI-013 Test Case Approval and AI Automation Studio |
| Previous screen | UI-014 Application Registry |
| Next screen | UI-016 Application Model |
| Existing baseline | Project applications/environments, Playwright MCP discovery agent, readiness service, agent-run events and locator-map persistence |
| Reference image | `docs/autonomous-automation-lab/screens/Live Discovery Session.png` (revision pending file replacement — see Section 25) |
| Implementation status | `REFERENCE_IMAGE_APPROVED_READY_FOR_IMPLEMENTATION` |

## 1. Purpose

Live Discovery Session is the governed workspace for observing and recording a real application so that automation is grounded in captured application evidence rather than guessed selectors, routes, screens, APIs or behaviour.

The screen must let an authorized tester:

- select a registered application and governed environment;
- choose Guided User, Free User-Action or supervised Agent-Driven discovery;
- pass deterministic readiness checks before starting;
- observe the current browser, device or AVD state;
- capture structured actions, DOM/accessibility structure, screenshots, network/API events, console events and timing evidence;
- pause, checkpoint, resume, stop, cancel or emergency-stop safely;
- review captured screens, elements, actions and blockers;
- create a versioned draft Application Model for UI-016;
- preserve a complete, immutable session and tool-call audit trail.

Video may be captured as supporting evidence when policy allows it, but structured events and application evidence are the primary source of truth.

## 2. Reuse and extension rule

UI-015 must extend the existing discovery foundation rather than introduce an unrelated browser automation stack.

Existing reusable backend capabilities:

- discovery trigger: `POST /api/v1/automation/agent/discover-ui`;
- discovery agent: `backend/app/agents/automation/mcp_discovery_agent.py`;
- isolated browser session: `backend/app/agents/automation/mcp_session.py`;
- readiness checks: `backend/app/services/automation_runner/readiness.py`;
- locator persistence: `backend/app/services/locator_map_service.py`;
- project application/environment source: `ProjectApplication` and project-application APIs;
- agent execution/progress foundation: `AgentRun`, Celery task dispatch and agent-run logs;
- current captured baseline: accessibility snapshots, ranked interactive elements, page URLs/titles, locator recommendations and live automation blockers;
- validation adapter/MCP registry: `MCPConnection` (`backend/app/models/mcp_connection.py`) and its `capability_key` column, project-scoped connection status (`connected`/`not_configured`/`error`), and `backend/app/services/test_classification/capability_resolver.py`'s resolution pattern — added for Test Automation Classification & Routing and directly reusable here. UI-015's "Validation Adapters / MCPs" panel and "System Validations" tab must resolve against these same real, project-scoped `MCPConnection` rows rather than a second registry; a validator with no matching `capability_key` in the project is `UNSUPPORTED`/`NOT_CONFIGURED`, never fabricated as connected.

Existing behavior is not sufficient for the complete UI-015 contract. The current discovery endpoint is a queued, bounded, headless agent run driven by selected test cases. It does not yet provide:

- persisted interactive discovery-session state;
- Guided User or Free User-Action recording;
- pause/resume/checkpoint/emergency-stop commands;
- live preview/control streaming;
- complete DOM/mobile/WebView/network/API/console/timing capture;
- session action editing or approval;
- versioned Application Model draft publication.

The UI must not display those capabilities as operational until their backend contracts and persistence exist.

## 3. Navigation and context preservation

Required entry behavior:

- UI-014 `Start Discovery` passes stable `project`, `application` and `environment` context.
- UI-012/UI-013 contextual entry also passes journey/test-case identifiers when present.
- Direct navigation without an application or environment opens the configuration state and requires explicit selection before readiness evaluation.
- Application selection uses stable registry IDs, never a hard-coded name list.
- Changing project clears application, environment, auth-profile and test-context selections that do not belong to the new project.

### 3.1 Test-case selection and upstream handoff

The test case shown in the Live Discovery Session must never be hard-coded.

Supported selection sources:

1. **UI-013 Test Case Approval** — `Send to Discovery` opens UI-015 with the approved test case preselected.
2. **UI-012 Journey Graph** — starting discovery from a journey/test node passes the selected journey and test-case context.
3. **UI-014 Application Registry** — `Start Discovery` passes the application/environment, then UI-015 requires the user to select an eligible test case for Guided or Agent-Driven mode.
4. **Direct UI-015 entry** — the session configuration panel presents an empty searchable Test Context selector.

The selector must search/filter by:

- Test Case ID and title
- Requirement ID and PPM ID
- Journey and scenario
- Application
- Test type / scenario class
- Approval status
- Discovery eligibility

Eligible test cases for Guided or Agent-Driven mode must:

- belong to the active project;
- be approved through UI-013;
- have a valid requirement/scenario/journey relationship where required;
- be mapped to the selected stable Application Registry ID;
- have no unresolved mandatory application-mapping blocker;
- be compatible with the selected environment/adapter;
- satisfy configured discovery policy and permissions.

Ineligible rows remain inspectable but cannot be selected. The selector must show the exact blocking reason and provide contextual navigation to Test Case Approval, Journey Graph or Application Registry.

A live discovery session has exactly one primary test case. If a user selects multiple test cases upstream, UI-015 creates a discovery queue and starts a separate session per test case; it must not merge unrelated steps and evidence into one session.

Mode rules:

- **Guided User Recording:** one approved eligible test case is mandatory.
- **Agent-Driven Recording:** one approved eligible test case is mandatory and its approved steps are immutable during execution; corrections create reviewed capture changes.
- **Free User-Action Recording:** test case is optional. The session purpose is mandatory, and captured actions may be mapped to a test case during review before publication.

Once a session reaches `INITIALISING`, the primary test case is locked. Changing it requires cancelling/stopping the current session and creating a new session so evidence lineage remains deterministic.

Required onward navigation:

- `Review Application Model` opens UI-016 with the completed session/model version.
- `Open API & Network Explorer` opens UI-017 with the selected session and captured request context.
- `Return to Registry` preserves project and application filters in UI-014.

## 4. Header

Required content:

- Breadcrumb: `e& STLC / Application Discovery / Live Discovery Session`
- Title: `Live Discovery Session`
- Badge: `P1-S4 UI-015`
- Subtitle: `Observe, record and ground application behaviour with governed evidence.`
- Inherited project selector and Jira sync state
- Application selector
- Environment selector
- Mode selector
- Test Context selector before session start; read-only Test Case ID/title chip after start
- Session ID when a session exists
- Live state badge
- Last event / connection timestamp
- `Session History`
- `Open Application Model`
- Permission-aware primary session action (`Start`, `Resume` or `Review Capture` according to state)

Header state and controls must reflect persisted backend session state, not local browser assumptions.

## 5. Discovery modes

The screen supports exactly three governed modes.

### 5.1 Guided User Recording

- Default Phase 1 mode.
- User follows approved test/journey steps.
- The system records structured actions and evidence.
- Current approved step, expected application state and evidence requirement remain visible.
- User may mark a step complete, add a note, identify an unexpected state or request remapping.
- Publication requires mapping and review completion.

### 5.2 Free User-Action Recording

- Used for reverse engineering, undocumented flows and reusable component discovery.
- User actions are captured without an approved step plan.
- Session must record the purpose and application scope before starting.
- Captured actions cannot be published into approved automation until test design, intent, mapping, assertions and independent review are complete.

### 5.3 Supervised Agent-Driven Recording

- Agent operates from approved test steps within configured allowed hosts and tools.
- Initially supervised.
- User can approve the next action, modify it, skip it, pause, take manual control, roll back, stop or emergency-stop.
- Agent tool access is revoked while paused and immediately on emergency stop.
- The agent may not approve or publish its own output.

Mode cannot be silently changed during an active session. A mode change requires stopping or creating a new session.

## 6. Session configuration panel

Before session creation, show a compact configuration panel containing:

- Project
- Registered application and stable application ID
- Environment and governed base URL
- Browser, device or AVD target
- Framework/adapter
- Discovery mode
- Test Context selector showing Test Case ID, title, Requirement ID/PPM ID, journey, approval and eligibility
- Approved authentication profile reference
- Journey, scenario and test-case context where applicable
- Starting URL or screen derived from the governed environment
- Test-data lease/reference when required
- Evidence policy
- Capture options
- Allowed host list
- Session purpose and notes

Rules:

- Credentials, passwords, OTP values, tokens and storage-state contents are never displayed.
- Starting URL must belong to the selected application/environment or an explicitly approved allowed host.
- Application, environment, auth-profile, test data and test context must belong to the active project.
- Agent-Driven mode requires eligible approved steps and agent policy.
- Guided mode requires one approved, application-mapped and discovery-eligible test case.
- Free mode may start without a test case but must record a purpose and cannot publish unmapped actions.
- Free mode requires a recorded purpose.
- Unsupported browser/device/AVD combinations are blocked by backend validation.

### 6.1 Test Context selector interaction

Before a session starts, display a visible `Test Context` control in the context/configuration area. It must not be represented only by static text in the left step panel.

Recommended compact presentation:

- label: `Test Context`;
- selected value: `TC-03428 · Cancel order before payment`;
- secondary line/chips: `REQ-0023`, `PPM-4589`, `JRN-001`, `Approved`, `Discovery Eligible`;
- `Change` action while the session is still `NOT_STARTED`;
- lock icon and `View Test Case` action after the session starts.

Opening the selector shows a searchable table/drawer with:

- TC ID
- Title
- Requirement / PPM ID
- Journey / Scenario
- Application mapping
- Approval status
- Discovery eligibility
- Blocking reason
- Select action

Selection is persisted by the backend session-creation request. A frontend-only selected test case is not sufficient.

## 7. Readiness gate

Starting or resuming requires a persisted readiness evaluation.

Required checks:

1. Application registration is active and discovery-eligible
2. Environment URL exists and is reachable
3. Selected browser/device/AVD capability is available
4. Approved authentication profile is configured when login is required
5. Test data is present or a valid lease is active when required
6. Required API dependencies are healthy
7. Database validation endpoint is reachable when required
8. Browser/adapter dependencies are installed
9. Environment is not under maintenance
10. Allowed-host and security policy validation passes
11. Evidence storage is writable and within managed workspace boundaries
12. User permission and project membership are valid
13. Guided/Agent-Driven test case is approved, application-mapped and discovery-eligible
14. Every validation adapter/MCP declared mandatory by the resolved automation classification (or by project/application policy when no classification exists) is connected and healthy

Check 14 resolves against the same real `MCPConnection` registry described in Section 2 — the specific
adapters shown (e.g. an "Event / Kafka" or "CRM MCP" row) are whatever the project has actually
registered and whatever the current session's application/journey/classification declares as
required, never a fixed list. A mandatory adapter that is `not_configured` or `error` is a `Blocked`
readiness result, not a warning; an optional adapter in that state is a `Warning`.

The gate displays live `Passed`, `Warning`, `Blocked` or `Not Evaluated` results with exact backend detail.

No session can start while a mandatory check is blocked. Warnings require an explicit, audited acknowledgment only where policy allows it.

## 8. KPI/status cards

Use six compact cards backed by session data:

1. **Session State** — persisted state and elapsed duration
2. **Screens Discovered** — unique screens/pages captured
3. **Elements Captured** — unique structured elements
4. **Actions Recorded** — included actions versus excluded/paused actions
5. **Network / API Events** — captured requests and validation issues
6. **Evidence & Blockers** — evidence completeness and open blockers

No illustrative totals, percentages or timestamps are permitted.

The revised reference image shows the readiness strip (Section 7, expanded to the per-check card
layout with a Readiness Score gauge) occupying this top band instead of the six KPI cards, and
keeps it visible for the whole session lifecycle rather than only pre-start. Both requirements
stand: the readiness strip is promoted to persistent, always-visible top placement (superseding
the "compact strip above session controls" wording in Section 21), and the six KPI cards move to
the Session Inspector's Live State tab (Section 11.3) as a persisted session summary once
`RECORDING` begins, rather than staying in the top band. Confirm this placement during the first
implementation review before treating it as final.

## 9. Persisted session state machine

Required states:

`NOT_STARTED`, `INITIALISING`, `RECORDING`, `PAUSE_REQUESTED`, `PAUSED`, `RESUMING`, `STOP_REQUESTED`, `STOPPED`, `COMPLETED`, `CANCELLED`, `FAILED`, `EMERGENCY_STOPPED`.

Required state behavior:

| Current state | Allowed primary operations |
|---|---|
| `NOT_STARTED` | Configure, validate readiness, start, cancel draft |
| `INITIALISING` | View progress, cancel, emergency stop |
| `RECORDING` | Pause, checkpoint, stop, emergency stop; agent supervision controls by mode |
| `PAUSE_REQUESTED` | Wait for safe checkpoint, emergency stop |
| `PAUSED` | Inspect, edit notes, validate resume state, resume, stop, cancel, emergency stop |
| `RESUMING` | View validation/progress, stop, emergency stop |
| `STOP_REQUESTED` | Wait for safe stop/checkpoint, emergency stop |
| `STOPPED` | Review capture, resume if eligible, complete, cancel |
| `COMPLETED` | Review, compare, create/update model draft, export evidence |
| `CANCELLED` | Read-only audit and preserved safety evidence |
| `FAILED` | Read error, inspect evidence, retry through a new/eligible transition |
| `EMERGENCY_STOPPED` | Read-only safety/audit review; explicit authorized recovery creates a new session |

Invalid transitions return a structured backend conflict and do not mutate state.

Pause, resume, stop, cancel and emergency stop must be idempotent.

## 10. Primary session controls

Required controls according to state and mode:

- Start
- Pause
- Resume
- Stop
- Save Checkpoint
- Complete Session
- Cancel / Discard
- Emergency Stop
- Approve Next Action — Agent-Driven only
- Modify Next Action — Agent-Driven only
- Skip Next Action — Agent-Driven only, reason required
- Take Manual Control — Agent-Driven only
- Return Control to Agent — only after readiness/state validation
- Roll Back to Checkpoint — Agent-Driven only, confirmation and reason required

Rules:

- Pause is acknowledged only after a checkpoint is persisted.
- No agent tool call may continue after pause acknowledgment.
- Actions performed while paused are excluded by default and visually identified.
- Stop saves a reviewable capture; it does not approve, publish or execute automation.
- Cancel preserves audit/safety evidence but marks incomplete capture as not publishable.
- Emergency Stop immediately revokes agent/tool access and preserves current evidence.
- Destructive or irreversible commands require confirmation and an audited reason.

## 11. Main live workspace

Use a dense three-region desktop layout that fits the approved viewport.

### 11.1 Left panel — step plan and session timeline

For Guided and Agent-Driven modes:

- Journey/scenario/test-case identity
- Approved preconditions
- Ordered test steps
- Current step
- Expected application transition
- Required evidence per step
- Step state: pending, active, captured, needs mapping, skipped, blocked or failed
- User/agent ownership marker
- Notes, corrections and checkpoints

For Free mode:

- Session purpose
- Chronological structured action timeline
- Detected screens and transitions
- Unmapped actions
- Suggested reusable components

The timeline must distinguish observed application events from agent recommendations and user corrections.

### 11.2 Center panel — live target view

Required presentation:

- Current browser/device/AVD viewport or policy-approved live preview
- Current URL/screen and title
- Connection/live-state indicator
- Viewport/device dimensions
- Screenshot capture control
- Element highlight/selection mode
- Current action indicator
- Redaction/masking indicator
- Zoom/fit controls
- Read-only mode while paused unless manual inspection is explicitly allowed

The frontend must not simulate a live target with a static image. If live preview streaming is unavailable, show the latest timestamped captured screenshot with an explicit `Latest capture — not live` label.

### 11.3 Right inspector — captured evidence and state

Required tabs:

- Live State
- DOM / Accessibility
- Elements
- Network / API
- System Validations
- Console / Timing
- Evidence
- Activity / Audit
- Notes

#### Live State

- Current URL/screen
- Authentication/session state classification
- Current user/test-data context where policy permits
- Application/build/environment identifiers
- Active WebView/frame/window/mobile context
- Readiness and resume-state classification
- Current checkpoint

#### DOM / Accessibility

- Captured DOM metadata when available
- Accessibility tree
- Mobile hierarchy / WebView tree when applicable
- Selected node details
- Stable attributes and semantic role/name
- Sensitive-value masking
- Snapshot timestamp and provenance

#### Elements

- Element name and business meaning
- Role, accessible name and type
- Recommended locator and strategy
- Locator confidence
- Alternative/fallback locator where persisted
- Screen/component association
- Used-by action/test references
- Validation result and ambiguity issues

#### Network / API

- Method, sanitized URL, status and duration
- Request/response content type and schema references
- Screen/action correlation
- Mock/sandbox/dependency classification
- Failed requests and policy violations
- `Open in API & Network Explorer` action to UI-017

Secrets, authorization headers, cookies, tokens and prohibited payload fields must be removed before persistence or display.

#### System Validations

Deterministic cross-system business-state validation, distinct from the raw HTTP/API log in the
Network / API tab — this tab answers "did the domains this journey touches actually reach the
expected state", not just "did a request succeed".

- Validation summary counts: Total, Passed, Failed, Inconclusive, Blocked, sourced from persisted
  validation results for the current session, never computed client-side from unrelated data.
- A table of individual validation results, one row per system/MCP check that ran or was expected
  to run for the current step/action, with columns:
  - System / MCP — the validator's `capability_key` and display name, resolved from the project's
    `MCPConnection` registry (Section 2); never a hard-coded system name.
  - Expected — the business-state assertion the classification/policy or step declared (e.g. an
    order status, a charge state, an event-publication fact).
  - Actual — the value the validator actually observed.
  - Result — `Passed`, `Failed`, `Inconclusive` or `Blocked`.
  - Evidence — link/reference to the persisted evidence record backing this result (raw
    request/response, DB row snapshot, consumed event payload, etc.), sanitized per Section 16.
- A blockers sub-list surfacing any `Failed`/`Blocked` row with its detail and timestamp, feeding
  the same blocker concept used in the KPI cards (Section 8) and completion gate (Section 15).
- Rows for validators that are configured but not yet evaluated for the current step show
  `Not Evaluated`, not a fabricated status.
- If a mandatory validator is `not_configured`/`error` in the `MCPConnection` registry, its row
  shows `Blocked` with that exact reason — never silently omitted or downgraded to optional,
  matching the same non-negotiable rule already enforced for automation classification
  (`docs/test-automation-classification-routing-implementation-prompt.md`).

#### Notes

- Free-text session notes and step-level annotations added by the user during Guided, Free or
  Agent-Driven capture (the `Add Note` control in Section 10/11.2).
- Each note persists actor, timestamp, associated step/action/checkpoint reference when
  applicable, and is included in the immutable audit trail (Activity / Audit tab, Section 17
  Session Transition Event where relevant).
- Notes are informational only — they do not change session state, readiness or validation
  results.

#### Console / Timing

- Console severity and sanitized message
- Page errors and unhandled exceptions
- Navigation and resource timing
- Slow interactions and timeouts
- Correlated screen/action/checkpoint

#### Evidence

- Screenshots
- DOM/accessibility snapshots
- Network/API logs
- Console logs
- Trace references
- Optional video reference
- Capture timestamp, source and checksum
- Evidence policy/completeness status
- Redaction outcome

#### Activity / Audit

- Session transitions
- User, agent and system actions
- Tool calls with sanitized arguments/results
- Checkpoints
- Corrections, exclusions and skips
- Control handoffs
- Errors and recovery decisions
- Actor, timestamp, reason, policy and correlation ID

### 11.4 Validation adapters / MCPs strip

A persistent, compact strip below the live workspace (not inside the right inspector) showing
every validation adapter/MCP connected to the current project, each as a small card with:

- adapter/MCP display name and `capability_key`;
- category icon (browser/web discovery, API/REST/SOAP, database, domain business system, event
  broker, etc.) sourced from the `MCPConnection.connection_type`, never inferred from the name;
- live connection status (`Connected`, `Not Configured`, `Error`/`Warning`), reflecting
  `MCPConnection.status` and `last_checked_at` — not a static badge;
- a `Configure` / `Add Adapter` action that deep-links into the existing MCP Connections
  management surface (`frontend/src/components/playwright-studio/McpConnectionsPanel.tsx` /
  `/api/v1/mcp-connections`) rather than duplicating adapter CRUD inside UI-015.

This strip is read-only status — adapter registration, credentials and health-check configuration
remain owned by the existing MCP Connections management screen. UI-015 only surfaces status and
routes users there to fix a gap; it must not grow its own adapter-editing UI.

## 12. Resume-state validation

Before resuming a paused or stopped eligible session, classify the current application state as:

- `UNCHANGED`
- `NAVIGATION_CHANGED`
- `SESSION_EXPIRED`
- `DATA_CHANGED`
- `APPLICATION_RESTARTED`
- `UNKNOWN`

The user must be offered only backend-approved recovery options:

- Continue
- Restore checkpoint
- Remap current screen/action
- Restart current step
- Stop and save

The system must not blindly resume when URL/screen, authentication, selected customer, order state, build, environment health, data lease or AVD connectivity has changed.

## 13. Captured-action contract

Each structured action must persist:

- stable action ID and sequence;
- session ID and mode;
- actor: user, agent or system;
- related test step/journey node when applicable;
- action family: navigate, click, input, select, upload, download, wait, read, API, database validation, window/frame/context switch or mobile gesture;
- semantic target and stable screen/component/element references when resolved;
- sanitized input binding, never raw secrets;
- pre-action and post-action application state;
- timestamp and duration;
- evidence references;
- locator evidence and confidence;
- included, excluded, corrected, skipped or rolled-back state;
- issue/blocker and reviewer notes;
- provenance and tool-call reference.

Raw pointer/keyboard events may support interpretation but cannot replace the structured action record.

## 14. Session queue/history

Below the live workspace, or in a dedicated history drawer, provide a compact session table.

Required columns:

- Session ID
- Application
- Environment
- Mode
- Journey / Test Context
- State
- Screens
- Actions
- Evidence Coverage
- Open Blockers
- Owner
- Started At
- Updated At
- Actions

Required filters:

- Application
- Environment
- Mode
- State
- Owner
- Date range
- Has blockers
- Model publication state

Selecting a completed session opens a read-only inspector and comparison/navigation controls.

## 15. Completion and publication gate

Completing a session requires:

- terminal-safe session state;
- at least one valid captured screen/page;
- structured actions where the mode requires them;
- evidence stored successfully;
- unresolved sensitive-data violations equal zero;
- mandatory step/evidence coverage evaluated;
- ambiguous application/screen/element mappings explicitly identified;
- open blockers recorded;
- session summary generated from persisted capture data;
- user confirmation for Free and Guided capture completion;
- agent output remains unapproved until independent review.

Completion creates or updates a **draft** Application Model version for UI-016. It does not automatically approve or publish the model.

## 16. Privacy and security

Required controls:

- Mask password, OTP, payment-card, PII, financial and secret fields.
- Redact configured screenshot/video regions.
- Support secure-input semantic actions.
- Suppress prohibited evidence by project policy.
- Store authentication profile references only.
- Enforce allowed hosts and reject cross-host navigation unless explicitly approved.
- Fence captured page/DOM/accessibility/network content as untrusted data for every agent/LLM prompt.
- Prevent prompt injection from changing agent tools, role, policy or allowed targets.
- Keep session artifacts under the managed workspace/storage root.
- Enforce project authorization on every session, command, event and artifact.
- Audit all session controls and agent tool calls.
- Never expose secrets in logs, network payload previews, screenshots or exports.

## 17. Data and backend delta

UI-015 requires persisted entities or equivalent versioned records for:

### Discovery Session

- stable session ID;
- project, application and environment IDs;
- mode and persisted state;
- browser/device/AVD/framework target;
- auth-profile reference;
- mandatory primary `test_case_id` for Guided/Agent-Driven mode and optional `test_case_id` for Free mode;
- requirement, PPM, journey and scenario context resolved server-side from the selected test case;
- purpose, evidence policy and allowed hosts;
- owner and active controller;
- timestamps, terminal reason and failure details;
- latest checkpoint and draft model version;
- correlation and agent-run IDs.

### Discovery Action

- structured action contract from Section 13;
- sequence, inclusion and correction history;
- evidence and model-node links.

### Discovery Checkpoint

- session/state/action position;
- sanitized URL/screen/application state;
- browser/device/AVD session reference;
- evidence snapshot;
- resumability and expiry metadata.

### Discovery Capture / Artifact

- capture type;
- storage reference and checksum;
- screen/action/checkpoint correlation;
- source/tool and timestamp;
- sanitized metadata;
- redaction and retention state.

### Session Transition Event

- actor and previous/new state;
- command, reason and timestamp;
- current step/node/action;
- checkpoint/evidence reference;
- idempotency key and correlation ID.

### Application Model Draft Link

- source session;
- model/version ID;
- extraction/build status;
- open mapping issues;
- reviewer and approval state.

### System Validation Result

- session ID and correlated step/action ID;
- validator `capability_key` and resolved `MCPConnection` ID (Section 2);
- expected value/assertion source (classification requirement, policy rule or manual step);
- actual observed value;
- result: `passed` / `failed` / `inconclusive` / `blocked` / `not_evaluated`;
- evidence reference (sanitized, Section 16);
- timestamp and duration;
- correlation ID.

## 18. Required API capabilities

Exact URLs may follow existing endpoint conventions, but the backend must expose equivalent project-scoped capabilities:

- create session and validate configuration;
- search/list eligible test cases for the selected project, application, environment and mode;
- list/filter sessions;
- get session detail;
- evaluate readiness;
- issue idempotent session commands;
- stream or poll persisted progress/events;
- read structured actions and captures;
- correct/include/exclude captured actions with audit history;
- read checkpoints and execute authorized recovery;
- retrieve sanitized artifacts;
- complete/cancel session;
- create/update draft Application Model;
- export sanitized session evidence;
- retrieve immutable activity/audit history;
- list the project's validation adapters/MCPs and live connection status (reuses the existing
  `MCPConnection`/`/api/v1/mcp-connections` registry — Section 2 — not a new endpoint family);
- read persisted System Validation Results for a session/step, and trigger a validator re-check
  where policy allows manual re-validation.

Suggested command shape:

`POST /api/v1/discovery/sessions/{sessionId}/commands`

with a typed command such as `start`, `pause`, `resume`, `checkpoint`, `stop`, `complete`, `cancel`, `emergency_stop`, `approve_next_action`, `take_manual_control`, `skip_action` or `rollback` and an idempotency key.

Do not implement critical lifecycle changes through frontend-only state.

## 19. Agent and adapter integration

- Existing `playwright_mcp_discovery` may be reused for bounded Agent-Driven web discovery after the session contract wraps it with persisted state, commands, progress and audit.
- Guided/Free capture requires a supported browser-side or runner-side recording adapter; do not infer actions from video alone.
- Mobile/Appium and UiPath capabilities must be maturity-labelled until real adapters exist.
- Every adapter declares supported capture types, controls and limitations.
- Agent tools receive only authorized project/application/environment context and time-bound secret references.
- Maximum exploration depth, links, actions, duration, tokens and cost are policy controlled.
- Stopping conditions, failure route and escalation are explicit.

## 20. Loading, empty, disconnected and error states

- Loading never shows a fake browser/session or sample event stream.
- No-application state links to UI-014 Application Registry.
- No-environment state explains the missing registry configuration.
- Readiness-blocked state lists exact blockers and permitted remediation.
- Initializing state shows persisted progress and correlation ID.
- Disconnected preview distinguishes target disconnection from backend/stream disconnection.
- Worker/agent failure preserves captured evidence and a readable error.
- Session conflict shows current persisted state and refresh/recovery options.
- Permission loss switches to authorized read-only behavior and stops control actions.
- Expired authentication/test data/AVD sessions require readiness validation before recovery.

## 21. Visual contract

- Existing dark navy sidebar and white application shell
- Compact header/context selectors, including the Test Case selector field (Section 6.1)
- Persistent, always-visible readiness strip with per-check cards and a Readiness Score gauge,
  directly below the header (Section 7, Section 8 note)
- Six KPI/session-summary cards relocate into the Session Inspector Live State tab once recording
  begins (Section 8 note)
- Dense three-region live workspace
- A read-only Validation Adapters/MCPs status strip below the live workspace (Section 11.4)
- Fixed-width right inspector consistent with UI-007 through UI-013, including the System
  Validations tab (Section 11.3)
- Blue primary/active controls
- Emerald ready/recording/completed states
- Amber initializing/paused/warning states
- Red blocked/failed/emergency states
- Violet agent/model/discovery intelligence accents
- Clear live versus latest-capture labeling
- Critical controls remain visible without excessive vertical scrolling
- Main desktop experience fits the approved viewport without oversized gaps

## 22. Accessibility

- All controls are keyboard accessible.
- Live state changes are announced through a non-disruptive status region.
- State is not conveyed by colour alone.
- Emergency Stop has a clear accessible name and confirmation behavior appropriate to policy.
- Browser/device preview has a textual current-state alternative.
- Tree views support keyboard navigation and selected-node context.
- Focus returns predictably after dialogs and session commands.
- Reduced-motion preferences are respected for live indicators.

## 23. Acceptance criteria

- UI-015 follows UI-014 in the approved 58-screen order.
- Project, application and environment context is preserved from UI-014.
- Test Context is visibly selectable before start and is never hard-coded.
- UI-012/UI-013 upstream navigation preselects the real approved test case by stable ID.
- Guided and Agent-Driven sessions require exactly one eligible approved test case; Free mode permits an optional mapping.
- The primary test case is locked after initialization and persisted with all session/actions/evidence.
- Only registered stable application IDs and governed environment URLs are used.
- All three discovery modes follow their publication and supervision rules.
- Readiness blocks invalid session start/resume.
- The complete persisted state machine and idempotent controls are backend enforced.
- Pause persists a checkpoint and stops agent tool calls before acknowledgment.
- Emergency Stop revokes tool access and preserves safety evidence.
- Structured actions are the primary recording source; video is supporting-only.
- DOM/accessibility, element, screenshot, network/API, console/timing and audit capture are real or explicitly marked unsupported.
- Sensitive values are masked before persistence/display.
- Live preview is never simulated with an unlabeled static image.
- Agent-Driven discovery is supervised and cannot self-approve.
- Completed sessions create draft, not approved, Application Model versions.
- UI-016 and UI-017 navigation preserves session/model context.
- No static counts, names, timestamps, screenshots or activity events are presented as live data.
- Frontend typecheck/lint/build, focused backend tests, state-transition tests, security tests and authenticated browser validation pass.

## 24. Required test coverage

Backend:

- session creation validation and project isolation;
- every allowed and rejected state transition;
- idempotent pause/resume/stop/cancel/emergency commands;
- checkpoint-before-pause invariant;
- agent tool revocation on pause/emergency stop;
- readiness start/resume blocking;
- allowed-host and cross-project rejection;
- artifact path containment and sanitization;
- secret/PII masking;
- action correction/inclusion audit;
- draft model creation and no self-approval;
- permission and audit enforcement.

Frontend/live browser:

- configuration and readiness flows;
- Test Context search, eligibility/blocker display, upstream preselection and post-start locking;
- Guided, Free and Agent-Driven presentation differences;
- state-specific control enablement;
- live versus latest-capture labeling;
- inspector tabs and empty/error states;
- pause/resume/reconnect behavior;
- emergency-stop confirmation/result;
- UI-014, UI-016 and UI-017 navigation context;
- responsive overflow and keyboard accessibility.

## 25. Reference image gate

**Resolved 2026-07-23.** The original reference image displayed `TC-03428` as static Test/Journey
context with no visible selection or upstream-handoff mechanism. A revised image was supplied
showing Test Case promoted to a header-level field alongside Application/Environment/Auth
Profile/Mode. Decision: build the full interactive selector per Sections 3.1/6.1 (chips, `Change`
action pre-start, lock icon post-start) — the revised image is treated as showing the field's
resting/selected state, not a simplification of the interaction contract.

The revised image also introduced a "System Validations" inspector tab, a "Validation Adapters /
MCPs" status strip, and an expanded, always-visible readiness-check layout with a Readiness Score
gauge, none of which were in the original contract. This document has been updated to specify
all three (Sections 2, 7, 8, 11.3, 11.4, 17, 18, 21) rather than treating the image as
implementation-only guidance the text doesn't cover.

**Outstanding action:** the revised image was supplied inline in chat, not as a file — it has not
yet replaced `docs/autonomous-automation-lab/screens/Live Discovery Session.png` on disk. Save it
to that path before implementation so the reference image and this contract stay in sync.

Implementation status: `REFERENCE_IMAGE_APPROVED_READY_FOR_IMPLEMENTATION`
