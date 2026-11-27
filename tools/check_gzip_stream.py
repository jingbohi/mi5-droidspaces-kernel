#!/usr/bin/env python3
"""Check the gzip stream inside a boot image the way the kernel's decompressor
sees it: locate the stream, inflate it, and compare the trailing CRC32/ISIZE
with the real values."""
import struct
import sys
import zlib

def check(path):
    d = open(path, "rb").read()
    page = 4096
    ksize = struct.unpack_from("<I", d, 8)[0]
    start = page
    stream = d[start:start + ksize]

    dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = dec.decompress(stream)
    out += dec.flush()
    print(f"{path}")
    print(f"  inflated      {len(out)} B, eof={dec.eof}, unused={len(dec.unused_data)} B")
    consumed = len(stream) - len(dec.unused_data)
    print(f"  stream length {consumed} B (kernel section {ksize} B, tail {ksize - consumed} B)")
    trailer = stream[consumed - 8:consumed]
    crc, isize = struct.unpack("<II", trailer)
    print(f"  trailer CRC32 {crc:#010x} ISIZE {isize} (expected CRC32 {zlib.crc32(out) & 0xffffffff:#010x} ISIZE {len(out) & 0xffffffff})")
    print(f"  -> {'OK' if crc == zlib.crc32(out) & 0xffffffff and isize == len(out) & 0xffffffff else 'MISMATCH'}")

for p in sys.argv[1:]:
    check(p)
