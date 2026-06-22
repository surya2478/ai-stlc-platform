# STLC Platform — Security Audit Report

**Audit Date:** June 16, 2026
**Auditor:** Senior Application Security Architect
**Platform:** AI-Powered STLC Platform
**Standards:** OWASP Top 10 2025, OWASP API Security Top 10 2023, OWASP ASVS 5.0.0
**Classification:** Confidential

---

## 1. Executive Summary

This report presents the findings of a comprehensive security audit of the AI-powered STLC (Software Test Lifecycle) platform. The platform consists of a Python/FastAPI backend, a Next.js frontend, PostgreSQL database, Redis cache, and Celery task queue, with integrations to Jira, multiple LLM providers (OpenAI, Anthropic, Cerebras, Groq, Google Gemini, Ollama), and GitHub.

The audit identified **70 security findings** across all layers: 6 Critical, 13 High, 28 Medium, and 18 Low severity issues, alongside 5 informational observations. The platform has a solid RBAC foundation and good file upload hygiene, but suffers from critical authentication weaknesses, exposed secrets, missing infrastructure hardening, and absent security headers.

**Overall Security Score: 3.5 / 10**

The score reflects the presence of multiple critical vulnerabilities that could allow unauthenticated admin access (hardcoded SSO credentials, exposed dev credentials), trivially forgeable JWT tokens (weak/placeholder secret key), exposed API keys in the environment file, and the use of a JWT library with known CVEs.

---

## 2. Overall Security Rating

| Category | Rating | Notes |
|---|---|---|
| Authentication | **Poor** | Default secret key, no brute-force protection, no token revocation, 24h JWT lifetime |
| Authorization | **Good** | Comprehensive RBAC with project-level isolation, but client-side bypasses exist |
| API Security | **Fair** | No rate limiting, API docs exposed in prod, excessive data exposure in some endpoints |
| Data Security | **Fair** | ORM used consistently but some raw SQL, GitHub PAT stored in plaintext |
| File Upload | **Good** | Magic-byte validation, extension checks, UUID filenames, size limits |
| LLM/AI Security | **Fair** | Output schema validation present, but prompt injection protections are minimal |
| Secrets Management | **Critical** | Real API keys in .env, placeholder secret key, credentials in alembic.ini |
| Frontend Security | **Poor** | No route protection, no security headers, tokens in localStorage, hardcoded admin creds |
| Infrastructure | **Poor** | No HTTPS, containers run as root, Redis unauthenticated, ports exposed |
| Audit Logging | **Fair** | Business entity approvals logged, but security events (login, auth failures) are not |

---

## 3. Key Risks Identified

1. **Unauthenticated admin access** via hardcoded SSO simulation credentials and NEXT_PUBLIC dev auth variables
2. **JWT token forgery** due to weak/placeholder APP_SECRET_KEY that passes production startup validation
3. **Exposed LLM API keys** (Cerebras, Groq) in the .env file with evidence of prior key compromise
4. **Known CVEs in JWT library** (python-jose 3.3.0) including ECDSA signature bypass
5. **No rate limiting** on any endpoint, including login and registration
6. **Unauthenticated Redis** exposed on port 6379 enabling task queue manipulation
7. **No HTTPS** configuration — all credentials transmitted in cleartext
8. **No security headers** on either frontend or backend
9. **Open user registration** without email verification, CAPTCHA, or rate limiting
10. **Server-side path traversal** via arbitrary local_path in code analysis endpoint

---

## 4. Critical Issues

### SEC-001: Hardcoded Admin Credentials in SSO Simulation

| Field | Value |
|---|---|
| **Finding ID** | SEC-001 |
| **Title** | Hardcoded Admin Credentials in SSO Login Simulation |
| **Severity** | Critical |
| **Affected Area** | Frontend Authentication |
| **Affected Files** | `frontend/src/app/login/page.tsx` (lines 400-402) |
| **Description** | The SSO login buttons (Okta, Azure AD, Ping Identity) execute a "handshake simulation" that authenticates with hardcoded credentials `admin@stlc.local` / `admin-password`. Any user clicking an SSO button gains admin access without identity verification. |
| **Evidence from Code** | `const response = await authApi.login("admin@stlc.local", "admin-password");` |
| **Business Impact** | Complete authentication bypass. Any visitor can gain full admin access to the platform. |
| **Technical Impact** | Full platform compromise including access to all projects, requirements, test cases, Jira integration, LLM settings, and user management. |
| **OWASP / ASVS Mapping** | OWASP Top 10 2025 A07 - Identification and Authentication Failures; ASVS V2.2 |
| **Recommended Fix** | Remove SSO simulation entirely. Implement real OIDC/SAML flows. If dev simulation needed, gate behind `NODE_ENV === 'development'` and never include in production builds. |
| **Implementation Complexity** | Medium |
| **Regression Risk** | Low — SSO buttons currently non-functional for real SSO |
| **Suggested Test Cases** | Verify SSO buttons do not authenticate with hardcoded credentials; verify production bundle does not contain admin credentials |
| **Priority** | P0 — Immediate |

### SEC-002: Dev Authentication Credentials Exposed via NEXT_PUBLIC Variables

| Field | Value |
|---|---|
| **Finding ID** | SEC-002 |
| **Title** | Dev Auth Credentials Inlined in Client-Side JavaScript Bundle |
| **Severity** | Critical |
| **Affected Area** | Frontend Authentication |
| **Affected Files** | `frontend/src/lib/api.ts` (lines 11-12, 51-78) |
| **Description** | `NEXT_PUBLIC_DEV_AUTH_EMAIL` and `NEXT_PUBLIC_DEV_AUTH_PASSWORD` are inlined into the client JavaScript bundle at build time. If set during a production build, every visitor's browser receives the credentials and the auto-login mechanism authenticates them automatically. |
| **Evidence from Code** | `const DEV_AUTH_EMAIL = process.env.NEXT_PUBLIC_DEV_AUTH_EMAIL ?? "";` / `const DEV_AUTH_PASSWORD = process.env.NEXT_PUBLIC_DEV_AUTH_PASSWORD ?? "";` |
| **Business Impact** | Automatic unauthenticated access to the platform for all visitors. |
| **Technical Impact** | Credential exposure in client-side JavaScript, automatic login bypass. |
| **OWASP / ASVS Mapping** | OWASP Top 10 2025 A07; OWASP API Security 2023 API2; ASVS V2.10 |
| **Recommended Fix** | Never use `NEXT_PUBLIC_` for credentials. Move dev-auth to server-side middleware. Add build-time checks to block production builds when these variables are set. |
| **Implementation Complexity** | Low |
| **Regression Risk** | Low |
| **Suggested Test Cases** | Verify production JS bundle does not contain dev credentials; verify auto-login does not trigger in production |
| **Priority** | P0 — Immediate |

### SEC-003: Weak/Placeholder APP_SECRET_KEY in Production

| Field | Value |
|---|---|
| **Finding ID** | SEC-003 |
| **Title** | JWT Signing Key Is a Placeholder String That Passes Production Validation |
| **Severity** | Critical |
| **Affected Area** | Authentication, Cryptography |
| **Affected Files** | `.env` (line 17), `backend/app/config.py` (line 25), `backend/app/core/startup_checks.py` (line 18) |
| **Description** | The `.env` file sets `APP_SECRET_KEY=REPLACE_WITH_NEW_SECRET_python_secrets_token_hex_32` with `APP_ENV=production`. The startup check only blocks the literal string `"change-me"`, so this placeholder passes. The key is used for JWT signing and Fernet encryption of Jira credentials. |
| **Evidence from Code** | `app_secret_key: str = Field(default="change-me", min_length=8)` / Startup check: `if settings.app_secret_key == "change-me":` |
| **Business Impact** | Any attacker who reads this placeholder can forge JWT tokens for any user, including superadmins, and decrypt stored Jira API tokens. |
| **Technical Impact** | Complete authentication bypass via JWT forgery. Decryption of all stored Jira credentials. |
| **OWASP / ASVS Mapping** | OWASP Top 10 2025 A02 - Cryptographic Failures; OWASP API Security 2023 API2; ASVS V2.10.1 |
| **Recommended Fix** | Generate a proper 64-character hex key: `python -c "import secrets; print(secrets.token_hex(32))"`. Update startup check to validate minimum 32-character length and block known placeholders. |
| **Implementation Complexity** | Low |
| **Regression Risk** | Low — requires .env update |
| **Suggested Test Cases** | Verify app refuses to start with placeholder keys in production; verify JWT signed with old key is rejected after key rotation |
| **Priority** | P0 — Immediate |

### SEC-004: Real LLM API Keys Exposed in .env File

| Field | Value |
|---|---|
| **Finding ID** | SEC-004 |
| **Title** | Real Cerebras and Groq API Keys Present in .env File |
| **Severity** | Critical |
| **Affected Area** | Secrets Management |
| **Affected Files** | `.env` (lines 46, 52) |
| **Description** | Production API keys for Cerebras (`csk-mnh6xkr...`) and Groq (`gsk_dJDZ5...`) are stored in the `.env` file. A comment on line 45 acknowledges a prior key exposure: "Previous key was exposed. Generate a new one now." — yet real keys remain. |
| **Evidence from Code** | `CEREBRAS_API_KEY=csk-mnh6xkrr3km8hexyme3k2m48he5xnhye5vdfhp35c3kcnpn6` / `GROQ_API_KEY=gsk_dJDZ5aAGs4WVQ3gQUR8UWGdyb3FY...` |
| **Business Impact** | Financial exposure from unauthorized API usage. Potential use of compromised keys for malicious LLM queries. |
| **Technical Impact** | Direct access to LLM provider accounts. Ability to exhaust API quotas. |
| **OWASP / ASVS Mapping** | OWASP Top 10 2025 A07; ASVS V8.3.1 |
| **Recommended Fix** | Rotate both keys immediately. Move to a secrets manager (AWS Secrets Manager, HashiCorp Vault). Never store real keys in files that could be version-controlled. |
| **Implementation Complexity** | Low |
| **Regression Risk** | None — keys rotate transparently |
| **Suggested Test Cases** | Verify .env.example contains only placeholders; verify git history does not contain real API keys |
| **Priority** | P0 — Immediate |

### SEC-005: Open User Registration Without Protection

| Field | Value |
|---|---|
| **Finding ID** | SEC-005 |
| **Title** | Unauthenticated User Registration Endpoint Without Rate Limiting or Verification |
| **Severity** | Critical |
| **Affected Area** | Authentication, API Security |
| **Affected Files** | `backend/app/api/v1/endpoints/users.py` (lines 44-57) |
| **Description** | The `/register` endpoint requires no authentication, has no rate limiting, no CAPTCHA, and no email verification. Any anonymous user can create unlimited accounts. New accounts receive `role="qa_engineer"` which can be assigned to projects. |
| **Evidence from Code** | `@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED) async def register(data: UserCreate, db: DBSession):` |
| **Business Impact** | Mass account creation for spam/abuse. Potential unauthorized access to projects through membership assignment. |
| **Technical Impact** | Database bloat, resource exhaustion, potential for credential stuffing via account enumeration. |
| **OWASP / ASVS Mapping** | OWASP API Security 2023 API2; ASVS V2.5.1 |
| **Recommended Fix** | Add rate limiting, require email verification, or restrict to admin-invite-only registration. Add CAPTCHA for public registration. |
| **Implementation Complexity** | Medium |
| **Regression Risk** | Medium — changes user onboarding flow |
| **Suggested Test Cases** | Verify rate limiting blocks rapid registration attempts; verify email verification is required |
| **Priority** | P0 — Immediate |

### SEC-006: Vulnerable JWT Library (python-jose 3.3.0)

| Field | Value |
|---|---|
| **Finding ID** | SEC-006 |
| **Title** | JWT Library Has Known CVEs Including Signature Bypass |
| **Severity** | Critical |
| **Affected Area** | Authentication, Dependencies |
| **Affected Files** | `backend/requirements.txt` (line 19), `backend/app/core/security.py` |
| **Description** | `python-jose[cryptography]==3.3.0` has CVE-2024-33663 (ECDSA signature bypass) and CVE-2024-33664 (denial of service via JWE). The library is unmaintained. |
| **Evidence from Code** | `python-jose[cryptography]==3.3.0` |
| **Business Impact** | Potential JWT signature bypass allowing token forgery. |
| **Technical Impact** | Authentication bypass, denial of service. |
| **OWASP / ASVS Mapping** | OWASP Top 10 2025 A06 - Vulnerable and Outdated Components |
| **Recommended Fix** | Replace with `PyJWT>=2.9.0` (actively maintained) or `joserfc`. Update all import statements. |
| **Implementation Complexity** | Medium |
| **Regression Risk** | Medium — requires updating JWT creation/verification code |
| **Suggested Test Cases** | Verify all JWT operations work with new library; verify token signatures are validated correctly |
| **Priority** | P0 — Immediate |

---

## 5. High-Risk Issues

### SEC-007: No Brute-Force Protection on Login

| Field | Value |
|---|---|
| **Finding ID** | SEC-007 |
| **Title** | Login Endpoint Has No Rate Limiting or Account Lockout |
| **Severity** | High |
| **Affected Area** | Authentication |
| **Affected Files** | `backend/app/api/v1/endpoints/users.py` (lines 112-140) |
| **Description** | The `/token` login endpoint allows unlimited password attempts with no rate limiting, account lockout, or progressive delays. |
| **OWASP / ASVS Mapping** | OWASP API Security 2023 API2; ASVS V2.2.1 |
| **Recommended Fix** | Add rate limiting per IP (e.g., 5 attempts/minute) and per account (e.g., lockout after 10 failures). Use `slowapi` for FastAPI. |
| **Priority** | P1 |

### SEC-008: Excessive JWT Token Lifetime (24 Hours) with No Revocation

| Field | Value |
|---|---|
| **Finding ID** | SEC-008 |
| **Title** | JWT Tokens Valid for 24 Hours with No Revocation Mechanism |
| **Severity** | High |
| **Affected Area** | Authentication, Session Management |
| **Affected Files** | `backend/app/core/security.py` (line 19), `backend/app/api/v1/endpoints/users.py` |
| **Description** | Access tokens are valid for 24 hours. There is no refresh token, no token blocklist, no `/logout` endpoint, and no mechanism to invalidate tokens when a user changes password or is deactivated. |
| **OWASP / ASVS Mapping** | OWASP API Security 2023 API2; ASVS V3.3.1, V3.5.3 |
| **Recommended Fix** | Reduce to 15-30 minutes. Implement refresh token rotation. Add server-side token blocklist (Redis-backed). Check `is_active` status on every request. |
| **Priority** | P1 |

### SEC-009: JWT Token Stored in localStorage

| Field | Value |
|---|---|
| **Finding ID** | SEC-009 |
| **Title** | JWT Access Token Stored in localStorage Accessible to XSS |
| **Severity** | High |
| **Affected Area** | Frontend Security, Session Management |
| **Affected Files** | `frontend/src/lib/api.ts` (lines 10, 70, 85, 193) |
| **Description** | The JWT access token is stored in `localStorage` which is accessible to any JavaScript running on the same origin. Any XSS vulnerability would allow token exfiltration. |
| **OWASP / ASVS Mapping** | OWASP Top 10 2025 A05; ASVS V3.4.1 |
| **Recommended Fix** | Store JWT in `httpOnly`, `Secure`, `SameSite=Strict` cookie set by the server. |
| **Priority** | P1 |

### SEC-010: No Protected Route Middleware

| Field | Value |
|---|---|
| **Finding ID** | SEC-010 |
| **Title** | All Frontend Pages Accessible Without Authentication |
| **Severity** | High |
| **Affected Area** | Frontend Authorization |
| **Affected Files** | All page files under `frontend/src/app/` |
| **Description** | No Next.js middleware or route guard validates authentication before rendering pages. All pages render fully; the 401 interceptor only fires after an API call fails, meaning page UI loads before any auth check. |
| **OWASP / ASVS Mapping** | OWASP Top 10 2025 A01 - Broken Access Control; ASVS V4.1.1 |
| **Recommended Fix** | Implement `middleware.ts` at the project root that validates the auth token server-side and redirects unauthenticated requests to `/login`. |
| **Priority** | P1 |

### SEC-011: Missing Security Headers (Frontend and Backend)

| Field | Value |
|---|---|
| **Finding ID** | SEC-011 |
| **Title** | No Security Headers Configured on Either Frontend or Backend |
| **Severity** | High |
| **Affected Area** | Infrastructure, Frontend |
| **Affected Files** | `frontend/next.config.js`, `backend/app/main.py` |
| **Description** | No CSP, X-Content-Type-Options, X-Frame-Options, HSTS, Referrer-Policy, or Permissions-Policy headers are set. This enables clickjacking, MIME sniffing, and XSS exploitation. |
| **OWASP / ASVS Mapping** | OWASP Top 10 2025 A05; ASVS V14.4.3 |
| **Recommended Fix** | Add security headers middleware to FastAPI and `headers()` function to `next.config.js`. |
| **Priority** | P1 |

### SEC-012: GitHub Personal Access Token Stored in Plaintext in Database

| Field | Value |
|---|---|
| **Finding ID** | SEC-012 |
| **Title** | GitHub PAT Persisted in agent_runs.input_data Column |
| **Severity** | High |
| **Affected Area** | Secrets Management, Data Security |
| **Affected Files** | `backend/app/api/v1/endpoints/requirements.py` (lines 538-546) |
| **Description** | The user's GitHub Personal Access Token is stored in plaintext in the `agent_runs.input_data` JSON column. Anyone with audit log access can read it. |
| **OWASP / ASVS Mapping** | OWASP API Security 2023 API3; ASVS V8.3.1 |
| **Recommended Fix** | Never persist the token. Redact from `input_data` before saving. Pass to worker via encrypted ephemeral channel. |
| **Priority** | P1 |

### SEC-013: Arbitrary Path Traversal in Code Analysis Endpoint

| Field | Value |
|---|---|
| **Finding ID** | SEC-013 |
| **Title** | Code Analysis Accepts Arbitrary Server Filesystem Paths |
| **Severity** | High |
| **Affected Area** | API Security, File System |
| **Affected Files** | `backend/app/api/v1/endpoints/requirements.py` (lines 516-527) |
| **Description** | The code-analysis endpoint accepts an arbitrary `local_path` from the user with only `os.path.exists()` and `os.path.isdir()` checks. No path restriction to allowed directories. An attacker could read any directory on the server. |
| **OWASP / ASVS Mapping** | OWASP API Security 2023 API5; ASVS V12.3.1 |
| **Recommended Fix** | Validate `local_path` with `os.path.realpath()` and check it starts with an allowed base directory from configuration. |
| **Priority** | P1 |

### SEC-014: Unauthenticated Redis with Exposed Port

| Field | Value |
|---|---|
| **Finding ID** | SEC-014 |
| **Title** | Redis Has No Authentication and Port Exposed to Host |
| **Severity** | High |
| **Affected Area** | Infrastructure |
| **Affected Files** | `docker-compose.yml` (lines 22-35), `.env` (line 13) |
| **Description** | Redis runs without `--requirepass` and port 6379 is exposed to the host network. Any local process can read/write cache data and manipulate Celery task queues. |
| **OWASP / ASVS Mapping** | OWASP Top 10 2025 A07; A05 |
| **Recommended Fix** | Add `--requirepass <strong-password>` to Redis command. Update `REDIS_URL`. Remove or restrict port mapping. |
| **Priority** | P1 |

### SEC-015: Default Database Credentials (postgres:postgres)

| Field | Value |
|---|---|
| **Finding ID** | SEC-015 |
| **Title** | Production Database Uses Default PostgreSQL Superuser Credentials |
| **Severity** | High |
| **Affected Area** | Infrastructure, Secrets |
| **Affected Files** | `.env` (line 10), `docker-compose.yml` (lines 9, 46) |
| **Description** | `DATABASE_URL=postgresql://postgres:postgres@db:5432/stlc_agents` uses default superuser credentials. Port 5432 is exposed to the host. |
| **OWASP / ASVS Mapping** | OWASP Top 10 2025 A07 |
| **Recommended Fix** | Create a dedicated application user with minimal privileges and a strong random password. Restrict port access. |
| **Priority** | P1 |

### SEC-016: Client-Side Authorization Bypass

| Field | Value |
|---|---|
| **Finding ID** | SEC-016 |
| **Title** | Admin UI Gated by Modifiable localStorage Role Data |
| **Severity** | High |
| **Affected Area** | Frontend Authorization |
| **Affected Files** | `frontend/src/app/users/page.tsx` (lines 57-62), `frontend/src/lib/api.ts` (lines 172-180) |
| **Description** | The auth profile including `global_role` is stored in localStorage and used for client-side admin feature gating. Users can modify localStorage to show admin UI, exposing admin endpoints and functionality. |
| **OWASP / ASVS Mapping** | OWASP Top 10 2025 A01 |
| **Recommended Fix** | Fetch roles from server on each page load. Treat localStorage role data as display hints only. |
| **Priority** | P1 |

### SEC-017: No CSRF Protection

| Field | Value |
|---|---|
| **Finding ID** | SEC-017 |
| **Title** | No CSRF Token Mechanism |
| **Severity** | High |
| **Affected Area** | Frontend Security |
| **Affected Files** | `frontend/src/lib/api.ts`, `frontend/next.config.js` |
| **Description** | No CSRF token is used. The login endpoint uses `application/x-www-form-urlencoded` which is susceptible to cross-origin form submission. |
| **OWASP / ASVS Mapping** | OWASP Top 10 2025 A01; ASVS V4.2.2 |
| **Recommended Fix** | Implement double-submit cookie pattern or synchronizer token pattern. |
| **Priority** | P1 |

### SEC-018: No HTTPS Configuration

| Field | Value |
|---|---|
| **Finding ID** | SEC-018 |
| **Title** | All Communication Over Plain HTTP |
| **Severity** | High |
| **Affected Area** | Infrastructure |
| **Affected Files** | `.env` (lines 20, 98), `docker-compose.yml` |
| **Description** | All URLs use HTTP. No TLS termination proxy is configured. JWT tokens, API keys, and credentials transit in cleartext. |
| **OWASP / ASVS Mapping** | OWASP Top 10 2025 A02; ASVS V9.1.1 |
| **Recommended Fix** | Add a reverse proxy (nginx/traefik/caddy) with TLS certificates. Update all URLs to HTTPS. |
| **Priority** | P1 |

### SEC-019: Swagger UI Exposed in Production

| Field | Value |
|---|---|
| **Finding ID** | SEC-019 |
| **Title** | OpenAPI Documentation Accessible Without Authentication in Production |
| **Severity** | High |
| **Affected Area** | API Security |
| **Affected Files** | `backend/app/main.py` (lines 92-94) |
| **Description** | `/docs` (Swagger UI) and `/redoc` are enabled unconditionally, exposing the full API schema to unauthenticated users. |
| **OWASP / ASVS Mapping** | OWASP API Security 2023 API8 |
| **Recommended Fix** | Disable in production: `docs_url=None if settings.app_env == "production" else "/docs"`. |
| **Priority** | P1 |

---

## 6. Medium-Risk Issues

### SEC-020: No Rate Limiting on Any API Endpoint
- **Severity:** Medium | **OWASP:** API4:2023 | **Files:** All endpoints
- No `slowapi` or rate limiting middleware. Enables brute-force, DoS, and LLM cost exhaustion.
- **Fix:** Add `slowapi` middleware with per-endpoint limits.

### SEC-021: CORS Allows All Methods and Headers
- **Severity:** Medium | **OWASP:** API8:2023 | **Files:** `backend/app/main.py` (lines 97-103)
- `allow_methods=["*"]` and `allow_headers=["*"]` with `allow_credentials=True`.
- **Fix:** Restrict to specific methods and headers.

### SEC-022: Debug Mode Defaults to True
- **Severity:** Medium | **OWASP:** API8:2023 | **Files:** `backend/app/config.py` (line 24)
- `app_debug: bool = True` enables SQL echo and verbose logging.
- **Fix:** Default to `False`.

### SEC-023: Webhook Signature Bypassed When Secret Empty
- **Severity:** Medium | **OWASP:** API2:2023 | **Files:** `backend/app/services/jira_service.py` (lines 170-177)
- `if not secret: return True` accepts all webhooks when no secret configured.
- **Fix:** Reject webhook requests when secret is not configured.

### SEC-024: No Password Complexity Enforcement
- **Severity:** Medium | **OWASP:** API2:2023 | **Files:** `backend/app/core/security.py`, `users.py`
- No minimum length, character diversity, or common password checks.
- **Fix:** Enforce 12+ characters, check against common password lists.

### SEC-025: No Audit Logging for Security Events
- **Severity:** Medium | **OWASP:** API9:2023 | **Files:** `users.py`, `deps.py`, `security.py`
- Login attempts, failures, user creation, password changes not logged.
- **Fix:** Add structured security event logging.

### SEC-026: Internal Server Path Exposed via Settings Endpoint
- **Severity:** Medium | **OWASP:** API3:2023 | **Files:** `backend/app/api/v1/endpoints/settings.py` (lines 32, 59)
- Returns `file_storage_path`, `ollama_base_url`, `jira_email` to authenticated users.
- **Fix:** Remove infrastructure details from response.

### SEC-027: Health/Pool Endpoint Exposes DB Internals Without Auth
- **Severity:** Medium | **OWASP:** API8:2023 | **Files:** `backend/app/api/v1/endpoints/health.py` (lines 24-28)
- Pool size, overflow count exposed unauthenticated.
- **Fix:** Require auth for pool stats.

### SEC-028: SQL Echo Enabled in Debug Mode
- **Severity:** Medium | **OWASP:** API8:2023 | **Files:** `backend/app/database.py` (line 64)
- Sensitive data (passwords, tokens) may appear in SQL logs.
- **Fix:** Never enable SQL echo in production.

### SEC-029: Error Detail Leakage in Dev User Seeding
- **Severity:** Medium | **OWASP:** API8:2023 | **Files:** `backend/app/api/deps.py` (lines 96-98)
- Raw exception details in HTTP responses.
- **Fix:** Return generic errors; log details server-side.

### SEC-030: Docker Containers Run as Root
- **Severity:** Medium | **OWASP:** A05 | **Files:** Both Dockerfiles
- Neither Dockerfile has a `USER` directive.
- **Fix:** Add non-root user.

### SEC-031: Hardcoded Credentials in alembic.ini
- **Severity:** Medium | **OWASP:** A02 | **Files:** `backend/alembic.ini` (line 5)
- `sqlalchemy.url = postgresql://user:password@db:5432/stlc_agents` in version-controlled file.
- **Fix:** Read from `DATABASE_URL` env var in `env.py`.

### SEC-032: Jira Encryption Key Derived via Simple SHA-256
- **Severity:** Medium | **OWASP:** A02 | **Files:** `backend/app/services/jira_service.py` (lines 39-41)
- Single SHA-256 hash, no salt, no KDF stretching.
- **Fix:** Use HKDF or PBKDF2 with salt.

### SEC-033: Startup Validation Only Checks One Literal Secret Value
- **Severity:** Medium | **OWASP:** A05 | **Files:** `backend/app/core/startup_checks.py` (line 18)
- Only checks for `"change-me"`, not other placeholders or weak keys.
- **Fix:** Check minimum length, entropy, and blocklist of common values.

### SEC-034: Dev Seed User Backdoor Mechanism Exists
- **Severity:** Medium | **OWASP:** A07 | **Files:** `.env` (lines 101-104), `backend/app/api/deps.py`
- `DEV_SEED_USER_ENABLED` can be flipped to create a backdoor account in production.
- **Fix:** Block in production startup validation.

### SEC-035: Vulnerable Next.js Version (14.2.3)
- **Severity:** Medium | **OWASP:** A06 | **Files:** `frontend/package.json` (line 12)
- Known CVEs: CVE-2024-46982, CVE-2024-51479, CVE-2025-29927.
- **Fix:** Update to latest 14.2.x patch or migrate to 15.x.

### SEC-036: External URLs Rendered Without Protocol Validation
- **Severity:** Medium | **OWASP:** A03 | **Files:** `frontend/src/app/test-cases/page.tsx` (lines 687-748)
- `jira_url`, `external_tc_url`, `evidence_url` rendered as `href` without validating protocol. `javascript:` URLs could execute code.
- **Fix:** Create `isSafeUrl()` utility that only allows `https://` and `http://`.

### SEC-037: Console Logging of Auth Errors with Sensitive Context
- **Severity:** Medium | **OWASP:** A09 | **Files:** `frontend/src/lib/api.ts` (lines 90, 129)
- Full error objects logged to browser console.
- **Fix:** Strip console logging in production builds.

### SEC-038: No Input Sanitization on Form Fields
- **Severity:** Medium | **OWASP:** A03 | **Files:** Multiple frontend pages
- Form validation checks presence only, not HTML/script injection.
- **Fix:** Reject HTML tags in text inputs; sanitize with DOMPurify where HTML rendering needed.

### SEC-039: Error Messages Leak Backend Infrastructure Details
- **Severity:** Medium | **OWASP:** A04 | **Files:** `frontend/src/lib/api.ts`, multiple pages
- Error messages expose backend URL, Docker Compose usage, dev auth instructions.
- **Fix:** Display generic messages in production.

### SEC-040: Logout Does Not Invalidate Server-Side Token
- **Severity:** Medium | **OWASP:** A07 | **Files:** `frontend/src/lib/api.ts` (lines 197-200)
- Logout only clears localStorage, no server-side revocation.
- **Fix:** Add `/logout` endpoint with token blocklist.

### SEC-041: Backend Runs with --reload in Docker
- **Severity:** Medium | **OWASP:** A05 | **Files:** `docker-compose.yml` (line 59)
- Auto-reload in production with source mounted as volume.
- **Fix:** Remove `--reload`, separate dev/prod compose files.

### SEC-042: Frontend Runs in Dev Mode in Docker
- **Severity:** Medium | **OWASP:** A05 | **Files:** `docker-compose.yml` (line 103), `frontend/Dockerfile` (line 14)
- `npm run dev` exposes source maps, error details, debug endpoints.
- **Fix:** Use `npm run build && npm run start` for production.

### SEC-043: Login Form Rate Limiting Absent
- **Severity:** Medium | **OWASP:** A07 | **Files:** `frontend/src/app/login/page.tsx` (lines 47-65)
- Unlimited login attempts from the UI with no progressive delays or CAPTCHA.
- **Fix:** Add progressive delays and CAPTCHA after failed attempts.

### SEC-044: Gemini API Key in URL Query Parameter
- **Severity:** Medium | **OWASP:** ASVS V8.3.1 | **Files:** `backend/app/llm/provider.py` (lines 489, 519)
- `params={"key": self.api_key}` puts API key in URL, logged by proxies.
- **Fix:** Use `x-goog-api-key` header.

### SEC-045: GitHub Token Handled in Frontend State
- **Severity:** Medium | **OWASP:** A07 | **Files:** `frontend/src/app/requirements/page.tsx` (lines 188, 438, 1322)
- PAT held in React state and transmitted to backend.
- **Fix:** Move token configuration server-side.

### SEC-046: Jira API Token Handled in Frontend Form
- **Severity:** Medium | **OWASP:** A07 | **Files:** `frontend/src/app/requirements/page.tsx` (lines 139, 1507)
- Similar to SEC-045 for Jira tokens.
- **Fix:** Server-side configuration.

### SEC-047: Open Redirect Potential in 401 Handler
- **Severity:** Medium | **OWASP:** A01 | **Files:** `frontend/src/lib/api.ts` (lines 136-138)
- Currently safe but if returnTo parameter added, no validation exists.
- **Fix:** Validate return URLs against application origin.

---

## 7. Low-Risk Issues

### SEC-048: No Password Hashing Cost Factor Configuration
- **Files:** `backend/app/core/security.py` (line 24) | Uses default bcrypt rounds, not configurable.

### SEC-049: Missing JWT ID (`jti`) Claim
- **Files:** `backend/app/core/security.py` (lines 40-46) | No unique token ID for revocation support.

### SEC-050: Root Health Endpoint Leaks Environment Info
- **Files:** `backend/app/main.py` (lines 109-116) | Returns `env` field without auth.

### SEC-051: Jira Error Messages May Leak Internal Details
- **Files:** `backend/app/services/jira_service.py` (lines 880-892) | Returns raw Jira errors.

### SEC-052: Undefined Variable DEV_USER_EMAIL (Bug)
- **Files:** `backend/app/api/deps.py` (line 90) | Should be `settings.dev_seed_user_email`.

### SEC-053: User Email Persisted in localStorage (Remember Me)
- **Files:** `frontend/src/app/login/page.tsx` (lines 43-44) | Leaks identity on shared devices.

### SEC-054: Sidebar/Column State Leaks Project IDs
- **Files:** `frontend/src/components/layout/Sidebar.tsx`, `test-cases/page.tsx` | localStorage keys include project IDs.

### SEC-055: File Upload Without Client-Side Validation
- **Files:** `frontend/src/app/requirements/page.tsx` (lines 1146-1148) | No JS-level size/type enforcement.

### SEC-056: Axios Version May Have SSRF Vulnerability
- **Files:** `frontend/package.json` (line 31) | `axios ^1.7.2`, CVE-2024-39338 in <1.7.4.

### SEC-057: Unsafe JSON.parse of localStorage Without Schema Validation
- **Files:** `frontend/src/lib/api.ts` (lines 175-178) | `as` cast provides no runtime safety.

### SEC-058: .gitignore Missing Certificate/Key Patterns
- **Files:** `.gitignore` | No patterns for `*.pem`, `*.key`, `*.p12`, `*.pfx`.

### SEC-059: API Docs Exposed in Production (duplicate — already in SEC-019)
- Covered by SEC-019.

### SEC-060: Source Code Mounted as Volume in Production Containers
- **Files:** `docker-compose.yml` (lines 49, 96) | Combined with `--reload`, enables code injection.

---

## 8. Positive Security Observations

1. **Bcrypt Password Hashing** — Strong password hashing using bcrypt directly (not deprecated passlib).

2. **Comprehensive RBAC** — Fine-grained role-based access control with 20+ permissions, project-level isolation, and consistent enforcement via dependency injection across all endpoints.

3. **Project Isolation** — Cross-project access consistently validated. Entity lookups verify project ownership before returning data.

4. **Jira Token Encryption** — Jira API tokens encrypted at rest using Fernet symmetric encryption derived from the app secret key.

5. **File Upload Security** — Content-type validation, magic byte signature verification, file extension allowlist, size limits (25MB), filename sanitization, UUID-based storage filenames.

6. **SSRF Protection** — URL analysis endpoint validates URL safety before accepting, guarding against server-side request forgery.

7. **Webhook Idempotency** — SHA-256 event keys prevent duplicate Jira webhook processing.

8. **HMAC Signature Verification** — Timing-safe `hmac.compare_digest()` for Jira webhook signatures (when configured).

9. **Soft Deletes** — Requirements use `is_deleted` flag preserving audit trail and traceability.

10. **LLM Circuit Breaker** — LLM provider includes circuit breaker with configurable failure thresholds and reset timers.

11. **LLM Output Schema Validation** — `structured.py` validates LLM outputs against Pydantic schemas before use.

12. **Pydantic-Settings Configuration** — Type-safe configuration from environment variables with validation.

13. **Approval Workflows** — Multi-step approval workflows with audit trails via `ApprovalAction` records.

14. **GZip Compression** — Response compression enabled.

---

## 9. OWASP Mapping

### OWASP Top 10 2025 Mapping

| OWASP Category | Findings | Severity Distribution |
|---|---|---|
| A01 - Broken Access Control | SEC-010, SEC-016, SEC-017, SEC-047 | 3 High, 1 Medium |
| A02 - Cryptographic Failures | SEC-003, SEC-004, SEC-018, SEC-031, SEC-032 | 3 Critical/High, 2 Medium |
| A03 - Injection | SEC-036, SEC-038 | 2 Medium |
| A04 - Insecure Design | SEC-039 | 1 Medium |
| A05 - Security Misconfiguration | SEC-011, SEC-019, SEC-021, SEC-022, SEC-027, SEC-030, SEC-041, SEC-042 | 2 High, 6 Medium |
| A06 - Vulnerable Components | SEC-006, SEC-035, SEC-056 | 1 Critical, 2 Medium/Low |
| A07 - Identification & Auth Failures | SEC-001, SEC-002, SEC-005, SEC-007, SEC-008, SEC-014, SEC-015 | 4 Critical, 3 High |
| A08 - Software & Data Integrity | SEC-057 | 1 Low |
| A09 - Security Logging Failures | SEC-025, SEC-037 | 2 Medium |

### OWASP API Security Top 10 2023 Mapping

| OWASP API Category | Findings |
|---|---|
| API1 - Broken Object Level Authorization | SEC-013 |
| API2 - Broken Authentication | SEC-001, SEC-002, SEC-003, SEC-005, SEC-007, SEC-008, SEC-023 |
| API3 - Broken Object Property Level Authorization | SEC-012, SEC-026 |
| API4 - Unrestricted Resource Consumption | SEC-020 |
| API5 - Broken Function Level Authorization | SEC-013 |
| API8 - Security Misconfiguration | SEC-019, SEC-021, SEC-022, SEC-027, SEC-028, SEC-029 |
| API9 - Improper Inventory Management | SEC-025 |

---

## 10. AI/LLM Security Observations

| Area | Assessment |
|---|---|
| Prompt Injection Protection | **Minimal** — No explicit prompt injection guards on user-supplied requirement text or uploaded document content |
| LLM Output Validation | **Good** — Pydantic schema validation on structured outputs |
| Secret Leakage in Prompts | **Medium Risk** — LLM API keys in env vars, not in prompts, but Jira connection details and GitHub tokens could be included in agent context |
| Model Configuration Security | **Fair** — Project-level LLM settings stored in DB, but no per-project API key isolation |
| RAG Security | Not implemented |
| Document Content as Prompt Input | **Risk** — Uploaded PDF/DOCX content is passed to LLM for analysis, creating prompt injection vector |

---

## 11. Secrets and Configuration Observations

| Secret | Location | Encrypted | Status |
|---|---|---|---|
| APP_SECRET_KEY | .env | N/A | **CRITICAL** — Placeholder value |
| DATABASE_URL (password) | .env | N/A | **HIGH** — Default `postgres:postgres` |
| CEREBRAS_API_KEY | .env | No | **CRITICAL** — Real key exposed |
| GROQ_API_KEY | .env | No | **CRITICAL** — Real key exposed |
| OPENAI_API_KEY | .env | No | Placeholder |
| ANTHROPIC_API_KEY | .env | No | Placeholder |
| Jira API Token | DB (encrypted) | Yes (Fernet) | **MEDIUM** — Weak key derivation |
| GitHub PAT | DB (agent_runs.input_data) | No | **HIGH** — Plaintext in DB |
| Redis | Connection URL | N/A | **HIGH** — No authentication |

---

## 12. Immediate Action Items

1. **Rotate exposed API keys** (Cerebras, Groq) — they must be considered compromised
2. **Generate proper APP_SECRET_KEY** — 64+ hex chars, update startup validation
3. **Remove hardcoded SSO simulation** from login page
4. **Remove NEXT_PUBLIC dev auth variables** from production builds
5. **Replace python-jose** with PyJWT
6. **Set strong database credentials** — not `postgres:postgres`
7. **Add Redis authentication** — `--requirepass`
8. **Disable API docs in production** — set `docs_url=None`

---

## 13. Long-Term Recommendations

1. Implement a proper secrets management solution (AWS Secrets Manager, HashiCorp Vault)
2. Add comprehensive rate limiting across all endpoints
3. Implement refresh token rotation with short-lived access tokens (15 min)
4. Move to httpOnly cookie-based session management
5. Add Next.js middleware for route protection
6. Implement security headers on both frontend and backend
7. Add HTTPS with TLS termination proxy
8. Implement structured security audit logging
9. Add prompt injection detection for LLM inputs
10. Separate dev and production Docker configurations
11. Add dependency scanning to CI/CD pipeline
12. Implement per-project LLM API key isolation with encryption
13. Add Content Security Policy headers
14. Implement token revocation (Redis-backed blocklist)
15. Add CAPTCHA and email verification for registration

---

*End of Security Audit Report*
