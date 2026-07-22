# P1-S4 UI-014 Application Registry UI Contract

## Document control

| Field | Value |
|---|---|
| Screen ID | UI-014 |
| Phase | Phase 1 - Foundation |
| Section | P1-S4 Application Discovery |
| Screen name | Application Registry |
| Parent area | Application Discovery |
| Proposed route | `/settings?project={projectId}&tab=applications` |
| Contextual entry | UI-012 Journey Graph, UI-013 Test Case Approval and AI Automation Studio |
| Previous screen | UI-013 Test Case Approval |
| Next screen | UI-015 Live Discovery Session |
| Existing baseline | Project Settings `Applications & Environments`, project-application API and external-dependency API |
| Implementation status | `CONTRACT_DRAFT_PENDING_REFERENCE_IMAGE` |

## 1. Purpose

Application Registry is the governed source of stable application identities used by requirements, journeys, test cases, discovery, automation, environments, evidence and execution.

The screen must let authorized users register, find, review, update, archive and assess applications without introducing a second application data store or hard-coded application-name list.

## 2. Reuse and extension rule

UI-014 must extend the existing project settings implementation rather than replace it:

- existing component: `frontend/src/components/settings/ApplicationsTab.tsx`;
- existing read API: `GET /api/v1/projects/{projectId}/applications`;
- existing application update API: `PUT /api/v1/projects/{projectId}/applications`;
- existing dependency update API: `PUT /api/v1/projects/{projectId}/external-dependencies`;
- existing models: `ProjectApplication` and `ProjectExternalDependency`;
- existing application IDs and authorized project changes must be preserved.

The approved reference image may refine the route or navigation presentation, but must not create duplicate application records or bypass the existing audited services.

## 3. Header

Required content:

- Breadcrumb: `e& STLC / Application Discovery / Application Registry`
- Title: `Application Registry`
- Badge: `P1-S4 UI-014`
- Subtitle: `Govern applications, environments, ownership and discovery readiness.`
- Project selector and Jira sync state inherited from the application shell
- Last refreshed timestamp
- `Refresh`
- `Export Registry`
- Permission-aware `Add Application`

## 4. KPI cards

Use six compact cards backed by authenticated project data:

1. **Total Applications**
2. **Active**
3. **Discovery Ready**
4. **Environment Gaps**
5. **Health Issues**
6. **Mapping Conflicts**

No fallback or illustrative counts are permitted.

## 5. Registry readiness strip

Required checks:

- Stable registry key present
- Application owner assigned
- At least one governed environment configured
- Environment URLs valid
- Authentication profile reference configured where required
- Supported products and channels mapped
- Discovery capability evaluated
- Health check configured where required
- External dependencies reviewed
- Lifecycle and approval state valid

Every check must show a live numerator, percentage or explicit missing-data reason.

## 6. Queue tabs

Required tabs:

- All
- Active
- Draft
- Needs Review
- Discovery Ready
- Health Issues
- Deprecated / Retired

Tabs filter one canonical registry collection and must not change application identity.

## 7. Search and filters

Required controls:

- Search by application ID, stable key, name, alias, owner, product, channel or URL host
- Lifecycle status
- Application type
- Business domain
- Product group / product
- Channel
- Owner
- Environment
- Discovery capability
- Health status
- Mapping status
- More Filters
- Clear Filters

## 8. Registry table

Required columns:

- Application ID
- Stable key
- Application name
- Type
- Domain / product
- Channels
- Owner
- Environments
- Default state
- Discovery readiness
- Health
- Mapping usage
- Lifecycle status
- Updated at
- Actions

Required behavior:

- Selecting a row opens the right-side inspector.
- Stable IDs and keys are never generated only in browser state.
- Missing ownership, environments, health, relationships or discovery metadata must display as missing or blocked.
- Default application state must be unique per project and enforced by the backend.
- Archive/deprecate must be used instead of destructive deletion for persisted registry entries.
- Pagination and page-size controls must follow the compact table pattern used by UI-012 and UI-013.

## 9. Right-side inspector

Required tabs:

- Overview
- Environments
- Relationships
- Dependencies
- Discovery & Health
- History
- Activity

### 9.1 Overview

- Stable application ID and key
- Display name and aliases
- Description and application type
- Lifecycle and approval state
- Default application state
- Business and technical owners
- Domain, product groups, products and channels
- Created by, updated by and effective dates
- Source and provenance

### 9.2 Environments

- Environment name and type
- Governed base URL
- URL validation result
- Browser, device or AVD compatibility
- Authentication profile reference only; never credentials
- Health-check endpoint or strategy
- Last health result and timestamp
- Environment-specific restrictions

### 9.3 Relationships

- Supported products
- Supported channels
- Participating journeys
- Linked requirements
- Targeting test cases
- Automation and execution usage
- Upstream and downstream applications
- Mapping conflicts and impact analysis

### 9.4 Dependencies

- External service name
- Owning application
- Sandbox URL where configured
- Mock strategy: intercept, sandbox or ignore
- Active state
- Dependency notes
- Validation issues

### 9.5 Discovery & Health

- Discovery capability and eligibility
- Supported discovery modes
- Web, mobile, WebView, API and network capabilities when persisted
- Application-model status and version
- Last discovery session
- Health-check configuration and latest outcome
- Open discovery blockers
- `Start Discovery` gated action to UI-015

### 9.6 History

- Versioned field changes
- Old and new values
- Change reason
- Actor and timestamp
- Approval and lifecycle decisions
- Seed, import, settings, discovery or API source

### 9.7 Activity

- Registration and seed events
- Environment changes
- Health-check events
- Discovery sessions
- Mapping changes
- Test-case usage changes
- Automation or execution usage events

## 10. Registry actions

Required permission-aware actions:

- Add Application
- Edit Application
- Add / edit environment
- Set as Default
- Add alias
- Map products and channels
- Assign owner
- Add / edit external dependency
- Validate URLs
- Run Health Check
- Start Discovery
- Request Review
- Approve / Activate when governance requires it
- Deprecate / Archive
- Export Application
- View Audit Log

Action rules:

- New and edited records must be validated by the backend before persistence.
- Stable keys cannot be silently changed after downstream use exists.
- Exactly one active default application is allowed per project where applications exist.
- URL fields accept only absolute `http` or `https` URLs.
- Credentials, tokens and passwords must not be stored in registry URL or metadata fields.
- Authentication must use approved profile references.
- Archive/deprecate must show downstream impact and require a change reason.
- Start Discovery is disabled until mandatory registry and environment checks pass.
- Backend validation and permission errors must be shown verbatim.

## 11. Canonical application seeds

The following approved applications must be supported through an idempotent seed or import process:

| Stable key | Display name |
|---|---|
| `APP-USP-DIRECT` | USP Direct |
| `APP-B2B` | B2B |
| `APP-CIM` | CIM |
| `APP-CODE` | CoDE |
| `APP-B2C` | B2C |
| `APP-SALES-PORTAL` | Sales Portal |
| `APP-SMILES` | Smiles |
| `APP-MOBILE-APP` | Mobile App |

Seeder rules:

- repeat execution is idempotent;
- stable keys never change;
- authorized administrative edits are not overwritten;
- B2B and B2C applications remain distinct from customer-segment taxonomy;
- consumers retrieve registry records instead of using a hard-coded list.

## 12. Data and backend delta

The current `ProjectApplication` foundation persists:

- numeric ID;
- project ID;
- key;
- name;
- description;
- default state;
- environment URLs;
- active state;
- creator, updater and timestamps.

UI-014 must not display unsupported governance fields as if they already exist. Before those fields become editable, the backend contract must be extended with persisted structures for:

- aliases and application type;
- owner references;
- lifecycle and approval state;
- effective dates;
- taxonomy relationships;
- authentication-profile references;
- discovery capabilities;
- health-check configuration and results;
- AVD/browser/device compatibility;
- application relationships and mapping conflicts;
- versioned change and approval history.

Required backend qualities:

- project-scoped authorization;
- immutable audit events with change reason;
- stable-key uniqueness;
- unique active default enforcement;
- referential validation for owners, taxonomy and auth profiles;
- cross-project reference rejection;
- deterministic seed behavior;
- impact checks before archive/deprecate.

## 13. Empty, loading and error states

- Loading does not display seeded or sample applications before the API responds.
- Empty state explains how an authorized user can register or seed the first application.
- Partial API failures identify the unavailable section and do not infer readiness.
- Permission failures preserve authorized read-only inspection.
- Validation errors identify the exact application, environment or dependency field.

## 14. Visual contract

- Existing dark navy sidebar and white application shell
- Compact six-card KPI row
- Compact readiness strip
- Dense registry table with fixed-width inspector
- Blue primary actions
- Emerald active/ready states
- Amber draft/review/health-warning states
- Red invalid/blocked/deprecated states
- Violet discovery/model intelligence accents
- Major regions fit the approved desktop viewport without excessive gaps

## 15. Acceptance criteria

- UI-014 follows UI-013 in the approved 58-screen order.
- Existing project applications and environments remain visible and editable through the governed registry.
- Every value shown is backed by authenticated project data.
- Stable key, default application and environment URL rules are backend enforced.
- The eight canonical applications can be seeded idempotently without overwriting authorized changes.
- Search, filters, table, inspector tabs, pagination and exports work.
- Add, edit, assign, map, health, discovery and lifecycle controls are permission-aware and audited.
- Missing metadata is shown as missing, not invented.
- Application-to-test, journey, product and channel relationships use stable registry IDs.
- Start Discovery preserves project, application and environment context for UI-015.
- TypeScript, backend tests, production build and authenticated browser validation pass before completion.

## 16. Reference image gate

Implementation must not begin until the UI-014 Application Registry reference image is provided and approved.

Expected image file:

`docs/autonomous-automation-lab/screens/Application_Registry.png`

After approval, update the status to:

`REFERENCE_IMAGE_APPROVED_READY_FOR_IMPLEMENTATION`
