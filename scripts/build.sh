#!/usr/bin/env bash
# Build the Xiaomi Mi 5 (gemini) kernel for Droidspaces.
#
#   scripts/build.sh release [outdir]     # flashable kernel, stock vermagic
#   scripts/build.sh probe   [outdir]     # + PL011, for the QEMU smoke test
#
# Environment:
#   SRC=.work/kernel     kernel source tree (downloaded when missing)
#   JOBS=$(nproc)        parallel make jobs
#   DIST=dist            where boot.img / Image / reports are collected
#   USE_CCACHE=1         wrap the cross compiler with ccache when available
#   SKIP_DOWNLOAD=1      fail instead of downloading the source
#
# The stock defconfig is extended by config/droidspaces.layer; for the probe
# build config/probe.layer is applied on top as well.
set -euo pipefail

VARIANT=${1:?usage: build.sh <release|probe> [outdir]}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${2:-"$ROOT/out-$VARIANT"}
SRC=${SRC:-"$ROOT/.work/kernel"}
DIST=${DIST:-"$ROOT/dist"}
JOBS=${JOBS:-$(nproc)}

KERNEL_REPO="MiCode/Xiaomi_Kernel_OpenSource"
KERNEL_BRANCH="scorpio-o-oss"
KERNEL_COMMIT="a36928ce4998125d9e71d1377a52d68cfe156872"
KERNEL_TARBALL="$ROOT/.work/kernel.tar.gz"
KERNEL_URL=${KERNEL_URL:-"https://codeload.github.com/$KERNEL_REPO/tar.gz/$KERNEL_COMMIT"}

export ARCH=arm64
export CROSS_COMPILE=${CROSS_COMPILE:-aarch64-linux-gnu-}
export KBUILD_BUILD_USER=${KBUILD_BUILD_USER:-mi5}
export KBUILD_BUILD_HOST=${KBUILD_BUILD_HOST:-droidspaces}

# Xiaomi's scripts/gcc-wrapper.py turns every compiler warning into an error and
# still asks for python2.  Modern gcc emits new warnings in 3.18 code, so call
# the cross compiler directly; the warnings stay in build.log.
REALCC="${CROSS_COMPILE}gcc"
if [ "${USE_CCACHE:-0}" = "1" ] && command -v ccache >/dev/null 2>&1; then
    CC_CMD="ccache $REALCC"
else
    CC_CMD="$REALCC"
fi

mkdir -p "$ROOT/.work" "$DIST"
# `make -C $SRC O=<dir>` resolves a relative output dir against $SRC, not against
# the caller, so normalise everything to absolute paths first.
DIST=$(cd "$DIST" && pwd)

if [ ! -f "$SRC/Makefile" ]; then
    if [ "${SKIP_DOWNLOAD:-0}" = "1" ]; then
        echo "!! $SRC is empty and SKIP_DOWNLOAD=1" >&2
        exit 1
    fi
    if [ ! -s "$KERNEL_TARBALL" ]; then
        echo "== fetching kernel source"
        echo "   $KERNEL_URL"
        tmp="$KERNEL_TARBALL.part"
        # direct first, then the local proxy, then GitHub proxies
        if ! curl -fL --retry 3 --connect-timeout 20 -o "$tmp" "$KERNEL_URL"; then
            proxy="http://127.0.0.1:1081"
            if ! curl -fL --retry 3 --connect-timeout 20 -x "$proxy" -o "$tmp" "$KERNEL_URL"; then
                mv "$tmp" "$KERNEL_TARBALL" 2>/dev/null || true
                echo "!! direct and proxy download failed." >&2
                echo "   Download manually and place it at $KERNEL_TARBALL" >&2
                echo "   $KERNEL_URL" >&2
                exit 1
            fi
        fi
        mv "$tmp" "$KERNEL_TARBALL"
    fi
    echo "== extracting kernel source"
    mkdir -p "$SRC"
    tar -xzf "$KERNEL_TARBALL" -C "$SRC" --strip-components=1
fi

echo "== kernel tree: $(sed -n 's/^\(VERSION\|PATCHLEVEL\|SUBLEVEL\) = \(.*\)/\1=\2/p' "$SRC/Makefile" | tr '\n' ' ')"
SRC=$(cd "$SRC" && pwd)

if [ -f "$SRC/.patched" ]; then
    echo "== patches already applied"
else
    for p in "$ROOT"/patches/*.patch; do
        [ -e "$p" ] || continue
        echo "== applying $(basename "$p")"
        patch -d "$SRC" -p1 --forward --no-backup-if-mismatch < "$p"
    done
    touch "$SRC/.patched"
fi

case "$VARIANT" in
    release) DEFCONFIG=mi5_droidspaces_defconfig; EXTRA="" ;;
    probe)   DEFCONFIG=mi5_probe_defconfig; EXTRA="--extra config/probe.layer" ;;
    *) echo "!! unknown variant $VARIANT" >&2; exit 2 ;;
esac

cd "$ROOT"
python3 tools/mi5_config.py --src "$SRC" --out-name "$DEFCONFIG" $EXTRA

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
make -C "$SRC" O="$OUT" CC="$CC_CMD" "$DEFCONFIG" >/dev/null
make -C "$SRC" O="$OUT" CC="$CC_CMD" olddefconfig >/dev/null
# prepare generates include/config/kernel.release, which check_config.py reads;
# on a fresh tree it does not exist right after olddefconfig.
make -C "$SRC" O="$OUT" CC="$CC_CMD" prepare >/dev/null
[ -f "$OUT/.config" ] || { echo "!! $OUT/.config was not generated" >&2; exit 1; }
cp -f "$OUT/.config" "$OUT/config-$VARIANT.txt"

python3 tools/check_config.py --config "$OUT/.config" \
    --release "$OUT/include/config/kernel.release" \
    --layer config/droidspaces.layer \
    --stock config/stock-resolved.config \
    --diff-out "$DIST/config-diff-$VARIANT.txt"

echo "== building Image ($JOBS jobs)"
make -C "$SRC" O="$OUT" CC="$CC_CMD" -j"$JOBS" Image 2>&1 | tee "$OUT/build.log"

IMAGE="$OUT/arch/arm64/boot/Image"
cp -f "$IMAGE" "$DIST/Image-$VARIANT"
md5sum "$IMAGE"

# The vermagic string is what makes the stock vendor modules accept this kernel;
# assert the whole string, flags included, straight out of vmlinux.
EXPECTED_VERMAGIC="3.18.71-perf-g4a0ef96 SMP preempt mod_unload modversions aarch64"
if grep -qaF "$EXPECTED_VERMAGIC" "$OUT/vmlinux"; then
    echo "== vermagic OK: $EXPECTED_VERMAGIC"
else
    echo "!! vermagic mismatch, expected: $EXPECTED_VERMAGIC" >&2
    grep -ao "3\.18\.71[^\"]*" "$OUT/vmlinux" | sort -u | head -5 >&2 || true
    exit 1
fi

python3 tools/crc_compare.py --symvers "$OUT/Module.symvers" \
    --dumps config/vendor-crc \
    --strict qca_cld_wlan,wil6210,exfat,br_netfilter | tee "$DIST/crc-$VARIANT.txt"

if [ "$VARIANT" = "release" ]; then
    echo "== packing boot image"
    python3 tools/pack_boot_mi5.py --template bootimg/mi5_boot.img \
        --image "$IMAGE" --out "$DIST/boot-mi5-droidspaces.img"
    python3 tools/verify_boot_mi5.py --boot "$DIST/boot-mi5-droidspaces.img" \
        --template bootimg/mi5_boot.img --image "$IMAGE" | tee "$DIST/verify-boot.txt"
    ( cd "$DIST" && sha256sum boot-mi5-droidspaces.img Image-release > SHA256SUMS.txt )
    cat "$DIST/SHA256SUMS.txt"
fi

echo "== done: variant=$VARIANT out=$OUT"
