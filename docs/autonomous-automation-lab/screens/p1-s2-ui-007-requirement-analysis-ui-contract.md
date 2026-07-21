# P1-S2 UI-007 Requirement Analysis UI Contract

## Document control

| Field | Value |
|---|---|
| Screen ID | UI-007 |
| Section | P1-S2 Requirement Intelligence Core |
| Screen name | Requirement Analysis |
| Gate status | IMPLEMENTED_FROM_EXISTING_REQUIREMENTS_BASELINE - VISUAL_APPROVAL_PENDING |
| Parent workspace | `/requirements?project={projectId}` |
| Baseline | Existing Requirements Workspace and STLC Command Center UI system |
| Approval rule | Reference image supplied on 2026-07-21; implementation completed for visual review |

## Purpose

Requirement Analysis turns validated intake records into grounded, structured and reviewable requirements. It must identify ambiguity, missing information, duplicates, conflicts, impacted systems, taxonomy classifications, risks and testability gaps while preserving source-level provenance.

## Reuse rule

- Implement as the **Requirement Analysis** sub-view of the existing Requirements Workspace.
- Preserve the existing shell, project context, compact cards, filters, requirement records, quality-review functions and right-side drawer pattern.
- Reuse current requirement APIs and AI quality-review behavior where they satisfy the contract.
- Do not create a disconnected dashboard or duplicate the Requirements route.
- UI-006 Intake remains available as the preceding workspace sub-view; UI-008 Traceability and UI-009 Review & Approval remain lifecycle destinations.

## Implemented reference alignment

- Implemented in `/requirements?project={projectId}` as the active **Requirement Analysis** lifecycle sub-view.
- Preserved the existing Requirements Workspace shell, cards, badges, table density, drawer pattern and action styling.
- Added project-level **PPM ID** immediately after **REQ ID** in the analysis work queue, using the existing project `ppm_id` field.
- Kept UI-008 Traceability and UI-009 Review & Approval visually present but locked pending their own gates.
- Reused existing `requirementsApi.triggerQuality` as the current analysis execution action until a richer requirement-analysis backend contract is introduced.

## Required screen regions

1. Workspace header
   - Requirements Workspace title and breadcrumb.
   - Active project, release/cycle and refresh state.
   - Requirement Intake, Requirement Analysis, Traceability and Review & Approval sub-navigation.

2. Analysis KPI row
   - Total requirements.
   - Analysis ready.
   - Analysis in progress.
   - Ambiguity detected.
   - Missing information.
   - Duplicate/conflict candidates.

3. Analysis work queue
   - Requirement ID and title.
   - Source and owner.
   - Analysis status and progress.
   - Quality/testability score.
   - Ambiguity, missing-information and conflict counts.
   - Taxonomy readiness.
   - Risk level.
   - Primary next action.

4. Analysis workspace or contextual drawer
   - Grounded requirement summary.
   - Source excerpts/locations and provenance.
   - Acceptance criteria and business rules.
   - Ambiguities, assumptions and clarification questions.
   - Missing information and contradictions.
   - Duplicate/similar requirement candidates.
   - Impacted applications, systems, interfaces and dependencies.
   - Taxonomy classifications with retrieval sources.
   - Risk, regulatory, revenue and customer-impact indicators.
   - AI model, prompt and tool version plus recent audit activity.

5. Review controls
   - Accept or correct AI suggestions.
   - Request clarification.
   - Re-run analysis after an authorized source/version change.
   - Send a valid analyzed requirement to Traceability.

## Required analysis states

- `NOT_ANALYZED`
- `QUEUED`
- `ANALYZING`
- `NEEDS_CLARIFICATION`
- `BLOCKED`
- `ANALYZED`
- `STALE_SOURCE`
- `FAILED`

Displayed labels may be user-friendly, but status ownership must remain deterministic and auditable.

## Grounding and AI rules

- Every generated statement or suggestion must link to a source section, page, issue, endpoint or repository location where available.
- Confidence is advisory and must not determine approval.
- AI must not silently invent missing business rules, taxonomy or application mappings.
- Assumptions and inferred classifications must be clearly marked.
- Corrections must retain the original AI value, reviewer value, actor, timestamp and reason.
- The same agent must not analyze and approve its own result.
- Re-analysis must not overwrite an approved version without versioning and authorization.

## Classification contract

Display configured values for:

- Business Domain.
- Customer Segment and Customer Type.
- Product Group and Product.
- Request Type and Sub Request Type.
- Business Journey.
- Channel and Application.
- Test Type and Scenario Type.
- Risk Level.

Taxonomy values and application names must come from governed registries, not hard-coded page logic.

## Action gates

- Analysis cannot run for invalid, blocked or unauthorized intake sources.
- Send to Traceability is disabled while mandatory ambiguity, taxonomy, application mapping or missing-information blockers remain.
- Duplicate resolution requires an explicit reviewer decision.
- Source version changes mark previous analysis stale.
- Backend authorization remains authoritative; permission failures must be clearly surfaced in the UI.

## Empty and error states

- No project selected.
- No intake-ready requirements.
- Analysis queued or running.
- Analysis failed with retry guidance.
- Source changed and analysis is stale.
- Permission denied.
- AI service unavailable.
- Taxonomy or application registry unavailable.
- No similar requirements found.

## Acceptance criteria

- Reference image and contract are approved before implementation.
- Visual language matches the current Requirements Workspace.
- Existing Requirements functionality is preserved.
- Analysis output is grounded, versioned, correctable and audit-visible.
- Ambiguity, missing information, duplicates, conflicts and classification gaps are actionable.
- Send to Traceability is deterministically gated.
- No UI-008 or UI-009 functionality is implemented ahead of its own visual gate.
