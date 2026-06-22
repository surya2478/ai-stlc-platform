# Test Case Generation Investigation

Date: 2026-06-12
Project: 7 (`Testing`)
Page checked: `http://localhost:3000/test-cases?project=7`

## New Code Changes Noted

- Added project-scoped artifact governance across requirements, test plans, scenarios, test cases, execution, defects, reports, automation, Jira sync, traceability, RBAC, and test data modules.
- Added direct `/api/v1/test-cases` aliases backed by the existing test planning service.
- Expanded test case metadata with approval status, execution mode, automation readiness, external test-management mapping fields, Jira sync fields, telecom taxonomy fields, history, and lineage.
- Added async agent run infrastructure with Celery/Redis, `agent_runs`, progress logs, idempotency metadata, and artifact persistence in worker tasks.
- Reworked frontend pages and API client for dashboards, requirements, test planning, test cases, test data, execution, automation, defects, reports, users, settings, and command-center views.
- Added migrations `002` through `014`, new backend tests, Docker/runtime updates, and module design/audit documents.

## Live Data Findings

- Project `7` exists as `Testing`.
- Project `7` has 11 requirements.
- 4 requirements are approved.
- 5 test scenarios exist for the project.
- 0 test cases exist for the project.
- Latest scenario generation run completed and created 5 scenarios.
- Latest test case generation run completed with output `{"test_case_ids": [], "count": 0}`.

## Root Cause

Test case generation did start, but the LLM provider returned HTTP `429 Too Many Requests` because the configured provider/model had exhausted its token-per-day quota. The worker log shows the test case agent retried and then received rate-limit failures for the selected scenario.

The second issue is observability: the test case agent caught the provider errors, generated zero cases, and still returned `success=True`. The worker then marked the agent run as `completed`, so the frontend simply reloaded the test case table and showed 0 items.

## Code Fix Applied

- Updated `backend/app/agents/test_planning/test_case_agent.py` so an all-error run with zero generated test cases returns `success=False`.
- Added `backend/tests/test_test_case_agent.py` to verify the test case agent fails when every scenario generation attempt errors.

## Follow-Up Recommendations

- Retry generation after the LLM quota resets, or switch to a provider/model with available quota.
- Surface failed async agent runs in the Test Case Library page instead of only refreshing the list.
- Consider honoring `settings.run_agents_synchronously` in `backend/app/api/v1/endpoints/test_plans.py`; it currently returns `False` unconditionally, so the UI gets a queued response and refreshes before async generation finishes.
