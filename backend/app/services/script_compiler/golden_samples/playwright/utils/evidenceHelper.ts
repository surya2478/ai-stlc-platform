import { TestInfo } from '@playwright/test';

/**
 * Attaches evidence required by the contract's evidenceRequired list.
 * Trace/video/screenshot capture itself is configured globally in
 * playwright.config.ts (retain-on-failure); this helper attaches
 * business-context evidence (e.g. the created order id) to the test report.
 */
export async function attachEvidence(testInfo: TestInfo, name: string, value: string): Promise<void> {
  await testInfo.attach(name, { body: value, contentType: 'text/plain' });
}

/**
 * Records that the contract requires a named piece of business evidence which
 * the current contract format cannot bind to a real value.
 *
 * This used to be rendered as `attachEvidence(testInfo, name, name)` — the
 * evidence's own label attached as its content, producing a report attachment
 * that looked captured but proved nothing. Declaring it unfulfilled is the
 * honest form: the requirement stays visible in the report, and nothing
 * downstream can mistake the marker for a captured artifact.
 *
 * Replace these call sites with `attachEvidence` once the contract carries a
 * value expression for each evidence item.
 */
export async function declareRequiredEvidence(testInfo: TestInfo, name: string): Promise<void> {
  await testInfo.attach(`evidence-required/${name}`, {
    body: JSON.stringify({
      evidence: name,
      status: 'not_captured',
      reason:
        'The generation contract declares this evidence but provides no value to capture. ' +
        'It is recorded as an outstanding requirement, not as captured evidence.',
    }),
    contentType: 'application/json',
  });
}
