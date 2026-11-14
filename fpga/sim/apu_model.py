#!/usr/bin/env python3
"""
Reference model of the Am9511 APU core (fpga/src/am9511.v), following the
ratboy666/am9511 emulator (MIT) semantics, with these deliberate fixes:

  * SUB carry is the true unsigned borrow (the emulator's sub16 treats any
    minuend of 0x8000 as a borrow, which corrupts 32-bit results).
  * 32-bit MUL/MUU test both operands for 0x80000000 (emulator typo).
  * FIXD of +2^31 reports OVF (undefined behaviour in the C emulator).
  * Basic float operations are rounded exactly to 24 bits (round to nearest
    even) with an unbounded intermediate exponent; the emulator rounds via
    IEEE single, which only differs for results below 2^-126.

Phase 1: the transcendental functions (SIN..ATAN, LOG, LN, EXP, PWR) are not
implemented yet; they leave the stack unchanged and report the ARG error.

  python apu_model.py gen    -> apu_vectors.hex, apu_expected_reads.txt
  python apu_model.py check  -> compares apu_reads.txt from the simulation
"""
import math
import os
import random
import struct
import sys
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                     # for apu_ucode (derived functions)
DATA, CMDP = 0x50, 0x51
ERR_DIV0, ERR_NEG, ERR_ARG, ERR_UND, ERR_OVF = 0x10, 0x08, 0x18, 0x04, 0x02
SINGLE, DOUBLE, FLOAT = 0x60, 0x20, 0x00

OPS = dict(NOP=0x00, SQRT=0x01, SIN=0x02, COS=0x03, TAN=0x04, ASIN=0x05, ACOS=0x06,
           ATAN=0x07, LOG=0x08, LN=0x09, EXP=0x0A, PWR=0x0B, ADD=0x0C, SUB=0x0D,
           MUL=0x0E, DIV=0x0F, FADD=0x10, FSUB=0x11, FMUL=0x12, FDIV=0x13, CHS=0x14,
           CHSF=0x15, MUU=0x16, PTO=0x17, POP=0x18, XCH=0x19, PUPI=0x1A,
           FLTD=0x1C, FLTS=0x1D, FIXD=0x1E, FIXS=0x1F)


# ------------------------------------------------------------------ float --
def am_unpack(v):
    """32-bit Am9511 word -> Fraction (or 0)."""
    if not v & 0x800000:
        return Fraction(0)
    e = (v >> 24) & 0x7F
    if e & 0x40:
        e -= 128
    m = v & 0xFFFFFF
    val = Fraction(m, 1 << 24) * (Fraction(2) ** e)
    return -val if v & 0x80000000 else val


def am_round(x):
    """Exact value -> (word, err) with RNE to 24 bits and exponent wrap."""
    if x == 0:
        return 0, 0
    s = 1 if x < 0 else 0
    a = -x if s else x
    # find e with a = M * 2^(e-24), M in [2^23, 2^24)
    e = a.numerator.bit_length() - a.denominator.bit_length()
    while a >= Fraction(2) ** e:
        e += 1
    while a < Fraction(2) ** (e - 1):
        e -= 1
    scaled = a / (Fraction(2) ** (e - 24))          # in [2^23, 2^24)
    m = scaled.numerator // scaled.denominator
    rem = scaled - m
    if rem > Fraction(1, 2) or (rem == Fraction(1, 2) and m & 1):
        m += 1
    if m == 1 << 24:
        m >>= 1
        e += 1
    err = 0
    if e > 63:
        err, e = ERR_OVF, e - 128
    elif e < -64:
        err, e = ERR_UND, e + 128
    return (s << 31) | ((e & 0x7F) << 24) | m, err


def ieee_path(x):
    """Emulator path: round to IEEE single (for cross-checking am_round)."""
    f = struct.unpack("<f", struct.pack("<f", float(x)))[0]
    return f


def fl(v):
    """Python float -> Am9511 word (RNE)."""
    return am_round(Fraction(v))[0]


# ------------------------------------------------------------------ model --
class Am9511:
    def __init__(self):
        self.stk = [0] * 16
        self.sp = 0
        self.status = 0

    def push(self, b):
        self.stk[self.sp] = b & 0xFF
        self.sp = (self.sp + 1) & 15

    def pop(self):
        self.sp = (self.sp - 1) & 15
        return self.stk[self.sp]

    def at(self, off):                      # off < 0 relative to sp
        return self.stk[(self.sp + off) & 15]

    def word(self, nbytes, depth):
        """Value occupying bytes [sp-depth-nbytes .. sp-depth-1], little endian."""
        v = 0
        for i in range(nbytes):
            v |= self.at(-depth - nbytes + i) << (8 * i)
        return v

    def sz(self, ftype):
        st = 0
        if ftype == SINGLE:
            if (self.at(-1) | self.at(-2)) == 0:
                st |= 0x20
        elif ftype & 0x20:
            if (self.at(-1) | self.at(-2) | self.at(-3) | self.at(-4)) == 0:
                st |= 0x20
        else:
            if not self.at(-2) & 0x80:
                st |= 0x20
        if self.at(-1) & 0x80:
            st |= 0x40
        return st

    def store(self, consumed, results):
        """Drop `consumed` bytes, then push each (value, nbytes)."""
        self.sp = (self.sp - consumed) & 15
        for v, n in results:
            for i in range(n):
                self.push((v >> (8 * i)) & 0xFF)

    def command(self, op):
        code, t = op & 0x1F, op & 0x60
        single = (t == SINGLE)
        w = 2 if single else 4
        bits = 8 * w
        mask = (1 << bits) - 1
        smin = 1 << (bits - 1)
        ftype = SINGLE if single else (DOUBLE if t & 0x20 else FLOAT)
        err, carry = 0, 0

        def sx(v):
            return v - (1 << bits) if v & smin else v

        if code in (0x00, 0x1B):
            self.status = 0
            return
        A = self.word(w, 0)
        B = self.word(w, w)
        if code == 0x1A:                                    # PUPI
            self.store(0, [(0x02C90FDA, 4)])
            ftype = FLOAT
        elif code == 0x17:                                  # PTO
            self.store(w, [(A, w), (A, w)])
        elif code == 0x18:                                  # POP
            self.store(w, [])
        elif code == 0x19:                                  # XCH
            self.store(2 * w, [(A, w), (B, w)])
        elif code == 0x14:                                  # CHS
            if A == smin:
                err = ERR_OVF
            else:
                self.store(w, [((-A) & mask, w)])
        elif code == 0x15:                                  # CHSF
            a4 = self.word(4, 0)
            if a4 & 0x800000:
                a4 ^= 0x80000000
            self.store(4, [(a4, 4)])
        elif code == 0x0C:                                  # ADD
            r = A + B
            carry = 1 if r > mask else 0
            r &= mask
            sa, sb, sc = A & smin, B & smin, r & smin
            if sa == sb and sc != sa:
                err = ERR_OVF
            self.store(2 * w, [(r, w)])
        elif code == 0x0D:                                  # SUB  NOS - TOS
            r = (B - A) & mask
            carry = 1 if B < A else 0
            sa, sb, sc = B & smin, A & smin, r & smin       # emulator osub(pa=B, pb=A)
            if (not sa and sb and sc) or (sa and not sb and not sc):
                err = ERR_OVF
            self.store(2 * w, [(r, w)])
        elif code in (0x0E, 0x16):                          # MUL / MUU
            if A == smin or B == smin:
                r, err = smin, ERR_OVF
            else:
                s = (A ^ B) & smin
                p = abs(sx(A)) * abs(sx(B))
                if code == 0x0E:
                    o = (p >> bits) != 0
                    o2 = bool(s) and p == (1 << (2 * bits - 1))
                    if s:
                        p = (-p) & ((1 << (2 * bits)) - 1)
                    r = p & mask
                    err = ERR_OVF if (o or o2) else 0
                else:
                    o2 = bool(s) and p == (1 << (2 * bits - 1))
                    if s:
                        p = (-p) & ((1 << (2 * bits)) - 1)
                    r = (p >> bits) & mask
                    err = ERR_OVF if o2 else 0
            self.store(2 * w, [(r, w)])
        elif code == 0x0F:                                  # DIV  NOS / TOS
            if A == 0:
                r, err = 0, ERR_DIV0
            else:
                q = abs(sx(B)) // abs(sx(A))
                if (sx(A) < 0) != (sx(B) < 0):
                    q = -q
                r = q & mask
            self.store(2 * w, [(r, w)])
        elif code in (0x10, 0x11, 0x12, 0x13):              # FADD FSUB FMUL FDIV
            a4, b4 = self.word(4, 0), self.word(4, 4)
            a, b = am_unpack(a4), am_unpack(b4)
            if code == 0x10:
                x = b + a
            elif code == 0x11:
                x = b - a
            elif code == 0x12:
                x = b * a
            else:
                if a == 0:
                    x, err = b, ERR_DIV0
                else:
                    x = b / a
            r, e2 = am_round(x)
            err |= e2
            self.store(8, [(r, 4)])
            ftype = FLOAT
        elif code == 0x01:                                  # SQRT
            a4 = self.word(4, 0)
            a = am_unpack(a4)
            ftype = FLOAT
            if a < 0:
                err = ERR_NEG
            else:
                r = sqrt_round(a4)
                self.store(4, [(r, 4)])
        elif 0x02 <= code <= 0x0B:                          # derived functions (microcode)
            import apu_ucode
            pwr = (code == 0x0B)
            res, e = apu_ucode.run_function(code, self.word(4, 0), self.word(4, 4) if pwr else 0)
            if not pwr:
                ftype = FLOAT
            if res is None:
                err = e
            else:
                self.store(8 if pwr else 4, [(res, 4)])
        elif code in (0x1C, 0x1D):                          # FLTD / FLTS
            n = 4 if code == 0x1C else 2
            v = self.word(n, 0)
            if v & (1 << (8 * n - 1)):
                v -= 1 << (8 * n)
            r, _ = am_round(Fraction(v))
            self.store(n, [(r, 4)])
            ftype = FLOAT
        elif code in (0x1E, 0x1F):                          # FIXD / FIXS
            a4 = self.word(4, 0)
            x = am_unpack(a4)
            if code == 0x1F:
                lo, hi, n = -32768, 32767, 2
            else:
                lo, hi, n = -(1 << 31), (1 << 31) - 1, 4
            if x < lo or x > hi:
                err = ERR_OVF
            else:
                q = int(x)                                  # truncation toward zero
                self.store(4, [(q & ((1 << (8 * n)) - 1), n)])
                ftype = SINGLE if code == 0x1F else DOUBLE
        self.status = self.sz(ftype) | err | carry


def sqrt_round(a4):
    """Correctly rounded square root of a non-negative Am9511 word (bit-level,
    same recurrence as the RTL)."""
    if not a4 & 0x800000:
        return 0
    e = (a4 >> 24) & 0x7F
    if e & 0x40:
        e -= 128
    m = a4 & 0xFFFFFF
    if e & 1:
        X, shift = m << 29, 3
    else:
        X, shift = m << 28, 2
    s = math.isqrt(X)
    rem = X - s * s
    M = s >> shift
    g = (s >> (shift - 1)) & 1
    st = (s & ((1 << (shift - 1)) - 1)) != 0 or rem != 0
    if g and (st or (M & 1)):
        M += 1
    E = (e + (e & 1)) >> 1
    if M == 1 << 24:
        M >>= 1
        E += 1
    return ((E & 0x7F) << 24) | M


# ------------------------------------------------------------------ script --
class Script:
    def __init__(self):
        self.vec, self.reads = [], []
        self.m = Am9511()

    def _v(self, op, a=0, v=0):
        self.vec.append((op << 24) | ((a & 0xFFFF) << 8) | (v & 0xFF))

    def push(self, value, nbytes):
        for i in range(nbytes):
            b = (value >> (8 * i)) & 0xFF
            self._v(1, DATA, b)
            self.m.push(b)

    def cmd(self, op):
        self._v(1, CMDP, op)
        self.m.command(op)
        self._v(8)                                   # wait until not BUSY
        self._v(2, CMDP)
        self.reads.append(self.m.status)

    def pull(self, nbytes):
        for _ in range(nbytes):
            self._v(2, DATA)
            self.reads.append(self.m.pop())

    def status(self):
        self._v(2, CMDP)
        self.reads.append(self.m.status)


def rand_float(r):
    kind = r.random()
    if kind < 0.05:
        return 0
    s = r.getrandbits(1) << 31
    if kind < 0.15:
        e = r.choice([-64, -63, 63, 62, -1, 0, 1])
    else:
        e = r.randint(-20, 20)
    return s | ((e & 0x7F) << 24) | 0x800000 | r.getrandbits(23)


def rand_int(r, bits):
    k = r.random()
    if k < 0.1:
        return r.choice([0, 1, (1 << bits) - 1, 1 << (bits - 1), (1 << (bits - 1)) - 1, 2])
    if k < 0.4:
        return r.getrandbits(bits // 2) | (((1 << bits) - 1) ^ ((1 << (bits // 2)) - 1)
                                          if r.random() < 0.5 else 0)
    return r.getrandbits(bits)


def scenario(seed=9511):
    r = random.Random(seed)
    s = Script()
    s.status()
    # directed: PUPI, stack ops, the classic examples
    s.cmd(OPS['PUPI']); s.pull(4)
    s.push(fl(2.0), 4); s.push(fl(3.0), 4); s.cmd(OPS['FADD']); s.pull(4)
    s.push(fl(10.0), 4); s.push(fl(4.0), 4); s.cmd(OPS['FSUB']); s.pull(4)
    s.push(fl(1.0), 4); s.push(0, 4); s.cmd(OPS['FDIV']); s.pull(4)      # /0
    s.push(fl(2.0), 4); s.cmd(OPS['SQRT']); s.pull(4)
    s.push(fl(-4.0), 4); s.cmd(OPS['SQRT']); s.pull(4)                   # NEG
    s.push(fl(1.0), 4); s.cmd(OPS['SIN']); s.pull(4)
    s.push(1234, 2); s.push(-5 & 0xFFFF, 2); s.cmd(SINGLE | OPS['MUL']); s.pull(2)
    s.push(0x7FFF, 2); s.push(1, 2); s.cmd(SINGLE | OPS['ADD']); s.pull(2)
    s.push(0x00008000, 4); s.push(0, 4); s.cmd(DOUBLE | OPS['SUB']); s.pull(4)
    s.push(fl(32767.5), 4); s.cmd(OPS['FIXS']); s.pull(4)                # OVF
    s.push(fl(-32768.0), 4); s.cmd(OPS['FIXS']); s.pull(2)
    s.push(fl(2147483648.0), 4); s.cmd(OPS['FIXD']); s.pull(4)           # OVF
    s.push(0x80000000, 4); s.cmd(OPS['FLTD']); s.pull(4)
    s.push(fl(1.5), 4); s.push(fl(2.5), 4); s.cmd(OPS['XCH']); s.pull(8)
    s.push(0x1234, 2); s.cmd(SINGLE | OPS['PTO']); s.pull(4)
    s.push(0x11223344, 4); s.push(0x55667788, 4); s.cmd(DOUBLE | OPS['POP']); s.pull(4)
    s.push(0x8000, 2); s.cmd(SINGLE | OPS['CHS']); s.pull(2)
    s.push(fl(3.0), 4); s.cmd(OPS['CHSF']); s.pull(4)
    s.push(0, 4); s.cmd(OPS['CHSF']); s.pull(4)
    s.push(fl(2.0 ** 40), 4); s.push(fl(2.0 ** 40), 4); s.cmd(OPS['FMUL']); s.pull(4)   # OVF
    s.push(fl(2.0 ** -40), 4); s.push(fl(2.0 ** -40), 4); s.cmd(OPS['FMUL']); s.pull(4)  # UND
    s.cmd(OPS['NOP']); s.status()
    s.cmd(0x9A); s.pull(4)                                               # PUPI with SR

    # derived functions: edges and domain errors
    for name, x in [('EXP', 32.0), ('EXP', 32.5), ('EXP', -32.0), ('EXP', 0.0), ('LN', 0.0),
                    ('LN', -1.0), ('LN', 1.0), ('LOG', 1000.0), ('ASIN', 1.0), ('ASIN', -1.0),
                    ('ASIN', 1.0000001), ('ACOS', -1.0), ('ACOS', 1.0), ('ACOS', 0.5),
                    ('TAN', -1e-5), ('TAN', 1e-5), ('TAN', 1.5707963), ('SIN', 1e10),
                    ('SIN', 0.0), ('COS', 0.0), ('ATAN', 1e20), ('ATAN', -1.0), ('SQRT', 0.25)]:
        s.push(fl(x), 4); s.cmd(OPS[name])
        s.pull(4)
    for b, a in [(2.0, 10.0), (-2.0, 2.0), (0.0, 2.0), (10.0, 20.0), (1.0, 123.0), (9.0, 0.5)]:
        s.push(fl(b), 4); s.push(fl(a), 4); s.cmd(OPS['PWR'])
        s.pull(4 if s.m.status & 0x1E == 0 else 8)
    s.push(fl(0.5), 4); s.cmd(0x80 | OPS['SIN']); s.pull(4)            # with SR

    # derived functions: random arguments over their domains
    doms = dict(SIN=(-20, 20), COS=(-20, 20), TAN=(-3, 3), ASIN=(-1.05, 1.05),
                ACOS=(-1.05, 1.05), ATAN=(-100, 100), LOG=(-1, 1e5), LN=(-1, 1e5), EXP=(-35, 35))
    for _ in range(300):
        name = r.choice(list(doms) + ['PWR'])
        if name == 'PWR':
            s.push(fl(r.uniform(-1, 50)), 4); s.push(fl(r.uniform(-6, 6)), 4); s.cmd(OPS['PWR'])
            s.pull(4 if s.m.status & 0x1E == 0 else 8)
        else:
            lo, hi = doms[name]
            s.push(fl(r.uniform(lo, hi)), 4); s.cmd(OPS[name]); s.pull(4)

    # random operations
    for _ in range(700):
        k = r.random()
        if k < 0.30:
            op = r.choice(['FADD', 'FSUB', 'FMUL', 'FDIV'])
            a, b = rand_float(r), rand_float(r)
            if op in ('FADD', 'FSUB') and r.random() < 0.3:      # near cancellation
                a = (b & 0xFF000000) | ((b + r.randint(-3, 3)) & 0xFFFFFF) | 0x800000
                a ^= r.getrandbits(1) << 31
            s.push(b, 4); s.push(a, 4); s.cmd(OPS[op]); s.pull(4)
        elif k < 0.38:
            a = rand_float(r) & 0x7FFFFFFF
            if r.random() < 0.1:
                a |= 0x80000000
            s.push(a, 4); s.cmd(OPS['SQRT']); s.pull(4)
        elif k < 0.70:
            single = r.random() < 0.5
            bits = 16 if single else 32
            op = r.choice(['ADD', 'SUB', 'MUL', 'MUU', 'DIV'])
            a, b = rand_int(r, bits), rand_int(r, bits)
            w = bits // 8
            s.push(b, w); s.push(a, w)
            s.cmd((SINGLE if single else DOUBLE) | OPS[op]); s.pull(w)
        elif k < 0.80:
            op = r.choice(['FLTS', 'FLTD'])
            n = 2 if op == 'FLTS' else 4
            s.push(rand_int(r, 8 * n), n); s.cmd(OPS[op]); s.pull(4)
        elif k < 0.90:
            op = r.choice(['FIXS', 'FIXD'])
            if r.random() < 0.6:
                lim = 33000 if op == 'FIXS' else 2.2e9
                a = fl(r.uniform(-lim, lim))
            else:
                a = rand_float(r)
            s.push(a, 4); s.cmd(OPS[op])
            if s.m.status & ERR_OVF:
                s.pull(4)
            else:
                s.pull(2 if op == 'FIXS' else 4)
        else:
            single = r.random() < 0.5
            w = 2 if single else 4
            t = SINGLE if single else DOUBLE
            op = r.choice(['CHS', 'PTO', 'POP', 'XCH'])
            a, b = rand_int(r, 8 * w), rand_int(r, 8 * w)
            s.push(b, w); s.push(a, w); s.cmd(t | OPS[op])
            s.pull({'CHS': 2 * w, 'PTO': 3 * w, 'POP': w, 'XCH': 2 * w}[op])
    s._v(7)
    return s


def selfcheck():
    """Cross-check exact rounding against the emulator's IEEE-single path."""
    r = random.Random(1)
    bad = 0
    for _ in range(20000):
        a, b = rand_float(r), rand_float(r)
        x, y = am_unpack(a), am_unpack(b)
        for res in (y + x, y - x, y * x, (y / x) if x else None):
            if res is None:
                continue
            w, err = am_round(res)
            if err or res == 0 or abs(res) < Fraction(2) ** -120 or abs(res) > Fraction(2) ** 120:
                continue
            f = ieee_path(res)
            if am_unpack(w) != Fraction(f):
                bad += 1
    for _ in range(5000):
        a = rand_float(r) & 0x7FFFFFFF
        if not a & 0x800000:
            continue
        want = ieee_path(math.sqrt(float(am_unpack(a))))
        if am_unpack(sqrt_round(a)) != Fraction(want):
            bad += 1
    return bad


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "gen"
    if mode == "gen":
        bad = selfcheck()
        print("model self-check vs IEEE single path: %d mismatches" % bad)
        s = scenario()
        with open(os.path.join(HERE, "apu_vectors.hex"), "w") as f:
            f.writelines("%08x\n" % w for w in s.vec)
        with open(os.path.join(HERE, "apu_expected_reads.txt"), "w") as f:
            f.writelines("%02x\n" % x for x in s.reads)
        print("vectors: %d, reads: %d" % (len(s.vec), len(s.reads)))
    else:
        def load(n):
            with open(os.path.join(HERE, n)) as f:
                return [l.strip().lower() for l in f if l.strip()]
        e, a = load("apu_expected_reads.txt"), load("apu_reads.txt")
        bad = 0
        if len(e) != len(a):
            print("read count differs: expected %d got %d" % (len(e), len(a)))
            bad += 1
        for i, (x, y) in enumerate(zip(e, a)):
            if x != y:
                bad += 1
                if bad < 15:
                    print("read %d: expected %s got %s" % (i, x, y))
        print("reads compared: %d, mismatches: %d" % (min(len(e), len(a)), bad))
        print("RESULT: %s" % ("PASS" if bad == 0 else "FAIL"))
        sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
