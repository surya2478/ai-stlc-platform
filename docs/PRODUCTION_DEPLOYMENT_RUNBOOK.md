# Production Deployment Runbook — stlc-platform

Target host: `/home/aitesting/stlc-platform` on `dx12348` (Linux, Docker Compose v2).
Written against repository HEAD on branch `Development` (`a2bab5a`).

Read sections 0 and 0b first — they explain why the 17-Aug and 19-Aug attempts
failed, and every later step exists to prevent one of those failures.

---

## 0. What failed on 17 Aug 2026, and why

| Symptom in the log | Real cause |
|---|---|
| `SyntaxError: unmatched ')'` at `/app/app/main.py:113` | The backend **image was stale**. The traceback shows `/usr/local/lib/python3.12/dist-packages` and `/usr/lib/python3.12`, but `backend/Dockerfile` builds on `python:3.11-slim` (`.../python3.11/site-packages`). That image was not built from the current Dockerfile. HEAD's `main.py` is 132 lines and parses clean — the broken file exists only inside the old image. `docker compose up` **without `--build`** reuses whatever image is already on the host. |
| `Could not find a production build in the '.next' directory` | Two things. (a) The frontend image was stale too — the log warns about `optimizeFonts` in `next.config.js`, a key that does not exist in the current config. (b) `docker-compose.override.yml` declares anonymous volumes on `/app/.next` and `/app/node_modules`. Docker Compose **carries anonymous volumes over when it recreates a container of the same name**, so an empty `.next` from an earlier dev run kept masking the image's built `.next`, even though the override was not loaded this time. |
| `FATAL: database "stlc_prod" does not exist` | `POSTGRES_DB` only creates a database when the data directory is **empty**. The log says `Skipping initialization` — `pg_data` was already initialized under a different database name, so `stlc_prod` in `DATABASE_URL` was never created. |
| Only 6 containers started; no `stlc_nginx` | The server's `docker-compose.yml` predates the `nginx` service in HEAD. The checkout on the server is behind the repository. |
| Whole stack died on Ctrl+C | `docker compose up` was run **in the foreground and without the production override**. Production must be `-d`, and must include `docker-compose.prod.yml`. |

**Root cause in one line:** production was started from a stale checkout with
stale images, with the wrong compose file set, on a database volume whose
database name no longer matched `.env`.

---

## 0b. What the 19 Aug 2026 07:28 retry showed

The retry was run as `docker compose up` — bare. That is **the development
stack**, in the foreground, with no rebuild:

- no `-f docker-compose.prod.yml`, so `docker-compose.override.yml` loaded instead
- no `-d`, so Ctrl+C stopped the whole stack (it did, at 07:29:47)
- no `--build`, so the stale images from section 0 are still in place

Four lines in that log prove it was the dev stack: `stlc_static_test` started
(a fixture that exists only in the override), the frontend ran `next dev`, the
backend ran `uvicorn --reload` watching `/app/app`, and the worker ran as
`uid=0` (production pins `10001:10001`).

| Symptom in the log | Real cause |
|---|---|
| Backend started fine this time, `SyntaxError` gone, migrations `060 → 067` ran | **Not fixed — masked.** The dev override bind-mounts `./backend:/app`, so the checkout shadowed the broken file baked into the image. The image is still stale: the worker logs `/usr/local/lib/python3.12/dist-packages/celery`, while `backend/Dockerfile` is `python:3.11-slim` (`.../python3.11/site-packages`). Under the production file set there is no bind mount, so the `SyntaxError` returns. Section 8.1 is still mandatory. |
| `FATAL: database "stlc_prod" does not exist`, repeating every 10 s | **The db healthcheck, not the application.** The backend connected and migrated successfully, so `DATABASE_URL` is correct. The FATALs land exactly 10 s apart, matching `interval: 10s` on the `db` healthcheck: `pg_isready -U ${POSTGRES_USER}` sends no `-d`, so libpq defaults the database name to the user name — `POSTGRES_USER=stlc_prod` asks for a database called `stlc_prod`, which the already-initialized volume never had. `pg_isready` still exits 0 (the server answered), so nothing blocks; it is log noise from a mismatched `.env`. Fix in section 6. |
| `EACCES: permission denied, mkdir '/app/.next/cache'`, frontend crash-looping | Dev-stack-only. The override bind-mounts `./frontend:/app` and the image runs as uid `10001`, which does not own the checkout under `/home/aitesting`. Production declares no frontend mounts at all and runs `npm start` against the `.next` built into the image, so this cannot occur there. Do not chown the checkout to fix it — run the production file set. |
| `cannot load certificate "/etc/nginx/certs/selfsigned.crt"`, nginx restart loop | `certs/` is in `.gitignore` (line 38), so **no certificate ships with the repository** — a fresh checkout has no `certs/` directory at all. Since resolved by moving production to HTTP only: section 7. |
| `⚠ non-standard "NODE_ENV" value` | A production `.env` fed into `next dev`. Disappears under the production file set. |
| `required variable AUTOMATION_EXECUTOR_TOKEN is missing a value` (first invocation) | Section 5.3. Already corrected during that session. |

**Root cause in one line:** the retry never used the production file set, so
every production-only guarantee — built images, no bind mounts, non-root uids,
a real `.next` — was absent, and the two genuine environment gaps (database
name in `.env`, missing TLS certificates) were still unaddressed.

---

## 1. Pre-flight (before touching the running stack)

Run everything from `/home/aitesting/stlc-platform`.

**1.1 Record what is deployed now** (needed for rollback):

```bash
docker compose ps -a > /tmp/deploy-before.txt; docker image ls | grep -i stlc >> /tmp/deploy-before.txt; git rev-parse HEAD >> /tmp/deploy-before.txt; cat /tmp/deploy-before.txt
```

**1.2 Confirm nothing local will be lost.** Never `git reset --hard` or
`git clean` before reading this:

```bash
git status --short
```

If files are modified on the server, save them (`git stash push -m "prod-local-$(date +%F)"`)
or copy them aside. `.env` is untracked and is not touched by git.

**1.3 Tag the currently running images** so rollback does not depend on
finding them later:

```bash
for s in backend worker frontend runner-executor; do docker image tag "$(docker compose images -q $s | head -1)" "stlc-rollback/$s:$(date +%Y%m%d)"; done; docker image ls | grep stlc-rollback
```

**1.4 Disk check** — a full rebuild needs several GB (Playwright + Chromium + Node):

```bash
df -h /var/lib/docker
```

---

## 2. Back up the database and storage (mandatory)

**2.1 Find the database that actually exists in the volume** — do not assume the
name in `.env` is the one that is there:

```bash
docker compose up -d db && sleep 5 && docker compose exec -T db psql -U "$(grep -E '^POSTGRES_USER=' .env | cut -d= -f2)" -l
```

Note the database name from the output. You need it in step 6.

**2.2 Dump it** (substitute the `<user>` and `<dbname>` you just saw):

```bash
docker compose exec -T db pg_dump -U <user> -d <dbname> -F c -f /tmp/stlc_$(date +%Y%m%d_%H%M).dump
```

**2.3 Copy the dump out of the container:**

```bash
mkdir -p /opt/stlc/backups && docker compose cp db:/tmp/. /opt/stlc/backups/
```

**2.4 Back up the uploads/reports/workspace volume:**

```bash
docker run --rm -v stlc-platform_stlc_storage:/data -v /opt/stlc/backups:/backup alpine tar czf /backup/storage_$(date +%Y%m%d_%H%M).tgz -C /data .
```

`stlc-platform_stlc_storage` is the name Compose derives from the directory
`stlc-platform`. Confirm it with `docker volume ls | grep stlc`.

---

## 3. Bring the current stack down cleanly

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down --remove-orphans
```

> **Never add `-v` here.** `docker compose down -v` deletes `pg_data`,
> `redis_data` and `stlc_storage` — total data loss, not a restart.

If the stack was previously started with a different file set, also run a plain
`docker compose down --remove-orphans`, so no orphaned `stlc_*` container
survives holding the old anonymous volumes.

---

## 4. Update the code to the release commit

```bash
git fetch --all --prune
```

```bash
git checkout Development && git pull --ff-only origin Development
```

```bash
git log --oneline -1 && git status --short
```

Confirm the commit is the release you intend to deploy. This checkout is also
what the `runner-executor` service runs: that service bind-mounts
`./backend:/app` **in production too**, so a stale checkout means the executor
runs different code from the backend image even after a successful rebuild.

**4.1 Syntax gate — catches exactly what broke the backend yesterday:**

```bash
python3 -m compileall -q backend/app && echo "backend python OK"
```

**4.2 Confirm a single Alembic head.** Two heads make `alembic upgrade head`
fail at container start, which crash-loops the backend:

```bash
grep -h '^down_revision' backend/alembic/versions/*.py | sort | uniq -d
```

Output must be empty (no revision claimed as parent twice). At the time of
writing HEAD has 67 revisions and one head, `067`.

---

## 5. Prepare `.env`

Docker Compose reads **only `.env`** — both for `env_file:` and for `${VAR}`
interpolation. `.env.production` is a template; it is never loaded automatically.

**5.1 Install the production values:**

```bash
cp .env .env.backup-$(date +%Y%m%d%H%M%S) && cp .env.production .env
```

**5.2 Check for keys the template is missing.** `.env.production` in the repo
predates several features that now read settings (`AI_GATEWAY_*`, `ASSISTANT_*`,
`AUTOMATION_CLASSIFICATION_*`, `DISCOVERY_SESSIONS_ENABLED`,
`TEST_AUTOMATION_STUDIO_ENABLED`). List what the example has and your `.env` does not:

```bash
comm -23 <(grep -oE '^[A-Z0-9_]+=' .env.example | tr -d '=' | sort -u) <(grep -oE '^[A-Z0-9_]+=' .env | tr -d '=' | sort -u)
```

Add the ones you intend to use, with production values.

**5.3 Variables Compose refuses to start without** (`:?` in the compose files).
All five must be set and non-empty:

```bash
grep -E '^(POSTGRES_PASSWORD|REDIS_PASSWORD|DATABASE_URL|REDIS_URL|AUTOMATION_EXECUTOR_TOKEN)=' .env | sed 's/=.*/=<set>/'
```

**5.4 Values the backend validates at startup in production** — a wrong one
crash-loops the API:

- `APP_ENV=production`
- `APP_SECRET_KEY` — 32+ characters, not `change-me`, not a placeholder string
- `DEV_SEED_USER_ENABLED=false`
- `ALLOWED_ORIGINS` — no `*`; the real origin, scheme and port included, e.g.
  `http://dx12348` (add `:12080` if `HTTP_PORT` is not 80)
- `SESSION_COOKIE_SECURE=false` — mandatory on HTTP. See section 7.
- `NEXT_PUBLIC_ENABLE_DEV_AUTH=false`, and `NEXT_PUBLIC_DEV_AUTH_EMAIL` /
  `NEXT_PUBLIC_DEV_AUTH_PASSWORD` empty or absent — `next.config.js` **throws
  and fails the frontend build** if any of them is set

**5.5 Internal URLs (runtime, not build-time):**

- `INTERNAL_API_URL=http://backend:8000` — where Next.js rewrites `/api/*`
- `NEXT_PUBLIC_API_URL=http://<your-host>` — server-side only; the browser
  calls the relative path `/api/v1`
- `AUTOMATION_RUNNER_MODE=executor` and `AUTOMATION_EXECUTOR_URL=http://runner-executor:8100`
- `AUTOMATION_DOCKER_VOLUME=stlc-platform_stlc_storage` — must equal the real
  volume name from step 2.4

**5.6 Cross-check the database name.** These two must agree with each other and
with what step 2.1 found in the volume:

```bash
grep -E '^POSTGRES_DB=' .env; grep -oE '^DATABASE_URL=.*/[a-zA-Z0-9_]+$' .env | sed 's#.*/#DATABASE_URL database: #'
```

---

## 6. Resolve the database-name mismatch (the `stlc_prod` error)

Two different things produce this line; check which one you have.

**6.0 If the FATAL repeats on a fixed 10-second cadence and the backend is
otherwise healthy** (migrations ran, `/api/v1/health/` answers), it is the `db`
healthcheck, not the application. `pg_isready -U ${POSTGRES_USER}` passes no
`-d`, so libpq defaults the database name to the user name. Make `.env`
self-consistent — `POSTGRES_USER` and `POSTGRES_DB` must be exactly the user and
database segments of `DATABASE_URL`, and must match what the volume already
holds:

```bash
grep -E '^(POSTGRES_USER|POSTGRES_DB|DATABASE_URL)=' .env
```

List what the volume actually has, using the user from `DATABASE_URL`:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d db && docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db psql -U <user-from-DATABASE_URL> -d postgres -c "\l"
```

Editing `POSTGRES_USER`/`POSTGRES_DB` on an initialized volume changes nothing
inside Postgres — those two are read only at first initialization. They are now
just labels the healthcheck uses, so align them with reality rather than
recreating the volume.

The healthcheck itself has since been fixed in `docker-compose.yml` to pass
`-d ${POSTGRES_DB}` explicitly, so the FATAL disappears once the checkout in
step 4 is current **and** `POSTGRES_DB` names a database that exists.

**6.1 If the backend itself cannot connect**, `DATABASE_URL` names a database
that does not exist. Pick **one** branch, based on what step 2.1 showed.

**Branch A — the real data lives in the existing database (recommended).**
Point `.env` at it: set `POSTGRES_DB` and the database segment of `DATABASE_URL`
to the name you saw in `psql -l`. No SQL needed.

**Branch B — you genuinely want a new, empty `stlc_prod`.** The Postgres image
will not create it on an initialized volume, so create it once by hand:

```bash
docker compose exec -T db psql -U <user> -d postgres -c 'CREATE DATABASE stlc_prod;'
```

Alembic then builds the schema in step 8; migration `001` runs
`CREATE EXTENSION IF NOT EXISTS vector`, which succeeds because the image is
`pgvector/pgvector:pg16`. Be clear that Branch B starts the application with
**no users, projects or history** — you will need step 9.6 to create the first admin.

---

## 7. Transport: HTTP only (no certificates)

Production terminates **plain HTTP**. Nothing in `certs/` is read, and there is
no certificate to install or renew.

What that decision is made of — these move together, all four are already in
the repository:

| Piece | Where |
|---|---|
| nginx serves the app on port 80 instead of redirecting to TLS | `nginx.prod.http.conf`, mounted by `docker-compose.prod.yml` |
| only `HTTP_PORT` is published; no `443` binding | `docker-compose.prod.yml` (the base file publishes no nginx ports at all) |
| session cookies drop the `Secure` attribute | `SESSION_COOKIE_SECURE=false` in `.env` → `Settings.cookie_secure` |
| no `Strict-Transport-Security` anywhere | `nginx.prod.http.conf`, `backend/app/main.py`, `frontend/next.config.js` |

**7.1 `SESSION_COOKIE_SECURE=false` is not optional here.** The browser sends no
`Authorization` header — the JWT rides in an httpOnly cookie — and a browser
silently discards a `Secure` cookie delivered over HTTP. Leave it unset and
login returns 200, then every following request 401s, with nothing in the
backend log to explain it:

```bash
grep -E '^SESSION_COOKIE_SECURE=' .env
```

**7.2 Confirm `HTTP_PORT` is free on the host** before starting:

```bash
ss -ltnp | grep -E ':(80|12080)\s'
```

If 80 is taken, set `HTTP_PORT=12080` in `.env` and put `:12080` into both
`ALLOWED_ORIGINS` and `NEXT_PUBLIC_API_URL`.

**7.3 What this costs.** Session cookies, login credentials and every JWT cross
the network in cleartext, readable by anything on the path. Acceptable on a
closed internal segment or behind a VPN; not acceptable on anything routable
from outside. Record the decision and the network boundary it assumes.

**7.4 Going back to TLS** — four changes, no code edits beyond reverting these:
point the nginx volume in `docker-compose.prod.yml` back at `nginx.prod.conf`,
restore the `"${HTTPS_PORT:-12443}:443"` publish on that service, remove
`SESSION_COOKIE_SECURE` from `.env` (unset derives `True` outside `local`), and
restore the HSTS headers in `backend/app/main.py` and `frontend/next.config.js`.
Then place the certificate at `certs/fullchain.pem` and `certs/privkey.pem`.
Development is unaffected and still serves HTTPS on 12443 from `nginx.conf`
with the self-signed pair.

> The `certs/` bind mount is still inherited from `docker-compose.yml`, so the
> directory must exist even though nothing reads it. Docker creates it empty if
> it is missing.

---

## 8. Build and start

**8.1 Build every image from the current source.** The absence of this step is
what produced yesterday's `SyntaxError`:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml build --pull --no-cache
```

`--no-cache` is deliberate for a release build: it guarantees the `COPY . .`
layers and `npm run build` re-run. Expect 10–25 minutes (Chromium + Playwright).

**8.2 Start detached, discarding stale anonymous volumes.**
`--renew-anon-volumes` is what clears the empty `/app/.next` that kept the
frontend crash-looping:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate --renew-anon-volumes
```

**8.3 Watch the first minute:**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f --tail=50 backend frontend nginx
```

The backend runs `alembic upgrade head` before uvicorn. Expect
`Running upgrade ... -> 067` when the schema changes, then uvicorn binding
`0.0.0.0:8000`.

---

## 9. Verify — do not declare success until all of these pass

**9.1 Every service up, none restarting:**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

Expected: `stlc_db`, `stlc_redis`, `stlc_backend`, `stlc_worker`, the beat
container, `stlc_runner_executor`, `stlc_frontend`, `stlc_nginx`.
`stlc_static_test` must **not** be there — it is a local fixture and the
production file set excludes it.

**9.2 Backend liveness:**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend curl -sf http://localhost:8000/api/v1/health/
```

**9.3 Database readiness:**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend curl -sf http://localhost:8000/api/v1/health/ready
```

**9.4 Migration state matches the code:**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend alembic current
```

**9.5 Worker and executor:**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec worker celery -A app.worker.celery_app inspect ping
```

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend curl -sf http://runner-executor:8100/health
```

**9.6 First admin — only on a fresh database (Branch B):**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend python /repo/scripts/dev/create_admin.py
```

**9.7 End to end through nginx** (substitute `HTTP_PORT` if it is not 80):

```bash
curl -sf http://localhost/api/v1/health/ && curl -sI http://localhost/ | head -1
```

**9.8 Browser smoke test:** log in at `http://<host>`, open a project,
open Requirements and Test Cases, then confirm no 5xx appeared. If the login
form returns to itself, or the app 401s straight after a successful login, open
the browser devtools Application tab: an `access_token` cookie that is not
there is section 7.1.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=200 backend
```

---

## 10. Rollback

If verification fails and the cause is not obvious inside your change window:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down --remove-orphans
```

```bash
git checkout <previous-commit-from-/tmp/deploy-before.txt>
```

Re-tag the images saved in step 1.3 back to the names Compose expects, then run
step 8.2 **without** rebuilding. If a migration already ran and the old code
cannot read the new schema, restore the dump instead:

```bash
docker compose exec -T db pg_restore -U <user> -d <dbname> --clean --if-exists /tmp/<your>.dump
```

---

## 11. Failure → fix quick reference

| Log line | Fix |
|---|---|
| `SyntaxError` / `ImportError` under `/app/app/...` | Stale image. Re-run 8.1 with `--no-cache`, and confirm step 4 actually moved the checkout. |
| `Could not find a production build in the '.next' directory` | Anonymous volume masking `.next`. Re-run 8.2 with `--renew-anon-volumes`, after a `down` that removes the old container. |
| `database "<name>" does not exist`, once, backend cannot start | Step 6.1. `POSTGRES_DB` does nothing on an already-initialized volume. |
| `database "<name>" does not exist`, repeating every 10 s, backend healthy | Step 6.0. It is the `db` healthcheck: `POSTGRES_USER` in `.env` disagrees with `DATABASE_URL`. Noise, not an outage. |
| `EACCES ... '/app/.next/cache'`, frontend crash-loop | You are running the dev stack. Production declares no frontend bind mount — use the `-f docker-compose.yml -f docker-compose.prod.yml` pair (step 8.2). |
| `stlc_static_test` appears in `ps` | Same: the override was loaded. That fixture must never run in production. |
| `set POSTGRES_PASSWORD in .env` (or REDIS_PASSWORD / DATABASE_URL / REDIS_URL / AUTOMATION_EXECUTOR_TOKEN) | Step 5.3 — interpolation reads `.env` only, never `.env.production`. |
| `APP_SECRET_KEY must be at least 32 characters long in production` | Step 5.4. |
| `BUILD BLOCKED: Development backdoor variables` during the frontend build | `NEXT_PUBLIC_ENABLE_DEV_AUTH` / `NEXT_PUBLIC_DEV_AUTH_*` are set. Clear them. |
| nginx exits immediately, `cannot load certificate` | You are on the TLS config. Production mounts `nginx.prod.http.conf` and needs no certificate — step 7. |
| Login returns 200, every request after it 401s, no `access_token` cookie in devtools | `SESSION_COOKIE_SECURE` is unset or true on an HTTP deployment. Step 7.1. |
| `bind: address already in use` on nginx | `HTTP_PORT` is taken. Step 7.2. |
| Alembic `Multiple heads` | Two migration branches merged. Do not deploy; create a merge revision first. |
| Automation runs fail with no runner | `AUTOMATION_RUNNER_MODE=executor`, `AUTOMATION_EXECUTOR_URL=http://runner-executor:8100`, and `AUTOMATION_DOCKER_VOLUME` equal to the real volume name (5.5). |
| Frontend 502 through nginx | `INTERNAL_API_URL=http://backend:8000`; check `ps` for a restarting backend. |

---

## 12. The short version, once the first clean run is done

```bash
cd /home/aitesting/stlc-platform && git pull --ff-only origin Development && python3 -m compileall -q backend/app && docker compose -f docker-compose.yml -f docker-compose.prod.yml down --remove-orphans && docker compose -f docker-compose.yml -f docker-compose.prod.yml build --pull && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate --renew-anon-volumes && docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

Take the backup from section 2 first, then run every check in section 9.

Set this once in the deploy shell and you can drop the `-f` flags entirely,
which removes the single most dangerous mistake available here — starting
production with the development file set, as happened on 17 Aug:

```bash
export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
```
