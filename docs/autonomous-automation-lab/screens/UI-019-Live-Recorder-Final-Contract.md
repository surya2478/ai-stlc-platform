# P1-S5 — Automation Studio Core
# UI-019 — Live Recorder
## Final UI/UX and Functional Contract

**Platform:** nxtQA STLC Platform  
**Repository:** `D:\AI\Projects\stlc-platform`  
**Module:** P1-S5 — Automation Studio Core  
**Screen ID:** UI-019  
**Screen Name:** Live Recorder  
**Predecessor:** UI-018 — Automation Workspace  
**Next lifecycle screen:** Automation IR Editor  
**Status:** Implementation-ready  
**Primary design principle:** Live Recorder operates in the context of a selected Automation Test Suite and Test Case. Test Case metadata, application mapping, framework profile, environment, test data, and linked traceability are inherited and must not be re-entered.

---

# 1. Purpose

UI-019 provides a controlled live-recording environment for capturing real user interactions against an actual target application.

The screen must allow users to:

- Select or confirm an Automation Test Suite
- Select a Test Case from that suite
- Launch the mapped application in the correct environment
- Record real user interactions
- Pause, resume, stop, discard, and save recording sessions
- Capture UI actions, locator candidates, screenshots, network activity, console activity, navigation, timings, and evidence
- Map recorded actions to existing Test Case steps
- Mark checkpoints and expected validations
- Record multi-application journeys
- Generate a framework-neutral Automation IR draft
- Preserve traceability to the Test Case, suite, application, framework, environment, and recording session
- Avoid generating automation from guessed or unverified behaviour

---

# 2. Position in P1-S5

```text
Automation Studio
├── UI-018 Automation Workspace
├── UI-019 Live Recorder
├── Automation IR Editor
├── Script Editor
└── Validation and Review
```

Lifecycle:

```text
Automation Workspace
→ Select suite and Test Case
→ Live Recorder
→ Launch application and capture real interactions
→ Automation IR Editor
→ Review and normalize framework-neutral actions
→ Script Editor
→ Generate framework-specific code
→ Validation and Review
→ Validate, approve, and publish
```

---

# 3. Core Domain Model

```text
Automation Test Suite
└── Test Case
    ├── Business Traceability
    ├── Test Steps
    ├── Expected Results
    ├── Application Mapping
    ├── Framework Profile
    ├── Environment
    ├── Test Data Profile
    └── Existing Automation Assets
        └── Live Recording Session
            ├── Recorded Actions
            ├── Screenshots
            ├── UI / DOM Snapshots
            ├── Locator Candidates
            ├── Network Events
            ├── Console Events
            ├── Checkpoints
            ├── Data Bindings
            ├── Evidence
            └── Automation IR Draft
```

---

# 4. Source-of-Truth Rules

| Information | Source of truth |
|---|---|
| Test Case objective, steps, expected results | Test Case |
| Project, requirement, CR, defect, release | Linked business entities |
| Application and system details | Application Model |
| Framework and runtime configuration | Framework Profile |
| Environment endpoints and availability | Environment service |
| Test data | Test Data Manager / linked data profile |
| Authentication | Authentication or secret profile |
| Recording output | Live Recording Session |
| Framework-neutral automation model | Automation IR |
| Generated code | Script asset |

Inherited information must be displayed as read-only. Corrections must be made in the authoritative source.

---

# 5. Entry Points

UI-019 may be opened from:

1. `Automation Workspace → Live Recorder`
2. `Automation Workspace → Open Suite → Test Cases → Start Recording`
3. A Test Case row action
4. `Live Recorder → Resume Draft Recording`

If no suite is active, the user must select an Automation Test Suite and one of its Test Cases.

A published recording must not be edited directly. Create a new recording version.

---

# 6. Preconditions

Before recording starts, validate:

- Automation Test Suite exists
- Test Case is selected and belongs to the suite
- Application mapping exists
- Application Model is available
- Environment is inherited or selected
- Environment is reachable
- Framework Profile is valid
- Recorder adapter supports the application and framework
- Authentication profile is available where required
- Required test data is available
- Execution agent, browser, emulator, or device is online
- User has recording permission
- No blocking mapping conflict exists
- Test Case is not locked by an incompatible operation

Missing inherited mappings must route the user to the source entity. Do not ask the user to duplicate application, framework, or environment configuration inside Live Recorder.

---

# 7. Recording Modes

## 7.1 Guided Test Case Recording — Default

- Display Test Case steps
- Highlight the active step
- Map one or more actions to each step
- Mark a step completed
- Skip with mandatory reason
- Add discovered sub-steps
- Mark expected-result checkpoints
- Show unmapped actions
- Show Test Case steps without recorded actions

## 7.2 Exploratory Recording — Controlled Option

Use for discovery, incomplete Test Cases, additional navigation, or reusable-flow capture.

Exploratory actions must still be linked to:

- Automation Test Suite
- Test Case or reusable flow
- Application
- Environment
- Recording session

Exploratory actions require review before conversion to Automation IR.

---

# 8. Page Layout

```text
Header
├── Breadcrumb and inherited context
├── Recording status
└── Session timer and controls

Main Workspace
├── Left Panel — Test Case and Session Context
├── Centre Panel — Live Application Session
└── Right Panel — Recorded Events and Technical Activity

Bottom Dock
├── Launch / Start / Pause / Resume / Stop
├── Evidence status
└── Save / Discard / Continue to IR
```

Both side panels should be collapsible to maximize the target-application viewport.

---

# 9. Header

Display:

- Breadcrumb: `Automation Studio / Live Recorder`
- Automation Test Suite selector
- Test Case selector
- Application selector when multiple applications are mapped
- Environment badge
- Framework Profile badge
- Recording mode
- Session status
- Session timer
- Help
- Exit

Example:

```text
Suite: Postpaid Order Provisioning E2E
Test Case: TC-2054 — Place Order
Application: CRM Portal
Environment: QA
Framework: Playwright Web
Mode: Guided Recording
Status: Ready
```

Lock inherited selectors when only one valid value exists. Context cannot change after recording starts; the current segment must first be stopped or saved.

---

# 10. Left Panel — Test Case Context

## 10.1 Test Case Summary

Show:

- Test Case ID
- Objective
- Test type
- Priority
- Criticality
- Automation status
- Application
- Framework
- Environment
- Linked requirements
- Existing automation status

## 10.2 Preconditions

Display inherited preconditions and allow:

- Mark verified
- Mark not met
- Add execution note
- Open source Test Case

Do not edit source precondition text in the recorder.

## 10.3 Test Steps

For each step, show:

- Step number
- Action
- Expected result
- Mapping status
- Recorded-action count
- Checkpoint status
- Warning or gap state

Statuses:

- Pending
- Active
- Recorded
- Partially Recorded
- Skipped
- Mismatch
- Needs Review
- Completed

Step actions:

- Set Active Step
- Complete Step
- Skip with Reason
- Add Discovered Sub-step
- Add Validation Checkpoint
- Add Note
- Review Captured Actions

---

# 11. Centre Panel — Live Application Session

The centre panel must host or control:

- Browser session
- Mobile device or emulator session
- Remote desktop session where supported
- External browser window with synchronized capture where embedding is unavailable

For web sessions, provide:

- Back
- Forward
- Refresh
- URL
- Secure-connection status
- Open externally
- Tab list
- Zoom
- Viewport
- Device emulation where supported

For mobile sessions, provide:

- Device
- Platform
- OS version
- Orientation
- App package
- Home
- Back
- Rotate
- Screenshot
- Device-log status

Optional overlays:

- Active-element highlight
- Locator confidence
- Step-mapping indicator
- Recording status
- Privacy-redaction indicator
- Network-capture status

Overlays must not alter application behaviour.

---

# 12. Right Panel — Recording Activity

Tabs:

```text
Actions
Network
Console
Locators
Evidence
Notes
```

## 12.1 Actions

For each action, show:

- Sequence
- Timestamp
- Action type
- Element summary
- Test Case step
- Application
- Page or screen
- Locator confidence
- Screenshot indicator
- Sensitivity indicator
- Review status

Supported action types include navigation, click, type, select, check, hover, drag-and-drop, upload, download, scroll, keyboard shortcut, tab/window handling, dialogs, waits, mobile tap/swipe/long press, and adapter-specific actions.

## 12.2 Network

Capture:

- Method
- Endpoint
- Status
- Duration
- Redacted headers
- Payload summary
- Response summary
- Step mapping
- Candidate API checkpoint
- Correlation IDs

Filters:

- Failed requests
- XHR / Fetch
- GraphQL
- Document
- WebSocket
- Status code
- Domain
- Duration

## 12.3 Console

Show errors, warnings, information, source, timestamp, and step mapping. Mask secrets and tokens.

## 12.4 Locators

Rank candidates in this order:

1. Stable test ID
2. Accessible role and name
3. Stable label
4. Stable semantic attribute
5. Stable unique text
6. Relative locator
7. CSS selector
8. XPath fallback

Show strategy, uniqueness, stability, confidence, match count, cross-session validation, and warning reason.

Low-confidence locators must not be automatically published.

## 12.5 Evidence

Show screenshots, video, trace, DOM snapshot, network archive, console log, downloaded files, uploaded-file metadata, and session timeline.

## 12.6 Notes

Allow notes linked to session, Test Case step, action, checkpoint, or application transition.

---

# 13. Recorder Controls

Required controls:

- Launch Application
- Start Recording
- Pause
- Resume
- Stop
- Save Draft
- Save and Continue to IR
- Discard Session
- Restart Session

Pause must stop user-action and locator capture, preserve the live session, continue only health monitoring, and avoid capturing sensitive activity during the pause.

Stop must finalize logs and evidence, process locators, identify unmapped actions and unrecorded steps, and create a recording summary.

Discard requires confirmation and a reason after capture begins. Audit the action.

---

# 14. Session State Model

```text
Draft
Preparing
Launching
Ready
Recording
Paused
Stopping
Processing
Captured
Needs Review
Failed
Cancelled
Discarded
Converted to IR
```

Typical transition:

```text
Draft → Preparing → Launching → Ready → Recording
Recording ↔ Paused
Recording → Stopping → Processing → Captured
Captured → Needs Review → Converted to IR
```

Preserve partial data on recoverable failures.

---

# 15. Test Case Step Mapping

Automatic mapping may use:

- Active step
- Action sequence
- Page context
- Element labels
- Expected result
- Prior sessions

Low-confidence mappings require review.

Users may:

- Map actions to steps
- Map multiple actions to one step
- Move actions between steps
- Mark setup or teardown
- Mark exploratory or reusable
- Exclude an action from IR

After Stop, detect:

- Steps without actions
- Actions without steps
- Expected results without checkpoints
- Unvalidated application transitions
- Missing data bindings
- Unsupported actions

---

# 16. Validation Checkpoints

Supported checkpoint types:

- Element visible or hidden
- Text equals or contains
- Value or attribute equals
- URL or title
- Download complete
- File exists
- API status
- API response field
- Network request occurred
- No severe console errors
- Mobile element state
- Application transition complete
- Async process status
- Custom adapter validation

Each checkpoint must link to the Test Case step, application, recorded point, expected result, and evidence.

Recorder recommendations must not silently become final assertions.

---

# 17. Multi-Application Recording

Support application segments for journeys across CRM, OMS, Billing, Provisioning, portals, mobile apps, APIs, databases, and external systems.

```text
Recording Session
├── Segment 1 — CRM Portal
├── Segment 2 — OMS Portal
├── Segment 3 — Billing API
└── Segment 4 — Provisioning Validation
```

Each segment must retain application, environment, adapter/framework, timestamps, step range, evidence, data inputs/outputs, and transition reason.

A new adapter creates a new segment within the same recording session.

---

# 18. Data Capture and Parameterization

Inherited test data is read-only.

Captured inputs may be classified as:

- Static value
- Test-data parameter
- Generated value
- Secret reference
- Previous-step output
- Environment value
- Runtime value

Never store plain-text passwords, tokens, API keys, session cookies, payment details, or protected personal values.

Support runtime data flow, for example:

```text
CRM order ID
→ runtime variable
→ OMS lookup
→ Billing validation
→ Provisioning validation
```

---

# 19. Locator Governance

Capture multiple candidates per action.

Evaluate:

- Uniqueness
- Stability
- Source
- Confidence
- Dynamic attributes
- Brittle hierarchy dependencies
- Fallback candidates

Statuses:

- Preferred
- Valid
- Needs Review
- Low Confidence
- Duplicate
- Invalid
- Deprecated

Final selection is reviewed in Automation IR Editor or Script Editor when below threshold.

---

# 20. Evidence Capture

Configurable options:

- Screenshot per action
- Screenshot on failure
- Video
- Browser trace
- Network archive
- Console log
- DOM snapshot
- Accessibility snapshot
- Mobile logs
- Download metadata
- Session timeline

Evidence policy must be inherited from suite or governance configuration rather than duplicated.

---

# 21. Recording Summary

After Stop, show:

- Duration
- Recorded actions
- Test Case coverage
- Unmapped actions
- Missing steps
- Checkpoints
- Applications visited
- Network failures
- Console errors
- Locator warnings
- Evidence generated
- Redactions
- Conflicts
- Unsupported actions
- IR readiness

Actions:

- Review Timeline
- Resume Recording
- Save Draft
- Discard
- Save and Continue to Automation IR Editor

---

# 22. Output Artifacts

A completed recording may produce:

- Recording Session
- Action timeline
- Step mappings
- Application segments
- Locator candidates
- Screenshots
- Video
- Trace
- Network archive
- Console log
- UI / DOM snapshots
- Data bindings
- Checkpoints
- Evidence index
- Automation IR draft
- Audit log

Automation IR must retain the source recording session and action IDs.

---

# 23. Existing Automation Assets

If the Test Case already has automation assets, show script, framework, repository, version, last validation, last execution, and recording source.

Provide:

- Create New Recording Version
- Record Missing Steps
- Compare Against Existing Script
- Re-record Entire Flow
- Cancel

Never silently overwrite a published asset.

---

# 24. Error and Recovery States

Handle:

- Application unavailable
- Authentication failure
- Runner or agent offline
- Session disconnected
- Browser or device crash
- Unsupported action
- Evidence-processing failure
- Network-capture failure
- Permission denied

Provide retry, reconnect, save partial, restart from checkpoint, open source configuration, or diagnostics where applicable.

Unsupported actions must be explicitly marked as manual, custom-adapter required, or IR review required.

---

# 25. Audit and Versioning

Audit:

- Session created
- Application launched
- Start
- Pause
- Resume
- Stop
- Mapping changes
- Checkpoints
- Redaction
- Discard
- Save
- IR generation

Create a new recording version when a published recording, Test Case, Application Model, Framework Profile, or recording flow changes materially.

---

# 26. Roles and Permissions

| Role | Capabilities |
|---|---|
| Automation Architect | Configure policy, review mappings, approve complex segments |
| Automation Engineer | Launch, record, map, save, and generate IR |
| Test Lead | Select scope and review coverage |
| Tester | Record assigned Test Cases where permitted |
| Reviewer | Review recordings, evidence, and mappings |
| Administrator | Manage adapters, agents, permissions, profiles |
| Viewer | Read-only |

Reuse the current authorization model.

---

# 27. UX and Visual Requirements

- Match UI-018 and the nxtQA design system
- Preserve dark left navigation and purple accent
- Keep inherited context visible and read-only
- Use a large centre viewport
- Allow side panels to collapse
- Keep recording controls sticky
- Use explicit status labels
- Confirm destructive actions
- Support keyboard navigation and accessibility
- Provide loading, empty, error, disconnected, permission, and stale-context states
- Preserve desktop responsiveness
- Do not fabricate target-application content

---

# 28. Non-Functional Requirements

- Use real application and environment services
- Stream events incrementally
- Persist partial sessions safely
- Prevent duplicate Start and Stop requests
- Support recovery
- Avoid blocking the UI during processing
- Mask secrets before persistence
- Encrypt protected storage as required
- Maintain auditability
- Keep adapters extensible
- Preserve backward compatibility
- Use additive schema/API changes
- Support long-running telecom flows and async transitions
- Use pagination or virtualization for long event histories

---

# 29. Suggested Data Relationships

Reuse existing entities where possible.

```text
recording_session
recording_segment
recording_action
recording_step_mapping
recording_checkpoint
recording_locator_candidate
recording_network_event
recording_console_event
recording_evidence
recording_data_binding
recording_version
```

Illustrative `recording_session` fields:

```text
id
suite_id
test_case_id
recording_mode
status
started_by
started_at
paused_at
stopped_at
duration
source_test_case_version
application_model_version
framework_profile_version
environment_id
agent_id
ir_status
created_at
updated_at
```

These names are illustrative and must not duplicate existing models.

---

# 30. Acceptance Criteria

UI-019 is complete when:

1. It opens from Automation Workspace and Test Case actions.
2. It requires a selected suite and Test Case.
3. Application, framework, environment, test data, and traceability are inherited.
4. Inherited context is read-only.
5. Guided Test Case Recording is the default.
6. The actual target application can be launched.
7. Start, pause, resume, stop, save, and discard work.
8. Paused activity is not captured as normal actions.
9. Actions map to Test Case steps.
10. Gaps and unmapped actions are detected.
11. Screenshots, locators, network, console, and evidence follow policy.
12. Sensitive values are masked.
13. Multi-application sessions use segments.
14. Published assets are not silently overwritten.
15. A summary is shown before saving.
16. Users can save Draft or continue to IR.
17. IR retains recording references.
18. Failures preserve partial data where possible.
19. Audit history and versioning are maintained.
20. The screen matches nxtQA UI/UX and preserves existing functionality.

---

# 31. Implementation Directive for Codex

```text
Act as a senior enterprise product engineer and automation-platform architect working on the nxtQA STLC Platform.

Repository:
D:\AI\Projects\stlc-platform

Implement P1-S5 UI-019 Live Recorder according to this contract.

Core principles:
- Operate inside a selected Automation Test Suite and Test Case.
- Test Case is the primary functional source.
- Inherit Application, Framework Profile, Environment, Test Data, and business traceability.
- Do not ask users to re-enter inherited information.
- Launch and record the real mapped application.
- Do not generate automation from guessed behaviour.
- Guided Test Case Recording is the default.
- Support pause, resume, stop, draft saving, discard, and continue to Automation IR Editor.
- Preserve end-to-end traceability.

Before implementation:
1. Inspect the repository.
2. Identify existing routes, components, recorder services, adapters, agents, Test Case entities, Application Model, Framework Profiles, environments, test data, evidence, authentication, and permissions.
3. Map reusable components and APIs.
4. Identify missing schema/API relationships.
5. Provide files to change, risks, and sequence.

Required UI:
- Context-rich header
- Left Test Case step panel
- Large centre live application viewport
- Right tabs for Actions, Network, Console, Locators, Evidence, and Notes
- Sticky controls
- Recording summary
- Error and recovery states

Required behaviour:
- Validate preconditions
- Stream events
- Map actions to Test Case steps
- Capture multiple locator candidates
- Capture governed evidence
- Mask secrets
- Support multi-application segments
- Preserve partial sessions
- Never silently overwrite published assets
- Generate framework-neutral Automation IR with source references
- Keep deterministic results authoritative

Engineering constraints:
- Reuse existing entities and services
- Do not duplicate Test Case, Application, Framework, Environment, or Test Data records
- Make changes additive and backward-compatible
- Do not hardcode sample values
- Preserve existing functionality
- Use the nxtQA design system
- Add unit, integration, state-transition, security, and UI tests

After implementation, provide:
- Files changed
- Schema/API changes
- Adapter integrations
- Completed behaviour
- Tests and results
- Known limitations
- Final screenshots
```

---

# 32. Final Design Summary

```text
Selected Test Case
→ Inherit automation context
→ Launch real application
→ Record actual actions
→ Map actions to Test Case steps
→ Capture evidence and locator candidates
→ Review gaps and conflicts
→ Generate Automation IR draft
```

Live Recorder must never become a second source of truth for Test Case, application, framework, environment, or test-data metadata.
