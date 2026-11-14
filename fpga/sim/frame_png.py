#!/usr/bin/env python3
"""
Render frame-buffer dumps (1024 bytes = 64x16 Model I screen) as a PNG.

  python frame_png.py frames.txt out.png [frame numbers...]

Block-graphics cells (0x80-0xBF) are drawn as their 2x3 pixels (white);
text cells are drawn as a dim green box with the character's code shape
approximated by a filled box, so text and graphics can be told apart.
Several frames are stacked vertically with a gap. Pure standard library.
"""
import struct
import sys
import zlib

SCALE = 4                       # screen pixel -> PNG pixels (2x3 cell = 8x12... per pixel)
PX_W, PX_H = 4, 6               # Model I pixels are tall: 128x48 on a 4:3 screen


def load(path):
    with open(path) as f:
        b = [int(l, 16) for l in f if l.strip()]
    return [b[i:i + 1024] for i in range(0, len(b), 1024)]


def frame_rgb(fr):
    W, H = 128 * PX_W, 48 * PX_H
    img = [[(10, 10, 10)] * W for _ in range(H)]
    for cell, code in enumerate(fr):
        row, col = divmod(cell, 64)
        if 0x80 <= code <= 0xBF:
            for bit in range(6):
                if code & (1 << bit):
                    px, py = col * 2 + (bit & 1), row * 3 + bit // 2
                    for y in range(py * PX_H, (py + 1) * PX_H):
                        for x in range(px * PX_W, (px + 1) * PX_W):
                            img[y][x] = (235, 235, 235)
        elif code != 0x20:
            x0, y0 = col * 2 * PX_W, row * 3 * PX_H
            for y in range(y0 + 2, y0 + 3 * PX_H - 2):
                for x in range(x0 + 1, x0 + 2 * PX_W - 1):
                    img[y][x] = (40, 170, 70)
    return img


def write_png(path, rows):
    h, w = len(rows), len(rows[0])
    raw = b"".join(b"\x00" + bytes(c for px in r for c in px) for r in rows)
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + \
          chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def main():
    frames = load(sys.argv[1])
    sel = [int(a) for a in sys.argv[3:]] or list(range(len(frames)))
    out = []
    for n in sel:
        img = frame_rgb(frames[n])
        if out:
            out += [[(60, 60, 60)] * len(img[0]) for _ in range(8)]
        out += img
    write_png(sys.argv[2], out)
    print("wrote %s (%d frames)" % (sys.argv[2], len(sel)))


if __name__ == "__main__":
    main()
