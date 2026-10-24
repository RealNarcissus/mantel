#!/usr/bin/env python3
"""Extract ObjC/Swift runtime-metadata sections from a Mach-O binary.

Used for the evidence cited in RE_REPORT.md (class map, selectors, reflection
strings). Usage: python3 scripts/extract_macho_metadata.py <macho> <outdir>
"""
import struct
import sys
import os

WANT = [
    ('__TEXT', '__objc_classname'),
    ('__TEXT', '__objc_methname'),
    ('__TEXT', '__swift5_reflstr'),
    ('__TEXT', '__swift5_typeref'),
    ('__TEXT', '__const'),
]


def sections(buf):
    magic, _, _, _, ncmds, _, _, _ = struct.unpack_from('<IiiIIIII', buf, 0)
    if magic != 0xfeedfacf:
        raise SystemExit('not a Mach-O 64-bit little-endian binary')
    off, out = 32, {}
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', buf, off)
        if cmd == 0x19:  # LC_SEGMENT_64
            nsects = struct.unpack_from('<I', buf, off + 64)[0]
            so = off + 72
            for _ in range(nsects):
                name = buf[so:so + 16].split(b'\0')[0].decode()
                seg = buf[so + 16:so + 32].split(b'\0')[0].decode()
                size = struct.unpack_from('<Q', buf, so + 40)[0]
                fileoff = struct.unpack_from('<I', buf, so + 48)[0]
                out[(seg, name)] = (fileoff, size)
                so += 80
        off += cmdsize
    return out


def main():
    src, dst = sys.argv[1], sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    buf = open(src, 'rb').read()
    secs = sections(buf)
    for key in WANT:
        if key not in secs:
            print(f'{key[0]},{key[1]}: MISSING')
            continue
        fileoff, size = secs[key]
        raw = buf[fileoff:fileoff + size]
        path = os.path.join(dst, f'{key[0]}_{key[1]}.bin')
        open(path, 'wb').write(raw)
        n = sum(1 for s in raw.split(b'\0') if len(s) >= 3)
        print(f'{key[0]},{key[1]}: {size} bytes, {n} strings -> {path}')


if __name__ == '__main__':
    main()
