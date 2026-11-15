#!/usr/bin/env python3
"""
galsim.py - fuse-level check of the GAL JEDEC files in hardware/gal/galasm/.

For each design it parses the .jed (verifying the JEDEC fuse checksum), simulates the
GAL16V8 (simple/complex mode) or GAL22V10 fuse array over EVERY input combination,
and compares each output - 0, 1 or Z - with a Python model written from the CUPL
source (hardware/gal/*.pld). Exit status 0 only if every design matches.

    python galsim.py [jedec_dir]

The device model follows the GAL16V8 / GAL22V10 fuse maps: AND array with true and
complement columns per signal (fuse 0 = connected), per-OLMC rows, XOR / S0 polarity,
AC1 / S1 and the SYN/AC0 mode bits.
"""
import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
JDIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "gal", "galasm")
Z = "Z"


# ------------------------------------------------------------------ JEDEC
def read_jedec(path):
    text = open(path, encoding="latin-1").read()
    body = text[text.index("*"):]
    fields = [f.strip() for f in body.split("*")]
    qf, default, fuses, csum = None, 0, {}, None
    for f in fields:
        if f.startswith("QF"):
            qf = int(f[2:])
        elif f.startswith("F") and f[1:].strip().isdigit():
            default = int(f[1:])
        elif f.startswith("L"):
            addr, bits = f[1:].split(None, 1)
            bits = "".join(bits.split())
            for i, b in enumerate(bits):
                fuses[int(addr) + i] = int(b)
        elif f.startswith("C") and len(f) == 5:
            csum = int(f[1:], 16)
    fm = [fuses.get(i, default) for i in range(qf)]
    total = 0
    for i in range(0, qf, 8):
        byte = 0
        for j, b in enumerate(fm[i:i + 8]):
            byte |= b << j
        total += byte
    if csum is not None and (total & 0xFFFF) != csum:
        raise ValueError("%s: fuse checksum %04X, file says %04X" % (path, total & 0xFFFF, csum))
    return fm


# ------------------------------------------------------------------ devices
COL16 = {  # pin -> true column, per mode
    "simple": {1: 2, 2: 0, 3: 4, 4: 8, 5: 12, 6: 16, 7: 20, 8: 24, 9: 28, 11: 30, 12: 26, 13: 22, 14: 18,
               17: 14, 18: 10, 19: 6},
    "complex": {1: 2, 2: 0, 3: 4, 4: 8, 5: 12, 6: 16, 7: 20, 8: 24, 9: 28, 11: 30, 13: 26, 14: 22, 15: 18,
                16: 14, 17: 10, 18: 6},
}
COL22 = {1: 0, 2: 4, 3: 8, 4: 12, 5: 16, 6: 20, 7: 24, 8: 28, 9: 32, 10: 36, 11: 40, 13: 42, 14: 38, 15: 34,
         16: 30, 17: 26, 18: 22, 19: 18, 20: 14, 21: 10, 22: 6, 23: 2}
ROWS22 = {23: (1, 10), 22: (10, 21), 21: (21, 34), 20: (34, 49), 19: (49, 66), 18: (66, 83), 17: (83, 98),
          16: (98, 111), 15: (111, 122), 14: (122, 131)}


def row_true(fm, row, ncols, colmap, pins):
    base = row * ncols
    for c in range(ncols):
        if fm[base + c] == 0:
            pin = next((p for p, k in colmap.items() if k == (c & ~1)), None)
            if pin is None:
                return False                 # connected to a column with no signal: treat as false
            v = pins[pin]
            if c & 1:
                v ^= 1
            if not v:
                return False
    return True


class GAL16V8:
    def __init__(self, fm):
        if len(fm) != 2194:
            raise ValueError("not a GAL16V8 fuse map")
        self.fm = fm
        syn, ac0 = fm[2192], fm[2193]
        if (syn, ac0) == (1, 0):
            self.mode = "simple"
        elif (syn, ac0) == (1, 1):
            self.mode = "complex"
        else:
            raise ValueError("registered mode not supported by this checker")

    def outputs(self, pins):
        fm, mode, cols = self.fm, self.mode, COL16[self.mode]
        out = {}
        for p in range(19, 11, -1):
            i = 19 - p
            xor, ac1 = fm[2048 + i], fm[2120 + i]
            rows = range(8 * i, 8 * i + 8)
            terms = [r for r in rows if fm[2128 + r]]          # product-term enables
            if mode == "simple":
                if ac1:
                    continue                                    # input
                s = any(row_true(fm, r, 32, cols, pins) for r in terms)
                out[p] = int(s) if xor else int(not s)
            else:
                oe = (8 * i in terms) and row_true(fm, 8 * i, 32, cols, pins)
                s = any(row_true(fm, r, 32, cols, pins) for r in terms if r != 8 * i)
                out[p] = (int(s) if xor else int(not s)) if oe else Z
        return out


class GAL22V10:
    def __init__(self, fm):
        if len(fm) != 5892:
            raise ValueError("not a GAL22V10 fuse map")
        self.fm = fm

    def outputs(self, pins):
        fm = self.fm
        out = {}
        for p in range(23, 13, -1):
            s0, s1 = fm[5808 + 2 * (23 - p)], fm[5809 + 2 * (23 - p)]
            if not s1:
                continue                                        # registered: not used here
            a, b = ROWS22[p]
            oe = row_true(fm, a, 44, COL22, pins)
            s = any(row_true(fm, r, 44, COL22, pins) for r in range(a + 1, b))
            out[p] = (int(s) if s0 else int(not s)) if oe else Z
        return out


# ------------------------------------------------------------------ reference models (from the CUPL)
def m_mem_decode(v):          # rev 0.1 U4: active-high names = asserted
    win = not v["A15"] and not v["A14"] and v["A13"] and v["A12"] and not v["A11"]
    eitop = all(v[k] for k in ("A10", "A9", "A8", "A7", "A6", "A5"))
    full, rd, wr = not v["FULL_N"], not v["RD_N"], not v["WR_N"]
    sel = win and (not eitop or full)
    return {"DP_CE_N": int(not (sel and v["MEMQ"] and (rd or wr)))}


def port_5x(v):
    std = not v["A7"] and v["A6"] and not v["A5"] and v["A4"] and not v["A3"] and not v["A2"]
    altp = not v["A7"] and v["A6"] and v["A5"] and v["A4"] and not v["A3"] and not v["A2"]
    alt = not v["ALT_N"]
    return (std and not alt) or (altp and alt)


def m_io_decode(v):
    port, i, o = port_5x(v), not v["IN_N"], not v["OUT_N"]
    act = (not v["DP_CE_N"]) or (port and i) or (port and o)
    return {"IORD": int(port and i), "IOWR": int(port and o), "MEMQ": int(not i and not o), "ACT_N": int(not act)}


def m_ecb_bridge(v):
    mrd, mwr, i, o = (not v[k] for k in ("MRD_N", "MWR_N", "IN_N", "OUT_N"))
    inta, rst, ext = not v["INTAK_N"], not v["SYSRES_N"], not v["EXTMEM_N"]
    claim = v["A15"] and ext
    return {"MREQ_N": int(not (mrd or mwr)), "IORQ_N": int(not (i or o or inta)), "RD_N": int(not (mrd or i)),
            "WR_N": int(not (mwr or o)), "M1_N": int(not inta), "RESET_N": int(not rst),
            "EI_RD_N": int(not (mrd and not claim)), "EI_WR_N": int(not (mwr and not claim))}


def m_ecb_bridge_card(v):
    mrd, mwr, i, o = (not v[k] for k in ("MRD_N", "MWR_N", "IN_N", "OUT_N"))
    inta, rst = not v["INTAK_N"], not v["SYSRES_N"]
    return {"MREQ_N": int(not (mrd or mwr)), "IORQ_N": int(not (i or o or inta)), "RD_N": int(not (mrd or i)),
            "WR_N": int(not (mwr or o)), "M1_N": int(not inta), "RESET_N": int(not rst)}


def m_ecb_bridge_claim(v):
    mrd, inp = not v["MRD_N"], not v["IN_N"]
    a = {k: v[k] for k in v if k[0] == "A"}
    win = not a["A15"] and not a["A14"] and a["A13"] and a["A12"] and not a["A11"]
    eitop = all(a[k] for k in ("A10", "A9", "A8", "A7", "A6", "A5"))
    memwin = (win and not eitop) or a["A15"]
    port = (a["A7"] << 5) | (a["A6"] << 4) | (a["A5"] << 3) | (a["A4"] << 2) | (a["A3"] << 1) | a["A2"]
    ports = port in (0b010000, 0b010100, 0b011100) or (port >> 2) == 0b1100
    claim = (mrd and memwin) or (inp and ports)
    return {"DIR": int(not claim), "BUF_OE_N": int(not ((not mrd and not inp) or claim))}


def m_ecb_mem_decode(v):
    win = not v["A15"] and not v["A14"] and v["A13"] and v["A12"] and not v["A11"]
    eitop = all(v[k] for k in ("A10", "A9", "A8", "A7", "A6", "A5"))
    full, mreq, rd, wr = (not v[k] for k in ("FULL_N", "MREQ_N", "RD_N", "WR_N"))
    sel = win and (not eitop or full)
    return {"DP_CE_N": int(not (sel and mreq and (rd or wr)))}


def m_ecb_io_decode(v):
    iorq, rd, wr, m1 = (not v[k] for k in ("IORQ_N", "RD_N", "WR_N", "M1_N"))
    port = port_5x(v) and iorq and not m1
    act = (not v["DP_CE_N"]) or (port and rd) or (port and wr)
    return {"IORD": int(port and rd), "IOWR": int(port and wr), "ACT_N": int(not act)}


def m_ecb_sd_decode(v):
    iorq, rd, wr, m1, en = (not v[k] for k in ("IORQ_N", "RD_N", "WR_N", "M1_N", "EN_N"))
    sel = v["A7"] and v["A6"] and not v["A5"] and not v["A4"] and iorq and not m1 and en
    return {"SELRD": int(sel and rd), "SELWR": int(sel and wr), "BUF_OE_N": int(not (sel and (rd or wr))),
            "WAIT_N": 0 if (sel and not v["ACK"]) else Z}


def m_ecb_xmem_io(v):
    iorq, wr, rd, m1, en = (not v[k] for k in ("IORQ_N", "WR_N", "RD_N", "M1_N", "EN_N"))
    sel = (not v["A7"] and v["A6"] and not v["A5"] and not v["A4"] and not v["A3"] and not v["A2"]
           and iorq and not m1)
    p41 = sel and not v["A1"] and v["A0"]
    p42 = sel and v["A1"] and not v["A0"]
    p43 = sel and v["A1"] and v["A0"]
    return {"CLK_LO": int((p41 or p43) and wr), "CLK_HI": int((p42 or p43) and wr),
            "RB_OE_N": int(not (p43 and rd and en))}


def m_ecb_xmem_mem(v):
    mreq, rd, wr, sm, en = (not v[k] for k in ("MREQ_N", "RD_N", "WR_N", "SM_N", "EN_N"))
    ramsel = v["A15"] and mreq and (rd or wr) and en
    a14 = v["A14"]
    sa14 = (sm and a14) or (not sm and a14 and v["HI4"]) or (not sm and not a14 and v["LO4"])
    return {"RAM_CE_N": int(not ramsel), "BUF_OE_N": int(not ramsel), "SA14": int(sa14),
            "EXTMEM_N": 0 if en else Z}


A_HI = {"A15": 1, "A14": 2, "A13": 3, "A12": 4, "A11": 5, "A10": 6, "A9": 7, "A8": 8, "A7": 9, "A6": 10, "A5": 11}
DESIGNS = [
    # name, device, inputs {name: pin}, outputs {name: pin}, model
    ("mem_decode", GAL22V10, dict(A_HI, RD_N=18, WR_N=19, FULL_N=20, MEMQ=21), {"DP_CE_N": 23}, m_mem_decode),
    ("io_decode", GAL16V8, {"A7": 1, "A6": 2, "A5": 3, "A4": 4, "A3": 5, "A2": 6, "IN_N": 8, "OUT_N": 9,
                            "ALT_N": 11, "DP_CE_N": 14},
     {"IORD": 12, "IOWR": 13, "MEMQ": 15, "ACT_N": 16}, m_io_decode),
    ("ecb_bridge", GAL16V8, {"MRD_N": 1, "MWR_N": 2, "IN_N": 3, "OUT_N": 4, "INTAK_N": 5, "SYSRES_N": 6,
                             "A15": 7, "EXTMEM_N": 8},
     {"MREQ_N": 12, "IORQ_N": 13, "RD_N": 14, "WR_N": 15, "M1_N": 16, "RESET_N": 17, "EI_RD_N": 18,
      "EI_WR_N": 19}, m_ecb_bridge),
    ("ecb_bridge_card", GAL16V8, {"MRD_N": 1, "MWR_N": 2, "IN_N": 3, "OUT_N": 4, "INTAK_N": 5, "SYSRES_N": 6},
     {"MREQ_N": 12, "IORQ_N": 13, "RD_N": 14, "WR_N": 15, "M1_N": 16, "RESET_N": 17}, m_ecb_bridge_card),
    ("ecb_bridge_claim", GAL22V10, dict(A_HI, A4=13, A3=14, A2=15, MRD_N=16, IN_N=19),
     {"DIR": 17, "BUF_OE_N": 18}, m_ecb_bridge_claim),
    ("ecb_mem_decode", GAL22V10, dict(A_HI, FULL_N=13, MREQ_N=14, RD_N=15, WR_N=16), {"DP_CE_N": 23},
     m_ecb_mem_decode),
    ("ecb_io_decode", GAL16V8, {"A7": 1, "A6": 2, "A5": 3, "A4": 4, "A3": 5, "A2": 6, "IORQ_N": 7, "RD_N": 8,
                                "WR_N": 9, "ALT_N": 11, "M1_N": 14, "DP_CE_N": 15},
     {"IORD": 12, "IOWR": 13, "ACT_N": 16}, m_ecb_io_decode),
    ("ecb_sd_decode", GAL16V8, {"A7": 1, "A6": 2, "A5": 3, "A4": 4, "IORQ_N": 5, "RD_N": 6, "WR_N": 7,
                                "M1_N": 8, "ACK": 9, "EN_N": 11},
     {"WAIT_N": 12, "SELRD": 13, "SELWR": 14, "BUF_OE_N": 15}, m_ecb_sd_decode),
    ("ecb_xmem_io", GAL16V8, {"A7": 1, "A6": 2, "A5": 3, "A4": 4, "A3": 5, "A2": 6, "A1": 7, "A0": 8,
                              "IORQ_N": 9, "WR_N": 11, "RD_N": 13, "M1_N": 14, "EN_N": 17},
     {"CLK_LO": 12, "CLK_HI": 15, "RB_OE_N": 16}, m_ecb_xmem_io),
    ("ecb_xmem_mem", GAL16V8, {"A15": 1, "A14": 2, "MREQ_N": 3, "RD_N": 4, "WR_N": 5, "SM_N": 6, "EN_N": 7,
                               "LO4": 8, "HI4": 9},
     {"EXTMEM_N": 12, "RAM_CE_N": 13, "BUF_OE_N": 14, "SA14": 15}, m_ecb_xmem_mem),
]


def check(name, dev, ins, outs, model):
    gal = dev(read_jedec(os.path.join(JDIR, name + ".jed")))
    names = sorted(ins)
    bad = 0
    n = 0
    for bits in itertools.product((0, 1), repeat=len(names)):
        v = dict(zip(names, bits))
        pins = {p: 0 for p in range(1, 25)}
        for k, b in v.items():
            pins[ins[k]] = b
        got = gal.outputs(pins)
        want = model(v)
        for o, p in outs.items():
            if got.get(p) != want[o]:
                bad += 1
                if bad <= 5:
                    print("  MISMATCH %s %s: %s=%s, model %s" % (name, v, o, got.get(p), want[o]))
        n += 1
    mode = getattr(gal, "mode", "")
    print("%-15s %-8s %-7s %6d input combinations, %d outputs: %s" %
          (name, dev.__name__, mode, n, len(outs), "OK" if not bad else "%d MISMATCHES" % bad))
    return bad == 0


if __name__ == "__main__":
    ok = all([check(*d) for d in DESIGNS])
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
