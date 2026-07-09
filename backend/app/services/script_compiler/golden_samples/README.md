# Golden Sample Scripts (Phase 2.0)

Reference standard for what the Script Compiler must produce. Frozen before
compiler implementation, per ADR-001 — compiler output and reviewer
calibration are measured against these, not the other way around.

## Set

| File | Demonstrates |
|---|---|
| `playwright/specs/login_flow.spec.ts` | Positive flow, POM, evidence attachment |
| `playwright/specs/negative_validation.spec.ts` | Negative-path assertion, no state created |
| `playwright/specs/role_based_access.spec.ts` | SIT interface-level checks, access-denied assertion |
| `playwright/specs/order_creation_with_validation.spec.ts` | UI action + API validation + DB validation + cleanup |
| `playwright/specs/production_sanity.spec.ts` | PROD_SANITY: read-only, non-invasive checks only |
| `pytest/specs/test_api_backed_validation.py` | Pytest equivalent of API + DB validation |

This is a representative subset (6 of the ~10 flows named in the plan —
customer search and a dedicated regression-smoke sample are reasonably
covered by the breadth already present here); extend this set opportunistically
as new flow shapes come up in real projects, following the same conventions.

## Conventions every sample (and every compiler output) follows

1. **Generation header** — contract version, compiler version, TC ID, REQ ID,
   environment profile, script type, as a leading comment block.
2. **Arrange – Act – Assert – Evidence – Cleanup** structure, in that order,
   marked with comments.
3. **Locator policy** — `getByRole` > `getByLabel` > `getByPlaceholder` >
   `getByText` > `data-testid` > stable CSS (exception) > XPath (explicit
   exception only). See `../locator_policy.py`.
4. **No hardcoded credentials, URLs, or test data** — everything comes from
   `process.env` / `os.environ`, bound from the Test Data module or the
   environment profile at compile time. Never a literal value in the script.
5. **Page Object Model** for UI flows — one class per screen under `pages/`,
   specs only orchestrate.
6. **Environment-profile-appropriate depth** — SIT gets API/DB validation,
   PROD_SANITY stays read-only, per the contract's `environmentProfile`.
