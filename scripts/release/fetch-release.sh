#!/usr/bin/env bash
# Download a release from GitHub onto the deployment host, then load it.
#
# Usage:  ./fetch-release.sh <release-tag> [repo]
#         ./fetch-release.sh 20260821-62ad749
#
# Assumes a public repository: the parts are fetched with plain curl and no
# credentials. If the repo is ever made private this stops working and the
# downloads need a token header instead.
set -euo pipefail

RELEASE="${1:?usage: fetch-release.sh <release-tag> [owner/repo]}"
REPO="${2:-surya2478/ai-stlc-platform}"
BASE="https://github.com/${REPO}/releases/download/${RELEASE}"

command -v curl >/dev/null || { echo "curl not on PATH"; exit 1; }

mkdir -p "${RELEASE}"
cd "${RELEASE}"

# Reachability first, with a clear message. This host's egress is filtered —
# apt and npm are intercepted — so GitHub being blocked is a real possibility
# and worth failing on loudly rather than through a half-downloaded part.
echo "==> checking GitHub is reachable from this host"
if ! curl -sSfI --max-time 20 "https://github.com" >/dev/null 2>&1; then
  echo "!! cannot reach github.com from this host."
  echo "!! Egress here is filtered (apt and npm are). Fall back to uploading the"
  echo "!! release with WinSCP — see docs/RELEASE_PREBUILT_IMAGES.md."
  exit 1
fi

# Small files first: SHA256SUMS names every part, so it decides what to fetch.
echo "==> fetching metadata"
for f in SHA256SUMS ARCHIVE.sha256 MANIFEST.txt load-images.sh docker-compose.pinned.yml; do
  curl -fL --retry 3 --retry-delay 2 -o "$f" "${BASE}/${f}"
done

PARTS=$(awk '{print $2}' SHA256SUMS | tr -d '*')
echo "==> fetching $(echo "$PARTS" | wc -w) parts"
for part in $PARTS; do
  # -C - resumes a partial file, so a dropped connection costs the remainder of
  # one part rather than the whole archive.
  echo "    $part"
  curl -fL --retry 5 --retry-delay 3 -C - -o "$part" "${BASE}/${part}"
done

echo "==> verifying"
sha256sum -c SHA256SUMS

chmod +x load-images.sh
echo
echo "==> downloaded and verified into $(pwd)"
echo "Now run:  ./load-images.sh"
