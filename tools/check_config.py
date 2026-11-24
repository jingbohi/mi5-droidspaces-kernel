#!/usr/bin/env python3
"""Check the resolved .config and the kernel release string of a build.

    python3 tools/check_config.py --config out/.config \
        --release out/include/config/kernel.release \
        [--layer config/droidspaces.layer] \
        [--stock config/stock-resolved.config] [--diff-out dist/config-diff.txt]

Every symbol in the layer file must end up in .config with exactly the value the
layer asked for (that is how "cannot exist on 3.18" is caught), and the release
string must reproduce the stock vermagic prefix.  Exits non-zero on failure.
"""
import argparse
import os
import sys

from mi5_config import parse_layer

EXPECTED_RELEASE = "3.18.71-perf-g4a0ef96"

# Symbols the other options imply; reported because they are the ones the
# container runtime actually probes at start-up.
INFO = ["SYSCTL", "NF_NAT", "NF_NAT_IPV4", "NF_NAT_IPV6", "SECCOMP_FILTER",
        "HAVE_ARCH_SECCOMP_FILTER", "CGROUP_NS", "CGROUP_PIDS"]


def parse_config(path):
    vals = {}
    disabled = set()
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("# CONFIG_") and line.endswith(" is not set"):
            disabled.add(line[len("# CONFIG_"):-len(" is not set")])
            continue
        if line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.startswith("CONFIG_"):
            vals[k[len("CONFIG_"):]] = v
    for sym in disabled:
        vals.setdefault(sym, "n")
    return vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--release", required=True)
    ap.add_argument("--layer", default="")
    ap.add_argument("--stock", default="")
    ap.add_argument("--diff-out", default="")
    args = ap.parse_args()

    cfg = parse_config(args.config)
    failed = []

    print("layer options:")
    for sym, want in parse_layer(args.layer):
        got = cfg.get(sym, "n")
        ok = got == want
        print("  %s %-32s %s" % ("PASS" if ok else "FAIL", sym, got))
        if not ok:
            failed.append("%s: want %s, got %s" % (sym, want, got))

    print("implied:")
    for sym in INFO:
        print("  %-34s %s" % (sym, cfg.get(sym, "n")))

    if not os.path.isfile(args.release):
        sys.exit("missing %s -- run `make prepare` first" % args.release)
    rel = open(args.release, encoding="utf-8", errors="replace").read().strip()
    ok = rel == EXPECTED_RELEASE
    print("release string: %s %s" % ("PASS" if ok else "FAIL", rel))
    if not ok:
        failed.append("kernel.release: want %s, got %s" % (EXPECTED_RELEASE, rel))

    if args.stock:
        stock = parse_config(args.stock)
        lines = []
        for sym in sorted(set(stock) | set(cfg)):
            a, b = stock.get(sym, "n"), cfg.get(sym, "n")
            if a != b:
                lines.append("%-52s %-22s -> %s" % ("CONFIG_" + sym, a, b))
        print("\nconfig diff vs stock: %d option(s)" % len(lines))
        for line in lines:
            print("  " + line)
        if args.diff_out:
            os.makedirs(os.path.dirname(args.diff_out) or ".", exist_ok=True)
            with open(args.diff_out, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            print("written: " + args.diff_out)

    if failed:
        print("\nRESULT: FAIL")
        for f in failed:
            print("  - " + f)
        return 1
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
