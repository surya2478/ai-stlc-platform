/**
 * Thin DB validation helper used by dbValidations steps in the Automation
 * Generation Contract. Connection details come from the environment
 * profile's configured DB validation endpoint (a read-only service, never a
 * direct DB credential in the script) — see dbValidations in the contract.
 */
export async function assertRowExists(
  validationEndpoint: string,
  query: Record<string, unknown>,
): Promise<void> {
  const response = await fetch(validationEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(query),
  });
  if (!response.ok) {
    throw new Error(`DB validation failed for query: ${JSON.stringify(query)}`);
  }
  const body = await response.json();
  if (!body.found) {
    throw new Error(`Expected DB row not found for query: ${JSON.stringify(query)}`);
  }
}
