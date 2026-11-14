#!/usr/bin/env python3
"""
Reference model of the sprite engine (docs/sprite-engine.md, fpga/src/sprite_engine.v)
and the test scenario that drives both it and the Verilog testbench (tb_sprite.v).

  python sprite_model.py gen    -> vectors.hex, expected_reads.txt, expected_frames.txt
  python sprite_model.py check  -> compares reads.txt / frames.txt from the simulation

Vector word (32-bit hex, one per line): [31:24] op, [23:8] a, [7:0] v
  op 1 OUT port a <- v        op 2 IN port a (recorded)    op 3 wait until not BUSY
  op 4 dump DPRAM 0..1023     op 5 Z80-side DPRAM write    op 6 wait for a new FRAME
  op 7 end
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PARAM, CMD = 0x52, 0x53
VIS, XOR, MX, MY, OPQ, NOC = 1, 2, 4, 8, 16, 32

NEED = {0x00: 0, 0x01: 0, 0x02: 0, 0x08: 1, 0x09: 2, 0x0A: 3, 0x0B: 3, 0x0C: 5,
        0x0D: 6, 0x0E: 2, 0x10: 3, 0x11: 5, 0x20: 5, 0x21: 3, 0x22: 2, 0x23: 2,
        0x24: 3, 0x25: 1, 0x30: 1, 0x40: 0, 0x41: 1, 0xF0: 1, 0xF1: 2, 0xF2: 3}


def s8(v):
    return v - 256 if v & 0x80 else v


class Engine:
    def __init__(self):
        self.dpram = [0x5A] * 2048            # testbench initial contents
        self.err = 0
        self.pf, self.rf = [], []
        self.auto = 0
        self.reset()

    # ------------------------------------------------------------ state --
    def reset(self):
        self.bg = [0x20] * 1024
        self.wk = [0x20] * 1024
        self.shw, self.shh = [0] * 64, [0] * 64
        self.shp = [[0] * 16 for _ in range(64)]
        self.spr = [dict(shape=0, x=0, y=0, dx=0, dy=0, fl=0) for _ in range(32)]
        self.hits = [0] * 32
        self.hit_any = 0
        self.frame = 0
        self.auto = 0

    def status(self):
        return (self.frame << 6) | (self.err << 5) | (self.hit_any << 4) | (1 if self.rf else 0)

    # ------------------------------------------------------------ ports --
    def out(self, port, v):
        if port == PARAM:
            if len(self.pf) == 64:
                self.err = 1
            else:
                self.pf.append(v)
        elif port == CMD:
            self.err = 0
            params, self.pf = self.pf, []      # all pushed params belong to it
            self.command(v, params)

    def inp(self, port):
        if port == PARAM:
            if self.rf:
                return self.rf.pop(0)
            self.err = 1
            return 0xFF
        if port == CMD:
            return self.status()
        raise ValueError(port)

    # ------------------------------------------------------------ pixels --
    def _cell(self, x, y):
        return (y // 3) * 64 + (x >> 1), (y % 3) * 2 + (x & 1)

    def _op(self, bits, b, op):
        m = 1 << b
        return bits & ~m if op == 0 else bits | m if op == 1 else bits ^ m

    def bg_pixel(self, buf, x, y, op):
        if not (0 <= x < 128 and 0 <= y < 48):
            return
        c, b = self._cell(x, y)
        old = buf[c]
        bits = old & 0x3F if 0x80 <= old <= 0xBF else 0
        buf[c] = 0x80 | (self._op(bits, b, op) & 0x3F)

    def spr_pixel(self, x, y, op):
        c, b = self._cell(x, y)
        old = self.wk[c]
        if 0x80 <= old <= 0xBF:
            bits = old & 0x3F
        elif old == 0x20:
            bits = 0
        else:
            return                              # text is left alone
        self.wk[c] = 0x80 | (self._op(bits, b, op) & 0x3F)

    # ------------------------------------------------------------ commands --
    def command(self, c, p):
        if c not in NEED or len(p) < NEED[c]:
            self.err = 1
            return
        a = p
        if c == 0x00:
            pass
        elif c == 0x01:
            self.pf, self.rf = [], []
            self.reset()
        elif c == 0x02:
            self.rf += [0, 2, 32, 64]
        elif c == 0x08:
            self.bg = [a[0]] * 1024
        elif c == 0x09:
            src = ((a[1] & 7) << 8) | a[0]
            self.bg = [self.dpram[(src + i) & 0x7FF] for i in range(1024)]
        elif c == 0x0A:
            if a[0] >= 64 or a[1] >= 16:
                self.err = 1
            else:
                self.bg[a[1] * 64 + a[0]] = a[2]
        elif c == 0x0B:
            if a[2] > 2:
                self.err = 1
            else:
                self.bg_pixel(self.bg, a[0], a[1], a[2])
        elif c == 0x0C:
            if a[4] > 2:
                self.err = 1
            else:
                self.line(a[0], a[1], a[2], a[3], a[4])
        elif c == 0x0D:
            x, y, w, h, mode, fill = a[:6]
            if mode > 2:
                self.err = 1
            else:
                for bi in range(h):
                    for bj in range(w):
                        if fill or bi in (0, h - 1) or bj in (0, w - 1):
                            self.bg_pixel(self.bg, x + bj, y + bi, mode)
        elif c == 0x0E:
            dx, dy = s8(a[0]), s8(a[1])
            old = self.bg[:]
            for r in range(16):
                for col in range(64):
                    sr, sc = r - dy, col - dx
                    self.bg[r * 64 + col] = old[sr * 64 + sc] if 0 <= sr < 16 and 0 <= sc < 64 else 0x20
        elif c == 0x10:
            i, w, h = a[0], a[1], a[2]
            if i >= 64 or not 1 <= w <= 16 or not 1 <= h <= 15 or len(p) < 3 + 2 * h:
                self.err = 1
            else:
                self.shw[i], self.shh[i] = w, h
                for r in range(h):
                    self.shp[i][r] = (p[3 + 2 * r] << 8) | p[4 + 2 * r]
        elif c == 0x11:
            i, w, h = a[0], a[1], a[2]
            if i >= 64 or not 1 <= w <= 16 or not 1 <= h <= 15:
                self.err = 1
            else:
                src = ((a[4] & 7) << 8) | a[3]
                self.shw[i], self.shh[i] = w, h
                for r in range(h):
                    self.shp[i][r] = (self.dpram[(src + 2 * r) & 0x7FF] << 8) | \
                                     self.dpram[(src + 2 * r + 1) & 0x7FF]
        elif c in (0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x30):
            n = a[0]
            if n >= 32 or (c in (0x20, 0x23) and a[1] >= 64):
                self.err = 1
                return
            s = self.spr[n]
            if c == 0x20:
                s.update(shape=a[1], x=a[2], y=a[3], fl=a[4] & 0x3F)
            elif c == 0x21:
                s.update(x=a[1], y=a[2])
            elif c == 0x22:
                s['fl'] = a[1] & 0x3F
            elif c == 0x23:
                s['shape'] = a[1]
            elif c == 0x24:
                s.update(dx=a[1], dy=a[2])
            elif c == 0x25:
                self.rf += [s['x'], s['y']]
            elif c == 0x30:
                h = self.hits[n]
                self.rf += [h & 255, (h >> 8) & 255, (h >> 16) & 255, (h >> 24) & 255]
        elif c == 0x40:
            self.render()
        elif c == 0x41:
            self.auto = a[0]
        elif c == 0xF0:
            for i in range(1024):
                self.dpram[i] = a[0]
            self.frame = 1
        elif c == 0xF1:
            self.rf.append(self.dpram[((a[1] & 7) << 8) | a[0]])
        elif c == 0xF2:
            self.dpram[((a[1] & 7) << 8) | a[0]] = a[2]

    def line(self, x0, y0, x1, y1, mode):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.bg_pixel(self.bg, x0, y0, mode)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def render(self):
        self.frame = 0
        self.hit_any = 0
        self.hits = [0] * 32
        for s in self.spr:
            s['x'] = (s['x'] + s['dx']) & 255
            s['y'] = (s['y'] + s['dy']) & 255
        self.wk = self.bg[:]
        own = [0] * 6144
        for n, s in enumerate(self.spr):
            sh, fl = s['shape'], s['fl']
            w, h = self.shw[sh], self.shh[sh]
            if not fl & VIS or w == 0 or h == 0:
                continue
            sx, sy = s8(s['x']), s8(s['y'])
            if fl & OPQ:
                for r in range(h):
                    for c in range(w):
                        self.bg_pixel(self.wk, sx + c, sy + r, 0)
            for r in range(h):
                word = self.shp[sh][h - 1 - r if fl & MY else r]
                for c in range(w):
                    cc = w - 1 - c if fl & MX else c
                    if not (word >> (15 - cc)) & 1:
                        continue
                    px, py = sx + c, sy + r
                    if not (0 <= px < 128 and 0 <= py < 48):
                        continue
                    self.spr_pixel(px, py, 2 if fl & XOR else 1)
                    if not fl & NOC:
                        o = own[py * 128 + px]
                        if o:
                            m = o - 1
                            self.hits[n] |= 1 << m
                            self.hits[m] |= 1 << n
                            self.hit_any = 1
                        own[py * 128 + px] = n + 1
        self.dpram[:1024] = self.wk
        self.frame = 1


# ===================================================================== scenario
class Script:
    def __init__(self):
        self.vec, self.reads, self.frames = [], [], []
        self.m = Engine()

    def _v(self, op, a=0, v=0):
        self.vec.append((op << 24) | ((a & 0xFFFF) << 8) | (v & 0xFF))

    def out(self, port, v):
        self._v(1, port, v)
        self.m.out(port, v)

    def inp(self, port):
        self._v(2, port)
        self.reads.append(self.m.inp(port))

    def wait(self):
        self._v(3)

    def cmd(self, c, *params):
        for p in params:
            self.out(PARAM, p & 0xFF)
        self.out(CMD, c)
        self.wait()

    def status(self):
        self.inp(CMD)

    def results(self, n):
        for _ in range(n):
            self.inp(PARAM)

    def dump(self):
        self._v(4)
        self.frames.append(self.m.dpram[:1024])

    def dpw(self, addr, v):
        self._v(5, addr, v)
        self.m.dpram[addr] = v

    def render(self):
        self.cmd(0x40)
        self.status()
        self.dump()


def scenario():
    s = Script()
    s.cmd(0x02); s.results(4); s.status()                       # VERSION

    # background: text, frame outline, lines, plots
    s.cmd(0x08, 0x20)
    for i, ch in enumerate(b"HELLO"):
        s.cmd(0x0A, i, 0, ch)
    for i, ch in enumerate(b"TRS-80"):
        s.cmd(0x0A, 58 + i, 15, ch)
    s.cmd(0x0D, 0, 3, 128, 42, 1, 0)                            # outline box
    s.cmd(0x0D, 60, 20, 9, 7, 1, 1)                             # filled box
    s.cmd(0x0C, 10, 10, 117, 40, 1)                             # line
    s.cmd(0x0C, 117, 10, 10, 40, 2)                             # xor line
    s.cmd(0x0C, 5, 44, 5, 44, 1)                                # single point line
    s.cmd(0x0B, 1, 1, 1)                                        # plot onto text cell
    s.cmd(0x0B, 64, 23, 0)                                      # clear inside filled box
    s.cmd(0x0B, 200, 10, 1)                                     # off screen: ignored
    s.render()

    # shapes
    ball = [0x3C00, 0x7E00, 0xFF00, 0xFF00, 0xFF00, 0xFF00, 0x7E00, 0x3C00]
    s.cmd(0x10, 0, 8, 8, *[b for w in ball for b in (w >> 8, w & 255)])
    ship = [(0x8001 | (0x0180 << (r % 7)) | (0xFFFF if r in (0, 14) else 0)) & 0xFFFF
            for r in range(15)]
    s.cmd(0x10, 1, 16, 15, *[b for w in ship for b in (w >> 8, w & 255)])
    s.cmd(0x10, 5, 3, 3, 0xE0, 0, 0xA0, 0, 0xE0, 0)
    arrow = [0xC000, 0xF000, 0xFC00, 0xFFC0]
    for r, w in enumerate(arrow):                               # Z80 writes DPRAM
        s.dpw(0x500 + 2 * r, w >> 8)
        s.dpw(0x501 + 2 * r, w & 255)
    s.cmd(0x11, 2, 10, 4, 0x00, 0x05)                           # SHAPE_LOAD

    # sprites
    s.cmd(0x20, 0, 0, 20, 10, VIS)
    s.cmd(0x20, 1, 1, 25, 12, VIS | XOR)                        # overlaps sprite 0
    s.cmd(0x20, 2, 2, (-4) & 255, 44, VIS | MX)                 # partly off screen
    s.cmd(0x20, 3, 0, 0, 0, VIS | OPQ)                          # opaque over "HELLO"
    s.cmd(0x20, 4, 1, 100, 30, VIS | MY | NOC)                  # no collisions
    s.cmd(0x20, 5, 5, (-56) & 255, 5, VIS)                      # fully off screen
    s.cmd(0x20, 6, 0, 50, 30, 0)                                # invisible
    s.cmd(0x20, 7, 5, 56, 45, VIS)                              # over "TRS-80" text row
    s.cmd(0x20, 8, 0, 96, 28, VIS)                              # touches sprite 4 (NOC)
    s.render()
    s.cmd(0x30, 0); s.results(4)
    s.cmd(0x30, 1); s.results(4)
    s.cmd(0x30, 4); s.results(4)
    s.cmd(0x30, 8); s.results(4)
    s.cmd(0x25, 2); s.results(2)

    # velocities
    s.cmd(0x24, 0, 3, 1)
    s.cmd(0x24, 4, (-2) & 255, 0)
    s.cmd(0x21, 1, 70, 5)
    s.cmd(0x22, 3, VIS)                                         # drop OPAQUE
    s.cmd(0x23, 7, 0)                                           # change shape
    s.render()
    s.render()
    s.cmd(0x25, 0); s.results(2)
    s.cmd(0x30, 0); s.results(4)

    # scrolling
    s.cmd(0x0E, 5, 2)
    s.render()
    s.cmd(0x0E, (-3) & 255, (-1) & 255)
    s.render()

    # error handling and parameter bookkeeping
    s.cmd(0x20, 40, 0, 0, 0, VIS); s.status()                   # bad sprite number
    s.cmd(0x10, 3, 8, 4, 1, 2, 3); s.status()                   # too few shape rows
    s.cmd(0x0B, 1, 1, 3); s.status()                            # bad mode
    s.cmd(0x99); s.status()                                     # unknown command
    s.cmd(0x23, 0, 64); s.status()                              # bad shape number
    s.cmd(0x00); s.status()                                     # NOP clears ERR
    s.cmd(0x00, 7, 7, 7)                                        # extra params dropped
    s.cmd(0x25, 1); s.results(2); s.status()

    # background from DPRAM
    for i in range(1024):
        s.dpw((0x400 + i) & 0x7FF, 0x80 | (i * 7 % 64) if i % 5 else 0x41 + i % 26)
    s.cmd(0x09, 0x00, 0x04)
    s.render()

    # reset
    s.cmd(0x01); s.status()
    s.render()

    # auto render
    s.cmd(0x0A, 30, 7, ord('A'))
    s.cmd(0x20, 0, 0, 64, 20, VIS)                              # shape 0 undefined after reset
    s.cmd(0x10, 0, 4, 2, 0xF0, 0, 0x90, 0)
    s.cmd(0x41, 4)
    s.m.render()                                                # model: one auto render
    s._v(6)                                                     # wait for an auto FRAME
    s.frames.append(s.m.dpram[:1024]); s._v(4)
    s.wait()
    s.cmd(0x41, 0); s.status()
    s._v(7)
    return s


def write_hex(path, words):
    with open(path, "w") as f:
        for w in words:
            f.write("%08x\n" % w)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "gen"
    if mode == "gen":
        s = scenario()
        write_hex(os.path.join(HERE, "vectors.hex"), s.vec)
        with open(os.path.join(HERE, "expected_reads.txt"), "w") as f:
            f.writelines("%02x\n" % r for r in s.reads)
        with open(os.path.join(HERE, "expected_frames.txt"), "w") as f:
            for fr in s.frames:
                f.writelines("%02x\n" % b for b in fr)
        print("vectors: %d, reads: %d, frames: %d" % (len(s.vec), len(s.reads), len(s.frames)))
    else:
        def load(name):
            with open(os.path.join(HERE, name)) as f:
                return [l.strip().lower() for l in f if l.strip()]
        er, ar = load("expected_reads.txt"), load("reads.txt")
        ef, af = load("expected_frames.txt"), load("frames.txt")
        bad = 0
        if len(er) != len(ar):
            print("read count differs: expected %d, got %d" % (len(er), len(ar)))
            bad += 1
        for i, (e, a) in enumerate(zip(er, ar)):
            if e != a:
                print("read %d: expected %s got %s" % (i, e, a))
                bad += 1
        if len(ef) != len(af):
            print("frame bytes differ in count: expected %d, got %d" % (len(ef), len(af)))
            bad += 1
        nfr = min(len(ef), len(af)) // 1024
        for f in range(nfr):
            diffs = [i for i in range(1024) if ef[f * 1024 + i] != af[f * 1024 + i]]
            if diffs:
                bad += 1
                i = diffs[0]
                print("frame %d: %d bytes differ, first at %d (row %d col %d): expected %s got %s"
                      % (f, len(diffs), i, i // 64, i % 64, ef[f * 1024 + i], af[f * 1024 + i]))
            else:
                print("frame %d: identical" % f)
        print("reads compared: %d" % min(len(er), len(ar)))
        print("RESULT: %s" % ("PASS" if bad == 0 else "FAIL"))
        sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
