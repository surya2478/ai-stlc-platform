# P1-S3 UI-013 Test Case Approval UI Contract

## Document control

| Field | Value |
|---|---|
| Screen ID | UI-013 |
| Phase | Phase 1 - Foundation |
| Section | P1-S3 Test Design and Approval |
| Screen name | Test Case Approval |
| Parent area | Test Planning |
| Proposed route | `/test-cases?project={projectId}&view=approval` |
| Previous screen | UI-012 Journey Graph |
| Next screen | UI-014 Application Registry |
| Primary baseline | Existing Test Planning shell and the compact UI-009/UI-011/UI-012 table plus right-side inspector pattern |
| Implementation status | `CONTRACT_DRAFT_PENDING_REFERENCE_IMAGE` |

## 1. Purpose

Test Case Approval is the independent governance gate between completed test design and downstream application discovery, automation, execution and evidence workflows.

The screen must allow an authorized reviewer to confirm that a test case:

- traces to an approved requirement and PPM ID;
- belongs to an approved scenario and reviewed journey;
- has complete preconditions, steps, test data and expected results;
- preserves positive, negative, boundary, recovery and other required classifications;
- has valid application mappings and discovery eligibility;
- declares required evidence;
- has passed deterministic validation and independent review;
- is safe to approve without unresolved blockers.

## 2. Placement and navigation

Required Test Planning order:

1. Test Planning Dashboard
2. Generated Test Cases — UI-010
3. Test Case Editor — UI-011
4. Journey Graph — UI-012
5. Test Case Approval — UI-013

UI-013 must reuse the existing `/test-cases` workspace with `view=approval`. It must not introduce a duplicate top-level Test Cases page.

## 3. Header

Required content:

- Breadcrumb: `e& STLC / Test Planning / Test Case Approval`
- Title: `Test Case Approval`
- Badge: `P1-S3 UI-013`
- Subtitle: `Independently review and approve validated test cases before discovery and execution.`
- Project selector inherited from the application shell
- Jira sync state inherited from the application shell
- Last refreshed timestamp
- `Refresh`
- `Export Review Queue`
- Optional permission-aware bulk action: `Approve Selected`

## 4. KPI cards

Use six compact cards consistent with UI-012:

1. **Total for Review**
2. **Ready for Approval**
3. **Pending Review**
4. **Changes Requested**
5. **Approved**
6. **Rejected / Blocked**

All counts must come from authenticated project test-case, review and approval APIs. No demo fallback counts are permitted.

## 5. Approval readiness strip

Required checks:

- Requirement approved
- Scenario approved
- Test case validation passed
- Journey coverage reviewed
- Application mapping complete
- Evidence requirements attached
- Discovery eligibility evaluated where required
- Policy and reviewer permissions compliant

Each check must show a deterministic pass, warning or blocker state with a numerator, percentage or short reason.

## 6. Queue tabs

Required tabs:

- All
- Ready
- Pending
- Changes Requested
- Approved
- Rejected
- Blocked

Each tab must show a live count and filter the same review queue without changing routes.

## 7. Search and filters

Required controls:

- Search by TC ID, requirement ID, PPM ID, title, scenario or journey
- Review status
- Domain
- Test type
- Scenario class
- Priority
- Assigned reviewer
- Journey readiness
- Evidence status
- Application mapping status
- More Filters
- Clear filters

## 8. Approval queue table

Required columns:

- Selection checkbox
- TC ID
- Requirement ID / PPM ID
- Title
- Test type
- Scenario class
- Priority
- Journey coverage
- Validation score
- Evidence status
- Review status
- Assigned reviewer
- SLA / age
- Updated at
- Actions

Required behavior:

- Selecting a row updates the right inspector.
- Status colors must match the established emerald, amber, red, blue and slate system.
- Readiness and validation values must be calculated from persisted source fields.
- Missing requirement, scenario, application, evidence or journey data must display as a blocker, not as an inferred pass.
- Pagination and page-size controls must use the existing compact table style.

## 9. Right-side inspector

Required tabs:

- Review
- Traceability
- Test Case
- Evidence
- History
- Activity

### 9.1 Review

- Test case ID and title
- Current review status
- Readiness summary
- Deterministic validation result
- Independent AI/reviewer recommendation when persisted
- Recommendation confidence when persisted
- Assigned reviewer
- Review SLA and due state
- Blocking findings

### 9.2 Traceability

- Requirement ID and PPM ID
- Scenario ID and scenario class
- Journey ID and journey name
- Application mapping
- Discovery eligibility
- Full trace link

### 9.3 Test Case

- Preconditions
- Ordered test steps
- Test data references
- Expected results
- Priority and severity
- Automation candidate state
- Validation findings
- Link back to UI-011 Test Case Editor

### 9.4 Evidence

- Required evidence types
- Evidence policy status
- Missing evidence requirements
- Application or execution evidence dependencies
- Evidence owner

### 9.5 History

- Test case change history
- Review decisions
- Changes requested
- Previous and new values
- Actor, timestamp, source and comment

### 9.6 Activity

- Generation event
- Editor saves and validation events
- Journey mapping changes
- Independent review events
- Approval actions
- Jira synchronization events where available

## 10. Review actions

Required permission-aware actions:

- Approve Test Case
- Request Changes
- Reject Test Case
- Send Back to Test Case Editor
- Send Back to Journey Graph
- Assign / Reassign Reviewer
- View Full Trace
- View Audit Log
- Export Test Case

Action rules:

- Approval must be disabled while mandatory readiness blockers remain.
- Request Changes and Reject require a reviewer comment.
- Approval must use the persisted test-case approval endpoint and create immutable approval history.
- Send Back to Editor must preserve the selected project and test case.
- Send Back to Journey Graph must preserve the selected project and linked journey context.
- Bulk approval must exclude ineligible rows and show exact per-row outcomes.

## 11. Independent review and separation of duties

The UI must surface, not bypass, backend reviewer-governance rules:

- required approval permission;
- project membership and role;
- independent review verdict;
- reviewer identity;
- self-approval restriction when configured;
- override permission and mandatory reason when supported;
- unresolved quality, traceability, application, evidence or discovery blockers.

The frontend must display the backend blocking reason verbatim when an approval attempt is rejected.

## 12. Data and API contract

Use the existing authenticated services where applicable:

- project test-case list and summary;
- test-case update and history;
- test-case approval action;
- artifact review list and history;
- traceability lineage and approval history;
- requirement, scenario and application records;
- test-case export.

The UI must not create approval results, reviewer recommendations, readiness scores or audit entries solely in local component state.

## 13. Empty, loading and error states

- Loading must preserve the screen skeleton without showing sample records.
- Empty queue must explain which upstream gate has no eligible test cases.
- API errors must appear in the established dismissible alert format.
- Partial API failure must identify the unavailable section and must not silently mark it ready.
- Permission failures must leave read-only inspection available when authorized.

## 14. Visual contract

- Dark navy application sidebar and existing header
- White page body
- Six compact KPI cards
- Compact readiness strip
- Single-row queue tabs and filters where the approved reference width permits
- Dense review table
- Fixed-width right-side inspector
- Blue primary actions
- Emerald approval states
- Amber pending/change states
- Red rejection/blocker states
- Violet AI/reviewer recommendation accents
- Major screen regions must fit the approved desktop viewport without excessive vertical gaps

## 15. Acceptance criteria

- UI-013 appears after Journey Graph in Test Planning navigation.
- The route is `/test-cases?project={projectId}&view=approval`.
- Header, KPI cards, readiness strip, queue tabs, filters, table and inspector are present.
- Every displayed value is backed by authenticated project data.
- Selecting a row updates all inspector tabs.
- Approval is gated by deterministic readiness and permission checks.
- Request Changes and Reject require comments.
- Successful review actions persist approval and audit history.
- Editor and Journey Graph return navigation preserves context.
- Export produces real project data.
- TypeScript, focused backend tests, production build and authenticated browser validation pass.
- The reference image and this contract are stored in `docs/autonomous-automation-lab/screens`.

## 16. Reference image gate

Implementation must not begin until the UI-013 Test Case Approval reference image is provided and approved.

Expected image file:

`docs/autonomous-automation-lab/screens/Test_Case_Approval.png`

After approval, update the status to:

`REFERENCE_IMAGE_APPROVED_READY_FOR_IMPLEMENTATION`
