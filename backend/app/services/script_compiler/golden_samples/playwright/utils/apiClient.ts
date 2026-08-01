/**
 * Thin API client used by apiValidations steps in the Automation Generation
 * Contract. Base URL and auth come from the environment profile, never
 * hardcoded — see environmentProfile in the contract.
 */

export interface ApiResponse {
  status: number;
  ok: boolean;
  body: any;
}

export interface RequestJsonOptions {
  method?: string;
  token?: string;
  /**
   * The status the contract declares. When set, a different status throws
   * before the body is inspected — a validation that expects 201 must not
   * quietly accept 200, and one that expects 404 must not be treated as a
   * transport failure.
   */
  expectedStatus?: number;
}

export async function requestJson(
  path: string,
  baseUrl: string,
  options: RequestJsonOptions = {},
): Promise<ApiResponse> {
  const { method = 'GET', token, expectedStatus } = options;
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  // Read the body regardless of status: an error body is usually the most
  // useful part of the failure message, and a contract may legitimately
  // expect a non-2xx status.
  let body: any = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (expectedStatus !== undefined && response.status !== expectedStatus) {
    throw new Error(
      `API validation ${method} ${path} expected status ${expectedStatus} ` +
        `but received ${response.status}. Body: ${JSON.stringify(body)}`,
    );
  }

  return { status: response.status, ok: response.ok, body };
}

/**
 * Backwards-compatible helper for callers that only want the parsed body of a
 * successful GET (contract cleanup actions still use this shape).
 */
export async function getJson(path: string, baseUrl: string, token?: string): Promise<any> {
  const response = await requestJson(path, baseUrl, { method: 'GET', token });
  if (!response.ok) {
    throw new Error(`API validation request failed: ${response.status} ${path}`);
  }
  return response.body;
}
