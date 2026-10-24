#!/usr/bin/env python3
"""Extract the PNG/JPEG payloads embedded in an Apple `.icns` container.

This is how the app's icon assets were recovered from the shipped artifact; the
extracted images themselves are not tracked. Usage:

    python3 tools/icns_extract.py Icon.icns out-dir/
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"


def payload_kind(payload: bytes) -> str:
    if payload.startswith(PNG_MAGIC):
        return "png"
    if payload.startswith(JPEG_MAGIC):
        return "jpg"
    return "raw"


def extract(container: Path, destination: Path) -> list[tuple[str, int, str]]:
    data = container.read_bytes()
    if data[:4] != b"icns":
        raise ValueError(f"{container} is not an icns file")
    total = struct.unpack(">I", data[4:8])[0]
    destination.mkdir(parents=True, exist_ok=True)
    written: list[tuple[str, int, str]] = []
    offset = 8
    while offset < min(total, len(data)):
        kind = data[offset:offset + 4].decode("latin1")
        size = struct.unpack(">I", data[offset + 4:offset + 8])[0]
        if size < 8:
            break
        payload = data[offset + 8:offset + size]
        extension = payload_kind(payload)
        if extension != "raw":
            (destination / f"{kind}.{extension}").write_bytes(payload)
            written.append((kind, size, extension))
        offset += size
    return written


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    written = extract(Path(argv[1]), Path(argv[2]))
    for kind, size, extension in written:
        print(f"  {kind} {size:>8} {extension}")
    print(f"payloads: {len(written)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
