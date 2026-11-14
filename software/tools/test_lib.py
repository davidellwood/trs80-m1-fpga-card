#!/usr/bin/env python3
"""
Test the Z80 library, the demo and the BASIC USR module in the emulated
Model I + card (tools/cardsim.py). Expected results come from the card
models and an independent Python implementation of the float conversion.

  python test_lib.py [--sjasm path\\to\\sjasmplus.exe]
"""
import math
import os
import sys
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cardsim                                  # noqa: E402
from cardsim import SOFT, FPGA_SIM              # noqa: E402
import apu_model                                # noqa: E402
import sprite_model                             # noqa: E402
sys.path.insert(0, FPGA_SIM)
import frame_png                                # noqa: E402

SJASM = cardsim.DEFAULT_SJASM
if "--sjasm" in sys.argv:
    SJASM = sys.argv[sys.argv.index("--sjasm") + 1]
FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print("FAIL %-34s got %s want %s" % (name, got, want))
    else:
        s = repr(got)
        print("ok   %-34s %s" % (name, s if len(s) < 40 else "(%d chars of data match)" % len(s)))


# ----------------------------------------------------- Level II single format
def mbf(x):
    """Python float -> Level II BASIC single (4 bytes), RNE to 24 bits."""
    if x == 0:
        return bytes(4)
    s = 0x80 if x < 0 else 0
    m, e = math.frexp(abs(x))
    mant = round(m * (1 << 24))
    if mant == 1 << 24:
        mant >>= 1
        e += 1
    return bytes([mant & 0xFF, (mant >> 8) & 0xFF, ((mant >> 16) & 0x7F) | s, e + 128])


def mbf_raw(m24, exp, neg=False):
    return bytes([m24 & 0xFF, (m24 >> 8) & 0xFF, ((m24 >> 16) & 0x7F) | (0x80 if neg else 0), exp])


def mbf_to_am_ref(b):
    """Independent reference conversion: -> (am bytes or None if out of range)."""
    if b[3] == 0:
        return bytes(4)
    E = b[3] - 128
    if not -64 <= E <= 63:
        return None
    return bytes([b[0], b[1], b[2] | 0x80, (b[2] & 0x80) | (E & 0x7F)])


def am_to_mbf_ref(a):
    if not a[2] & 0x80:
        return bytes(4)
    E = a[3] & 0x7F
    E = E - 128 if E & 0x40 else E
    return bytes([a[0], a[1], (a[2] & 0x7F) | (a[3] & 0x80), E + 128])


def word(b):
    return int.from_bytes(b, "little")


# ===================================================================== tests
def test_library():
    print("\n== library (test/libtest.asm)")
    code, sym = cardsim.assemble(os.path.join(SOFT, "test", "libtest.asm"), "libtest", SJASM)

    # no card: detection must fail without hanging
    m = cardsim.Machine(card=False)
    m.load(code, 0x6000)
    m.poke(sym["only_detect"], [1])
    m.call(0x6000)
    check("CARD_DETECT without card -> CF", m.peek(sym["r_detcf"])[0], 1)

    m = cardsim.Machine()
    m.load(code, 0x6000)
    # T2 inputs
    vals = [mbf(v) for v in (0.0, 1.0, -1.0, 0.5, 3.14159265, -123456.0, 1e-15, 4.5e18, 2.0 ** -64,
                             2.0 ** 62 * 1.5, -2.0 ** -60, 1e-30, 1e30)]
    vals += [mbf_raw(0x400000, 20), mbf_raw(0x123456, 250, True), mbf_raw(0x7FFFFF, 191),
             mbf_raw(0, 64), mbf_raw(0x2AAAAA, 63)]
    m.poke(sym["n_mbf"], [len(vals)])
    m.poke(sym["mbf_in"], b"".join(vals))
    # T3 inputs: (cmd, type, A, B) -> FP1: A=f(A); FP2: A = B op A
    A = apu_model.OPS
    fps = [(A['SIN'], 1, 0.5, 0), (A['COS'], 1, 1.0, 0), (A['SQRT'], 1, 2.0, 0),
           (A['LN'], 1, 10.0, 0), (A['EXP'], 1, 1.5, 0), (A['ATAN'], 1, 1.0, 0),
           (A['LOG'], 1, 1000.0, 0), (A['SQRT'], 1, -1.0, 0),            # NEG error
           (A['FADD'], 2, 1.25, 2.5), (A['FSUB'], 2, 1.25, 2.5), (A['FMUL'], 2, -3.0, 0.75),
           (A['FDIV'], 2, 4.0, 1.0), (A['PWR'], 2, 10.0, 2.0), (A['FDIV'], 2, 0.0, 1.0),
           (A['SIN'], 1, 1e30, 0)]                                       # out of Am9511 range
    tab = b"".join(bytes([c, t]) + mbf(a) + mbf(b) for c, t, a, b in fps)
    m.poke(sym["n_fp"], [len(fps)])
    m.poke(sym["fp_tab"], tab)

    m.call(0x6000)
    print("   test program ran %d T-states (%.0f ms on a Model I)" % (m.cpu.t, m.cpu.t / 1774.0))

    check("CARD_DETECT with card -> CF", m.peek(sym["r_detcf"])[0], 0)
    check("CARD_DETECT minor version", m.peek(sym["r_det"])[0], 2)

    # T2
    bad = 0
    for i, v in enumerate(vals):
        ref = mbf_to_am_ref(v)
        cf = m.peek(sym["cf_out"] + i)[0]
        am = m.peek(sym["am_out"] + 4 * i, 4)
        back = m.peek(sym["back_out"] + 4 * i, 4)
        if ref is None:
            ok = (cf == 1)
        else:
            ok = cf == 0 and am == ref and back == am_to_mbf_ref(ref) and \
                (back == v or v[3] == 0)
        bad += not ok
        if not ok:
            print("   conversion %d: in %s am %s back %s cf %d (ref %s)"
                  % (i, v.hex(), am.hex(), back.hex(), cf, ref and ref.hex()))
    check("MBF<->Am9511 conversions wrong", bad, 0)

    # T3 against the APU model
    bad = 0
    for i, (cmd, t, a, b) in enumerate(fps):
        out = m.peek(sym["fp_out"] + 6 * i, 6)
        res, st, cf = out[:4], out[4], out[5]
        am_a, am_b = mbf_to_am_ref(mbf(a)), mbf_to_am_ref(mbf(b))
        if am_a is None or am_b is None:
            want = (mbf(a), 0xFF, 1)
        else:
            apu = apu_model.Am9511()
            if t == 2:
                for x in am_b:
                    apu.push(x)
            for x in am_a:
                apu.push(x)
            apu.command(cmd)
            err = apu.status & 0x1E
            if err:
                want = (mbf(a), apu.status, 1)
            else:
                r = bytes(reversed([apu.pop() for _ in range(4)]))
                want = (am_to_mbf_ref(r), apu.status, 0)
        got = (res, st, cf)
        if got != want:
            bad += 1
            print("   FP %d (cmd %02x): got %s/%02x/%d want %s/%02x/%d"
                  % (i, cmd, res.hex(), st, cf, want[0].hex(), want[1], want[2]))
    check("FP1/FP2 results wrong", bad, 0)
    sinv = m.peek(sym["fp_out"], 4)
    print("   e.g. SIN(0.5) via FP1 -> MBF %s = %.7f" % (sinv.hex(), mbf_value(sinv)))

    # T4: replay the same commands on a fresh engine model
    e = sprite_model.Engine()
    def cmd(c, *p):
        for x in p:
            e.out(0x52, x & 0xFF)
        e.out(0x53, c)
    cmd(0x01); cmd(0x08, ord('.'))
    for i, ch in enumerate(b"LIB TEST"):
        cmd(0x0A, 10 + i, 2, ch)
    for i, ch in enumerate(b"CLIPPED"):
        if 60 + i < 64:
            cmd(0x0A, 60 + i, 4, ch)
    cmd(0x0B, 5, 40, 1); cmd(0x0D, 40, 20, 30, 10, 2, 0)
    for r, b in enumerate((0xE0, 0xA0, 0xE0)):
        e.dpram[0x400 + 2 * r], e.dpram[0x401 + 2 * r] = b, 0
    cmd(0x11, 3, 3, 3, 0x00, 0x04)
    cmd(0x20, 0, 3, 20, 10, 1); cmd(0x20, 1, 3, 21, 11, 3); cmd(0x24, 1, 1, -1)
    cmd(0x23, 2, 3); cmd(0x22, 2, 5); cmd(0x21, 2, 100, 30)
    cmd(0x40)
    frame1 = e.dpram[:1024]
    st_show = e.inp(0x53)
    cmd(0x25, 1); gx, gy = e.inp(0x52), e.inp(0x52)
    cmd(0x30, 0); mask = bytes(e.inp(0x52) for _ in range(4))
    check("frame after FRAME_SHOW", list(m.peek(sym["vid1"], 1024)), frame1)
    check("FRAME_SHOW status", m.peek(sym["r_show"])[0], st_show)
    check("SPR_GET after velocity", (m.peek(sym["r_gx"])[0], m.peek(sym["r_gy"])[0]), (gx, gy))
    check("SPR_COLLIDE mask", m.peek(sym["r_mask"], 4), mask)
    check("SPR_COLLIDE OR-result", m.peek(sym["r_any"])[0], mask[0] | mask[1] | mask[2] | mask[3])
    check("bad sprite number -> CF", m.peek(sym["r_errcf"])[0], 1)
    cmd(0x0E, 2, 1)
    img = [((1024 - i) & 0x3F) | 0x80 for i in range(1024)]
    e.dpram[:1024] = img
    cmd(0x09, 0, 0); cmd(0x40)
    check("BG_FROM + FRAME_SHOW screen", m.video(), e.dpram[:1024])
    return m


def mbf_value(b):
    if b[3] == 0:
        return 0.0
    m = ((b[2] | 0x80) << 16) | (b[1] << 8) | b[0]
    v = m / (1 << 24) * 2.0 ** (b[3] - 128)
    return -v if b[2] & 0x80 else v


def test_usr():
    print("\n== BASIC USR module (basic/cardusr.asm)")
    code, sym = cardsim.assemble(os.path.join(SOFT, "basic", "cardusr.asm"), "cardusr", SJASM)
    check("USR module fits 7D00h-7FFFh", len(code) <= 768, True)
    m = cardsim.Machine()
    m.load(code, 0x7D00)
    state = {}

    def getarg(mm):
        mm.cpu.hl = state["arg"]
        mm.cpu.pc = mm.cpu.pop()
        return False

    def retint(mm):
        state["ret"] = mm.cpu.hl
        return True
    m.traps[0x0A7F] = getarg
    m.traps[0x0A9A] = retint
    VA, VB = 0x7000, 0x7004

    def usr(n):
        state["arg"] = n
        m.call(0x7D00, sp=0x7C00)
        return state["ret"]

    m.poke(VA, mbf(0.5))
    m.poke(0x7D03, [2]); m.poke(0x7D04, [VA & 255, VA >> 8])
    r = usr(2)
    check("USR(2) SIN on a variable: status", r < 256, True)
    print("   SIN(.5) -> %.7f (true %.7f)" % (mbf_value(m.peek(VA, 4)), math.sin(0.5)))
    check("USR(2) result within 2^-23", abs(mbf_value(m.peek(VA, 4)) - math.sin(0.5)) < 2 ** -23, True)
    m.poke(VA, mbf(10.0)); m.poke(VB, mbf(2.0))
    m.poke(0x7D03, [11]); m.poke(0x7D06, [VB & 255, VB >> 8])
    usr(3)
    check("USR(3) PWR 2^10", mbf_value(m.peek(VA, 4)), 1024.0)
    m.poke(VA, mbf(-4.0)); m.poke(0x7D03, [1])
    r = usr(2)
    check("USR(2) SQRT(-4) -> error code", r, 256 + (m.apu.status & 0x7F))
    check("  variable unchanged", mbf_value(m.peek(VA, 4)), -4.0)
    m.gfx.out(0x52, ord('X')); m.gfx.out(0x53, 0x08)
    r = usr(0)
    check("USR(0) render + copy", (r < 256, m.video()), (True, [ord('X')] * 1024))
    check("USR(9) unknown -> -1", usr(9), 0xFFFF)
    return code


def test_demo(frames=40):
    print("\n== demo (demo/demo.asm)")
    code, sym = cardsim.assemble(os.path.join(SOFT, "demo", "demo.asm"), "demo", SJASM)
    m = cardsim.Machine()
    m.load(code, 0x6000)
    shots, times = [], []
    m.kbd = lambda a: 0x04 if (a & 0x40) and m.peek(sym["frames"])[0] >= frames else 0

    def on_copy(mm):
        times.append(mm.cpu.t)
        shots.append(list(mm.gfx.dpram[:1024]))
        return False
    m.traps[sym["FRAME_COPY"]] = on_copy
    m.traps[0x402D] = lambda mm: True                    # DOS exit
    m.call(0x6000)
    check("demo ran its frames", m.peek(sym["frames"])[0], frames)
    check("demo library errors", m.peek(sym["errors"])[0], 0)
    check("screen = last rendered frame", m.video(), shots[-1])
    per = [(b - a) for a, b in zip(times[1:], times[2:])]
    tz = sum(per) / len(per)
    print("   Z80 time per frame: %.0f T-states = %.1f ms at 1.774 MHz" % (tz, tz / 1774.0))
    print("   + card RENDER ~2.7 ms and APU ~0.1 ms per frame -> ~%.0f frames/s on a real Model I"
          % (1000.0 / (tz / 1774.0 + 2.8)))
    hits = sum(1 for s in shots if bytes(s[15 * 64 + 2:15 * 64 + 6]) == b"HIT!")
    print("   frames showing HIT!: %d of %d" % (hits, len(shots)))
    out = os.path.join(SOFT, "demo", "demo_frames.png")
    path = os.path.join(SOFT, "build", "demo_frames.txt")
    with open(path, "w") as f:
        for s in (shots[1], shots[len(shots) // 3], shots[2 * len(shots) // 3], shots[-1]):
            f.writelines("%02x\n" % b for b in s)
    sys.argv = ["frame_png", path, out]
    frame_png.main()
    return tz


if __name__ == "__main__":
    test_library()
    test_usr()
    test_demo()
    print("\nRESULT: %s" % ("PASS" if not FAILS else "FAIL (%d)" % len(FAILS)))
    sys.exit(1 if FAILS else 0)
