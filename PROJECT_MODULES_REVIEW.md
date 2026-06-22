# STLC PLATFORM — FULL PROJECT MODULE REVIEW
**Telecom QA Command Center | stlc-platform**
**Review Date:** June 2026 | **Reviewer:** Principal Solution Architect + Senior Full-Stack Engineer
**Scope:** All modules — code-level inspection of actual committed files

---

## EXECUTIVE SUMMARY

> **Overall Verdict: Solid architectural foundation — not yet enterprise-telecom-ready for production**
>
> The platform has a well-structured async FastAPI backend, 9 LangGraph-based AI agents, a clean Next.js frontend, functional Celery async workflows, Jira two-way sync infrastructure, and an enterprise-grade audit/lineage/RBAC skeleton. The core AI pipeline from requirement intake to report generation is working end-to-end.
>
> However, critical gaps exist across every module that prevent this platform from being used in a real Telecom QA enterprise context. The most severe: the Execution module uses LLM-simulated pass/fail results (not real test execution), the Defect module lacks the full telecom triage fields, the Reports module generates narrative from LLM without pulling real DB metrics, the Test Planning module has no telecom domain awareness, and the Dashboard is cosmetic-only with no drill-down or governance capability. None of the modules carry telecom-domain fields through their data models, making AI output generic rather than telecom-specific.

---

## FILES REVIEWED

### Backend
| Layer | Files |
|---|---|
| Models | requirement.py, requirement_review.py, test_plan.py, test_scenario.py, test_case.py, test_data.py, automation_script.py, execution.py, defect.py, report.py, agent.py, approval.py, artifact_lineage.py, jira_connection.py, jira_sync.py, project.py, project_membership.py, document.py, user.py |
| Agents | requirement/intake_agent.py, requirement/quality_agent.py, test_planning/planning_agent.py, test_planning/scenario_agent.py, test_planning/test_case_agent.py, automation/automation_agent.py, execution/execution_agent.py, defect/defect_agent.py, reporting/reporting_agent.py, agents/structured_schemas.py |
| API Endpoints | requirements.py, test_plans.py, execution.py, defects.py, automation.py, reports.py, traceability.py, jira.py, agents.py, users.py, projects.py, health.py, settings.py |
| Services | requirement_service.py, jira_service.py, traceability_service.py, approval_service.py, agent_run_service.py, agent_dispatch_service.py, execution_service.py, defect_service.py, test_plan_service.py, automation_service.py, report_service.py, rbac_service.py, document_service.py |
| Workers | celery_app.py, tasks/agent_tasks.py, tasks/jira_tasks.py, tasks/document_tasks.py |
| Migrations | 001–006 Alembic versions |
| Tests | 15 test files |

### Frontend
| File | Lines |
|---|---|
| requirements/page.tsx | 850 |
| test-planning/page.tsx | 639 |
| execution/page.tsx | 439 |
| defects/page.tsx | 487 |
| automation/page.tsx | 536 |
| reports/page.tsx | 333 |
| dashboard/page.tsx | 343 |
| src/lib/api.ts | N/A (API client) |
| src/components/layout/Sidebar.tsx | N/A |

---

## MODULE 1: DASHBOARD

### What Exists
- Project selector driving per-project stats (requirements, test cases, automation, execution, defects)
- 9-agent pipeline status panel showing latest run status per agent
- Recent execution runs list with pass/fail metrics
- Recent agent runs log

### What Is Good
- Real API calls to per-module services — stats are not hardcoded
- Agent pipeline visualization is unique and useful
- Pass-rate progress bars are clean and readable

### Critical Gaps
| Gap | Severity |
|---|---|
| No Jira sync health indicator | High |
| No pending approvals count or link | High |
| No traceability coverage overview | High |
| No release readiness indicator | High |
| No domain/phase breakdown (Billing vs Mobile vs CRM) | High |
| Stat cards load independently without loading skeleton | Medium |
| No drill-down from stats to filtered module view | Medium |
| No DEMO_MODE banner (simulated data not labelled) | High |
| No quick-action links from dashboard | Low |
| No activity feed showing cross-module events | Low |

### Data Model Concerns
None — the dashboard queries existing models correctly. Gaps are UX-level.

### Verdict
Dashboard is a functional status panel, not a command center. It needs release readiness, approval governance, Jira sync health, and domain-aware metrics before it is enterprise-ready.

---

## MODULE 2: REQUIREMENTS
*(Full deep-dive covered in REQUIREMENTS_MODULE_REVIEW.md — summary here)*

### Critical Gaps (repeated for completeness)
- 22 telecom-domain fields entirely absent from `Requirement` model
- `quality_score` / `quality_feedback` declared in schema but absent from model
- Quality agent matches by title string — breaks on duplicates/title changes
- No `readiness_status` field — no downstream generation gate
- Read endpoints require `approve_requirements` — Viewer role locked out
- No requirement versioning
- No traceability visible in UI
- Quality review has no telecom domain dimensions

### Verdict
See `REQUIREMENTS_MODULE_REVIEW.md`. Redesign required before scaling.

---

## MODULE 3: TEST PLANNING

### What Exists
- Test Plan generation via Agent 3 (LangGraph, LLM)
- Scenario generation via Agent 4 (per-requirement, 3-5 scenarios each)
- Test Case generation via Agent 5 (2-4 per scenario with full BDD steps)
- Approval flow for test plans (approve/reject with notes)
- Async Celery dispatch via `enqueue_agent_run`
- Frontend: expandable plan cards, scenario accordion, test case list with step viewer

### What Is Good
- Per-requirement scenario generation preserves requirement context
- Test cases include preconditions, test_data, steps, expected_result, BDD format
- `automation_candidate` boolean flags test cases for automation
- Status lifecycle: draft → pending_approval → approved → rejected
- Frontend shows linked scenarios per requirement after generation

### Critical Gaps
| Gap | Severity |
|---|---|
| Planning agent receives no telecom context — `telecom_domain`, `test_phase`, `risk_level`, `impacted_interfaces`, `release_version` are not passed to the LLM | Critical |
| Scenario agent passes only title, summary, AC, business_rules — no telecom fields | Critical |
| No readiness gate — test plans can be generated from draft/poor-quality requirements | Critical |
| `PLANNING_SYSTEM` prompt has no mention of SIT, UAT, Regression, NFR, API testing, integration testing, telecom protocols | High |
| `SCENARIO_SYSTEM` generates generic scenarios — no OCS charging flows, BSS order management, diameter protocol edge cases | High |
| Test plan model missing: `test_phase`, `release_version`, `telecom_domains_covered`, `environment_config`, `entry_exit_criteria_version` | High |
| Scenario model missing: `test_phase`, `environment`, `test_data_requirements`, `automation_priority` | Medium |
| No scenario de-duplication — running agent twice doubles scenarios | High |
| Scenario counter resets per-run — TS-001 appears in multiple runs for same project | High |
| Frontend: no filter by scenario type (positive/negative/boundary) | Medium |
| Frontend: no ability to manually add scenarios or edit generated ones | Medium |
| No bulk approve/reject for test cases | Medium |
| `test_plan_service.py` — list_plans has no pagination | Medium |
| Test case `test_data` is a JSONB dict — no structured test data model linkage | Medium |

### Agent Quality Observations
The planning agent prompt is generic QA Manager language — it will produce identical structures for a Billing requirement and a Mobile requirement. Critical telecom test types (OCS Ro/Gy, BSS provisioning, CDR generation, SLA breach) will never appear unless prompted with telecom context.

Scenario agent generates 3-5 scenarios per requirement by default. For a simple requirement with 2 acceptance criteria, this produces correct output. For a complex Charging requirement with 8 AC and 3 APIs, 3-5 scenarios is severe under-coverage.

### Security / RBAC
- `trigger_test_planning` uses `approve_test_plans` permission — correct
- No cross-project check on requirement_ids passed to agent trigger — a user in Project A could pass requirement IDs from Project B

### Performance / Scale
- No batch generation for large projects (50+ requirements) — single Celery task handles all
- `list_requirements` in test plan trigger fetches all approved requirements without limit
- Frontend loads all scenarios and test cases at once — no pagination

### Verdict
Structurally correct but telecom-blind. The agent pipeline works end-to-end; the output quality is generic and will fail telecom QA review without telecom domain injection.

---

## MODULE 4: AUTOMATION

### What Exists
- Agent 7 generates Playwright (TypeScript) or Pytest scripts per test case
- Two prompt systems: `PLAYWRIGHT_SYSTEM` and `PYTEST_SYSTEM`
- Framework selection (playwright/pytest) as input parameter
- Script model: script_id, framework, file_path, code, setup_required, execution_command
- Approval lifecycle: draft → pending_approval → approved
- Frontend: syntax-highlighted code view, copy button, execution command display
- JSON repair utility `_repair_json` for malformed LLM output

### What Is Good
- Framework abstraction (playwright/pytest) with distinct prompts
- `_repair_json` utility is a practical safeguard against LLM escape character issues
- Execution command stored alongside script for reproducibility
- Approval gate before script can be executed

### Critical Gaps
| Gap | Severity |
|---|---|
| Generated code is LLM hallucinated — uses `data-testid` selectors that don't exist in the actual application | Critical |
| No real test execution — execution agent is completely simulated (see Module 5) | Critical |
| No test environment configuration in scripts — hardcoded `localhost:3000` assumed | Critical |
| Scripts have no link to actual application pages, APIs, or endpoints | High |
| No script versioning — re-running agent overwrites or duplicates | High |
| Generated Playwright code references UI elements that are inferred, not validated | High |
| No script linting or syntax validation before persistence | High |
| `_repair_json` uses character-by-character scanning — breaks on very large scripts | Medium |
| No support for API test scripts (httpx/requests) for telecom API testing | High |
| No environment variables injection pattern in generated scripts | High |
| No page object model template — scripts are monolithic | Medium |
| Frontend: no script edit capability | Medium |
| Frontend: no run-in-sandbox button | Medium |
| Automation model missing: `language`, `target_url`, `environment_config`, `last_execution_result`, `script_version` | Medium |
| No telecom protocol test support (diameter, SOAP, REST for OSS/BSS APIs) | High |

### Verdict
The automation generation feature produces syntactically correct but functionally unusable scripts. They are placeholder templates, not runnable automation. The downstream execution module simulates results from these templates. This is the largest disconnect from real enterprise value in the entire platform.

---

## MODULE 5: EXECUTION

### What Exists
- Agent 8 (`TestExecutionAgent`) — reads test cases, returns execution results
- `EXECUTION_SYSTEM` prompt instructs LLM to return 70% passed / 20% failed / 10% skipped
- ExecutionRun model: suite_name, environment, status, passed/failed/skipped counts
- ExecutionResult model: test_name, status, duration_ms, error_message, stack_trace, logs
- Frontend: run cards with pass rate bar, expandable failed test details
- Defect auto-generation from failed results (calls defect agent after execution)

### What Is Good
- ExecutionResult model has screenshot_path, video_path, trace_path (correct forward-looking design)
- Defect agent is automatically triggered after failed results
- Pass rate visualization is clear and functional
- AgentRun tracking is properly integrated

### Critical Gaps — THIS MODULE IS FUNDAMENTALLY SIMULATED
| Gap | Severity |
|---|---|
| **Execution is 100% LLM-simulated** — the agent instructs the LLM to generate realistic-looking pass/fail results | Critical |
| No real test runner integration (Playwright, Pytest, CI/CD) | Critical |
| `DEMO_MODE` flag does not exist in execution logic — there is no way to distinguish simulated from real results | Critical |
| Generated error messages are LLM hallucinations ("AssertionError: Expected 200, got 401") — not real failures | Critical |
| No actual script execution via subprocess or container | Critical |
| No screenshot capture, video capture, or trace capture | High |
| No environment validation before execution | High |
| Environment field is passed as a string — no connection to actual environment config | High |
| ExecutionRun has no `simulated` flag — real and simulated results are indistinguishable in DB | Critical |
| `allure_report_path` is stored but never generated | High |
| No execution timeout enforcement | High |
| No test parallelization or execution ordering | Medium |
| Frontend: no distinction between simulated and real run results | Critical |
| No retry mechanism for flaky test cases | Medium |
| No execution scheduling (cron, CI trigger) | Low |

### Verdict
This is the most critical gap in the entire platform. The execution module is a demonstration simulator, not a test execution engine. All defects generated are fictitious. All pass/fail rates are fictitious. All release readiness decisions based on this data are fictitious. Replacing this with real Playwright/Pytest execution is a prerequisite for any production use.

---

## MODULE 6: DEFECTS

### What Exists
- Agent 9 (`DefectAnalysisAgent`) generates defect drafts from failed execution results
- DefectDraft model: summary, description, steps_to_reproduce, expected/actual result
- Severity (Critical/High/Medium/Low), priority, root_cause_hypothesis, classification
- JiraDefect model for post-push Jira issue tracking
- Approval workflow: draft → pending_approval → approved → pushed_to_jira → rejected
- Jira push endpoint (via jira_service) — creates Bug in Jira if connection configured
- Frontend: defect cards with severity/classification badges, expand for details

### What Is Good
- Two-table design (DefectDraft + JiraDefect) cleanly separates local drafts from Jira records
- classification field (product_defect/automation_issue/environment_issue/test_data_issue) is enterprise-grade
- Jira push is gated behind approval — no unauthorized Jira bug creation
- Duplicate Jira bug prevention via `unique=True` on defect_draft_id FK

### Critical Gaps
| Gap | Severity |
|---|---|
| All defects are generated from **simulated execution results** — they are fictitious | Critical |
| No telecom triage fields: `impacted_domain`, `impacted_system`, `impacted_interface`, `test_phase`, `release_version`, `environment` | High |
| No `detected_by` field (automated vs manual) | Medium |
| No `assigned_to` field | Medium |
| No defect lifecycle beyond status string — no transitions, no SLA, no resolution fields | High |
| No `linked_requirement_id` on DefectDraft — cannot trace defect back to requirement | High |
| Jira sync is push-only — no pull-back of Jira defect status changes | High |
| No `sync_status`, `last_synced_at`, `sync_error` on DefectDraft | High |
| No retry mechanism on Jira push failure | Medium |
| No audit log for Jira push operations | Medium |
| No defect deduplication — same failure can create multiple defects on repeated execution | High |
| Frontend: no defect search or filter by domain/phase/release | Medium |
| Frontend: no Jira key link to open defect in Jira after push | High |
| Frontend: no defect trend chart | Low |
| `list_defects` has no pagination | Medium |
| No decision_type enforcement (per PRINCIPLE-05 — undecided failures block release) | High |

### Verdict
The defect data model is 60% enterprise-ready. The critical gap is that all defects currently originate from simulated execution results. The Jira integration skeleton is in place but lacks two-way sync. Telecom triage fields are absent.

---

## MODULE 7: REPORTS

### What Exists
- Agent 11 (`TestReportingAgent`) — generates QA status reports
- Report types: daily / weekly / sprint / release
- `REPORT_SYSTEM` prompt asks LLM to generate coverage, execution_metrics, defect_metrics sections
- `report_service.py` aggregates real DB metrics (requirements count, test case count, execution stats, defect count)
- Report model: coverage (JSONB), execution_metrics (JSONB), defect_metrics (JSONB), risks, recommendations
- Frontend: expandable report cards with metric sections, progress bars

### What Is Good
- `report_service.py` actually queries the database for real metrics before calling the LLM
- Report sections map to real fields — not purely hallucinated
- Multiple report types supported
- Draft → approved lifecycle with approval endpoint

### Critical Gaps
| Gap | Severity |
|---|---|
| Real DB metrics are passed to LLM, but LLM rewrites them freely — final report numbers may not match DB | Critical |
| Reporting agent uses `achat` method not `generate` — inconsistency with other agents | Medium |
| No telecom domain breakdown in reports (Billing vs CRM vs Charging quality split) | High |
| No test_phase breakdown (SIT vs UAT vs Regression) | High |
| No go/no-go recommendation with rule engine | Critical |
| No traceability gap section | High |
| No Jira sync status in reports | High |
| No release readiness report type (only daily/weekly/sprint/release) — release type exists but has no special go/no-go logic | High |
| All execution metrics are based on **simulated execution results** | Critical |
| `report_service.py` uses `execute_run` (sync) — may not work with async sessions | Medium |
| No report export (PDF, Excel) | Medium |
| Frontend: no release readiness dashboard | High |
| Frontend: report list is reverse chronological only — no filter by type or date | Medium |
| Report model missing: `telecom_domains`, `test_phase`, `go_nogo_recommendation`, `traceability_gaps` | High |
| Report metrics stored as JSONB — no structured schema enforcement | Medium |

### Verdict
The reporting module has the right shape but wrong data. It passes real counts to the LLM but the LLM can rewrite them. The go/no-go logic is absent. Telecom domain reporting is absent. Release readiness decision-making is not implemented.

---

## MODULE 8: JIRA INTEGRATION

### What Exists
- JiraConnection model with Fernet-encrypted credentials
- JiraSyncHistory, ConflictRecord, WebhookEvent models (all well-designed)
- Inbound sync (Jira → platform): JQL-based fetch, idempotent upsert by jira_issue_key
- Outbound sync (platform → Jira): push comments/fields for AI review, approval status, test scenarios
- Webhook receive endpoint with HMAC signature verification
- Celery tasks: inbound_sync, outbound_sync, two_way_sync, process_jira_webhook
- Conflict detection and ConflictRecord creation
- Batch processing (configurable batch_size)
- Frontend: connection management, filter UI, fetch preview, import button, sync status

### What Is Good
- Fernet encryption for Jira API tokens — never plaintext in DB
- ConflictRecord design with local_snapshot/remote_snapshot JSONB
- Webhook deduplication via event_key UniqueConstraint
- HMAC signature verification on webhook endpoint
- Full JiraSyncHistory audit trail
- Celery task design correctly separates HTTP request from processing

### Critical Gaps
| Gap | Severity |
|---|---|
| Jira import does NOT populate the 22 telecom fields on Requirement — Jira metadata is not mapped to domain, risk, test_phase | High |
| `jira_issue_id` not stored on Requirement (only `jira_issue_key`) — key renames break traceability | High |
| `jira_status`, `jira_assignee`, `jira_reporter`, `jira_labels`, `jira_components`, `jira_fix_versions`, `jira_sprint`, `jira_epic_key` not stored on Requirement | High |
| `sync_status`, `sync_error` not on Requirement model | High |
| No webhook endpoint currently registered in main router — WebhookEvent model exists but endpoint may not be active | Medium |
| Outbound sync pushes comments to Jira, but requirement approval status sync depends on telecom fields not existing yet | Medium |
| No real-time Jira sync indicator in requirements list UI | High |
| Conflict resolution UI exists in design spec but not in current frontend | High |
| No scheduled sync (cron-triggered, only manual and webhook-triggered) | Medium |
| `last_sync_at` on JiraConnection is a String, not DateTime — schema inconsistency | Low |
| No epic/sprint/component filter chips in Jira fetch UI | Medium |

### Verdict
The Jira integration infrastructure is the strongest part of the platform. The models, service layer, and Celery tasks are well-designed. The main gap is that imported Jira data is not mapped to telecom fields on the Requirement model, so the platform cannot leverage Jira's fix_version, sprint, component, or label data for telecom-specific filtering.

---

## MODULE 9: TRACEABILITY & APPROVAL GOVERNANCE

### What Exists
- ArtifactLineage model: parent_type/id → child_type/id, agent_run_id, correlation_id (append-only)
- ApprovalAction model: entity_type, entity_id, decision, actor_user_id, actor_role, notes, old/new value, jira_issue_key
- Traceability matrix API: `GET /api/v1/traceability/projects/{id}/matrix` with domain/phase/release filters and pagination
- Coverage gaps API: `GET /api/v1/traceability/projects/{id}/gaps`
- Approval endpoint: `POST /api/v1/traceability/approvals/{entity_type}/{entity_id}`
- `traceability_service.py`: builds matrix rows by joining all STLC artifacts, detects gaps
- No dedicated frontend traceability page — matrix data not surfaced in UI

### What Is Good
- ArtifactLineage is correctly append-only by design
- ApprovalAction includes old_value/new_value JSONB for diff audit
- Traceability matrix API supports filtering by domain, phase, release — forward-looking design
- Coverage gap types: no_test_cases, no_approved_test_cases, no_execution, undecided_failures

### Critical Gaps
| Gap | Severity |
|---|---|
| No traceability page in the frontend — data is queryable via API but invisible to users | High |
| Traceability matrix cannot filter by `domain` or `test_phase` because those fields don't exist on Requirement yet | Critical |
| No "undecided_failures" count in current traceability matrix — PRINCIPLE-05 compliance is not enforced | High |
| ApprovalAction history is not queryable per-requirement in the frontend | High |
| No "approve all" bulk operation for test cases | Medium |
| No traceability visualization (matrix grid, coverage heat map) | High |
| Approval endpoint uses entity_type as a string — no validation against allowed types | Low |
| No approval history tab in any module detail view (except partial in requirements drawer design) | High |
| `traceability_service.py` builds matrix with N+1 queries — will be slow at scale | High |

### Verdict
The backend traceability infrastructure is well-designed and close to enterprise-grade. The critical gap is that none of it is visible in the frontend, and the filtering depends on telecom fields that don't exist yet. At telecom scale (10,000+ test cases), the current N+1 query pattern will time out.

---

## MODULE 10: AGENT INFRASTRUCTURE (CROSS-CUTTING)

### What Exists
- AgentRun model with: idempotency_key, progress_percent, progress_message, prompt_version, input_hash, celery_task_id
- AgentLog model for structured step-level logging
- `agent_run_service.py`: start/complete/fail/cancel AgentRun, update progress
- `agent_dispatch_service.py`: enqueue_agent_run — creates AgentRun + dispatches Celery task
- `agent_tasks.py`: Celery task router dispatching to correct agent
- HTTP 202 returns on all agent trigger endpoints
- Idempotency key deduplication: same key = return existing run
- Retry policy in Celery tasks (configurable)

### What Is Good
- Idempotency via SHA-256 key on all agent triggers — prevents duplicate runs from double-clicks
- Progress tracking (percent + message) allows frontend polling
- AgentLog table gives per-step audit trail
- All agents use typed LangGraph StateGraph — correct async pattern

### Critical Gaps
| Gap | Severity |
|---|---|
| `structured_schemas.py` — `RequirementQualityLLMOutput` has no `telecom_domain_completeness_score` or `scenario_generation_readiness` | High |
| Quality agent still uses fragile `re.search(r'\[.*\]', text, re.DOTALL)` regex — not governed pipeline | High |
| Planning agent uses regex JSON extraction too (`re.search(r'\{.*\}', text, re.DOTALL)`) | High |
| Scenario agent uses regex extraction despite structured_schemas existing for it | High |
| No LLMCallLog model — LLM call telemetry (provider, model, tokens, duration, validation_status) not captured | High |
| Prompt injection detection not implemented — Jira descriptions flow directly to LLM prompt | High |
| No circuit breaker for LLM provider failures | Medium |
| No telecom context injection in any agent prompt | Critical |
| AgentRun status includes `pending` but launch sequence uses `queued` inconsistently | Low |
| No agent progress polling UI — frontend only shows final result | Medium |

### Verdict
The agent infrastructure skeleton is enterprise-grade in design. The agents themselves are generic and lack telecom domain awareness. The LLM governance layer (structured validation, injection protection, telemetry) is partially implemented but inconsistently applied across agents.

---

## MODULE 11: SECURITY & RBAC

### What Exists
- JWT bearer token authentication on all business endpoints
- ProjectMembership model: user_id + project_id + role
- RBAC permissions: view_project, manage_project, sync_jira, approve_requirements, approve_test_plans, approve_test_cases, generate_automation, execute_tests, raise_defects, push_defects_to_jira, approve_release_report, view_audit_logs
- Roles: Platform Admin, QA Manager, Test Lead, Tester, Automation Engineer, Release Manager, Defect Manager, Business Analyst, Viewer/Auditor
- `require_permission(permission, project_id, user, db)` FastAPI dependency
- `require_project_access(project_id, user, db)` for read-only access
- `require_entity_permission(entity, permission, user, db)` for object-level checks

### What Is Good
- RBAC is backend-enforced — not frontend-only
- Project membership model supports different roles per project per user
- All agent trigger endpoints require appropriate permissions
- Cross-project access checks prevent data leakage

### Critical Gaps
| Gap | Severity |
|---|---|
| `GET /requirements/project/{id}` requires `approve_requirements` — Viewer/Auditor role cannot read requirements | High |
| `GET /requirements/{req_id}` same issue | High |
| `PATCH /{req_id}` on requirements has no terminal status guard — approved requirements can be silently modified | High |
| No test suite for cross-project isolation (only basic auth tests exist) | Medium |
| Platform Admin bypass needs explicit test | Medium |
| No rate limiting on auth endpoints | Low |
| No token refresh endpoint documented in README | Low |
| Jira credentials logged in some error paths (needs audit) | High |

### Verdict
RBAC implementation is structurally correct and backend-enforced. Two critical read permission bugs exist that block Viewer/Auditor role functionality. The silent modification of approved artifacts is a data integrity risk.

---

## MODULE 12: LLM PROVIDER & RESILIENCE

### What Exists
- `llm/provider.py`: provider abstraction (OpenAI, Ollama, other LLM providers)
- `llm/structured.py`: `validate_structured_output()` for Pydantic schema validation
- Structured schemas: RequirementLLMOutput, RequirementQualityLLMOutput, TestPlanLLMOutput, TestScenarioLLMOutput, TestCaseLLMOutput, AutomationScriptLLMOutput, ExecutionResultLLMOutput, DefectLLMOutput, ReportLLMOutput

### What Is Good
- Provider abstraction allows LLM switching via config
- Pydantic schemas with `extra="ignore"` and field validators are correct design
- `_string_list` normalizer handles various LLM response shapes for list fields

### Critical Gaps
| Gap | Severity |
|---|---|
| Most agents **bypass** `validate_structured_output` and use regex extraction directly | Critical |
| Only quality_agent and intake_agent consistently use the structured validation pipeline | High |
| No circuit breaker implementation | High |
| No retry with exponential backoff — transient LLM failures cause immediate agent failure | High |
| No `LLMCallLog` model for per-call telemetry | High |
| No prompt injection sanitization | High |
| No prompt versioning stored with output | Medium |
| `reporting_agent.py` uses `llm.achat()` instead of `llm.generate()` — API inconsistency | Low |

---

## MODULE 13: SETTINGS & CONFIGURATION

### What Exists
- Settings page (frontend) with project-level config
- `config.py`: typed settings via Pydantic Settings
- `.env.example` present

### Critical Gaps
| Gap | Severity |
|---|---|
| No production startup validation (APP_SECRET_KEY, APP_DEBUG, DEMO_MODE, DB/Redis reachability checks) | High |
| API docs (/docs, /redoc) not disabled in production | High |
| No configurable go/no-go thresholds per project | High |
| No per-project telecom domain configuration | Medium |
| No Jira field mapping UI in settings | High |
| DEMO_MODE flag not in config or enforced anywhere | Critical |

---

## CROSS-CUTTING ISSUES

### 1. The Simulation Problem (MOST CRITICAL)
The entire platform from Module 5 onwards operates on simulated data:
- Execution results are LLM-generated (fictitious pass/fail)
- Defects are generated from fictitious failures
- Reports aggregate metrics based on fictitious results
- Release readiness would be based on fictitious data

This is acceptable for demo purposes but makes the platform **not deployable** for real QA governance without addressing execution first.

### 2. Telecom Blindness
No agent prompt mentions SIT, UAT, Regression, OCS, BSS, OSS, Billing, Charging, CRM, Diameter, SOAP, CDR, provisioning, MSISDN, network element, or any telecom concept. Every module generates generic output. A Billing domain requirement and a Digital app requirement receive identical treatment.

### 3. UI Pattern Inconsistency
Each frontend page follows a slightly different UI pattern:
- Requirements page: three-tab layout (Requirements / Documents / Jira)
- Test Planning: accordion cards per plan
- Execution: card grid + expandable result rows
- Defects: card list with expand
- Automation: card list with code viewer
- Reports: card list with section expansion

No shared component library exists. StatusBadge is redefined in every page file. This will cause visual drift as the platform evolves.

### 4. Missing Observability
- No structured JSON logging — `print()` and basic `logging.getLogger()` used
- No /metrics endpoint for Prometheus
- No request_id propagation
- No Celery task correlation to request_id
- No per-module health sub-checks

### 5. Performance at Scale
Every list endpoint returns up to 500 records with full objects. No cursor pagination exists. At 10,000 test cases and 5,000 requirements (typical large telecom project), the platform will time out on first page load.

---

## COMPLETE GAP INVENTORY BY PRIORITY

### P0 — CRITICAL (Blocks enterprise production use)

| ID | Module | Gap |
|---|---|---|
| P0-01 | Execution | Replace LLM-simulated execution with real Playwright/Pytest runner |
| P0-02 | Execution | Add `simulated` flag to ExecutionRun — distinguish demo from real |
| P0-03 | All agents | Inject telecom domain context into all LLM prompts |
| P0-04 | Requirements | Add 22 telecom fields to Requirement model |
| P0-05 | Requirements | Fix `quality_score` schema/model inconsistency |
| P0-06 | Requirements | Fix read permissions (view_project vs approve_requirements) |
| P0-07 | Test Planning | Add readiness gate before test plan/scenario generation |
| P0-08 | All agents | Fix regex JSON extraction → governed Pydantic validation pipeline |
| P0-09 | Config | Add DEMO_MODE flag enforced at startup in production |
| P0-10 | Reports | Prevent LLM from rewriting real DB metrics in report sections |

### P1 — HIGH (Reduces enterprise value significantly)

| ID | Module | Gap |
|---|---|---|
| P1-01 | Defects | Add telecom triage fields (impacted_domain, impacted_system, test_phase, environment) |
| P1-02 | Defects | Add linked_requirement_id to DefectDraft |
| P1-03 | Defects | Add Jira defect status sync (pull-back) |
| P1-04 | Jira | Map imported Jira fields to telecom fields on Requirement |
| P1-05 | Jira | Store jira_issue_id, jira_status, jira_labels, jira_sprint, jira_epic_key on Requirement |
| P1-06 | Reports | Add go/no-go recommendation rule engine |
| P1-07 | Reports | Add telecom domain and test_phase breakdown |
| P1-08 | Traceability | Add traceability frontend page (matrix view) |
| P1-09 | Traceability | Fix N+1 query pattern in traceability_service |
| P1-10 | Dashboard | Add pending approvals, Jira sync health, release readiness indicators |
| P1-11 | Requirements | Add requirement versioning |
| P1-12 | Security | Add terminal status guard on PATCH requirements |
| P1-13 | Agent | Add LLMCallLog model and per-call telemetry |
| P1-14 | Agent | Add prompt injection sanitization |
| P1-15 | All | Add cursor-based pagination to all list endpoints |

### P2 — MEDIUM (UX, completeness, quality improvements)

| ID | Module | Gap |
|---|---|---|
| P2-01 | Test Planning | Add scenario deduplication guard |
| P2-02 | Test Planning | Fix scenario counter resetting between runs |
| P2-03 | Automation | Add script linting/syntax validation before persistence |
| P2-04 | Automation | Add environment variable injection pattern to scripts |
| P2-05 | Automation | Add support for API/HTTP test scripts |
| P2-06 | Defects | Add defect deduplication (same failure → same defect) |
| P2-07 | Jira | Add scheduled sync (cron-based) |
| P2-08 | Reports | Add PDF/Excel export |
| P2-09 | Dashboard | Add domain-wise quality breakdown |
| P2-10 | All | Shared component library (StatusBadge, etc.) |
| P2-11 | Settings | Add go/no-go threshold configuration per project |
| P2-12 | Settings | Add Jira field mapping UI |
| P2-13 | Observability | Add structured JSON logging + /metrics endpoint |
| P2-14 | LLM | Add circuit breaker and retry/backoff |
| P2-15 | Config | Add production startup validation |

### P3 — NICE TO HAVE

| ID | Module | Gap |
|---|---|---|
| P3-01 | Traceability | Coverage heat map visualization |
| P3-02 | Test Planning | AI test plan quality review before approval |
| P3-03 | Execution | Execution scheduling (CI/CD trigger) |
| P3-04 | Automation | Page object model template generation |
| P3-05 | Dashboard | Trend charts (7-day/30-day quality trends) |
| P3-06 | Reports | AI-powered QA health score |
| P3-07 | All | Export to Excel/CSV per module |
| P3-08 | Defects | SLA/aging alerts for open defects |
| P3-09 | Requirements | Requirement similarity/duplicate detection |
| P3-10 | Agent | Multi-model LLM routing per agent type |

---

## MODULE MATURITY SCORES

| Module | Backend Model | API | Agent Quality | Frontend | Telecom-Ready | Enterprise Security |
|---|---|---|---|---|---|---|
| Requirements | 45% | 70% | 40% | 55% | 10% | 75% |
| Test Planning | 60% | 65% | 35% | 60% | 10% | 70% |
| Automation | 65% | 65% | 30% | 65% | 15% | 65% |
| **Execution** | **50%** | **60%** | **5%** | **55%** | **0%** | **60%** |
| Defects | 55% | 65% | 40% | 65% | 20% | 65% |
| Reports | 55% | 60% | 35% | 55% | 15% | 65% |
| Jira Integration | 80% | 85% | N/A | 70% | 50% | 90% |
| Traceability | 80% | 80% | N/A | 15% | 40% | 75% |
| Agent Infrastructure | 70% | 70% | 50% | 40% | 10% | 65% |
| Dashboard | 60% | 70% | N/A | 50% | 10% | 70% |
| Security/RBAC | 75% | 75% | N/A | 65% | N/A | 75% |
| LLM Governance | 40% | N/A | 35% | N/A | N/A | 50% |

**Overall Platform Maturity: ~52% — Functional Demo / Not Enterprise-Ready**

---

## RECOMMENDED IMPLEMENTATION ORDER

Phase A (Prerequisite — must precede all others):
1. Add telecom fields to Requirement model (P0-04)
2. Fix LLM governance — remove regex extraction (P0-08)
3. Inject telecom context into all agent prompts (P0-03)
4. Fix quality_score inconsistency (P0-05)
5. Fix read permissions (P0-06)

Phase B (Core execution value):
6. Replace simulated execution with real test runner (P0-01)
7. Add DEMO_MODE flag and simulated flag (P0-02, P0-09)
8. Add readiness gate before generation (P0-07)
9. Add telecom triage fields to Defects (P1-01, P1-02)

Phase C (Reporting and governance):
10. Fix report metrics immutability (P0-10)
11. Add go/no-go rule engine (P1-06)
12. Add telecom domain breakdown to reports (P1-07)
13. Add traceability frontend page (P1-08)
14. Add pending approvals + Jira health to dashboard (P1-10)

Phase D (Scale and observability):
15. Cursor pagination everywhere (P1-15)
16. Fix traceability N+1 queries (P1-09)
17. Add LLMCallLog + structured logging + metrics (P1-13, P2-13)
18. Add circuit breaker and retry (P2-14)

---

*End of PROJECT_MODULES_REVIEW.md*
