#!/usr/bin/env python3
"""Per-module import table: imports / missing / mismatched, for the build report."""
import os
import sys

symvers = sys.argv[1]
dumps = sys.argv[2]
vendor = sys.argv[3] if len(sys.argv) > 3 else None

exported = {}
for line in open(symvers, encoding="utf-8", errors="replace"):
    p = line.rstrip("\n").split("\t")
    if len(p) >= 2:
        exported[p[1]] = int(p[0], 16)

vend = set()
if vendor and os.path.isdir(vendor):
    for fn in os.listdir(vendor):
        if fn.endswith(".ko"):
            vend.add(fn[:-3])

rows = []
for fn in sorted(os.listdir(dumps)):
    if not fn.endswith(".versions"):
        continue
    mod = fn[:-len(".versions")]
    imports = missing = bad = 0
    for line in open(os.path.join(dumps, fn), encoding="utf-8", errors="replace"):
        p = line.rstrip("\n").split("\t")
        if len(p) != 2:
            continue
        imports += 1
        crc, name = int(p[0], 16), p[1]
        if name not in exported:
            missing += 1
        elif exported[name] != crc:
            bad += 1
    rows.append((mod, imports, missing, bad, "rom" if mod in vend else "extra"))

print("%-16s %8s %8s %8s  %s" % ("module", "imports", "missing", "crc-diff", "origin"))
ti = tm = tb = 0
for mod, imports, missing, bad, origin in rows:
    print("%-16s %8d %8d %8d  %s" % (mod, imports, missing, bad, origin))
    ti += imports
    tm += missing
    tb += bad
print("%-16s %8d %8d %8d" % ("TOTAL", ti, tm, tb))
print("\nROM module dir: %s (%d .ko files)" % (vendor, len(vend)))
