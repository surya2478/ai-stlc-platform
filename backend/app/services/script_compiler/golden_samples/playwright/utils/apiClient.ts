/**
 * Thin API client used by apiValidations steps in the Automation Generation
 * Contract. Base URL and auth come from the environment profile, never
 * hardcoded — see environmentProfile in the contract.
 */
export async function getJson(path: string, baseUrl: string, token?: string): Promise<any> {
  const response = await fetch(`${baseUrl}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok) {
    throw new Error(`API validation request failed: ${response.status} ${path}`);
  }
  return response.json();
}
