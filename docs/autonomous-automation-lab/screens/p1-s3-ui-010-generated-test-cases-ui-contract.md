# P1-S3 UI-010 Generated Test Cases UI Contract

## Document control

| Field | Value |
|---|---|
| Screen ID | UI-010 |
| Section | P1-S3 Test Design and Generation |
| Screen name | Generated Test Cases |
| Gate status | REFERENCE_IMAGE_APPROVED_IMPLEMENTED |
| Parent workspace | `/test-cases?project={projectId}` rendered as Test Planning / Generated Test Cases |
| Baseline | Existing STLC Command Center UI system, Test Planning lifecycle and Test Cases generation APIs |
| Approval rule | Reference image `Test-cases.png` is the visual implementation target |

## Purpose

Generated Test Cases presents AI-generated test cases derived from approved requirements, approved scenarios, analysis output, traceability context, taxonomy, risk, application model and evidence. The screen lets reviewers inspect generated coverage, identify gaps, and move generated cases toward UI-011 Test Case Editor and UI-013 Test Case Approval.

## Reuse rule

- Reuse `/test-cases?project={projectId}` as the implementation route.
- Use Test Planning in the breadcrumb and sidebar grouping because the lifecycle entry point is approved planning/scenarios.
- Preserve the existing command-center shell, project selector, compact KPI cards, filters, tables, badges and right-side drawer pattern.
- UI-010 must not implement UI-011 Test Case Editor or UI-013 Test Case Approval beyond navigational/gated actions.

## Required screen regions

1. Test generation KPI row
   - Requirements selected.
   - Test cases generated.
   - Positive cases.
   - Negative cases.
   - Edge/boundary cases.
   - Gaps or blocked generation.

2. Generation readiness panel
   - Approved requirements count.
   - Analysis completeness.
   - Traceability readiness.
   - Test data readiness.
   - Application/model availability.
   - Generation policy and permissions.

3. Generated-case category tabs and actions
   - All Generated.
   - Positive.
   - Negative.
   - Edge / Boundary.
   - Regression.
   - Integration.
   - Gaps / Blocked.
   - Generate Test Cases.
   - Re-generate.
   - More actions.

4. Generated test case table
   - Test case ID.
   - Linked requirement ID.
   - PPM ID.
   - Title.
   - Test type.
   - Scenario class.
   - Priority.
   - Automation candidate.
   - Data dependency.
   - Review status.
   - Traceability health.
   - Actions.

5. Right-side drawer
   - Header with TC ID, Generated status, title, linked requirement and PPM ID.
   - Tabs: Overview, Test Cases, Coverage & Gaps, AI Info, Activity.
   - Requirement Summary.
   - AI Generation Summary.
   - Coverage & Gaps.
   - Test Data Dependency.
   - Actions: Send to Test Case Editor, Send to Approval, Add Missing Scenario, Export Test Cases.

6. Actions
   - Generate test cases.
   - Re-generate selected requirement.
   - Add missing scenario class.
   - Send to Test Case Editor.
   - Send to Test Case Approval.
   - Export generated test cases.

## Required states

- `NOT_GENERATED`
- `QUEUED`
- `GENERATING`
- `GENERATED`
- `PARTIAL`
- `NEEDS_REVIEW`
- `BLOCKED`
- `FAILED`
- `STALE_SOURCE`

## Action gates

- Generation is disabled until requirements are approved or explicitly authorized for draft generation.
- Generated cases must link back to requirement ID and PPM ID.
- Cases with missing expected result, unclear data, unsupported application context or unresolved requirement blockers cannot move to approval.
- Re-generation must preserve previous versions and audit history.
- Backend authorization remains authoritative; permission failures must be surfaced clearly.
- Scenario-approved gating remains authoritative for generation.
- PPM ID is resolved from linked approved requirement context until a dedicated test case PPM field is added.

## Acceptance criteria

- Visual language matches the current STLC Command Center pages.
- Existing Test Planning and Test Cases functionality remains intact.
- Generated cases are traceable to requirements, PPM ID, source evidence and generation run.
- Coverage gaps and missing test classes are visible and actionable.
- UI-011 Test Case Editor and UI-013 Test Case Approval are not implemented ahead of their own visual gates.
