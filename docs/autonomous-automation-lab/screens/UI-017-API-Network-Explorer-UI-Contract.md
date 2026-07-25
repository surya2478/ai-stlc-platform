# P1-S4 UI-017 API and Network Explorer UI Contract

## Document control

| Field | Value |
|---|---|
| Screen ID | UI-017 |
| Phase | Phase 1 — Grounded Web PoC |
| Section | P1-S4 Application Discovery |
| Screen name | API and Network Explorer |
| Parent area | Application Discovery |
| Proposed route | `/automation?project={projectId}&view=api-network&application={applicationId}&session={sessionId}` |
| Previous screen | UI-016 Application Model |
| Next screen | UI-018 Automation Workspace |
| Contextual entry | UI-015 Live Discovery Session, UI-016 Application Model, UI-012 Journey Graph, UI-013 Test Case Approval |
| Existing baseline | Playwright/network capture, discovery-session evidence, external-system validations, API relationships, application registry and artifact lineage |
| Reference image target | `docs/autonomous-automation-lab/screens/API_Network_Explorer.png` |
| Implementation status | `CONTRACT_DRAFT_PENDING_REFERENCE_IMAGE_APPROVAL` |

## 1. Purpose

API and Network Explorer is the governed workspace for reviewing, correlating and validating network activity captured during application discovery.

The screen must help authorized users understand:

- which UI action triggered which request;
- which API, service or external system processed it;
- whether request and response matched approved expectations;
- which business entities and test steps were affected;
- whether external-system evidence is complete;
- whether failures are application, integration, environment, data or validator failures;
- which relationships should be promoted into the Application Model and Automation IR.

The screen is an evidence explorer and validation workspace. It must not become an unrestricted API client or expose secrets.

## 2. Reuse and extension rule

Reuse existing UI-015 session context, UI-016 model nodes, browser/network captures, API validator results, external MCP results, application/environment registry, journey/test context, artifact lineage, RBAC, audit and feature flags.

Do not create a separate API catalogue disconnected from the Application Model.

PostgreSQL remains authoritative for metadata, correlations, review state and validation results. Large sanitized payloads remain in governed artifact storage.

## 3. Navigation and context preservation

- UI-015 `Open API & Network Explorer` preserves project, application, environment, session, test case, step/action and selected request.
- UI-016 may open UI-017 from a screen, element, journey, API node or external-system node.
- UI-012/UI-013 may open UI-017 filtered to journey, test case, step, expected API, missing validation or unresolved mapping.
- UI-017 links back to UI-015 and UI-016, onward to UI-018, and contextually to UI-012/UI-013.

## 4. Header

Required:

- Breadcrumb: `e& STLC / Application Discovery / API & Network Explorer`
- Title: `API & Network Explorer`
- Badge: `P1-S4 UI-017`
- Subtitle: `Correlate UI actions, APIs, external systems and evidence from governed discovery sessions.`
- Project selector
- Application selector
- Environment selector
- Discovery session selector
- Test context chip
- Request count
- Live/captured state badge
- Last event timestamp
- Refresh
- Export Evidence
- Open Application Model
- Permission-aware primary action: Validate Selected, Approve Mapping or Publish Relationship

Header values must come from persisted backend state.

## 5. KPI cards

Use six compact cards:

1. Requests Captured
2. APIs Identified
3. Validation Passed
4. Failures & Warnings
5. External Systems
6. Mapping Readiness

No illustrative counts are allowed.

## 6. Readiness and governance strip

Checks:

- discovery session authorized;
- network capture available;
- sanitization completed;
- secrets and prohibited headers removed;
- API validator configured where required;
- external MCPs available where required;
- request-to-action correlation available;
- application/model mapping available;
- evidence storage accessible;
- no unresolved sensitive-data violation;
- user permission valid.

Each check shows Passed, Warning, Blocked or Not Evaluated with exact backend detail.

## 7. Main layout

Use a dense four-region layout:

1. Left request/session navigator
2. Center request timeline and waterfall
3. Lower request/response detail area
4. Fixed right-side inspector

## 8. Left request navigator

Grouping:

- By Test Step
- By Screen
- By API
- By External System
- By Status
- By Validation Result
- By Time
- By Correlation ID

Controls:

- Search by URL, method, API name, system, step, request ID or correlation ID
- Method/status/system/request-type filters
- Validation-result filter
- Failures only
- Unmapped only
- External-system calls only
- Sensitive-data findings
- Clear filters

## 9. Center request timeline and waterfall

Show:

- chronological request sequence;
- UI action markers;
- page navigation;
- API calls;
- redirects and retries;
- websocket/event-stream activity;
- external-system validations;
- screenshots/checkpoints;
- errors and warnings.

Required lanes:

- UI Actions
- Browser Navigation
- API Requests
- External Systems
- Validators
- Evidence

Controls:

- Zoom and fit
- Jump to current step
- Selected request chain
- Correlation chain
- Retries
- Async callbacks
- External validation
- Export timeline

If only persisted data exists, label it `Captured timeline — not live`.

## 10. Request table

Columns:

- Timestamp
- Method
- Sanitized URL
- API name
- Status
- Duration
- Size
- Screen/action
- Test step
- Owning system
- Validation result
- Correlation ID
- Evidence state
- Mapping state
- Actions

Sensitive fields must never appear raw.

## 11. Request detail tabs

Tabs:

- Overview
- Request
- Response
- Headers
- Schema
- Timing
- Correlation
- Validation
- Evidence
- History

### Overview

Show request identity, method, sanitized URL, API/system, linked screen/action/test step, status, duration, capture source, correlation ID, validation result and mapping state.

### Request and Response

Show sanitized parameters/body previews, content type, schema reference, redaction summary and safe error summary.

### Headers

Show approved sanitized headers only. Never show authorization headers, cookies, tokens, session IDs, API keys or prohibited internal headers.

### Schema

Show request/response schema, required/optional fields, validation result, schema drift and contract version.

### Timing

Show DNS, connect, TLS, request, server wait, response, total duration, slow-call classification, retry and timeout details.

### Correlation

Show linked UI action, screen, journey node, test step, upstream/downstream requests, external-system checks, event/message correlation and trace ID where available.

### Validation

Show expected versus actual, schema validation, business assertion, external-system state, validator/MCP, deterministic outcome, blockers and evidence.

### Evidence

Show sanitized artifacts, API/external MCP evidence, traces, checksums, redaction and retention state.

### History

Show mapping changes, reviewer decisions, schema changes, validation history, linked model versions, actor and timestamp.

## 12. Right-side inspector

Tabs:

- Request Summary
- System Mapping
- Validation
- Evidence
- Gaps
- Activity

The inspector must show request context, API/system mapping, required adapters/MCPs, maturity state, deterministic validation, evidence, gaps and audit activity.

## 13. External systems and MCPs

Represent:

- Playwright MCP
- API Validator
- DB Validator
- CRM MCP
- OMS MCP
- Billing MCP
- Provisioning MCP
- Kafka/Event MCP
- Observability MCP
- other governed adapters

Each must show stable ID, type, required/optional state, capability maturity, availability, environment, authentication profile reference, latest validation, evidence and blockers.

Maturity values:

`REAL`, `MOCK`, `VIRTUALIZED`, `RECORDED`, `NOT_CONFIGURED`, `UNSUPPORTED`.

Mock or unavailable capabilities must never be presented as operational.

## 14. Validation outcomes

Use deterministic outcomes:

`PASSED`, `FAILED`, `BLOCKED`, `INCONCLUSIVE`, `ENVIRONMENT_FAILURE`, `DATA_FAILURE`, `AUTOMATION_FAILURE`, `POLICY_BLOCKED`, `NOT_APPLICABLE`.

AI may explain but cannot override deterministic outcomes.

## 15. Mapping actions

Permission-aware actions:

- Map API to Application Model
- Map request to screen/action/test step
- Assign owning system
- Assign external validator
- Mark validator required/optional
- Link schema
- Confirm correlation chain
- Add business assertion
- Add evidence requirement
- Mark request ignored
- Resolve gap
- Request rediscovery
- Approve/reject mapping
- Open source discovery session
- Open related model node
- Export sanitized evidence
- View audit log

Approved mappings are immutable in place.

## 16. Sensitive-data handling

- Strip authorization headers.
- Mask cookies, tokens, PII and payment data.
- Redact configured payload fields.
- Prevent prohibited payload persistence.
- Sanitize logs.
- Store secret references only.
- Block export when sanitization fails.
- Audit every export.

## 17. Publication to Application Model

UI-017 may publish reviewed relationships such as:

- Screen CALLS API
- Action TRIGGERS API
- API OWNED_BY System
- API VALIDATED_BY Validator
- API REQUIRES External System
- API HAS_SCHEMA Schema
- API HAS_EVIDENCE Evidence
- Request CORRELATES_WITH Test Step
- Request PRODUCES Event

Publication preserves source session, request/action IDs, evidence, reviewer, approval, model version, timestamp and correlation ID.

## 18. Data contract

```ts
type NetworkEventType =
  | "navigation"
  | "xhr"
  | "fetch"
  | "document"
  | "websocket"
  | "event_stream"
  | "resource"
  | "api_validation"
  | "external_validation";

type NetworkValidationOutcome =
  | "PASSED"
  | "FAILED"
  | "BLOCKED"
  | "INCONCLUSIVE"
  | "ENVIRONMENT_FAILURE"
  | "DATA_FAILURE"
  | "AUTOMATION_FAILURE"
  | "POLICY_BLOCKED"
  | "NOT_APPLICABLE";
```

Persist session/event identity, sanitized URL, timing, correlation, screen/action/test links, API/system/validator IDs, result, artifact references, evidence, mapping and review state.

## 19. Backend delta

Required structures:

- Network Capture Session Link
- Captured Network Event
- Sanitized Request Artifact
- Sanitized Response Artifact
- API Endpoint
- API Schema Reference
- Request Correlation
- External System Mapping
- Validator Requirement
- Validation Result
- Network Evidence Link
- Mapping Review/Approval
- Network Gap
- Audit Event

Require project authorization, stable IDs, sanitization, idempotent ingestion, versioned mappings, immutable approvals, reversible migrations and structured errors.

## 20. API capabilities

Suggested family:

`/api/v1/lab/discovery/network`

Capabilities:

- list/filter events;
- request detail;
- sanitized artifacts;
- timeline/correlation chain;
- APIs/systems;
- validate request;
- run validators;
- map screen/action/test step;
- assign system/validator;
- approve/reject mapping;
- resolve gaps;
- export sanitized evidence;
- activity/audit;
- publish relationships to Application Model.

## 21. Authorization and audit

Permissions:

- view network evidence;
- view sanitized payloads;
- validate requests;
- edit/approve mappings;
- assign validators;
- publish relationships;
- export evidence;
- view audit.

Audit every change with project, session, application, environment, event, actor, old/new state, reason, validator/tool, timestamp and correlation ID.

## 22. Loading, empty and error states

- Loading uses skeletons and no sample requests.
- No-capture state explains why and links to UI-015.
- Partial capture identifies unavailable areas.
- Sanitization failure blocks payload display/export.
- Permission denied may allow metadata-only view.
- Distinguish target disconnect, backend stream disconnect, completed capture and latest-capture-only states.

## 23. Accessibility

- Keyboard-accessible timeline, table and inspector.
- Textual waterfall alternative.
- Focus management and live-region updates.
- State not conveyed by colour alone.
- Reduced-motion support.
- Accessible method/status/result labels.
- Responsive overflow and focus restoration.

## 24. Visual contract

Match nxtQA/STLC:

- dark navy sidebar;
- white/soft-grey workspace;
- compact header/selectors;
- six KPI cards;
- readiness strip;
- dense navigator;
- central timeline/waterfall;
- compact table/detail tabs;
- fixed inspector;
- blue active;
- violet discovery/intelligence;
- emerald passed;
- amber warning/inconclusive;
- red failed/blocked;
- slate neutral;
- rounded cards, thin borders, restrained shadows;
- no fake live data or consumer-style clutter.

## 25. Required tests

Backend:

- project/session isolation;
- sanitization and prohibited-header removal;
- payload masking;
- ingestion idempotency;
- correlation mapping;
- validator execution;
- normalized outcomes;
- external MCP unavailable;
- mapping approval/versioning;
- publication to model;
- export authorization;
- audit;
- migration up/down;
- artifact containment.

Frontend:

- session/request selection;
- filters/search;
- timeline/table synchronization;
- detail and inspector tabs;
- MCP states;
- validation results;
- blocked/inconclusive states;
- sanitization failure;
- mapping approval;
- navigation context;
- loading/empty/partial errors;
- keyboard accessibility;
- responsive overflow.

## 26. Acceptance criteria

- UI-017 is the final P1-S4 screen.
- It follows UI-016 and preserves project/application/session context.
- Requests correlate to screens, actions, test steps and systems.
- Sensitive fields never appear.
- External MCPs and validators are explicit.
- Outcomes are deterministic and normalized.
- Timeline, table, details and inspector stay synchronized.
- Gaps are explicit.
- Approved relationships can be published to UI-016.
- Mock/unavailable capabilities are clearly labeled.
- UI success alone never proves end-to-end pass.
- Values come from authenticated persisted data.
- Exports are sanitized, authorized and audited.
- TypeScript, lint, build, backend, migration, security and browser tests pass.

## 27. Reference image gate

Implementation must not begin until the reference image and contract are approved.

Expected files:

```text
docs/autonomous-automation-lab/screens/API_Network_Explorer.png
docs/autonomous-automation-lab/screens/UI-017-API-Network-Explorer-UI-Contract.md
```

After approval:

```text
REFERENCE_IMAGE_APPROVED_READY_FOR_IMPLEMENTATION
```
