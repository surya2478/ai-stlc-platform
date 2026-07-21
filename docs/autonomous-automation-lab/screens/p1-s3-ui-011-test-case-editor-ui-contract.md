# P1-S3 UI-011 Test Case Editor UI Contract

## Document control

| Field | Value |
|---|---|
| Screen ID | UI-011 |
| Section | P1-S3 Test Design and Generation |
| Screen name | Test Case Editor |
| Gate status | REFERENCE_IMAGE_APPROVED_IMPLEMENTED |
| Parent workspace | `/test-cases?project={projectId}&view=editor` rendered as Test Planning / Test Case Editor |
| Baseline | Existing STLC Command Center UI system and UI-010 Generated Test Cases implementation |
| Approval rule | Reference image `Test_Case_Editor.png` is the visual implementation target |

## Purpose

Test Case Editor lets QA reviewers refine AI-generated test cases before approval. The screen must support editing test case content, validation, traceability checks, test data readiness, metadata correction, automation readiness and governed handoff to UI-013 Test Case Approval.

## Reuse rule

- Reuse `/test-cases?project={projectId}&view=editor` as the implementation route.
- Preserve the existing command-center shell, sidebar, project selector, compact cards, filters, tables, badges and right-side inspector pattern.
- Use the UI-010 Generated Test Cases screen as the immediate upstream source.
- Do not implement UI-013 Test Case Approval decisions beyond gated navigation or handoff actions.

## Required screen regions

1. Header
   - Breadcrumb: `e& STLC / Test Planning / Test Case Editor`.
   - Title: `Test Case Editor`.
   - Badge: `P1-S3 UI-011`.
   - Subtitle: `Review and refine generated test cases before approval.`
   - Actions: Save Draft, Validate, Export.

2. KPI row
   - Total Editable Cases.
   - Draft Edits.
   - Validation Issues.
   - Ready for Approval.
   - Automation Ready.
   - Blocked.

3. Editing readiness and validation panel
   - Requirement linked.
   - Scenario linked.
   - Test steps complete.
   - Expected results complete.
   - Test data available.
   - Policy and permissions.

4. Editable test case list
   - TC ID.
   - Requirement ID.
   - PPM ID.
   - Title.
   - Test type.
   - Scenario class.
   - Priority.
   - Edit status.
   - Validation status.
   - Updated at.
   - Actions.

5. Test case editor workspace
   - Test case header.
   - Linked requirement summary.
   - Preconditions editor.
   - Step-by-step action editor.
   - Step-level expected result editor.
   - Overall expected result editor.
   - Test data dependency editor.
   - Metadata and classification editor.
   - Automation readiness editor.

6. Right-side context inspector
   - Traceability summary.
   - Validation findings.
   - AI suggested improvements.
   - Requirement and scenario provenance.
   - Change history.
   - Governance and audit information.

7. Actions
   - Edit title.
   - Edit preconditions.
   - Edit test steps.
   - Edit expected result.
   - Edit test data dependency.
   - Edit priority, type and classification.
   - Mark automation candidate.
   - Validate test case.
   - Save draft.
   - Send to Approval.
   - Revert unsaved changes.

## Required states

- `GENERATED`
- `EDITING`
- `DRAFT_SAVED`
- `VALIDATING`
- `VALIDATION_FAILED`
- `READY_FOR_APPROVAL`
- `BLOCKED`
- `STALE_SOURCE`

## Action gates

- Cannot send to approval if title, preconditions, steps or expected result are missing.
- Cannot send to approval if requirement or scenario traceability is broken.
- Cannot send to approval if unresolved validation findings remain.
- Cannot mark automation ready without test data and application context.
- Revert must restore the last saved server state.
- Edits must preserve audit history.
- Backend authorization remains authoritative; permission failures must be surfaced clearly.

## Acceptance criteria

- Visual language matches UI-010 and the current STLC Command Center shell.
- All editable areas from the approved reference image are implemented.
- Existing generated test case data loads from the current test case APIs.
- PPM ID remains visible beside the linked requirement.
- Validation findings are visible and actionable.
- Save, validate, revert and send-to-approval actions are gated and auditable.
