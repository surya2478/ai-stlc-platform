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
