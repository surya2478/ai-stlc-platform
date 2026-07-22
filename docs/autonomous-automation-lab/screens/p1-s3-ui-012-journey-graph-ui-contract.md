# P1-S3 UI-012 Journey Graph UI Contract

| Field | Value |
|---|---|
| Screen ID | UI-012 |
| Phase | Phase 1 - Foundation |
| Section | P1-S3 Test Design and Approval |
| Screen name | Journey Graph |
| Parent area | Test Planning |
| Proposed route | `/test-cases?project=3&view=journey-graph` |
| Previous screen | UI-011 Test Case Editor |
| Next screen | UI-013 Test Case Approval |
| Primary baseline | Existing Test Planning / Generated Test Cases / Test Case Editor shell, sidebar, compact white cards, blue primary actions, right-side inspector |
| Implementation status | `REFERENCE_IMAGE_APPROVED_IMPLEMENTED_AND_VALIDATED` |

## 1. Purpose

Journey Graph visualizes the approved requirement-to-scenario-to-test-case journey before final approval.

The screen must help reviewers verify that generated and edited test cases cover the correct business journeys, application touchpoints, taxonomy classifications, evidence requirements, positive/negative/boundary/recovery paths, and discovery eligibility before cases move to independent Test Case Approval.

## 2. Placement and navigation

UI-012 belongs inside **P1-S3 Test Design and Approval**.

Recommended Test Planning navigation order:

- Test Planning Dashboard
- Generated Test Cases
- Test Case Editor
- Journey Graph
- Test Case Approval

The existing separate top-level **Test Cases** entry must not duplicate this P1-S3 flow.

## 3. Header requirements

Header must include:

- Breadcrumb: `e& STLC / Test Planning / Journey Graph`
- Page title: `Journey Graph`
- Screen badge: `P1-S3 UI-012`
- Subtitle: `Visualize scenario coverage, journey paths, application touchpoints and approval readiness.`
- Project selector inherited from shell
- Jira sync badge inherited from shell
- Last refreshed timestamp
- `Refresh` button
- Primary action: `Generate Journey Graph` or `Rebuild Graph`
- Secondary action: `Export Graph`

## 4. Top KPI cards

Top row must use the same compact KPI card style as UI-010 and UI-011.

Required KPI cards:

1. **Requirements Mapped**
   - Example value: `96`
   - Description: approved requirements included in graph

2. **Journeys Identified**
   - Example value: `42`
   - Description: unique business journeys

3. **Scenario Nodes**
   - Example value: `184`
   - Description: positive, negative, boundary and recovery nodes

4. **Application Touchpoints**
   - Example value: `28`
   - Description: mapped screens/APIs/services

5. **Coverage Gaps**
   - Example value: `14`
   - Description: missing or weak journey coverage

6. **Approval Ready**
   - Example value: `82%`
   - Description: graph-ready test design coverage

## 5. Readiness and governance strip

Below KPI cards, show a compact readiness strip.

Required checks:

- Requirements approved
- Test cases generated
- Test cases edited / validated
- Taxonomy mapped
- Application mapping complete
- Evidence requirements attached
- Discovery eligibility checked
- Independent review required

Each check must show pass/warning/fail state and a short value.

## 6. Main graph canvas

The center of the screen must be a visual graph/canvas.

Required graph layers:

- Requirement nodes
- Journey nodes
- Scenario nodes
- Test case nodes
- Application touchpoint nodes
- Evidence nodes
- Gap/blocker nodes

Required edge types:

- Requirement → Journey
- Journey → Scenario
- Scenario → Test Case
- Test Case → Application
- Test Case → Evidence
- Gap → Missing scenario/application/evidence

Node states:

- Covered
- Partial
- Missing
- Blocked
- Needs review
- Ready for approval

Graph must visually distinguish:

- Positive scenarios
- Negative scenarios
- Boundary scenarios
- Recovery scenarios
- Regression candidates
- Automation candidates

Recommended visual behavior:

- Compact graph map fits within the visible screen height.
- Selected node updates right-side inspector.
- Hover or selection highlights connected lineage.
- Mini legend appears inside the graph canvas.
- Zoom/search controls appear in the graph toolbar.

## 7. Left / lower journey list panel

A journey list should be available either as a left panel beside the canvas or a lower table below the graph.

Required columns:

- Journey ID
- Journey name
- Requirement count
- Scenario count
- Test case count
- Application mappings
- Evidence coverage
- Gaps
- Approval readiness
- Owner
- Updated at
- Actions

Required sample journeys:

- Order Cancellation
- Payment Failure Recovery
- Customer Onboarding
- Notification Delivery
- Invoice Download
- Bulk Upload

## 8. Filters and graph controls

Required controls:

- Search by requirement, journey, scenario, test case, PPM ID or application
- Domain filter
- Journey filter
- Scenario type filter
- Application filter
- Coverage status filter
- Approval readiness filter
- More filters

Graph toolbar:

- Fit to screen
- Zoom in
- Zoom out
- Show gaps only
- Show evidence links
- Show application links
- Rebuild graph
- Export graph

## 9. Right-side inspector drawer

The right-side inspector must follow the same pattern as UI-007 to UI-011.

Drawer title changes based on selected object:

- Requirement
- Journey
- Scenario
- Test Case
- Application
- Evidence
- Gap

Drawer tabs:

- Overview
- Coverage
- Applications
- Evidence
- Activity

Required inspector content:

### 9.1 Overview

- Selected node ID/name
- Status badge
- Linked requirement / PPM ID where applicable
- Domain
- Journey
- Scenario class
- Risk/priority
- Owner/reviewer

### 9.2 Coverage

- Positive coverage
- Negative coverage
- Boundary coverage
- Recovery coverage
- Regression coverage
- Missing classes
- Duplicate or overlapping nodes

### 9.3 Applications

- Application registry ID
- Screen/API/service mapping
- Discovery eligibility
- Mapping confidence
- Ambiguous mapping warnings
- Missing application onboarding action

### 9.4 Evidence

- Required evidence types
- Attached evidence requirements
- Missing evidence
- Evidence policy status
- Evidence owner

### 9.5 Activity

- Generated by AI
- Edited by user
- Validation events
- Mapping changes
- Review notes
- Audit trail

## 10. Gap and blocker handling

The screen must explicitly show gaps rather than hiding them.

Gap types:

- Missing positive scenario
- Missing negative scenario
- Missing boundary scenario
- Missing recovery scenario
- Missing application mapping
- Ambiguous application mapping
- Missing evidence requirement
- Duplicate test coverage
- Discovery not eligible
- Approval blocker

Each gap must include:

- Severity
- Impacted requirement/journey
- Required remediation
- Owner
- Suggested action

## 11. Required actions

Actions must be visible but permission-aware.

Required actions:

- Rebuild Journey Graph
- Add Missing Scenario
- Link Existing Test Case
- Add Evidence Requirement
- Resolve Application Mapping
- Send to Discovery Review
- Mark Gap Reviewed
- Export Graph
- Send to Test Case Approval

If blockers remain, `Send to Test Case Approval` must be disabled or show the blocking reason.

## 12. Data contract

The implementation may use deterministic frontend data first, but it must be structured for backend/API integration.

```ts
type JourneyGraphNodeType =
  | "requirement"
  | "journey"
  | "scenario"
  | "test_case"
  | "application"
  | "evidence"
  | "gap";

type JourneyGraphStatus =
  | "covered"
  | "partial"
  | "missing"
  | "blocked"
  | "needs_review"
  | "ready_for_approval";

type JourneyGraphNode = {
  id: string;
  label: string;
  type: JourneyGraphNodeType;
  status: JourneyGraphStatus;
  requirementId?: string;
  ppmId?: string;
  journeyId?: string;
  scenarioClass?: "positive" | "negative" | "boundary" | "recovery" | "regression";
  applicationId?: string;
  evidenceRequired?: boolean;
  confidence?: number;
};

type JourneyGraphEdge = {
  id: string;
  source: string;
  target: string;
  relation:
    | "requires"
    | "contains"
    | "validates"
    | "maps_to"
    | "requires_evidence"
    | "has_gap";
};
```

## 13. Authorization and audit

The UI must respect:

- View journey graph permission
- Rebuild graph permission
- Edit journey/scenario mapping permission
- Resolve gaps permission
- Send to approval permission
- Export permission

Every state-changing action must create audit metadata:

- Actor
- Project
- Node/edge affected
- Previous state
- New state
- Timestamp
- Reason/comment

## 14. Visual and UX requirements

Must match the existing UI style:

- Dark navy sidebar
- White dashboard body
- Rounded cards
- Compact table density
- Blue primary action buttons
- Emerald success states
- Amber warning states
- Red blocker/failure states
- Violet AI/automation accents
- Right drawer consistent with UI-010/UI-011

The graph should fit the screen without forcing excessive vertical scroll.

## 15. Acceptance criteria

- UI-012 is reachable from Test Planning navigation after Test Case Editor.
- Header, KPIs, readiness strip, graph canvas, journey list, filters, and inspector are present.
- Graph represents requirement, journey, scenario, test case, application, evidence and gap nodes.
- Positive, negative, boundary and recovery scenarios are visually distinguishable.
- Coverage gaps and discovery eligibility blockers are clearly visible.
- Selecting graph/list items updates the right-side inspector.
- `Send to Test Case Approval` is gated by unresolved blockers.
- TypeScript passes.
- UI contract and approved reference image are stored in `docs/autonomous-automation-lab/screens`.

## 16. Reference image requirement

Implementation must not begin until the reference image for UI-012 Journey Graph is provided and approved.

Expected image file:

`docs/autonomous-automation-lab/screens/Journey Graph.png`

After reference image approval, this contract status should move from:

`CONTRACT_DRAFT_PENDING_REFERENCE_IMAGE`

to:

`REFERENCE_IMAGE_APPROVED_READY_FOR_IMPLEMENTATION`

## 17. Implementation and validation record

- Implemented route: `/test-cases?project={projectId}&view=journey-graph`
- Implementation component: `frontend/src/app/test-cases/JourneyGraphView.tsx`
- Navigation: Journey Graph is placed between Test Case Editor and Test Case Approval.
- Data source: approved requirements, test scenarios, test cases, project applications, artifact reviews and approval history from authenticated project APIs.
- No display counts, graph nodes, readiness results, owners, timestamps or blockers are supplied by demo fallback data.
- Journey grouping uses persisted journey metadata when present, then persisted business process, then the approved requirement title as the deterministic traceability boundary.
- State-changing actions use existing authenticated APIs for scenario generation, application discovery and test-case approval, plus audited test-case updates for evidence requirements, application mappings, gap reviews and existing-case links.
- Test Case Approval remains disabled while the selected journey has unresolved source-data blockers.
- Browser validation was completed against project `3` using the portal session and approved 1680 x 944 reference dimensions.
- Verified browser controls: Refresh, Rebuild Graph, Export Graph, search, all filter controls, More Filters, graph search, fit/zoom, graph toggles, graph menu, node selection, inspector tabs, inspector close/reopen, action forms and Test Planning navigation.
- State-changing submit paths are covered by focused backend tests without altering the user's live project data during validation.
- Validation completed on 2026-07-22:
  - `npx.cmd tsc --noEmit`
  - focused backend approval, authorization and test-case governance tests
  - authenticated browser validation with no console errors
