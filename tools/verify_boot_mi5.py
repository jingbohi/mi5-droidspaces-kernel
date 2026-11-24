#!/usr/bin/env python3
"""Check that a repacked Mi 5 boot.img only changed the kernel payload.

    python3 tools/verify_boot_mi5.py --boot boot-mi5-droidspaces.img \
        --template mi5_boot.img --image Image

Every check must pass; any failure exits non-zero.
"""
import argparse
import hashlib
import struct
import sys
import zlib

PAGE = 4096
FAILED = []


def align(n, page=PAGE):
    return (n + page - 1) // page * page


def check(ok, label, detail=""):
    print("  %s  %s%s" % ("PASS" if ok else "FAIL", label, ("  " + detail) if detail else ""))
    if not ok:
        FAILED.append(label)


def boot_id(kernel, ramdisk, second):
    h = hashlib.sha1()
    h.update(kernel)
    h.update(struct.pack("<I", len(kernel)))
    h.update(ramdisk)
    h.update(struct.pack("<I", len(ramdisk)))
    h.update(second)
    h.update(struct.pack("<I", len(second)))
    return h.digest() + b"\x00" * 12


def layout(d):
    magic, ksize, kaddr, rsize, raddr, ssize, saddr, tags, page, hver, osver = \
        struct.unpack("<8s10I", d[:48])
    ko = page
    ro = ko + align(ksize, page)
    so = ro + align(rsize, page)
    to = so + align(ssize, page)
    return dict(magic=magic, ksize=ksize, kaddr=kaddr, rsize=rsize, raddr=raddr,
                ssize=ssize, saddr=saddr, tags=tags, page=page, hver=hver,
                osver=osver, ko=ko, ro=ro, so=so, to=to,
                cmdline=d[64:576].split(b"\x00")[0],
                name=d[48:64].split(b"\x00")[0],
                ident=d[576:608], extra=d[608:1632].split(b"\x00")[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--image", required=True)
    args = ap.parse_args()

    boot = open(args.boot, "rb").read()
    tpl = open(args.template, "rb").read()
    image = open(args.image, "rb").read()
    b = layout(boot)
    t = layout(tpl)

    print("boot     : %s (%d B)" % (args.boot, len(boot)))
    print("template : %s (%d B)" % (args.template, len(tpl)))
    print("image    : %s (%d B) md5 %s" % (args.image, len(image), hashlib.md5(image).hexdigest()))
    print("checks:")

    check(b["magic"] == b"ANDROID!", "boot magic")
    check(b["hver"] == t["hver"], "header version", str(b["hver"]))
    check(b["page"] == PAGE, "page size", str(b["page"]))

    ksec = boot[b["ko"]:b["ko"] + b["ksize"]]
    tsec = tpl[t["ko"]:t["ko"] + t["ksize"]]

    # gzip part must decode to exactly the new Image; everything after is the stock DTB tail
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = d.decompress(ksec)
    check(d.eof, "kernel gzip stream complete")
    tail = d.unused_data
    tz = zlib.decompressobj(16 + zlib.MAX_WBITS)
    tz.decompress(tsec)
    ttail = tz.unused_data
    check(out == image, "kernel decompresses to Image", "md5 %s" % hashlib.md5(out).hexdigest())
    check(tail == ttail, "DTB tail identical to template", "%d B" % len(tail))
    off, n = 0, 0
    while off + 40 <= len(tail) and struct.unpack(">I", tail[off:off + 4])[0] == 0xd00dfeed:
        off += struct.unpack(">I", tail[off + 4:off + 8])[0]
        n += 1
    check(off == len(tail) and n > 0, "DTB tail parses as FDT chain", "%d DTBs" % n)

    check(ksec[:2] == b"\x1f\x8b", "kernel section starts with gzip magic")
    check(boot[b["ko"] + b["ksize"]:b["ro"]] == b"\x00" * (b["ro"] - b["ko"] - b["ksize"]),
          "kernel page padding zeroed")

    ramdisk = boot[b["ro"]:b["ro"] + b["rsize"]]
    tramdisk = tpl[t["ro"]:t["ro"] + t["rsize"]]
    check(b["rsize"] == t["rsize"], "ramdisk size unchanged", "%d B" % b["rsize"])
    check(ramdisk == tramdisk, "ramdisk bytes unchanged", "md5 %s" % hashlib.md5(ramdisk).hexdigest())

    check(b["ssize"] == 0, "second stage size 0", str(b["ssize"]))
    check(boot[b["so"]:b["to"]] == tpl[t["so"]:t["to"]], "second stage area unchanged")

    trailer = boot[b["to"]:]
    ttrailer = tpl[t["to"]:]
    check(trailer == ttrailer, "certificate trailer unchanged", "%d B" % len(trailer))

    # header fields that must not change
    for key, label in [("kaddr", "kernel_addr"), ("raddr", "ramdisk_addr"),
                       ("saddr", "second_addr"), ("tags", "tags_addr")]:
        check(b[key] == t[key], label + " unchanged", hex(b[key]))
    check(b["osver"] == t["osver"], "os_version unchanged", "0x%08x" % b["osver"])
    check(b["cmdline"] == t["cmdline"], "cmdline unchanged", b["cmdline"].decode("ascii", "replace"))
    check(b["name"] == t["name"], "board name unchanged", b["name"].decode("ascii", "replace"))
    check(b["extra"] == t["extra"], "extra_cmdline unchanged")
    check(b["ident"] == boot_id(ksec, ramdisk, boot[b["so"]:b["so"] + b["ssize"]]),
          "header id digest recomputed correctly")

    # partition limit
    check(len(boot) <= 64 * 1024 * 1024, "fits 64 MiB boot partition", "%d B" % len(boot))
    check(len(boot) >= len(tpl), "not smaller than stock", "%+d B" % (len(boot) - len(tpl)))

    print("result   : %s (%d failed)" % ("PASS" if not FAILED else "FAIL", len(FAILED)))
    if FAILED:
        for f in FAILED:
            print("  - " + f)
        sys.exit(1)


if __name__ == "__main__":
    main()
