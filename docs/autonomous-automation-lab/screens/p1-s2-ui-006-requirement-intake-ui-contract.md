# P1-S2 UI-006 Requirement Intake UI Contract

## Document control

| Field | Value |
|---|---|
| Screen ID | UI-006 |
| Section | P1-S2 Requirement Intelligence Core |
| Screen name | Requirement Intake |
| Gate status | IMPLEMENTED_FROM_EXISTING_REQUIREMENTS_BASELINE — VISUAL_APPROVAL_PENDING |
| Baseline | nxtQA AAF v1.0 FINAL, 21 July 2026 |
| UI reference style | Existing `/requirements?project=3` page, within the STLC Command Center layout and color system |
| Approval rule | User explicitly approved reuse-first implementation on the existing Requirements route; final visual approval remains required |

## Purpose

Requirement Intake is the governed entry point for bringing business, product, telecom, Jira, document, API, UI screenshot, and repository-derived requirement sources into nxtQA AAF.

The page must let users add sources, validate them, track ingestion status, detect missing metadata or duplicates, and send accepted items into Requirement Analysis without losing source provenance.

## Approved reuse baseline

- Parent route: `/requirements?project={projectId}`.
- Do not introduce a separate UI-006 dashboard or duplicate route.
- Preserve the existing application shell, page header patterns, project context, KPI/card language, source integrations, filters, requirement table, detail drawer, exports and review actions.
- Requirement Intake is the default Requirements Workspace sub-view.
- Requirement Analysis, Traceability, and Review & Approval remain visible lifecycle destinations but are implemented only after their individual visual gates.
- The existing requirement records table is retained as **Extracted Requirements**.

Required source tabs:

- Documents / UI Input.
- URL Input.
- GitHub / Local Repository.
- Jira.
- Add Paste Text.
- Add API Specification.
- Extracted Requirements.

## Primary users

- Business Analyst
- QA Lead
- Test Designer
- Automation Engineer
- Release Manager
- Auditor or Reviewer

## Primary user outcomes

- Add or link a requirement source.
- See all intake sources for the selected project/release.
- Understand which sources are ready, processing, blocked, duplicated, invalid, or already analyzed.
- Validate mandatory metadata before analysis begins.
- Trigger AI-assisted requirement intake only when permitted.
- Open resulting requirements and provenance/audit details.

## Required layout

Use the existing dashboard page style:

- Left application sidebar.
- Top breadcrumb and project selector area.
- White/soft-gray workspace background.
- Compact enterprise cards.
- Blue primary actions.
- Green success, amber warning, red blocker/error, purple AI accents.
- Dense dashboard/table layout, not a marketing-style page.

Required screen regions:

- Header: breadcrumb, page title, short subtitle, project/release/environment selectors, refresh/sync status.
- Intake action bar: upload document, link Jira/source, paste text, import from repository/API/UI screenshot where available.
- Summary KPI row: total sources, ready for analysis, processing, blocked, duplicate candidates, requirements extracted.
- Source queue table/list: source name, type, owner, status, created time, progress, linked requirement count, blocker count, next action.
- Validation and blocker panel: missing metadata, duplicate candidates, unsupported format, permission issue, source extraction failure.
- Provenance panel: source hash/version, uploader, connector, Jira sync state, audit stamp.
- AI intake panel: allowed trigger, status, confidence, handoff state, model/prompt version where available.
- Recent intake activity timeline.

## Required data inputs

| Data area | Required source contract |
|---|---|
| Project context | Current project, selected release/cycle, environment if applicable |
| Source registry | Uploaded files, linked Jira imports, pasted text, URL/UI analysis sources, repo/code analysis sources |
| Source status | `NEW`, `VALIDATING`, `READY`, `INGESTING`, `ANALYZED`, `BLOCKED`, `DUPLICATE`, `FAILED`, `ARCHIVED` |
| Source type | `DOCUMENT`, `JIRA`, `TEXT`, `URL`, `UI_SCREENSHOT`, `API_SPEC`, `REPOSITORY`, `OTHER` |
| Metadata | Domain, product group, product, request type, sub request type, journey, channel, application, owner |
| Validation | Required-field checks, file/type checks, duplicate checks, taxonomy checks, connector checks |
| AI intake | Job state, progress, extracted requirements count, warnings, model/prompt/tool version |
| Provenance | Source ID, source version, content hash, connector ID, imported by, imported at |
| Audit | User actions, agent actions, approval/override actions, failure details |

## KPI contract

Each KPI must include:

- Label.
- Count.
- Status tone.
- Last updated timestamp or source freshness indicator.
- Link/filter target.

Required KPIs:

- Total Sources.
- Ready for Analysis.
- Processing.
- Blocked.
- Duplicate Candidates.
- Requirements Extracted.

## Source queue contract

Each source row/card must show:

- Source title.
- Source type icon.
- Owner/uploader.
- Current status.
- Progress percentage where processing.
- Requirement count extracted or linked.
- Validation issue count.
- Last updated time.
- Primary next action.

Allowed row actions:

- View source.
- Validate metadata.
- Run AI intake.
- Open extracted requirements.
- Resolve duplicate.
- Archive source.
- Retry failed intake.

Actions must be permission and status gated.

## AI intake rules

- AI intake must not run for invalid or blocked sources.
- AI output must remain traceable to source sections/pages/items.
- AI-extracted requirements must not be auto-approved.
- Confidence is advisory only; deterministic validation and human review decide readiness.
- The same agent must not generate and approve requirements.
- Prompt/model/tool version must be audit-visible where available.

## Validation rules

The page must visibly block or warn for:

- Missing mandatory taxonomy metadata.
- Invalid file type or unreadable source.
- Duplicate source or duplicate requirement candidate.
- Jira connector unavailable or stale.
- Unauthorized source access.
- Empty extraction result.
- AI intake failure.
- Requirement count mismatch between source and extracted records.

## Empty and error states

Required states:

- No project selected.
- No sources added.
- Upload/import in progress.
- Source validation failed.
- AI intake queued/running.
- AI intake failed with retry.
- Duplicate candidates detected.
- Permission denied.
- Backend/API unavailable.
- Feature disabled, if AAF or Requirement Intelligence is disabled.

## Navigation targets

Primary outgoing links:

- Requirement Analysis (`UI-007`)
- Requirement Traceability (`UI-008`)
- Requirement Review and Approval (`UI-009`, Phase 2)
- Generated Test Cases (`UI-010`)
- Taxonomy Explorer (`UI-034`, Phase 3)
- Audit/Security/Retention (`UI-058`, Phase 3)

## Suggested API shape

Suggested endpoint:

`GET /api/v1/lab/requirements/intake?project_id={id}&release_id={id}`

Suggested response shape:

```json
{
  "project": {},
  "filters": {},
  "summary": [],
  "sources": [],
  "validation_issues": [],
  "ai_jobs": [],
  "provenance": [],
  "activity": [],
  "actions": []
}
```

The implementation may reuse existing requirement APIs if the same UI contract is satisfied without losing provenance, validation, authorization, or auditability.

## Security and governance guardrails

- Do not expose credentials or connector secrets.
- Do not display raw sensitive content by default.
- Mask PII in source previews where applicable.
- Keep uploaded source provenance immutable after ingestion.
- Require audit records for upload, import, retry, archive, AI intake, duplicate resolution and metadata override.
- Do not hard-code taxonomy or application names into page logic.

## Acceptance criteria

- Reference image/mockup approved by user.
- UI contract approved by user.
- Page follows the existing dashboard layout and color system.
- All source statuses and validation blockers are represented.
- AI intake is clearly gated and audit-aware.
- Duplicate and failed intake states are visible.
- Provenance is visible for every source.
- No implementation begins until this gate is approved.
