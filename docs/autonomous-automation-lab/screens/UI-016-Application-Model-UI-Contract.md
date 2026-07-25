# P1-S4 UI-016 Application Model UI Contract

## Document control

| Field | Value |
|---|---|
| Screen ID | UI-016 |
| Phase | Phase 1 — Grounded Web PoC |
| Section | P1-S4 Application Discovery |
| Screen name | Application Model |
| Parent area | Application Discovery |
| Proposed route | `/automation?project={projectId}&view=application-model&application={applicationId}&model={modelVersionId}` |
| Previous screen | UI-015 Live Discovery Session |
| Next screen | UI-017 API and Network Explorer |
| Contextual entry | UI-014 Application Registry, UI-015 Live Discovery Session, UI-012 Journey Graph, UI-013 Test Case Approval and AI Automation Studio |
| Existing baseline | Project Application Registry, discovery-session evidence, locator-map persistence, Playwright MCP discovery output, network/API captures and artifact lineage |
| Reference image target | `docs/autonomous-automation-lab/screens/Application_Model.png` |
| Implementation status | `CONTRACT_DRAFT_PENDING_REFERENCE_IMAGE_APPROVAL` |

## 1. Purpose

Application Model is the governed, versioned representation of a registered application created from approved discovery evidence.

It must let authorized users inspect, validate, correct, compare, approve and publish the discovered application structure before it is used by Automation Studio, script generation, reusable assets, execution, healing or knowledge retrieval.

The model must represent applications, environments, screens, components, elements, locator evidence, transitions, journeys, test cases, APIs, external systems, MCPs, evidence, provenance, gaps, versions and approvals.

## 2. Reuse and extension rule

Reuse existing project applications, stable application IDs, discovery-session records, accessibility snapshots, locator recommendations, network/API evidence, external validation results, artifact lineage, approval patterns, RBAC, audit and feature flags.

Do not create a parallel application registry, locator database or disconnected model store.

PostgreSQL remains authoritative for model metadata and versioning. Large artifacts remain in governed storage. Only sanitized and approved model projections may become retrieval-eligible knowledge.

## 3. Navigation and context preservation

- UI-015 `Review Application Model` opens UI-016 with project, application, environment, discovery-session ID and draft model version.
- UI-014 may open the latest approved model, latest draft, model history or model health.
- UI-012/UI-013 may open UI-016 filtered to an application, journey, test case, screen or blocker.
- UI-016 links onward to UI-017, UI-018, UI-015, UI-014, UI-012 and UI-013 while preserving context.
- Completing UI-015 creates or updates a draft model only; it does not auto-approve or auto-publish.

## 4. Header

Required:

- Breadcrumb: `e& STLC / Application Discovery / Application Model`
- Title: `Application Model`
- Badge: `P1-S4 UI-016`
- Subtitle: `Review, validate and publish the grounded application structure created from discovery evidence.`
- Project selector
- Application selector using stable registry IDs
- Environment selector where relevant
- Model version selector
- Model lifecycle badge
- Source discovery-session ID
- Last refreshed timestamp
- Refresh
- Compare Versions
- Export Model
- Permission-aware primary action: Submit for Review, Approve Model, Publish Model or Create New Draft

The header must reflect persisted backend state.

## 5. Model lifecycle

Required states:

`DRAFT`, `BUILDING`, `BUILD_FAILED`, `PENDING_REVIEW`, `CHANGES_REQUESTED`, `APPROVED`, `PUBLISHED`, `SUPERSEDED`, `REJECTED`, `STALE`, `ARCHIVED`.

Approved and published versions are immutable. Corrections require a new draft. The same agent identity cannot build and approve the same model.

## 6. KPI cards

Use six compact cards:

1. Screens & Views
2. Components & Elements
3. Journeys Mapped
4. APIs & Dependencies
5. Model Gaps
6. Publication Readiness

All values must come from authenticated persisted data.

## 7. Readiness and governance strip

Checks:

- Registered application and stable ID valid
- Source discovery session completed
- Evidence sanitized
- Screen/component mappings reviewed
- Element semantics and locators validated
- Journey/test-case relationships valid
- API/network relationships reviewed
- External validator/MCP relationships captured
- Mandatory evidence present
- Sensitive-data violations resolved
- Separation of duties valid
- Policy and permission checks passed
- No unresolved critical blocker

Each check displays Passed, Warning, Blocked or Not Evaluated with exact reason.

## 8. Main layout

Use a dense enterprise layout with:

1. Left model navigator
2. Center model canvas
3. Lower relationship/details grid
4. Fixed-width right inspector

## 9. Left model navigator

Recommended hierarchy:

```text
Application
├── Environments
├── Journeys
├── Screens & Views
├── Components
├── Elements
├── APIs & Network
├── External Systems & MCPs
├── Evidence
├── Gaps & Blockers
└── Versions
```

Support search, expand/collapse, type/state filters, gaps-only, changed-only, unreviewed, low-confidence, automation-used and stale-locator views.

## 10. Center model canvas

Required tabs:

- Application Map
- Screen Flow
- Component Map
- Element Map
- Journey Overlay
- API & System Map
- Evidence Overlay
- Change Comparison

The canvas must visualize application structure, navigation, reusable components, semantic elements, locators, journeys, test cases, APIs, external systems, MCPs, evidence, gaps and version differences.

## 11. Canvas controls

- Search
- Fit to screen
- Zoom in/out
- Center selection
- Expand/collapse lineage
- Show gaps
- Show evidence
- Show APIs
- Show external systems
- Show automation usage
- Compare versions
- Export image
- Export structured model

Use nxtQA semantic colors: blue active, violet intelligence, emerald approved, amber partial/stale, red blocker, slate neutral. State must not rely on colour alone.

## 12. Lower relationship grid

Required table views:

- Screens
- Components
- Elements
- Journeys & Test Cases
- APIs
- External Systems & MCPs
- Evidence
- Gaps
- Version Changes

Tables must use compact density, pagination, filters and selection synchronized with the canvas and inspector.

## 13. Right-side inspector

Tabs:

- Overview
- Structure
- Locators
- Journeys
- APIs & Systems
- Evidence
- Gaps
- History
- Activity

The inspector updates for the selected application, screen, component, element, API, system, journey, evidence item or gap.

Key content includes stable IDs, lifecycle, source session, hierarchy, locators, confidence, journey/test links, APIs, MCPs, evidence, blockers, version history and audit activity.

## 14. Gap and blocker model

Required gap types:

`MISSING_SCREEN`, `MISSING_COMPONENT`, `MISSING_ELEMENT`, `AMBIGUOUS_ELEMENT`, `UNSTABLE_LOCATOR`, `BROKEN_NAVIGATION`, `MISSING_JOURNEY_MAPPING`, `MISSING_TEST_CASE_MAPPING`, `MISSING_API_MAPPING`, `AMBIGUOUS_API_MAPPING`, `MISSING_EXTERNAL_VALIDATOR`, `UNAVAILABLE_MCP`, `MISSING_EVIDENCE`, `SENSITIVE_DATA_VIOLATION`, `STALE_SOURCE`, `CONFLICTING_DISCOVERY_EVIDENCE`, `UNSUPPORTED_CONTEXT`, `APPROVAL_BLOCKER`.

Every gap stores severity, impacted nodes, evidence, remediation, owner, status, reviewer notes and approval impact. Critical gaps block approval and publication.

## 15. Model actions

Required permission-aware actions:

- Build/Rebuild Model
- Save Draft
- Edit semantic names and mappings
- Merge/split nodes
- Confirm locator
- Add fallback locator
- Mark locator unstable
- Link journey/test/API/external system/MCP
- Add evidence requirement
- Resolve or review gap
- Request rediscovery
- Open source session
- Submit for Review
- Request Changes
- Reject Model
- Approve Model
- Publish Model
- Create New Draft
- Compare Versions
- Export Model
- View Audit Log

## 16. Publication gate

Publication requires:

- state is APPROVED;
- stable application ID is valid;
- source evidence is sanitized;
- no unresolved critical gap;
- required screens/components/elements reviewed;
- journey/test mappings valid;
- API/system relationships reviewed;
- required MCP/validator relationships captured;
- mandatory evidence complete;
- no sensitive-data violation;
- model not stale;
- separation of duties valid;
- publication permission valid;
- downstream impact acknowledged where required.

Publishing creates an immutable publication record, model version, artifact lineage, KB projection job where enabled, graph projection event where enabled, audit event and supersession relationship.

## 17. Knowledge Base and RAG publication

Raw discovery sessions must not be embedded directly into the KB.

Required lifecycle:

```text
Discovery Session
    ↓
Sanitized Evidence
    ↓
Draft Application Model
    ↓
Independent Review
    ↓
Approved Application Model
    ↓
Published Model
    ↓
Approved Knowledge Projection
    ↓
pgvector / metadata / graph retrieval
```

Only sanitized, reviewed and approved model content becomes retrieval eligible.

Do not index credentials, OTPs, cookies, authorization headers, tokens, raw PII, unredacted screenshots, prohibited payloads, unapproved AI assumptions or incomplete observations presented as facts.

Every knowledge item retains provenance to project, application, model version, discovery session, source node, evidence artifact and approval record.

## 18. Downstream consumption

Published model versions may be consumed by UI-017, UI-018, UI-019, UI-020, UI-021, UI-023, execution readiness, locator reuse, failure diagnosis, healing, RAG and graph engineering.

Consumers must reference stable model and node IDs. Approved downstream assets retain the exact model version used. New models must trigger impact analysis rather than silently overwrite approved assets.

## 19. Data contract

```ts
type ApplicationModelLifecycle =
  | "DRAFT"
  | "BUILDING"
  | "BUILD_FAILED"
  | "PENDING_REVIEW"
  | "CHANGES_REQUESTED"
  | "APPROVED"
  | "PUBLISHED"
  | "SUPERSEDED"
  | "REJECTED"
  | "STALE"
  | "ARCHIVED";

type ApplicationModelNodeType =
  | "application"
  | "environment"
  | "journey"
  | "scenario"
  | "test_case"
  | "screen"
  | "view"
  | "dialog"
  | "component"
  | "element"
  | "api"
  | "external_system"
  | "validator"
  | "evidence"
  | "gap";

type ApplicationModelNodeState =
  | "DISCOVERED"
  | "PARTIAL"
  | "VALIDATED"
  | "APPROVED"
  | "PUBLISHED"
  | "AMBIGUOUS"
  | "MISSING"
  | "BROKEN"
  | "STALE"
  | "BLOCKED";
```

Persist versioned nodes, typed edges, locator evidence, gaps, reviews, approvals, publication and audit.

## 20. Backend delta

Required persisted structures:

- Application Model
- Model Version
- Model Node
- Model Edge
- Locator Evidence
- Model Gap
- Model Review
- Model Approval
- Model Publication
- Model Activity/Audit
- Knowledge Projection Link
- Downstream Impact Link

Required qualities: project authorization, stable IDs, immutability, versioning, supersession, reversible migrations, provenance, idempotent jobs and structured errors.

## 21. API capabilities

Suggested family:

```text
/api/v1/lab/application-models
```

Required capabilities:

- list/filter models;
- get summary/version;
- build/rebuild draft from discovery;
- search nodes/relationships;
- edit draft metadata and mappings;
- merge/split nodes;
- validate/add locators;
- link journeys/tests/APIs/systems/validators;
- list/resolve gaps;
- submit review;
- request changes;
- approve/reject/publish;
- create new draft;
- compare versions;
- export;
- retrieve impact, activity and audit;
- publish approved KB projection.

State-changing commands must be backend-authoritative and idempotent where applicable.

## 22. Authorization and audit

Permissions:

- view
- create draft
- build/rebuild
- edit
- review
- approve
- publish
- resolve gaps
- validate locators
- link relationships
- export
- view audit
- publish knowledge projection

Every change records actor, project, application, environment, model/version, affected node/edge/gap, previous/new state, reason, source session, timestamp, correlation ID and agent/model/prompt/tool provenance where applicable.

## 23. Privacy and security

- Never expose credentials or authentication material.
- Sanitize DOM, network, screenshots and logs.
- Mask PII and financial data.
- Redact prohibited screenshot regions.
- Enforce project/environment isolation and allowed-host policy.
- Treat captured application content as untrusted.
- Prevent prompt injection from altering model rules or tools.
- Validate artifact paths.
- Authorize every model/node/edge/gap/evidence request.
- Audit exports and publication.
- Apply retention and legal-hold policies.

## 24. Loading, empty and error states

- Loading uses skeletons and never sample model data.
- No-model state links to UI-015.
- Build-failed state preserves source evidence and shows safe error/correlation ID.
- Partial failures identify unavailable regions and do not infer readiness.
- Permission failures preserve authorized read-only access.
- Stale state explains source changes, impact and rebuild/review actions.

## 25. Accessibility

- Keyboard-accessible tree, graph and tables.
- Textual alternative for graph.
- Focus management.
- Live-region state announcements.
- State not conveyed by colour alone.
- Reduced-motion support.
- Accessible node and relationship labels.
- Table/list alternative for graph navigation.
- Sufficient contrast using existing tokens.

## 26. Visual contract

Match the current nxtQA/STLC enterprise system:

- dark navy navigation;
- white/soft-grey workspace;
- compact header/selectors;
- six KPI cards;
- compact readiness strip;
- dense navigator;
- large central canvas;
- lower data grid;
- fixed right inspector;
- blue primary actions;
- violet model intelligence;
- emerald approved/published;
- amber partial/stale;
- red blocker/rejected;
- slate neutral;
- rounded cards and subtle shadows;
- no oversized gaps;
- no disconnected design system;
- no fake live data.

## 27. Required tests

Backend:

- draft creation from completed discovery;
- project isolation;
- node/edge versioning;
- lifecycle transitions;
- approved/published immutability;
- separation of duties;
- gap blocking;
- locator history;
- API/system linkage;
- stale detection;
- publication gating;
- KB projection after publication only;
- idempotent build/publish;
- permission/audit;
- migration up/down;
- artifact containment;
- sanitization.

Frontend:

- model/version selection;
- loading/empty/build-failed;
- tree navigation;
- graph/table/inspector synchronization;
- node correction;
- locator validation;
- gap resolution;
- version comparison;
- stale state;
- approval/publication gates;
- navigation context;
- keyboard accessibility;
- responsive overflow;
- permission actions;
- partial API failures.

## 28. Acceptance criteria

- UI-016 follows UI-015 in P1-S4.
- Route preserves project, application, environment, session and model context.
- Models derive from persisted discovery evidence.
- Raw sessions are not automatically published to KB.
- Header, KPIs, readiness, navigator, canvas, grid and inspector are present.
- Screens, components, elements, journeys, tests, APIs, systems, validators, evidence and gaps are represented.
- Locator recommendations preserve evidence and confidence.
- External MCP/validator relationships are visible.
- Selection synchronizes canvas, grid and inspector.
- Critical gaps block approval/publication.
- Approved/published versions are immutable.
- Publishing creates approved knowledge projection only.
- Downstream assets preserve exact model version.
- No approved asset is silently overwritten.
- All values come from authenticated project data.
- No secrets or unredacted sensitive data are shown.
- TypeScript, lint, build, backend, migration, security and authenticated browser tests pass.

## 29. Reference image gate

Implementation must not begin until the UI-016 reference image and this contract are approved.

Expected files:

```text
docs/autonomous-automation-lab/screens/Application_Model.png
docs/autonomous-automation-lab/screens/UI-016-Application-Model-UI-Contract.md
```

After approval, update status to:

```text
REFERENCE_IMAGE_APPROVED_READY_FOR_IMPLEMENTATION
```
