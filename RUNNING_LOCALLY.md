# Daily Local Run Guide

## One-Time Setup

Requirements:

- Docker Desktop running
- Git

Create your private local environment file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set at least:

```env
APP_SECRET_KEY=replace-with-a-long-random-secret
```

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
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/docs |

Sign in at `http://localhost:3000/login`.

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
