# STLC Platform Implementation Audit

Audit date: 2026-06-10

## Summary

This implementation pass hardened the backend around authenticated project access, moved agent triggers toward Celery-backed execution, added approval audit creation, made artifact display IDs DB-safe, moved document extraction to a background task, and added central LLM resilience plus Pydantic validation for structured agent output.

## Priority 1 - Authorization

- Removed `OptionalUser` from business endpoints and replaced it with `CurrentUser`.
- Removed fallback ownership logic such as `current_user.id if current_user else 1`.
- Added shared authorization helpers in `backend/app/api/deps.py`:
  - `require_project_access(project_id, current_user, db)`
  - `require_entity_project_access(entity, current_user, db)`
- Applied project access checks to documents, requirements, test plans, automation, execution, defects, reports, agents, and settings endpoints.
- Added entity-by-id project checks before returning, approving, rejecting, deleting, or mutating records.
- Added tests proving unauthenticated requests return `401` and cross-user project access returns `403`.

## Priority 2 - Agent Execution

- Fixed the Celery task mismatch where `RequirementQualityAgent.run` was called with `project_id`.
- Added `backend/app/services/agent_dispatch_service.py` to create pending `AgentRun` rows and enqueue Celery tasks.
- Agent trigger endpoints now return `202 Accepted` with `agent_run_id` and `task_id` when not using the local synchronous mode.
- Kept the existing synchronous artifact-producing flow behind local settings: `APP_ENV=local` and `RUN_AGENTS_SYNCHRONOUSLY=true`.

Operational note: the generic Celery worker stores agent output and logs on `agent_runs`. The local synchronous path still performs the full artifact persistence workflow.

## Priority 3 - Approvals And IDs

- Added immutable approval audit creation through `backend/app/services/approval_service.py`.
- Approval actions are created for requirement, test plan, test case, automation script, and defect approve/reject paths.
- Added model-level project-scoped uniqueness constraints for:
  - requirements: `(project_id, requirement_id)`
  - test plans: `(project_id, test_plan_id)`
  - test scenarios: `(project_id, scenario_id)`
  - test cases: `(project_id, test_case_id)`
  - automation scripts: `(project_id, script_id)`
  - execution runs: `(project_id, execution_id)`
  - defect drafts: `(project_id, defect_id)`
  - reports: `(project_id, report_id)`
- Added Alembic migration `002_project_scoped_artifact_ids.py` and verified `alembic upgrade head`.
- Replaced count-based display ID generation with temporary UUID-backed IDs followed by row-id-based display IDs.

## Priority 4 - Uploads And LLM Hardening

- Document uploads now stream to disk in chunks instead of reading the full file into memory.
- Filenames are sanitized before storage.
- File signatures are validated for PDF, DOCX, XLSX, and text-like uploads.
- Document text extraction now runs through Celery task `document_tasks.extract_document_text`.
- Added central LLM retry, exponential backoff, and in-process circuit breaker behavior in `backend/app/llm/provider.py`.
- Added Pydantic structured output schemas for requirements, quality reviews, test plans, scenarios, test cases, automation scripts, execution results, defects, and reports.
- Agent validators now normalize and validate LLM JSON before downstream persistence.

## Validation

Completed successfully:

- `docker compose exec -T backend alembic upgrade head`
- `docker compose exec -T backend python -m compileall app tests`
- `docker compose exec -T backend python -m pytest` - 18 passed
- `docker compose exec -T frontend npm run lint`
- `docker compose exec -T frontend npm run build`

## Follow-Up Notes

- Because business endpoints now require authentication, local UI/API calls without a bearer token will correctly return `401`.
- Existing local data with duplicate artifact display IDs would need cleanup before applying the uniqueness migration in another environment.
- The asynchronous Celery path is now available, but deeper artifact-specific persistence in worker workflows can be expanded after this security baseline.

## Phase 1 - RBAC And Project Membership

Principles addressed:

- `P07 Backend-Enforced Authorization`: added project membership and permission derivation in backend services/dependencies.
- `P09 Telecom Scale Design`: membership queries use indexed `project_id`, `user_id`, `role`, and `is_active` fields.
- `P03 Complete Audit Trail`: not completed in this phase; approval audit exists, but universal audit records remain a later phase.

Files created:

- `backend/app/models/project_membership.py` - project membership model with unique `project_id + user_id`.
- `backend/alembic/versions/003_project_memberships_rbac.py` - migration creating memberships and backfilling project owners as `Project Admin`.
- `backend/app/services/rbac_service.py` - role-to-permission map and membership permission helpers.
- `backend/app/schemas/project_membership.py` - project membership request/response schemas and available roles response.
- `backend/tests/test_rbac_phase1.py` - focused tests for role permissions, member access, and permission denial.

Files modified:

- `backend/app/models/user.py` - added `project_memberships` relationship.
- `backend/app/models/project.py` - added `memberships` relationship.
- `backend/app/models/__init__.py` - registered `ProjectMembership`.
- `backend/app/api/deps.py` - made project access membership-aware and added permission helper.
- `backend/app/core/security.py` - added optional extra JWT claims.
- `backend/app/schemas/user.py` - added token membership claim schemas.
- `backend/app/api/v1/endpoints/users.py` - login now returns JWT claims with `global_role` and `project_memberships`.
- `backend/app/repositories/project_repository.py` - added membership-visible and admin-visible project listing.
- `backend/app/services/project_service.py` - creates owner membership, enforces view/manage permissions, and manages memberships.
- `backend/app/api/v1/endpoints/projects.py` - added role and membership endpoints; project CRUD now uses membership-aware service calls.

Files deleted:

- None.

Validation:

- `docker compose exec -T backend alembic upgrade head` - passed.
- `docker compose exec -T backend python -m pytest` - 25 passed.
- `docker compose exec -T backend python -m compileall app tests` - passed.
- `docker compose exec -T frontend npm run lint` - passed.
- `docker compose exec -T frontend npm run build` - passed.

## Test Cases Metadata Source Of Truth

Issue summary:

- The Test Cases screen exposed only a thin subset of persisted fields while Automation Control Center displayed richer mapping, execution, and Jira metadata.
- Several Test Cases counts and statuses were derived from loaded frontend rows rather than a backend summary contract.
- Test Case edits did not create an append-only change history, and there was no direct `/api/v1/test-cases` contract for patch/history/Jira sync.

Root cause:

- Shared operational metadata was split between `test_cases`, automation mappings, execution results, and frontend shaping logic without a consistent source-of-truth API.
- Legacy automation state names such as `automation_candidate` and `not_automated` remained in backend/frontend contracts after Automation Control Center introduced newer workflow states.

Files reviewed:

- `frontend/src/app/test-cases/page.tsx`
- `frontend/src/app/automation/page.tsx`
- `frontend/src/lib/api.ts`
- `backend/app/models/test_case.py`
- `backend/app/models/automation_mapping.py`
- `backend/app/models/execution.py`
- `backend/app/schemas/test_plan.py`
- `backend/app/schemas/automation.py`
- `backend/app/api/v1/endpoints/test_plans.py`
- `backend/app/api/v1/endpoints/automation.py`
- `backend/app/services/test_plan_service.py`
- `backend/app/services/automation_service.py`
- `backend/app/services/jira_service.py`

Files modified:

- Added migration `backend/alembic/versions/008_test_case_metadata_history.py`.
- Added `backend/app/api/v1/endpoints/test_cases.py`.
- Added tests in `backend/tests/test_test_case_metadata_governance.py`.
- Updated TestCase model, schemas, services, API router, Automation service/schema, Jira inbound pagination, frontend API client, Test Cases page, and Automation visibility logic.

API changes:

- Added direct aliases:
  - `GET /api/v1/test-cases/projects/{project_id}`
  - `GET /api/v1/test-cases/projects/{project_id}/summary`
  - `GET /api/v1/test-cases/{test_case_id}`
  - `PATCH /api/v1/test-cases/{test_case_id}`
  - `GET /api/v1/test-cases/{test_case_id}/history`
  - `POST /api/v1/test-cases/{test_case_id}/sync-jira`
- Added equivalent summary/history/sync routes under the existing `/api/v1/test-plans/cases/...` namespace for compatibility.

Database/model changes:

- Added persisted TestCase metadata for automation readiness, phase/domain, active external mapping fields, latest automation/evidence, Jira URL/status/sync fields, traceability release/plan fields, update actor, and last status update actor/time.
- Added append-only `TestCaseHistory` for audited field changes.
- Normalized legacy automation statuses during migration.

UI changes:

- Rebuilt `/test-cases` as an operational metadata table with inline editable status, priority, mode, automation eligibility/status/readiness, external mapping fields, Jira final status, telecom domain, and test phase.
- Added real backend summary cards, filters for approval/mode/automation/Jira states, Jira external link, Jira sync action, and history panel.
- Kept generation/export flows while ensuring saved values reload from backend and stay consistent with `/automation`.

Edge cases handled:

- Invalid enum values and invalid external/Jira URLs.
- Manual or automation-ineligible cases cannot be marked automated.
- Automated status requires external TC ID or selected automation script.
- Duplicate external TC ID is rejected within project/tool/suite.
- Rejected cases require a comment.
- Core title changes are blocked after execution results exist.
- Jira conflict blocks direct Jira final status updates.
- Missing Jira connection records a failed sync state without external synchronous Jira calls.
- Missing Jira links show a safe disabled state; real links open with `noopener noreferrer`.
- Partial PATCH does not overwrite unspecified fields with null.
- Audit rows are created in the same transaction as the metadata update.

Tests added/updated:

- `backend/tests/test_test_case_metadata_governance.py` verifies patch persistence, history creation, invalid metadata transitions, duplicate external ID rejection, and schema URL validation.
- Existing Jira two-way sync tests now pass after updating inbound sync pagination to the current `/rest/api/3/search/jql` token flow.

Test results:

- `docker compose exec -T backend python -m compileall app tests` - passed.
- `docker compose exec -T backend alembic upgrade head` - passed, DB at `008_test_case_metadata_history`.
- `docker compose exec -T backend python -m pytest` - 93 passed, 5 warnings.
- `docker compose exec -T frontend npm run lint` - passed.
- `docker compose exec -T frontend npm run build` - passed.
- `http://localhost:3000/test-cases` - 200.
- `http://localhost:3000/automation` - 200.
- `GET /api/v1/test-cases/projects/1/summary` without token - 401, confirming the route is protected.

Known limitations:

- The Test Cases page queues Jira sync through the existing outbound Jira worker path; deeper per-test-case Jira execution sync remains tied to the current Jira integration model.
- Frontend automated browser visual verification was not used because local HTTP smoke checks were sufficient for this backend-heavy change.

Recommended next improvement:

- Add a dedicated test-case Jira sync worker that updates one TestCase at a time and records per-test-case success/failure independently from requirement outbound sync.

## Test Cases Column Visibility UI

Issue summary:

- The upgraded Test Cases screen displayed too many operational fields in a single default table.
- The fixed 13-column grid made the default view horizontally stretched and harder to scan.

Root cause of layout problem:

- `frontend/src/app/test-cases/page.tsx` used a hardcoded `min-w-[1680px]` table and fixed grid columns for all core and advanced metadata.
- Advanced automation and Jira fields were always visible instead of being available on demand.

Files reviewed:

- `frontend/src/app/test-cases/page.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/app/automation/page.tsx`

Files modified:

- `frontend/src/app/test-cases/page.tsx`
- `IMPLEMENTATION_AUDIT.md`

UI changes implemented:

- Added a configurable `Columns` selector to the Test Cases filter row.
- Added a column configuration model used for headers and row cells.
- Kept the default table focused on ID, Title, Status, Priority, Mode, Automation, Jira Link, and Actions.
- Moved advanced fields behind user-selected columns without removing data or edit capability.
- Added compact view toggle and cleaner row spacing.
- Improved default table width so horizontal scrolling appears only when advanced columns are selected.

New column visibility behavior:

- Visible columns persist in `localStorage` with project-aware keys: `testCases.visibleColumns.{projectId}`.
- Compact view persists with `testCases.compactView.{projectId}`.
- Invalid saved localStorage values are sanitized.
- Required columns ID, Title, and Actions cannot be removed.
- If a user hides a column with unsaved edits, the edit is preserved and a notice is shown.

Presets added:

- Default View
- Automation View
- Jira View
- Telecom View

Edge cases handled:

- Too many selected columns use intentional horizontal scroll.
- Deselecting all columns is prevented through required columns and fallback defaults.

## Test Data Generate And Import

Feature summary:

- Implemented real backend-backed `Generate Test Data` requests using an external-tool request model instead of frontend placeholders.
- Implemented CSV/Excel import preview and confirm flow with persisted preview tokens and row-level record storage.
- Updated the Test Data UI so `Generate Test Data` and `Import CSV/Excel` are working actions with validation, preview, and refresh behavior.

Root cause of non-working buttons:

- The generate endpoint returned a placeholder message only and no persisted dataset request.
- The import action had no backend preview/confirm workflow and the frontend rendered the button as disabled.

Files reviewed:

- `frontend/src/app/test-data/page.tsx`
- `frontend/src/lib/api.ts`
- `backend/app/models/test_data.py`
- `backend/app/schemas/test_data.py`
- `backend/app/api/v1/endpoints/test_data.py`
- `backend/app/services/test_data_service.py`
- `backend/app/services/document_service.py`
- `backend/app/config.py`

Files created:

- `backend/app/services/external_test_data_tools.py`
- `backend/app/services/test_data_generation_service.py`
- `backend/app/services/test_data_import_service.py`
- `backend/alembic/versions/010_test_data_generation_import.py`

Files modified:

- `backend/app/models/test_data.py`
- `backend/app/models/__init__.py`
- `backend/app/schemas/test_data.py`
- `backend/app/api/v1/endpoints/test_data.py`
- `backend/app/services/test_data_service.py`
- `backend/tests/test_route_registration.py`
- `backend/tests/test_test_data_module.py`
- `frontend/src/lib/api.ts`
- `frontend/src/app/test-data/page.tsx`

Database/model changes:

- Added generation/import fields to `test_data` for external tool mapping, generation state, record counts, validation state, and import filename.
- Added `test_data_records` for persisted imported/generated rows.
- Added `test_data_import_previews` for server-side preview tokens with expiry and single-use confirmation.

API endpoints added/updated:

- `POST /api/v1/test-data/projects/{project_id}/generate`
- `POST /api/v1/test-data/projects/{project_id}/import/preview`
- `POST /api/v1/test-data/projects/{project_id}/import/confirm`

Frontend modal changes:

- Added Generate modal with dataset name, telecom/test phase/environment dropdowns, external tool mapping fields, request notes, and due date.
- Added Import modal with file upload, metadata, append/create mode, preview table, validation messages, and confirm action.
- Updated the main table to surface generation status, record counts, external tool links, and validation state.

External tool mapping behavior:

- External generation requests are saved as `source_type=external_tool`.
- Unsupported tools are accepted and persisted with `generation_status=pending_external_generation`.
- `Mock` remains future-ready through a dedicated abstraction and only produces demo-safe sample rows in local debug mode.

CSV/Excel import behavior:

- Supports `.csv`, `.xlsx`, and `.xls` parsing with preview token persistence.
- Returns detected columns, first rows, warnings, and errors before confirmation.
- Confirm import persists the dataset plus row-level records and marks the preview token consumed.

Edge cases handled:

- Invalid or cross-project requirement/test-case links.
- Record count bounds for generation requests.
- Invalid external URL and past expected date via schema validation.
- Empty upload, duplicate headers, unsupported file type, empty rows, duplicate rows, and PII with public privacy level.
- Expired or reused preview tokens and append-to-wrong-project dataset attempts.

Tests added/updated:

- Added route registration coverage for generate/import endpoints.
- Added test coverage for CSV parsing, duplicate header rejection, import metadata validation, and generation request persistence.

Validation results:

- `docker compose exec -T backend alembic upgrade head` - passed
- `docker compose exec -T backend python -m compileall app tests` - passed
- `docker compose exec -T backend python -m pytest tests/test_route_registration.py tests/test_test_data_module.py` - passed
- `docker compose exec -T frontend npm run lint` - passed
- `docker compose exec -T frontend npm run build` - passed
- `http://localhost:3000/test-data` - 200

Known limitations:

- Real external tool execution is still asynchronous-by-design and not yet integrated with live vendor APIs.
- Excel import uses the first sheet only in this phase.
- Full end-to-end browser submission was not automated in this pass; validation used build/tests plus local page load checks.

Recommended next improvement:

- Add a dataset detail endpoint for row-level browsing/download plus async reconciliation hooks that update `generation_status` when an external tool completes.
- Invalid localStorage column IDs are ignored.
- Hidden fields are not overwritten during save because PATCH payloads now include only changed fields.
- Null and empty values render as `-` or `Not linked`.
- Long titles and URLs truncate with safe titles/links where applicable.
- Existing status/mode filters remain independent from column customization.

Validation results:

- `docker compose exec -T frontend npm run lint` - passed.
- `docker compose exec -T frontend npm run build` - passed.
- `docker compose restart frontend` - passed.
- `http://localhost:3000/test-cases` - 200.

Known limitations:

- The legacy hardcoded row block remains hidden in the file to minimize churn in this dirty worktree; the visible table is rendered from the new column configuration. A later cleanup can remove the hidden block once the page stabilizes.

## Automation Eligibility Display Fix

Issue summary:

- Manual or automation-ineligible test cases could still appear in Automation Control Center.
- The screenshot case showed Test Cases as `mode=manual`, `automation_eligible=no`, `automation_status=not_required`, while Automation still displayed the row using stale/legacy labels.

Root cause:

- Automation Control Center loaded approved test cases from the generic Test Cases API without a backend automation eligibility filter.
- Frontend `isAutomationVisible` allowed hybrid rows, automation candidates, and mapping-required/ready statuses even when the TestCase source-of-truth mode and eligibility were not active for automation.
- Active mappings could remain after a TestCase was changed back to manual/ineligible.

Files reviewed:

- `frontend/src/app/automation/page.tsx`
- `frontend/src/app/test-cases/page.tsx`
- `frontend/src/lib/api.ts`
- `backend/app/services/test_plan_service.py`
- `backend/app/services/automation_service.py`
- `backend/app/api/v1/endpoints/test_cases.py`
- `backend/app/api/v1/endpoints/test_plans.py`
- `backend/tests/test_test_case_metadata_governance.py`

Files modified:

- `backend/app/services/test_plan_service.py`
- `backend/app/services/automation_service.py`
- `backend/app/api/v1/endpoints/test_cases.py`
- `backend/app/api/v1/endpoints/test_plans.py`
- `backend/tests/test_test_case_metadata_governance.py`
- `frontend/src/lib/api.ts`
- `frontend/src/app/automation/page.tsx`
- `frontend/src/app/test-cases/page.tsx`

Backend filtering rule implemented:

- Added `automation_only=true` support to Test Cases project list APIs.
- Backend filtering now requires normalized `execution_mode = automated` and `automation_eligible = yes`.
- Automation actions now validate the same rule before mapping or running automation.

Frontend changes implemented:

- Automation page now requests `testCasesApi.list(projectId, { status: "approved", automation_only: true })`.
- Frontend guard now shows only `execution_mode=automated` and `automation_eligible=yes`.
- Empty state now explains how to include a test case: mark it Automated and Eligible Yes.
- Test Cases edit draft now auto-normalizes Manual to Eligible No and Not Required, and Automated to Eligible Yes with Mapping Required when appropriate.

Data consistency approach:

- TestCase remains the source of truth for mode and eligibility.
- Existing automation evidence is preserved.
- Active automation mappings are deactivated when a TestCase becomes non-applicable.
- Audit/history rows continue to capture mode, eligibility, and automation status changes in the same update transaction.

Edge cases handled:

- Manual test cases are excluded from Automation API and UI.
- `automation_eligible=no` test cases are excluded from Automation API and UI.
- Hybrid test cases are excluded for this phase.
- Explicit invalid payloads such as manual + automated or eligible no + automated are rejected.
- Clean mode-only transition to manual is normalized safely.
- Clean transition to automated + eligible yes sets mapping-required if no active automation status exists.
- Stale active mappings are deactivated without deleting history/evidence.

Tests added/updated:

- `backend/tests/test_test_case_metadata_governance.py` now verifies automation-only query filtering, manual normalization, mapping deactivation, automated+eligible inclusion state, and invalid automation combinations.

Validation results:

- `docker compose exec -T backend python -m compileall app tests` - passed.
- `docker compose exec -T backend python -m pytest` - 96 passed, 5 warnings.
- `docker compose exec -T frontend npm run lint` - passed.
- `docker compose exec -T frontend npm run build` - passed.
- `docker compose restart backend frontend` - passed.
- `http://localhost:3000/automation` - 200.
- `http://localhost:3000/test-cases` - 200.
- `GET /api/v1/test-cases/projects/1?status=approved&automation_only=true` without token - 401, confirming the route is protected.

Known limitations:

- Existing database rows with legacy `not_applicable` / `under_review` values should be normalized by the current migration path; if an environment bypassed migrations, those rows will be excluded from Automation until corrected.

Recommended next improvement:

- Add a dedicated Automation candidate endpoint with summary counts so the Automation page no longer needs to load generic TestCase rows plus mapping/scripts independently.

Known limitations:

- Existing module endpoints still mostly enforce project view access; detailed per-action permission enforcement across every STLC endpoint should be expanded in Phase 2 before Jira sync or release governance work.
- JWTs include membership claims for clients, but backend authorization still loads permissions from the database, which is intentional and safer.
- Refresh token support is not yet implemented.

Next phase:

- Phase 2 should complete backend permission enforcement across STLC actions and approval gates, then add tests for each permission boundary before building Jira sync on top.

## Phase 2 - RBAC Permission Enforcement

Backend changes:

- Added `require_entity_permission(entity, permission, current_user, db)` in `backend/app/api/deps.py`.
- Kept read-only list/detail endpoints on `view_project`.
- Added explicit permission checks for document upload/delete, requirement mutation/approval/agents, test planning mutation/approval/agents, test case mutation/approval/agents, automation mutation/approval/generation, test execution, defect mutation/approval/analysis, Jira defect push, release report generation, and agent run/log access.
- Platform admins and project owners continue to inherit all project permissions through the existing RBAC service.

Permission mapping:

- Documents: `manage_project`.
- Requirements: `approve_requirements`.
- Test plans and scenario generation: `approve_test_plans`.
- Test cases and test case generation: `approve_test_cases`.
- Automation scripts and generation: `generate_automation`.
- Execution runs: `execute_tests`.
- Defects and defect analysis: `raise_defects`.
- Jira defect push: `push_defects_to_jira`.
- Reports: `approve_release_report`.
- Agent runs and logs: `view_audit_logs`.

Tests added:

- `backend/tests/test_rbac_phase2.py` verifies users without the required permission receive `403` on representative approval, generation, audit-log, and Jira-push boundaries.

Validation:

- `docker compose exec -T backend python -m compileall app tests` - passed.
- `docker compose exec -T backend python -m pytest` - 29 passed.
- `docker compose exec -T frontend npm run lint` - passed.
- `docker compose exec -T frontend npm run build` - passed.

## Admin User Management

Backend changes:

- Added platform-admin protected user listing, creation, and update endpoints under `backend/app/api/v1/endpoints/users.py`.
- Public self-registration now ignores submitted admin/superuser fields and always creates a normal `qa_engineer` account.
- Added password length validation, explicit global role validation, and last-active-admin protection.
- Added user search support in `backend/app/repositories/user_repository.py`.

Frontend changes:

- Added `/users` as a User Management screen for platform admins.
- Added user creation with password confirmation, global role selection, active status controls, and superuser controls.
- Added project membership assignment on the same screen, including project role selection and membership disable actions.
- Added User Management to the System sidebar section.

Edge cases covered:

- Duplicate emails are rejected.
- Invalid global roles are rejected.
- Passwords shorter than 8 characters or longer than 72 characters are rejected.
- Admin/superuser escalation through public registration is blocked.
- The final active platform admin cannot be deactivated, demoted, or stripped of superuser status.
- Project membership assignment reuses backend project access and role validation.

Validation:

- `docker compose exec -T backend python -m compileall app tests` - passed.
- `docker compose exec -T backend python -m pytest` - 25 passed.
- `docker compose exec -T frontend npm run lint` - passed.
- `docker compose exec -T frontend npm run build` - passed.

## Repository Hygiene And Deployment Readiness

Changes:

- Added `ARCHITECTURE_BASELINE.md` with repository inventory, security baseline, RBAC baseline, deployment notes, and gap analysis.
- Added root, backend, and frontend `.dockerignore` files.
- Replaced stale README content with current GitHub-safe local setup, RBAC summary, backend deployment notes, and Vercel frontend deployment guidance.
- Refreshed `RUNNING_LOCALLY.md` with explicit local admin seed instructions.
- Made local dev user seeding opt-in through environment variables.
- Removed prefilled dev credentials from the login screen.
- Made frontend dev auto-auth require explicit environment variables.
- Added `frontend/vercel.json` for Vercel frontend deployment.
- Replaced secret-looking UI examples with placeholder text to reduce false-positive secret scans.

Validation:

- `docker compose config --quiet` - passed.
- `docker compose exec -T backend python -m compileall app tests` - passed.
- `docker compose exec -T backend python -m pytest` - 29 passed.
- `docker compose exec -T frontend npm run lint` - passed.
- `docker compose exec -T frontend npm run build` - passed.

## Phase 5 - Traceability And Approval Governance

Backend changes:

- Added append-only `ArtifactLineage` model and migration `005_traceability_approval_governance`; lineage records use typed parent/child references without cascade-delete relationships.
- Enhanced `ApprovalAction` with source, actor role, old/new values, Jira key, request/correlation IDs, and agent run references while preserving append-only behavior.
- Added `traceability_service` for lineage creation, approval governance, approval history, traceability matrix assembly, coverage gap detection, and RULE-14 metrics.
- Added `/api/v1/traceability` endpoints for matrix, gaps, artifact approvals, and approval history.
- Inserted lineage records in synchronous agent artifact creation paths for requirements, test plans, scenarios, test cases, automation scripts, execution runs/results, defect drafts, and reports.
- Updated report-generation metrics to exclude unapproved artifacts by default, with explicit `include_drafts=true` opt-in.
- Hardened approval edge cases so execution run/result lifecycle statuses are preserved and approval state is stored in metadata.
- Hardened coverage gap detection to aggregate all traceability matrix pages, not only the first page.

Tests added:

- `backend/tests/test_traceability_governance.py` verifies atomic lineage behavior, no lineage mutation routes, trace chains, all three gap types, all-page gap aggregation, append-only approvals, execution outcome preservation, and RULE-14 default metrics.

Validation:

- `docker compose exec -T backend python -m pytest tests/test_traceability_governance.py` - 10 passed.
- `docker compose exec -T backend python -m pytest` - 62 passed.
- `docker compose exec -T backend python -m compileall app tests` - passed.
- `docker compose exec -T frontend npm run lint` - passed.
- `docker compose exec -T frontend npm run build` - passed.

## Phase 6 - Async Agent Workflow Hardening

Backend changes:

- Added `idempotency_key`, `input_hash`, `prompt_version`, `progress_percent`, and `progress_message` to `AgentRun` with migration `006_async_agent_workflow`.
- Added deterministic input hashing and idempotency-key derivation for all agent dispatches.
- Updated agent dispatch to reuse existing pending/running/completed runs for duplicate triggers and enqueue only new work.
- Converted agent trigger gate behavior to always enqueue through Celery and return HTTP 202 from trigger endpoints.
- Expanded agent polling/list responses with task ID, progress, idempotency, input hash, prompt version, input, and output data.
- Hardened Celery task lifecycle with queued/running/completed/failed transitions, progress updates, sanitized error persistence, transient/permanent failure classification, and retry backoff for transient failures.
- Added worker-side artifact persistence for async agent completions, including lineage creation for generated artifacts.
- Hardened duplicate failed/cancelled trigger behavior to requeue the existing idempotent `AgentRun` instead of creating a conflicting duplicate.
- Hardened broker enqueue failure handling so a newly created run is marked failed with a sanitized error instead of being left permanently pending.
- Expanded error sanitization for JSON-style secret fields such as `"token": "..."`.

Tests added:

- `backend/tests/test_async_agent_workflow.py` verifies 202 trigger response, duplicate trigger reuse, failed-run requeue, enqueue failure handling, task running/completed lifecycle, sanitized failure persistence, transient/permanent retry classification, and polling-visible progress.

Validation:

- `docker compose exec -T backend python -m pytest tests/test_async_agent_workflow.py` - 10 passed.
- `docker compose exec -T backend python -m pytest` - 72 passed.
- `docker compose exec -T backend python -m compileall app tests` - passed.
- `docker compose exec -T frontend npm run lint` - passed.
- `docker compose exec -T frontend npm run build` - passed.

## Phase 7 - Test Data Management Foundations

Feature summary:

- Added the first incremental implementation of a dedicated `Test Data` module, including architecture/design documentation, backend data model expansion, project-scoped APIs, governance workflow, reservation lifecycle, masking, validation, and a first usable frontend page.

Systems and industry patterns reviewed:

- Tricentis-style reusable dataset inventory and reservation
- Broadcom / CA-style reservation and consumption control
- IBM Optim / Informatica-style masking and governance
- Delphix-style masking-first environment readiness concepts
- K2View-style business-entity telecom templates
- GenRocket / faker-style synthetic generation patterns

Final Test Data Management design:

- Documented in `TEST_DATA_MANAGEMENT_DESIGN.md`
- Chosen architecture uses an expanded `test_data` artifact model plus a reusable `test_data_templates` model
- Phase 1 intentionally focuses on manual/governed data management before async AI generation, bulk import, and deeper execution/Jira orchestration

Files reviewed:

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

Files created:

- `TEST_DATA_MANAGEMENT_DESIGN.md`
- `backend/app/schemas/test_data.py`
- `backend/app/services/test_data_service.py`
- `backend/app/api/v1/endpoints/test_data.py`
- `backend/alembic/versions/009_test_data_management.py`
- `backend/tests/test_test_data_module.py`
- `frontend/src/app/test-data/layout.tsx`
- `frontend/src/app/test-data/page.tsx`

Files modified:

- `backend/app/models/test_data.py`
- `backend/app/models/__init__.py`
- `backend/app/services/rbac_service.py`
- `backend/app/services/traceability_service.py`
- `backend/app/api/v1/router.py`
- `backend/tests/test_route_registration.py`
- `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/lib/api.ts`
- `IMPLEMENTATION_AUDIT.md`

Database models added:

- `TestDataTemplate`

Database models enhanced:

- `TestData` now includes lifecycle, privacy, masking, quality, reservation, approval, template linkage, execution linkage, Jira linkage, audit, and telecom metadata fields while keeping legacy fields intact for compatibility

API endpoints added:

- `GET /api/v1/test-data/projects/{project_id}`
- `GET /api/v1/test-data/projects/{project_id}/summary`
- `GET /api/v1/test-data/{data_id}`
- `POST /api/v1/test-data/projects/{project_id}`
- `PATCH /api/v1/test-data/{data_id}`
- `DELETE /api/v1/test-data/{data_id}`
- `POST /api/v1/test-data/projects/{project_id}/generate`
- `POST /api/v1/test-data/{data_id}/validate`
- `POST /api/v1/test-data/{data_id}/mask`
- `POST /api/v1/test-data/{data_id}/reserve`
- `POST /api/v1/test-data/{data_id}/release`
- `POST /api/v1/test-data/{data_id}/consume`
- `POST /api/v1/test-data/{data_id}/submit`
- `POST /api/v1/test-data/{data_id}/approve`
- `POST /api/v1/test-data/{data_id}/reject`
- `GET /api/v1/test-data/{data_id}/history`
- `GET /api/v1/test-data/templates/projects/{project_id}`
- `POST /api/v1/test-data/templates/projects/{project_id}`
- `PATCH /api/v1/test-data/templates/{template_id}`
- `DELETE /api/v1/test-data/templates/{template_id}`

UI components added:

- Sidebar navigation entry for `Test Data`
- `frontend/src/app/test-data/page.tsx` with:
  - project selector
  - summary cards
  - action toolbar
  - manual creation form
  - filter chips
  - main table
  - detail pane
  - approval history view

Agent added:

- No agent implementation added in this increment
- Generation is intentionally deferred to the next phase, but the route and design contract are now in place

RBAC permissions added:

- `view_test_data`
- `create_test_data`
- `edit_test_data`
- `delete_test_data`
- `generate_test_data`
- `import_test_data`
- `approve_test_data`
- `reserve_test_data`
- `consume_test_data`
- `mask_test_data`
- `sync_test_data_jira`
- `view_sensitive_test_data`

Traceability changes:

- Test data creation now writes lineage to linked requirements and/or test cases using existing `artifact_lineage`
- `traceability_service` now recognizes `test_data` as an artifact type and approval-governed entity

Jira integration behavior:

- Added storage fields for Jira linkage and sync status on `TestData`
- Outbound Jira summary sync is intentionally deferred to a later increment to avoid accidental payload exposure

Execution integration behavior:

- Added execution linkage fields on `TestData`
- Full execution-driven reservation orchestration is deferred to the next increment

Edge cases handled:

- PII without masking requirement
- empty or missing payload
- required-field validation gaps
- invalid status transitions
- reservation conflicts
- releasing another user’s reservation
- consumption tracking
- sensitive payload redaction in non-sensitive responses

Tests added/updated:

- `backend/tests/test_test_data_module.py`
- `backend/tests/test_route_registration.py`

Validation results:

- `python -m compileall app tests` - passed locally
- `pytest` - could not run locally because `pytest` is not installed in the available Python runtimes
- backend runtime smoke imports - could not run locally because the available Python runtimes in this environment do not have project dependencies like `fastapi` and `sqlalchemy`
- frontend `npm run lint` / `npm run build` - could not run locally because the workspace does not currently have installed frontend dependencies; `frontend/node_modules` exists but does not contain `next`

Known limitations:

- AI generation route currently returns a phase-planning response instead of queueing a new `TestDataGenerationAgent`
- import workflow is not implemented yet
- outbound Jira summary sync is not implemented yet
- deeper execution-run reservation orchestration is not implemented yet
- validation and masking rules are practical foundational implementations, not yet a full telecom-rules engine
- frontend page focuses on Phase 1 actions and does not yet include import wizard, template designer UI, or column chooser

Recommended next improvements:

- implement `TestDataGenerationAgent` and async persistence flow
- add CSV/JSON import with row-level validation summary
- add template management UI
- integrate test data reservation directly into execution run creation
- add Jira-safe async summary sync
- add richer telecom identifier validation rules and duplicate detection
