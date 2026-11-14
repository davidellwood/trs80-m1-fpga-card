#!/usr/bin/env python3
"""
Raw binary -> TRS-80 /CMD file (TRSDOS / LDOS / NEWDOS load module).

  python bin2cmd.py demo.bin 6000 DEMO.CMD [entry]

Format: 01 len addrlo addrhi data...  (len = data bytes + 2, data <= 252)
        02 02 entrylo entryhi        (transfer address)
"""
import sys


def bin2cmd(data, org, entry):
    out = bytearray()
    for i in range(0, len(data), 252):
        chunk = data[i:i + 252]
        a = org + i
        out += bytes([0x01, len(chunk) + 2, a & 0xFF, a >> 8]) + chunk
    out += bytes([0x02, 0x02, entry & 0xFF, entry >> 8])
    return bytes(out)


if __name__ == "__main__":
    src, org, dst = sys.argv[1], int(sys.argv[2], 16), sys.argv[3]
    entry = int(sys.argv[4], 16) if len(sys.argv) > 4 else org
    data = open(src, "rb").read()
    open(dst, "wb").write(bin2cmd(data, org, entry))
    print("%s: %d bytes at %04X, entry %04X -> %s" % (src, len(data), org, entry, dst))
