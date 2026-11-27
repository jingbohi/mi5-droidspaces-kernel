#!/usr/bin/env python3
"""Compare the arm64 Image headers of two kernels.

    python3 tools/image_header.py a.img b.img

The first 64 bytes of an arm64 Image are a header the bootloader reads: a branch
into the kernel, the load offset, the size of the image and a page-size/endianness
flags word, followed by the "ARM\\x64" magic.  A mismatch there is a bootloader
level problem, not a kernel one.
"""
import struct
import sys


def dump(path):
    d = open(path, 'rb').read()
    magic_at = d.find(b'ARM\x64')
    h = {
        'path': path,
        'size': len(d),
        'code0': struct.unpack_from('<I', d, 0)[0],
        'code1': struct.unpack_from('<I', d, 4)[0],
        'text_offset': struct.unpack_from('<Q', d, 8)[0],
        'image_size': struct.unpack_from('<Q', d, 16)[0],
        'flags': struct.unpack_from('<Q', d, 24)[0],
        'magic_at': magic_at,
    }
    return h


a, b = dump(sys.argv[1]), dump(sys.argv[2])
for k in ('size', 'code0', 'code1', 'text_offset', 'image_size', 'flags', 'magic_at'):
    same = 'same' if a[k] == b[k] else 'DIFF'
    if isinstance(a[k], int) and k != 'size':
        print('%-12s %-14s 0x%08x   0x%08x   %s' % (k, '', a[k], b[k], same))
    else:
        print('%-12s %-14s %-10d %-10d %s' % (k, '', a[k], b[k], same))
print('\n%-12s %s' % ('A', a['path']))
print('%-12s %s' % ('B', b['path']))
print('\nflags: page size bits 0-2 = %d (%s), bit 3 endianness = %d, bits 4-63 reserved' % (
    a['flags'] & 7, '4K' if (a['flags'] & 7) == 0 else '?', (a['flags'] >> 3) & 1))
