#!/bin/bash
# Verify a downloaded CI artifact against the stock template, the same way the
# published release was checked.
#
#   tools/verify_ci_artifact.sh <artifact-dir>
set -uo pipefail
ART=${1:?usage: verify_ci_artifact.sh <artifact-dir>}
REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO"

BOOT="$ART/boot-mi5-droidspaces.img"
IMG="$ART/Image-release"

echo "== files"
ls -l "$BOOT" "$IMG" 2>&1
echo
echo "== sha256"
sha256sum "$BOOT"
echo
echo "== structure check (26 invariants)"
python3 tools/verify_boot_mi5.py --boot "$BOOT" --template bootimg/mi5_boot.img --image "$IMG"
echo
echo "== byte-level audit vs the stock boot image"
python3 tools/boot_image_audit.py bootimg/mi5_boot.img "$BOOT"
echo
echo "== kernel identity"
strings -a -n 10 "$IMG" | grep -m1 '^Linux version' || true
strings -a -n 10 "$IMG" | grep -m1 '3\.18\.71-perf-g4a0ef96 SMP' || true
