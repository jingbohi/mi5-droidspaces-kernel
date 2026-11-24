#!/usr/bin/env python3
"""Repack the Mi 5 (gemini) boot.img with a new kernel, keeping everything else.

Stock layout (Android boot header v0, MIUI 10 / Android 8.0):

    page 0          : ANDROID! header (4096 B)
    +4096           : kernel = gzip(Image) || 20 concatenated DTBs
    page-aligned    : ramdisk (gzip), untouched
    page-aligned    : second stage (size 0)
    page-aligned    : 1354-byte Qualcomm certificate blob

Only the gzip part of the kernel section is replaced; the DTB tail, the
ramdisk, the second stage and the certificate are copied byte for byte from
the template.  The header id digest is recomputed the way mkbootimg does it.

    python3 tools/pack_boot_mi5.py --template mi5_boot.img \
        --image Image --out boot-mi5-droidspaces.img
"""
import argparse
import gzip
import hashlib
import io
import struct
import sys
import zlib

PAGE = 4096


def align(n, page=PAGE):
    return (n + page - 1) // page * page


def parse_header(d):
    fields = struct.unpack("<8s10I", d[:48])
    magic, ksize, kaddr, rsize, raddr, ssize, saddr, tags, page, hver, osver = fields
    if magic != b"ANDROID!":
        sys.exit("not an Android boot image")
    if hver != 0:
        sys.exit("unexpected header version %d (this tool is for v0)" % hver)
    if page != PAGE:
        sys.exit("unexpected page size %d" % page)
    return dict(ksize=ksize, kaddr=kaddr, rsize=rsize, raddr=raddr, ssize=ssize,
                saddr=saddr, tags=tags, osver=osver)


def split_kernel_section(section):
    """Return (gzip_bytes, dtb_tail) from the stock kernel section."""
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    d.decompress(section)
    if not d.eof:
        sys.exit("stock kernel section does not start with a complete gzip stream")
    tail = d.unused_data
    return section[:len(section) - len(tail)], tail


def boot_id(kernel, ramdisk, second):
    h = hashlib.sha1()
    h.update(kernel)
    h.update(struct.pack("<I", len(kernel)))
    h.update(ramdisk)
    h.update(struct.pack("<I", len(ramdisk)))
    h.update(second)
    h.update(struct.pack("<I", len(second)))
    return h.digest() + b"\x00" * 12


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--out-size", type=int, default=0,
                    help="pad the output to this size (0 = keep stock size)")
    args = ap.parse_args()

    tpl = open(args.template, "rb").read()
    image = open(args.image, "rb").read()
    hdr = parse_header(tpl)

    if struct.unpack("<8s", tpl[:8])[0] != b"ANDROID!":
        sys.exit("bad template")
    ko = PAGE
    ksec = tpl[ko:ko + hdr["ksize"]]
    ro = ko + align(hdr["ksize"])
    ramdisk = tpl[ro:ro + hdr["rsize"]]
    so = ro + align(hdr["rsize"])
    second = tpl[so:so + hdr["ssize"]]
    trailer_off = so + align(hdr["ssize"])
    trailer = tpl[trailer_off:]

    stock_gz, dtb_tail = split_kernel_section(ksec)
    md5_img = hashlib.md5(image).hexdigest()
    print("template      : %s (%d B)" % (args.template, len(tpl)))
    print("  kernel      : %d B (gzip %d + dtb %d)" % (len(ksec), len(stock_gz), len(dtb_tail)))
    print("  ramdisk     : %d B md5 %s" % (len(ramdisk), hashlib.md5(ramdisk).hexdigest()[:12]))
    print("  trailer     : %d B" % len(trailer))
    print("new Image     : %d B md5 %s" % (len(image), md5_img))

    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as gz:
        gz.write(image)
    new_gz = buf.getvalue()
    new_ksec = new_gz + dtb_tail
    print("new kernel    : %d B (gzip %d + dtb %d), %+d B"
          % (len(new_ksec), len(new_gz), len(dtb_tail), len(new_ksec) - len(ksec)))

    new_hdr = bytearray(tpl[:PAGE])
    struct.pack_into("<I", new_hdr, 8, len(new_ksec))          # kernel_size
    struct.pack_into("<I", new_hdr, 16, len(ramdisk))          # ramdisk_size (unchanged)
    struct.pack_into("<I", new_hdr, 24, len(second))           # second_size
    new_hdr[576:608] = boot_id(new_ksec, ramdisk, second)

    payload = bytes(new_hdr) + new_ksec + b"\x00" * (align(len(new_ksec)) - len(new_ksec))
    payload += ramdisk + b"\x00" * (align(len(ramdisk)) - len(ramdisk))
    payload += second + b"\x00" * (align(len(second)) - len(second))
    out = payload + trailer

    total = args.out_size or len(out)
    if len(out) > total:
        sys.exit("output %d B does not fit in %d B" % (len(out), total))
    out += b"\x00" * (total - len(out))

    with open(args.out, "wb") as f:
        f.write(out)

    print("output        : %s (%d B)" % (args.out, len(out)))
    print("  kernel at   : %d, ramdisk at %d, trailer at %d"
          % (PAGE, PAGE + align(len(new_ksec)), PAGE + align(len(new_ksec)) + align(len(ramdisk))))
    print("  md5         : %s" % hashlib.md5(out).hexdigest())
    print("  sha256      : %s" % hashlib.sha256(out).hexdigest())


if __name__ == "__main__":
    main()
