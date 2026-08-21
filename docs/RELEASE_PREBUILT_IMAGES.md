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

Writes `dist/release/<tag>/`: ~1.9 GB split parts, `SHA256SUMS`,
`ARCHIVE.sha256`, `MANIFEST.txt`, and copies of the loader and the pin overlay.

`docker save | gzip | split` runs as a single stream, so no full archive is ever
written. That is a disk decision, not a style one: this machine has ~25 GB free,
and writing the archive and then splitting it would spend ~8 GB on two copies of
something only the parts are needed from.

### 3. Upload (WinSCP)

Upload the whole `dist/release/<tag>/` directory to a staging directory on the
host — **not** over the deployment tree. Use binary transfer mode.

There is no `images.tar.gz` to upload; the parts are the artifact.

### 4. Load and verify (on dx12348)

```bash
chmod +x load-images.sh && ./load-images.sh
```

It checksums the parts, verifies they join in the right order, streams them
straight into `docker load`, and then compares every loaded image ID against the
manifest. Nothing is written to disk on the host either — that host is also
short on space, and a 4 GB temp file is how a load fails at 95%. Image IDs are the point: a tag can be moved or
left over from an earlier attempt, an ID cannot. If anything mismatches it stops
and tells you not to deploy.

### 5. Point the deployment at the release

Copy `docker-compose.pinned.yml` next to the other compose files, and set in
`.env`:

```
STLC_IMAGE_TAG=<release-tag>
AUTOMATION_DOCKER_IMAGE=stlc_backend:<release-tag>
```

`AUTOMATION_DOCKER_IMAGE` matters as much as the compose tag: the executor
passes it to `docker run` for every spawned automation run. Left on an old tag,
the stack serves new code while its runs execute old code.

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
