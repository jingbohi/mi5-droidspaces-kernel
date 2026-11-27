#!/usr/bin/env python3
"""Audit an Android boot image (v0) at the byte level.

    python3 tools/boot_image_audit.py stock.img ours.img

Checks the things a Qualcomm aboot actually looks at:

  * header fields, name / cmdline / extra_cmdline
  * the SHA1 ``id`` field, recomputed from the sections the way mkbootimg does
  * the gzip stream in front of the appended DTBs: header flags, mtime, XFL,
    OS byte, whether a file name is stored, plus the ISIZE/CRC32 trailer
  * where the appended DTB starts inside the kernel section, its alignment and
    the ``totalsize`` recorded in the FDT header
"""
import hashlib
import struct
import sys
import zlib

PAGE = 4096


def align(n, page=PAGE):
    return (n + page - 1) // page * page


def cstr(b):
    return b.split(b"\x00", 1)[0].decode("utf-8", "replace")


def boot_id(kernel, ramdisk, second):
    h = hashlib.sha1()
    h.update(kernel)
    h.update(struct.pack("<I", len(kernel)))
    h.update(ramdisk)
    h.update(struct.pack("<I", len(ramdisk)))
    h.update(second)
    h.update(struct.pack("<I", len(second)))
    return h.digest() + b"\x00" * 12


def audit(path):
    d = open(path, "rb").read()
    (magic, ksize, kaddr, rsize, raddr, ssize, saddr, tags,
     page, hver, osver) = struct.unpack("<8s10I", d[:48])
    name = cstr(d[48:64])
    cmdline = cstr(d[64:576])
    ident = d[576:608]
    extra = cstr(d[608:1632])

    ko = page
    ksec = d[ko:ko + ksize]
    ro = ko + align(ksize, page)
    ramdisk = d[ro:ro + rsize]
    so = ro + align(rsize, page)
    second = d[so:so + ssize]
    trailer = d[so + align(ssize, page):]

    print("=" * 72)
    print(path)
    print("  file size      %d" % len(d))
    print("  magic          %r" % magic)
    print("  kernel         size %d  addr 0x%08x" % (ksize, kaddr))
    print("  ramdisk        size %d  addr 0x%08x" % (rsize, raddr))
    print("  second         size %d  addr 0x%08x" % (ssize, saddr))
    print("  tags addr      0x%08x" % tags)
    print("  page size      %d" % page)
    print("  header version %d   os_version 0x%08x" % (hver, osver))
    print("  name           %r" % name)
    print("  cmdline        %r" % cmdline)
    print("  extra_cmdline  %r" % extra)
    print("  trailer        %d B at %d" % (len(trailer), so + align(ssize, page)))

    calc = boot_id(ksec, ramdisk, second)
    print("  id (header)    %s" % ident.hex())
    print("  id (computed)  %s   %s" % (calc.hex(), "MATCH" if calc == ident else "MISMATCH"))
    if ident == b"\x00" * 32:
        print("  note           header id is all zero (bootloader ignores it)")

    # --- gzip stream -----------------------------------------------------
    dg = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = dg.decompress(ksec)
    if not dg.eof:
        print("  !! kernel section is not a complete gzip stream")
        return
    gz = ksec[:len(ksec) - len(dg.unused_data)]
    tail = dg.unused_data
    print("  gzip           %d B, inflates to %d B" % (len(gz), len(out)))
    print("  gzip header    %s" % gz[:10].hex(" "))
    flg = gz[3]
    print("    CM=%d FLG=0x%02x (FTEXT=%d FHCRC=%d FEXTRA=%d FNAME=%d FCOMMENT=%d)"
          % (gz[2], flg, flg & 1, flg >> 1 & 1, flg >> 2 & 1, flg >> 3 & 1, flg >> 4 & 1))
    print("    MTIME=%d XFL=%d OS=%d" % (struct.unpack("<I", gz[4:8])[0], gz[8], gz[9]))
    if len(gz) >= 18:
        # the gzip trailer is CRC32 first, then ISIZE (both little endian)
        crc, isize = struct.unpack("<II", gz[-8:])
        print("    ISIZE=%d (actual %d) %s, CRC32=0x%08x (actual 0x%08x) %s"
              % (isize, len(out), "ok" if isize == len(out) % 2 ** 32 else "BAD",
                 crc, zlib.crc32(out) & 0xffffffff,
                 "ok" if crc == zlib.crc32(out) & 0xffffffff else "BAD"))

    # --- appended DTB ----------------------------------------------------
    print("  dtb tail       %d B" % len(tail))
    if len(tail) >= 40:
        magic, totalsize, off_struct, off_strings, off_rsvmap, version, \
            last_comp, boot_cpuid, size_strings, size_struct = struct.unpack(">10I", tail[:40])
        print("    magic        0x%08x %s" % (magic, "ok" if magic == 0xd00dfeed else "BAD"))
        print("    totalsize    %d" % totalsize)
        print("    version      %d (last compatible %d)" % (version, last_comp))
        print("    strings      %d B, struct %d B, rsvmap at %d"
              % (size_strings, size_struct, off_rsvmap))
        print("    dtb start    section offset %d (addr 0x%08x), %d-aligned in the section"
              % (len(gz), kaddr + len(gz), 8 if len(gz) % 8 == 0 else 4 if len(gz) % 4 == 0 else 1))
        # walk the concatenated DTBs
        off, n = 0, 0
        sizes = []
        while off + 40 <= len(tail):
            m, ts = struct.unpack(">II", tail[off:off + 8])
            if m != 0xd00dfeed or ts <= 0 or off + ts > len(tail):
                break
            sizes.append(ts)
            off += ts
            n += 1
        print("    concatenated %d DTBs, %d B total, %d B unparsed"
              % (n, sum(sizes), len(tail) - off))
        if sizes:
            print("    dtb sizes    %s" % sizes)


for p in sys.argv[1:]:
    audit(p)
