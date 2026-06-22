# STLC Platform — Security Implementation Backlog

**Date:** June 16, 2026
**Version:** 1.0

---

## Backlog Table

| Priority | Security Area | Task | Finding ID | Severity | Effort | Risk Reduction | Affected Module | Phase | Status |
|---|---|---|---|---|---|---|---|---|---|
| P0 | Secrets | Rotate exposed Cerebras & Groq API keys | SEC-004 | Critical | Low | Critical | Backend Config | 1 | Pending |
| P0 | Authentication | Generate cryptographic APP_SECRET_KEY | SEC-003 | Critical | Low | Critical | Backend Core | 1 | Pending |
| P0 | Authentication | Remove hardcoded SSO simulation credentials | SEC-001 | Critical | Low | Critical | Frontend Login | 1 | Pending |
| P0 | Authentication | Remove NEXT_PUBLIC dev auth credential exposure | SEC-002 | Critical | Low | Critical | Frontend API | 1 | Pending |
| P0 | Authentication | Replace python-jose with PyJWT | SEC-006 | Critical | Medium | Critical | Backend Core | 1 | Pending |
| P0 | Authentication | Secure open registration (rate limit, password policy) | SEC-005 | Critical | Medium | High | Backend Users API | 1 | Pending |
| P1 | Authentication | Add brute-force protection to login | SEC-007 | High | Medium | High | Backend Users API | 1 | Pending |
| P1 | Session | Reduce JWT lifetime to 15min + refresh tokens | SEC-008 | High | High | High | Backend Core | 2 | Pending |
| P1 | Session | Move JWT to httpOnly cookies | SEC-009 | High | High | High | Backend/Frontend | 2 | Pending |
| P1 | Authorization | Add Next.js route protection middleware | SEC-010 | High | Medium | High | Frontend | 2 | Pending |
| P1 | Infrastructure | Add security headers (frontend + backend) | SEC-011 | High | Medium | High | Both | 2 | Pending |
| P1 | Secrets | Redact GitHub PAT from agent_runs DB | SEC-012 | High | Low | High | Backend Requirements | 3 | Pending |
| P1 | API Security | Fix path traversal in code analysis endpoint | SEC-013 | High | Low | High | Backend Requirements | 3 | Pending |
| P1 | Infrastructure | Add Redis authentication | SEC-014 | High | Low | High | Docker Config | 2 | Pending |
| P1 | Infrastructure | Set strong database credentials | SEC-015 | High | Low | High | Docker/.env | 1 | Pending |
| P1 | Authorization | Fix client-side role bypass (fetch from server) | SEC-016 | High | Medium | Medium | Frontend Users | 2 | Pending |
| P1 | Authentication | Add CSRF protection | SEC-017 | High | Medium | Medium | Frontend/Backend | 2 | Pending |
| P1 | Infrastructure | Configure HTTPS with TLS proxy | SEC-018 | High | High | High | Docker Config | 2 | Pending |
| P1 | API Security | Disable API docs in production | SEC-019 | High | Low | Medium | Backend Main | 2 | Pending |
| P2 | API Security | Add rate limiting to all endpoints | SEC-020 | Medium | Medium | High | Backend All | 4 | Pending |
| P2 | Infrastructure | Restrict CORS methods and headers | SEC-021 | Medium | Low | Medium | Backend Main | 2 | Pending |
| P2 | Configuration | Default debug mode to False | SEC-022 | Medium | Low | Medium | Backend Config | 1 | Pending |
| P2 | Integration | Fix webhook signature bypass when secret empty | SEC-023 | Medium | Low | Medium | Backend Jira | 4 | Pending |
| P2 | Authentication | Add password complexity enforcement | SEC-024 | Medium | Medium | Medium | Backend Users | 1 | Pending |
| P2 | Audit | Implement security event audit logging | SEC-025 | Medium | High | High | Backend Core | 4 | Pending |
| P2 | API Security | Remove internal paths from settings endpoint | SEC-026 | Medium | Low | Low | Backend Settings | 4 | Pending |
| P2 | API Security | Add auth to health pool endpoint | SEC-027 | Medium | Low | Low | Backend Health | 4 | Pending |
| P2 | Configuration | Disable SQL echo in production | SEC-028 | Medium | Low | Low | Backend Database | 1 | Pending |
| P2 | API Security | Sanitize error details in dev user seeding | SEC-029 | Medium | Low | Low | Backend Deps | 1 | Pending |
| P2 | Infrastructure | Add non-root users to Dockerfiles | SEC-030 | Medium | Low | Medium | Docker | 2 | Pending |
| P2 | Secrets | Remove credentials from alembic.ini | SEC-031 | Medium | Low | Low | Backend Alembic | 1 | Pending |
| P2 | Cryptography | Improve Jira token encryption (HKDF) | SEC-032 | Medium | Medium | Medium | Backend Jira | 4 | Pending |
| P2 | Configuration | Enhance startup secret key validation | SEC-033 | Medium | Low | Medium | Backend Core | 1 | Pending |
| P2 | Configuration | Block dev seed user in production | SEC-034 | Medium | Low | Medium | Backend Core | 1 | Pending |
| P2 | Dependencies | Update Next.js to latest patch | SEC-035 | Medium | Medium | Medium | Frontend | 2 | Pending |
| P2 | Frontend | Validate external URL protocols before rendering | SEC-036 | Medium | Low | Medium | Frontend Test Cases | 3 | Pending |
| P2 | Logging | Strip console auth logging in production | SEC-037 | Medium | Low | Low | Frontend API | 2 | Pending |
| P2 | Frontend | Add input sanitization on form fields | SEC-038 | Medium | Medium | Medium | Frontend All | 3 | Pending |
| P2 | Frontend | Sanitize error messages in production | SEC-039 | Medium | Low | Low | Frontend API | 2 | Pending |
| P2 | Session | Add server-side logout / token revocation | SEC-040 | Medium | Medium | Medium | Backend/Frontend | 2 | Pending |
| P2 | Infrastructure | Remove --reload from production Docker | SEC-041 | Medium | Low | Low | Docker | 2 | Pending |
| P2 | Infrastructure | Use production build for frontend in Docker | SEC-042 | Medium | Low | Low | Docker | 2 | Pending |
| P2 | Frontend | Add login rate limiting / CAPTCHA on frontend | SEC-043 | Medium | Medium | Medium | Frontend Login | 2 | Pending |
| P2 | LLM Security | Move Gemini API key to header | SEC-044 | Medium | Low | Low | Backend LLM | 3 | Pending |
| P2 | Frontend | Move GitHub token config server-side | SEC-045 | Medium | Medium | Medium | Frontend/Backend | 3 | Pending |
| P2 | Frontend | Move Jira token config server-side | SEC-046 | Medium | Medium | Medium | Frontend/Backend | 3 | Pending |
| P2 | Frontend | Validate returnTo URLs against origin | SEC-047 | Medium | Low | Low | Frontend API | 2 | Pending |
| P3 | Authentication | Make bcrypt cost factor configurable | SEC-048 | Low | Low | Low | Backend Core | 5 | Pending |
| P3 | Authentication | Add jti claim to JWT tokens | SEC-049 | Low | Low | Medium | Backend Core | 1 | Pending |
| P3 | API Security | Remove env info from root health endpoint | SEC-050 | Low | Low | Low | Backend Main | 4 | Pending |
| P3 | Integration | Sanitize Jira error messages to client | SEC-051 | Low | Low | Low | Backend Jira | 4 | Pending |
| P3 | Bug Fix | Fix DEV_USER_EMAIL undefined variable | SEC-052 | Low | Low | Low | Backend Deps | 1 | Pending |
| P3 | Frontend | Use sessionStorage for remember-me email | SEC-053 | Low | Low | Low | Frontend Login | 5 | Pending |
| P3 | Frontend | Remove project IDs from localStorage keys | SEC-054 | Low | Low | Low | Frontend | 5 | Pending |
| P3 | Frontend | Add client-side file upload validation | SEC-055 | Low | Low | Low | Frontend Requirements | 3 | Pending |
| P3 | Dependencies | Update axios to >=1.7.4 | SEC-056 | Low | Low | Low | Frontend | 2 | Pending |
| P3 | Frontend | Add Zod validation for localStorage parsing | SEC-057 | Low | Low | Low | Frontend API | 5 | Pending |
| P3 | DevOps | Add cert/key patterns to .gitignore | SEC-058 | Low | Low | Low | Config | 5 | Pending |
| P3 | Infrastructure | Remove source code volume mounts in prod | SEC-060 | Low | Low | Low | Docker | 2 | Pending |

---

## Summary by Phase

| Phase | Tasks | Critical | High | Medium | Low |
|---|---|---|---|---|---|
| Phase 1 | 16 | 6 | 2 | 6 | 2 |
| Phase 2 | 18 | 0 | 9 | 8 | 1 |
| Phase 3 | 7 | 0 | 2 | 5 | 0 |
| Phase 4 | 8 | 0 | 0 | 7 | 1 |
| Phase 5 | 6 | 0 | 0 | 0 | 6 |

## Summary by Priority

| Priority | Count | Description |
|---|---|---|
| P0 | 6 | Immediate — fix before any deployment |
| P1 | 13 | Within 1 week — essential security hardening |
| P2 | 28 | Within 2-4 weeks — defense in depth |
| P3 | 12 | Within 1-2 months — best practices |

---

*End of Security Implementation Backlog*
