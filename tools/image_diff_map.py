#!/usr/bin/env python3
"""Where do two arm64 Images differ?

    python3 tools/image_diff_map.py a.img b.img

Prints the differing byte runs and which ELF-ish section they fall in, so a
"same source, different build stamp" difference can be told apart from a real
code change.
"""
import sys

a = open(sys.argv[1], "rb").read()
b = open(sys.argv[2], "rb").read()
print("sizes: %d vs %d" % (len(a), len(b)))
if len(a) != len(b):
    print("size mismatch")

runs = []
i, n = 0, min(len(a), len(b))
while i < n:
    if a[i] != b[i]:
        j = i
        while j < n and a[j] != b[j]:
            j += 1
        runs.append((i, j))
        i = j
    else:
        i += 1

total = sum(e - s for s, e in runs)
print("differing bytes: %d in %d runs" % (total, len(runs)))
for s, e in runs:
    sa = a[s:e]
    sb = b[s:e]
    pa = "".join(chr(c) if 32 <= c < 127 else "." for c in sa)
    pb = "".join(chr(c) if 32 <= c < 127 else "." for c in sb)
    print("  %#010x +%-5d  %s  ->  %s" % (s, e - s, pa, pb))
