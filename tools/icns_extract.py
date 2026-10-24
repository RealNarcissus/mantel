"""Extract embedded PNG/JPEG payloads from an Apple .icns container."""
import struct, sys, os
data = open(sys.argv[1], "rb").read()
assert data[:4] == b"icns", "not an icns"
total = struct.unpack(">I", data[4:8])[0]
off, out = 8, []
os.makedirs(sys.argv[2], exist_ok=True)
while off < min(total, len(data)):
    typ = data[off:off+4].decode("latin1"); size = struct.unpack(">I", data[off+4:off+8])[0]
    if size < 8: break
    payload = data[off+8:off+size]
    ext = "png" if payload[:8] == b"\x89PNG\r\n\x1a\n" else ("jpg" if payload[:3] == b"\xff\xd8\xff" else "raw")
    if ext != "raw":
        p = os.path.join(sys.argv[2], f"{typ}.{ext}")
        open(p, "wb").write(payload); out.append((typ, size, ext))
    off += size
for t, s, e in out: print(f"  {t} {s:>8} {e}")
print("payloads:", len(out))
