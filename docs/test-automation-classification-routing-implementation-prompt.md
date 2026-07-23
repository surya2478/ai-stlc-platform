# Implementation Prompt — Policy-Driven Test Automation Classification and Routing

## Project context

Work on the existing nxtQA STLC Platform repository:

```text
D:\AI\Projects\stlc-platform
```

Before making any changes, inspect the repository and confirm the current branch, working tree status, existing uncommitted changes, relevant frontend routes, backend services, models, migrations, APIs, feature flags and tests.

Do not overwrite, revert, delete or reformat unrelated user changes.

The implementation must follow the locked nxtQA Autonomous Automation Fabric structure of 58 screens. Do not introduce a new top-level screen or increase the approved screen count. The relevant Phase 1 sequence is:

```text
P1-S3 — Test Design and Approval

UI-010 Generated Test Cases
UI-011 Test Case Editor
UI-012 Journey Graph
UI-013 Test Case Approval

P1-S4 — Application Discovery

UI-014 Application Registry
UI-015 Live Discovery Session
UI-016 Application Model
UI-017 API and Network Explorer
```

The approved plan assigns automation preference, application mapping, evidence requirements, independent approval and discovery eligibility to P1-S3, while UI-015 is responsible for grounded discovery after the test case is approved.

---

## Objective

Implement a governed, policy-driven **Test Automation Classification and Routing capability** within the existing P1-S3 Test Design and Approval workflow.

The capability must determine:

- Whether a test case is an automation candidate.
- Whether it is fully recommended, conditional, blocked, deferred or not recommended.
- The appropriate primary automation adapter or framework.
- The supporting MCPs and external validators required.
- Whether Live Discovery is required.
- The recommended discovery mode.
- Required test data, application mappings and environment capabilities.
- Required deterministic evidence sources.
- Complexity and automation-value scores.
- The policy rules and technical conditions that led to the result.

The classification must be generated before UI-015. UI-015 must consume the approved classification and validate runtime readiness; it must not originate or silently alter the classification.

---

## Non-negotiable constraints

1. Preserve all existing functionality.
2. Do not add a 59th screen.
3. Do not create a new top-level menu named Classification & Routing.
4. Do not move this functionality to Project Settings.
5. Do not place it inside the legacy AI Automation Studio.
6. Keep the capability within the new Autonomous Automation initiative.
7. Reuse existing authentication, RBAC, project selection, audit, feature flags, API conventions, database patterns, jobs and UI components.
8. Do not hard-code application names, MCP names, framework choices, routing rules or telecom taxonomy values.
9. Do not let the AI agent make the final approval decision.
10. Do not permit the same agent identity to recommend and approve the same classification.
11. Do not treat AI confidence as an approval criterion.
12. Do not generate or execute unrestricted SQL.
13. Do not expose secrets, credentials, tokens, OTP values or sensitive data.
14. Do not silently overwrite an approved classification when policies or test cases change.
15. All classification, review, override and approval actions must be versioned and auditable.
16. Backend authorization and deterministic rules remain authoritative.
17. All new migrations must be reversible.
18. Long-running classification jobs must be idempotent and expose persisted progress.
19. Missing mandatory application, evidence, data or validator capability must not produce an approved result.
20. UI-015 must block discovery when mandatory classification requirements are unavailable.

---

## Required lifecycle

Implement the following lifecycle:

```text
Approved or draft-authorized test case
        ↓
Resolve effective classification policy
        ↓
Run deterministic eligibility rules
        ↓
Run Test Classification Agent
        ↓
Resolve adapter and MCP capabilities
        ↓
Calculate complexity and automation value
        ↓
Store versioned recommendation
        ↓
Reviewer corrects or accepts recommendation
        ↓
Journey and application feasibility validation
        ↓
Independent classification approval
        ↓
UI-015 consumes approved classification
        ↓
Runtime readiness validation
```

Responsibility separation:

```text
Deterministic rules engine
    Decides what is allowed, blocked or mandatory.

Classification agent
    Recommends the most suitable automation route.

Reviewer
    Corrects and reviews the recommendation.

Independent approver
    Approves the final classification.

UI-015
    Executes discovery according to the approved classification.
```

---

## Screen integration

### UI-010 — Generated Test Cases

Extend the existing Generated Test Cases screen without creating a disconnected route.

Add an automation-classification summary to each generated test case.

Required fields:

- Candidate status.
- Recommended primary adapter.
- Supporting adapters or MCPs.
- Discovery required.
- Recommended discovery mode.
- Complexity score.
- Automation-value score.
- Required evidence.
- Deterministic blockers.
- Classification review status.
- Effective policy and version.
- Last classified timestamp.

Recommended candidate states:

```ts
type AutomationCandidateStatus =
  | "NOT_EVALUATED"
  | "RECOMMENDED"
  | "CONDITIONAL"
  | "NOT_RECOMMENDED"
  | "BLOCKED"
  | "DEFERRED"
  | "APPROVED"
  | "POLICY_STALE"
  | "RECLASSIFICATION_REQUIRED";
```

Add row actions:

- Classify.
- Reclassify.
- View recommendation.
- View matched rules.
- Open classification policy.
- Send to Test Case Editor.

Add a contextual **Classification Policy** drawer or modal.

It must show:

- Effective enterprise/project policy.
- Candidate thresholds.
- Blocking conditions.
- Routing matrix.
- Mandatory and optional MCP mappings.
- Evidence rules.
- Policy version.
- Simulation result for the selected test case.
- Read-only policy details unless the user has an authorized Phase 1 policy-management permission.

Do not build the full Phase 3 policy-administration screen here.

### UI-011 — Test Case Editor

Extend the existing Test Case Editor with an **Automation Readiness** section.

Allow authorized users to review and correct:

- Candidate status recommendation.
- Test channel and technical test type.
- Primary adapter.
- Supporting adapters.
- Mandatory external validators.
- Optional validators.
- Discovery requirement.
- Discovery mode.
- Test-data dependencies.
- Application mapping.
- Environment capability requirements.
- Evidence requirements.
- Automation assumptions.
- Known blockers.
- Reviewer notes.

Corrections must preserve:

- Original AI value.
- Revised reviewer value.
- Actor.
- Timestamp.
- Reason.
- Policy version.
- Classification version.

The user may correct the recommendation, but cannot approve it from UI-011.

### UI-012 — Journey Graph

Extend Journey Graph incrementally.

Do not replace or redesign the accepted screen structure.

Represent the approved or proposed execution route within the graph:

```text
Requirement
   ↓
Journey
   ↓
Scenario
   ↓
Test Case
   ├── Primary automation adapter
   ├── API validator
   ├── Database validator
   ├── Domain MCPs
   ├── Event or Kafka validator
   ├── Observability validator
   └── Evidence requirements
```

Add visual states for:

- Adapter available.
- Adapter unavailable.
- Mandatory validator missing.
- Optional validator missing.
- Application mapping incomplete.
- Evidence policy incomplete.
- Discovery eligible.
- Discovery blocked.
- Conditional automation route.
- Fully automation ready.

Selecting a test-case node should expose:

- Candidate status.
- Primary adapter.
- Supporting MCPs.
- Mandatory validators.
- Missing capabilities.
- Evidence requirements.
- Classification policy.
- Matched rules.
- Classification version.
- Required remediation.

Do not approve classifications from UI-012.

### UI-013 — Test Case Approval

UI-013 is the independent approval gate.

Extend the right-side inspector with a new tab or section:

```text
Automation Classification
```

Required content:

- Agent recommendation.
- Deterministic rule result.
- Candidate status.
- Primary adapter.
- Supporting adapters and MCPs.
- Mandatory external validators.
- Optional validators.
- Discovery requirement.
- Discovery mode.
- Required evidence.
- Complexity score.
- Automation-value score.
- Effective policy ID and version.
- Matched rules.
- Deterministic blockers.
- Reviewer corrections.
- Separation-of-duty validation.
- Approval history.

Required decisions:

- Approve automation classification.
- Approve as conditional.
- Mark not recommended.
- Defer.
- Request changes.
- Return to Test Case Editor.
- Return to Journey Graph.

Request Changes, Conditional, Deferred and Not Recommended decisions must require a reason.

Approval must fail when:

- Test case is not approved.
- Requirement or scenario traceability is invalid.
- Mandatory application mapping is missing.
- Mandatory expected results are incomplete.
- Required evidence is undefined.
- Required adapter is unsupported.
- Mandatory MCP or validator is unavailable or unconfigured.
- Classification policy is stale.
- Classification inputs changed after recommendation.
- Reviewer separation-of-duty requirements fail.
- User lacks approval permission.

After approval, persist an immutable approved classification version.

### UI-015 — Live Discovery Session

Update UI-015 only after the classification backend contract is available.

UI-015 must receive and display the approved classification:

- Test Case ID and title.
- Candidate status.
- Classification version.
- Policy version.
- Primary adapter.
- Supporting MCPs.
- Mandatory validators.
- Optional validators.
- Discovery mode.
- Application ID.
- Environment.
- Test-data requirement.
- Evidence policy.

Add a visible **Approved Automation Route** summary.

Example:

```text
Primary adapter: Playwright MCP
Discovery mode: Guided User Recording

Required validators:
- API Validator
- OMS MCP
- Billing MCP
- Kafka MCP

Optional validators:
- CRM MCP
- Observability MCP
```

The adapter and MCP selection must come from the approved classification and capability registry. Do not use local static arrays.

UI-015 readiness must verify:

- Primary adapter is connected and operational.
- Mandatory MCPs are connected.
- Authentication profiles exist.
- Target environment is authorized.
- Required test data is available.
- Application mapping matches the approved stable application ID.
- Required evidence storage and policies are available.
- Required external validation endpoints are reachable.

If a mandatory validator is unavailable:

```text
Discovery Readiness: BLOCKED
Reason: Mandatory Billing MCP is unavailable.
```

Do not silently downgrade a mandatory validator to optional.

---

## User-configurable policy model

The classification agent must follow user-defined, approved policy criteria.

Implement policy scope and precedence:

```text
Security and regulatory guardrails
    >
Enterprise mandatory rules
    >
Project classification policy
    >
Application or journey overrides
    >
Agent recommendation
    >
Reviewer override with explicit permission and reason
```

Phase 1 should support consumption, inspection, simulation and limited authorized policy maintenance through contextual drawers.

The complete administration of policies, agents and adapters remains assigned to:

- UI-055 Policy and Autonomy Control.
- UI-056 Agent, Model, Prompt and Tool Registry.
- UI-057 Integration and Adapter Administration.
- UI-058 Audit, Security and Retention.

Do not implement these Phase 3 screens early.

---

## Policy criteria

Support configurable policy criteria such as:

### Candidate suitability

- Requirement approval.
- Test-case completeness.
- Expected-result determinism.
- Repeatability.
- Execution frequency.
- Regression value.
- Business criticality.
- Manual effort.
- Reusability.
- Test-data availability.
- Application stability.
- Environment availability.
- Manual-judgment dependency.
- Production-only constraint.
- CAPTCHA, biometric or OTP dependency.
- Destructive action.
- Regulatory sensitivity.
- Financial impact.
- External dependency count.

### Routing criteria

- Web, API, mobile, desktop, database or integration test.
- Modern DOM availability.
- Accessibility semantics.
- Existing Selenium assets.
- Browser requirements.
- Native mobile or WebView.
- API specification availability.
- Database validation requirement.
- Messaging or Kafka requirement.
- External-system validation.
- Application or channel compatibility.
- Runner and operating-system compatibility.

### Evidence criteria

- Screenshot.
- DOM snapshot.
- Accessibility snapshot.
- Network trace.
- API response.
- Database state.
- Event evidence.
- Logs.
- Distributed trace.
- Business assertion.
- Optional video.

---

## Example policy

Store policy as typed persisted data. YAML or JSON may be used for transport or display, but database entities should be normalized where practical.

```yaml
policy:
  code: WEB_TELECOM_E2E
  version: 1

candidate_rules:
  require_approved_requirement: true
  require_deterministic_expected_result: true
  minimum_repeatability_score: 70
  minimum_automation_value_score: 60

  block_if:
    - unresolved_requirement
    - missing_expected_result
    - production_only
    - unsupported_application
    - mandatory_validator_not_configured

  conditional_if:
    - test_data_not_ready
    - unstable_ui
    - optional_validator_unavailable

routing_rules:
  - when:
      channel: WEB
      modern_dom: true
    primary_adapter: PLAYWRIGHT_MCP

external_validation_rules:
  - journey: ORDER_CANCELLATION
    required:
      - API_VALIDATOR
      - OMS_MCP
      - BILLING_MCP
      - KAFKA_MCP
    optional:
      - CRM_MCP
      - OBSERVABILITY_MCP

evidence_rules:
  web_e2e:
    mandatory:
      - SCREENSHOT
      - DOM_SNAPSHOT
      - NETWORK_TRACE
      - STEP_RESULT
      - BUSINESS_ASSERTION
```

---

## Classification output contract

Use a versioned typed contract similar to:

```ts
type ClassificationResult = {
  id: string;
  projectId: number;
  testCaseId: number;
  version: number;

  candidateStatus:
    | "RECOMMENDED"
    | "CONDITIONAL"
    | "NOT_RECOMMENDED"
    | "BLOCKED"
    | "DEFERRED"
    | "APPROVED";

  primaryAdapter: string | null;
  supportingAdapters: string[];
  mandatoryValidators: string[];
  optionalValidators: string[];

  discoveryRequired: boolean;
  recommendedDiscoveryMode:
    | "GUIDED_USER"
    | "FREE_USER_ACTION"
    | "SUPERVISED_AGENT"
    | null;

  complexityScore: number | null;
  automationValueScore: number | null;

  requiredEvidence: string[];
  requiredCapabilities: string[];
  deterministicBlockers: ClassificationBlocker[];
  advisoryWarnings: ClassificationWarning[];
  matchedRules: ClassificationRuleMatch[];

  policyId: string;
  policyVersion: number;

  agentId: string | null;
  modelVersion: string | null;
  promptVersion: string | null;
  toolVersions: Record<string, string>;

  reviewStatus:
    | "PENDING_REVIEW"
    | "CHANGES_REQUESTED"
    | "REVIEWED"
    | "APPROVED"
    | "REJECTED";

  createdAt: string;
  updatedAt: string;
};
```

---

## Backend design

Inspect existing models first and reuse existing canonical entities where possible.

Recommended domain service:

```text
backend/app/services/autonomous_automation/test_classification/
├── classification_service.py
├── deterministic_rules.py
├── policy_resolver.py
├── routing_resolver.py
├── capability_resolver.py
├── scoring_service.py
├── audit_service.py
└── schemas.py
```

Adapt naming to repository conventions discovered during inspection.

Required responsibilities:

### Classification service

- Load the test case and related requirement, journey, application and evidence context.
- Resolve the effective policy.
- Execute deterministic rules.
- Invoke the classification agent for advisory analysis.
- Resolve adapter and MCP capabilities.
- Calculate scores.
- Persist a versioned result.
- Emit audit and progress events.

### Policy resolver

- Resolve enterprise, project, application and journey scope.
- Apply permitted override precedence.
- Return policy ID and version.
- Reject invalid or unpublished policies.

### Capability resolver

Resolve from governed registries:

- Adapter maturity.
- MCP availability.
- Environment compatibility.
- Browser/device support.
- Authentication profile availability.
- Validator configuration.
- Evidence support.

Capability maturity should use explicit values such as:

```ts
type CapabilityMaturity =
  | "REAL"
  | "MOCK"
  | "VIRTUALIZED"
  | "RECORDED"
  | "NOT_CONFIGURED"
  | "UNSUPPORTED";
```

No capability marked `MOCK`, `NOT_CONFIGURED` or `UNSUPPORTED` may be treated as fully operational unless policy explicitly permits simulation and the UI clearly labels it.

---

## Database entities

Review existing `aal_*`, test-case, approval, policy, agent, tool and audit models before introducing new tables.

Likely additions or extensions:

```text
AutomationClassificationPolicy
AutomationClassificationPolicyVersion
AutomationRoutingRule
AutomationEvidenceRule
AutomationValidatorRule
TestCaseAutomationClassification
TestCaseAutomationClassificationVersion
TestCaseAdapterRequirement
TestCaseValidatorRequirement
ClassificationRuleMatch
ClassificationReview
ClassificationDecision
ClassificationOverride
ClassificationAuditEvent
```

Required qualities:

- Project-scoped authorization.
- Versioning.
- Soft deletion where audit history is required.
- Immutable approved versions.
- Supersession references.
- Policy provenance.
- Agent/model/prompt/tool provenance.
- Reviewer and approver identities.
- Separation-of-duty enforcement.
- Timestamps and reasons.
- Optimistic concurrency or equivalent stale-update protection.
- Reversible migrations.

---

## API requirements

Follow the existing `/api/v1/lab` compatibility strategy and repository API conventions.

Suggested endpoint family:

```text
/api/v1/lab/test-design/classifications
```

Suggested operations:

```http
GET  /api/v1/lab/test-design/classification-policies/effective
GET  /api/v1/lab/test-design/classification-policies/{policyId}
POST /api/v1/lab/test-design/classification-policies/simulate

POST /api/v1/lab/test-design/classifications/evaluate
POST /api/v1/lab/test-design/classifications/bulk-evaluate
GET  /api/v1/lab/test-design/classifications/{classificationId}
GET  /api/v1/lab/test-design/test-cases/{testCaseId}/classification

POST /api/v1/lab/test-design/classifications/{classificationId}/review
POST /api/v1/lab/test-design/classifications/{classificationId}/request-changes
POST /api/v1/lab/test-design/classifications/{classificationId}/approve
POST /api/v1/lab/test-design/classifications/{classificationId}/defer
POST /api/v1/lab/test-design/classifications/{classificationId}/reject
POST /api/v1/lab/test-design/classifications/{classificationId}/reclassify
```

Every endpoint must include:

- Project authorization.
- Typed request and response schemas.
- Structured errors.
- Audit event.
- Idempotency where applicable.
- Correlation ID.
- Stale-version detection.
- Pagination where collections are returned.
- Feature-flag enforcement.

Suggested errors:

```text
CLASSIFICATION_POLICY_NOT_FOUND
CLASSIFICATION_POLICY_NOT_PUBLISHED
TEST_CASE_NOT_ELIGIBLE
TEST_CASE_VERSION_STALE
APPLICATION_MAPPING_MISSING
MANDATORY_VALIDATOR_UNAVAILABLE
ADAPTER_NOT_SUPPORTED
CLASSIFICATION_ALREADY_APPROVED
CLASSIFICATION_REVIEW_CONFLICT
SEPARATION_OF_DUTY_VIOLATION
RECLASSIFICATION_REQUIRED
PERMISSION_DENIED
```

---

## Classification agent

Implement or extend a governed Test Classification Agent using the repository’s existing LangGraph and role-routing conventions.

The agent input must include:

- Test case and version.
- Requirement and analysis context.
- Journey and scenario context.
- Application mappings.
- Test-data requirements.
- Evidence requirements.
- Effective classification policy.
- Adapter capability registry.
- MCP capability registry.
- Similar approved classifications when available.
- Relevant RAG sources with provenance.

The agent output must be typed and include:

- Candidate recommendation.
- Primary adapter.
- Supporting adapters.
- Mandatory and optional validators.
- Discovery requirement and mode.
- Complexity estimate.
- Automation-value estimate.
- Reasons.
- Assumptions.
- Warnings.
- Referenced policy rules.
- Confidence.

The agent must not:

- Approve the result.
- Override deterministic blockers.
- Invent an application or MCP.
- Invent an API, database or system capability.
- Treat unavailable capabilities as operational.
- Execute automation or discovery.
- Modify an approved classification in place.

---

## Deterministic rules

At minimum, implement deterministic checks for:

- Requirement approval state.
- Test-case approval eligibility.
- Title, preconditions, steps and expected results.
- Requirement and scenario traceability.
- Stable application mapping.
- Discovery eligibility.
- Required test data.
- Supported application channel.
- Adapter capability.
- Required MCP capability.
- Environment compatibility.
- Evidence policy completeness.
- Sensitive or prohibited actions.
- Policy version currency.
- User permission.
- Separation of duties.

Deterministic blockers must always take precedence over the agent recommendation.

---

## Scoring

Implement configurable scoring rather than hard-coded arithmetic embedded in UI components.

Suggested outputs:

```text
Automation Value Score: 0–100
Complexity Score: 0–100
Maintenance Risk Score: 0–100
Execution Stability Score: 0–100
```

Store the factor-level breakdown so users can understand the result.

Example:

```json
{
  "automation_value_score": 86,
  "factors": [
    {
      "factor": "regression_frequency",
      "weight": 20,
      "score": 18
    },
    {
      "factor": "manual_effort",
      "weight": 20,
      "score": 19
    },
    {
      "factor": "expected_result_determinism",
      "weight": 20,
      "score": 20
    }
  ]
}
```

Do not allow scores alone to bypass deterministic blockers.

---

## Feature flags and permissions

Add or extend feature flags following current AAF conventions.

Suggested flags:

```text
AUTONOMOUS_LAB_TEST_CLASSIFICATION_ENABLED
AUTONOMOUS_LAB_CLASSIFICATION_AGENT_ENABLED
AUTONOMOUS_LAB_CLASSIFICATION_POLICY_SIMULATION_ENABLED
AUTONOMOUS_LAB_EXTERNAL_VALIDATOR_ROUTING_ENABLED
```

Suggested permissions:

```text
autonomous_lab.classification.view
autonomous_lab.classification.evaluate
autonomous_lab.classification.review
autonomous_lab.classification.approve
autonomous_lab.classification.override
autonomous_lab.classification.simulate_policy
autonomous_lab.classification.view_audit
```

Use actual repository permission naming conventions after inspection.

---

## Frontend requirements

Reuse the existing Next.js, React, TypeScript, Tailwind, Radix and TanStack Query stack.

Do not add another frontend framework.

Reuse:

- Existing page shell.
- Project selector.
- KPI cards.
- Status badges.
- Compact tables.
- Drawers.
- Tabs.
- Dialogs.
- Filters.
- Toasts and alerts.
- Permission wrappers.
- Query hooks.
- Loading, empty and error states.

Required UI states:

- Not evaluated.
- Evaluating.
- Recommendation ready.
- Conditional.
- Blocked.
- Not recommended.
- Deferred.
- Review pending.
- Changes requested.
- Approved.
- Policy stale.
- Reclassification required.
- Permission denied.
- Agent unavailable.
- Capability registry unavailable.
- Partial API failure.

Do not show sample counts or fabricated records while loading.

---

## Audit requirements

Persist audit events for:

- Classification requested.
- Policy resolved.
- Agent recommendation produced.
- Deterministic blocker generated.
- Reviewer correction.
- Validator added or removed.
- Adapter changed.
- Policy simulation.
- Review completed.
- Approval.
- Rejection.
- Deferral.
- Override.
- Reclassification.
- Policy-stale transition.
- UI-015 readiness refusal.

Each event must contain:

- Project ID.
- Test case ID and version.
- Classification ID and version.
- Actor.
- Agent identity where applicable.
- Policy ID and version.
- Previous value.
- New value.
- Reason.
- Timestamp.
- Correlation ID.
- Source screen or API.
- Model, prompt and tool versions where applicable.

---

## Testing requirements

### Backend

Add tests for:

- Policy precedence.
- Enterprise mandatory-rule enforcement.
- Project and application override behavior.
- Deterministic blockers.
- Agent output schema validation.
- Unsupported adapter handling.
- Mandatory MCP unavailable.
- Optional MCP unavailable.
- Classification versioning.
- Approved classification immutability.
- Policy-stale detection.
- Reclassification.
- Separation of duties.
- Project isolation.
- Permission enforcement.
- Idempotent evaluation.
- Bulk evaluation.
- Audit creation.
- Migration upgrade and downgrade.

### Frontend

Add tests for:

- UI-010 classification status and policy drawer.
- UI-011 reviewer corrections.
- UI-012 route and MCP visualization.
- UI-013 approval gating.
- UI-015 approved-route display.
- Mandatory-validator readiness failure.
- Policy-stale state.
- Loading, empty, permission and partial-error states.
- Keyboard accessibility.
- Responsive table and drawer behavior.

### Regression

Run and preserve:

- Existing backend test suite.
- Existing focused Autonomous Lab tests.
- Frontend lint.
- TypeScript typecheck.
- Production build.
- Existing test-case workflow tests.
- Existing Journey Graph tests.
- Existing Test Case Approval tests.
- Existing Application Registry tests.
- Existing discovery tests.

---

## Implementation sequence

Follow this order:

1. Inspect repository and document exact extension points.
2. Report the current working tree and protect unrelated changes.
3. Confirm current UI-010 through UI-015 routes and components.
4. Confirm existing test-case approval and audit APIs.
5. Confirm existing agent, policy, adapter and feature-flag foundations.
6. Produce a concise gap analysis.
7. Define database and API contracts.
8. Implement reversible migrations.
9. Implement policy resolver and deterministic rules.
10. Implement capability resolver.
11. Implement versioned classification service.
12. Implement the classification agent.
13. Add APIs and permissions.
14. Extend UI-010.
15. Extend UI-011.
16. Extend UI-012.
17. Extend UI-013.
18. Integrate approved classifications into UI-015 readiness.
19. Add tests.
20. Run full verification.
21. Provide screenshots and implementation evidence.
22. Update the implementation tracker and relevant UI contracts.
23. Do not proceed to unrelated screens.

---

## Required initial response from the coding agent

Before changing code, provide:

1. Current branch and working tree status.
2. Relevant existing routes and components for UI-010 through UI-015.
3. Relevant backend models, services, APIs and migrations.
4. Existing feature flags and permissions.
5. Existing test-classification or routing logic, if any.
6. Existing Playwright MCP and external adapter registries.
7. Exact files proposed for modification.
8. Exact new files proposed.
9. Database migration proposal.
10. API proposal.
11. Identified risks and compatibility concerns.
12. Implementation sequence.
13. Explicit confirmation that no new screen or top-level menu will be created.

Do not start implementation until this assessment is complete.

---

## Definition of done

The change is complete only when:

- The approved 58-screen structure remains unchanged.
- UI-010 produces a policy-driven classification recommendation.
- UI-011 supports audited reviewer corrections.
- UI-012 displays adapter, MCP and evidence feasibility.
- UI-013 independently approves the automation classification.
- UI-015 consumes the approved route and blocks unavailable mandatory validators.
- Policies are versioned and explainable.
- Agent and deterministic results remain separate.
- Mandatory rules cannot be overridden by AI.
- All actions are authorized and audited.
- Approved classifications are immutable and versioned.
- Policy changes trigger stale or reclassification states.
- No static application, adapter or MCP list is embedded in frontend logic.
- Existing functionality remains intact.
- Feature flags can disable the capability safely.
- Migrations upgrade and downgrade successfully.
- Backend tests pass.
- Frontend lint, typecheck and production build pass.
- Authenticated browser verification passes.
- Implementation tracker and contracts are updated.
- Known limitations and maturity labels are documented.

---

## Final instruction

Implement this as an incremental, production-quality extension of the existing nxtQA Autonomous Automation Fabric.

Do not create a parallel architecture.

Do not create a disconnected classification page.

Do not simulate unavailable adapters or MCPs as operational.

Inspect first, reuse existing foundations, implement backend source-of-truth behavior, preserve all working features, and provide evidence for every completed change.
