# P1-S2 UI-008 Requirement Traceability UI Contract

## Document control

| Field | Value |
|---|---|
| Screen ID | UI-008 |
| Section | P1-S2 Requirement Intelligence Core |
| Screen name | Requirement Traceability |
| Gate status | IMPLEMENTED_FROM_EXISTING_REQUIREMENTS_BASELINE - VISUAL_APPROVAL_PENDING |
| Parent workspace | `/requirements?project={projectId}` |
| Baseline | Existing Requirements Workspace and STLC Command Center UI system |
| Approval rule | Reference image supplied on 2026-07-21; implementation completed for visual review |

## Purpose

Requirement Traceability shows how analyzed requirements connect to source evidence, test scenarios, test cases, automation candidates, execution results, defects, approvals and evidence. It must make coverage gaps and broken links visible before downstream work proceeds.

## Reuse rule

- Implement as the **Traceability** sub-view of the existing Requirements Workspace.
- Preserve the current shell, lifecycle navigation, compact KPI cards, table density, filters and drawer pattern.
- Reuse existing traceability APIs and the requirement chain drawer behavior where they satisfy the contract.
- Do not create a disconnected route or duplicate the Requirements page.
- UI-006 Intake and UI-007 Analysis remain accessible as preceding lifecycle sub-views; UI-009 Review & Approval remains locked until its own gate.

## Implemented reference alignment

- Implemented in `/requirements?project={projectId}&view=traceability` as the active **Traceability** lifecycle sub-view.
- Preserved the existing Requirements Workspace shell, project context, compact KPI card language, filters, matrix table density and right-side drawer pattern.
- Added the supplied screen regions: KPI row, traceability health distribution, coverage progress, traceability filters/actions, matrix table and vertical trace-chain drawer.
- Kept **PPM ID** immediately after **REQ ID** for consistency with UI-007.
- Reused `traceabilityApi.matrix`, `traceabilityApi.requirementChain` and existing export behavior where available.

## Required screen regions

1. Traceability KPI row
   - Total requirements.
   - Fully traced.
   - Partial trace.
   - Missing test scenarios.
   - Missing test cases.
   - Broken or stale links.

2. Traceability matrix
   - Requirement ID.
   - PPM ID.
   - Requirement title.
   - Source/evidence reference.
   - Analysis status.
   - Scenario coverage.
   - Test case coverage.
   - Automation coverage.
   - Execution/evidence coverage.
   - Defect linkage.
   - Traceability health.
   - Next action.

3. Trace chain drawer
   - Source provenance.
   - Requirement analysis summary.
   - Linked scenarios.
   - Linked test cases.
   - Linked automation scripts or candidates.
   - Execution runs and latest results.
   - Evidence artifacts.
   - Defects and incident links.
   - Gaps, stale links and required next action.

4. Visual trace graph
   - Requirement to scenarios.
   - Scenarios to test cases.
   - Test cases to scripts/executions/evidence.
   - Defects back to requirement or execution failure.
   - Broken, missing and stale links must be visually distinct.

5. Action gates
   - Generate missing scenarios.
   - Link existing scenarios or test cases.
   - Send covered requirements to Review & Approval.
   - Rebuild traceability index.
   - Export traceability matrix.

## Required states

- `NOT_TRACED`
- `PARTIAL`
- `FULLY_TRACED`
- `STALE`
- `BROKEN_LINK`
- `BLOCKED`
- `REBUILDING`

## Acceptance criteria

- Visual language matches `/requirements?project={projectId}`.
- `PPM ID` remains visible after `REQ ID` for consistency with UI-007.
- Requirements with missing scenarios, missing test cases or stale links are clearly gated.
- Trace chain drawer provides evidence-backed links and latest audit activity.
- UI-009 Review & Approval is not implemented ahead of its own visual gate.
