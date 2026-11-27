#!/usr/bin/env bash
# Boot a probe Image in QEMU's generic arm64 machine and assert that the kernel
# reaches userspace.  This proves the Image is a bootable arm64 kernel; it cannot
# prove the phone drivers work (no MSM8996 hardware here).
#
#   scripts/qemu_probe.sh dist/Image-probe [logfile]
#
# A tiny static init (tools/probe_init.c) is cross-compiled into an initramfs so
# the kernel has a root filesystem; without one it panics in mount_root() before
# printing "Freeing unused kernel memory".
#
# Exit status 0 only when every marker below appears in the serial log.
set -euo pipefail

IMAGE=${1:?usage: qemu_probe.sh <Image> [logfile]}
LOG=${2:-qemu-serial.log}
TIMEOUT=${TIMEOUT:-180}
MEM=${MEM:-2048}
# The kernel itself is built with the Android gcc 4.9 prebuilt, but the tiny
# initramfs below is a glibc static binary, so it keeps using the distro cross
# compiler.  Override with INIT_CC if needed.
INIT_CC=${INIT_CC:-aarch64-linux-gnu-gcc}
ROOT=$(cd "$(dirname "$0")/.." && pwd)

command -v qemu-system-aarch64 >/dev/null || {
    echo "!! qemu-system-aarch64 not installed" >&2
    exit 1
}
command -v "$INIT_CC" >/dev/null || {
    echo "!! $INIT_CC not installed (needed for the probe initramfs)" >&2
    exit 1
}

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "== building probe initramfs"
"$INIT_CC" -static -nostdlib -ffreestanding -O2 \
    -Wl,-e,_start -o "$WORK/init" "$ROOT/tools/probe_init.c"
mkdir -p "$WORK/root/dev"
cp "$WORK/init" "$WORK/root/init"
chmod 755 "$WORK/root/init"
# The kernel opens /dev/console for init's stdio; without the node it prints
# "Warning: unable to open an initial console" and our marker goes nowhere.
# /dev/kmsg is the fallback that actually works here: on QEMU's virt machine the
# PL011 device is dropped after one -EPROBE_DEFER (3.18 of_amba_device_create),
# so no ttyAMA0 exists, but kmsg output still reaches the boot console.
mknod "$WORK/root/dev/console" c 5 1
chmod 600 "$WORK/root/dev/console"
mknod "$WORK/root/dev/kmsg" c 1 11
chmod 600 "$WORK/root/dev/kmsg"
( cd "$WORK/root" && find . | cpio -o -H newc --owner=0:0 2>/dev/null | gzip -9 ) \
    > "$WORK/initramfs.cpio.gz"
echo "   $(wc -c < "$WORK/initramfs.cpio.gz") B"

rm -f "$LOG"

# panic=1 + -no-reboot: any failure stops quickly instead of hanging.
#
# initcall_blacklist: pm-boot.o is built whenever CONFIG_PM is set and its
# postcore initcall talks to the Qualcomm secure monitor ("smc #0") before it
# looks at the device tree.  QEMU's virt machine has no EL3, so that trap turns
# into an undefined-instruction oops.  The same applies to the Qualcomm restart
# and secure-IOMMU initcalls; none of them can do anything on this machine.
BLACKLIST="msm_pm_boot_init,msm_restart_init,msm_iommu_sec_init"
qemu-system-aarch64 \
    -M virt -cpu cortex-a72 -m "$MEM" -smp 2 -nic none -display none \
    -kernel "$IMAGE" -initrd "$WORK/initramfs.cpio.gz" \
    -append "console=ttyAMA0 earlycon=pl011,0x09000000 keep_bootcon panic=1 ignore_loglevel loglevel=8 rdinit=/init initcall_blacklist=$BLACKLIST" \
    -serial "file:$LOG" -no-reboot &
QPID=$!

DONE="PROBE: userspace init reached"
deadline=$(( $(date +%s) + TIMEOUT ))
while kill -0 "$QPID" 2>/dev/null; do
    grep -qF "$DONE" "$LOG" 2>/dev/null && break
    [ "$(date +%s)" -ge "$deadline" ] && break
    sleep 2
done
kill "$QPID" 2>/dev/null || true
wait "$QPID" 2>/dev/null || true

echo "== serial log: $LOG ($(wc -l < "$LOG" 2>/dev/null || echo 0) lines)"
tail -40 "$LOG" 2>/dev/null || true

rc=0
check() {
    if grep -qF "$1" "$LOG" 2>/dev/null; then
        echo "  PASS  $1"
    else
        echo "  FAIL  $1"
        rc=1
    fi
}
echo "== markers"
# arm64 prints "Boot CPU: AArch64 Processor [...]" (the 32-bit "Booting Linux"
# message does not exist in this tree).
check "Boot CPU:"
check "Linux version"
check "Kernel command line"
check "Memory:"
check "Freeing unused kernel memory"
check "$DONE"

if [ "$rc" -eq 0 ]; then
    echo "== QEMU probe: PASS"
else
    echo "== QEMU probe: FAIL" >&2
fi
exit "$rc"
