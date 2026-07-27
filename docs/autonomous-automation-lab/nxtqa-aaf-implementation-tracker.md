# nxtQA Autonomous Automation Fabric Implementation Tracker

## 1. Document control

| Field | Value |
|---|---|
| Plan ID | AAF-IMP-001 |
| Plan version | 1.0 |
| Authoritative requirement baseline | `nxtQA_AAF_Codex_Master_Prompt_FINAL_v1.0.docx` |
| Baseline version and date | 1.0 FINAL, 21 July 2026 |
| Target platform | STLC Platform / nxtQA |
| Capability | nxtQA Autonomous Automation Fabric (nxtQA AAF) |
| Repository | `D:\AI\Projects\stlc-platform` |
| Current branch at assessment | `feature/autonomous-automation-lab` |
| Tracker status | Phase 0 validated; implementation not started |
| Screen scope | 58 functional screens |
| Delivery model | Phase 0 assessment plus Phases 1-3 incremental delivery |
| Approval rule | No section implementation begins until every screen in that section has an approved visual design and UI contract |

This tracker is the implementation control document for the locked v1.0 baseline. Older Autonomous Automation Lab plans remain useful repository history, but they do not override this tracker or the locked source prompt.

## 2. Status legend

| Status | Meaning |
|---|---|
| `NOT_STARTED` | No implementation activity has started |
| `MOCKUP_IN_REVIEW` | Screen images or interaction designs are under review |
| `APPROVED_FOR_BUILD` | Visuals and contracts are approved |
| `IN_PROGRESS` | The vertical slice is being implemented |
| `BLOCKED` | Progress needs a documented decision or external dependency |
| `VERIFYING` | Implementation is complete and verification is running |
| `ACCEPTED` | Section exit criteria and evidence are approved |
| `DEFERRED` | Explicitly deferred with impact and approval recorded |

## 3. Non-negotiable delivery rules

- [ ] Preserve all existing working functionality.
- [ ] Keep nxtQA AAF isolated and controlled by a master feature flag and sub-feature flags.
- [ ] Reuse existing authentication, RBAC, navigation, API, data, audit, logging, error-handling, deployment and job conventions.
- [ ] Do not invent application screens, locators, URLs, APIs, database fields or business outcomes.
- [ ] Ground every generated UI action in approved live or versioned evidence.
- [ ] Make deterministic systems responsible for readiness, assertions, evidence completeness and pass/fail.
- [ ] Treat missing mandatory evidence as `INCONCLUSIVE`.
- [ ] Treat environment failures as `BLOCKED` or `ENVIRONMENT_FAILURE`, not application defects.
- [ ] Do not allow the same agent to generate and approve an asset.
- [ ] Do not silently overwrite approved automation, locators, application models or reusable components.
- [ ] Do not bulk-rewrite the existing script estate.
- [ ] Do not store credentials or secrets in prompts, source code, recordings, screenshots, videos or evidence.
- [ ] Do not generate automation from video alone; structured recording is authoritative.
- [ ] Do not let an agent act after pause acknowledgement or Emergency Stop.
- [ ] Do not publish free recordings or stopped recordings without the required approvals.
- [ ] Do not hard-code telecom taxonomy values or named application lists where governed registry data is available.
- [ ] Require a valid parent Request Type for every Sub Request Type.
- [ ] Use stable application IDs so display-name changes cannot break traceability.
- [ ] Make every schema migration reversible.
- [ ] Require authorization, input validation, audit and structured errors for every new API.
- [ ] Make long-running work idempotent and expose persisted progress.
- [ ] Preserve rollback versions for every editable or approved asset.

## 4. Current-state repository baseline

| Layer | Verified current capability | Implementation decision |
|---|---|---|
| Frontend | Next.js 14.2.3, React 18, TypeScript, Tailwind, Radix UI, TanStack Query, Recharts | Reuse; do not introduce a second frontend stack |
| Backend | FastAPI, Pydantic and async SQLAlchemy | Reuse and split AAF APIs by domain |
| Database | PostgreSQL, pgvector and Alembic | Keep as system of record; add normalized/versioned AAF entities |
| Authentication | JWT | Reuse unchanged |
| Authorization | Project-scoped DB-backed RBAC | Extend with explicit AAF permissions |
| Jobs | Celery and Redis | Reuse dedicated `autonomous_lab` queue and add bounded schedules only when feature-enabled |
| Automation | Generation contract, deterministic compiler, static gate, Playwright runner, locator evidence, approval/versioning | Reuse as the compilation and execution foundation |
| Grounding | Existing grounded automation PoC and discovery services | Extend into full application discovery and recording |
| AI and RAG | LangGraph agents, role routing, PostgreSQL/pgvector RAG | Reuse; introduce governed graph workflows and retrieval provenance |
| Existing Lab module | `/autonomous-lab`, `/api/v1/lab`, feature flags, ten combined pages and extensive `Aal*` models | Preserve compatibility and incrementally decompose into AAF domains |
| Test Data | Search, generation, reservation and Lab data-package services | Extend into the complete Fabric state, lease, certification and cleanup model |
| Evidence and audit | Execution evidence, lineage, approvals, agent audit and Lab evidence records | Reuse and add journey-specific deterministic quorum |
| Defects | Jira plus Lab RTC adapter/gateway foundations | Preserve Jira; keep RTC behind an adapter and explicit maturity state |
| Deployment | Docker Compose, Dockerfiles and nginx | Reuse initially; Kubernetes and Temporal need separate justification |

Baseline verification recorded during planning:

- Targeted backend verification: 77 tests passed.
- Frontend lint: completed successfully with existing warnings.
- Repository has pre-existing user changes; they must remain untouched unless explicitly included in an approved section.

## 5. Target architecture

### 5.1 Architectural layers

1. **nxtQA UI shell** - existing layout, navigation, project selection, authentication and shared components.
2. **AAF presentation modules** - 58 route-level functional screens composed from shared workspaces, tabs, drawers and visual components.
3. **AAF API domains** - requirements, taxonomy, applications, discovery, recording, Automation IR, execution, evidence, graph, healing and administration.
4. **AAF domain services** - typed business logic independent from FastAPI route handlers.
5. **Canonical nxtQA systems of record** - Requirement, TestCase, AutomationScript, ExecutionRun, AgentRun, ApprovalAction, ArtifactLineage and existing TestData entities.
6. **AAF-owned records** - orchestration, recording, application model, graph, environment, AVD, policy, evidence quorum and version metadata.
7. **Async control plane** - Celery/Redis with idempotency keys, correlation IDs, explicit timeouts and stopping conditions.
8. **Adapter layer** - Playwright, Playwright MCP, Appium, Katalon, UiPath, Selenium, REST, SOAP, database, messaging, RTC, Git, storage and infrastructure integrations.
9. **Knowledge plane** - PostgreSQL system of record, pgvector semantic retrieval and an approved graph repository implementation.
10. **Governance plane** - RBAC, policy, approvals, audit, kill switches, privacy, model/prompt/tool registries and cost controls.

### 5.2 Compatibility decisions

- Keep `/api/v1/lab` compatible during incremental delivery.
- Keep `/autonomous-lab` routes operational until canonical AAF routes and redirects pass regression testing.
- Display the capability as **Autonomous Automation** / **nxtQA AAF** without renaming physical `aal_*` tables solely for branding.
- Split the current monolithic Lab router incrementally; do not perform a flag-day rewrite.
- Keep PostgreSQL authoritative even if Neo4j or an approved graph equivalent is added.
- Add a graph repository interface and outbox/synchronization contract before selecting or activating an external graph engine.
- Do not introduce Temporal, Kubernetes, OPA, object storage or new messaging infrastructure without an approved operational need and rollback plan.
- Label every integration and evidence source as `REAL`, `MOCK`, `VIRTUALIZED`, `RECORDED` or `NOT_CONFIGURED`.

## 6. Standard section workflow and approval gate

Every implementation section uses the following lifecycle:

1. Confirm requirements and repository extension points.
2. Produce an image representation for every screen in the section.
3. Include default, loading, empty, error, permission-denied and relevant safety/control states.
4. Document screen actions, validation, roles, data sources, APIs and audit events.
5. Obtain explicit user approval for all screen images and the UI contract.
6. Define or confirm database, API, event, agent, adapter and evidence contracts.
7. Implement reversible migrations.
8. Implement backend domain logic and authorized APIs.
9. Implement frontend routes and shared components.
10. Add security, privacy, audit, feature flags, idempotency and progress reporting.
11. Run existing and new unit, API, frontend, migration and integration tests.
12. Provide working screenshots, test evidence, limitations and rollback notes.
13. Obtain section acceptance before starting the next section.

No UI-only placeholder counts as an implemented screen.

## 7. Phase and section summary

| Phase | Section | Name | Screens | Status |
|---|---|---|---:|---|
| 0 | P0-S1 | Baseline reconciliation | 0 | `ACCEPTED` |
| 0 | P0-S2 | Architecture and contracts | 0 | `ACCEPTED` |
| 0 | P0-S3 | Delivery controls | 0 | `ACCEPTED` |
| 0 | P0-S4 | UI foundation | 0 | `ACCEPTED` |
| 0 | P0-S5 | Verification baseline | 0 | `ACCEPTED` |
| 1 | P1-S1 | Command Centre Foundation | 1 | `VERIFYING` |
| 1 | P1-S2 | Requirement Intelligence Core | 3 | `NOT_STARTED` |
| 1 | P1-S3 | Test Design and Approval | 4 | `IN_PROGRESS` |
| 1 | P1-S4 | Application Discovery | 4 | `NOT_STARTED` |
| 1 | P1-S5 | Automation Studio Core | 5 | `IN_PROGRESS` |
| 1 | P1-S6 | Test Data Selection | 1 | `NOT_STARTED` |
| 1 | P1-S7 | Execution and Evidence | 2 | `NOT_STARTED` |
| 2 | P2-S1 | Operational Command Centre | 3 | `NOT_STARTED` |
| 2 | P2-S2 | Requirement Governance | 1 | `NOT_STARTED` |
| 2 | P2-S3 | Framework and Reusable Assets | 3 | `NOT_STARTED` |
| 2 | P2-S4 | Existing Script Maintenance | 4 | `NOT_STARTED` |
| 2 | P2-S5 | Test Data Lifecycle | 3 | `NOT_STARTED` |
| 2 | P2-S6 | Script Dependency Graph | 1 | `NOT_STARTED` |
| 2 | P2-S7 | Execution Planning and Assignment | 3 | `NOT_STARTED` |
| 3 | P3-S1 | Taxonomy and GraphRAG | 4 | `NOT_STARTED` |
| 3 | P3-S2 | Graph Engineering | 5 | `NOT_STARTED` |
| 3 | P3-S3 | Healing and Defect Intelligence | 4 | `NOT_STARTED` |
| 3 | P3-S4 | Reporting and Release Governance | 2 | `NOT_STARTED` |
| 3 | P3-S5 | Administration and Governance | 4 | `NOT_STARTED` |
| 3 | P3-S6 | Alerts and Incidents | 1 | `NOT_STARTED` |

Functional screen reconciliation: Phase 1 = 20, Phase 2 = 18, Phase 3 = 20, total = **58**.

## 8. Phase 0 - assessment and contract baseline

### P0-S1 Baseline reconciliation

Deliverables:

- [ ] Requirement-to-codebase traceability matrix.
- [ ] Available/partial/reusable/extension/new/unsuitable/deferred classification.
- [ ] Existing Automation and Lab compatibility assessment.
- [ ] Exact route, component, model, migration, service and job extension points.
- [ ] Conflict register between the locked v1.0 baseline and older repository plans.
- [ ] Approved naming and compatibility strategy.

Exit criteria:

- Every locked baseline section maps to at least one planned work package and verification artifact.
- No unresolved conflict is silently interpreted.

### P0-S2 Architecture and contracts

Deliverables:

- [ ] Module boundaries.
- [ ] API and structured error contracts.
- [ ] Event and progress contracts.
- [ ] Database entity ownership map.
- [ ] Automation IR schema.
- [ ] Adapter interface and maturity model.
- [ ] Agent graph and typed handoff schemas.
- [ ] Graph ontology and repository contract.
- [ ] Evidence and quorum schema.
- [ ] Recording session/action/checkpoint/state schemas.
- [ ] Readiness, environment and AVD schemas.
- [ ] Taxonomy and Application Registry schemas.

### P0-S3 Delivery controls

Deliverables:

- [ ] Master and sub-feature-flag matrix.
- [ ] Project policy and autonomy defaults.
- [ ] Global and project kill-switch design.
- [ ] Reversible migration sequence.
- [ ] Rollback and data-backfill strategy.
- [ ] Change-request template with architecture, data, screens, API, tests, migration and rollback impact.

### P0-S4 UI foundation

Deliverables:

- [ ] Approved 58-screen information architecture.
- [ ] Route and menu plan.
- [ ] Shared page header, status, approval, evidence, graph, editor and live-progress components.
- [ ] Screen state and accessibility standards.
- [ ] Image mockup naming, version and approval convention.
- [ ] Compatibility plan for the existing ten Lab pages.

### P0-S5 Verification baseline

Deliverables:

- [ ] Full backend test baseline.
- [ ] Frontend lint/build baseline.
- [ ] Migration upgrade/downgrade baseline.
- [ ] Existing Automation regression suite.
- [ ] Security and RBAC baseline.
- [ ] Performance and job-queue baseline.
- [ ] Evidence-storage and retention baseline.

### Phase 0 validation evidence - 21 July 2026

Outcome: Phase 0 validation is complete for planning, architecture, delivery controls, UI approval gating and focused regression verification. The local backend Python environment was repaired and the focused Autonomous Lab regression suite now passes.

| Check | Result | Evidence |
|---|---|---|
| 58-screen inventory | Passed | Tracker contains 58 unique `UI-001` through `UI-058` rows |
| Phase screen totals | Passed | Phase 1 = 20, Phase 2 = 18, Phase 3 = 20 |
| Automation Studio count | Passed | Six screens confirmed: Automation Workspace, Live Recorder, Automation IR Editor, Script Editor, Framework Configuration, Validation and Review |
| Framework Configuration placement | Passed | Included in the six-screen Automation Studio design pack; implementation remains Phase 2 under Framework and Reusable Assets |
| Existing Lab compatibility | Passed with migration constraint | Existing `/autonomous-lab` frontend has 10 combined pages and must be decomposed into the 58-screen IA by approved section |
| Feature flag isolation | Passed | Backend `AUTONOMOUS_LAB_ENABLED` gate and frontend gated Autonomous Lab navigation are present |
| RBAC baseline | Passed | Existing `autonomous_lab.*` permissions are present and must be extended by domain |
| Taxonomy model fit | Constraint confirmed | Current taxonomy has Product Group/Product/Sub Request Type, but lacks required Customer Segment, Customer Type, Request Type and Channel dimensions; current Sub Request Type is flat |
| Application registry fit | Constraint confirmed | `ProjectApplication` has stable key/name/default/environment URLs, but must be extended for governed registry metadata and seed application IDs |
| Recording state baseline | Constraint confirmed | Full locked state machine is documented in this tracker and not yet implemented in product code |
| Frontend lint | Passed with existing warnings | `npm.cmd run lint` completed successfully; warnings are pre-existing React hook and image warnings |
| Backend focused tests | Passed | Repointed backend `.venv` to bundled Python `3.12.13`; `pytest 8.2.2` is visible; 77 focused Autonomous Lab tests passed |
| Whitespace check | Passed with warning | `git diff --check` completed; Git reported an existing LF-to-CRLF warning on an unrelated modified file |
| Working tree safety | Passed with caution | Existing modified/untracked files remain untouched except this tracker |

Phase 0 decision: proceed to P1-S1 visual mockup and UI contract. Do not start product implementation until the relevant screen mockup is approved.

## 9. Phase 1 - Grounded Web PoC

Phase objective: demonstrate one governed eSIM or postpaid activation journey from requirement intake through deterministic evidence using grounded web automation.

### P1-S1 Command Centre Foundation - 1 screen

Screen: **Executive Overview**.

- [ ] Requirement, test, discovery, automation, execution and evidence lifecycle summary.
- [ ] Active project and environment context.
- [ ] Approval, mapping, readiness and evidence blockers.
- [ ] Current runs and recent deterministic outcomes.
- [ ] Integration maturity labels and feature status.
- [ ] Navigation into every Phase 1 workflow.

Dependencies: P0-S1 through P0-S4.

### P1-S2 Requirement Intelligence Core - 3 screens

Screens: **Requirement Intake**, **Requirement Analysis**, **Requirement Traceability**.

- [ ] Ingest BRD, requirements, designs, process flows, test plans, test cases, user stories, acceptance criteria, API specifications, schemas, taxonomy documents, scripts, results, defects, incidents and standards.
- [ ] Support approved DOCX, PDF, XLSX, CSV, JSON, YAML and configured export formats.
- [ ] Extract structured, versioned requirements and source locations.
- [ ] Detect ambiguity, missing information, duplicates and conflicts.
- [ ] Classify Business Domain, Customer Segment, Customer Type, Product Group, Product, Request Type, Sub Request Type, Channel, Application, Test Type, Scenario Type and Risk Level.
- [ ] Display taxonomy retrieval sources and reviewer corrections.
- [ ] Retrieve similar requirements, tests, scripts, incidents and defects.
- [ ] Maintain requirement version and provenance.
- [ ] Trace requirement to tests, applications, automation, executions, evidence and defects.

### P1-S3 Test Design and Approval - 4 screens

Screens: **Generated Test Cases**, **Test Case Editor**, **Journey Graph**, **Test Case Approval**.

- [ ] Generate positive, negative, boundary, exception, concurrency, timeout, rollback, recovery, duplicate, partial-failure, asynchronous-callback and data-inconsistency scenarios.
- [ ] Preserve classifications, taxonomy references and source evidence.
- [x] Define preconditions, steps, expected results, data needs, evidence needs, application roles and automation preference.
- [ ] Detect duplicates and missing coverage.
- [ ] Require an independent approval decision.
- [ ] Validate mappings to stable Application Registry IDs.
- [ ] Route missing applications to onboarding and ambiguous mappings to mapping review.
- [ ] Disable Proceed to Discovery until mandatory mappings are valid.
- [ ] Prevent URLs and credentials from entering approved test cases.

**Test Automation Classification & Routing (2026-07-23):** governed, policy-driven automation
candidacy classification extending all 4 P1-S3 screens end to end — deterministic rules engine
+ governed LangGraph classification agent (advisory only, never overrides a blocker) +
capability resolver (against real `MCPConnection` rows, never a static list) + weighted scoring,
producing immutable versioned `TestCaseAutomationClassification` records with a reviewer
correction stage (UI-011) and an independent approval gate (UI-013) separate from test-case
approval itself. New backend: migration `040_automation_classification.py`, 4 tables, `/api/v1/
automation-classifications/*` (flag-gated, isolated namespace, disabled by default), permissions
`automation_classification.*`. UI-010 shows classification status + a policy/simulation drawer,
UI-011 adds an Automation Readiness reviewer-correction panel, UI-012 adds an Automation
inspector tab + graph node status dots, UI-013 adds a governance check + full decision panel
(Approve / Approve Conditional / Not Recommended / Defer / Request Changes). Verified live
against real project-1 data with the flag on and off (see
`docs/test-automation-classification-routing-implementation-prompt.md` for the full spec).
Explicitly out of scope this pass: UI-015 wiring (needs this contract, not yet consumed) and the
Phase 3 policy-administration screens (UI-055/056/057) — Phase 1 only has the read/simulate/
limited-edit drawer described above.

### P1-S4 Application Discovery - 4 screens

**UI-017 API and Network Explorer — Phase 1 (2026-07-25):** governed request browser built on
the only structured signal the current discovery capture pipeline can honestly produce. New
backend: migration `045_network_events.py` (2 tables: `network_events`, `network_event_activity`),
`network_event_service.py` — a regex parser confirmed against a real live capture (the actual
`@playwright/mcp` `browser_network_requests` tool numbers each entry, e.g. `"12. [GET] url =>
[200]"`; an initial parser without that numbered-list prefix marked every real request
`unparsed` until fixed and re-verified live) that turns a session's masked `network_log`
`DiscoveryCapture` text files into structured method/URL/host/status rows, idempotent
rebuild-in-place, KPI computation, and per-request review actions (mark reviewed/ignored) with
audit logging. `/api/v1/lab/network-explorer/*` (flag-gated on `NETWORK_EXPLORER_ENABLED`,
disabled by default), permissions `network_explorer.*`. Frontend: `NetworkExplorerView.tsx` at
`/applications?view=api-network`, new sidebar entry. Requests, correlation to the owning
`DiscoverySession`/`DiscoveryAction` (screen/test-step), review/ignore actions, evidence viewing
(reuses UI-015's existing capture-content endpoint) and sanitized export are real and
backend-authoritative. Headers, request/response bodies, timing/waterfall, API/DB validators,
external-system MCP mapping and publishing relationships into the Application Model are visibly
present but disabled with an honest reason (the MCP capture tool never reports headers/bodies/
timing at all, and no validator or publish pipeline exists yet — the same
visible-but-disabled pattern UI-016 used for its own APIs/External Systems tabs). Backend: 11
new focused tests pass (`test_network_event_service.py`), full suite 1098/1109 passing (the
same 5 pre-existing unrelated failures confirmed by UI-016's stash-and-compare remain, nothing
new broken). Frontend typecheck/lint/build clean. Verified live against real project-1 discovery
session data (24 captured lines, 20 parsed / 4 honestly-unparsed non-request lines, 12 distinct
APIs, 2 external hosts, 100% action-linked) including a live regex bug found and fixed during
verification, plus review and export actions confirmed via direct authenticated API calls.

Screens: **Application Registry**, **Live Discovery Session**, **Application Model**, **API and Network Explorer**.

- [ ] Register, search, filter, edit and archive applications.
- [ ] Store stable ID, aliases, type, domains, channels, owners, environments, auth profiles, frameworks, dependencies, health checks, AVD needs and discovery capability.
- [ ] Associate product groups, products, customer segments/types, request/sub-request types and channels.
- [ ] Seed the eight approved applications idempotently without overwriting authorized changes.
- [ ] Select application, environment, browser/device/AVD and approved authentication profile.
- [ ] Support guided, free and supervised agent-driven discovery/recording modes.
- [ ] Capture DOM, accessibility tree, mobile hierarchy, WebViews, screens, components, elements, navigation, network, APIs, console, timing and screenshots.
- [ ] Build versioned application-model and journey relationships.
- [ ] Expose tree, graph, details, history, comparison, approval and impact views.
- [ ] Link API requests/responses and schema details to screens, steps and IR actions.

**UI-016 Application Model — Phase 1 (2026-07-25):** governed, versioned Application Model
built from completed Live Discovery Session evidence. New backend: migration
`044_application_models.py` (6 tables: `application_models`, `application_model_nodes`,
`application_model_edges`, `application_model_locator_evidence`, `application_model_gaps`,
`application_model_activity`; converts `discovery_sessions.draft_model_version_id` from a
placeholder column into a real FK), `application_model_service.py` (build/rebuild-in-place from
`DiscoveryAction.target_screen_ref`/`target_component_ref`/`target_element_ref`, deterministic
gap detection, ADR-001-style version chain, separation-of-duties approval reusing
`ApprovalAction`), `/api/v1/lab/application-models/*` (flag-gated on
`APPLICATION_MODELS_ENABLED`, disabled by default), permissions `application_model.*`. Frontend:
`ApplicationModelView.tsx` at `/applications?view=model`, new sidebar entry. Screens, components,
elements, locator evidence and gaps are real and backend-authoritative; Journeys, APIs/External
Systems, Evidence viewing, Change Comparison, KB projection and node merge/split are visibly
present but disabled with an explanation (no backing data source yet — needs UI-017 and a
network-log parser that doesn't exist). Verified live against real project data: build → resolve
gap → submit for review → separation-of-duty block → approve as a second user → publish →
immutability → create new draft → rebuild-in-place, all through the real API with two real user
accounts. Backend: 7 new focused tests pass (`test_application_model_service.py`), full suite
1088/1093 passing (5 pre-existing unrelated failures confirmed via stash-and-compare). Frontend
typecheck/lint/build clean.

### P1-S5 Automation Studio Core - 5 implementation screens

Screens: **Automation Workspace**, **Live Recorder**, **Automation IR Editor**, **Script Editor**, **Validation and Review**.

The six-page Automation Studio design pack must also include **Framework Configuration**, implemented in P2-S3.

- [ ] Show project, application, environment, framework, test, journey, assets, executions and issues in one workspace.
- [ ] Implement all three recording modes and the complete state machine in Section 15.
- [ ] Capture structured actions as the primary generation source.
- [ ] Keep video optional and supporting-only.
- [ ] Produce versioned, validated Automation IR.
- [ ] Compile Phase 1 IR through the existing deterministic Playwright path.
- [ ] Support code/file tree, run, debug, console, results, provenance, requirement/IR links, diff and live replay.
- [ ] Apply static, security, hard-coded-data, locator-quality, assertion, backend-evidence and negative-coverage checks.
- [ ] Enforce generator/reviewer separation.
- [ ] Support reject, request changes, approve and publish decisions.

**UI-018 Automation Workspace — Phase A (2026-07-26):** implemented against
the final consolidated UI-018 contract, which supersedes the earlier
per-test-case build. The contract establishes **Automation Test Suite** as a
first-class aggregate — an orchestration container over selected test cases
where application, framework, script, environment and traceability data is
*inherited read-only* from authoritative sources and never re-entered.

The earlier Phase 1 aggregate (`automation_workspaces` +
`automation_workspace_blockers` + `automation_workspace_activity`) was
**retired**: it was scoped to one test case × environment, which cannot
express suite membership or cross-member conflicts. Its readiness *logic* was
preserved and relocated — all 10 checks port 1:1 with their reason,
remediation, severity and stage strings intact (parity is pinned by tests) —
now evaluated per suite member and persisted as gap rows on the suite. The
uncommitted `046_automation_workspaces.py` was downgraded out of the dev DB
and replaced by `046_automation_suites.py`, so head stays at 046 with no
orphan revision.

New backend: `046_automation_suites.py` (4 tables: `automation_suites`,
`automation_suite_test_cases`, `automation_suite_gaps`,
`automation_suite_activity`) and the `services/automation_suite/` package.
Its defining structure is that **`inheritance.py` is the only module that
queries for evaluation; readiness, conflict detection, gap planning and status
are pure functions over frozen dataclasses.** That is what bounds cost: one
`evaluate_suite` pass measured 14 SQL statements for 2 members and 15 for 13
members (scaling with distinct applications, not member count — a naive
per-member port would have issued ~130).

Suite-level capabilities the per-test-case engine could not provide:
cross-member conflict detection (`MULTIPLE_FRAMEWORKS`,
`MULTIPLE_ENVIRONMENTS`, `MIXED_MANUAL_AUTOMATED`), and gap **adjudication** —
`plan_gap_sync` upserts by fingerprint and auto-closes what it no longer
detects, but never deletes, because a suite gap carries `exception_approved` /
`resolution_action` / `reviewer_notes` / `first_detected_at` that a
delete-and-rebuild would silently discard (the retired engine wiped its
blockers each pass, which was only safe because they held no human decision).
Fingerprints key on stable identity — `LOCATOR_MISSING` keys on the model, not
the Application Model gap-id list, which churns on every rebuild and would
otherwise orphan an approved waiver. Waived and excluded findings stop
blocking at *both* member and suite level, so "approve exception" and "exclude
test case" genuinely advance status.

7 of the contract's 13 statuses are reachable and deterministic (`DRAFT`,
`SCOPE_SELECTED`, `MAPPING_INCOMPLETE`, `CONFLICT_REVIEW_REQUIRED`,
`INHERITANCE_REVIEW_REQUIRED`, `READY_FOR_VALIDATION`, `ARCHIVED`); the other
6 need UI-023 validation, the approval workflow or immutable snapshots and are
reserved in the CHECK constraint so Phase B needs no migration.
`/api/v1/lab/automation-suites/*` (23 routes, flag-gated on
`AUTOMATION_SUITE_ENABLED`, disabled by default), 10 `automation_suite.*`
permissions with `approve_exception` under `APPROVE_TEST_CASES` rather than
`GENERATE_AUTOMATION` — waiving a readiness gap is a governance decision.
Wizard step 1 is server-side paginated; suite creation is idempotent on a
client-supplied key so a refresh or double-submit cannot create two suites.

Frontend: `AutomationSuiteDashboard.tsx` (landing), `AutomationSuiteDetail.tsx`
(drill-in) and `NewAutomationSuiteWizard.tsx` (6-step), sharing
`suite-shared.tsx`, at `/automation?view=workspace`,
`?view=workspace&suite=<id>` and `?view=workspace-new`. Detail tabs Overview /
Test Cases / Inherited Scope / Conflicts and Gaps are live; Execution Groups,
Automation Assets, Test Data, Executions, Evidence and Versions are visibly
disabled with the reason, per the UI-016/017 pattern.

**Two rules deliberately not invented.** Environment resolves from the
suite-owned default only — deriving it from `test_data.environment` was
rejected because "test data exists for env X" is not "this test case runs in
env X", and that is also why the selection filters expose no environment
filter. `UNSUPPORTED_FRAMEWORK_APPLICATION` is reserved but never raised: no
framework/application pairing matrix exists anywhere in this repo, so
authoring one would be a guessed business rule surfaced as a governance
finding.

**Honest degradation** (contract element → missing source): Framework Profile
identity/version → no `framework_profile` table (UI-022, P2-S3), so the plain
`automation_scripts.framework` string is shown sourced to the script;
Automation IR → no entity (UI-020); page objects, reusable components, API
collections, object repositories, git repositories → no entities; change
requests → no entity at all; releases → free-text on the test case, not a
link; evidence tab/policy → no evidence entity; execution↔suite linkage → no
FK, so `ExecutionRun.suite_name` is emitted verbatim with
`suite_link_available: false` and success rate is labelled project-wide;
`Blocked`/`Inconclusive` execution states → not values of
`ExecutionRun.status` (the real `review_required` is exposed under its own
label); validation-pending KPI → no validation subsystem; execution groups,
schedule, approvals, snapshots, versions, impact review → Phase B; environment
health and storage usage → no subsystems (agent availability *is* real from
`mcp_connections`). Each is returned as `null` with a stated reason in an
`unavailable` map and rendered as an explained dash, never as `0`.

Backend: 88 new focused tests pass across 7 modules (readiness incl. parity
ports, conflicts, gap-sync planning, status precedence, service, dashboard
honest-nulls, grounding); full suite 1186 passed / 5 failed — the same 5
pre-existing unrelated failures (Jira import, security middleware) recorded in
UI-016/017. Frontend typecheck/lint/build clean. Verified live against real
project-1 data: migration round-tripped 045↔046; suite created from 2 approved
test cases landed `MAPPING_INCOMPLETE` with 4 real critical gaps and 3
warnings; the project-default application fallback resolved so no spurious
mapping gap; replaying the idempotency key returned the same suite and created
nothing; duplicate active name 409'd; waiving all 4 criticals advanced the
suite to `READY_FOR_VALIDATION` and the waivers survived re-evaluation
un-reopened; archive and double-archive/evaluate-archived guards returned 409;
inherited scope showed every item with a real source label
("Inherited from TC-0008", "Derived from linked script framework
'playwright'"); export, activity and member grounding all returned real data.

**UI-018 Automation Workspace — Phase B (2026-07-26):** migration
`047_automation_suite_phase_b.py` (additive: `automation_suite_execution_groups`,
`automation_suite_snapshots`, `execution_group_id` on
`automation_suite_test_cases`, and the approval audit columns on
`automation_suites`), plus `services/automation_suite/execution_groups.py` and
`lifecycle.py`. 37 routes total; 6 new permissions, with `review`/`approve`/
`publish` under `APPROVE_TEST_CASES` and group management under
`GENERATE_AUTOMATION`.

Four capabilities, all backed by real data:

*Execution groups* — `plan_auto_split` (pure) groups members by an inherited
discriminator (framework, environment or application). This is what finally
makes `split_execution_groups` a real resolution instead of a 422: splitting a
`MULTIPLE_FRAMEWORKS` conflict into one group per framework resolves it without
touching anything at source. A member with no script lands in an honestly
labelled "unmapped" group carrying no invented framework.

*Approval workflow* — submit / request changes / reject / approve / publish,
mirroring `application_model_service` so governance reads the same across
UI-016 and UI-018, including the separation-of-duty rule (the submitter cannot
approve) and the critical-findings-must-be-clear gate. The key structural
addition is `WORKFLOW_OWNED_STATUSES`: once a suite is in review, approved or
published, evaluation refreshes its rollup and findings but **must not**
recompute its status, otherwise the next evaluation pass would silently undo an
approval. `READY_FOR_REVIEW`, `APPROVED`, `PUBLISHED` and `DEPRECATED` are now
reachable — 11 of 13 statuses; only `VALIDATION_PENDING`/`VALIDATION_FAILED`
remain reserved, pending UI-023.

*Immutable snapshots* — publication writes an `AutomationSuiteSnapshot` holding
each member's resolved source ids and versions plus a sha256 over a canonical,
order-independent payload, and never updates it. A published suite is frozen:
membership, rename and re-split all return 409 `SUITE_IMMUTABLE`.

*Versions and impact review* — `create_new_draft` opens version n+1 copying
membership, marks the prior version not-current, and keeps the chain rooted at
`parent_suite_id`. Impact review compares a published suite's snapshot against
live sources and emits `SNAPSHOT_DRIFT` findings; because gaps upsert rather
than delete, restoring the source auto-closes the finding while preserving its
`first_detected_at`. Execution groups are deliberately *not* copied to a new
version — a new version re-splits, and copying would leave grouping decisions
attributed to a scope that has since changed.

**Deliberately not built, with the reason.** Schedule, parallelism, retry,
timeout, evidence policy, notification rules and agent-pool preference are all
execution-time concerns, and there is no suite-to-execution path: `execution_runs`
has no FK to a suite, no runner integration consumes one, and Celery beat only
carries retention jobs. Storing policy that nothing honours would misrepresent
it, so the Execution Groups tab lists each with its reason instead. Wiring real
dispatch belongs with P1-S7 Execution and Evidence.

Backend: 117 focused tests across 9 modules (29 new for Phase B covering split
planning, every approval transition, separation of duty, snapshot determinism
and immutability, the version chain and drift detection); full suite 1216 passed
/ 5 failed — the same 5 pre-existing unrelated failures. Frontend
typecheck/lint/build clean; the Execution Groups and Versions tabs are now live
(Automation Assets, Test Data, Executions and Evidence remain honestly disabled).

Verified live end to end on project 1: migration 047 round-tripped; suite split
into 2 real framework groups; submitted for review; **the submitter's own
approval was refused 409 `SEPARATION_OF_DUTY_VIOLATION`**; a second real user
approved and published; the snapshot froze 2 members and 2 groups with a
64-char checksum; all three mutation paths on the published suite returned 409
`SUITE_IMMUTABLE`; bumping a real test case's version produced an impact finding
while the snapshot stayed **byte-identical** (same checksum); evaluating the
published suite recorded `SNAPSHOT_DRIFT` and left the status at `PUBLISHED`;
a new version opened as v2 with membership copied, v1 marked not-current, and
v2's findings requiring their own adjudication rather than inheriting v1's
waivers; restoring the source auto-closed the drift finding with its
`first_detected_at` intact.

**UI-019 Live Recorder (2026-07-27):** implemented against the approved
UI-019 contract and reference image. Migration `048`, additive only: seven
columns on `discovery_sessions` (suite/member link, recording mode and origin,
IR status, version chain) and seven new tables — step states, step mappings,
validation checkpoints, segments, data bindings, notes, and
`automation_ir_drafts`.

The capture engine is **not** duplicated. A Live Recorder run *is* a
`DiscoverySession`: UI-015's state machine, `DiscoveryAction` rows,
`DiscoveryCapture` evidence and `DiscoverySessionEvent` audit trail are reused
unchanged (contract Section 29 forbids duplicating them, and a second
implementation would fork the only code that actually observes a browser).
Network activity in the recorder reuses UI-017's parser; inherited context
reuses UI-018's `inheritance.resolve_suite_inheritance`.

Interaction model, stated plainly because the reference image implies
otherwise: the centre panel is a **proxied viewport**, not an embedded
browser. The application runs headless via Playwright-MCP on the backend host,
so the panel shows the real screenshot it just took plus the real
accessibility tree it just read; the user selects a real element and names an
action, and the backend performs it against the live application. Every
recorded action is one the platform genuinely executed. Native click capture
would need screencast/VNC infrastructure that does not exist and was not in
scope.

The emitted Automation IR is `AutomationGenerationContract` — the same
validated, framework-neutral structure the script compiler already renders to
Playwright and pytest. Recording became a second way to produce one, so a
recorded test case reaches runnable code with no new format. Verified live: a
recording driven entirely through the UI produced a draft that compiled to
`IndexHtmlPage.ts` plus a spec filling a test-data fixture and asserting the
URL. The emitter never guesses — an action with no observed locator becomes a
`custom` step (a visible TODO), only user-accepted checkpoints become
assertions, and everything unresolved is listed in `readiness`.

Deliberate scope limits, each surfaced in the UI rather than hidden: mobile
and desktop adapters (none exist — a member resolving to one is blocked with
that stated), video and trace capture (Playwright-MCP does not expose them),
and Section 23's "Compare Against Existing Script". A member left `BLOCKED` by
suite evaluation is an **advisory, not a blocker** — the two common causes are
"no automation classification" and "no approved Application Model", neither of
which prevents driving a browser, and recording is one of the ways those gaps
get closed; blocking on it would have been circular.

Backend: 124 focused tests across 4 modules; full suite 1344 passed with the
same 3 pre-existing failures (`test_jira_foundation` ×2,
`test_security::test_xss_attempt_in_json_body`), confirmed identical at
unmodified HEAD via a throwaway worktree. Frontend lint/typecheck/build clean.
Live-verified end to end in the browser against real suite data.

Remaining for P1-S5: UI-020 Automation IR Editor, UI-021 Script Editor,
UI-023 Validation and Review.

### P1-S6 Test Data Selection - 1 screen

Screen: **Data Search and Selection**.

- [ ] Search approved data sources by scenario eligibility.
- [ ] Mask PII and enforce row/result limits.
- [ ] Reserve or lock exclusive records.
- [ ] Issue time-bound leases linked to execution.
- [ ] Preserve source, lineage, environment and eligibility evidence.
- [ ] Prevent agents from receiving unrestricted database credentials.

### P1-S7 Execution and Evidence - 2 screens

Screens: **Live Execution Monitor**, **Execution Report and Evidence**.

- [ ] Require environment, application, data, framework and worker readiness before start.
- [ ] Execute the approved Phase 1 journey on compatible infrastructure.
- [ ] Stream persisted progress with correlation IDs.
- [ ] Support pause, resume, stop, cancel and emergency termination where applicable.
- [ ] Collect UI, DOM, accessibility, API, database, event, log, trace, screenshot and optional video evidence.
- [ ] Evaluate deterministic business assertions across order, billing, charging, inventory and provisioning as configured.
- [ ] Apply journey-specific evidence quorum.
- [ ] Produce PASS, FAIL, INCONCLUSIVE, BLOCKED, ENVIRONMENT_FAILURE, DATA_FAILURE, AUTOMATION_FAILURE or POLICY_BLOCKED.
- [ ] Build complete requirement-to-defect evidence lineage.

Phase 1 exit criteria:

- [ ] All 20 screen implementations accepted.
- [ ] One approved eSIM or postpaid journey completes end to end.
- [ ] No action is generated without grounding evidence.
- [ ] No run starts without readiness.
- [ ] Missing evidence produces `INCONCLUSIVE`.
- [ ] Existing Automation Studio behavior remains unchanged.
- [ ] Existing and new regression suites pass.

## 10. Phase 2 - Enterprise Core

### P2-S1 Operational Command Centre - 3 screens

Screens: **Environment Health**, **AVD Operations**, **Live Executions**.

- [ ] Monitor telecom and automation service dependencies.
- [ ] Display HEALTHY, DEGRADED, UNAVAILABLE, MAINTENANCE, UNKNOWN, DEPENDENCY_FAILURE, AUTHENTICATION_FAILURE and CAPACITY_EXHAUSTED.
- [ ] Display READY, READY_WITH_WARNINGS, NOT_READY and READINESS_UNKNOWN.
- [ ] Show AVD fleet totals, availability, utilisation, queues, waits, duration and capacity by environment/framework.
- [ ] Expose authorized, audited fleet and execution controls.

### P2-S2 Requirement Governance - 1 screen

Screen: **Requirement Review and Approval**.

- [ ] Review quality findings, ambiguity and classification corrections.
- [ ] Approve or reject a version without erasing history.
- [ ] Initiate graph-based change impact for approved changes.
- [ ] Record decision, actor, reason, policy and evidence.

### P2-S3 Framework and Reusable Assets - 3 screens

Screens: **Framework Configuration**, **Reusable Asset Catalogue**, **Asset Versions and Impact**.

- [ ] Complete the six-page Automation Studio module.
- [ ] Configure approved frameworks, versions, languages, runners, browsers, devices, timeouts, traces, screenshots, reports and secret references.
- [ ] Validate dependency, licence and environment compatibility.
- [ ] Register reusable pages, components, locators, keywords, API clients, DB assertions, data builders, utilities and business assertions.
- [ ] Track versions, provenance, owners, approvals, dependants, usage and rollback.
- [ ] Support Playwright, Katalon, Appium and appropriate UiPath adapter contracts.

### P2-S4 Existing Script Maintenance - 4 screens

Screens: **Script Inventory**, **Static Analysis**, **Dynamic Health**, **Maintenance Campaigns**.

- [ ] Inventory approximately 2,000 Katalon and Appium scripts without bulk rewriting.
- [ ] Parse repositories, frameworks, versions, applications, channels, locators, reusable assets, data sources and dependencies.
- [ ] Link scripts to requirements and business journeys.
- [ ] Detect duplicates, credentials, hard-coded data, weak XPath, fixed sleeps, missing assertions, unsupported capabilities, obsolete libraries, insecure logging and version drift.
- [ ] Establish dynamic execution baselines and health states.
- [ ] Prioritize weekly work from requirement/UI/API/DB/catalogue changes, failures, flakiness, vulnerabilities, critical journeys, shared-asset centrality and staleness.
- [ ] Generate controlled repair proposals, validate representative impacted journeys, create PRs and preserve rollback versions.

### P2-S5 Test Data Lifecycle - 3 screens

Screens: **Data Creation and Certification**, **Lease Operations**, **Capacity, Cleanup and Quarantine**.

- [ ] Create synthetic, negative and boundary data with referential integrity.
- [ ] Retrieve through allow-listed APIs, views, stored procedures and parameterized queries.
- [ ] Implement AVAILABLE, RESERVED, IN_USE, CONSUMED, DIRTY, REPAIR_REQUIRED, QUARANTINED and EXPIRED states.
- [ ] Support certification, lease heartbeat, expiry, release and execution-created data.
- [ ] Schedule cleanup, repair or quarantine.
- [ ] Forecast environment-specific capacity.
- [ ] Audit all data access and writes.

### P2-S6 Script Dependency Graph - 1 screen

Screen: **Script Dependency Graph**.

- [ ] Model repositories, projects, scripts, tests, keywords, page/screen objects, locators, libraries, versions, data and environments.
- [ ] Support CALLS, IMPORTS, USES_LOCATOR, USES_KEYWORD, READS_DATA_FROM, DEPENDS_ON_VERSION, DUPLICATES, IMPLEMENTS, COVERS and EXECUTED_BY.
- [ ] Calculate centrality, dependency and impact paths.

### P2-S7 Execution Planning and Assignment - 3 screens

Screens: **Execution Planner**, **Intelligent Scheduler and Queue**, **Run Details and Assignments**.

- [ ] Plan application, environment, framework, evidence, data and capacity needs.
- [ ] Match framework/version, OS, access, CPU, memory, browser, device, licence, locality, load, reliability, priority, criticality and security classification.
- [ ] Never assign an incompatible or unhealthy AVD.
- [ ] Persist assignment, step execution and progress events.
- [ ] Support authorized reroute, reserve, release, drain, pause, resume, terminate, quarantine and diagnostics.

Phase 2 exit criteria:

- [ ] Cumulative 38 screens accepted.
- [ ] Framework Configuration completes the six-page Automation Studio.
- [ ] Existing script maintenance is impact/risk-based, never bulk overwrite.
- [ ] Test Data Fabric state and lease invariants pass concurrency tests.
- [ ] Distributed execution rejects incompatible workers.

## 11. Phase 3 - Autonomous Enterprise

### P3-S1 Taxonomy and GraphRAG - 4 screens

Screens: **Taxonomy Explorer**, **Taxonomy Ingestion**, **Retrieval Workbench**, **Taxonomy Governance and Coverage**.

- [ ] Navigate the canonical hierarchy and parallel dimensions.
- [ ] Ingest, parse, normalize, validate, deduplicate, detect conflicts, approve, chunk, embed, relate and publish taxonomy versions.
- [ ] Use hybrid PostgreSQL, pgvector, metadata and graph retrieval.
- [ ] Preserve source citations, retrieval events and reviewer corrections.
- [ ] Exclude deprecated or unapproved taxonomy from generation.
- [ ] Report taxonomy and test-coverage gaps.

### P3-S2 Graph Engineering - 5 screens

Screens: **Agent and Work Graph**, **Telecom Knowledge Graph**, **Application and Journey Graph**, **Environment and AVD Graph**, **Evidence, Causality and Impact**.

- [ ] Model agent delegation, review, invocation, approval, escalation, shared state and prohibited calls.
- [ ] Model typed work nodes from requirement intake to reporting with timeouts, retries, completion, failure, approval and rollback.
- [ ] Model the canonical telecom ontology and stable-ID relationships.
- [ ] Model discovered applications, screens, components, actions, APIs, decisions, failures and recovery paths.
- [ ] Model environments, services, certificates, VPN, frameworks, AVDs, devices and capabilities.
- [ ] Model evidence lineage, correlation, causality, reproduction and resolution.
- [ ] Version and approve graph changes.
- [ ] Enforce project/security boundaries during traversal.

### P3-S3 Healing and Defect Intelligence - 4 screens

Screens: **Failure Diagnosis**, **Healing Proposals**, **Defect Candidates**, **Replay and Retest**.

- [ ] Classify automation, data, environment, application, policy and evidence failures separately.
- [ ] Require evidence, previous/proposed implementation, confidence, impact, dependants, differential results, reviewer, approval, version and rollback for healing.
- [ ] Prevent genuine application failures from being healed as automation defects.
- [ ] Never silently overwrite approved code or shared assets.
- [ ] Create reviewable defect candidates only after deterministic classification.
- [ ] Support replay capsules, RTC/Jira adapter flows, synchronization and retest requests with explicit maturity labels.

### P3-S4 Reporting and Release Governance - 2 screens

Screens: **Reports and Analytics**, **Release Quality Gate**.

- [ ] Provide management, engineering, telecom operations and automation-health views.
- [ ] Retain requirement/test/taxonomy/application-model/IR/script versions, environment, build, worker, framework, data lease, agents, models, policies and evidence.
- [ ] Support controlled exports with project authorization and privacy policies.
- [ ] Produce deterministic release-quality assessments and approval gates.

### P3-S5 Administration and Governance - 4 screens

Screens: **Policy and Autonomy Control**, **Agent, Model, Prompt and Tool Registry**, **Integration and Adapter Administration**, **Audit, Security and Retention**.

- [ ] Support A0 Manual, A1 Assistant, A2 Supervised, A3 Bounded Autonomous, A4 Closed-Loop Non-Production and A5 Highly Autonomous Assurance.
- [ ] Default to A3 generation/maintenance, A4 controlled non-production execution, A2 defects and A1/A2 production-connected actions.
- [ ] Implement RBAC, project/environment isolation, least privilege and secure secret references.
- [ ] Implement prompt-injection and untrusted-content controls.
- [ ] Implement tool/network/filesystem/container allow-lists.
- [ ] Register and version agents, models, prompts, tools and policies.
- [ ] Implement plan-drift, critic, risk, destructive-action approval, rollback and kill switches.
- [ ] Apply PII masking and screenshot/video redaction.
- [ ] Enforce data classification and retention.

### P3-S6 Alerts and Incidents - 1 screen

Screen: **Alerts and Incidents**.

- [ ] Aggregate environment, capacity, policy, evidence, agent, AVD, security and integration alerts.
- [ ] Support severity, ownership, acknowledgement, escalation, correlation and resolution.
- [ ] Preserve immutable incident and action audit.

Phase 3 exit criteria:

- [ ] All 58 screens accepted.
- [ ] Full graph, taxonomy, impact, bounded healing, release gate and governance capabilities verified.
- [ ] Every autonomous loop has limits, stopping conditions, escalation, rollback and kill switch.
- [ ] All integrations accurately report maturity and configuration.

## 12. Complete 58-screen tracking register

Use `-` for not applicable and add approval/evidence links when work starts.

| ID | Phase | Section | Screen | Mockup | Approved | Contract | Backend | Frontend | Tests | Evidence |
|---|---:|---|---|---|---|---|---|---|---|---|
| UI-001 | 1 | P1-S1 | Executive Overview | [x] | [x] | [x] | [ ] | [x] | [x] | [x] |
| UI-002 | 2 | P2-S1 | Environment Health | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-003 | 2 | P2-S1 | AVD Operations | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-004 | 2 | P2-S1 | Live Executions | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-005 | 3 | P3-S6 | Alerts and Incidents | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-006 | 1 | P1-S2 | Requirement Intake | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-007 | 1 | P1-S2 | Requirement Analysis | [x] | [ ] | [x] | [ ] | [x] | [x] | [ ] |
| UI-008 | 1 | P1-S2 | Requirement Traceability | [x] | [ ] | [x] | [ ] | [x] | [x] | [ ] |
| UI-009 | 2 | P2-S2 | Requirement Review and Approval | [x] | [ ] | [x] | [ ] | [x] | [x] | [ ] |
| UI-010 | 1 | P1-S3 | Generated Test Cases | [ ] | [ ] | [x] | [ ] | [ ] | [ ] | [ ] |
| UI-011 | 1 | P1-S3 | Test Case Editor | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-012 | 1 | P1-S3 | Journey Graph | [x] | [x] | [x] | [x] | [x] | [x] | [x] |
| UI-013 | 1 | P1-S3 | Test Case Approval | [x] | [x] | [x] | [x] | [x] | [x] | [x] |
| UI-014 | 1 | P1-S4 | Application Registry | [x] | [x] | [x] | [x] | [x] | [x] | [x] |
| UI-015 | 1 | P1-S4 | Live Discovery Session | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-016 | 1 | P1-S4 | Application Model | [x] | [x] | [x] | [x] | [x] | [x] | [x] |
| UI-017 | 1 | P1-S4 | API and Network Explorer | [x] | [x] | [x] | [x] | [x] | [x] | [x] |
| UI-018 | 1 | P1-S5 | Automation Workspace | [x] | [x] | [x] | [x] | [x] | [x] | [x] |
| UI-019 | 1 | P1-S5 | Live Recorder | [x] | [x] | [x] | [x] | [x] | [x] | [x] |
| UI-020 | 1 | P1-S5 | Automation IR Editor | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-021 | 1 | P1-S5 | Script Editor | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-022 | 2 | P2-S3 | Framework Configuration | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-023 | 1 | P1-S5 | Validation and Review | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-024 | 2 | P2-S3 | Reusable Asset Catalogue | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-025 | 2 | P2-S3 | Asset Versions and Impact | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-026 | 2 | P2-S4 | Script Inventory | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-027 | 2 | P2-S4 | Static Analysis | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-028 | 2 | P2-S4 | Dynamic Health | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-029 | 2 | P2-S4 | Maintenance Campaigns | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-030 | 1 | P1-S6 | Data Search and Selection | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-031 | 2 | P2-S5 | Data Creation and Certification | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-032 | 2 | P2-S5 | Lease Operations | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-033 | 2 | P2-S5 | Capacity, Cleanup and Quarantine | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-034 | 3 | P3-S1 | Taxonomy Explorer | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-035 | 3 | P3-S1 | Taxonomy Ingestion | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-036 | 3 | P3-S1 | Retrieval Workbench | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-037 | 3 | P3-S1 | Taxonomy Governance and Coverage | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-038 | 3 | P3-S2 | Agent and Work Graph | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-039 | 3 | P3-S2 | Telecom Knowledge Graph | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-040 | 3 | P3-S2 | Application and Journey Graph | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-041 | 2 | P2-S6 | Script Dependency Graph | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-042 | 3 | P3-S2 | Environment and AVD Graph | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-043 | 3 | P3-S2 | Evidence, Causality and Impact | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-044 | 2 | P2-S7 | Execution Planner | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-045 | 2 | P2-S7 | Intelligent Scheduler and Queue | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-046 | 1 | P1-S7 | Live Execution Monitor | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-047 | 2 | P2-S7 | Run Details and Assignments | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-048 | 3 | P3-S3 | Failure Diagnosis | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-049 | 3 | P3-S3 | Healing Proposals | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-050 | 3 | P3-S3 | Defect Candidates | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-051 | 3 | P3-S3 | Replay and Retest | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-052 | 1 | P1-S7 | Execution Report and Evidence | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-053 | 3 | P3-S4 | Reports and Analytics | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-054 | 3 | P3-S4 | Release Quality Gate | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-055 | 3 | P3-S5 | Policy and Autonomy Control | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-056 | 3 | P3-S5 | Agent, Model, Prompt and Tool Registry | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-057 | 3 | P3-S5 | Integration and Adapter Administration | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |
| UI-058 | 3 | P3-S5 | Audit, Security and Retention | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] | [ ] |

## 13. Canonical taxonomy and Application Registry

### 13.1 Canonical hierarchy

`Business Domain -> Product Group -> Product -> Request Type -> Sub Request Type -> Business Journey`

Parallel dimensions that must remain distinct:

- Customer Segment.
- Customer Type.
- Channel.
- Application.
- Test Type.
- Scenario Type.
- Evidence Type.
- Automation Framework.
- Environment.
- Risk Level.

### 13.2 Required governance

- [ ] Stable ID and code.
- [ ] Alias support.
- [ ] Version history.
- [ ] Source and provenance.
- [ ] Draft, approval, active, deprecated and retired lifecycle.
- [ ] Effective dates.
- [ ] Owner and audit.
- [ ] Conflict and duplicate detection.
- [ ] Approved retrieval eligibility.
- [ ] Impact analysis on change.

### 13.3 Canonical relationship rules

- `CustomerSegment HAS_CUSTOMER_TYPE CustomerType`.
- `ProductGroup HAS_PRODUCT Product`.
- `Product SUPPORTS_REQUEST_TYPE RequestType`.
- `RequestType HAS_SUB_REQUEST_TYPE SubRequestType`.
- `Application SUPPORTS_PRODUCT Product`.
- `Application SUPPORTS_CHANNEL Channel`.
- `Application PARTICIPATES_IN Journey`.
- `TestCase TARGETS_APPLICATION Application`.
- `TestCase APPLIES_TO_SEGMENT CustomerSegment`.
- `TestCase APPLIES_TO_CUSTOMER_TYPE CustomerType`.
- `TestCase VALIDATES_PRODUCT Product`.
- `TestCase COVERS_SUB_REQUEST SubRequestType`.

### 13.4 Application seeds

| Stable key | Display name | Seed status |
|---|---|---|
| `APP-USP-DIRECT` | USP Direct | [ ] |
| `APP-B2B` | B2B | [ ] |
| `APP-CIM` | CIM | [ ] |
| `APP-CODE` | CoDE | [ ] |
| `APP-B2C` | B2C | [ ] |
| `APP-SALES-PORTAL` | Sales Portal | [ ] |
| `APP-SMILES` | Smiles | [ ] |
| `APP-MOBILE-APP` | Mobile App | [ ] |

Seeder acceptance:

- [ ] Idempotent.
- [ ] Stable keys never change.
- [ ] Authorized administrative changes are not overwritten.
- [ ] B2B/B2C applications remain separate from customer-segment taxonomy.
- [ ] No UI, agent or adapter depends on a hard-coded application-name list.

## 14. Automation Intermediate Representation

The versioned Automation IR must be framework-neutral and include:

- Stable ID, version, lifecycle and approval state.
- Requirement, test, journey and application references.
- Preconditions and environment requirements.
- Test-data bindings and lease requirements.
- Typed steps and semantic targets.
- Grounding references and locator evidence.
- Expected application transitions.
- Deterministic UI, API, DB, event and business assertions.
- Evidence policy and mandatory sources.
- Retry rules limited to transient conditions.
- Timeouts and asynchronous wait definitions.
- Postconditions and cleanup.
- Reusable component references.
- Security and privacy handling.
- Compiler target and framework configuration reference.
- Provenance, generator, reviewers and policy decisions.
- Diff, supersession and rollback reference.

Allowed structured action families include Navigate, Click, Input, Select, Upload, Download, Wait for condition, Read value, Call API, Query database, Validate result, Switch window, Switch frame, Switch mobile context and Perform gesture.

## 15. Recording architecture and state machine

### 15.1 Recording modes

| Mode | Purpose | Publication rule |
|---|---|---|
| Guided User Recording | User performs approved test steps; default for Phase 1 | Requires mapping/review completion |
| Free User-Action Recording | Reverse engineering, undocumented processes and reusable capture | Cannot publish until test design, purpose, mapping, assertion review and approval complete |
| Agent-Driven Recording | Supervised agent acts from approved test steps | Initially supervised; user can approve, pause, take control, correct, skip, roll back, stop or emergency-stop |

### 15.2 Persisted states

`NOT_STARTED`, `INITIALISING`, `RECORDING`, `PAUSE_REQUESTED`, `PAUSED`, `RESUMING`, `STOP_REQUESTED`, `STOPPED`, `COMPLETED`, `CANCELLED`, `FAILED`, `EMERGENCY_STOPPED`.

### 15.3 Controls and invariants

- [ ] Start.
- [ ] Pause.
- [ ] Resume.
- [ ] Stop.
- [ ] Save Checkpoint.
- [ ] Cancel/Discard.
- [ ] Emergency Stop.
- [ ] Approve Next Action for agent-driven mode.
- [ ] Take Manual Control for agent-driven mode.
- [ ] Skip or Modify Next Action for agent-driven mode.
- [ ] Roll Back for agent-driven mode.
- [ ] Persist a checkpoint before acknowledging pause.
- [ ] Stop agent tool calls during and after pause acknowledgement.
- [ ] Exclude actions performed while paused by default.
- [ ] Validate URL/screen, authentication, selected customer, order state, build, health, data lease and AVD connectivity before resume.
- [ ] Classify resumed state as UNCHANGED, NAVIGATION_CHANGED, SESSION_EXPIRED, DATA_CHANGED, APPLICATION_RESTARTED or UNKNOWN.
- [ ] Support continue, restore checkpoint, remap, restart step or stop/save after state change.
- [ ] Do not auto-publish, approve or execute on Stop.
- [ ] Revoke agent tool access immediately on Emergency Stop.
- [ ] Preserve safety evidence and audit on cancellation or emergency stop.
- [ ] Make pause/resume/stop/emergency operations idempotent.
- [ ] Prevent duplicate actions after resume.

### 15.4 Transition audit

Every transition stores session ID, actor, mode, previous state, new state, time, reason, current test step, current graph node, last completed action and evidence checkpoint.

### 15.5 Privacy

- [ ] Mask password, OTP, payment-card, PII, financial and secret fields.
- [ ] Provide screenshot and video-region redaction.
- [ ] Provide secure-input mode.
- [ ] Support evidence suppression where policy requires it.
- [ ] Replace secret entry with approved semantic actions.

## 16. Agent swarms, loops and autonomy

Required swarm domains:

- Supervisor and routing.
- Requirement intelligence.
- Application grounding and discovery.
- Script and IR engineering.
- Static, security, business-assertion and evidence review.
- Execution and readiness.
- Healing and maintenance.
- Defect intelligence and reporting.

Every agent workflow must define:

- Typed input and output.
- Permitted tools and targets.
- Maximum iterations.
- Timeout.
- Token and cost budget.
- Retry policy.
- Stopping and success conditions.
- Failure route and escalation.
- Approval requirements.
- Rollback behavior.
- Global and project kill-switch behavior.
- Version, model, prompt and policy provenance.
- Complete AgentRun and tool-call audit.

No agent may generate and approve the same asset.

## 17. Graph engineering and GraphRAG

### 17.1 Graph planes

- Execution Graph Plane.
- Knowledge Graph Plane.
- Graph Analytics and impact traversal.

### 17.2 Required graph domains

- Agent organization.
- Work and execution.
- Telecom knowledge and taxonomy.
- Application and journey.
- Script dependencies.
- Environment and AVD.
- Evidence and causality.

### 17.3 Graph controls

- [ ] Stable node and relationship IDs.
- [ ] Version and approval.
- [ ] Source and provenance.
- [ ] Project and security boundary enforcement.
- [ ] Synchronization status when an external graph engine is used.
- [ ] Retryable outbox for graph projection.
- [ ] Impact results linked back to authoritative PostgreSQL records.
- [ ] Retrieval event logs with vector, metadata and graph paths.

## 18. Environment, AVD and scheduler

### 18.1 Environment services

Monitor configured CRM, CPQ, catalogue, order, billing, charging, payment, provisioning, inventory, mediation, number management, portals, mobile backends, partner/contact-centre services and the AAF technical stack.

### 18.2 AVD model

Track ID, hostname, host pool, environment, OS, region, CPU, memory, disk, frameworks/versions, browsers, devices, robot identity, health, assignment, patch date and capacity.

States: `PROVISIONING`, `STARTING`, `AVAILABLE`, `RESERVED`, `PREPARING`, `EXECUTING`, `PAUSED`, `RECOVERING`, `DRAINING`, `PATCHING`, `OFFLINE`, `FAILED`, `QUARANTINED`, `DECOMMISSIONED`.

### 18.3 Scheduler gates

- Framework and version.
- OS, browser and device.
- Environment and application access.
- CPU, memory and capacity.
- Licence availability.
- Data locality.
- Current load and historical reliability.
- Priority and business criticality.
- Security classification.

## 19. Evidence, deterministic outcomes and diagnosis

Every execution must retain the applicable requirement, test, taxonomy, application-model, IR and script versions plus environment, build, worker, framework, data lease, agents, models, policies and evidence.

Evidence sources include screenshot, optional video, trace, DOM, accessibility, API, DB, event/message, log and deterministic assertion results.

Result rules:

- UI success alone never proves an end-to-end pass.
- Mandatory evidence quorum is journey-specific.
- Missing mandatory evidence produces `INCONCLUSIVE`.
- Environment readiness failures produce `BLOCKED`/`ENVIRONMENT_FAILURE`.
- Data failures, automation failures and application defects remain distinct.
- AI can classify and summarize but cannot independently declare the final pass.

## 20. API and event plan

| Domain | Planned endpoint family | Primary phase |
|---|---|---:|
| Status/configuration | `/api/v1/lab/status`, feature and capability metadata | 0/1 |
| Requirement intelligence | `/api/v1/lab/requirements/*` | 1 |
| Taxonomy/classification | `/api/v1/lab/taxonomy/*` | 1/3 |
| Applications/environments | `/api/v1/lab/applications/*` | 1 |
| Test approval/mapping | `/api/v1/lab/test-design/*` | 1 |
| Discovery/model/network | `/api/v1/lab/discovery/*` | 1 |
| Recording | `/api/v1/lab/recordings/*` | 1 |
| Automation IR | `/api/v1/lab/automation-ir/*` | 1 |
| Automation assets/reuse | `/api/v1/lab/automation/*`, `/assets/*` | 1/2 |
| Test Data Fabric | `/api/v1/lab/data/*` | 1/2 |
| Readiness/environment | `/api/v1/lab/readiness/*`, `/environments/*` | 1/2 |
| AVD/scheduling | `/api/v1/lab/avd/*`, `/scheduler/*` | 2 |
| Execution/evidence | `/api/v1/lab/executions/*`, `/evidence/*` | 1/2 |
| Script maintenance | `/api/v1/lab/maintenance/*` | 2 |
| Graph and impact | `/api/v1/lab/graph/*`, `/impact/*` | 2/3 |
| Diagnosis/healing | `/api/v1/lab/diagnosis/*`, `/healing/*` | 3 |
| Defects/replay/retest | existing Lab families extended compatibly | 3 |
| Reporting/release | `/api/v1/lab/reports/*`, `/release-gates/*` | 3 |
| Governance/admin | `/api/v1/lab/governance/*`, `/registries/*` | 3 |

All endpoints must define request/response schemas, project authorization, validation, idempotency where applicable, structured errors, audit events, pagination and progress semantics.

## 21. Data ownership and migration plan

### 21.1 Reuse canonical records

- Requirements and requirement source chunks.
- Test cases, history and approvals.
- Automation scripts and versions.
- Execution runs/results and step evidence where compatible.
- Agent runs/logs.
- Artifact lineage and approvals.
- Existing base test-data records.
- Projects, memberships, users and organizations.

### 21.2 Extend or introduce versioned AAF records

- RequirementVersion and TestIntentVersion where current history is insufficient.
- TestCaseVersion and TestCaseApplicationMapping.
- Complete taxonomy entities, versions, relationships, embeddings, retrieval and coverage.
- Application aliases, environments, associations and model snapshots.
- DiscoverySession, RecordingSession, RecordingAction, RecordingCheckpoint and RecordingStateTransition.
- Screen, UIElement and APIEndpoint evidence records.
- AutomationIRVersion, ReusableComponent, FrameworkArtifact and LocatorEvidence.
- ExecutionPlan, ExecutionAssignment, StepExecution and progress events.
- EvidenceArtifact, AssertionResult and evidence quorum decisions.
- DataLease and Fabric lifecycle extensions.
- HealingProposal, ImpactAnalysis and ReleaseQualityAssessment.
- Environment, services, dependencies, checks, readiness and incidents.
- AVDHost, capability, health and capacity forecast.
- GraphNode, GraphRelationship, GraphVersion and GraphApproval or equivalent authoritative metadata.

### 21.3 Migration sequence

1. Taxonomy and Application Registry foundations.
2. Requirement/test classification, versions and mappings.
3. Recording and application-model entities.
4. Automation IR and reusable assets.
5. Environment, readiness, AVD and assignments.
6. Script inventory and dependency records.
7. Graph metadata/projection and impact records.
8. Evidence quorum, healing and release assessment.

Each migration requires upgrade, downgrade, data-backfill, idempotency and production-volume tests.

## 22. Security, privacy and governance checklist

- [ ] Explicit AAF permission constants and role mapping.
- [ ] Project access check on every record and graph traversal.
- [ ] Environment authorization and production-action restrictions.
- [ ] Secure secret references with no plaintext responses.
- [ ] Prompt-injection filtering and untrusted-source isolation.
- [ ] Agent tool, filesystem and network allow-lists.
- [ ] Container and worker isolation.
- [ ] Destructive-action approval.
- [ ] Immutable structured audit with correlation IDs.
- [ ] PII masking in logs, prompts, screenshots, video, exports and evidence.
- [ ] Retention, legal hold and deletion policies.
- [ ] Model, prompt, tool, agent and policy version registries.
- [ ] Global and project kill switches.
- [ ] Emergency Stop has highest control priority.
- [ ] No credential material in generated scripts or recorded actions.
- [ ] Security regression and negative authorization tests.

## 23. Test strategy

### 23.1 Required suites per section

- Unit tests for domain rules and state machines.
- API schema, authorization, validation and structured-error tests.
- Repository/service transaction and concurrency tests.
- Migration upgrade/downgrade/backfill tests.
- Frontend component, route and interaction tests.
- Accessibility and responsive-state verification.
- Celery idempotency, retry, timeout, progress and cancellation tests.
- Adapter contract and maturity-label tests.
- Security, prompt-injection, PII and permission tests.
- Existing Automation and Lab regression tests.
- End-to-end vertical-slice demonstration.

### 23.2 High-risk invariants

- [ ] No action after pause acknowledgement.
- [ ] Emergency Stop revokes tools.
- [ ] Resume cannot duplicate actions.
- [ ] Missing evidence cannot pass.
- [ ] Unready environments cannot execute.
- [ ] Incompatible AVDs cannot receive work.
- [ ] Same agent cannot generate and approve.
- [ ] Healing cannot overwrite approved assets.
- [ ] Free recording cannot publish without approval.
- [ ] Sub Request Type cannot exist without Request Type.
- [ ] Seeder is idempotent and preserves authorized edits.
- [ ] Display-name changes preserve stable-ID traceability.
- [ ] Mock integrations are never presented as real.
- [ ] Existing functionality remains unchanged when the AAF flag is disabled.

## 24. Requirement traceability by locked baseline section

| Baseline section | Scope | Planned coverage |
|---:|---|---|
| 0 | Lock and change control | Sections 1, 3 and 28 |
| 1 | Project context and repository inspection | Sections 4, 5 and Phase 0 |
| 2 | Product vision and lifecycle | Phases 1-3 and Sections 5, 14-19 |
| 3.1 | Requirement-to-automation lifecycle | P1-S2 through P1-S7 |
| 3.2 | Supported automation technologies | P2-S3, adapter contracts and Section 20 |
| 3.3 | Existing script maintenance | P2-S4 and P2-S6 |
| 3.4 | Test Data Fabric | P1-S6 and P2-S5 |
| 4.1 | Grounded automation | P1-S4, P1-S5 and Section 14 |
| 4.2 | Deterministic pass/fail | P1-S7 and Section 19 |
| 4.3 | Independent review | P1-S3, P1-S5 and Section 16 |
| 4.4 | Controlled healing | P3-S3 |
| 5 | Discover-to-report lifecycle | P1-S2 through P3-S4 |
| 6 | Automation IR | P1-S5 and Section 14 |
| 7 | Reusable automation | P2-S3 |
| 8 | Agent swarms | Section 16 and P3-S2/P3-S5 |
| 9 | Loop engineering | Section 16 and governance tests |
| 10 | Graph engineering | P2-S6, P3-S2 and Section 17 |
| 11 | GraphRAG and taxonomy | P3-S1 and Section 13 |
| 12 | Test approval and Application Registry | P1-S3, P1-S4 and Section 13 |
| 13 | Application Discovery screens | P1-S4 |
| 14 | Automation Studio screens | P1-S5 plus P2-S3 Framework Configuration |
| 15 | Environment health/readiness | P1-S7 and P2-S1 |
| 16 | AVD operations | P2-S1 and P2-S7 |
| 17 | Intelligent Scheduler | P2-S7 |
| 18 | Script Maintenance Factory | P2-S4 and P2-S6 |
| 19 | Evidence and reporting | P1-S7 and P3-S4 |
| 20 | Enterprise capabilities | Phases 2-3 |
| 21 | Security and governance | P3-S5 and Section 22 |
| 22 | Autonomy levels | P3-S5 and Section 16 |
| 23 | Technical architecture | Section 5 and Phase 0 |
| 24 | Core data entities | Sections 13, 15, 17-21 |
| 25 | Menu structure | Section 12 and P0-S4 |
| 26 | 58-screen scope | Sections 7 and 12 |
| 27 | Delivery phases | Sections 8-11 |
| 28 | Mandatory acceptance criteria | Sections 25 and 27 |
| 29 | Required working method | Sections 6, 8 and 23 |
| 30 | Coding standards | Section 26 |
| 31 | Required deliverables | Section 27 |
| 32 | Initial response requirements | Phase 0 and this tracker |
| 33 | Final engineering rules | Sections 3, 25 and 27 |

## 25. Mandatory acceptance checklist

- [ ] Existing functionality remains unchanged.
- [ ] AAF is isolated and feature-controlled.
- [ ] Every generated UI action is grounded.
- [ ] Every test is traceable to requirements.
- [ ] Every generated test shows taxonomy sources.
- [ ] Every approved test maps to registered applications.
- [ ] Tests contain no environment URL or credential.
- [ ] Credentials are absent from prompts, scripts, recordings and evidence.
- [ ] Pass/fail is deterministic.
- [ ] Missing evidence produces `INCONCLUSIVE`.
- [ ] Environment issues produce `BLOCKED`.
- [ ] Runs cannot begin without readiness.
- [ ] AVD compatibility is checked.
- [ ] Agent workflows are versioned graphs.
- [ ] Every loop has stopping conditions.
- [ ] Every agent action is audited.
- [ ] Generator and approver are different actors.
- [ ] Healing never silently overwrites approved code.
- [ ] Healing includes impact and rollback.
- [ ] Existing scripts are not bulk-overwritten.
- [ ] Weekly maintenance is risk-based.
- [ ] Shared-component changes execute impacted journeys.
- [ ] Every run creates evidence lineage.
- [ ] Automation failures remain separate from application defects.
- [ ] Taxonomy is versioned and approved.
- [ ] Deprecated taxonomy is excluded.
- [ ] Graph nodes retain provenance.
- [ ] Graph traversal follows security boundaries.
- [ ] PII is masked.
- [ ] Global and project kill switches exist.
- [ ] Migrations are reversible.
- [ ] APIs include validation and authorization.
- [ ] Screens use the existing design system.
- [ ] Background work reports progress.
- [ ] Recording supports all three modes.
- [ ] All modes support pause, resume, stop, cancel and Emergency Stop.
- [ ] Agent-driven mode supports manual takeover.
- [ ] Pause checkpoints state.
- [ ] Stop does not auto-publish.
- [ ] Paused actions are excluded by default.
- [ ] Structured recording drives generation.
- [ ] Video is supporting evidence only.
- [ ] Sensitive actions support redaction and secure-input mode.
- [ ] Recording transitions are audited.
- [ ] Agent cannot act after pause acknowledgement.
- [ ] Emergency Stop revokes tool access.
- [ ] Resume validates application and session state.
- [ ] Unmapped actions require review.
- [ ] Free recordings cannot publish without test approval.
- [ ] Agent-driven recording begins supervised.
- [ ] Canonical classification includes all required dimensions.
- [ ] Request Type is the mandatory parent of Sub Request Type.
- [ ] Taxonomy is configurable, versioned and approval-controlled.
- [ ] Eight applications are idempotently seeded with stable IDs.
- [ ] B2B/B2C applications remain distinct from customer segments.
- [ ] Seeder preserves authorized administrative changes.
- [ ] Generated tests retain classifications, taxonomy references and source evidence.
- [ ] Application Registry supports all required associations.
- [ ] Taxonomy/application changes trigger graph impact analysis.
- [ ] No application-name hard-coding remains where registry data is available.

## 26. Engineering standards

- Typed models and explicit enums/state validation.
- Small route handlers and separated domain services.
- Transactions around state transitions and multi-record updates.
- Idempotent background jobs and control actions.
- Correlation IDs across API, jobs, agents, adapters and evidence.
- No PII or secret logging.
- Structured, documented error codes.
- Retry only transient failures; never hide defects with retries.
- Pagination or streaming for large data.
- Asset versioning and soft deletion where audit history is required.
- Explicit recording transitions and highest-priority emergency operations.
- Shared frontend components and existing design tokens.
- Tests and documentation in the same vertical slice as implementation.

## 27. Required final deliverables

- [ ] Repository assessment and gap analysis.
- [ ] Target architecture and module design.
- [ ] Database and migration implementation.
- [ ] API and event specifications.
- [ ] Automation IR specification.
- [ ] Recording architecture and state model.
- [ ] Graph ontology and workflow definitions.
- [ ] All 58 UI routes and approved components.
- [ ] Application Discovery and Automation Studio.
- [ ] Environment Health, AVD Operations and scheduler.
- [ ] Taxonomy RAG and GraphRAG.
- [ ] Script Maintenance Factory.
- [ ] Test Data Fabric.
- [ ] Security, observability and feature-flag design.
- [ ] Deployment changes.
- [ ] Unit, API, frontend, migration, integration and end-to-end tests.
- [ ] End-to-end grounded PoC.
- [ ] User and administrator documentation.
- [ ] Known limitations and integration maturity register.
- [ ] Phase 2/3 backlog closure evidence.
- [ ] Canonical taxonomy and ontology specification.
- [ ] Application seed-data specification and implementation.
- [ ] Taxonomy migration, versioning and change-control design.

## 28. Risks, dependencies and change control

| ID | Risk/dependency | Impact | Mitigation | Status |
|---|---|---|---|---|
| R-001 | Locked baseline supersedes older Lab documentation | Conflicting scope or terminology | Maintain this traceability tracker and conflict register | Open |
| R-002 | Existing taxonomy lacks required dimensions and Request Type parent | Data migration and compatibility risk | Add reversible normalized migrations and backfill validation | Open |
| R-003 | Existing ten Lab screens differ from 58-screen IA | Route and user-workflow disruption | Preserve compatibility and migrate by approved section | Open |
| R-004 | Existing Lab router is monolithic | Change coupling and review difficulty | Extract one domain router/service per vertical slice | Open |
| R-005 | Enterprise integrations are mostly mock/not configured | False readiness or misleading reports | Mandatory maturity labels and capability gates | Open |
| R-006 | Graph engine not operationally selected | GraphRAG/impact delivery risk | Graph repository abstraction and PostgreSQL authority first | Open |
| R-007 | AVD control plane details unavailable | Scheduler/control integration blocked | Contract-first adapter and simulated mode clearly labelled | Open |
| R-008 | Existing uncommitted user changes | Accidental overwrite | Preserve and isolate changes; inspect before every patch | Active |
| R-009 | Evidence/artifact volume | Storage, retention and performance risk | Retention policy, streaming, metadata indexing and approved object storage decision | Open |
| R-010 | Automation estate size and shared dependencies | Unsafe repair blast radius | Risk/graph prioritization, representative tests and rollback | Open |
| R-011 | PII in telecom screens and data | Security/compliance exposure | Secure input, redaction, masking, suppression and audit | Open |
| R-012 | Long-running agent loops | Cost, latency and runaway action risk | Budgets, timeouts, iteration limits, escalation and kill switches | Open |
| R-013 | Backend local Python test environment was broken | Backend regression tests could not be executed locally until repaired | Repointed `.venv` metadata to bundled Python `3.12.13` and verified focused tests | Resolved |

Every post-baseline scope change must record:

- Changed requirement and reason.
- Architecture and module impact.
- Entity and migration impact.
- Screen and route impact.
- API/event/adapter impact.
- Test and evidence impact.
- Security, privacy and operational impact.
- Rollback impact.
- Approval decision and effective plan version.

## 29. Approval register

| Approval ID | Scope | Version | Decision | Approver | Date | Notes |
|---|---|---|---|---|---|---|
| APR-001 | 58-screen inventory and phase/section breakdown | 1.0 | Approved | User | 21 July 2026 | Implementation tracker requested |

## 30. Change log

| Plan version | Date | Change | Author/approver |
|---|---|---|---|
| 1.0 | 21 July 2026 | Initial implementation tracker created from locked baseline and approved 58-screen section plan | Codex / user approval pending for document contents |
| 1.0.1 | 21 July 2026 | Phase 0 validation evidence recorded; P0-S1 through P0-S4 accepted; P0-S5 blocked by backend Python environment repair | Codex |
| 1.0.2 | 21 July 2026 | Backend Python environment repaired; focused Autonomous Lab tests passed; P0-S5 accepted | Codex |
| 1.0.3 | 21 July 2026 | UI-001 Executive Overview implemented from approved screen image; frontend lint, TypeScript and local route verification passed | Codex |
| 1.0.4 | 25 July 2026 | UI-016 Application Model implemented (Phase 1) from approved reference image and contract; migration 044, service, API, permissions, frontend view and sidebar entry; live-verified end to end with two real user accounts; tracker row and P1-S4 note updated | Claude |
| 1.0.5 | 27 July 2026 | UI-019 Live Recorder implemented from approved reference image and contract; migration 048 (7 additive columns + 7 tables), recorder service package, `/lab/recorder` API, 7 permissions, frontend workspace and sidebar entry; reuses UI-015's capture engine, UI-017's network parser and UI-018's inheritance rather than duplicating them; emits `AutomationGenerationContract` as the IR; 124 focused tests; live-verified end to end in the browser | Claude |

Note: this tracker's per-screen register and changelog were not kept current with every commit between 22 July and 25 July (UI-006 through UI-015 shipped in that window — see git log and `docs/autonomous-automation-lab/CLAUDE_CODE_HANDOVER.md` for what actually landed). A full resync of those rows is a separate, not-yet-started task.

## 31. Immediate next action

1. Present `UI-017 API and Network Explorer` — the last P1-S4 screen — for a reference image and UI contract.
2. Wait for explicit visual approval before implementing.
3. Note: UI-017 will need a network-log parser that doesn't exist yet (see the UI-016 P1-S4 note above) — scope that gap explicitly in the UI-017 contract rather than assuming it's available.
4. After P1-S4 is complete, move to P1-S5 Automation Studio Core.
