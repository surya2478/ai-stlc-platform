# Agentic Automation Implementation Plan (nxtQA)

**Status:** Approved for implementation (external review verdict: "approved with minor mandatory additions" — all incorporated) · **Date:** 2026-07-09
**Governing ADR:** [ADR_001_CONTROLLED_AUTOMATION_GENERATION.md](ADR_001_CONTROLLED_AUTOMATION_GENERATION.md) · Supersedes chat-level proposals.

## 1. Objective

Evolve the STLC platform's agent architecture so that:

1. Every stage artifact (requirement → scenario → test case → script → execution → defect → report) passes a **senior review gate** before promotion.
2. Automation scripts are **grounded in the real UI** via Playwright MCP instead of blind LLM codegen.
3. Consistency is enforced by a **controlled generation framework** — templates, contracts, deterministic validators, coverage tracking, and human approval — not by adding more LLM reviewers alone.

**Governing principle (from review):** nxtQA remains the test intelligence engine. MCP is a browser-grounding layer only. AI drafts; standards, templates, validators, execution evidence, and approval gates enforce consistency.

**Non-negotiable rule (ADR-001): No Free-Form Script Generation.** No agent persists `.spec.ts`/`.py` as final output — ever, including repair/healing loops. Agents emit the versioned Automation Generation Contract (JSON); the Script Compiler renders all code. Enforced by schema validation, a compiler-stamped generation header, and Static Quality Gate rejection of unstamped code.

**What each phase actually fixes** (set expectations accordingly in management communication):

| Phase | Improves |
|---|---|
| 2 | Script **consistency** (structure, POM, naming, assertions, evidence hooks) |
| 3 | Locator **correctness** (real UI grounding) |
| 4 | Executable **reliability** (dry-run-proven scripts) |
| 5 | Long-term **stability** (healing, drift maintenance, CI) |

## 2. Current Asset Inventory — build on, don't rebuild

| Capability | Existing asset | Reuse in this plan |
|---|---|---|
| Agent lifecycle, audit, idempotency, progress | `agent_run_service.py`, `agent_dispatch_service.py`, `AgentRun`/`AgentLog` | All new agents register in `AGENT_REGISTRY` and inherit this for free |
| Per-project LLM routing + fallback + circuit breaker | `llm/provider.py`, `project_llm_settings_service.resolve_project_llm_routes(module_scope=...)` | Reviewers run on stronger model routes via `module_scope` |
| Reviewer-agent template | `requirement/quality_agent.py` (7 dimensions, verdicts, `RequirementQualityReview`) | Pattern generalized into `BaseReviewerAgent` |
| Rule-based script analysis | `services/automation_intelligence.py` (hard waits, weak locators, assertion gaps, data issues, health score) | Becomes the deterministic half of the Static Quality Gate |
| Script execution runner + artifacts | `services/automation_runner/` (workspace, playwright/pytest subprocess, trace/video/screenshot) | Dry-run + repair loop executes through it unchanged |
| Runner preflight | `automation_runner/preflight.py` | Extended into full Environment Readiness Check |
| Test data module | `TEST_DATA_MANAGEMENT_DESIGN.md`, `test_data_service.py`, `test_data_generation/` (faker + telco providers), `parameter_binding.py` (`${placeholder}` binding) | Script generation binds test data through this module; no new TDM system |
| Traceability | `traceability_service.py` (`ArtifactLineage`) | Coverage Matrix is built on top of lineage, not parallel to it |
| Approval audit | `approval_service.py` (`ApprovalAction`) | Extended with granular script lifecycle states |
| Prompt-injection hardening | `<user_content>` data-fencing pattern (see `test_case_agent.py`) | Applied to all MCP snapshots and page content |
| Error/PII redaction | `agent_run_service.sanitize_error`, sensitive-pattern scrubbing | Extended to MCP evidence (snapshots, logs) |

## 3. Target End-to-End Flow

```text
1.  Requirement / Jira / PRD / UI / URL / Code input
2.  Requirement Intelligence Agents (intake, ui/url/code analysis)     [exists]
3.  Senior Requirement Reviewer                                        [exists: quality_agent — upgraded]
4.  Scenario Generator                                                 [exists]
5.  Scenario Reviewer + Coverage Matrix update                         [NEW]
6.  Test Case Generator (phase-aware: SIT/QA/UAT/Regression/Prod-Sanity) [exists — upgraded]
7.  Test Case Reviewer (coverage map vs acceptance criteria)           [NEW]
8.  Automation Eligibility Agent (pass 1: static, from TC text)        [NEW]
9.  Playwright MCP Discovery Agent → persists Locator Map              [NEW]
    + Eligibility pass 2: confirm UI availability / OTP / Captcha
10. Script Generator → structured JSON contract → Script Compiler     [NEW: contract + compiler]
    (approved template, POM, locator policy, test data bindings)
11. Static Quality Gate (tsc, eslint, playwright --list, rule engine)  [NEW; rule engine exists]
12. Dry Run Execution (trace/screenshot/video/console/network)         [runner exists; artifacts extended]
13. Failure Classification (app defect | locator | data | env | API | timeout) [NEW]
14. Bounded Repair Loop (locator/wait/assertion fixes only)            [NEW]
15. Script Review Agent (LLM senior review on top of rule results)     [NEW]
16. Human Approval (multi-level statuses)                              [exists — statuses extended]
17. Git Promotion → PR → CI regression                                 [NEW]
18. Reporting / Defect Draft / Healing / Continuous Learning           [exists + NEW healing]
```

Routing after failure classification:
- **App defect** → `defect_analysis` agent → `DefectDraft` (→ Jira)
- **Data issue** → Test Data module task
- **Environment issue / timeout** → run flagged, no defect, readiness re-check
- **Locator issue** → Healing Recommendation → `healing_proposed` version → re-review → re-approval (never silent overwrite)

## 4. Phase Plan

### Phase 0 — Foundation hardening (prerequisite for everything)

Backend plumbing only; no product-visible change except stability.

| # | Work item | Where |
|---|---|---|
| 0.1 | Replace `AGENT_REGISTRY: dict[str, callable]` with `dict[str, AgentSpec]` — `callable`, `timeout_seconds`, `retry_policy`, `chain_on_success`, `module_scope` | `worker/tasks/agent_tasks.py` |
| 0.2 | Per-agent timeouts (defaults): requirement 120s · generators 180s · reviewers 180s · MCP discovery 300–600s · dry run 300–600s · regression execution uses runner timeout (existing 600s default) | same |
| 0.3 | Remove duplicated `classify_exception` / `_mark_agent_failed` definitions | `agent_tasks.py` (~L907 and ~L1060) |
| 0.4 | Unify result envelope: all agents return `AgentResult` (add `success`/`data`/`logs` aliases); delete per-agent ad-hoc result classes; remove `_is_success`/`_result_data` duck-typing | `base_agent.py` + every agent |
| 0.5 | On-success chaining hook in `_run_agent_task`: after persist+complete, enqueue `chain_on_success` agents with mapped inputs | `agent_tasks.py` |
| 0.6 | Cancellation: cancel endpoint → `AgentRun.status="cancelled"` + Celery revoke + cooperative check between graph nodes | `endpoints/agents.py`, `base_agent.py` |
| 0.7 | **Baseline metrics capture (before MCP)**: script generation success rate, dry-run pass rate, repairs needed, locator failure rate, hard-wait count, missing-assertion count (from `automation_intelligence`), manual correction effort, stability over 5 runs. Persist as a metrics snapshot so post-MCP improvement is provable | `metrics_service.py` + report |
| 0.8 | Housekeeping: remove `*_bkp.py` files (`intake_agent_bkp`, `quality_agent_bkp`, `requirements_bkp`, `requirement_service_bkp`) | backend |

**Exit criteria:** all existing agents run through `AgentSpec` with per-agent timeout; chaining demonstrated on one pair (test_case → placeholder reviewer); baseline metrics report generated for one project.

### Phase 1 — Review & coverage backbone

| # | Work item | Notes |
|---|---|---|
| 1.1 | `BaseReviewerAgent(BaseAgent)` with structured verdict schema: dimension scores, `issues[]`, `suggestions[]`, `coverage_gaps[]`, `verdict: pass/needs_revision/fail` | Pattern lifted from `quality_agent.py` |
| 1.2 | Migration: `artifact_reviews` table — `artifact_type`, `artifact_id`, `project_id`, `agent_run_id`, `reviewer_agent`, `scores JSONB`, `findings JSONB`, `coverage_gaps JSONB`, `verdict`, `review_mode` | Generic across all stages |
| 1.3 | Migration: `coverage_matrix` table — `requirement_id`, `acceptance_criteria_index`, `business_rule_index`, `scenario_id`, `test_case_id`, `test_type`, `risk_level`, `case_class` (positive/negative/boundary/exception), `automation_eligible`, `automation_reason`, `script_id`, `execution_status`, `defect_id`. Built/refreshed from `ArtifactLineage` + reviewer output; a DB object, not just reviewer prose | Mandatory per review feedback |
| 1.4 | `scenario_review` agent: receives requirement (ACs, business rules) + generated scenarios; emits coverage map + gaps; writes `artifact_reviews` + `coverage_matrix` rows | Chained after `test_scenario` via 0.5 |
| 1.5 | `test_case_review` agent: requirement + scenarios + TCs; checks step atomicity, test data presence, expected results, phase differentiation (SIT/QA/UAT/Regression/Prod-Sanity), AC coverage | Chained after `test_case` |
| 1.6 | Upgrade `requirement_quality` to write `artifact_reviews` too (single UI surface) | Keep `RequirementQualityReview` for back-compat |
| 1.7 | Project setting `review_mode: off / advisory / gating`; in gating mode approval endpoints reject artifacts with `verdict=fail` unless override-with-note (audited via `ApprovalAction`) | `project` settings + approval endpoints |
| 1.8 | Reviewer LLM routes: register reviewer `module_scope`s so reviewers can use a stronger model than generators | `project_llm_settings_service` |
| 1.9 | UI: review badges + findings drawer on Scenario/Test Case tables (replicate requirement quality badge); Coverage Matrix view with gap highlighting | frontend |

**Exit criteria:** generating scenarios/TCs auto-produces review verdicts + coverage rows; gating mode blocks approval of `fail` artifacts; coverage view shows uncovered ACs.

### Phase 2 — Script generation standardization (before MCP)

Controlled generation framework. The agent generates **into a schema**; the backend renders code deterministically. May start in parallel with Phase 1 once Phase 0 is complete — standardization does not depend on the reviewer backbone.

| # | Work item | Notes |
|---|---|---|
| 2.0 | **Golden sample scripts** — before any compiler code, manually author, review, and freeze 5–10 reference scripts: login flow, customer search, order creation, negative validation, role-based access check, API-backed validation, DB-backed validation, regression smoke, production sanity. These define what compiler output must look like; compiler conformance and reviewer calibration are measured against them | Reference standard (ADR-001) |
| 2.1 | **Automation Generation Contract** (Pydantic, **versioned — `contractVersion: "1.0"`**): `testCaseId`, `requirementId`, `testType`, `scriptType`, `businessFlow`, `preconditions`, `testDataBindings` (Test Data module `${placeholder}` refs), `pageObjects[]` (name, elements, locators), `steps[]` (arrange/act/assert phases), `expectedResults`, `assertions[]` (web-first `expect` patterns only), `locators[]`, `apiValidations[]`, `dbValidations[]`, `cleanupActions[]`, `evidenceRequired[]`, `environmentProfile`. Compiler supports schema version N and N-1 so older assets never break silently | Agent output = JSON, never raw code |
| 2.1b | **Multi-environment profiles** in the contract: DEV / SIT / QA / UAT / PREPROD / PROD_SANITY. Profile selects compiled validation depth — SIT: API + DB + integration validation; QA/Regression: reusable stable assertions; UAT: business-readable validation; PROD_SANITY: non-invasive read-only checks only, stricter approval path | Same TC, environment-appropriate script |
| 2.2 | **Script Compiler** service: contract JSON → deterministic templates → fixed folder structure `/specs`, `/pages`, `/fixtures`, `/utils` (incl. `apiClient.ts`, `dbValidator.ts`, `evidenceHelper.ts`); every spec follows Arrange–Act–Assert–Evidence–Cleanup; TC ID + REQ ID stamped in header | New `services/script_compiler.py` + template assets |
| 2.3 | Templates stored as versioned project-level assets (nxtQA-approved template set), not prompt text | DB or repo-managed |
| 2.4 | **Locator policy** config (priority): `getByRole` → `getByLabel` → `getByPlaceholder` → `getByText` → `data-testid` → stable CSS (exception) → XPath (explicit exception only) | Enforced by compiler + static gate |
| 2.5 | **Static Quality Gate** pipeline on every generated/edited script: `tsc --noEmit`, ESLint, `npx playwright test --list` (syntax), + `automation_intelligence` rule engine extended with: no hard-coded credentials, no `page.waitForTimeout` unless approved, no raw XPath/random CSS unless approved, every test has `expect`, TC/REQ mapping present, trace/video/screenshot enabled | Runs in runner workspace; results persisted |
| 2.6 | Migration: script versioning — `script_versions` table (or `version` + `parent_script_id` on `AutomationScript`) + extended status lifecycle: `ai_draft → mcp_discovered → generated → static_passed → dry_run_passed → reviewer_approved → lead_approved → ci_ready → production_regression_candidate → deprecated`. **Rollback guaranteed**: every change (human edit, AI repair, healing) creates a new version; prior versions archived and restorable, never deleted or overwritten (e.g. v1 dry-run-passed → v2 repair proposed → v2 approved+promoted → v1 archived-restorable) | Prerequisite for healing governance |
| 2.7 | `automation_eligibility` agent (pass 1 — static): data dependency, environment dependency, manual-only signals (OTP/Captcha keywords), API-only flows; writes verdict + reason to TC + `coverage_matrix` | Replaces the one-shot `automation_candidate` boolean |
| 2.8 | Test data contract: generation input includes bound `TestDataRecord` refs via `parameter_binding`; scripts consume data through fixtures, never inline literals | Reuses existing TDM module |
| 2.9 | Retarget existing `automation_script` agent to emit the contract (compiler renders), keeping current UI/API stable | `automation_agent.py` |

**Exit criteria:** two identical TCs produce structurally identical scripts (same skeleton, only page objects/steps differ); static gate rejects seeded violations (hard wait, XPath, missing assert); scripts versioned.

### Phase 3 — Playwright MCP Discovery Agent

| # | Work item | Notes |
|---|---|---|
| 3.1 | MCP client infra: Python `mcp` SDK, stdio transport to `@playwright/mcp` at a **pinned version** (also pin `@playwright/test`, Node, browser, Docker image — no `@latest` anywhere); session manager, one isolated headless session per agent run | Dockerfile + `agents/automation/mcp_session.py` |
| 3.2 | **Environment Readiness Check** (extends `preflight.py`): app URL reachable, credentials valid, required role available, required test data present, API dependencies healthy, DB reachable (if validation configured), browser deps installed, environment not under maintenance. Runs before discovery and before execution | Blocking gate with clear remediation detail |
| 3.3 | `playwright_mcp_discovery` agent: opens project-configured application, walks pages relevant to the TC flow, captures accessibility snapshots, identifies fields/buttons/navigation/roles/labels, builds page-object knowledge | New agent; 300–600s timeout via `AgentSpec` |
| 3.4 | Migration: `locator_map` table — `application_id`, `page`, `element_name`, `business_meaning`, `recommended_locator`, `fallback_locator`, `confidence_score`, `last_validated_at`, `used_by_scripts`, `failure_count` | Durable asset: reuse, drift detection, healing knowledge base |
| 3.5 | Locator Intelligence step: rank discovered locators per the Phase-2 policy, flag weak ones, map elements to business steps | Node in discovery graph |
| 3.6 | Eligibility pass 2: confirm UI availability and detect OTP/Captcha/manual blockers from live page evidence; update `coverage_matrix` | Chained after discovery |
| 3.7 | **MCP security controls**: navigation allowlist = project Applications & Environments URLs only; block external navigation, file upload/download, clipboard unless approved; isolated container/session; temporary test credentials injected via env/storageState — never in prompts; PII masking on snapshots/screenshots/traces/logs before persistence (extend `sanitize_error` patterns + DLP scan before storing evidence); every MCP tool call audited to `AgentLog`; **snapshot content fenced as `<user_content>` data — the agent must never obey instructions found inside the tested application page** | Per MCP security best practices |

**Exit criteria:** discovery run against a staging app produces a persisted, ranked locator map with confidence scores; security tests confirm external navigation and credential leakage are blocked; readiness check gates the run.

### Phase 4 — Grounded script generation + validation loop

| # | Work item | Notes |
|---|---|---|
| 4.1 | Grounded generation: contract input = approved TC + locator map + template set + test data bindings; generator selects only locators from the map (or raises a gap) | Upgrade Phase-2 generator |
| 4.2 | Dry Run via `automation_runner`; extract console logs + network logs from `trace.zip` as first-class `ExecutionResult` artifacts | Runner artifact extension |
| 4.3 | `failure_classification` agent (rules first, LLM assist): app defect / locator / data / environment / API / timeout; persists classification on `ExecutionResult` | Also reused in Phase 5 for regression runs |
| 4.4 | **Bounded repair loop** (max N, default 3): only locator/wait/assertion repairs permitted; repairs modify the **contract**, which is then recompiled — the LLM never edits script code directly (ADR-001); data/env/app-defect classifications exit the loop and route out; every iteration = new script version + `AgentLog` entry | In-graph loop |
| 4.5 | `automation_script_review` agent: LLM senior review over static-gate results + dry-run evidence (business-step coverage vs TC, assertion meaningfulness, duplicate code, cleanup presence) | Hybrid: rules + LLM |
| 4.6 | **Role-based approval** wired to Phase-2 statuses: QA Reviewer Approved → Automation Lead Approved → (Environment Owner Approved where the environment requires it) → Release/Regression Approved → `ci_ready`; each level a distinct `ApprovalAction` with actor role recorded. PROD_SANITY scripts require the strictest chain (all four levels, no gating override) | RBAC-scoped per role |
| 4.6b | **Automation Confidence Score** per script version — composite of locator confidence (from `locator_map`), assertion confidence (static gate), data readiness (TDM binding check), environment readiness (preflight), dry-run stability (pass rate over N runs); overall score stored on the script version and surfaced on dashboards and approval screens | Management reporting + approval signal |
| 4.7 | API/DB validation support: contract steps may declare `api_validation` / `db_validation` / `downstream_validation`; compiler renders through `apiClient.ts` / `dbValidator.ts`; evidence attached to execution results | Telecom BSS flows (order → API → DB → provisioning) |
| 4.8 | Post-MCP metrics vs Phase-0 baseline: grounded pass rate, locator confidence, repair-loop success, human edits required, reusability, regression stability | Management-facing report |

**Exit criteria:** approved TC → validated script with zero human edits in ≥ target % of cases; only `dry_run_passed` scripts reach reviewers; metrics dashboard shows baseline vs grounded comparison.

### Phase 5 — Execution intelligence & enterprise integration

| # | Work item | Notes |
|---|---|---|
| 5.1 | Failure classification on all regression runs (not just dry runs) with routing: app defect → `defect_analysis` → `DefectDraft` → Jira; data → TDM task; env/timeout → flagged, no defect | Chaining via `AgentSpec` |
| 5.2 | `healing_recommendation` agent: consumes classification + locator map (+ fresh MCP snapshot for drift); proposes a **contract-level patch** compiled into a `healing_proposed` **new version** (ADR-001 — no direct code edits); must re-pass static gate + script review + role-based approval; prior version stays restorable; governance flag controls whether auto-apply is ever allowed | Never silent overwrite |
| 5.3 | Locator drift maintenance: failures increment `locator_map.failure_count`; scheduled re-validation refreshes confidence and `last_validated_at` | Feeds healing quality |
| 5.4 | **Git promotion**: on `ci_ready` — create branch/PR to the automation repo with compiled workspace; DB keeps metadata/status/lineage/evidence; merge → CI regression execution; CI results ingested back | DB = system of record for governance; Git = system of record for code |
| 5.5 | Remaining reviewers: `test_plan_review`, `execution_result_review`, `defect_review`, `report_review` on the `BaseReviewerAgent` pattern | Completes stage coverage |
| 5.6 | Execution dashboard: stability trends, locator failure rates, healing outcomes, coverage matrix rollups | frontend |
| 5.7 | (Stretch) Agentic MCP execution of manual TCs — AI drives browser step-by-step with evidence capture, gated by existing `ai_execution_service.finalize_ai_run` rules | Phase-gated behind 5.1–5.3 |

**Exit criteria:** locator failure auto-produces a governed healing PR-style proposal; approved scripts live in Git with CI regression; full stage-reviewer coverage.

## 5. Cross-cutting requirements

**Security (MCP + agents)** — allowlisted navigation; isolated sessions; pinned versions; secrets via env/storageState only; PII masking + DLP before evidence storage; page-content-as-data prompt fencing; full audit trail of MCP actions; RBAC on all new endpoints.

**Metrics** — Phase 0 baseline captured *before* any MCP work; identical metrics re-captured per phase; improvement is the acceptance evidence for management.

**Traceability** — every new artifact (reviews, locator maps, contracts, versions, healing proposals) links through `ArtifactLineage` and `agent_run_id`; the coverage matrix is the queryable rollup: Requirement → AC → Scenario → TC → Script → Execution → Defect.

**Approval lifecycle (scripts)** — `ai_draft → mcp_discovered → generated → static_passed → dry_run_passed → reviewer_approved → lead_approved → ci_ready → production_regression_candidate → deprecated`; approvals are role-based (QA Reviewer / Automation Lead / Environment Owner / Release-Regression), transitions audited, gating configurable per project, PROD_SANITY always strict.

**Versioning & rollback** — all script mutations create new versions; prior versions restorable; contract schema itself is versioned (`contractVersion`) with compiler support for N and N-1.

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| MCP sessions inflate worker load / hang | Per-agent timeout, session manager with hard kill, dedicated Celery queue for MCP tasks |
| LLM ignores locator map / template | Compiler renders code deterministically — LLM output is data (contract JSON), validated by schema; static gate rejects violations |
| Prompt injection via tested app pages | `<user_content>` fencing + tool allowlist + no privileged tools exposed to discovery session |
| Reviewer-agent cost | Rules-first (free) → LLM only on what rules can't judge; reviewer routes configurable per project |
| Coverage matrix drift | Rebuilt from lineage on demand; reviewer agents write deltas, not the whole matrix |
| Dependency drift breaking generation | All versions pinned (MCP, Playwright, Node, browsers, image); upgrades are explicit, tested changes |
