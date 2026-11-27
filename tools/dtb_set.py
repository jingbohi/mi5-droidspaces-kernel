#!/usr/bin/env python3
"""Compare the appended DTB chain of two Mi 5 boot images as a set.

    python3 tools/dtb_set.py a.img b.img

Prints each DTB's size and md5 in both images and whether the two chains hold
the same device trees (possibly in a different order).
"""
import hashlib
import struct
import sys
import zlib


def chain(path):
    d = open(path, "rb").read()
    page = struct.unpack_from("<I", d, 36)[0]
    ksize = struct.unpack_from("<I", d, 8)[0]
    ksec = d[page:page + ksize]
    dg = zlib.decompressobj(16 + zlib.MAX_WBITS)
    dg.decompress(ksec)
    tail = dg.unused_data
    out, off = [], 0
    while off + 40 <= len(tail):
        magic, total = struct.unpack(">II", tail[off:off + 8])
        if magic != 0xD00DFEED or total <= 0 or off + total > len(tail):
            break
        blob = tail[off:off + total]
        out.append((total, hashlib.md5(blob).hexdigest()))
        off += total
    return out


a, b = chain(sys.argv[1]), chain(sys.argv[2])
for name, c in ((sys.argv[1], a), (sys.argv[2], b)):
    print("%s: %d DTBs" % (name, len(c)))
    for i, (size, md5) in enumerate(c):
        print("  %2d  %7d  %s" % (i, size, md5))

sa, sb = set(a), set(b)
print("\nsame set of device trees: %s" % ("yes" if sa == sb else "NO"))
print("same order             : %s" % ("yes" if a == b else "no"))
if sa != sb:
    print("only in first : %s" % (sa - sb))
    print("only in second: %s" % (sb - sa))
