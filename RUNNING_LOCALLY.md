# STLC Platform — Daily Run Guide

## Prerequisites (one-time setup)
- Docker Desktop installed and running
- Git (to pull latest changes if needed)

---

## Every Day: Starting the Platform

Open **PowerShell** and navigate to the project folder:

```powershell
cd C:\Test_AI_Agents\Test_AI_Agents\stlc-platform
```

Start all services:

```powershell
docker compose up -d
```

Wait about 30 seconds, then open your browser:

| Service | URL |
|---|---|
| Frontend (UI) | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |

---

## Every Day: Stopping the Platform

```powershell
cd C:\Test_AI_Agents\Test_AI_Agents\stlc-platform
docker compose stop
```

This stops all containers but keeps your database data intact.

---

## Checking if Everything is Running

```powershell
docker compose ps
```

All five services should show **Up** or **healthy**:
- `stlc_db` — PostgreSQL database
- `stlc_redis` — Redis cache
- `stlc_backend` — FastAPI backend
- `stlc_worker` — Celery background worker
- `stlc_frontend` — Next.js frontend

---

## Viewing Logs (for debugging)

All services at once:
```powershell
docker compose logs -f
```

One service at a time:
```powershell
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f worker
```

Press `Ctrl+C` to stop following logs.

---

## After Editing Code

The backend and frontend both use **hot reload** — most code changes apply automatically with no restart needed.

If a change isn't showing up, restart just the affected service:

```powershell
docker compose restart frontend
docker compose restart backend
```

---

## After Adding Python Packages to requirements.txt

```powershell
docker compose build --no-cache backend worker
docker compose up -d
```

---

## After Adding npm Packages to package.json

```powershell
docker compose build --no-cache frontend
docker compose up -d frontend
```

---

## Resetting the Database (wipes all data)

Only do this if you want a completely fresh start:

```powershell
docker compose down -v
docker compose up -d
```

The `-v` flag removes all Docker volumes including the database.

---

## Using Ollama (local LLM — optional)

To run AI agents with a local model instead of OpenAI:

```powershell
docker compose --profile ollama up -d
```

Then pull a model (first time only):
```powershell
docker compose exec ollama ollama pull llama3
```

Set `LLM_PROVIDER=ollama` in your `.env` file and restart the backend:
```powershell
docker compose restart backend worker
```

---

## Quick Reference

| Task | Command |
|---|---|
| Start everything | `docker compose up -d` |
| Stop everything | `docker compose stop` |
| Restart one service | `docker compose restart <name>` |
| View logs | `docker compose logs -f <name>` |
| Check status | `docker compose ps` |
| Full reset (deletes data) | `docker compose down -v` |
| Rebuild backend | `docker compose build --no-cache backend worker` |
| Rebuild frontend | `docker compose build --no-cache frontend` |
