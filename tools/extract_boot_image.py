#!/usr/bin/env python3
"""Extract the Image from a Mi 5 boot image and print its build identity.

    python3 tools/extract_boot_image.py <boot.img> <out Image>

The boot image is the stock ANDROID! v0 layout: header page 0, then
gzip(Image) || DTBs.  The gzip stream ends on its own, so zlib tells us where
the Image stops and the DTB chain begins.
"""
import struct
import sys
import zlib

boot, out = sys.argv[1], sys.argv[2]
data = open(boot, 'rb').read()

assert data[:8] == b'ANDROID!', 'not an Android boot image'
page = struct.unpack_from('<I', data, 36)[0]
kernel_size = struct.unpack_from('<I', data, 8)[0]
kernel = data[page:page + kernel_size]

d = zlib.decompressobj(16 + zlib.MAX_WBITS)
image = d.decompress(kernel)
assert d.eof, 'gzip stream did not terminate inside the kernel section'
open(out, 'wb').write(image)

print('boot image   : %s (%d B)' % (boot, len(data)))
print('page size    : %d' % page)
print('kernel_size  : %d B (gzip %d + dtb %d)' % (
    kernel_size, len(kernel) - len(d.unused_data), len(d.unused_data)))
print('Image        : %d B -> %s' % (len(image), out))
