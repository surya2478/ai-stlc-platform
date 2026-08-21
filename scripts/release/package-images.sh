#!/usr/bin/env bash
# Pack the built images into checksummed parts that survive a WinSCP upload.
#
# Usage:  ./scripts/release/package-images.sh <release-tag>
#         PART_SIZE=1900m ./scripts/release/package-images.sh <tag>
set -euo pipefail

cd "$(dirname "$0")/../.."

RELEASE="${1:?usage: package-images.sh <release-tag>}"
OUT="dist/release/${RELEASE}"
# 400 MiB by default, sized for the GitHub transport.
#
# GitHub's limits, per its own docs: a release asset must be under 2 GiB, a file
# pushed through git is hard-blocked at 100 MiB, and a file added through the
# browser to the repo tree is capped at 25 MiB. Git LFS on the free plan gives
# 1 GiB of storage, which does not fit this at all.
#
# Release assets are therefore the channel, and 400 MiB is well inside that
# limit rather than near it. The reason not to use one ~1.9 GiB asset is
# resumability, on both ends: a browser upload cannot resume, and a failed
# download on the deployment host costs one part instead of the whole archive.
PART_SIZE="${PART_SIZE:-400m}"

[ -f "${OUT}/MANIFEST.txt" ] || { echo "no manifest at ${OUT} — run build-images.sh first"; exit 1; }

IMAGES=(
  "stlc_backend:${RELEASE}"
  "stlc_backend:latest"
  "stlc_frontend:${RELEASE}"
  "stlc_frontend:latest"
  "pgvector/pgvector:pg16"
  "redis:7-alpine"
  "nginx:alpine"
)

# save | gzip | split, as one stream. Writing the archive and then splitting it
# would put two full copies (~8 GB) on a disk that has ~25 GB free, and the
# intermediate file buys nothing: the parts are what gets uploaded.
#
# One archive rather than one per image. Backend and frontend share no layers,
# but the four backend tags do, and saving them together stores those once.
echo "==> saving ${#IMAGES[@]} tags, compressing and splitting in one pass"
rm -f "${OUT}"/images.tar.gz.part-*
docker save "${IMAGES[@]}" | gzip -6 | split -b "${PART_SIZE}" -d -a 2 - "${OUT}/images.tar.gz.part-"

# Per-part sums catch a truncated or dropped upload. The whole-archive sum
# catches parts that are individually intact but rejoined in the wrong order —
# which a split/cat glob will do silently once there are more than 100 parts.
echo "==> checksumming"
( cd "${OUT}" && sha256sum images.tar.gz.part-* > SHA256SUMS )
( cd "${OUT}" && cat images.tar.gz.part-* | sha256sum | sed 's/-$/images.tar.gz(joined)/' > ARCHIVE.sha256 )

# The loader and the pin overlay travel with the images; a tarball that arrives
# without them is only half a release.
cp scripts/release/load-images.sh "${OUT}/"
cp docker-compose.pinned.yml "${OUT}/"

echo
echo "==> ${OUT}"
ls -lh "${OUT}"
du -sh "${OUT}"
echo
echo "Upload every file in that directory to a staging dir on dx12348"
echo "(binary mode), then run ./load-images.sh there."
