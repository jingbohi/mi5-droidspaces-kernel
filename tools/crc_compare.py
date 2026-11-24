#!/usr/bin/env python3
"""Compare the symbols stock vendor modules import with what this kernel exports.

    python3 tools/crc_compare.py --symvers out/Module.symvers \
        --dumps config/vendor-crc [--strict qca_cld_wlan,wil6210,exfat,br_netfilter] \
        [--fail-on-mismatch]

<dumps> holds "<module>.versions" files, one "0xCRC<TAB>symbol" line each, as
produced by `modprobe --dump-modversions`.

Modules named in --strict must not have a single *missing* symbol: a missing
export is a real ABI break and fails the build.

CRC mismatches are reported but do not fail, because this kernel enables the IPC
namespace, which adds fields to struct task_struct and shifts genksyms checksums
for thousands of unrelated exports (patches/02-allow-crc-mismatch.patch makes the
loader accept them).  --fail-on-mismatch restores the strict behaviour, e.g. for
comparing against a build without that patch.
"""
import argparse
import os
import sys


def read_symvers(path):
    syms = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 2:
            syms[parts[1]] = int(parts[0], 16)
    return syms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symvers", required=True)
    ap.add_argument("--dumps", required=True)
    ap.add_argument("--strict", default="")
    ap.add_argument("--fail-on-mismatch", action="store_true")
    args = ap.parse_args()

    strict = set(s.strip() for s in args.strict.split(",") if s.strip())
    exported = read_symvers(args.symvers)
    print("kernel exports: %d symbols" % len(exported))

    total_missing = total_bad = 0
    strict_failed = []
    for fn in sorted(os.listdir(args.dumps)):
        if not fn.endswith(".versions"):
            continue
        mod = fn[:-len(".versions")]
        missing, bad, imports = [], [], 0
        for line in open(os.path.join(args.dumps, fn), encoding="utf-8", errors="replace"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 2:
                continue
            imports += 1
            crc, name = int(parts[0], 16), parts[1]
            if name not in exported:
                missing.append(name)
            elif exported[name] != crc:
                bad.append((name, crc, exported[name]))

        verdict = "OK" if not missing and not bad else "MISSING" if missing else "CRC"
        print("\n== %-16s imports %3d  %s" % (mod, imports, verdict))
        for n in missing:
            print("   MISSING  %s" % n)
        for n, want, got in bad[:40]:
            print("   MISMATCH %-40s module 0x%08x kernel 0x%08x" % (n, want, got))
        if len(bad) > 40:
            print("   ... %d more mismatches" % (len(bad) - 40))
        total_missing += len(missing)
        total_bad += len(bad)
        if mod in strict and missing:
            strict_failed.append(mod)

    print("\nsummary: %d missing, %d mismatched" % (total_missing, total_bad))
    failed = False
    if strict_failed:
        print("strict modules with MISSING exports: %s" % ", ".join(strict_failed))
        failed = True
    if args.fail_on_mismatch and total_bad:
        print("CRC mismatches are fatal (--fail-on-mismatch)")
        failed = True
    if failed:
        return 1
    print("strict modules: %s -- no missing exports" % (", ".join(sorted(strict)) or "(none)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
