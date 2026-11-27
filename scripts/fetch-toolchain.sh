#!/usr/bin/env bash
# Fetch the AOSP aarch64 gcc 4.9 prebuilt that this kernel must be built with.
#
# The ROM Image reports "gcc version 4.9.x 20150123 (prerelease)".  An Image
# built with a modern distro compiler (gcc 9.4 from Ubuntu 20.04) never reaches
# console_init() on the real MSM8996: the phone shows the MI logo, hangs, and
# reboots after ~10 s.  The same tree, config, patches and packer built with
# this toolchain boot normally.  See docs/BUILD-AND-QEMU.md, section
# "Toolchain: why gcc 4.9".
#
#   scripts/fetch-toolchain.sh [dir]
#
# Default target: .work/aarch64-linux-android-4.9 (git-ignored).
# Download order: direct -> local proxy (1081) -> GitHub proxy.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
DIR=${1:-${TOOLCHAIN_DIR:-"$ROOT/.work/aarch64-linux-android-4.9"}}
REPO_URL="https://github.com/LineageOS/android_prebuilts_gcc_linux-x86_aarch64_aarch64-linux-android-4.9"
# AOSP's own copy is behind android.googlesource.com, which is not reliably
# reachable from CN; the LineageOS mirror is a byte-identical prebuilt tree.
GH_PROXIES="https://ghfast.top/ https://gh-proxy.com/"

have_toolchain() { [ -x "$DIR/bin/aarch64-linux-android-gcc" ]; }

report_version() {
    local out
    if ! out=$("$DIR/bin/aarch64-linux-android-gcc" --version 2>&1); then
        echo "!! the prebuilt compiler does not run on this host:" >&2
        echo "$out" >&2
        echo "   it is a Python wrapper: make sure a 'python' exists in PATH" >&2
        echo "   (Ubuntu 20.04: apt-get install -y python-is-python3)" >&2
        exit 1
    fi
    echo "== compiler: $(echo "$out" | head -1)"
    case "$out" in
        *4.9.x*) : ;;
        *) echo "!! expected a 4.9.x compiler, got the line above" >&2; exit 1 ;;
    esac
}

if have_toolchain; then
    echo "== toolchain already present: $DIR"
    report_version
    exit 0
fi

# Local proxy candidates.  In WSL2 127.0.0.1 is not the Windows host, so derive
# the host address from the resolver instead of hardcoding 172.x.
proxy_candidates() {
    local list="" p ip
    for p in "${HTTPS_PROXY:-}" "${https_proxy:-}" "${HTTP_PROXY:-}" "${http_proxy:-}"; do
        [ -n "$p" ] && list="$list $p"
    done
    list="$list http://127.0.0.1:1081"
    if grep -qi microsoft /proc/version 2>/dev/null; then
        ip=$(awk '/^nameserver/{print $2; exit}' /etc/resolv.conf 2>/dev/null || true)
        [ -n "$ip" ] && list="$list http://$ip:1081"
    fi
    printf '%s\n' $list | awk '!seen[$0]++'
}

mkdir -p "$(dirname "$DIR")"
PART="$DIR.part"
export GIT_TERMINAL_PROMPT=0

clone_try() {
    # clone_try <description> [git -c key=value ...] -- <url>
    local desc=$1; shift
    local gitcfg=()
    while [ "$1" != "--" ]; do gitcfg+=("$1"); shift; done
    shift
    local url=$1
    rm -rf "$PART"
    echo "-- $desc"
    echo "   $url"
    if timeout 900 git "${gitcfg[@]}" clone --depth 1 --single-branch \
            "$url" "$PART" 2>&1 | tail -3; then
        [ -x "$PART/bin/aarch64-linux-android-gcc" ] && return 0
    fi
    rm -rf "$PART"
    return 1
}

ok=0
clone_try "direct" -- "$REPO_URL" && ok=1

if [ $ok -eq 0 ]; then
    while read -r p; do
        [ -n "$p" ] || continue
        clone_try "via proxy $p" -c "http.proxy=$p" -- "$REPO_URL" && { ok=1; break; }
    done <<< "$(proxy_candidates)"
fi

if [ $ok -eq 0 ]; then
    for gp in $GH_PROXIES; do
        clone_try "via $gp" -- "$gp$REPO_URL" && { ok=1; break; }
    done
fi

if [ $ok -eq 0 ]; then
    echo "!! could not download the toolchain." >&2
    echo "   Download it manually and unpack it at: $DIR" >&2
    echo "   $REPO_URL" >&2
    exit 1
fi

rm -rf "$DIR"
mv "$PART" "$DIR"
echo "== installed $DIR ($(du -sh "$DIR" | cut -f1))"
report_version
