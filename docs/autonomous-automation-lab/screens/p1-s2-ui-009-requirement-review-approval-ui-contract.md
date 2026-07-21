# P1-S2 UI-009 Requirement Review and Approval UI Contract

## Document control

| Field | Value |
|---|---|
| Screen ID | UI-009 |
| Section | P1-S2 Requirement Intelligence Core |
| Screen name | Requirement Review and Approval |
| Gate status | IMPLEMENTED_FROM_EXISTING_REQUIREMENTS_BASELINE - VISUAL_APPROVAL_PENDING |
| Parent workspace | `/requirements?project={projectId}` |
| Baseline | Existing Requirements Workspace and STLC Command Center UI system |
| Approval rule | Reference image supplied on 2026-07-21; implementation completed for visual review |

## Purpose

Requirement Review and Approval is the governed decision point after intake, analysis and traceability. It must let authorized reviewers approve, reject, request changes, compare AI analysis with reviewer decisions, verify traceability readiness and preserve a full immutable audit trail.

## Reuse rule

- Implement as the **Review & Approval** sub-view of the existing Requirements Workspace.
- Preserve the existing shell, lifecycle navigation, compact KPI cards, filters, table density and right-side drawer pattern.
- Reuse existing requirement approval APIs, approval history and traceability readiness signals where available.
- Do not create a disconnected route or duplicate the Requirements page.
- UI-006 Intake, UI-007 Analysis and UI-008 Traceability remain accessible as preceding lifecycle sub-views.

## Implemented reference alignment

- Implemented in `/requirements?project={projectId}&view=review` as the active **Review & Approval** lifecycle sub-view.
- Preserved the existing Requirements Workspace shell, lifecycle navigation, compact KPI cards, filters, work queue table and right-side drawer pattern.
- Added the supplied screen regions: review KPI row, approval readiness overview, review status tabs, filter bar, approval work queue, workload/SLA/activity cards and approval drawer.
- Kept **PPM ID** immediately after **REQ ID** for consistency with UI-007 and UI-008.
- Reused existing requirement approval APIs for approve/reject actions.

## Required screen regions

1. Review KPI row
   - Total requirements for review.
   - Ready for approval.
   - Pending reviewer action.
   - Changes requested.
   - Approved.
   - Rejected or blocked.

2. Review readiness panel
   - Analysis completion.
   - Traceability health.
   - Missing information status.
   - Duplicate/conflict resolution.
   - Mandatory evidence presence.
   - Policy and permission readiness.

3. Approval work queue
   - Requirement ID.
   - PPM ID.
   - Title.
   - Owner.
   - Analysis status.
   - Traceability health.
   - Review status.
   - Assigned reviewer.
   - SLA or age.
   - Last updated.
   - Next action.

4. Review drawer
   - Requirement summary.
   - Source provenance.
   - AI analysis summary and confidence.
   - Traceability readiness.
   - Acceptance criteria.
   - Open blockers.
   - Reviewer comments.
   - Approval decision history.
   - Audit trail with actor, timestamp, action and reason.

5. Decision controls
   - Approve requirement.
   - Reject requirement.
   - Request changes.
   - Reassign reviewer.
   - Send back to Analysis.
   - Send back to Traceability.
   - Bulk approve only when all selected records pass deterministic gates.

## Required states

- `READY_FOR_REVIEW`
- `PENDING_REVIEW`
- `CHANGES_REQUESTED`
- `APPROVED`
- `REJECTED`
- `BLOCKED`
- `RETURNED_TO_ANALYSIS`
- `RETURNED_TO_TRACEABILITY`

## Action gates

- Approval is disabled if mandatory analysis, traceability, evidence or duplicate-resolution gates fail.
- A reviewer cannot approve an analysis result produced by the same autonomous agent identity.
- Rejection and change requests require reviewer notes.
- Bulk approval must fail closed if any selected requirement is not eligible.
- Backend authorization remains authoritative; permission failures must be surfaced clearly.
- Every decision must create an auditable approval action.

## Acceptance criteria

- Visual language matches `/requirements?project={projectId}`.
- `PPM ID` remains visible after `REQ ID`.
- UI shows why each requirement can or cannot be approved.
- Review drawer exposes decision history and audit activity.
- Approve, reject and request-change flows are gated and auditable.
- Existing UI-006, UI-007 and UI-008 functionality remains intact.
