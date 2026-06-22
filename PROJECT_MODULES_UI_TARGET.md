# STLC PLATFORM — FULL PROJECT UI TARGET DESIGN

**Telecom QA Command Center | stlc-platform** **Design Spec Version:** 1.0 | **Date:** June 2026 **Companion file:** `PROJECT_MODULES_REVIEW.md`

---

## DESIGN SYSTEM (GLOBAL)

This document defines the target UI design for every module. All modules share one design language. No per-module visual divergence.

### Design Principles

1. Enterprise, not consumer — dense information, not spacious marketing  
2. Status is always visible — every artifact shows its lifecycle state at a glance  
3. Telecom domain is always labelled — Billing, Charging, CRM, OSS/BSS tags visible everywhere  
4. AI output is never final — every AI-generated artifact is clearly labelled DRAFT until human-approved  
5. Simulated data is always labelled — DEMO MODE banner is persistent when active  
6. Actions follow permissions — controls that the user cannot perform are hidden, not disabled with tooltip

### Global Color Tokens

Navy sidebar:     \#0F1B35

Page background:  \#F1F5F9

Card surface:     \#FFFFFF

Border:           \#E2E8F0

Border strong:    \#CBD5E1

Primary blue:     \#2563EB   (primary actions, links, info)

Cyan:             \#06B6D4   (ready states, AI accents)

Violet:           \#7C3AED   (AI-generated label, improvement assistant)

Green:            \#10B981   (approved, passed, synced)

Amber:            \#F59E0B   (pending, warnings, needs clarification)

Red:              \#EF4444   (errors, critical, failed, rejected)

Slate:            \#64748B   (muted text, secondary labels)

### Global Typography

Display numbers:  Inter 22px / 600

Section labels:   Inter 10.5px / 600 / uppercase / 0.06em tracking

Body text:        Inter 13px / 400 / line-height 1.5

Table cells:      Inter 12px / 400 (title 500\)

Monospace IDs:    JetBrains Mono 10.5–11px / 400

Badge text:       Inter 10–10.5px / 500

### Shared Components (to be built once, used everywhere)

| Component | Usage |
| :---- | :---- |
| `<StatusChip>` | Lifecycle state of any artifact (draft/approved/rejected/pending) |
| `<TelecomDomainBadge>` | Billing / Charging / CRM / Mobile / OSS / BSS colored pill |
| `<RiskChip>` | Critical/High/Medium/Low with colored dot |
| `<QualityBar>` | Mini progress bar \+ numeric score |
| `<JiraSyncChip>` | Synced/Conflict/Error/Not-synced |
| `<TraceabilityPills>` | TC count \+ SC count pills, red when zero |
| `<AgentRunStatus>` | queued/running/completed/failed with spinner |
| `<ApprovalChip>` | approved/pending/rejected with icon |
| `<DemoBanner>` | Persistent top bar when DEMO\_MODE=true |
| `<ReadinessBanner>` | Green/Amber/Red readiness gate banner |
| `<EmptyState>` | Icon \+ title \+ subtitle \+ CTA button(s) |
| `<LoadingSkeleton>` | Animated bars matching exact column widths |
| `<PageTitle>` | Module title \+ subtitle \+ breadcrumb |
| `<DataTable>` | Sortable, filterable, paginated — used in all modules |
| `<DetailDrawer>` | Right-side 520px slide-in with tabbed sections |
| `<SummaryCards>` | Responsive grid of stat cards |
| `<FilterRow>` | Search input \+ filter chips \+ right controls |

---

## PAGE 1: DASHBOARD

**Route:** `/dashboard` **Title:** QA Command Center **Subtitle:** Live platform health across all projects and STLC stages

### Layout

\[DEMO BANNER — conditional\]

\[TOP BAR: title | project selector | release selector | last refreshed\]

\[ROW 1: SUMMARY CARDS — 6 cards\]

Requirements  |  Test Cases  |  Automation  |  Executions  |  Open Defects  |  Pending Approvals

\[ROW 2: TWO COLUMNS — 60/40 split\]

LEFT: RELEASE READINESS GAUGE per release         RIGHT: JIRA SYNC HEALTH

  \- Go/No-Go indicator                              \- Last sync time

  \- Blocker count                                   \- Conflict count

  \- Domain coverage bars (Billing, CRM, etc.)       \- Pending webhook events

  \- \[View Release Readiness\]                         \- \[View Jira Sync Monitor\]

\[ROW 3: TWO COLUMNS — 50/50 split\]

LEFT: AI AGENT PIPELINE STATUS                    RIGHT: PENDING APPROVALS QUEUE

  \- 9 pipeline stages with status dots              \- Count by artifact type

  \- Latest run per agent with duration              \- Oldest pending (SLA warning)

  \- \[View Agent Run Monitor\]                         \- \[Go to Approval Center\]

\[ROW 4: TWO COLUMNS — 60/40\]

LEFT: RECENT EXECUTION RUNS                       RIGHT: TOP DEFECTS (Critical/High)

  \- Last 5 runs with pass rate bar                  \- Most recent open Critical defects

  \- Click → execution page                          \- Severity \+ domain badge

  \- \[View All Executions\]                            \- \[View All Defects\]

### Summary Cards (6)

Total Requirements | Total Test Cases | Automation Coverage % | Last Pass Rate % | Open Defects | Pending Approvals

### Key UX Rules

- Dashboard never shows mock data — if an API call fails, the card shows "--" not a fake number  
- Release readiness gauge is color-coded: green (GO) / amber (AT RISK) / red (NO-GO) / grey (not computed)  
- Pending approvals card links directly to Approval Center filtered by project  
- DEMO MODE banner at top: "You are viewing DEMO MODE — simulated execution data. Not for production use."  
- All cards are clickable — drill to the relevant module with pre-applied filter

---

## PAGE 2: REQUIREMENTS COMMAND CENTER

**Route:** `/requirements?project={id}` **Fully specified in:** `REQUIREMENTS_MODULE_UI_TARGET.md` **Summary:** 8 summary cards, 8-stage pipeline tracker, sortable table with 10 columns, domain/risk filters, right-side 11-tab detail drawer, AI quality review panel, requirement improvement assistant

---

## PAGE 3: TEST PLANNING COMMAND CENTER

**Route:** `/test-planning?project={id}` **Title:** Test Planning Command Center **Subtitle:** AI-generated test plans, scenarios, and test cases — from approved requirements

### Layout

\[TOP BAR: project selector | release | test\_phase selector | \[Generate Test Plan\] \[Generate Scenarios\] \[Generate Test Cases\]\]

\[SUMMARY CARDS — 6\]

Approved Requirements  |  Test Plans  |  Scenarios  |  Test Cases  |  Automation Candidates  |  Pending Approvals

\[TAB BAR\]

Test Plans  |  Scenarios  |  Test Cases

\[TAB: TEST PLANS\]

  \[FILTER ROW: search | All / Draft / Pending / Approved | telecom\_domain | test\_phase\]

  \[TABLE\]

    Plan ID  |  Title  |  Source Requirements  |  Test Types  |  Effort  |  Coverage  |  Status  |  Approval  |  Actions

  

  \[DETAIL DRAWER — tabs\]

    Overview  |  Scope  |  Test Types  |  Entry/Exit Criteria  |  Risks  |  Linked Scenarios  |  Approval History

\[TAB: SCENARIOS\]

  \[FILTER ROW: search | All / Draft / Approved | scenario\_type | domain | priority\]

  \[TABLE\]

    Scenario ID  |  Title  |  Type  |  Domain  |  Priority  |  Source Req  |  Linked TCs  |  Status  |  Approval  |  Actions

  

  \[DETAIL DRAWER — tabs\]

    Overview  |  Linked Test Cases  |  Source Requirement  |  Approval History

\[TAB: TEST CASES\]

  \[FILTER ROW: search | All / Draft / Approved / Automated | test\_type | domain | priority | automation\_candidate\]

  \[TABLE\]

    TC ID  |  Title  |  Type  |  Severity  |  Priority  |  BDD  |  Steps  |  Automation  |  Status  |  Approval  |  Actions

  

  \[DETAIL DRAWER — tabs\]

    Overview  |  Steps  |  Test Data  |  BDD Scenario  |  Preconditions  |  Linked Scenarios  |  Execution History  |  Approval History

### Key Design Decisions

**Readiness gate banner (per tab):** If generating test plans when requirements have insufficient readiness:

⚠ 14 requirements are not ready for test planning

   6 missing acceptance criteria | 4 quality score below 3.0 | 4 AI review pending

   \[View Requirements\] \[Generate Anyway — I accept the risk\]

**Telecom domain context injection indicator:** Each generated test plan shows which telecom domains were considered:

Generated for: \[Billing\] \[Charging\] \[CRM\]   Test phase: SIT

**Scenario type chips:**

- Positive (green)  
- Negative (red)  
- Edge (amber)  
- Boundary (amber)  
- Integration (blue)  
- Security (violet)  
- Performance (slate)

**Test case BDD preview:** Each test case row shows a truncated Given/When/Then inline.

**Automation candidate indicator:** `[⚡ Auto]` chip in the Automation column for `automation_candidate=true` test cases.

---

## PAGE 4: AUTOMATION COMMAND CENTER

**Route:** `/automation?project={id}` **Title:** Automation Command Center **Subtitle:** AI-generated Playwright and Pytest scripts — approve before execution

### Layout

\[TOP BAR: project | \[Generate Scripts: Playwright\] \[Generate Scripts: Pytest\]\]

\[SUMMARY CARDS — 4\]

Total Scripts  |  Approved  |  Pending Approval  |  Last Execution Pass Rate

\[FILTER ROW: search | All / Draft / Pending / Approved | framework | test\_type\]

\[TABLE\]

  Script ID  |  Title  |  Framework  |  Source TC  |  Domain  |  Status  |  Last Run  |  Pass Rate  |  Actions

\[DETAIL DRAWER — tabs\]

  Code Viewer  |  Execution History  |  Source Test Case  |  Setup Instructions  |  Approval History

### Code Viewer Tab

\[Framework badge: Playwright / Pytest\]

\[Language badge: TypeScript / Python\]

\[Execution command: npx playwright test tests/billing/tc\_0042.spec.ts\]

\[Setup required: npm install @playwright/test | npx playwright install\]

\[--- CODE BLOCK (syntax highlighted, line numbers, copy button) \---\]

import { test, expect } from '@playwright/test';

...

\[IMPORTANT NOTICE: This script was AI-generated. Validate selectors and 

assertions against the actual application before running in any environment.\]

### AI-Generated Warning Banner

Every script card must show:

⚡ AI-generated script — validate before execution

   Selectors and assertions are inferred from test case description.

   Review against actual application UI/API before approving.

This banner is NOT dismissable. It prevents users from treating generated scripts as production-ready without review.

### Execution History Tab (per script)

Run \#3   20 May 2026 14:32   Passed   2.4s   SIT Environment

Run \#2   18 May 2026 09:11   Failed   8.1s   SIT Environment  \[View Error\]

Run \#1   15 May 2026 16:55   Passed   2.2s   SIT Environment

---

## PAGE 5: EXECUTION COMMAND CENTER

**Route:** `/execution?project={id}` **Title:** Execution Command Center **Subtitle:** Test execution runs, results, evidence, and failure triage

### Layout

\[TOP BAR: project | environment selector | \[Run Tests: Playwright\] \[Run Tests: Pytest\]\]

\[DEMO MODE EXECUTION NOTICE — shown when DEMO\_MODE=true\]

"Results shown are simulated. Real execution requires DEMO\_MODE=false and a configured test environment."

\[SUMMARY CARDS — 6\]

Total Runs  |  Passed  |  Failed  |  Blocked  |  Pass Rate %  |  Undecided Failures

\[LEFT PANEL — run list, 35% width\]

  \[FILTER: status / date range / environment\]

  \[RUN CARDS — each showing:\]

    Execution ID  |  Suite Name  |  Environment  |  Pass Rate Bar

    Passed / Failed / Skipped counts  |  Duration  |  \[SIMULATED\] or \[REAL\] badge

\[RIGHT PANEL — selected run detail, 65% width\]

  \[TABS\]

  Results  |  Failure Decisions  |  Evidence  |  Agent Logs

  \[TAB: RESULTS\]

    \[Per test result row: status icon | test name | duration | error message if failed\]

    Failed results show expandable stack trace \+ logs

  \[TAB: FAILURE DECISIONS\]

    For each failed result — PRINCIPLE-05 compliance tracking:

    

    TC-0042 — OCS Quota Deduction  \[FAILED\]

    Decision: \[ \] Defect Created  \[ \] Linked to Existing  \[ \] Known Issue  \[ \] Waived

    ← This decision is required before release readiness can be approved.

    

    \[Decide →\] opens inline form to record decision type \+ comment

  \[TAB: EVIDENCE\]

    Screenshots, trace files, video recordings per test

    \[Download All Evidence\]

  \[TAB: AGENT LOGS\]

    Step-by-step log from execution agent run

### Failure Decision UX

This is a new UX pattern implementing PRINCIPLE-05. When a test fails, the user must make one of four documented decisions before the run can be closed. The "Failure Decisions" tab shows all undecided failures in red, with a required decision form per failure.

┌─────────────────────────────────────────────────────────────┐

│ ✗ TC-0042 — OCS Quota fails when quota \= 0 bytes           │

│ Error: AssertionError: Expected session terminated, got...   │

│                                                              │

│ Decision required before release readiness:                  │

│ ○ Create defect  ○ Link to existing issue  ○ Known issue     │

│ ○ Waive (requires Release Manager approval)                  │

│                                                              │

│ \[Note / Jira Key\]    \[Save Decision\]                         │

└─────────────────────────────────────────────────────────────┘

---

## PAGE 6: DEFECTS COMMAND CENTER

**Route:** `/defects?project={id}` **Title:** Defects Command Center **Subtitle:** AI-analyzed defects, telecom triage, Jira Bug sync

### Layout

\[TOP BAR: project | release | \[Analyze Failed Tests\] \[Push Selected to Jira\]\]

\[SUMMARY CARDS — 6\]

Total Defects  |  Critical  |  High  |  Open  |  Pushed to Jira  |  Pending Approval

\[FILTER ROW: search | All / Draft / Pending / Approved / Pushed | severity | domain | test\_phase | classification\]

\[TABLE\]

  Defect ID  |  Summary  |  Severity  |  Domain  |  System  |  Test Phase  |  Classification  |

  Source TC  |  Status  |  Jira Key  |  Approval  |  Actions

\[DETAIL DRAWER — tabs\]

  Overview  |  Steps to Reproduce  |  Environment  |  Root Cause  |  Linked Artifacts  |

  Jira Sync  |  Approval History  |  Audit Trail

### Telecom Triage Section (in Overview tab)

Impacted Domain:    \[Charging\]

Impacted System:    OCS — Online Charging System

Impacted Interface: Gy (Ro diameter interface)

Test Phase:         SIT

Release Version:    Release 24.3

Environment:        SIT-2 (5G Core)

Revenue Impact:     ⚠ Yes

Regulatory:         No

### Jira Sync Tab

Jira Status:      Not yet pushed

\[Push to Jira as Bug\]

─── OR ───

Jira Issue:       BSS-1847  \[Open in Jira ↗\]

Jira Status:      In Progress

Priority:         Critical

Last Synced:      2 Jun 2026 14:32

Sync Status:      ✓ Synced

\[Sync Now\]  \[Add Comment to Jira\]

---

## PAGE 7: REPORTS COMMAND CENTER

**Route:** `/reports?project={id}` **Title:** Reports & Release Readiness **Subtitle:** QA status reporting, release readiness, go/no-go decision support

### Layout

\[TOP BAR: project | release | test\_phase | \[Generate Report: Daily/Weekly/Sprint/Release\]\]

\[SUMMARY CARDS — 4\]

Reports Generated  |  Latest Pass Rate  |  Open Critical Defects  |  Go/No-Go Status

\[RELEASE READINESS PANEL — full width, prominent\]

  ┌─────────────────────────────────────────────────────────────────────┐

  │  Release 24.3 — SIT Phase                                           │

  │                                                                     │

  │  Go / No-Go:  ⛔ NO-GO                                              │

  │                                                                     │

  │  Blockers (3):                                                      │

  │  ✗ 2 Critical defects open with no resolution decision             │

  │  ✗ 1 undecided execution failure                                    │

  │  ✗ 4 requirements missing test coverage                             │

  │                                                                     │

  │  ✓ Requirements approved: 68/72 (94%)                              │

  │  ✓ Test cases executed: 241/253 (95%)                              │

  │  ✓ Automation coverage: 47%                                         │

  │                                                                     │

  │  \[Drill into blockers\]  \[Generate Release Report\]                   │

  └─────────────────────────────────────────────────────────────────────┘

\[DOMAIN QUALITY GRID — per telecom domain bar chart\]

Billing | Charging | CRM | OSS | Mobile | Fixed

Each domain shows: pass rate \+ open defects \+ coverage %

\[REPORTS LIST\]

  \[FILTER: type / date range\]

  \[TABLE\]

    Report ID  |  Type  |  Title  |  Pass Rate  |  Defects  |  Status  |  Approval  |  Actions

  

  \[DETAIL DRAWER — tabs\]

    Summary  |  Coverage  |  Execution Metrics  |  Defect Analysis  |  Risks  |  Recommendations  |

    Traceability Gaps  |  Approval History

### Go/No-Go Rule Display

Show the actual rule engine results so users can see WHY the recommendation was made:

Rule                                    Threshold   Actual    Result

─────────────────────────────────────────────────────────────────

Open Critical defects                   0           2         ✗ FAIL

Undecided execution failures            0           1         ✗ FAIL  

Requirements coverage (Critical/High)   100%        94%       ✗ FAIL

Test case execution rate                95%         95%       ✓ PASS

Open High defects (no waiver)           ≤2          1         ✓ PASS

Pending required approvals              0           0         ✓ PASS

### Report Detail Drawer

The Summary tab must show real computed metrics before the AI narrative, with a clear separator:

\[Real Metrics — Computed from Database\]

Requirements total: 147 | Approved: 68 (46%) | Pending: 14

Test cases: 312 | Executed: 294 (94%) | Passed: 241 (82%)

Open defects: Critical 2 | High 6 | Medium 11 | Low 8

─── AI Narrative ───────────────────────────────────────────

AI-generated summary based on the above metrics. This narrative

is for human review only — the numbers above are authoritative.

\[AI text here...\]

---

## PAGE 8: TRACEABILITY MATRIX

**Route:** `/traceability?project={id}` **Title:** Traceability Matrix **Subtitle:** End-to-end artifact coverage from requirement to execution evidence

### Layout

\[TOP BAR: project | release | domain filter | test\_phase filter | \[Export Matrix\]\]

\[SUMMARY CARDS — 4\]

Total Requirements  |  Fully Traced  |  Coverage Gaps  |  Undecided Failures

\[GAP SUMMARY ROW\]

\[4 gap type counts as pills — click to filter\]

No Test Cases (12)  |  No Execution (8)  |  Undecided Failures (3)  |  No Approval (5)

\[MATRIX TABLE — wide, horizontal scroll\]

Jira Key  |  REQ ID  |  Title  |  Domain  |  Risk  |  Test Plan  |  Scenarios  |

Test Cases  |  Executions (Pass/Fail)  |  Defects  |  Jira Bugs  |  Approval  |  Readiness

\[DETAIL SIDE PANEL — opens when clicking a row\]

Shows full artifact chain for selected requirement:

  \[Req\] → \[Scenario x3\] → \[TC x8\] → \[Run x3: 6 passed, 2 failed\] → \[Defects x2\]

### Matrix Row Color Coding

- **Green row:** fully traced, all passed, approved  
- **Amber row:** partially traced or pending decisions  
- **Red row:** coverage gaps or undecided failures  
- **Grey row:** draft/unapproved requirement (excluded from metrics unless include\_drafts=true)

### Gap Indicators (per cell)

- Empty cell with red X: artifact missing (e.g., no test cases)  
- Amber clock: artifact exists but not approved  
- Green check: artifact approved and executed  
- Red exclamation: execution failure with no decision

---

## PAGE 9: APPROVAL CENTER

**Route:** `/approvals?project={id}` **Title:** Approval Center **Subtitle:** Pending approvals across all STLC artifact types

### Layout

\[TOP BAR: project | \[Bulk Approve Selected\]\]

\[SUMMARY CARDS — 5\]

Pending Requirements  |  Pending Test Plans  |  Pending Test Cases  |  Pending Defects  |  Pending Reports

\[TAB BAR\]

All Pending  |  Requirements  |  Test Plans  |  Test Cases  |  Automation Scripts  |  Defects  |  Reports

\[TABLE — shared across tabs\]

Artifact ID  |  Type  |  Title  |  Domain  |  Risk  |  Quality  |  Submitted By  |  Submitted At  |  SLA  |  Actions

\[ACTIONS PER ROW\]

\[View\]  \[Approve\]  \[Reject\]  \[Request Clarification\]

\[APPROVAL HISTORY PANEL — full width\]

Shows recent approvals across all types in reverse chronological order

### SLA Column

For enterprise telecom governance, approvals may have SLAs. The SLA column shows:

- Green: within SLA  
- Amber: approaching SLA breach (\< 2 hours)  
- Red: SLA breached

This is configurable per artifact type in project settings.

---

## PAGE 10: AGENT RUN MONITOR

**Route:** `/agents?project={id}` **Title:** Agent Run Monitor **Subtitle:** AI agent execution status, progress, logs, and history

### Layout

\[TOP BAR: project | \[Refresh\] \[Clear Completed\]\]

\[SUMMARY CARDS — 4\]

Running  |  Queued  |  Completed Today  |  Failed Today

\[FILTER ROW: agent\_name | status | date range\]

\[TABLE\]

Run ID  |  Agent  |  Status  |  Progress  |  Input  |  Duration  |  LLM  |  Tokens  |  Started  |  Actions

\[PROGRESS COLUMN\]

For running agents: animated progress bar \+ percent \+ current step message

For completed: "100% — Completed in 42s"

For failed: "Failed at step: LLM validation error"

\[DETAIL DRAWER — tabs\]

Overview  |  Step Logs  |  Input Data  |  Output Data  |  LLM Calls  |  Errors

\[STEP LOGS TAB\]

14:32:01  INFO   Starting requirement quality review for 23 requirements

14:32:01  INFO   Batch 1/5: requirements REQ-0001 to REQ-0005

14:32:03  INFO   Batch 1: quality scores computed — 3 pass, 1 needs\_revision, 1 fail

14:32:04  INFO   Batch 2/5: requirements REQ-0006 to REQ-0010

...

14:32:41  INFO   Completed — 23 requirements reviewed

---

## PAGE 11: JIRA SYNC MONITOR

**Route:** `/jira?project={id}`  (or new route `/jira-monitor`) **Title:** Jira Sync Monitor **Subtitle:** Jira connection health, sync history, conflict resolution, webhook events

### Layout

\[TOP BAR: project | Jira connection selector | status badge | \[Test Connection\] \[Sync Now\]\]

\[CONNECTION HEALTH BAR\]

Connected as: Mohammed Al-Rashidi  |  Project: BSS-JIRA  |  Last sync: 4 min ago  |  ✓ Synced  |  2 conflicts

\[TABS\]

Sync History  |  Conflicts  |  Webhook Events  |  Connection Settings

\[TAB: SYNC HISTORY\]

\[TABLE\]

Sync ID  |  Direction  |  Trigger  |  Started  |  Duration  |  Created  |  Updated  |  Conflicts  |  Status

\[TAB: CONFLICTS\]

\[Each conflict shows:\]

Jira Key  |  Field  |  Jira Value  |  Platform Value  |  Last Synced  |  Status

\[Actions: Use Jira Value\] \[Use Platform Value\] \[Manual Review\]

\[TAB: WEBHOOK EVENTS\]

Event ID  |  Type  |  Jira Key  |  Received  |  Processing Status  |  Retry Count  |  Actions

\[TAB: CONNECTION SETTINGS\]

\[Form: Jira base URL | Email | API Token (masked) | Project Key\]

\[Field Mappings: map Jira fields to platform telecom fields\]

\[Sync Direction: Jira to Platform | Platform to Jira | Bidirectional\]

\[Conflict Strategy: Jira Wins | Platform Wins | Manual Review\]

### Field Mapping UI (Connection Settings tab)

Telecom Field          ←→    Jira Field

────────────────────────────────────────

telecom\_domain                Components (mapped via rules)

risk\_level                    Priority

test\_phase                    Fix Version prefix

release\_version               Fix Version

impacted\_systems              Labels (prefix: system:)

\[+ Add Mapping\]

---

## PAGE 12: SETTINGS

**Route:** `/settings?project={id}` **Title:** Project Settings **Subtitle:** Configuration, RBAC, thresholds, and deployment settings

### Tabs

- General (project name, description, telecom domains)  
- Team & Roles (member list, role assignments)  
- Jira Connections (link to Jira Monitor or inline manage)  
- Go/No-Go Thresholds (per domain thresholds for release readiness)  
- Agent Configuration (default LLM, batch sizes, timeouts)  
- Environment Configuration (SIT/UAT/Regression environments)  
- DEMO MODE warning (if active, prominent warning with disable instruction)

### Go/No-Go Threshold Configuration

Default thresholds:

  Max open Critical defects:           0

  Max open High defects (no waiver):   2

  Min requirements coverage:           95%

  Min execution rate:                  95%

Per-domain overrides:

  Billing domain — Max open Critical:  0   (revenue impact — zero tolerance)

  Digital domain — Max open High:      1   (with Release Manager waiver)

\[+ Add domain override\]

---

## SHARED PAGE PATTERNS

### Empty States (consistent across all modules)

\[Icon — relevant to module\]

No \[artifact type\] yet for this project

\[Context-appropriate description\]

\[Primary CTA button\]   \[Secondary CTA button\]

### Loading Skeletons

All tables show 5 rows of animated gray bars at the correct column widths while loading. Summary cards show animated gray boxes. Never show "0" before data loads.

### Error States

All API errors show a consistent inline alert:

\[⚠ icon\]  Failed to load \[module name\]. Check that the backend is running.

\[Retry button\]   \[×\]

### DEMO MODE Banner (every page)

When DEMO\_MODE=true, the following banner appears at the top of every page, below the sidebar, above the topbar:

\[DEMO MODE\] You are viewing simulated data. Execution results, defects, and 

reports are AI-generated and do not reflect real system behavior.

Background: dark navy gradient. Text: light blue. Non-dismissable. Width: full.

---

## NAVIGATION SIDEBAR TARGET

Current sidebar navigation is functional but lacks governance section. Target structure:

\[Logo: Telecom QA | STLC Command Center\]

OVERVIEW

  ○ Dashboard

STLC PIPELINE

  ○ Requirements        \[14 pending\]

  ○ Test Planning

  ○ Automation

  ○ Execution

  ○ Defects             \[3 critical\]

  ○ Reports

GOVERNANCE

  ○ Approval Center     \[5 pending\]

  ○ Traceability Matrix

  ○ Release Readiness

PLATFORM

  ○ Jira Sync Monitor   \[2 conflicts\]

  ○ Agent Run Monitor

  ○ Settings

\[User avatar \+ name \+ role\]

\[Settings icon\]

Badges on navigation items are live counts from the API. They update on each page load and can be polled every 60 seconds for real-time awareness.

---

## IMPLEMENTATION NOTES FOR DEVELOPERS

### Component Priority Order

Build shared components first, then modules in this order:

1. StatusChip, TelecomDomainBadge, RiskChip — used everywhere  
2. DataTable with sorting and pagination  
3. DetailDrawer with tab system  
4. DemoBanner (CRITICAL — must ship before any demo)  
5. SummaryCards, FilterRow

### Module Build Order (frontend)

Corresponds to backend P0/P1 priorities:

1. Requirements (already in progress, spec in separate document)  
2. Dashboard (add governance sections to existing)  
3. Traceability Matrix (new page — backend API exists)  
4. Approval Center (new page — backend API exists)  
5. Execution (add Failure Decision UX — new critical pattern)  
6. Test Planning (add telecom domain display, readiness gate)  
7. Defects (add telecom triage fields)  
8. Reports (add go/no-go panel, domain breakdown)  
9. Jira Sync Monitor (extend existing Jira tab)  
10. Agent Run Monitor (extend existing agents page)

### What NOT to Do

- Do not create per-module StatusBadge components — use the shared one  
- Do not show approval buttons to users who lack the required permission — hide, never disable  
- Do not render unbounded lists — always paginate  
- Do not load all module data on dashboard — use summary endpoints  
- Do not show numerical zeros before data loads — use skeleton loaders  
- Do not build new pages without first auditing whether the backend API covers the required data  
- Do not redesign the sidebar or global layout — only page content areas

---

*End of PROJECT\_MODULES\_UI\_TARGET.md*  
