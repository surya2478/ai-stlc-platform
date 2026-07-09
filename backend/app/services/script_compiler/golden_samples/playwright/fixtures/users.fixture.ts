/**
 * Test data fixture. Values are bound from the platform's Test Data module
 * via ${placeholder} references resolved at compile time (see
 * app/services/parameter_binding.py) — never hardcoded literals. This file
 * is the deterministic shape the compiler renders; actual values come from
 * the bound TestDataRecord for the run's environment profile.
 */
export interface UserFixture {
  username: string;
  password: string;
  role: string;
}

export const VALID_USER: UserFixture = {
  username: process.env.TEST_USERNAME ?? '',
  password: process.env.TEST_PASSWORD ?? '',
  role: process.env.TEST_USER_ROLE ?? 'standard',
};

export const INVALID_USER: UserFixture = {
  username: process.env.TEST_USERNAME ?? '',
  password: 'wrong-password-placeholder',
  role: 'n/a',
};
