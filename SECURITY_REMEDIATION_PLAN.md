# STLC Platform — Security Remediation Plan

**Date:** June 16, 2026
**Version:** 1.0
**Classification:** Confidential

---

## Phase 0: Security Baseline and Backup

**Objective:** Establish a safe foundation before making any changes.

**Scope:** Version control, backup, dependency audit, documentation.

**Files likely to be changed:** None (read-only phase)

**Implementation steps:**

1. Create a dedicated security branch: `git checkout -b security/hardening-v1`
2. Tag current state: `git tag pre-security-audit-baseline`
3. Document all current working features with screenshots/recordings
4. Run dependency audits:
   - Backend: `pip audit` (install `pip-audit` first)
   - Frontend: `npm audit` in `frontend/`
5. Export current database schema: `pg_dump --schema-only`
6. Document current `.env` variable inventory
7. Create a security issue tracker (GitHub Issues project board or Jira epic)
8. Verify all tests pass on the baseline: `pytest backend/tests/`

**Validation steps:**
- Confirm baseline tag exists in git
- Confirm dependency audit reports saved
- Confirm all existing tests pass
- Confirm feature inventory document created

**Regression testing required:** Run full test suite to establish baseline pass/fail.

**Rollback plan:** Checkout the baseline tag.

**Expected outcome:** A documented baseline with known-good state, dependency audit results, and a tracking mechanism for all security changes.

---

## Phase 1: Critical Security Fixes

**Objective:** Eliminate all Critical and authentication-bypass vulnerabilities.

**Scope:** Secret key, exposed API keys, hardcoded credentials, vulnerable JWT library, open registration.

**Files likely to be changed:**
- `.env` — Generate real APP_SECRET_KEY, rotate API keys, set strong DB password
- `backend/app/core/startup_checks.py` — Enhanced secret validation
- `backend/app/config.py` — Default debug=False, stronger secret validation
- `backend/requirements.txt` — Replace python-jose with PyJWT
- `backend/app/core/security.py` — Update JWT implementation for PyJWT, add jti claim
- `backend/app/api/deps.py` — Fix DEV_USER_EMAIL bug, check is_active on every request
- `backend/app/api/v1/endpoints/users.py` — Add rate limiting to login/register, add password complexity
- `frontend/src/app/login/page.tsx` — Remove SSO simulation with hardcoded credentials
- `frontend/src/lib/api.ts` — Remove NEXT_PUBLIC dev auth variables
- `backend/alembic.ini` — Remove hardcoded credentials

**Implementation steps:**

1. **Rotate exposed API keys (SEC-004)**
   - Generate new Cerebras API key from provider dashboard
   - Generate new Groq API key from provider dashboard
   - Update `.env` with new keys
   - Verify LLM functionality works

2. **Generate proper APP_SECRET_KEY (SEC-003)**
   - Run: `python -c "import secrets; print(secrets.token_hex(32))"`
   - Update `.env` with generated key
   - Update `startup_checks.py` to validate: minimum 32 chars, not in blocklist of placeholders
   - Update `config.py` to raise ValueError (not just warn) for weak keys in production

3. **Set strong database credentials (SEC-015)**
   - Generate random password: `python -c "import secrets; print(secrets.token_urlsafe(24))"`
   - Update `.env` DATABASE_URL
   - Update `docker-compose.yml` POSTGRES_PASSWORD
   - Restart database, run migrations

4. **Replace python-jose with PyJWT (SEC-006)**
   - Replace `python-jose[cryptography]==3.3.0` with `PyJWT[cryptography]>=2.9.0` in requirements.txt
   - Update `backend/app/core/security.py`:
     - Change `from jose import jwt, JWTError` to `import jwt; from jwt.exceptions import PyJWTError`
     - Update `create_access_token()` to use `jwt.encode(payload, key, algorithm="HS256")`
     - Update token decode to use `jwt.decode(token, key, algorithms=["HS256"])`
     - Add UUID `jti` claim to payload
   - Update `backend/app/api/deps.py` to catch `PyJWTError` instead of `JWTError`

5. **Remove hardcoded SSO credentials (SEC-001)**
   - In `frontend/src/app/login/page.tsx`: Remove the simulation login calls from SSO buttons
   - Replace with placeholder UI that shows "SSO integration coming soon" or real OIDC redirect

6. **Remove NEXT_PUBLIC dev auth (SEC-002)**
   - In `frontend/src/lib/api.ts`: Remove `DEV_AUTH_EMAIL` and `DEV_AUTH_PASSWORD` constants
   - Remove the auto-login mechanism (lines 51-78)
   - Add build-time validation that blocks builds when these vars are set

7. **Secure user registration (SEC-005)**
   - Add rate limiting decorator: max 3 registrations per IP per hour
   - Add password complexity validation: min 12 chars, 1 upper, 1 lower, 1 digit, 1 special
   - Add common password check against top-1000 list

8. **Add brute-force protection to login (SEC-007)**
   - Install `slowapi`: add to requirements.txt
   - Add rate limiter: max 5 login attempts per IP per minute
   - Add account-level lockout: 30-minute lockout after 10 failed attempts
   - Log all failed login attempts

9. **Fix DEV_USER_EMAIL bug (SEC-052)**
   - Change `DEV_USER_EMAIL` to `settings.dev_seed_user_email` in deps.py
   - Add startup check to block `DEV_SEED_USER_ENABLED=true` in production

10. **Remove credentials from alembic.ini (SEC-031)**
    - Set `sqlalchemy.url =` to empty in alembic.ini
    - In `alembic/env.py`, override from DATABASE_URL: `config.set_main_option("sqlalchemy.url", settings.database_url)`

**Validation steps:**
- All existing tests pass
- Login works with valid credentials
- Login fails after 5 rapid attempts (rate limiting active)
- Registration rejects weak passwords
- JWT tokens created/validated with new PyJWT library
- SSO buttons no longer auto-authenticate
- Dev auto-login does not trigger
- LLM calls work with new API keys

**Regression testing required:**
- Full authentication flow (register, login, token validation)
- All API endpoints that use JWT auth
- LLM test case generation
- Jira integration (Fernet key derives from same secret)

**Rollback plan:** `git checkout pre-security-audit-baseline`

**Expected outcome:** All Critical vulnerabilities eliminated. Authentication hardened with rate limiting and password policies. No exposed secrets.

---

## Phase 2: High-Risk Security Hardening

**Objective:** Address all High-severity infrastructure and session management issues.

**Scope:** HTTPS, security headers, session management, Redis auth, route protection.

**Files likely to be changed:**
- `docker-compose.yml` — Add nginx proxy, Redis auth, restrict ports, remove --reload
- `backend/app/main.py` — Security headers middleware, disable docs in prod
- `backend/app/core/security.py` — Short-lived tokens, refresh token support
- `backend/app/api/v1/endpoints/users.py` — Add logout endpoint with token blocklist
- `frontend/next.config.js` — Security headers
- `frontend/src/middleware.ts` — New file: route protection
- `frontend/src/lib/api.ts` — Refresh token logic, remove localStorage token storage
- `frontend/src/app/users/page.tsx` — Server-side role verification
- Backend/frontend Dockerfiles — Non-root user

**Implementation steps:**

1. **Add security headers middleware to backend (SEC-011)**
   - Create middleware that adds: X-Content-Type-Options, X-Frame-Options, HSTS, Referrer-Policy, Permissions-Policy
   - Add to `main.py` before CORS middleware

2. **Add security headers to Next.js (SEC-011)**
   - Add `headers()` function to `next.config.js`
   - Include CSP, X-Frame-Options, X-Content-Type-Options, HSTS

3. **Disable API docs in production (SEC-019)**
   - `docs_url="/docs" if settings.app_env != "production" else None`
   - Same for `redoc_url`

4. **Implement refresh token rotation (SEC-008)**
   - Reduce access token lifetime to 15 minutes
   - Create refresh token endpoint with 7-day lifetime
   - Store refresh token family in Redis for rotation detection
   - Add `jti` claim to access tokens

5. **Add server-side token blocklist (SEC-008, SEC-040)**
   - Create `/users/logout` endpoint that adds token `jti` to Redis blocklist
   - Check blocklist in `get_current_user` dependency
   - Check `is_active` status on every request

6. **Move JWT to httpOnly cookies (SEC-009)**
   - Set access token as `httpOnly`, `Secure`, `SameSite=Strict` cookie in login response
   - Update `get_current_user` to read from cookie
   - Update frontend to not store token in localStorage

7. **Add Next.js middleware for route protection (SEC-010)**
   - Create `frontend/src/middleware.ts`
   - Validate auth cookie on server-side for all routes except `/login` and `/api`
   - Redirect unauthenticated requests to `/login`

8. **Fix client-side authorization (SEC-016)**
   - Fetch user profile from `/users/me` on page load instead of localStorage
   - Treat cached role data as display hints only

9. **Add Redis authentication (SEC-014)**
   - Add `--requirepass` to Redis command in docker-compose.yml
   - Update REDIS_URL with password
   - Update Celery broker URL

10. **Restrict Docker ports (SEC-015, SEC-014)**
    - Change `"5432:5432"` to `"127.0.0.1:5432:5432"` or remove
    - Change `"6379:6379"` to `"127.0.0.1:6379:6379"` or remove

11. **Add non-root users to Dockerfiles (SEC-030)**
    - Backend Dockerfile: `RUN adduser --disabled-password appuser && USER appuser`
    - Frontend Dockerfile: same pattern

12. **Add HTTPS via reverse proxy (SEC-018)**
    - Add nginx service to docker-compose.yml
    - Configure TLS termination with Let's Encrypt or self-signed cert
    - Update all URLs to HTTPS

13. **Restrict CORS (SEC-021)**
    - `allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]`
    - `allow_headers=["Authorization", "Content-Type", "Accept"]`
    - Update allowed origins to HTTPS

14. **Separate dev/prod Docker configs (SEC-041, SEC-042)**
    - Create `docker-compose.override.yml` for dev (with --reload, volumes, npm run dev)
    - Base `docker-compose.yml` for production (no --reload, COPY not mount, npm run start)

**Validation steps:**
- All security headers present in responses (check with securityheaders.com)
- Refresh token rotation works correctly
- Token revocation (logout) invalidates access
- Next.js middleware redirects unauthenticated users to /login
- Redis requires authentication
- DB port not accessible from outside Docker
- HTTPS working with valid certificate
- Frontend route protection active

**Regression testing required:**
- Full login/logout flow
- All CRUD operations across all modules
- Jira integration
- LLM test case generation
- File upload/download
- Agent workflows

**Rollback plan:** Revert git changes; restore docker-compose.yml from backup.

**Expected outcome:** Hardened session management, HTTPS-only communication, proper security headers, protected routes, and secured infrastructure.

---

## Phase 3: AI/LLM Security Hardening

**Objective:** Protect against prompt injection, secure LLM interactions, validate AI outputs.

**Scope:** Prompt templates, input sanitization, output validation, document content safety.

**Files likely to be changed:**
- `backend/app/agents/requirement/intake_agent.py` — Input sanitization
- `backend/app/agents/requirement/quality_agent.py` — Output validation
- `backend/app/agents/test_planning/test_case_agent.py` — Prompt hardening
- `backend/app/agents/test_planning/scenario_agent.py` — Prompt hardening
- `backend/app/llm/provider.py` — Gemini API key in header, logging safeguards
- `backend/app/llm/structured.py` — Enhanced output validation
- `backend/app/services/document_service.py` — Document content sanitization
- `backend/app/api/v1/endpoints/requirements.py` — Path traversal fix, GitHub PAT redaction

**Implementation steps:**

1. **Add prompt injection detection**
   - Create `backend/app/security/prompt_guard.py`
   - Detect injection patterns: "ignore previous instructions", "system prompt", role-switching attempts
   - Apply to all user-supplied text before LLM calls
   - Log detected injection attempts

2. **Harden prompt templates**
   - Wrap all user-supplied content in clear delimiters: `<user_content>...</user_content>`
   - Add system-level instructions that ignore instructions within user content
   - Use structured output schemas to constrain LLM responses

3. **Sanitize uploaded document content**
   - Strip potential prompt injection from extracted PDF/DOCX text
   - Limit document text length passed to LLM
   - Add content type detection for adversarial documents

4. **Fix path traversal in code analysis (SEC-013)**
   - Add `ALLOWED_CODE_ANALYSIS_PATHS` configuration
   - Validate `os.path.realpath(local_path).startswith(allowed_base)`
   - Reject paths outside allowed directories

5. **Redact GitHub PAT from agent_runs (SEC-012)**
   - Mask token in `input_data` before database write: `github_token: "***REDACTED***"`
   - Pass actual token to worker via separate secure parameter

6. **Move Gemini API key to header (SEC-044)**
   - Change `params={"key": self.api_key}` to `headers={"x-goog-api-key": self.api_key}`

7. **Add LLM output content safety checks**
   - Validate generated test cases don't contain executable code injection
   - Validate generated content doesn't contain HTML/script tags
   - Add maximum output length limits

**Validation steps:**
- Prompt injection attempts detected and logged
- Document upload with injection payload safely processed
- Code analysis rejects paths outside allowed directories
- GitHub PAT not visible in agent_runs table
- Gemini API key not in URL/logs
- LLM outputs pass safety validation

**Regression testing required:**
- All LLM-powered features (test case generation, requirement analysis, quality scoring)
- File upload and processing
- Code analysis workflow
- GitHub integration

**Rollback plan:** Revert agent and service changes; prompt guard can be disabled via config flag.

**Expected outcome:** LLM interactions hardened against prompt injection. Sensitive data redacted from persistence. Path traversal eliminated.

---

## Phase 4: Data and Integration Security

**Objective:** Harden data access, Jira integration, audit logging, and data isolation.

**Scope:** Jira security, database access patterns, audit logging, data retention.

**Files likely to be changed:**
- `backend/app/services/jira_service.py` — Webhook validation, error sanitization, encryption improvement
- `backend/app/api/v1/endpoints/jira.py` — Import validation
- `backend/app/api/v1/endpoints/settings.py` — Remove internal path exposure
- `backend/app/api/v1/endpoints/health.py` — Auth for pool stats
- `backend/app/services/project_service.py` — Replace raw SQL with ORM cascades
- New: `backend/app/core/audit_logger.py` — Security event logging
- New: `backend/app/middleware/audit_middleware.py` — Request audit middleware

**Implementation steps:**

1. **Fix webhook signature bypass (SEC-023)**
   - Change `if not secret: return True` to `if not secret: return False`
   - Add configuration validation that warns when webhook secret is empty

2. **Improve Jira encryption (SEC-032)**
   - Replace simple SHA-256 with HKDF: `from cryptography.hazmat.primitives.kdf.hkdf import HKDF`
   - Add salt to key derivation
   - Migration: decrypt existing tokens with old method, re-encrypt with new

3. **Sanitize Jira error messages (SEC-051)**
   - Return generic errors to client
   - Log detailed Jira errors server-side

4. **Remove internal path exposure from settings (SEC-026)**
   - Remove `file_storage_path`, `ollama_base_url` from settings response
   - Only expose what the UI needs: provider names, model names

5. **Add auth to health pool endpoint (SEC-027)**
   - Require authentication for `/health/pool`
   - Keep `/health` and `/health/ready` unauthenticated for probes

6. **Remove environment info from root endpoint (SEC-050)**
   - Return only `{"status": "ok"}` from unauthenticated root

7. **Implement security audit logging (SEC-025)**
   - Create `audit_logger.py` with structured logging for:
     - Login attempts (success/failure)
     - Registration events
     - Password changes
     - Permission changes
     - Token generation/revocation
     - File uploads
     - LLM configuration changes
     - Jira import/export events
   - Store in dedicated audit log table or structured log files

8. **Replace raw SQL in project deletion (SEC-006 related)**
   - Use ORM cascade deletes instead of `text(f"DELETE FROM {table}")`

9. **Add data retention policy**
   - Auto-cleanup uploaded files after configurable retention period
   - Purge expired JWT blocklist entries from Redis
   - Archive old agent run logs

**Validation steps:**
- Webhooks rejected when secret not configured
- Jira tokens correctly encrypted/decrypted with new method
- Settings endpoint no longer leaks internal paths
- Pool endpoint requires authentication
- Audit logs capture all security events
- Project deletion uses ORM cascades

**Regression testing required:**
- Jira integration (connection, import, sync, webhooks)
- Settings page functionality
- Health check monitoring
- Project creation and deletion
- All CRUD operations

**Rollback plan:** Revert service changes. For Jira encryption migration, keep backward-compatible decrypt.

**Expected outcome:** Hardened integrations, comprehensive audit logging, reduced information leakage.

---

## Phase 5: DevSecOps and Production Readiness

**Objective:** Establish ongoing security practices and production-ready deployment.

**Scope:** CI/CD security, dependency scanning, security testing, monitoring.

**Files likely to be changed:**
- New: `.github/workflows/security-scan.yml` — CI security pipeline
- New: `backend/tests/test_security.py` — Security test suite
- New: `frontend/src/middleware.ts` — (if not done in Phase 2)
- `.gitignore` — Add certificate/key patterns
- `docker-compose.yml` — Production-ready configuration
- New: `docker-compose.prod.yml` — Production override
- New: `SECURITY_RUNBOOK.md` — Incident response procedures

**Implementation steps:**

1. **Add dependency scanning to CI/CD**
   - GitHub Action: `npm audit --audit-level=high` for frontend
   - GitHub Action: `pip-audit` for backend
   - Fail build on high/critical vulnerabilities
   - Schedule weekly scans

2. **Add SAST scanning**
   - Integrate `bandit` for Python security scanning
   - Integrate `eslint-plugin-security` for JavaScript
   - Add `semgrep` rules for common web vulnerabilities

3. **Create security test suite**
   - Auth bypass tests
   - IDOR tests
   - Rate limiting verification
   - Input validation tests
   - See SECURITY_TEST_CASES.md for full list

4. **Add .gitignore patterns (SEC-058)**
   - Add `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.crt`

5. **Create production docker-compose**
   - Separate `docker-compose.prod.yml`
   - No source mounts, no --reload, no dev mode
   - Includes nginx TLS proxy
   - Health checks on all services

6. **Set up monitoring and alerting**
   - Log aggregation (ELK stack or cloud equivalent)
   - Alert on: repeated auth failures, unusual API patterns, error rate spikes
   - Dashboard for security metrics

7. **Create security runbook**
   - Incident response procedures
   - Key rotation procedures
   - Account compromise response
   - Vulnerability disclosure process

8. **Implement environment separation**
   - Separate `.env.development`, `.env.staging`, `.env.production` templates
   - Ensure dev features are build-time excluded from production

**Validation steps:**
- CI/CD pipeline includes security scans
- Security tests pass
- Production compose works without dev features
- Monitoring dashboards operational
- Runbook reviewed and accessible

**Regression testing required:**
- Full end-to-end testing in production-like environment
- All features functional without dev conveniences
- Performance testing under rate limiting

**Rollback plan:** Individual components can be reverted. CI/CD changes are additive.

**Expected outcome:** Sustainable security posture with automated scanning, testing, monitoring, and incident response procedures.

---

## Summary Timeline

| Phase | Duration | Dependencies | Critical Findings Addressed |
|---|---|---|---|
| Phase 0 | 1 day | None | None (preparation) |
| Phase 1 | 3-5 days | Phase 0 | SEC-001 through SEC-006 (all Critical) |
| Phase 2 | 5-7 days | Phase 1 | SEC-007 through SEC-019 (all High) |
| Phase 3 | 3-5 days | Phase 1 | SEC-012, SEC-013, SEC-044, SEC-045 |
| Phase 4 | 3-5 days | Phase 2 | SEC-020 through SEC-034 (Medium) |
| Phase 5 | 5-7 days | Phase 3, 4 | Ongoing security practices |
| **Total** | **20-30 days** | | |

---

*End of Security Remediation Plan*
