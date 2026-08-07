# Daily Local Run Guide

## One-Time Setup

Requirements:

- Docker Desktop running
- Git

Create your private local environment file:

```powershell
Copy-Item .env.development .env
```

`.env.development` carries working local defaults, so the stack starts from that
copy unchanged. `.env.example` is the annotated reference for every supported
key; if you start from that one instead, replace each `replace-...` placeholder
before running compose.

Three keys have no usable default and stop compose from starting at all when
they are missing — not just the service that reads them:

```env
APP_SECRET_KEY=replace-with-a-long-random-secret
REDIS_PASSWORD=replace-local-redis-password
AUTOMATION_EXECUTOR_TOKEN=replace-with-a-local-executor-token-min-32-chars
```

`REDIS_PASSWORD` must also appear inside `REDIS_URL`
(`redis://:<password>@redis:6379/0`) — compose hands the password to
`redis-server --requirepass`, and the application authenticates with the URL.

Optional local admin seed:

```env
DEV_SEED_USER_ENABLED=true
DEV_SEED_USER_EMAIL=your-local-admin@example.com
DEV_SEED_USER_PASSWORD=replace-with-a-local-password
```

Keep LLM and Jira secrets empty until you need those integrations.

## Start The Platform

```powershell
cd C:\Test_AI_Agents\Test_AI_Agents\stlc-platform
docker compose up -d
```

Open:

| Service | URL |
|---|---|
| Frontend | http://localhost:4300 |
| Backend API | http://localhost:8400 |
| Swagger Docs | http://localhost:8400/docs |

3000 and 8000 are reserved on the shared host, so the compose override
publishes the app on `FRONTEND_PORT` (default 4300) and the API on
`BACKEND_PORT` (default 8400). Both containers still listen on 3000 and 8000
internally, which is what nginx and `INTERNAL_API_URL` address.

Sign in at `http://localhost:4300/login`.

## Stop The Platform

```powershell
docker compose stop
```

This keeps database volumes intact.

## Check Status

```powershell
docker compose ps
```

Expected services:

- `stlc_db`
- `stlc_redis`
- `stlc_backend`
- `stlc_worker`
- `stlc_frontend`

## Logs

```powershell
docker compose logs -f
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f worker
```

## After Code Changes

Hot reload is enabled for backend and frontend in local Docker Compose.

If the browser still shows stale code:

```powershell
docker compose restart frontend
docker compose restart backend
```

## Rebuild Images

Backend dependency changes:

```powershell
docker compose build --no-cache backend worker
docker compose up -d
```

Frontend dependency changes:

```powershell
docker compose build --no-cache frontend
docker compose up -d frontend
```

## Reset Database

This deletes all local data:

```powershell
docker compose down -v
docker compose up -d
```

## Optional Ollama

```powershell
docker compose --profile ollama up -d
docker compose exec ollama ollama pull llama3
```

Then set:

```env
DEFAULT_LLM_PROVIDER=ollama
```

Restart:

```powershell
docker compose restart backend worker
```

## Playwright AI Studio — Docker execution mode

The Studio (`/playwright-studio`) can execute generated scripts in ephemeral
Docker containers (parallel, isolated) instead of the worker's local
subprocess. Requirements:

1. **Rebuild the backend/worker image** after pulling this feature — the
   Dockerfile now installs the docker CLI:

   ```powershell
   docker compose build backend worker
   docker compose up -d
   ```

2. **Docker socket**: `docker-compose.yml` mounts `/var/run/docker.sock`
   into the worker. On Docker Desktop for Windows this works with the
   default WSL2 backend (Linux containers).

3. **Settings** (all optional, `.env`):

   ```env
   AUTOMATION_RUNNER_MODE=local            # global default; Studio runs pick their own mode per run
   AUTOMATION_DOCKER_IMAGE=stlc-platform-worker
   AUTOMATION_DOCKER_VOLUME=stlc-platform_stlc_storage
   AUTOMATION_DOCKER_NETWORK=              # set to the compose network if the app under test runs in-stack
   STUDIO_MAX_PARALLEL=4
   ```

   The defaults assume the compose project directory is named
   `stlc-platform` (compose v2 names the worker image
   `stlc-platform-worker` and the volume `stlc-platform_stlc_storage`).
   If your checkout directory differs, check `docker images` /
   `docker volume ls` and set the two values accordingly.

   Spawned runner containers use the worker's own image, so Node,
   @playwright/test and Chromium are already inside them — nothing is
   downloaded at container start.

4. **Verify**: start a Studio run with runner mode "Docker containers",
   approve the plan and scripts, then `docker ps` — you should see
   `stlc-pw-<hash>` containers appear (up to the configured parallelism)
   while the batch executes.
