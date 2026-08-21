# Shipping prebuilt images to dx12348

Production stopped being able to build. `npm install` and `apt-get update` inside
a build container do not resolve on that network, so every deploy that ended in
`docker compose build` either hung or produced an image from a stale cache. The
fix is to stop building there at all: images are built here, where the network
works, and arrive as an artifact.

The rule this document exists to enforce: **nothing is ever built on dx12348.**
A deploy that starts a build is a failed deploy, even if it succeeds.

## What gets shipped

| Image | Serves | Approx |
|---|---|---|
| `stlc_backend:<release>` | backend, worker, beat, runner-executor | 5.1 GB |
| `stlc_frontend:<release>` | frontend | 3.2 GB |
| `pgvector/pgvector:pg16` | db | 621 MB |
| `redis:7-alpine` | redis | 58 MB |
| `nginx:alpine` | nginx | 94 MB |

One backend image serves four services. They differ by command and user, never
by content — building it once is what stops them drifting apart.

Roughly 9 GB before compression, 3–4 GB after.

## Why the frontend image is not tied to this hostname

It would be reasonable to expect `NEXT_PUBLIC_API_URL` to be baked in at build
time, which would mean a new image for every URL change. It is not, and the
image is deliberately built without it:

- `frontend/src/lib/api.ts` creates the axios client with `baseURL: "/api/v1"` —
  relative, so the browser calls whatever origin served the page.
- `nginx.prod.conf` proxies `/api/` straight to `backend:8000`, so the Next.js
  rewrite and `INTERNAL_API_URL` never come into play in production.
- The only place the variable reaches is the CSP `connect-src` and one error
  string. Browser traffic is same-origin, which `'self'` already covers, and the
  app opens no websockets.

So the same image is correct at any hostname or port. **Do not add a
`NEXT_PUBLIC_API_URL` build arg** to get a tidier CSP — it trades a cosmetic
improvement for a rebuild every time the URL moves, which is the problem this
whole document exists to avoid.

The one thing that *would* force a rebuild is `basePath`. It is baked, and it is
needed only if users reach the app under a path prefix such as `/esmart`. They
reach it at `https://dx12348.etisalat.corp.ae:12443` — root, no prefix — so no
`basePath` is set. If that ever changes, the frontend image must be rebuilt.

## Procedure

### 1. Build (here)

```bash
./scripts/release/build-images.sh
```

Prints a release tag like `20260821-0eebf0b`, built from the date and the commit.
Build from a clean tree; a dirty tree is tagged `-dirty` and you will not be able
to say later what is running.

### 2. Package (here)

```bash
./scripts/release/package-images.sh <release-tag>
```

Writes `dist/release/<tag>/`: the archive in **400 MiB parts** (five, for a
~1.9 GiB archive), plus `SHA256SUMS`, `ARCHIVE.sha256`, `MANIFEST.txt`, and
copies of the loader and the pin overlay. Override with `PART_SIZE=<size>` if the
transport ever changes; step 3 explains why 400 MiB.

`docker save | gzip | split` runs as a single stream, so no full archive is ever
written. That is a disk decision, not a style one: this machine has ~25 GB free,
and writing the archive and then splitting it would spend ~8 GB on two copies of
something only the parts are needed from.

### 3. Publish the parts as a GitHub release

The artifact is delivered through a **GitHub release**, not through the git tree.
GitHub's published limits decide this:

| Channel | Per-file limit |
|---|---|
| Release asset | **under 2 GiB**, up to 1000 assets, no total size or bandwidth limit |
| File pushed via git | **100 MiB** hard block (50 MiB warning) |
| File added via browser to the repo tree | **25 MiB** |
| Git LFS, free plan | 1 GiB storage — does not fit this artifact |

Committing the parts into the repository would work at 95 MiB each, but it
permanently bloats the repo with ~2 GiB of binaries that cannot easily be removed
afterwards. Release assets are stored separately and count against none of it.

Parts are 400 MiB rather than one ~1.9 GiB asset. That is inside the limit with
room to spare, and it is about resumability at both ends: a browser upload cannot
resume, and a failed download on the deployment host costs one part instead of
the whole archive.

Create a release tagged with the release name and attach **every file** in
`dist/release/<tag>/` — the parts, `SHA256SUMS`, `ARCHIVE.sha256`, `MANIFEST.txt`,
`load-images.sh` and `docker-compose.pinned.yml`.

> **The repository is public**, so these assets are publicly downloadable. That is
> a deliberate choice recorded here so it is not rediscovered by accident: the
> images contain the full built application. Moving the artifacts to a private
> repository means downloads on the host need an authenticated request instead.

### 3b. When the release step can be skipped

Publishing to GitHub is what gets the artifact from the build machine to whoever
is deploying. If that is the same person on the same machine, the folder from
step 2 is already the artifact — go straight to 4b and upload it with WinSCP.

The release is still worth creating: it is the only durable record of what was
shipped, and it is what a rollback or a second deployer fetches later.

### 4. Download to a workstation, then WinSCP it up

The deployment host cannot reach GitHub — its egress is filtered, which is the
same reason images are not built there. So the artifact takes three hops:
**GitHub → an office workstation → WinSCP → dx12348.** The host only ever runs
`load-images.sh`.

**4a. On the workstation** (Windows, no Git Bash required):

```powershell
powershell -ExecutionPolicy Bypass -File fetch-release.ps1 -Tag <release-tag>
```

Get the script itself from the repo — `scripts/release/fetch-release.ps1`, or
straight from
`https://raw.githubusercontent.com/surya2478/ai-stlc-platform/New-Branch/scripts/release/fetch-release.ps1`.

It reads `SHA256SUMS` to learn which parts exist, downloads each one, and checks
its hash. **Re-running is how you recover a failed download**: anything that
already verifies is skipped, so only the missing or corrupt parts are fetched
again. It forces TLS 1.2, because the Windows PowerShell 5.1 default is what
corporate proxies reject — and it surfaces as "could not create SSL/TLS secure
channel", which does not obviously mean "wrong TLS version".

**4b. Upload with WinSCP** in **binary** transfer mode: the whole
`<release-tag>` folder, into a staging directory on dx12348. Not into the
deployment tree.

**4c. On dx12348:**

```bash
cd <staging>/<release-tag> && chmod +x load-images.sh && ./load-images.sh
```

It checksums the parts, verifies they join in the right order, streams them
straight into `docker load`, and compares every loaded image ID against the
manifest. Nothing is written to disk on the host — that host is short on space,
and a 2 GB temp file is how a load fails at 95%.

Image IDs are the point: a tag can be moved or left over from an earlier
attempt, an ID cannot. If anything mismatches it stops and tells you not to
deploy.

> If a host ever *does* have GitHub access, `scripts/release/fetch-release.sh`
> collapses 4a–4c into one step by downloading directly onto it. It checks
> reachability first and fails clearly if GitHub is blocked.

### 5. Point the deployment at the release

Copy `docker-compose.pinned.yml` next to the other compose files, and set exactly
one line in `.env`:

```
STLC_IMAGE_TAG=<release-tag>
```

That is the only value to change per release.

`AUTOMATION_DOCKER_IMAGE` is **not** set by hand. It is the image the executor
passes to `docker run` for every spawned automation run, and it is derived from
`STLC_IMAGE_TAG` in `docker-compose.pinned.yml`. Maintained separately it
silently lags a release, and the stack then serves new code while its runs
execute old code — which presents as a stale image and gets blamed on the
deploy. Deriving it also means a rollback rolls the runners back with it rather
than half way. A compose `environment:` entry beats `env_file`, so any
`AUTOMATION_DOCKER_IMAGE` still sitting in `.env` is overridden.

A wrong value there does not fail the deploy: `docker run` with an absent image
attempts a pull, which fails on this network, so it surfaces later as every
automation run failing.

### 6. Start

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
               -f docker-compose.pinned.yml up -d --no-build
```

`--no-build` is not decorative. `docker-compose.yml` still declares `build:` for
backend, worker, runner-executor and frontend, and the merged config keeps it —
verified, not assumed. Three separate things stop a build here: the pinned
`image:`, `pull_policy: never`, and this flag. Any one would do; all three are
present because this failure has already cost two weeks.

`STLC_IMAGE_TAG` is required rather than defaulted to `latest`. `latest` is
whatever was loaded last, which is precisely the ambiguity behind every "the fix
isn't taking effect" report on this host.

### 7. Confirm nothing was built

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
               -f docker-compose.pinned.yml ps
docker image inspect -f '{{.Id}}' stlc_backend:<release-tag>
```

The ID must equal the `image=stlc_backend:<tag> id=` line in `MANIFEST.txt`.
`stlc_static_test` must not appear in `ps` — it is a local fixture and lives in
a separate repository now.

## Rollback

The previous release's images are still loaded — `docker load` adds, it never
replaces. Point `STLC_IMAGE_TAG` and `AUTOMATION_DOCKER_IMAGE` at the older tag
and repeat step 6. That is the reason for immutable tags: rollback is an edit to
one variable, not another 4 GB upload.

Prune deliberately, never with a blanket `docker image prune -a`, which on this
host deletes images that cannot be rebuilt.

## Certificate note

nginx serves TLS from `certs/fullchain.pem` with `server_name _`, so it answers
on any hostname. The certificate itself must still be valid for
`dx12348.etisalat.corp.ae`. If it was issued for `dx12348.exp.corp.ae`, browsers
will warn on every visit — nginx will start regardless, so this shows up as a
user complaint rather than a failed deploy. Check before announcing the release:

```bash
openssl x509 -in certs/fullchain.pem -noout -subject -ext subjectAltName -dates
```
