# Test Data Management Design

## Purpose

This document defines the architecture and phased implementation plan for adding an enterprise-grade `Test Data` module to the STLC platform in `C:\Test_AI_Agents\Test_AI_Agents\stlc-platform`.

The design is grounded in the current platform implementation and adapts proven test data management patterns to this product's existing FastAPI, SQLAlchemy, Celery, RBAC, lineage, approval, and Next.js UI architecture.

## Existing Platform Review

### Project structure

- Backend: `backend/app` with FastAPI endpoints under `backend/app/api/v1/endpoints`, SQLAlchemy models under `backend/app/models`, service-layer modules under `backend/app/services`, agent implementations under `backend/app/agents`, and Celery workers under `backend/app/worker/tasks`.
- Frontend: Next.js App Router under `frontend/src/app` with page modules for Requirements, Test Planning, Test Cases, Automation, Execution, Defects, Reports, Agents, Projects, and Settings.
- Database migrations: Alembic under `backend/alembic/versions`.
- Shared API client: `frontend/src/lib/api.ts`.

### Existing backend models

Relevant existing models already present:

- `TestCase` supports operational metadata, Jira linkage, history, and relationship to `TestData`.
- `ExecutionRun` and `ExecutionResult` already persist run metadata and evidence.
- `ApprovalAction` provides append-only approval audit.
- `ArtifactLineage` provides append-only lineage across STLC artifacts.
- `AgentRun` and Celery tasks already support asynchronous AI workflows.
- `JiraConnection`, `JiraSyncHistory`, and webhook support already exist.
- `TestData` exists today, but only as a narrow dataset shell with `valid_data`, `invalid_data`, `boundary_data`, `notes`, `status`, and a loose `metadata` field. It is not yet a full module.

### Existing APIs

Patterns already in use:

- Project-scoped listing via `/projects/{project_id}` or `/project/{project_id}` routes.
- Summary endpoints for modules like Test Cases.
- Entity-level endpoints for update, history, and async sync actions.
- Authentication and project authorization enforced through `backend/app/api/deps.py`.
- Project RBAC via `rbac_service.py`.

### Existing frontend layout and navigation

- Sidebar navigation lives in `frontend/src/components/layout/Sidebar.tsx`.
- Page style varies a bit by module, but Test Cases is the closest fit for the target Test Data UX because it already has:
  - project selector
  - summary cards
  - action toolbar
  - filter chips
  - column selection
  - inline actions
  - history panel

### Existing Test Cases module

Useful patterns to reuse:

- Rich operational metadata model
- Summary endpoint
- History view
- Jira sync action
- Column selector and view presets
- Draft editing and project-scoped filtering

### Existing Execution module

Useful patterns to reuse:

- Execution run and result lifecycle
- Agent-triggered asynchronous execution
- Traceability creation from test case to execution run and execution result

### Existing Automation module

Useful patterns to reuse:

- Async agent queueing for generation
- Approval action persistence
- External-tool integration summary patterns

### Existing Jira integration

Existing Jira foundation is strong enough for safe Test Data summary sync:

- encrypted credentials
- async sync history
- webhook support
- inbound and outbound sync patterns

Test Data should reuse this foundation but must never push sensitive payloads.

### Existing agent workflow pattern

Current agent flow:

1. API endpoint validates permissions.
2. Endpoint calls `enqueue_agent_run(...)`.
3. Celery worker dispatches a registered agent.
4. Worker persists output through `_persist_agent_artifacts(...)`.
5. Agent run status, logs, and output are stored centrally.

This pattern should be reused for `TestDataGenerationAgent`.

### Existing migration approach

- Alembic revisions extend schema incrementally.
- Models are registered through `backend/app/models/__init__.py`.
- The existing `test_data` table should be evolved by a new migration instead of introducing a parallel competing table unless a decomposition into header/detail tables is clearly needed.

## Industry Pattern Comparison

### Tricentis-style patterns

Selected:

- centralized inventory of reusable datasets
- reservation and release
- approval and controlled usage
- quality and readiness indicators

Deferred:

- deep environment cloning orchestration
- large-scale enterprise data pool orchestration

### Broadcom / CA-style patterns

Selected:

- reservation status
- single-use consumption lifecycle
- availability tracking

Deferred:

- heavyweight pool scheduling engine

### IBM Optim / Informatica patterns

Selected:

- masking-aware governance
- privacy classification
- validation before use

Deferred:

- full source-database subsetting
- full production extraction pipelines

### Delphix-style concepts

Selected:

- virtualized mindset for environment-specific copies through metadata and source-type abstraction
- masking-first safety model

Deferred:

- actual data virtualization infrastructure

### K2View-style concepts

Selected:

- business-entity-centered telecom templates
- entity payload as structured JSON

Deferred:

- full micro-database/entity-store architecture

### GenRocket / faker-based patterns

Selected:

- synthetic data generation
- template-driven generation rules
- negative/boundary/invalid modes

Deferred:

- full standalone generator framework UI

### QA automation runtime patterns

Selected:

- runtime-generated source type
- execution-aware reservation and consumption
- traceability to test runs

Deferred:

- deep runner-specific plugin contracts

## Final Capability Selection

### Included in scope now

- project-scoped Test Data list and summary
- extended Test Data data model
- Test Data template model
- manual create and update
- async AI generation request endpoint
- validation endpoint
- masking endpoint
- reserve, release, and consume endpoints
- submit, approve, reject, and history endpoints
- lineage creation
- Jira-safe summary sync fields
- frontend Test Data page with core actions

### Included with practical simplification

- Import support will begin with JSON and CSV-safe ingestion patterns and can expand to Excel parsing in follow-up work if library/runtime constraints need isolation.
- Sensitive data exposure control will rely first on API redaction and permission-aware serialization rather than a separate secrets vault.
- Reservation expiry will be persisted and enforced at service level rather than through a dedicated scheduler in the first increment.

### Explicitly deferred

- production data virtualization
- live external system provisioning
- advanced template field mapping wizard
- full bulk Excel multi-sheet UX
- configurable sharing policy engine
- automated reservation expiry background sweeper
- outbound Jira comment sync until safe summary behavior is fully wired and tested

## Final Architecture

### Domain model

Use a header-and-template-centric approach:

- `test_data`
  - one row per reusable dataset or data entity
  - stores traceability, lifecycle, reservation, privacy, payload, and quality state
- `test_data_templates`
  - reusable telecom schemas and rules
- `approval_actions`
  - immutable governance history
- `artifact_lineage`
  - traceability graph

The first implementation will keep a single `test_data` table for payload-bearing rows to minimize disruption and migration complexity.

### Core design decision

Instead of creating separate `test_data_sets` and `test_data_records` tables immediately, the first increment will model a test data asset as one persisted row with:

- a primary `data_payload_json`
- schema and validation metadata
- quality and reservation state
- traceability references

This keeps the first release aligned with the platform's current single-artifact patterns. If later needed, a follow-up migration can split header/detail storage for large batch imports.

## Data Model

### `test_data`

Planned fields:

- identity
  - `id`
  - `data_id`
  - `project_id`
  - `name`
  - `description`
  - `version`
- classification
  - `data_type`
  - `source_type`
  - `status`
  - `telecom_domain`
  - `test_phase`
  - `environment`
  - `tags`
- traceability
  - `linked_requirement_id`
  - `linked_requirement_key`
  - `linked_scenario_id`
  - `linked_test_case_id`
  - `linked_execution_run_id`
  - `linked_defect_id`
  - `linked_jira_issue_key`
  - `linked_jira_url`
- payload and rules
  - `data_payload_json`
  - `schema_json`
  - `sample_preview_json`
  - `sensitive_fields_json`
  - `masking_rules_json`
  - `validation_rules_json`
- privacy and governance
  - `privacy_level`
  - `contains_pii`
  - `masking_status`
  - `synthetic_generation_status`
  - `approval_status`
  - `approved_by`
  - `approved_at`
  - `rejection_reason`
- reservation
  - `reservation_status`
  - `reserved_by`
  - `reserved_for_execution_id`
  - `reserved_at`
  - `reservation_expires_at`
  - `consumed_at`
  - `released_at`
- audit and usage
  - `created_by`
  - `updated_by`
  - `last_used_at`
  - `usage_count`
  - `agent_run_id`
- quality
  - `quality_score`
  - `quality_status`
  - `quality_issues_json`
- integration state
  - `jira_sync_status`
  - `last_synced_at`
  - `sync_error`
- compatibility
  - preserve legacy `notes`
  - preserve legacy historical data columns in migration where reasonable

### `test_data_templates`

Planned fields:

- `id`
- `template_id`
- `project_id`
- `name`
- `description`
- `telecom_domain`
- `test_phase`
- `data_type`
- `schema_json`
- `default_generation_rules_json`
- `validation_rules_json`
- `masking_rules_json`
- `is_active`
- `created_by`
- `updated_by`
- `created_at`
- `updated_at`

## API Design

### Project-scoped collection

- `GET /api/v1/test-data/projects/{project_id}`
- `GET /api/v1/test-data/projects/{project_id}/summary`
- `POST /api/v1/test-data/projects/{project_id}`
- `POST /api/v1/test-data/projects/{project_id}/generate`
- `POST /api/v1/test-data/projects/{project_id}/import`

### Item actions

- `GET /api/v1/test-data/{data_id}`
- `PATCH /api/v1/test-data/{data_id}`
- `DELETE /api/v1/test-data/{data_id}`
- `POST /api/v1/test-data/{data_id}/validate`
- `POST /api/v1/test-data/{data_id}/mask`
- `POST /api/v1/test-data/{data_id}/reserve`
- `POST /api/v1/test-data/{data_id}/release`
- `POST /api/v1/test-data/{data_id}/consume`
- `POST /api/v1/test-data/{data_id}/submit`
- `POST /api/v1/test-data/{data_id}/approve`
- `POST /api/v1/test-data/{data_id}/reject`
- `GET /api/v1/test-data/{data_id}/history`

### Templates

- `GET /api/v1/test-data/templates/projects/{project_id}`
- `POST /api/v1/test-data/templates/projects/{project_id}`
- `PATCH /api/v1/test-data/templates/{template_id}`
- `DELETE /api/v1/test-data/templates/{template_id}`

### Authorization model

- All endpoints require authentication.
- All endpoints enforce project-scoped authorization.
- All mutating endpoints enforce dedicated Test Data RBAC permissions.
- Sensitive payload fields are redacted unless the caller has `view_sensitive_test_data`.

## UI Design

### Main page

Path:

- `/test-data`

Main sections:

- page header with subtitle
- project selector
- summary cards
- action toolbar
- filter chips
- table with default and advanced columns
- row-level actions
- detail/history panel

### Initial UI actions to implement first

- view
- create manual data
- generate test data
- validate
- mask
- reserve
- release
- consume
- submit
- approve
- reject
- history

### Future UI actions

- import CSV/Excel with mapping wizard
- template designer
- bulk export
- Jira sync action

## Security and Privacy Design

- Never persist raw unvalidated LLM output.
- Never expose original sensitive payload to users lacking `view_sensitive_test_data`.
- Masking endpoint should update preview and sensitive field metadata without leaking original values.
- Logs, history, approval notes, and Jira sync payloads must only contain safe summaries.
- `contains_pii=true` requires `masking_status != not_required`.
- Restricted data must not move to approved/active use without explicit approval.

## AI Generation Approach

### Agent

- New agent: `TestDataGenerationAgent`
- Location: `backend/app/agents/test_data/test_data_agent.py`

### Invocation pattern

- HTTP handler validates request and project RBAC.
- Handler queues an `agent_run` using the existing Celery pattern.
- Worker dispatch persists only schema-validated output.

### Output contract

Each generated item should include:

- `name`
- `data_type`
- `payload`
- `explanation`
- `validation_rules`
- `risk_notes`
- `quality_score`

### Safety constraints

- no real personal data
- no realistic customer identifiers
- synthetic telecom-safe ranges and prefixes
- `contains_pii=false` by default
- invalid JSON or schema mismatch causes rejection and no persistence

## Masking Approach

Rules implemented in service layer:

- field-aware maskers for `msisdn`, `email`, `name`, `address`, `account_number`, `payment_reference`, generic strings
- masking preserves test usefulness and format shape
- masking result updates:
  - `data_payload_json`
  - `sample_preview_json`
  - `sensitive_fields_json`
  - `masking_status`

## Reservation Approach

Reservation rules:

- only `approved` or `active` data with valid quality can be reserved
- already reserved data cannot be reserved by another user
- expired reservations can be reclaimed
- consume marks single-use data unavailable until reset by future admin action

Implementation in first increment:

- service-level transactional checks
- persisted expiry timestamp
- no separate lock table

## Execution Integration

Planned first-step integration:

- execution can later reference `test_data` IDs in run metadata
- lineage can connect `test_data -> execution_run` and `test_data -> execution_result`

Practical first increment:

- prepare model and service contracts
- add the required fields for future execution linkage
- do not deeply redesign execution flow in the first slice

## Jira Integration

Safe Jira behavior:

- only safe summary metadata should ever be synced
- no payload values
- no sensitive field content

First increment:

- persist Jira linkage fields and sync status on Test Data
- defer outbound Jira comment job until summary serialization is covered by tests

## Edge Cases To Handle

- invalid AI JSON
- schema mismatch
- unsafe generated identifiers
- duplicate key business data
- missing required fields
- unknown template
- invalid status transition
- reservation race
- releasing someone else’s reservation
- using rejected, draft, invalid, or expired data
- masking required but no masking rule
- unauthorized sensitive field access
- empty history
- empty project state

## Files Reviewed

- `backend/app/models/test_data.py`
- `backend/app/models/test_case.py`
- `backend/app/models/execution.py`
- `backend/app/models/approval.py`
- `backend/app/models/artifact_lineage.py`
- `backend/app/services/approval_service.py`
- `backend/app/services/traceability_service.py`
- `backend/app/services/rbac_service.py`
- `backend/app/services/jira_service.py`
- `backend/app/api/deps.py`
- `backend/app/api/v1/router.py`
- `backend/app/api/v1/endpoints/test_cases.py`
- `backend/app/api/v1/endpoints/automation.py`
- `backend/app/api/v1/endpoints/execution.py`
- `backend/app/worker/tasks/agent_tasks.py`
- `backend/app/services/agent_dispatch_service.py`
- `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/app/test-cases/page.tsx`
- `frontend/src/app/execution/page.tsx`
- `frontend/src/lib/api.ts`
- `backend/alembic/versions/001_initial_schema.py`

## Files To Create

Planned new files:

- `backend/app/agents/test_data/__init__.py`
- `backend/app/agents/test_data/test_data_agent.py`
- `backend/app/schemas/test_data.py`
- `backend/app/services/test_data_service.py`
- `backend/app/api/v1/endpoints/test_data.py`
- `frontend/src/app/test-data/layout.tsx`
- `frontend/src/app/test-data/page.tsx`
- `backend/tests/test_test_data_module.py`
- `backend/alembic/versions/009_test_data_management.py`

## Files To Modify

Planned modifications:

- `backend/app/models/test_data.py`
- `backend/app/models/__init__.py`
- `backend/app/api/v1/router.py`
- `backend/app/services/rbac_service.py`
- `backend/app/services/traceability_service.py`
- `backend/app/worker/tasks/agent_tasks.py`
- `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/lib/api.ts`
- `IMPLEMENTATION_AUDIT.md`

Possible follow-up modifications:

- `backend/app/models/execution.py`
- `backend/app/schemas/execution.py`
- `backend/app/services/execution_service.py`

## APIs To Add

- test data collection, detail, summary, validation, masking, reservation, approval, history, and template APIs listed above

## UI Components To Add

- Test Data page
- summary cards
- generate panel
- manual create form or modal
- data table
- row action controls
- history panel

## Tests To Add

Backend:

- manual create
- validate endpoint
- mask endpoint
- reserve, release, consume
- approval workflow
- history retrieval
- sensitive field redaction
- summary counts
- lineage creation
- invalid status transition rejection
- double-reservation prevention

Frontend:

- page renders
- empty state
- summary cards
- action dialogs/panels open
- permission-aware action visibility where feasible

## Incremental Implementation Plan

### Phase 1

Backend foundation and core UI:

- expand `test_data` model
- add `test_data_templates`
- add schemas, service, endpoints
- add summary, manual CRUD, validation, masking, reservation, approval, history
- add sidebar item and Test Data page

### Phase 2

AI generation and async workflow:

- implement `TestDataGenerationAgent`
- register Celery dispatch
- persist validated generated data
- add generation UI

### Phase 3

Import and stronger integration:

- CSV/JSON import
- template-driven validation
- execution linkage
- Jira-safe sync summary
- richer reports and traceability coverage

## Recommended First Build Slice

Implement Phase 1 now:

- deliver end-to-end Test Data module foundations
- keep import and Jira push intentionally deferred
- keep execution integration light but schema-ready

