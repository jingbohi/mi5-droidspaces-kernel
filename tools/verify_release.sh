#!/bin/bash
# Verify a downloaded release directory end to end.
#
#   tools/verify_release.sh <release-dir>
#
# Re-derives everything from the published files alone: the checksum file, the
# structure of the boot image against the repo's stock template, the byte-level
# audit, the gzip trailer and the kernel identity.
set -uo pipefail
DIR=${1:?usage: verify_release.sh <release-dir>}
REPO=$(cd "$(dirname "$0")/.." && pwd)
cd "$REPO"

BOOT="$DIR/boot-mi5-droidspaces.img"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "== files"
ls -l "$DIR"

echo
echo "== sha256 against SHA256SUMS.txt"
( cd "$DIR" && sha256sum -c SHA256SUMS.txt )

echo
echo "== extract the Image back out of the published boot image"
python3 tools/extract_boot_image.py "$BOOT" "$TMP/Image"

echo
echo "== structure check (26 invariants)"
python3 tools/verify_boot_mi5.py --boot "$BOOT" --template bootimg/mi5_boot.img --image "$TMP/Image" | tail -6

echo
echo "== gzip stream trailer"
python3 tools/check_gzip_stream.py "$BOOT"

echo
echo "== byte-level audit vs the stock boot image"
python3 tools/boot_image_audit.py bootimg/mi5_boot.img "$BOOT" | grep -E 'id \(|ISIZE|concatenated|MATCH|MISMATCH|BAD'

echo
echo "== kernel identity"
strings -a -n 10 "$TMP/Image" | grep -m1 '^Linux version'
strings -a -n 10 "$TMP/Image" | grep -m1 '3\.18\.71-perf-g4a0ef96 SMP'
