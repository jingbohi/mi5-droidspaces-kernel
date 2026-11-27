#!/bin/bash
# Verify a downloaded release directory end to end.
#
#   tools/verify_release.sh <release-dir>
#
# Re-derives everything from the published files alone: the checksum file, the
# structure of both boot images against their stock templates, the byte-level
# audit, the gzip trailer and the kernel identity.
set -uo pipefail
DIR=${1:?usage: verify_release.sh <release-dir>}
REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "== files"
ls -l "$DIR"

echo
echo "== sha256 against SHA256SUMS.txt"
( cd "$DIR" && sha256sum -c SHA256SUMS.txt )

for pair in "boot-mi5-droidspaces.img:mi5_boot.img" \
            "boot-mi5-droidspaces-global.img:mi5_boot_g.img"; do
    BOOT="$DIR/${pair%%:*}"
    TEMPLATE="bootimg/${pair##*:}"
    IMG="$TMP/Image.${pair%%:*}"
    echo
    echo "== ${pair%%:*} ($(stat -c%s "$BOOT" 2>/dev/null || echo missing) B)"
    echo "-- extract the Image back out of the published boot image"
    python3 tools/extract_boot_image.py "$BOOT" "$IMG"
    echo "-- structure check (26 invariants) against $TEMPLATE"
    python3 tools/verify_boot_mi5.py --boot "$BOOT" --template "$TEMPLATE" --image "$IMG" | tail -4
    echo "-- gzip stream trailer"
    python3 tools/check_gzip_stream.py "$BOOT"
    echo "-- byte-level audit vs $TEMPLATE"
    python3 tools/boot_image_audit.py "$TEMPLATE" "$BOOT" | grep -E 'id \(|ISIZE|concatenated|MATCH|MISMATCH|BAD'
    echo "-- kernel identity"
    strings -a -n 10 "$IMG" | grep -m1 '^Linux version'
    strings -a -n 10 "$IMG" | grep -m1 '3\.18\.71-perf-g4a0ef96 SMP'
done

echo
echo "== both boot images must carry the same Image"
cmp -s "$TMP/Image.boot-mi5-droidspaces.img" "$TMP/Image.boot-mi5-droidspaces-global.img" \
    && echo "MATCH  identical kernel Image in both boot images" \
    || { echo "MISMATCH  the two boot images carry different kernels"; exit 1; }
