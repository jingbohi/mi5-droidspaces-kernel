#!/bin/bash
# Verify a downloaded CI artifact against the stock templates, the same way the
# published release was checked.
#
#   tools/verify_ci_artifact.sh <artifact-dir>
set -uo pipefail
ART=${1:?usage: verify_ci_artifact.sh <artifact-dir>}
REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO"

IMG="$ART/Image-release"

echo "== files"
ls -l "$ART"/boot-mi5-droidspaces*.img "$IMG" 2>&1
echo
echo "== sha256"
sha256sum "$ART"/boot-mi5-droidspaces*.img
echo
echo "== structure check (26 invariants) + byte-level audit"
for pair in "boot-mi5-droidspaces.img:mi5_boot.img" \
            "boot-mi5-droidspaces-global.img:mi5_boot_g.img"; do
    BOOT="$ART/${pair%%:*}"
    TEMPLATE="bootimg/${pair##*:}"
    [ -f "$BOOT" ] || { echo "-- ${pair%%:*}: not present, skipped"; continue; }
    echo
    echo "-- ${pair%%:*} vs $TEMPLATE"
    python3 tools/verify_boot_mi5.py --boot "$BOOT" --template "$TEMPLATE" --image "$IMG"
    python3 tools/boot_image_audit.py "$TEMPLATE" "$BOOT"
done
echo
echo "== kernel identity"
strings -a -n 10 "$IMG" | grep -m1 '^Linux version' || true
strings -a -n 10 "$IMG" | grep -m1 '3\.18\.71-perf-g4a0ef96 SMP' || true
