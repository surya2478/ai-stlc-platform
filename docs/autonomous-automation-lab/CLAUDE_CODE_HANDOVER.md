# nxtQA AAF — Claude Code Implementation Handover

**Handover date:** 22 July 2026  
**Repository:** `D:\AI\Projects\stlc-platform`  
**Active branch:** `security/hardening-v1`  
**Product scope:** 58 functional screens across Phases 1–3  
**Next ordered screen:** `UI-014 Application Registry`  
**Primary tracker:** `docs/autonomous-automation-lab/nxtqa-aaf-implementation-tracker.md`

## 1. Purpose

This document is the working handover for Claude Code to continue the Autonomous Automation Framework (AAF) implementation without relying on prior chat history. It records the repository architecture, approved delivery process, implemented screens, incomplete areas, live routes, current uncommitted changes, tests and the remaining 58-screen roadmap.

The original master prompt is outside this repository at:

`D:\AI\Projects\Prompts\nxtQA_AAF_Codex_Master_Prompt_FINAL_v1.0.docx`

Do not modify or redistribute that source document. Use the repository tracker as the implementation-level source of truth and reconcile any conflict with the user before coding.

## 2. User-approved delivery model

The user requires a visual approval gate for every screen:

1. Identify the next screen in the approved phase/section order.
2. Produce or update its Markdown UI contract.
3. Obtain the user's reference image and approval.
4. Inspect existing frontend, backend, database, agents and adjacent workflow routes.
5. Implement every visible section precisely using real persisted data and real APIs.
6. Validate navigation, buttons, permissions, stage gates, error states and live browser behaviour.
7. Record evidence and update the tracker.
8. Commit the accepted screen before moving to the next screen when the user asks for a commit.

Do not start the next screen from assumptions. Do not treat an image-only recreation as implementation.

## 3. Product and UX rules

- Preserve the current STLC shell, sidebar, project selector, compact card/table density and blue/indigo/emerald/amber/red status palette.
- Reuse existing routes and add governed sub-views instead of duplicate menu entries.
- Keep `PPM ID` immediately after `REQ ID` in requirement/test-design tables where applicable.
- Right-side inspectors should follow the compact UI-007–UI-013 drawer pattern.
- Do not hide unavailable functionality behind inert buttons. Wire it, disable it with a reason, or remove it until supported.
- Never use fabricated counts, timestamps, names, audit events or AI confidence as live values.
- Empty data must render an honest empty state, not demo content.
- Do not overwrite the existing `/dashboard`; `UI-001 Executive Overview` belongs to Command Centre at `/autonomous-lab/missions`.

## 4. Agent versus human responsibility

AAF is not intended to be a manual workflow tracker.

Agents must perform:

- requirement extraction, normalization, provenance capture and duplicate detection;
- quality analysis, ambiguity/missing-information detection and classification;
- traceability construction and deterministic readiness validation;
- positive, negative, boundary, recovery and taxonomy-enriched test generation;
- application/journey mapping, discovery, Automation IR and script generation;
- execution planning, evidence collection, result classification and defect correlation.

Human intervention is reserved for:

- business information that trusted sources cannot provide;
- conflicting or ambiguous mappings;
- low-confidence or policy-exception decisions;
- independent requirement/test/automation/release approvals;
- high-risk production, security or compliance actions.

Expected lifecycle behaviour:

`agent work -> deterministic validation -> automatic stage advancement -> human approval only at governed gates`

Keep manual transition buttons as authorized retry/override controls, not the primary happy path.

## 5. Repository architecture

### Frontend

- Next.js `14.2.3`, React 18, TypeScript 5, Tailwind CSS.
- Root: `frontend/`
- Route pages: `frontend/src/app/`
- Shared UI/components: `frontend/src/components/`
- API types and clients: `frontend/src/lib/api.ts`
- Primary navigation: `frontend/src/components/layout/Sidebar.tsx`

Important AAF workspaces:

- Command Centre: `frontend/src/app/autonomous-lab/missions/page.tsx`
- Requirements: `frontend/src/app/requirements/page.tsx`
- Test Planning: `frontend/src/app/test-planning/page.tsx`
- Test Design: `frontend/src/app/test-cases/page.tsx`
- Journey Graph: `frontend/src/app/test-cases/JourneyGraphView.tsx`
- Test Case Approval: `frontend/src/app/test-cases/TestCaseApprovalView.tsx`
- Automation: `frontend/src/app/automation/page.tsx`
- Playwright AI Studio: `frontend/src/app/playwright-studio/page.tsx`
- Execution: `frontend/src/app/execution/`
- Test Data: `frontend/src/app/test-data/page.tsx`

### Backend

- FastAPI, async SQLAlchemy, Alembic.
- Root: `backend/`
- API endpoints: `backend/app/api/v1/endpoints/`
- Models: `backend/app/models/`
- Pydantic schemas: `backend/app/schemas/`
- Domain services: `backend/app/services/`
- Agents: `backend/app/agents/`
- Celery worker/task dispatch: `backend/app/worker/`
- Migrations: `backend/alembic/versions/`
- Tests: `backend/tests/`

Core services:

- PostgreSQL/pgvector
- Redis
- FastAPI backend
- Celery worker
- Next.js frontend
- Nginx proxy

The local stack is defined in `docker-compose.yml`. Never copy its development defaults into production guidance.

## 6. Runtime and authentication

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Local credentials are stored in the ignored root `.env`.
- Read `.env` only when login is required for local testing. Never echo secret values to output and never commit them.
- Project context must remain dynamic through `?project=<id>`; previous testing used projects 3 and 4, but code must not hard-code either.

Useful commands:

```powershell
docker compose ps
docker compose up -d
docker compose logs -f backend
docker compose logs -f worker
docker compose restart backend worker frontend
```

## 7. Current git state

Recent commits:

| Commit | Purpose |
|---|---|
| `60a45a0` | Fix Requirement Analysis interactions |
| `ae06528` | Enforce governed requirement workflow |
| `72aeecf` | Implement UI-013 Test Case Approval |
| `4a4b389` | Add UI-013 contract |
| `d307fe3` | Implement UI-012 Journey Graph |
| `586a609` | Restore the original Dashboard route behaviour |
| `b694e97` | Implement AAF Requirements and Test Case UI screens |
| `e9bf55b` | Add deployment requirements and AAF implementation tracker |

### Uncommitted work that must be preserved

At handover time the following tracked files are modified:

- `backend/app/agents/requirement/quality_agent.py`
- `backend/app/api/v1/endpoints/requirements.py`
- `backend/app/schemas/requirement.py`
- `backend/app/services/requirement_service.py`
- `backend/tests/test_requirement_workflow.py`
- `frontend/src/app/requirements/page.tsx`
- `frontend/src/lib/api.ts`

These changes implement and refine Requirement Analysis interactions, including:

- visible missing-information details;
- working edit/resolution dialogs inside the modal drawer layer;
- lifecycle-stage visibility in Requirement Intake;
- governed `resolve_clarification` transition;
- clarification answers stored in audit/reviewer context;
- re-queued `analysis_pending` state after clarification;
- clarified answers passed back into the quality agent so re-analysis does not ignore them;
- regression coverage for the clarification workflow.

Do not discard, reset or overwrite these edits. Review `git diff` before any new implementation and commit them separately after live end-to-end validation if the user requests it.

Untracked user/local files also exist. Treat them as user-owned and do not delete or stage them indiscriminately:

- `.claude/`
- `docs/New Text Document.txt`
- `docs/autonomous-automation-lab/screens/p2-s1-ui-002-environment-health-ui-contract.md`
- `docs/impl_plan.txt`

## 8. Implemented screen inventory

“Implemented” below means code exists. It does not automatically mean production acceptance; limitations are explicit.

| ID | Screen | Route | State | Notes |
|---|---|---|---|---|
| UI-001 | Executive Overview | `/autonomous-lab/missions?project=<id>` | Partial | Approved visual is present. Dashboard revert is intentional. Several displayed project/environment/timestamp values are static and require real API integration before production acceptance. |
| UI-006 | Requirement Intake | `/requirements?project=<id>&view=intake` | Implemented, verify | Reuses existing Requirements route. Intake Source Queue, source tabs and Extracted Requirements are present. Extracted list must show all project requirements with lifecycle stage, not only intake-stage items. |
| UI-007 | Requirement Analysis | `/requirements?project=<id>&view=analysis` | Implemented, active fixes | Compact KPIs/workflow/table/drawer, PPM ID, editing and clarification flow. Current uncommitted clarification fixes require live retest with worker re-analysis. |
| UI-008 | Requirement Traceability | `/requirements?project=<id>&view=traceability` | Implemented | Traceability metrics, health distribution, table and chain inspector. Validate every real link/action against project data. |
| UI-009 | Requirement Review & Approval | `/requirements?project=<id>&view=review` | Implemented | Final approval gate only. Earlier stages must not expose approval decisions. Eligibility is controlled by analysis and traceability validation. |
| UI-010 | Generated Test Cases | `/test-cases?project=<id>&view=generated` | Partial | Main UI and actions exist, but `DEMO_COUNTS`, calculated fallback percentages and static timestamps remain in `test-cases/page.tsx`. Remove them and use honest API/empty-state values before acceptance. |
| UI-011 | Test Case Editor | `/test-cases?project=<id>&view=editor` | Partial/implemented | Editor actions were wired to existing APIs. Revalidate Save, Validate, Send to Approval, Add Step, View Requirement, View Data, history/audit and discard behaviour with authenticated live data. Static history/timestamps remain and must be replaced. |
| UI-012 | Journey Graph | `/test-cases?project=<id>&view=journey-graph` | Implemented | Dedicated view, backend metadata/governance support and tests were committed in `d307fe3`. |
| UI-013 | Test Case Approval | `/test-cases?project=<id>&view=approval` | Implemented | Dedicated approval queue/inspector, backend approval governance and tests were committed in `72aeecf`. |
| UI-014 | Application Registry | To be finalized from approved contract | Contract only | The contract exists. Do not implement until the user supplies/approves the reference image. |

The tracker still contains stale checkboxes for some UI-006–UI-011 work. Reconcile it only after code and live verification; do not mark all columns complete merely because the page renders.

## 9. Approved UI contracts and reference assets

Directory: `docs/autonomous-automation-lab/screens/`

Contracts currently available:

- `p1-s1-executive-overview-ui-contract.md`
- `p1-s2-ui-006-requirement-intake-ui-contract.md`
- `p1-s2-ui-007-requirement-analysis-ui-contract.md`
- `p1-s2-ui-008-requirement-traceability-ui-contract.md`
- `p1-s2-ui-009-requirement-review-approval-ui-contract.md`
- `p1-s3-ui-010-generated-test-cases-ui-contract.md`
- `p1-s3-ui-011-test-case-editor-ui-contract.md`
- `p1-s3-ui-012-journey-graph-ui-contract.md`
- `p1-s3-ui-013-test-case-approval-ui-contract.md`
- `p1-s4-ui-014-application-registry-ui-contract.md`

Approved/used reference images include:

- `screen-1.png`
- `Requiement analysis.png`
- `Requirement_-Tracebility.png`
- `Req_Rev_Approve.png`
- `Test-cases.png`
- `Test_Case_Editor.png`
- `Journey Graph.png`
- `Test_Case_Approval.png`

The untracked UI-002 Environment Health contract is a draft only and must not be treated as approved.

## 10. Requirement lifecycle currently implemented

Canonical stages:

`Intake -> Analysis -> Traceability -> Review & Approval`

Important backend ownership is in `backend/app/services/requirement_service.py`.

Supported governed transitions include:

- `send_to_analysis`
- `request_clarification`
- `resolve_clarification`
- `send_to_traceability`
- `send_to_review`
- `send_back_to_analysis`
- `send_back_to_traceability`

Rules:

- Intake approval is not valid. Approval belongs only to Review & Approval.
- Rows should appear in the stage owned by their persisted workflow state, while Intake's Extracted Requirements view may show all records with their lifecycle-stage badge.
- Missing information, quality failure and absent classification block Traceability.
- Traceability validation is required before final requirement approval.
- Clarification supplied by a human must be passed back to the quality agent on re-analysis.
- Routine advancement should become automatic after successful deterministic validation; manual transitions are fallback controls.

## 11. Known risks and incomplete work

1. UI-001 contains static project/environment/timestamp presentation values.
2. UI-010/UI-011 contain `DEMO_COUNTS`, inferred percentages and static audit/history values.
3. UI-007 clarification context has focused tests but still needs a complete live run through the Celery quality agent after backend/worker reload.
4. Some large route files are monolithic (`requirements/page.tsx`, `test-cases/page.tsx`). Extract shared components carefully, without visual regression.
5. The implementation tracker is not fully synchronized with the code state.
6. Existing lint warnings remain in unrelated pages; do not claim a warning-free repository unless they are separately resolved.
7. Preserve the original Dashboard route; do not remount UI-001 there.
8. Do not create a duplicate top-level Test Cases entry. Test Design views belong under Test Planning.
9. The Automation Studio total is six pages, not five. Five are Phase 1; Framework Configuration (`UI-022`) completes the module in Phase 2.
10. Existing `/autonomous-lab` pages must remain compatible while the 58-screen IA is implemented incrementally.

## 12. Remaining roadmap — all 58 screens

### Phase 1 — 20 screens

- P1-S1: UI-001 Executive Overview — partial; finish real-data integration.
- P1-S2: UI-006 Requirement Intake, UI-007 Requirement Analysis, UI-008 Requirement Traceability — implemented; finish verification and automation of happy-path transitions.
- P1-S3: UI-010 Generated Test Cases, UI-011 Test Case Editor, UI-012 Journey Graph, UI-013 Test Case Approval — implemented/partial as noted above.
- P1-S4: UI-014 Application Registry, UI-015 Live Discovery Session, UI-016 Application Model, UI-017 API and Network Explorer.
- P1-S5: UI-018 Automation Workspace, UI-019 Live Recorder, UI-020 Automation IR Editor, UI-021 Script Editor, UI-023 Validation and Review.
- P1-S6: UI-030 Data Search and Selection.
- P1-S7: UI-046 Live Execution Monitor, UI-052 Execution Report and Evidence.

### Phase 2 — 18 screens

- P2-S1: UI-002 Environment Health, UI-003 AVD Operations, UI-004 Live Executions.
- P2-S2: UI-009 Requirement Review and Approval — code exists; complete acceptance in its Phase 2 governance scope.
- P2-S3: UI-022 Framework Configuration, UI-024 Reusable Asset Catalogue, UI-025 Asset Versions and Impact.
- P2-S4: UI-026 Script Inventory, UI-027 Static Analysis, UI-028 Dynamic Health, UI-029 Maintenance Campaigns.
- P2-S5: UI-031 Data Creation and Certification, UI-032 Lease Operations, UI-033 Capacity, Cleanup and Quarantine.
- P2-S6: UI-041 Script Dependency Graph.
- P2-S7: UI-044 Execution Planner, UI-045 Intelligent Scheduler and Queue, UI-047 Run Details and Assignments.

### Phase 3 — 20 screens

- P3-S1: UI-034 Taxonomy Explorer, UI-035 Taxonomy Ingestion, UI-036 Retrieval Workbench, UI-037 Taxonomy Governance and Coverage.
- P3-S2: UI-038 Agent and Work Graph, UI-039 Telecom Knowledge Graph, UI-040 Application and Journey Graph, UI-042 Environment and AVD Graph, UI-043 Evidence, Causality and Impact.
- P3-S3: UI-048 Failure Diagnosis, UI-049 Healing Proposals, UI-050 Defect Candidates, UI-051 Replay and Retest.
- P3-S4: UI-053 Reports and Analytics, UI-054 Release Quality Gate.
- P3-S5: UI-055 Policy and Autonomy Control, UI-056 Agent, Model, Prompt and Tool Registry, UI-057 Integration and Adapter Administration, UI-058 Audit, Security and Retention.
- P3-S6: UI-005 Alerts and Incidents.

## 13. Immediate next execution sequence

1. Review and finish the uncommitted UI-007 clarification flow.
2. Restart/reload backend and worker so the agent receives `clarification_context`.
3. Live-test: request clarification -> supply clarification -> re-run analysis -> validate -> automatic readiness/Traceability eligibility.
4. Remove UI-010/UI-011 demo fallbacks and verify all actions with real project data.
5. Update tracker evidence for UI-006 through UI-013 only after verification.
6. Present `UI-014 Application Registry` name and its existing UI contract to the user.
7. Wait for the UI-014 reference image/approval.
8. Inspect existing Project Settings/Application APIs and models before implementing UI-014.
9. Continue in order through UI-015, UI-016 and UI-017, repeating the visual gate for every screen.

## 14. Validation commands

Frontend:

```powershell
cd D:\AI\Projects\stlc-platform\frontend
npx.cmd tsc --noEmit
npm.cmd run lint
npm.cmd run build
```

Backend focused requirement workflow:

```powershell
cd D:\AI\Projects\stlc-platform\backend
& .\.venv\Scripts\python.exe -m pytest tests/test_requirement_workflow.py -q
```

Relevant focused suites for completed P1-S3 work:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests/test_test_case_metadata_governance.py tests/test_test_case_approval_governance.py -q
```

Broader backend verification:

```powershell
& .\.venv\Scripts\python.exe -m compileall -q app tests
& .\.venv\Scripts\python.exe -m pytest -q
```

Live-browser validation must use the authenticated application and verify visible outcomes, API error handling, navigation and persisted reload state. A click handler alone is not evidence.

## 15. Definition of done for every remaining screen

A screen is complete only when all applicable statements are true:

- approved image and Markdown UI contract exist;
- layout fits the target viewport and matches the existing shell;
- every section in the reference image is present;
- data comes from real authorized APIs or an honest empty/error state;
- all actions work, navigate correctly or explain why they are disabled;
- backend state transitions are deterministic, authorized and audited;
- agent actions use persisted inputs/outputs and expose progress/errors;
- stage eligibility prevents invalid forward movement;
- responsive/overflow behaviour is checked;
- frontend typecheck, lint and build pass;
- focused backend tests pass;
- authenticated live-browser flow is verified;
- tracker status/evidence is updated;
- unrelated worktree changes remain untouched;
- accepted work is committed with a focused message when requested.

## 16. First response Claude Code should give the user

After reading this handover and inspecting the worktree, Claude Code should report:

1. that it found and will preserve the current uncommitted clarification fix;
2. the exact implemented/partial range (`UI-001`, `UI-006`–`UI-013`);
3. the known static/demo-data cleanup required in UI-001/UI-010/UI-011;
4. that the next ordered screen is `UI-014 Application Registry`;
5. that the UI-014 contract exists and a reference image/approval is required before implementation.

