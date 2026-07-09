# ADR-001: Controlled Playwright Automation Generation with MCP Grounding

**Status:** Accepted · **Date:** 2026-07-09
**Related:** [AGENTIC_AUTOMATION_IMPLEMENTATION_PLAN.md](AGENTIC_AUTOMATION_IMPLEMENTATION_PLAN.md)

## Context

The platform's original automation agent generated Playwright/Pytest code directly from
test-case text: the LLM guessed selectors, waits, assertions, file layout, and naming.
The result was inconsistent, frequently non-executable scripts and no enforceable
standard. External architecture review (2026-07) concluded that inconsistency cannot be
fixed by adding more reviewer LLMs; it requires a controlled generation framework where
AI drafts intent and deterministic tooling owns the code.

## Decision

Ownership is fixed as follows and must not drift:

| Concern | Owner |
|---|---|
| Test intelligence (coverage, business rules, taxonomy, test types, risk) | **nxtQA platform** (requirement → scenario → test case pipeline) |
| Automation intent | **LLM agents** — emit a structured, versioned Automation Generation Contract (JSON) only |
| Code generation | **nxtQA Script Compiler** — deterministic templates, Page Object Model, fixed folder structure |
| Browser-grounded discovery (real locators, page structure, UI feasibility) | **Playwright MCP** (pinned version, sandboxed, allowlisted) |
| Execution and evidence | **Playwright Test** via the automation runner |
| Promotion of production-grade scripts | **Humans** — role-based approvals (QA Reviewer → Automation Lead → Environment Owner → Release/Regression) |
| Long-term automation assets | **Git + CI** — DB retains metadata, status, lineage, and evidence |

### Non-negotiable rule: No Free-Form Script Generation

No agent may persist `.spec.ts` / `.py` source code as its final output.

```text
Agent Output → Automation Generation Contract JSON → Script Compiler → Generated Code
```

Enforcement:
- `AutomationScript` rows must reference a contract (`contract_json`, `contractVersion`) and
  the compiler version that rendered them.
- The Static Quality Gate rejects any script lacking the compiler-stamped generation header
  (TC ID, REQ ID, contract version, compiler version).
- Code review must reject any change that lets an LLM write or edit script files directly,
  including inside repair/healing loops — repairs modify the contract, then recompile.

### Contract requirements

- The contract schema is **versioned** (`contractVersion`), starting at `1.0`; the compiler
  supports N and N-1 versions so previously generated assets never break silently.
- The contract carries, at minimum: `testCaseId`, `requirementId`, `testType`,
  `businessFlow`, `preconditions`, `testDataBindings`, `pageObjects`, `steps`,
  `expectedResults`, `assertions`, `locators`, `apiValidations`, `dbValidations`,
  `cleanupActions`, `evidenceRequired`, `environmentProfile`, `scriptType`.
- **Multi-environment awareness:** `environmentProfile` (DEV / SIT / QA / UAT / PREPROD /
  PROD_SANITY) selects validation depth — e.g. SIT compiles API + DB + integration
  validation; UAT compiles business-readable validation; Production Sanity compiles
  non-invasive, read-only checks only.

### Reference standard

Golden sample scripts (manually authored, reviewed, and frozen before compiler
implementation) define what compiler output must look like. Compiler and reviewer
conformance is measured against them.

### Versioning and rollback

Script changes (including AI repair/healing proposals) always create a new version;
prior versions are archived and restorable, never overwritten. A working approved
script can always be rolled back to.

## Consequences

- Structural consistency is guaranteed by construction, not by review.
- LLM output becomes schema-validatable data; hallucinated code structure is impossible.
- Adding a new convention (naming, evidence hook, retry rule) is a template/compiler
  change applied uniformly — not a prompt tweak hoped to stick.
- Cost: the compiler and templates must be built and maintained; contract schema changes
  require versioned migration. This is accepted as the price of enterprise consistency.
- Any future feature that needs "just let the model write the code" requires a new ADR
  superseding this one.
