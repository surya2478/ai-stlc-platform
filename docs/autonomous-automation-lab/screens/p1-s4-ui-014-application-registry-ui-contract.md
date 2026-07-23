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
| Implemented route | `/applications?project={projectId}` (standalone dense workspace — see §16 implementation note) |
| Contextual entry | UI-012 Journey Graph, UI-013 Test Case Approval and AI Automation Studio |
| Previous screen | UI-013 Test Case Approval |
| Next screen | UI-015 Live Discovery Session |
| Existing baseline | Project Settings `Applications & Environments`, project-application API and external-dependency API |
| Implementation status | `IMPLEMENTED` |

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

## 10.1 Add / Edit Application form

`Add Application` opens a large right-side drawer consistent with the governed inspectors used by UI-007 through UI-013. It must not use a small confirmation modal because application identity, environments, ownership, discovery readiness and dependencies require structured review.

Recommended drawer width: `640–720px` on the approved desktop viewport, with a full-screen responsive form on smaller widths.

The same form is reused for Edit Application. Edit mode loads persisted values and applies stable-key, default-state, lifecycle and downstream-impact restrictions.

### Form header

- Title: `Add Application` or `Edit Application`
- Subtitle: `Register a stable application identity and governed discovery context.`
- Project name and ID — read-only
- Draft/validation state badge
- Close action with unsaved-change confirmation
- Optional `View Audit Log` in Edit mode

### Form sections

Use four compact steps or vertical accordion sections. All values must remain in one validated draft while the drawer is open.

#### Step 1 — Identity

Required fields:

- **Application Name** — required, 2–200 characters
- **Stable Key** — required, project-unique, uppercase recommendation such as `APP-CUSTOMER-PORTAL`
- **Application Type** — required when the governed application-type model exists
- **Description** — optional, maximum length enforced by backend
- **Lifecycle State** — `Draft`, `Active`, `Deprecated` or `Retired` according to permission and policy
- **Set as Project Default** — switch with unique-default warning
- **Active** — permission-aware lifecycle control; archive/deprecate is preferred after downstream use exists

Optional governed fields when persisted:

- Aliases — repeatable values
- External/system identifier
- Effective from / effective to
- Source/provenance

Stable Key behavior:

- The UI may suggest a key from the application name, but the backend creates/validates the canonical value.
- The key remains editable only before initial persistence or before downstream references exist.
- Duplicate keys display the conflicting application and block submission.
- Application ID is backend-generated after save and is never created only in frontend state.

#### Step 2 — Ownership and classification

Required governance fields when the backend extension exists:

- Business Owner — project-authorized user/team reference
- Technical Owner — project-authorized user/team reference
- Business Domain
- Product Group / Product
- Channel

Optional relationships:

- Customer Segment
- Customer Type
- Request Type / Sub Request Type
- Supported journeys
- Upstream applications
- Downstream applications

Interaction rules:

- Owner fields search real authorized users/teams; free-text names are not accepted as ownership references.
- Taxonomy selectors read approved taxonomy versions and show source/version.
- Multi-select relationships display stable IDs and names.
- Cross-project relationships are rejected.
- Missing classification may allow `Save Draft` but blocks `Activate` or `Start Discovery` according to policy.

#### Step 3 — Environments and access

Display environments as repeatable compact cards or rows.

Each environment contains:

- Environment Name — required and unique within the application
- Environment Type — for example SIT, QA, UAT, Staging or Production according to configured values
- Base URL — absolute `http` or `https` URL
- Health-check URL or strategy — optional until health monitoring is configured
- Authentication Profile Reference — selector only; never credentials
- Browser compatibility
- Device / AVD compatibility
- Framework / adapter compatibility
- Environment restrictions or notes
- Default environment marker where the governed model supports it
- Active state

Row actions:

- Add Environment
- Validate URL
- Test Health Check
- Duplicate Environment Configuration — removes secret/auth-profile bindings by default
- Remove unsaved environment
- Archive persisted environment with impact warning

Rules:

- An application may be saved as Draft without an environment.
- At least one active governed environment with a valid URL is required for Discovery Ready.
- Environment URL validation is performed by the backend and records result/timestamp.
- URLs must not contain embedded credentials, tokens or sensitive query parameters.
- Auth-profile contents are never returned to this form.
- Production discovery requires explicit policy eligibility; an application being Active does not automatically authorize production discovery.

#### Step 4 — Discovery, dependencies and review

Discovery configuration when persisted:

- Discovery Enabled
- Supported modes: Guided User, Free User-Action and/or Agent-Driven
- Supported surfaces: Web, Mobile, WebView, API and Network
- Allowed host/domain list
- Browser/device/AVD requirements
- Evidence/redaction policy reference
- Application-model status — read-only in Edit mode
- Last discovery session — read-only

External dependencies:

- Service Name
- Owning Application
- Sandbox URL
- Mock Strategy: `Intercept`, `Sandbox` or `Ignore`
- Active state
- Notes

Final review summary:

- Identity checks
- Ownership/classification checks
- Environment and URL checks
- Authentication-reference checks
- Discovery eligibility
- Dependency validation
- Default-application impact
- Downstream usage/impact in Edit mode
- Missing optional versus mandatory fields

The final review must distinguish:

- **Valid Draft** — record may be saved but is not discovery-ready
- **Ready to Activate** — mandatory registry governance passes
- **Discovery Ready** — active application, environment and discovery gates pass
- **Blocked** — submission or requested lifecycle action is invalid

### Form footer actions

Persistent footer actions:

- `Cancel`
- `Save Draft`
- `Validate`
- Primary action: `Add Application`, `Save Changes` or `Activate Application` depending on mode and permission

Behavior:

- `Validate` runs backend validation without silently persisting lifecycle advancement.
- `Save Draft` persists supported partial data and records the actor/source.
- `Add Application` creates the canonical backend record and returns its stable numeric ID/key.
- `Activate Application` is shown only when activation governance exists and all mandatory checks pass.
- The drawer remains open on validation/API failure and focuses the first invalid section.
- Successful creation closes the drawer, refreshes the registry and selects the created row.
- Successful edit refreshes the inspector and preserves the current filters/page.
- Double submission is prevented through disabled/busy state and backend idempotency where creation retries are possible.

### Field-level validation

- Application name cannot be blank.
- Stable key is normalized and validated by the backend; invalid characters are identified.
- Project-scoped stable key must be unique.
- Exactly one active default application is allowed per project.
- Every configured URL must be absolute `http` or `https`.
- Environment names must be unique for the application.
- Owner, taxonomy, auth-profile and related-application references must exist and belong to the permitted project/tenant scope.
- Dependency sandbox URL follows the same URL/secret rules.
- Archive/deprecate requires a reason and downstream impact review.
- Unsupported fields must not be submitted until their backend schema exists.

### Permission behavior

- Users with view permission can inspect but cannot open the Add form.
- `Add Application` and `Save Draft` require project-management/application-registry permission.
- Default, lifecycle, ownership, health and discovery controls may require separate governed permissions as defined by RBAC.
- Permission changes during editing are handled by the backend; the form preserves input and shows an authorization error without pretending the save succeeded.

### Empty and failure states

- Reference-data loading failures disable the affected selector and identify the unavailable service.
- No approved taxonomy displays an honest missing-taxonomy message rather than sample options.
- No auth profiles displays a contextual link to the authorized configuration page.
- URL/health failures show exact sanitized backend results.
- Concurrent update conflicts show the latest persisted version and require refresh/review before overwrite.
- Partial environment/dependency failure must not create orphan frontend-only rows.

### Backend implementation boundary

The current project-application API can persist only:

- key;
- name;
- description;
- default state;
- environment URL map;
- active state.

Therefore the first implementation must either:

1. extend the database/schema/service/API for the remaining governed fields before rendering them as editable; or
2. render only the supported fields and mark unavailable governance sections as `Not configured` without fake controls.

Frontend metadata or local state must not be used as a substitute for persisted ownership, taxonomy, discovery, health, compatibility, lifecycle or history records.

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

## 17. Implementation notes (2026-07-22)

- **Route**: implemented as a standalone `/applications` route (own `layout.tsx` + a new "Application Discovery" sidebar group) rather than inside the `/settings` tabbed shell, per §2's allowance to refine navigation. The reference image's KPI row + tabs + dense table + inspector density does not fit the Settings page's narrow two-column form shell. The existing `/settings` "Applications & Environments" tab is unchanged and now links out to the full registry; both read/write through the same `GET/PUT .../applications` and `PUT .../external-dependencies` endpoints — no duplicate application data store was created.
- **Backend extension**: migration `039_project_application_governance_fields` added `application_type`, `aliases`, `lifecycle_status`, `business_owner_id`, `technical_owner_id`, `domain`, `product_group`, `product`, `channel` to `project_applications`, mirroring existing patterns (`created_by`/`updated_by` FK style, `Requirement.telecom_domain`-style plain string taxonomy fields). New endpoints: `GET .../applications/summary`, `GET .../applications/audit-log`, `POST .../applications/seed-canonical`.
- **Deliberately not built** (rendered as explicit "Not configured" — no backing subsystem exists): health-check config/results, discovery capability/session tracking, AVD/browser/device compatibility, authentication-profile references, a separate approval-state workflow beyond `lifecycle_status`, participating journeys (no journey model exists anywhere in the backend).
- **Disclosed proxies, not fabricated data**: "Discovery Ready" (KPI, queue tab, table column) uses the contract's own stated gate — active + at least one environment URL — labelled everywhere as a proxy, not real discovery telemetry. "Mapping Conflicts" is computed from the new `product_group`/`product`/`channel` columns. "Mapping Usage" uses the real, pre-existing `TestCase.application_id` FK.
- **History/Activity tabs**: read from the existing `ProjectSettingAuditLog` whole-payload snapshots (no new versioned-history table), diffed client-side per application into a field-level history view and a human-readable activity feed.
- Canonical seed (§11) is idempotent (`POST .../applications/seed-canonical`) — verified live: seeding twice never overwrites or duplicates rows.
