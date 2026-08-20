# Local Automation Runner — Install & Operate

The automation execution module runs LLM-generated scripts as real subprocesses
on the host where the backend (and Celery worker) processes execute. Two
runners ship:

| Framework  | Tool                  | Used for              |
| ---------- | --------------------- | --------------------- |
| `pytest`   | `python -m pytest`    | API / service tests   |
| `playwright` | `npx playwright test` | UI / browser tests    |

The runner abstraction lives in `app/services/automation_runner/`. It is
deployment-target agnostic — Docker, bare-metal VM, or Kubernetes node — as
long as the runtime requirements below are present on PATH.

## Runtime requirements

### Pytest runner
Already satisfied by the standard backend Python environment. Installed via
`requirements.txt`:

- `pytest`
- `pytest-json-report` *(used by the runner for structured per-test outcomes)*

No host install needed. Restart the backend after pulling new requirements.

### Playwright runner
Requires Node.js + `@playwright/test` on PATH.

**Docker (current default):**
The `backend/Dockerfile` installs Node.js 20 LTS, `@playwright/test@1.62.1`
and `@playwright/mcp@0.0.77` during image build. Rebuild the backend image
after this change:

```sh
docker compose build backend
docker compose up -d backend worker
```

The Chromium browser used by `@playwright/test` is also installed during the
build (`npx playwright install chromium`).

**Bare metal / VM (production-style):**
Run once on the host where the backend (or Celery worker) lives:

```sh
# Node 20 LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt-get install -y nodejs

# Playwright CLI + Chromium
sudo npm install -g @playwright/test@1.62.1
sudo npx --yes playwright install chromium
sudo npx --yes playwright install-deps chromium   # system libs

# Browser MCP server used by Studio discovery (mcp_session.py). Not optional
# on a host without registry access: `npx -y @playwright/mcp@<version>`
# resolves the package spec through npm and reaches the network even when the
# package is already installed globally, so the discovery run fails without
# this. Keep the version equal to PLAYWRIGHT_MCP_VERSION in
# app/agents/automation/mcp_session.py.
sudo npm install -g @playwright/mcp@0.0.77
```

Restart the backend and worker after the install so the cached preflight check
re-detects Node:

```sh
systemctl restart stlc-backend stlc-worker
```

**Kubernetes:**
Either bake the install into a custom backend image (same Dockerfile lines), or
run the runner in a sidecar container using
`mcr.microsoft.com/playwright:v1.62.1-noble`. Either way the runner code is
unchanged.

## Verify

```sh
# Pytest
python -m pytest --version

# Playwright
npx --yes playwright --version
```

Or call the API once the backend is up:

```http
GET /api/v1/automation/runner/status
```

You should see both frameworks with `available: true`. If one shows `false`,
the `detail` field contains a remediation hint.

## How a run works (end to end)

1. UI clicks **Run** on an approved `AutomationScript`.
2. `POST /api/v1/automation/scripts/{id}/execute` creates an
   `ExecutionRun(status="queued")` and one `ExecutionResult(status="pending")`,
   then enqueues a Celery task.
3. The Celery task:
   - Materialises the script under
     `<file_storage_path>/automation_workspace/<execution_run_id>/`
   - Writes `package.json` + `playwright.config.ts` for Playwright runs, or a
     stub `conftest.py` for Pytest runs.
   - Sets the `AUTOMATION_ENV` environment variable so scripts can branch on
     environment (e.g. `staging`, `SIT`).
   - Runs the subprocess with a configurable timeout (default 600 s).
   - Parses the JSON reporter output for per-test outcomes.
   - Writes results to `ExecutionResult` rows and updates the run's
     `passed / failed / skipped / total_tests / status` columns.
4. UI polls `GET /api/v1/execution/{run_id}` every few seconds while the run is
   `queued` or `running`, then renders the final per-test rows + artifact links.

## Artifacts

Each `ExecutionResult` row may have any of:

- `logs` — stdout + stderr capture
- `screenshot_path` — failure screenshot (Playwright only)
- `video_path` — failure video (Playwright only)
- `trace_path` — `trace.zip` for the Playwright trace viewer

Downloaded through the authenticated route:

```
GET /api/v1/automation/runner/results/{result_id}/artifact/{kind}
```

where `kind ∈ {log, screenshot, video, trace}`. Path traversal is guarded by
canonicalising the resolved file path and checking that it lives under
`file_storage_path`.

## Tuning

Per-request:
- `environment` — free-form string, passed to the script as `AUTOMATION_ENV`
- `timeout_seconds` — 30 – 3600 s, default 600 s

Per-deploy (env vars):
- `FILE_STORAGE_PATH` — root of materialised workspaces and artifacts
- `MAX_UPLOAD_SIZE_MB` — also caps the size of incoming evidence uploads

## What this runner deliberately does **not** do (yet)

- Docker-isolated runs (each script in its own ephemeral container).
- Parallel sharding (`--workers N`).
- Retry-only-failed-tests as a backend action.
- Live log streaming via WebSocket / SSE — the UI polls.
- Auto-installing project-specific `npm` or `pip` dependencies inside the
  workspace. If a generated script needs a custom package it must declare it
  via `setup_required` and a separate review step.

These are tracked as follow-up work in the Execution module roadmap.
