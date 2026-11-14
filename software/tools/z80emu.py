#!/usr/bin/env python3
"""
Small Z80 interpreter for testing the card library against the card models.

Implements the main, CB and ED instruction groups with full S/Z/H/PV/N/C
flags for the arithmetic, logic, shift and bit instructions (no IX/IY,
no DAA, no undocumented flags). Any instruction it does not implement
raises NotImplementedError, so untested code can't slip through quietly.
T-states are counted for every instruction (standard timings), which lets
the test estimate real-machine speed at 1.774 MHz.
"""

FS, FZ, FH, FPV, FN, FC = 0x80, 0x40, 0x10, 0x04, 0x02, 0x01


def _parity(v):
    v ^= v >> 4
    v ^= v >> 2
    v ^= v >> 1
    return 0 if v & 1 else FPV


class Z80:
    def __init__(self, rd, wr, inp, out):
        self.rd, self.wr, self.inp, self.out = rd, wr, inp, out
        self.a = self.f = self.b = self.c = self.d = self.e = self.h = self.l = 0
        self.a_ = self.f_ = 0
        self.alt = [0] * 6
        self.sp = 0xFFFF
        self.pc = 0
        self.halted = False
        self.t = 0                       # T-states

    # ---------------------------------------------------------------- access
    def fetch(self):
        v = self.rd(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return v

    def fetch16(self):
        lo = self.fetch()
        return lo | (self.fetch() << 8)

    def rd16(self, a):
        return self.rd(a) | (self.rd((a + 1) & 0xFFFF) << 8)

    def wr16(self, a, v):
        self.wr(a, v & 0xFF)
        self.wr((a + 1) & 0xFFFF, v >> 8)

    def push(self, v):
        self.sp = (self.sp - 2) & 0xFFFF
        self.wr16(self.sp, v)

    def pop(self):
        v = self.rd16(self.sp)
        self.sp = (self.sp + 2) & 0xFFFF
        return v

    @property
    def hl(self):
        return (self.h << 8) | self.l

    @hl.setter
    def hl(self, v):
        self.h, self.l = (v >> 8) & 0xFF, v & 0xFF

    def get_rp(self, p, af=False):
        if p == 0:
            return (self.b << 8) | self.c
        if p == 1:
            return (self.d << 8) | self.e
        if p == 2:
            return self.hl
        return ((self.a << 8) | self.f) if af else self.sp

    def set_rp(self, p, v, af=False):
        v &= 0xFFFF
        if p == 0:
            self.b, self.c = v >> 8, v & 0xFF
        elif p == 1:
            self.d, self.e = v >> 8, v & 0xFF
        elif p == 2:
            self.hl = v
        elif af:
            self.a, self.f = v >> 8, v & 0xFF
        else:
            self.sp = v

    def get_r(self, i):
        return (self.b, self.c, self.d, self.e, self.h, self.l, None, self.a)[i] \
            if i != 6 else self.rd(self.hl)

    def set_r(self, i, v):
        v &= 0xFF
        if i == 0: self.b = v
        elif i == 1: self.c = v
        elif i == 2: self.d = v
        elif i == 3: self.e = v
        elif i == 4: self.h = v
        elif i == 5: self.l = v
        elif i == 6: self.wr(self.hl, v)
        else: self.a = v

    def cond(self, y):
        f = self.f
        return (not f & FZ, f & FZ, not f & FC, f & FC,
                not f & FPV, f & FPV, not f & FS, f & FS)[y]

    # ---------------------------------------------------------------- ALU
    def add8(self, b, cy=0):
        a = self.a
        r = a + b + cy
        f = (r & 0x80) | (0 if r & 0xFF else FZ)
        if ((a & 0xF) + (b & 0xF) + cy) > 0xF: f |= FH
        if (~(a ^ b) & (a ^ r) & 0x80): f |= FPV
        if r > 0xFF: f |= FC
        self.a, self.f = r & 0xFF, f

    def sub8(self, b, cy=0, store=True):
        a = self.a
        r = a - b - cy
        f = (r & 0x80) | (0 if r & 0xFF else FZ) | FN
        if (a & 0xF) < (b & 0xF) + cy: f |= FH
        if ((a ^ b) & (a ^ r) & 0x80): f |= FPV
        if r < 0: f |= FC
        self.f = f
        if store:
            self.a = r & 0xFF

    def logic(self, r, h):
        self.a = r & 0xFF
        self.f = (self.a & 0x80) | (0 if self.a else FZ) | (FH if h else 0) | _parity(self.a)

    def alu(self, y, v):
        if y == 0: self.add8(v)
        elif y == 1: self.add8(v, self.f & FC)
        elif y == 2: self.sub8(v)
        elif y == 3: self.sub8(v, self.f & FC)
        elif y == 4: self.logic(self.a & v, True)
        elif y == 5: self.logic(self.a ^ v, False)
        elif y == 6: self.logic(self.a | v, False)
        else: self.sub8(v, 0, store=False)

    def inc8(self, v):
        r = (v + 1) & 0xFF
        f = (self.f & FC) | (r & 0x80) | (0 if r else FZ)
        if (v & 0xF) == 0xF: f |= FH
        if v == 0x7F: f |= FPV
        self.f = f
        return r

    def dec8(self, v):
        r = (v - 1) & 0xFF
        f = (self.f & FC) | (r & 0x80) | (0 if r else FZ) | FN
        if (v & 0xF) == 0: f |= FH
        if v == 0x80: f |= FPV
        self.f = f
        return r

    def rot(self, y, v):
        cy = self.f & FC
        if y == 0: c = v >> 7; r = (v << 1) | c
        elif y == 1: c = v & 1; r = (v >> 1) | (c << 7)
        elif y == 2: c = v >> 7; r = (v << 1) | cy
        elif y == 3: c = v & 1; r = (v >> 1) | (cy << 7)
        elif y == 4: c = v >> 7; r = v << 1
        elif y == 5: c = v & 1; r = (v >> 1) | (v & 0x80)
        elif y == 6: raise NotImplementedError("SLL")
        else: c = v & 1; r = v >> 1
        r &= 0xFF
        self.f = (r & 0x80) | (0 if r else FZ) | _parity(r) | (FC if c else 0)
        return r

    # ---------------------------------------------------------------- step
    def step(self):
        op = self.fetch()
        x, y, z = op >> 6, (op >> 3) & 7, op & 7
        p, q = y >> 1, y & 1
        t = 4
        if x == 0:
            if z == 0:
                if y == 0:
                    pass
                elif y == 1:
                    self.a, self.a_ = self.a_, self.a
                    self.f, self.f_ = self.f_, self.f
                elif y == 2:
                    d = self.fetch(); d -= 256 if d & 0x80 else 0
                    self.b = (self.b - 1) & 0xFF
                    t = 8
                    if self.b:
                        self.pc = (self.pc + d) & 0xFFFF; t = 13
                else:
                    d = self.fetch(); d -= 256 if d & 0x80 else 0
                    t = 7
                    if y == 3 or self.cond(y - 4):
                        self.pc = (self.pc + d) & 0xFFFF; t = 12
            elif z == 1:
                if q == 0:
                    self.set_rp(p, self.fetch16()); t = 10
                else:
                    hl, rr = self.hl, self.get_rp(p)
                    r = hl + rr
                    f = self.f & (FS | FZ | FPV)
                    if ((hl & 0xFFF) + (rr & 0xFFF)) > 0xFFF: f |= FH
                    if r > 0xFFFF: f |= FC
                    self.hl, self.f, t = r & 0xFFFF, f, 11
            elif z == 2:
                if q == 0:
                    if p == 0: self.wr(self.get_rp(0), self.a); t = 7
                    elif p == 1: self.wr(self.get_rp(1), self.a); t = 7
                    elif p == 2: self.wr16(self.fetch16(), self.hl); t = 16
                    else: self.wr(self.fetch16(), self.a); t = 13
                else:
                    if p == 0: self.a = self.rd(self.get_rp(0)); t = 7
                    elif p == 1: self.a = self.rd(self.get_rp(1)); t = 7
                    elif p == 2: self.hl = self.rd16(self.fetch16()); t = 16
                    else: self.a = self.rd(self.fetch16()); t = 13
            elif z == 3:
                self.set_rp(p, self.get_rp(p) + (1 if q == 0 else -1)); t = 6
            elif z == 4:
                self.set_r(y, self.inc8(self.get_r(y))); t = 11 if y == 6 else 4
            elif z == 5:
                self.set_r(y, self.dec8(self.get_r(y))); t = 11 if y == 6 else 4
            elif z == 6:
                self.set_r(y, self.fetch()); t = 10 if y == 6 else 7
            else:
                a, f = self.a, self.f
                keep = f & (FS | FZ | FPV)
                if y == 0: c = a >> 7; self.a = ((a << 1) | c) & 0xFF; self.f = keep | c
                elif y == 1: c = a & 1; self.a = (a >> 1) | (c << 7); self.f = keep | c
                elif y == 2: c = a >> 7; self.a = ((a << 1) | (f & FC)) & 0xFF; self.f = keep | c
                elif y == 3: c = a & 1; self.a = (a >> 1) | ((f & FC) << 7); self.f = keep | c
                elif y == 4: raise NotImplementedError("DAA")
                elif y == 5: self.a = a ^ 0xFF; self.f = f | FH | FN
                elif y == 6: self.f = keep | FC
                else: self.f = keep | (FH if f & FC else 0) | (0 if f & FC else FC)
        elif x == 1:
            if op == 0x76:
                self.halted = True
                self.pc = (self.pc - 1) & 0xFFFF
            else:
                self.set_r(y, self.get_r(z)); t = 7 if (y == 6 or z == 6) else 4
        elif x == 2:
            self.alu(y, self.get_r(z)); t = 7 if z == 6 else 4
        else:
            if z == 0:
                t = 5
                if self.cond(y):
                    self.pc = self.pop(); t = 11
            elif z == 1:
                if q == 0:
                    self.set_rp(p, self.pop(), af=True); t = 10
                elif p == 0:
                    self.pc = self.pop(); t = 10
                elif p == 1:                                # EXX
                    regs = [self.b, self.c, self.d, self.e, self.h, self.l]
                    self.b, self.c, self.d, self.e, self.h, self.l = self.alt
                    self.alt = regs
                elif p == 2:
                    self.pc = self.hl
                else:
                    self.sp = self.hl; t = 6
            elif z == 2:
                nn = self.fetch16(); t = 10
                if self.cond(y): self.pc = nn
            elif z == 3:
                if y == 0: self.pc = self.fetch16(); t = 10
                elif y == 1: t = self.step_cb()
                elif y == 2: self.out(self.fetch(), self.a); t = 11
                elif y == 3: self.a = self.inp(self.fetch()); t = 11
                elif y == 4:
                    v = self.rd16(self.sp); self.wr16(self.sp, self.hl); self.hl = v; t = 19
                elif y == 5:
                    de = self.get_rp(1); self.set_rp(1, self.hl); self.hl = de
                else:
                    pass                                    # DI / EI
            elif z == 4:
                nn = self.fetch16(); t = 10
                if self.cond(y):
                    self.push(self.pc); self.pc = nn; t = 17
            elif z == 5:
                if q == 0:
                    self.push(self.get_rp(p, af=True)); t = 11
                elif p == 0:
                    nn = self.fetch16(); self.push(self.pc); self.pc = nn; t = 17
                elif p == 2:
                    t = self.step_ed()
                else:
                    raise NotImplementedError("IX/IY prefix at %04x" % ((self.pc - 1) & 0xFFFF))
            elif z == 6:
                self.alu(y, self.fetch()); t = 7
            else:
                self.push(self.pc); self.pc = y * 8; t = 11
        self.t += t

    def step_cb(self):
        op = self.fetch()
        x, y, z = op >> 6, (op >> 3) & 7, op & 7
        v = self.get_r(z)
        if x == 0:
            self.set_r(z, self.rot(y, v))
            return 15 if z == 6 else 8
        if x == 1:
            bit = (v >> y) & 1
            f = (self.f & FC) | FH | (0 if bit else (FZ | FPV))
            if y == 7 and bit: f |= FS
            self.f = f
            return 12 if z == 6 else 8
        self.set_r(z, (v & ~(1 << y)) if x == 2 else (v | (1 << y)))
        return 15 if z == 6 else 8

    def step_ed(self):
        op = self.fetch()
        x, y, z = op >> 6, (op >> 3) & 7, op & 7
        p, q = y >> 1, y & 1
        if x == 1:
            if z == 0:
                v = self.inp(self.c)
                if y != 6: self.set_r(y, v)
                self.f = (self.f & FC) | (v & 0x80) | (0 if v else FZ) | _parity(v)
                return 12
            if z == 1:
                self.out(self.c, 0 if y == 6 else self.get_r(y)); return 12
            if z == 2:
                hl, rr, cy = self.hl, self.get_rp(p), self.f & FC
                if q == 0:
                    r = hl - rr - cy
                    f = FN | (FH if (hl & 0xFFF) - (rr & 0xFFF) - cy < 0 else 0)
                    if ((hl ^ rr) & (hl ^ r) & 0x8000): f |= FPV
                    if r < 0: f |= FC
                else:
                    r = hl + rr + cy
                    f = FH if (hl & 0xFFF) + (rr & 0xFFF) + cy > 0xFFF else 0
                    if (~(hl ^ rr) & (hl ^ r) & 0x8000): f |= FPV
                    if r > 0xFFFF: f |= FC
                r &= 0xFFFF
                f |= ((r >> 8) & 0x80) | (0 if r else FZ)
                self.hl, self.f = r, f
                return 15
            if z == 3:
                nn = self.fetch16()
                if q == 0: self.wr16(nn, self.get_rp(p))
                else: self.set_rp(p, self.rd16(nn))
                return 20
            if z == 4:
                a = self.a; self.a = 0; self.sub8(a); return 8
        if x == 2 and y >= 4 and z == 0:              # LDI LDD LDIR LDDR
            step = 1 if y in (4, 6) else -1
            t = 0
            while True:
                self.wr(self.get_rp(1), self.rd(self.hl))
                self.hl = (self.hl + step) & 0xFFFF
                self.set_rp(1, self.get_rp(1) + step)
                bc = (self.get_rp(0) - 1) & 0xFFFF
                self.set_rp(0, bc)
                t += 21
                if y < 6 or bc == 0:
                    break
            self.f = (self.f & (FS | FZ | FC)) | (FPV if bc else 0)
            return t - 5
        raise NotImplementedError("ED %02x at %04x" % (op, (self.pc - 2) & 0xFFFF))

    def run(self, max_steps=50_000_000, stop=None):
        for _ in range(max_steps):
            if self.halted or (stop and stop(self)):
                return
            self.step()
        raise RuntimeError("step limit reached at PC %04x" % self.pc)


def selftest():
    """Spot checks of tricky flags against known Z80 results."""
    mem = bytearray(65536)
    cpu = Z80(lambda a: mem[a], lambda a, v: mem.__setitem__(a, v), lambda p: 0xFF, lambda p, v: None)
    cases = [
        # (code bytes, A in, F expected mask check (A_out, flags & mask, mask))
        (bytes([0x3E, 0x7F, 0xC6, 0x01]), 0x80, FS | FPV | FH, FS | FZ | FH | FPV | FN | FC),  # 7F+1
        (bytes([0x3E, 0x80, 0xD6, 0x01]), 0x7F, FPV | FH | FN, FS | FZ | FH | FPV | FN | FC),  # 80-1
        (bytes([0x3E, 0x00, 0xD6, 0x01]), 0xFF, FS | FH | FN | FC, FS | FZ | FH | FPV | FN | FC),
        (bytes([0x3E, 0x55, 0xE6, 0x0F]), 0x05, FH | FPV, FS | FZ | FH | FPV | FN | FC),      # AND parity
        (bytes([0x3E, 0x01, 0xED, 0x44]), 0xFF, FS | FH | FN | FC, FS | FZ | FH | FPV | FN | FC),  # NEG
        (bytes([0x3E, 0x80, 0xCB, 0x7F]), 0x80, FS | FH, FS | FZ | FH | FN),                   # BIT 7,A
    ]
    bad = 0
    for code, aout, fexp, mask in cases:
        mem[0:len(code)] = code
        mem[len(code)] = 0x76
        cpu.pc, cpu.halted, cpu.f = 0, False, 0
        cpu.run()
        if cpu.a != aout or (cpu.f & mask) != fexp:
            bad += 1
            print("selftest fail:", code.hex(), hex(cpu.a), hex(cpu.f))
    return bad


if __name__ == "__main__":
    print("z80emu selftest failures:", selftest())
