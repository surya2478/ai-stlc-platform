# STLC Platform — Security Runbook

This runbook covers incident response, key rotation, and operational security procedures.
All procedures assume Docker-based deployment with the `docker-compose.prod.yml` override.

---

## 1. Incident Response

### 1.1 Suspected Account Compromise

**Indicators:** Unusual login locations in audit log, unexpected API activity, failed login spikes.

1. **Contain** — Deactivate the user account immediately:
   ```sql
   UPDATE users SET is_active = false WHERE email = '<compromised@email>';
   ```
   Or via API (requires admin token):
   ```
   PATCH /api/v1/users/{user_id}  {"is_active": false}
   ```

2. **Revoke sessions** — Revoke all tokens for the user by adding their active JTIs to the Redis blocklist. If JTIs are unknown, rotate `APP_SECRET_KEY` (see §2.1) to invalidate all tokens platform-wide.

3. **Audit** — Search audit log for the user's activity:
   ```bash
   grep '"user_id": <id>' /var/log/stlc/security.audit.log | jq .
   ```

4. **Notify** — Inform the user and your security team.

5. **Investigate** — Determine attack vector (phishing, credential stuffing, insider threat).

6. **Restore** — Re-activate account after password reset and MFA enrollment if available.

---

### 1.2 Suspected API Key / Jira Token Leak

**Indicators:** Unauthorised Jira API calls, unexpected Jira webhook activity.

1. **Rotate Jira API token immediately** in Atlassian admin.

2. **Update the encrypted credential** in the database:
   - Delete the existing `JiraConnection` record and recreate it with the new token.
   - The `encrypt_credential()` call in `jira_service.py` uses HKDF + Fernet; re-encryption happens automatically on the next `create_connection` API call.

3. **Rotate `APP_SECRET_KEY`** if the encryption key may have been exposed (see §2.1).

4. **Check Jira audit log** for any actions performed using the compromised token.

---

### 1.3 Suspected Prompt Injection

**Indicators:** `prompt_injection_detected` events in audit log, unusual LLM outputs, agent outputs that reference system internals.

1. **Identify the project and requirement** from the audit log entry (contains `project_id`, `artifact_type`, `artifact_id`).

2. **Quarantine the content** — mark the requirement / document as pending review:
   ```sql
   UPDATE requirements SET metadata_ = jsonb_set(
     COALESCE(metadata_, '{}'),
     '{quarantine}', 'true'
   ) WHERE id = <requirement_id>;
   ```

3. **Review LLM outputs** for the agent run identified in the audit event — check `agent_runs.output_data`.

4. **Delete or sanitise** the injected content and re-run the agent.

5. **Review prompt guard rules** in `backend/app/core/prompt_guard.py` and update detection patterns if the injection bypassed them.

---

### 1.4 Data Breach / Unintended Data Exposure

1. **Identify scope** — which tables, which project(s), which users could see the data.

2. **Revoke access** — deactivate affected project memberships:
   ```sql
   UPDATE project_memberships SET is_active = false WHERE project_id = <id>;
   ```

3. **Rotate secrets** (§2) and force re-authentication.

4. **Preserve evidence** — snapshot relevant database rows and audit logs before any cleanup.

5. **Notify stakeholders** per your organisation's breach notification policy (GDPR 72-hour window if applicable).

---

### 1.5 Denial of Service / Rate Limit Abuse

**Indicators:** High 429 response rate in nginx logs, worker queue depth spiking.

1. **Identify source IPs** from nginx access log:
   ```bash
   awk '{print $1}' /var/log/nginx/access.log | sort | uniq -c | sort -rn | head -20
   ```

2. **Block at nginx** — add to `nginx.prod.conf`:
   ```nginx
   deny <attacker-ip>;
   ```
   Then: `docker compose exec nginx nginx -s reload`

3. **Scale workers** if legitimate load spike:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --scale worker=8
   ```

4. **Review rate limit config** in `backend/app/core/limiter.py` and tighten per-endpoint limits if needed.

---

## 2. Key Rotation Procedures

### 2.1 Rotate APP_SECRET_KEY (JWT signing key)

**Effect:** All existing JWT tokens are immediately invalidated. All users are logged out.

1. Generate a new key:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

2. Update the secret in your secrets manager / environment.

3. Rolling restart:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d backend
   ```

4. Notify users of the forced logout (via in-app banner or email).

---

### 2.2 Rotate Jira API Token (Jira encryption key derived from APP_SECRET_KEY)

The Jira credential encryption key is derived from `APP_SECRET_KEY` via HKDF. If `APP_SECRET_KEY` rotates, previously encrypted Jira tokens become unreadable.

**Procedure when rotating APP_SECRET_KEY with active Jira connections:**

1. Before rotating, export existing plaintext tokens (requires current key):
   ```python
   from app.services.jira_service import JiraService
   plain = JiraService.decrypt_credential(encrypted_token)
   ```

2. Rotate `APP_SECRET_KEY` (§2.1).

3. Re-encrypt and update each `JiraConnection`:
   ```
   PATCH /api/v1/jira/connections/{id}  {"api_token": "<plain_token>"}
   ```
   This triggers `encrypt_credential()` with the new key.

4. Verify Jira connections via the test endpoint:
   ```
   POST /api/v1/jira/connections/{id}/test
   ```

---

### 2.3 Rotate PostgreSQL Password

1. Update password in PostgreSQL:
   ```sql
   ALTER USER stlc_prod WITH PASSWORD 'new-strong-password';
   ```

2. Update `POSTGRES_PASSWORD` and `DATABASE_URL` in secrets manager.

3. Rolling restart: `docker compose ... up -d backend worker beat`

---

### 2.4 Rotate Redis Password

1. Update in `redis.conf` or command args:
   ```
   requirepass new-redis-password
   ```

2. Update `REDIS_URL` in secrets manager.

3. Rolling restart: `docker compose ... up -d redis worker beat backend`

---

### 2.5 Rotate Jira Webhook Secret

1. Generate a new secret (min 32 chars):
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. Update `JIRA_WEBHOOK_SECRET` in secrets manager and redeploy.

3. Update the webhook URL secret in Atlassian Jira admin (Settings → System → WebHooks).

4. Verify the next incoming webhook event is accepted (check audit log for `jira_webhook_received`).

---

## 3. Vulnerability Disclosure Process

1. **Report channel** — Email `security@yourdomain.com` with subject `[SECURITY] <brief description>`.

2. **Acknowledgement** — Acknowledge receipt within 24 hours.

3. **Assessment** — Assign CVSS score and severity within 5 business days.

4. **Remediation SLAs:**
   - Critical (CVSS ≥ 9.0): patch within 24 hours
   - High (CVSS 7.0–8.9): patch within 7 days
   - Medium (CVSS 4.0–6.9): patch within 30 days
   - Low (CVSS < 4.0): patch within 90 days

5. **Disclosure** — Coordinate public disclosure with the reporter after the patch is deployed.

---

## 4. Monitoring Checklist

| Signal | Source | Alert threshold |
|---|---|---|
| Repeated auth failures | `security.audit` log — `login_failure` | > 10 in 5 min from same IP |
| Account lockouts | `security.audit` — `login_failure` with `reason=account_locked` | Any occurrence |
| Access denied spikes | `security.audit` — `access_denied` | > 20 in 1 min |
| Webhook rejections | `security.audit` — `jira_webhook_rejected` | Any `invalid_signature` |
| Prompt injection | `security.audit` — `prompt_injection_detected` | Any occurrence |
| Retention purge anomaly | `security.audit` — `retention_purge` | `deleted_count` > 10,000 |
| Worker queue depth | Celery Flower / Redis `LLEN celery` | > 500 tasks |
| Error rate | nginx / backend logs | 5xx rate > 1% over 5 min |
| DB connection pool | `/api/v1/health/pool` (authenticated) | `overflow` > 80% |

### Log aggregation setup (ELK)

Security audit events are emitted by the `security.audit` Python logger as JSON lines.
To route them to Elasticsearch:

1. Configure Logstash or Filebeat to tail `/var/log/stlc/security.audit.log` (or collect from Docker stdout using the `security.audit` logger name filter).
2. Parse with the JSON codec.
3. Index pattern: `stlc-audit-*`
4. Create Kibana saved searches for the alert thresholds above.
5. Set Kibana alerting rules → Slack/PagerDuty for Critical/High thresholds.

---

## 5. Deployment Security Checklist

Run before every production deployment:

- [ ] `APP_SECRET_KEY` is not `change-me` or any default
- [ ] `APP_ENV=production` is set
- [ ] `APP_DEBUG=false`
- [ ] `DEV_SEED_USER_ENABLED=false`
- [ ] `NEXT_PUBLIC_ENABLE_DEV_AUTH=false`
- [ ] `JIRA_WEBHOOK_SECRET` is set and ≥ 32 characters
- [ ] `JIRA_SIMULATION_MODE=false` (if Jira is active)
- [ ] TLS certificates are valid and not within 30 days of expiry
- [ ] `npm audit --audit-level=high` passes (frontend)
- [ ] `pip-audit --severity high` passes (backend)
- [ ] `bandit -r app --severity-level high` has no findings
- [ ] All containers running as non-root (`user: "1000:1000"`)
- [ ] No source-code bind mounts in production compose
- [ ] Database port not exposed externally
- [ ] Redis port not exposed externally
- [ ] Security test suite passes: `pytest tests/test_security.py -v`
