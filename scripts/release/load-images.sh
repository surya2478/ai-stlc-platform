#!/usr/bin/env bash
# Run this ON dx12348, in the directory the parts were uploaded to.
#
# Verifies the upload, loads the images, and proves what was loaded matches what
# was built. It never builds and never pulls: if something is missing it says so
# and stops, rather than quietly reconstructing it from this host's network.
set -euo pipefail

cd "$(dirname "$0")"

command -v docker >/dev/null || { echo "docker not on PATH"; exit 1; }
[ -f SHA256SUMS ] || { echo "SHA256SUMS missing — upload incomplete"; exit 1; }
[ -f MANIFEST.txt ] || { echo "MANIFEST.txt missing — upload incomplete"; exit 1; }

RELEASE="$(sed -n 's/^release=//p' MANIFEST.txt)"
echo "==> release ${RELEASE}"

echo "==> verifying uploaded parts"
sha256sum -c SHA256SUMS

# Guards against parts that are each intact but joined in the wrong order.
if [ -f ARCHIVE.sha256 ]; then
  echo "==> verifying the joined archive"
  want="$(cut -d' ' -f1 ARCHIVE.sha256)"
  got="$(cat images.tar.gz.part-* | sha256sum | cut -d' ' -f1)"
  [ "$want" = "$got" ] || { echo "!! joined archive does not match ($got != $want)"; exit 1; }
fi

# Streamed, so the host never stores a rejoined copy either. That host is short
# on disk and a 4 GB temp file is how a load fails at 95%.
echo "==> loading images"
cat images.tar.gz.part-* | gunzip -c | docker load

# A tag can be moved; an image ID cannot. This is the step that catches a
# half-finished upload, a stale tag left over from an earlier attempt, or an
# image someone rebuilt on this host by hand.
echo "==> verifying loaded image IDs against the manifest"
fail=0
while read -r img_field id_field; do
  img="${img_field#image=}"; want="${id_field#id=}"
  got="$(docker image inspect -f '{{.Id}}' "$img" 2>/dev/null || echo MISSING)"
  if [ "$got" = "$want" ]; then
    echo "  ok       $img"
  else
    echo "  MISMATCH $img"
    echo "           expected $want"
    echo "           got      $got"
    fail=1
  fi
done < <(grep '^image=' MANIFEST.txt)

[ "$fail" -eq 0 ] || { echo; echo "!! images do not match the manifest — do NOT deploy"; exit 1; }

echo
echo "==> all images match the manifest"
echo
echo "1. Put docker-compose.pinned.yml next to the other compose files."
echo "2. Set this one line in .env:"
echo
echo "     STLC_IMAGE_TAG=${RELEASE}"
echo
echo "   That is the only value to change. AUTOMATION_DOCKER_IMAGE is derived"
echo "   from it in docker-compose.pinned.yml, so it cannot lag behind a"
echo "   release; any AUTOMATION_DOCKER_IMAGE still in .env is overridden."
echo
echo "3. Deploy (--no-build is required; nothing here may build):"
echo
echo "     docker compose -f docker-compose.yml -f docker-compose.prod.yml \\"
echo "                    -f docker-compose.pinned.yml up -d --no-build"
