#!/usr/bin/env bash
# Build every image this deployment needs, here, where the network works.
#
# The enterprise host cannot build: npm and apt egress are intercepted there, so
# `docker compose build` fails or — worse — succeeds against a stale cache. This
# script produces the images locally and stamps them with an immutable tag, so
# what runs in production is a thing you shipped rather than a thing that host
# assembled on its own.
#
# Usage:  ./scripts/release/build-images.sh [release-tag]
# Default tag: <UTC date>-<short git sha>, with -dirty if the tree is not clean.
set -euo pipefail

cd "$(dirname "$0")/../.."

# Dirtiness is judged on the build contexts alone, because that is what the tag
# describes. Editing docker-compose.prod.yml or a runbook changes nothing inside
# either image, and marking such a build -dirty trains people to ignore the
# marker — which is worse than not having one. A change under backend/ or
# frontend/ does change the image, and that is what this catches.
CONTEXTS=(backend frontend)
if [ -n "$(git status --porcelain -- "${CONTEXTS[@]}")" ]; then
  DIRTY="-dirty"
else
  DIRTY=""
fi

RELEASE="${1:-$(date -u +%Y%m%d)-$(git rev-parse --short HEAD)${DIRTY}}"
OUT="dist/release/${RELEASE}"

# The host is x86_64 Linux. Building on an ARM machine without this produces
# images that load fine and then die with "exec format error" on first start.
PLATFORM="linux/amd64"

# Third-party images are pinned by the same digests the stack already uses, so
# the host never has to reach Docker Hub.
BASE_IMAGES=(
  "pgvector/pgvector:pg16"
  "redis:7-alpine"
  "nginx:alpine"
)

echo "==> release tag : ${RELEASE}"
echo "==> platform    : ${PLATFORM}"
echo

if [ -n "${DIRTY}" ]; then
  echo "!! backend/ or frontend/ has uncommitted changes — the tag is -dirty."
  echo "!! You will not be able to say later what is in this image. Commit first."
  git status --short -- "${CONTEXTS[@]}"
  echo
fi

# One image serves backend, worker, beat and runner-executor. They differ only
# by command and user, never by content, so building it once is not an
# optimisation — it is what keeps them from drifting apart.
echo "==> building stlc_backend:${RELEASE}"
docker build --platform "${PLATFORM}" \
  -t "stlc_backend:${RELEASE}" -t "stlc_backend:latest" \
  -f backend/Dockerfile backend

# No build args, deliberately. NEXT_PUBLIC_API_URL would be baked into the
# bundle and tie this image to one hostname; the app calls /api/v1 relative and
# nginx proxies it, so the image does not need to know where it is deployed.
# See docs/RELEASE_PREBUILT_IMAGES.md before adding one.
echo "==> building stlc_frontend:${RELEASE}"
docker build --platform "${PLATFORM}" \
  -t "stlc_frontend:${RELEASE}" -t "stlc_frontend:latest" \
  -f frontend/Dockerfile frontend

echo "==> pulling third-party base images for ${PLATFORM}"
for img in "${BASE_IMAGES[@]}"; do
  docker pull --platform "${PLATFORM}" "$img"
done

mkdir -p "${OUT}"

# Record what was built. On the host this is the only way to prove the image
# that started is the image that was shipped — tags can be reused, IDs cannot.
{
  echo "release=${RELEASE}"
  echo "built_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_commit=$(git rev-parse HEAD)"
  echo "git_dirty_build_contexts=$([ -n "${DIRTY}" ] && echo yes || echo no)"
  # Recorded for transparency: the rest of the tree may legitimately be mid-edit
  # (deployment config, docs) without affecting either image.
  echo "git_dirty_elsewhere=$([ -n "$(git status --porcelain)" ] && echo yes || echo no)"
  echo "platform=${PLATFORM}"
  for img in "stlc_backend:${RELEASE}" "stlc_frontend:${RELEASE}" "${BASE_IMAGES[@]}"; do
    printf 'image=%s id=%s\n' "$img" "$(docker image inspect -f '{{.Id}}' "$img")"
  done
} > "${OUT}/MANIFEST.txt"

echo
echo "==> built:"
cat "${OUT}/MANIFEST.txt"
echo
echo "Next: ./scripts/release/package-images.sh ${RELEASE}"
