/**
 * Thin DB validation helper used by dbValidations steps in the Automation
 * Generation Contract. Connection details come from the environment
 * profile's configured DB validation endpoint (a read-only service, never a
 * direct DB credential in the script) — see dbValidations in the contract.
 */

async function queryRow(
  validationEndpoint: string,
  query: Record<string, unknown>,
): Promise<{ found: boolean }> {
  const response = await fetch(validationEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(query),
  });
  if (!response.ok) {
    // A transport/endpoint failure is not evidence about the row. It must not
    // be collapsed into "absent", or a broken validator would silently satisfy
    // every expectFound=false assertion.
    throw new Error(
      `DB validation endpoint failed (${response.status}) for query: ${JSON.stringify(query)}`,
    );
  }
  return response.json();
}

export async function assertRowExists(
  validationEndpoint: string,
  query: Record<string, unknown>,
): Promise<void> {
  const body = await queryRow(validationEndpoint, query);
  if (!body.found) {
    throw new Error(`Expected DB row not found for query: ${JSON.stringify(query)}`);
  }
}

/**
 * The expectFound=false half of the contract. Previously this case rendered as
 * assertRowExists with a TODO comment, which asserted the exact opposite of
 * what the contract declared.
 */
export async function assertRowAbsent(
  validationEndpoint: string,
  query: Record<string, unknown>,
): Promise<void> {
  const body = await queryRow(validationEndpoint, query);
  if (body.found) {
    throw new Error(
      `DB row was expected to be absent but was found for query: ${JSON.stringify(query)}`,
    );
  }
}
