# P1-S5 — Automation Studio Core  
# UI-018 — Automation Workspace  
## Final Consolidated UI/UX and Functional Contract

**Platform:** nxtQA STLC Platform  
**Repository:** `D:\AI\Projects\stlc-platform`  
**Module:** P1-S5 — Automation Studio Core  
**Screen ID:** UI-018  
**Screen Name:** Automation Workspace  
**Related flow:** New Automation Test Suite  
**Version:** Final consolidated update  
**Status:** Implementation-ready  
**Primary design decision:** Automation Test Suites are created from Test Cases, Test Packs, or Regression Packs. Test-case-linked metadata and automation assets are inherited rather than re-entered.

---

# 1. Purpose

UI-018 is the central landing page and control workspace for the Automation Studio.

It must enable users to:

- Create an Automation Test Suite from existing Test Cases, Test Packs, or Regression Packs
- Open and manage existing Automation Test Suites
- Review inherited business, application, framework, script, test data, and environment information
- Identify missing mappings and conflicts before execution
- Configure suite-level orchestration without duplicating test-case metadata
- Resume recording, Automation IR editing, script editing, validation, review, and execution
- Monitor active executions, notifications, approvals, environments, agents, and storage
- Maintain the selected Automation Test Suite context across all P1-S5 screens

---

# 2. P1-S5 Menu Structure

The approved P1-S5 scope remains limited to five implementation screens:

```text
Automation Studio
├── Automation Workspace
├── Live Recorder
├── Automation IR Editor
├── Script Editor
└── Validation and Review
```

## 2.1 Placement of Automation Test Suite Creation

The creation flow must be launched from:

```text
Automation Studio
→ Automation Workspace
→ New Automation Test Suite
```

Do not introduce a separate top-level menu for Automation Test Suites.

Framework Profiles must be managed through the Automation Test Suite detail view or an existing shared Settings capability. Do not add a sixth P1-S5 implementation screen.

---

# 3. Final Domain and Terminology Decisions

## 3.1 Automation Test Suite

An **Automation Test Suite** is an orchestration and grouping container for selected Test Cases and their linked automation assets.

It is not:

- A business project
- A Jira or Azure DevOps project
- A test case owner
- A framework definition
- An application definition
- A duplicate metadata container

## 3.2 Test Case as the Primary Source

The Test Case is the primary scope element for creating an Automation Test Suite.

The suite must inherit related information through the selected Test Cases and their linked entities.

```text
Automation Test Suite
    references Test Cases
        which reference Business Traceability
        which reference Applications
        which reference Framework Profiles
        which reference Scripts and Automation Assets
        which reference Test Data and Environments
```

## 3.3 Required Terminology

| Previous terminology | Final terminology |
|---|---|
| Automation Project | Automation Test Suite |
| New Project | New Automation Test Suite |
| Recent Projects | Recent Automation Test Suites |
| Project Name | Suite Name |
| Project in automation execution tables | Automation Test Suite |
| Scripts, where broader assets are counted | Automation Assets |
| Framework, when referring to reusable configuration | Framework Profile |

Do not globally rename actual business Project entities elsewhere in the STLC platform.

---

# 4. Source-of-Truth and Inheritance Model

## 4.1 Authoritative Entities

| Information | Source of truth |
|---|---|
| Test objective, type, priority, criticality, domain, channel, product | Test Case |
| Project, requirement, change request, defect, release, sprint | Existing linked business entities |
| Application details | Application Model / Application Discovery |
| Framework type and technical configuration | Framework Profile |
| Script, repository path, language, branch, version | Automation Asset |
| Automation flow | Automation IR |
| Test data | Test Data Manager or linked data profile |
| Environment | Test Case, execution profile, or environment service |
| Execution result | Deterministic execution engine |
| Evidence | Execution and evidence services |

## 4.2 Inheritance Rules

The New Automation Test Suite flow must not ask users to re-enter:

- Domain
- Product
- Channel
- Business Project
- Requirement
- Change Request
- Defect
- Release
- Application
- Framework
- Script
- Automation IR
- Test Data
- Environment
- Test Case priority
- Test Case criticality
- Test Case owner

These values must be displayed as inherited, read-only information.

Each inherited value must show its source, for example:

```text
Inherited from TC-2054
Inherited from Regression Pack RP-108
Inherited from CRM Application Model
Inherited from Framework Profile PW-QA-01
Inherited from login.spec.ts
```

## 4.3 No Silent Duplication

The suite must store references to authoritative entities rather than copying editable values into a separate suite record.

Where published auditability requires historical stability:

- Draft suites may resolve current source references dynamically
- Published suite versions must retain an immutable execution snapshot
- Changes to source Test Cases or assets after publication must trigger impact review
- Historical execution results must continue to reference the version used at execution time

## 4.4 Permitted Suite-Owned Information

The Automation Test Suite may own only orchestration-level information such as:

- Suite Name
- Optional Description
- Optional suite tags
- Selected Test Case membership
- Execution grouping
- Planned execution sequence
- Parallelism
- Retry policy
- Schedule
- Evidence policy
- Approval workflow
- Notification rules
- Suite-level access
- Exception decisions
- Default values only for missing test-case-level information

The suite must not overwrite valid Test Case or Automation Asset metadata.

---

# 5. UI-018 — Automation Workspace Layout

## 5.1 Page Header

Display:

- Breadcrumb: `Automation Studio / Automation Workspace`
- Global search
- Primary action: `+ New`
- Notifications
- Help
- User profile
- Optional persistent Automation Test Suite selector

Example:

```text
Selected Suite: Postpaid Order Provisioning E2E ▼
```

The suite selector should show `No suite selected` or remain hidden when the user is viewing the portfolio-level workspace.

---

## 5.2 Left Navigation

Preserve the existing nxtQA dark navigation style and base application layout.

Within Automation Studio, show:

```text
Automation Workspace
Live Recorder
Automation IR Editor
Script Editor
Validation and Review
```

Do not add:

- Automation Project
- Automation Framework as a parent menu
- New Automation Test Suite as a separate menu item

New Automation Test Suite remains a workspace action.

---

# 6. Workspace KPI Cards

The KPI row must contain:

## 6.1 Automation Suites

Show:

- Total suites
- Active suites
- Draft suites
- Validation-pending suites
- Weekly trend

## 6.2 Test Cases

Show:

- Total linked Test Cases
- Automation candidates
- Automated Test Cases
- Automation coverage percentage

## 6.3 Automation Assets

Show combined counts for applicable assets:

- Scripts
- Automation IR definitions
- Recordings
- Page objects
- Reusable components
- API collections

## 6.4 Active Executions

Show:

- Running
- Queued
- Blocked
- Inconclusive

## 6.5 Success Rate

Show:

- Current pass rate
- Weekly change
- Small trend graph

All values must come from real services. Do not hardcode the values shown in reference designs.

---

# 7. Quick Actions

The required Quick Actions are:

| Action | Subtitle | Behaviour |
|---|---|---|
| **New Automation Test Suite** | Create a suite from existing Test Cases and automation assets | Opens the test-case-centric creation flow |
| **Live Recorder** | Start a suite-linked recording session | Opens Live Recorder with selected suite, Test Case, and application context |
| **Import Automation Assets** | Import or connect existing automation assets | Supports scripts, repositories, IR, page objects, Katalon projects, Appium assets, and API collections |
| **Schedule Execution** | Plan suite, execution group, pack, or Test Case execution | Opens scheduling for the selected suite |
| **Test Data Manager** | Manage reusable and execution-specific test data | Opens the existing Test Data capability |

Do not use `New Automation Framework` as the primary action.

Framework Profiles are inherited through linked automation assets or selected where mappings are missing.

---

# 8. Recent Automation Test Suites

Rename the current section to:

```text
Recent Automation Test Suites
```

## 8.1 Recommended Columns

| Column | Description |
|---|---|
| Suite Name | Primary suite identifier |
| Test Scope | Number of Test Cases, packs, or regression packs |
| Business Scope | Inherited project, CR, release, or requirement summary |
| Applications | Inherited application count and primary application |
| Frameworks | Inherited Framework Profile badges |
| Asset Coverage | Automated, missing, and manual Test Case counts |
| Validation | Draft, Pending, Failed, Ready, Approved, Published |
| Updated | Last update timestamp |
| Actions | Open, validate, execute, clone, archive, more |

## 8.2 Suite Statuses

Supported statuses:

- Draft
- Scope Selected
- Inheritance Review Required
- Mapping Incomplete
- Conflict Review Required
- Ready for Validation
- Validation Pending
- Validation Failed
- Ready for Review
- Approved
- Published
- Deprecated
- Archived

## 8.3 Recommended Row Actions

- Open Suite
- Review Inherited Scope
- Resolve Conflicts
- Open Live Recorder
- Open Automation IR
- Open Script Assets
- Validate
- Execute
- Clone
- Archive
- View Audit History

Use a primary row action plus an overflow menu to avoid visual clutter.

---

# 9. Automation Test Suite Detail View

Opening a suite must remain within UI-018 as a detailed workspace state.

Required tabs:

```text
Overview
Test Cases
Inherited Scope
Conflicts and Gaps
Execution Groups
Automation Assets
Test Data
Executions
Evidence
Versions
```

This is not a new implementation screen.

## 9.1 Overview

Show:

- Suite Name and description
- Suite status
- Selected Test Case count
- Automated coverage
- Missing mapping count
- Conflict count
- Inherited application count
- Inherited framework count
- Linked script count
- Execution group count
- Validation summary
- Recent activity

## 9.2 Test Cases

Support:

- View selected Test Cases
- Add or remove Test Cases
- Add Test Packs or Regression Packs
- Link external Test Case references
- Review Test Case source system
- Review automation candidacy
- Review mapping status
- Review planned execution sequence
- Navigate to the authoritative Test Case editor

Do not edit inherited Test Case metadata directly from this tab.

## 9.3 Inherited Scope

Display read-only inherited sections:

- Business Traceability
- Applications
- Framework Profiles
- Scripts
- Automation IR
- Test Data
- Environments
- Owners and approvers

Every item must show:

- Source entity
- Source ID
- Inheritance status
- Last synchronized timestamp
- Open source action

## 9.4 Conflicts and Gaps

Show:

- Missing application mapping
- Missing framework mapping
- Missing script or IR
- Conflicting frameworks
- Conflicting environments
- Deprecated assets
- Duplicate Test Cases
- Unsupported framework/application combinations
- Invalid repository links
- Missing test data
- Access or permission issues

Supported resolution actions:

- Keep configuration per Test Case
- Split into execution groups
- Apply default only to missing values
- Exclude affected Test Case
- Open authoritative source for correction
- Approve exception
- Save as Draft with unresolved non-blocking issues

Never silently overwrite inherited values.

## 9.5 Execution Groups

Allow grouping selected Test Cases by:

- Framework
- Application
- Environment
- Channel
- Execution agent
- Test type
- Sequence dependency
- Parallel execution compatibility

The group configuration is suite-owned orchestration metadata.

## 9.6 Automation Assets

Display:

- Scripts
- Automation IR
- Recordings
- Page objects
- Reusable components
- API collections
- Object repositories
- Git repositories
- Asset versions
- Validation state

Assets must remain linked to Test Cases and Framework Profiles.

---

# 10. Active Executions

Keep the Active Executions section.

Replace `Project` with `Automation Test Suite`.

Recommended columns:

- Execution Name
- Automation Test Suite
- Execution Group
- Test Case or Pack
- Environment
- Framework
- Started At
- Progress
- Status
- Actions

Supported statuses:

- Queued
- Preparing
- Running
- Passed
- Failed
- Blocked
- Inconclusive
- Cancelled

Deterministic execution results are authoritative.

AI may recommend diagnosis, healing, or classification but must not overwrite pass/fail status.

---

# 11. Activity Feed

Examples:

- Automation Test Suite created
- Test Cases added
- Regression Pack linked
- Inherited scope refreshed
- Missing mapping detected
- Conflict resolved
- Recording completed
- Automation IR updated
- Script generated
- Script manually modified
- Validation completed
- Validation failed
- Suite approved
- Suite published
- Execution completed
- Healing proposal submitted

---

# 12. Notifications

Examples:

- Failed executions
- Approvals pending
- Environments down
- Test data issues
- Missing framework mappings
- Missing application mappings
- Unmapped Test Cases
- Deprecated scripts
- Repository connection issues
- Validation blockers
- Source Test Case changed after publication

All counts must come from actual services.

---

# 13. Footer Status

Preserve:

- QA Environment status
- Agent availability
- Storage usage
- Current date and time
- Time zone

The footer must not hide content or break desktop responsiveness.

---

# 14. New Automation Test Suite — Final Wizard Design

## 14.1 Design Principle

The wizard must begin with Test Case selection because Test Cases are the primary source for the suite.

The wizard must not begin by requesting domain, product, channel, application, framework, script, priority, criticality, or owner.

## 14.2 Recommended Layout

Use a full-page wizard with three zones:

### Left Vertical Stepper

1. Select Test Cases
2. Suite Identification
3. Review Inherited Details
4. Resolve Conflicts and Define Scope
5. Execution and Schedule
6. Review and Create

### Main Workspace

Display the controls and information for the active step.

### Right Summary Panel

Show live counts:

- Selected Test Cases
- Selected Test Packs
- Business Projects
- Applications
- Framework Profiles
- Existing Scripts
- Automation IR definitions
- Environments
- Test Data Sources
- Requirements
- Defects
- Change Requests
- Missing Mappings
- Conflicts
- Execution Groups

### Sticky Footer Actions

```text
Cancel | Save as Draft | Back | Continue
```

On the final step:

```text
Cancel | Save as Draft | Back | Create Suite
```

---

# 15. Wizard Step 1 — Select Test Cases

## 15.1 Purpose

Select the Test Cases, Test Packs, or Regression Packs that define the Automation Test Suite.

## 15.2 Selection Options

Provide tabs or segmented controls:

- Test Cases
- Test Case Packs
- Regression Packs
- Import Test Case References

## 15.3 Search and Filters

Support:

- Test Case ID
- Objective
- Project
- Requirement
- Change Request
- Application
- Test type
- Automation status
- Framework
- Environment
- Priority
- Criticality
- Source system
- Tags

## 15.4 Test Case Table

Recommended columns:

- Selection
- Test Case ID
- Title / Objective
- Project / CR
- Application
- Test Type
- Priority
- Automation Status
- Linked Assets
- Mapping Status
- Expand

Expanding a Test Case should show:

- Linked requirements
- Applications
- Framework Profile
- Script or IR
- Environment
- Test data profile
- Last execution
- Validation state
- Source system

## 15.5 Selection Summary

The right panel must update immediately with inherited counts.

Display a clear message:

```text
All application, framework, script, environment, data, and traceability information is inherited from the selected Test Cases and linked assets.
```

---

# 16. Wizard Step 2 — Suite Identification

Capture only:

- Suite Name — mandatory
- Optional Description
- Optional Suite Tags

Optional behaviour:

- Auto-suggest a Suite Name from the selected Test Pack, Regression Pack, dominant business flow, or application journey
- Allow the user to edit the suggested name
- Check uniqueness within the permitted organisation or tenant scope

Do not capture:

- Domain
- Product
- Channel
- Application
- Framework
- Priority
- Criticality
- Owner
- Environment

Where suite ownership is required, derive it from the authenticated user, selected Test Pack owner, or existing governance configuration and display it as inherited.

---

# 17. Wizard Step 3 — Review Inherited Details

Display read-only sections:

## 17.1 Business Traceability

- Projects
- Programmes
- Requirements
- Change Requests
- Defects
- Releases
- Sprints
- Test Plans

## 17.2 Applications

- Primary applications
- Supporting applications
- APIs
- Databases
- External systems
- Application Model status

## 17.3 Framework Profiles

- Playwright
- Selenium
- Appium
- Katalon
- API automation
- Database validation
- Custom enterprise profiles

## 17.4 Automation Assets

- Scripts
- Automation IR
- Recordings
- Page objects
- Reusable components
- API collections
- Repositories

## 17.5 Execution Dependencies

- Environments
- Agents
- Test data
- Authentication profiles
- Browser or device matrices

Every inherited record must include:

- Source
- Source ID
- Status
- Last synchronized date
- Open source action

The user must not directly edit inherited values in this step.

---

# 18. Wizard Step 4 — Resolve Conflicts and Define Scope

This step is shown whenever conflicts or missing mappings exist.

## 18.1 Conflict Types

- Multiple Framework Profiles across selected Test Cases
- Multiple environments
- Missing application mapping
- Missing script or Automation IR
- Unsupported framework and application pairing
- Duplicate Test Cases
- Deprecated automation assets
- Missing test data
- Different execution constraints
- Conflicting sequencing
- Insufficient permissions
- Invalid source references

## 18.2 Resolution Options

- Keep configuration per Test Case
- Create separate execution groups
- Apply a default only where a value is missing
- Exclude affected Test Case
- Open the source entity for correction
- Approve a controlled exception
- Save as Draft
- Mark as manual-only within the suite
- Send for mapping review

## 18.3 Scope Controls

Allow users to define suite-owned scope such as:

- Include or exclude selected Test Cases
- Execution groups
- Planned execution sequence
- Dependency order
- Parallel execution eligibility
- Manual-only or automation-only filters
- Critical Test Case subset
- Smoke subset
- Regression subset

No resolution may silently modify the authoritative Test Case, Framework Profile, Application Model, or Automation Asset.

---

# 19. Wizard Step 5 — Execution and Schedule

Capture only suite-level orchestration:

- Execution group configuration
- Schedule — optional
- Parallelism
- Retry policy
- Timeout policy
- Evidence policy
- Notification rules
- Approval workflow
- Agent pool preference
- Default environment only for Test Cases with missing environment
- Default browser or device only for Test Cases with missing values

Do not overwrite an existing valid Test Case or asset-level configuration.

Do not store raw credentials. Use references to secret, authentication, or environment profiles.

---

# 20. Wizard Step 6 — Review and Create

Display:

- Suite Name
- Selected Test Cases
- Selected Test Packs or Regression Packs
- Inherited business scope
- Inherited applications
- Inherited frameworks
- Linked scripts and assets
- Execution groups
- Schedule
- Missing mappings
- Blocking conflicts
- Approved exceptions
- Activation readiness

Actions:

- Back
- Save as Draft
- Create Suite

## 20.1 Draft Rules

A Draft may be created when:

- Suite Name exists
- At least one Test Case, Test Pack, or Regression Pack is selected

Drafts may contain:

- Missing mappings
- Unresolved non-blocking conflicts
- Manual Test Cases
- Missing scripts
- Pending validations

## 20.2 Activation Rules

A suite is ready for validation or activation when:

- Suite Name exists
- At least one Test Case is selected
- Each executable Test Case has a valid application mapping
- Each automated Test Case has a valid Framework Profile
- Each automated Test Case has a valid script or Automation IR
- Blocking conflicts equal zero
- At least one executable execution group exists
- Required environment and test data dependencies are available
- Required approvals are satisfied

---

# 21. Cross-Screen Suite Context

The selected Automation Test Suite must remain available across all P1-S5 screens.

```text
Automation Workspace
    Create or open suite
            ↓
Live Recorder
    Record a selected Test Case within suite context
            ↓
Automation IR Editor
    Create or edit framework-neutral automation flow
            ↓
Script Editor
    Generate or maintain framework-specific scripts
            ↓
Validation and Review
    Validate, approve, publish, and release
```

The selected context must include:

- Suite ID
- Suite version
- Test Case ID
- Application ID
- Framework Profile ID
- Automation Asset ID
- Environment ID

Do not duplicate suite metadata independently on each screen.

---

# 22. Synchronization and Impact Management

## 22.1 Synchronization

The suite must show:

- Last inherited-data synchronization time
- Current synchronization status
- Refresh inherited scope action
- Source changes detected count

## 22.2 Source Changes

When an authoritative source changes:

- Draft suite: refresh inherited details
- Approved or Published suite: create impact review
- Active execution: retain the execution snapshot
- Historical execution: never change past evidence or results

## 22.3 Impact Review Examples

- Test Case objective changed
- Framework Profile version changed
- Script version changed
- Application endpoint changed
- Environment removed
- Test data profile changed
- Requirement or CR link changed
- Test Case disabled or deprecated

---

# 23. Suggested Data Relationships

Follow existing repository architecture and reuse equivalent entities when available.

Suggested additive relationships:

```text
automation_suite
automation_suite_test_case
automation_suite_pack
automation_suite_execution_group
automation_suite_exception
automation_suite_snapshot
automation_suite_approval
automation_suite_version
```

## 23.1 Suite Test Case Link

Suggested fields:

```text
suite_id
test_case_id
source_system
source_reference
inclusion_status
execution_group_id
planned_sequence
added_by
added_at
```

## 23.2 Execution Group

Suggested fields:

```text
suite_id
name
framework_profile_id
application_id
environment_id
agent_pool_id
parallelism
retry_policy
timeout_policy
sequence
status
```

## 23.3 Suite Snapshot

Suggested fields:

```text
suite_id
suite_version
test_case_version
application_model_version
framework_profile_version
automation_asset_version
environment_version
test_data_profile_version
created_at
created_by
```

These names are illustrative. Do not duplicate existing models.

---

# 24. Roles and Permissions

At minimum:

| Role | Key permissions |
|---|---|
| Automation Architect | Create suites, resolve architecture conflicts, define execution groups |
| Automation Engineer | Record, edit IR, generate and maintain scripts |
| Test Lead | Select Test Cases, review scope, approve suite |
| Tester | Review assigned Test Cases and evidence |
| Reviewer | Validate automation assets and evidence |
| Administrator | Manage reusable Framework Profiles and access |
| Viewer | Read-only access |

Reuse the existing authorization model.

---

# 25. UX and Visual Requirements

- Match the current nxtQA design system
- Preserve the dark left navigation
- Use the existing purple primary accent
- Use the current typography and components
- Maintain an enterprise SaaS appearance
- Use consistent spacing
- Use readable table density
- Use badges with text labels
- Do not rely on colour alone
- Provide loading, empty, error, permission-denied, partial-data, and stale-data states
- Support keyboard navigation
- Provide accessible labels
- Preserve responsive behaviour
- Keep sticky footer actions visible without hiding content
- Do not display editable controls for inherited values
- Clearly distinguish:
  - Inherited
  - Missing
  - Conflicting
  - Overridden for missing values
  - Exception approved
  - Version snapshot

---

# 26. Empty and Error States

## 26.1 No Test Cases Available

Display:

```text
No Test Cases are available for selection.
Create or import Test Cases in Test Management before creating an Automation Test Suite.
```

Actions:

- Open Test Cases
- Import Test Cases
- Refresh

## 26.2 No Automation Assets

Display:

```text
Selected Test Cases do not yet have automation assets.
The suite can be saved as Draft and completed through Live Recorder, Automation IR Editor, or Script Editor.
```

## 26.3 Missing Application Mapping

Display:

```text
Application mapping is missing for one or more selected Test Cases.
Update the source Test Case or map it through Application Discovery.
```

## 26.4 Synchronization Failure

Show:

- Failed source
- Failure reason
- Last successful synchronization
- Retry action
- Continue with last synchronized snapshot, when permitted

---

# 27. Non-Functional Requirements

- Do not hardcode sample values
- Use real backend counts
- Reuse existing components and services
- Keep API changes backward-compatible
- Use additive migrations
- Preserve existing routes and functionality
- Avoid duplicate entities
- Maintain audit history
- Enforce role-based access
- Handle large Test Case volumes with server-side pagination
- Support search and filters
- Avoid loading all Test Cases at once
- Keep wizard state recoverable after browser refresh where feasible
- Prevent duplicate suite creation from repeated submissions
- Validate source permissions before linking entities
- Log inheritance, conflict resolution, exception approval, and publication events

---

# 28. Acceptance Criteria

UI-018 is complete when:

1. Automation Workspace remains the creation and management entry point.
2. `New Project` is replaced by `New Automation Test Suite`.
3. Test Cases, Test Packs, or Regression Packs are the primary creation elements.
4. The wizard begins with Test Case selection.
5. Domain, product, channel, application, framework, script, environment, priority, criticality, and owner are not manually re-entered.
6. Inherited values are read-only and show their source.
7. Missing mappings and conflicts are clearly identified.
8. The system never silently overwrites authoritative data.
9. Users can split conflicting Test Cases into execution groups.
10. Users can save an incomplete suite as Draft.
11. Users can create or activate a suite only when blocking requirements are satisfied.
12. Published suite versions retain immutable snapshots.
13. Source changes trigger synchronization or impact review.
14. Recent Automation Test Suites uses the updated terminology.
15. Active Executions uses Automation Test Suite terminology.
16. The selected suite context is available across all five P1-S5 screens.
17. Existing functionality remains operational.
18. All metrics use real application data.
19. The screen supports loading, empty, error, stale, and permission states.
20. The final implementation matches the approved UI reference and nxtQA design system.

---

# 29. Implementation Directive for Codex

```text
Act as a senior enterprise product engineer and UI architect working on the nxtQA STLC Platform.

Repository:
D:\AI\Projects\stlc-platform

Implement the final consolidated P1-S5 UI-018 Automation Workspace contract.

Core decision:
Automation Test Suites must be created from selected Test Cases, Test Packs, or Regression Packs. Test Cases are the primary source of scope. Applications, frameworks, scripts, Automation IR, environments, test data, business traceability, priorities, criticality, and ownership must be inherited from authoritative linked entities.

Do not ask users to re-enter inherited information because this creates conflicting records.

The Automation Test Suite must own only:
- Suite Name
- Optional Description and Tags
- Selected Test Case membership
- Execution grouping
- Planned sequence
- Parallelism
- Retry and timeout policies
- Schedule
- Evidence policy
- Approval and notification rules
- Controlled defaults only for missing data
- Approved exceptions
- Version snapshots

Keep P1-S5 limited to:
1. Automation Workspace
2. Live Recorder
3. Automation IR Editor
4. Script Editor
5. Validation and Review

Do not add a separate Automation Test Suite menu.

Required UI-018 updates:
- Automation Suites KPI
- Test Cases KPI
- Automation Assets KPI
- Active Executions KPI
- Success Rate KPI
- New Automation Test Suite quick action
- Recent Automation Test Suites section
- Active Executions using Automation Test Suite terminology
- Suite detail tabs:
  Overview, Test Cases, Inherited Scope, Conflicts and Gaps, Execution Groups, Automation Assets, Test Data, Executions, Evidence, Versions

New Automation Test Suite wizard:
1. Select Test Cases
2. Suite Identification
3. Review Inherited Details
4. Resolve Conflicts and Define Scope
5. Execution and Schedule
6. Review and Create

Important constraints:
- First inspect the repository and map existing entities, APIs, routes, components, permissions, design tokens, state management, and migrations.
- Reuse existing Test Case, Project, Requirement, CR, Defect, Release, Application Model, Framework Profile, Script, Automation IR, Environment, Test Data, Execution, Evidence, and user entities.
- Do not duplicate business entities.
- Do not globally rename actual Project models.
- Do not hardcode dashboard values.
- Do not remove existing functionality.
- Make schema and API changes additive and backward-compatible.
- Inherited fields must be read-only.
- Every inherited value must show its source.
- Conflicts must be explicit and never silently overwritten.
- Draft suites may use current references.
- Published suites must retain immutable versioned snapshots.
- Deterministic execution results remain authoritative.
- AI may recommend mapping, classification, or healing but must not overwrite pass/fail results or silently publish changes.

Before implementation, provide:
- Current-state findings
- Existing reusable components and APIs
- Entity mapping
- Missing relationships
- Files to change
- Migration risks
- Implementation sequence

After implementation, provide:
- Files changed
- Schema and API changes
- Completed UI behaviour
- Tests executed and results
- Known limitations
- Final screenshots
```

---

# 30. Reference Images

Use the following references together with this contract:

- `UI-018-Automation-Workspace-Updated-Reference.png`
- Test-case-centric `New Automation Test Suite` wizard reference

Where a previous image conflicts with this contract, this final consolidated contract takes precedence.
