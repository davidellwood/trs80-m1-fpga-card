#!/usr/bin/env python3
"""
Am9511 derived functions (phase 2): coefficient fitting, microcode source,
assembler and bit-exact interpreter.

  python apu_ucode.py        -> writes ../src/am9511_ucode.vh, prints a listing
                                summary and the accuracy report

The interpreter (run_function) is imported by apu_model.py and executes
exactly what the RTL microsequencer executes, using the same primitive
semantics (each FADD/FSUB/FMUL/FDIV/SQRT/FLT rounded to 24 bits).

Micro-instruction (24 bits): [23:19] opc [18:16] d [15:13] b [12:10] a [9:0] imm
  r[d] = r[b] OP r[a]   for FADD FSUB FMUL FDIV;  SQRT/MOV/NEG/ABS/SCALE/GETX use a
"""
import math
import os
import random
import sys
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apu_model as am            # am_round, am_unpack, sqrt_round, error codes

OPC = dict(END=0, ERR=1, FADD=2, FSUB=3, FMUL=4, FDIV=5, SQRT=6, LDK=7, MOV=8, NEG=9,
           ABS=10, FIX=11, FLT=12, SCALE=13, GETX=14, JMP=15, JNEG=16, JZ=17, JBIT=18,
           ADDN=19, CALL=20, RET=21, JPOS=22)

ERRCODE = {'ARG': 0x0C, 'NEG': 0x04}        # status bits 4:1 (ERR field)


# ======================================================== coefficient fitting
def solve(M, v):
    n = len(v)
    A = [[Fraction(x) for x in row] + [Fraction(v[i])] for i, row in enumerate(M)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(A[r][c]))
        A[c], A[p] = A[p], A[c]
        for r in range(n):
            if r != c and A[r][c] != 0:
                f = A[r][c] / A[c][c]
                A[r] = [a - f * b for a, b in zip(A[r], A[c])]
    return [float(A[i][n] / A[i][i]) for i in range(n)]


def fit(g, w, lo, hi, deg, nodes=200):
    """Weighted least squares fit of g(t) ~ sum c_k t^k on Chebyshev nodes."""
    ts = [(lo + hi) / 2 + (hi - lo) / 2 * math.cos(math.pi * (k + 0.5) / nodes) for k in range(nodes)]
    M = [[0.0] * (deg + 1) for _ in range(deg + 1)]
    v = [0.0] * (deg + 1)
    for t in ts:
        wt = w(t) ** 2
        p = [t ** k for k in range(deg + 1)]
        y = g(t)
        for i in range(deg + 1):
            v[i] += wt * p[i] * y
            for j in range(deg + 1):
                M[i][j] += wt * p[i] * p[j]
    return solve(M, v)


R4 = math.pi / 4
COEF = {}
# sin r = r + r z S(z), cos r = 1 - z/2 + z^2 C(z), tan r = r + r z T(z), z = r^2, |r| <= pi/4
COEF['S'] = fit(lambda z: (math.sin(math.sqrt(z)) - math.sqrt(z)) / z ** 1.5,
                lambda z: z ** 1.5 / math.sin(math.sqrt(z)), 0, R4 * R4, 2)
COEF['C'] = fit(lambda z: (math.cos(math.sqrt(z)) - 1 + z / 2) / (z * z),
                lambda z: z * z / math.cos(math.sqrt(z)), 0, R4 * R4, 2)
COEF['T'] = fit(lambda z: (math.tan(math.sqrt(z)) - math.sqrt(z)) / z ** 1.5,
                lambda z: z ** 1.5 / math.tan(math.sqrt(z)), 0, R4 * R4, 5)
# e^r = 1 + r + r^2 Q(r), |r| <= ln2/2
L2 = math.log(2) / 2
COEF['Q'] = fit(lambda r: (math.exp(r) - 1 - r) / (r * r) if abs(r) > 1e-9 else 0.5,
                lambda r: r * r / math.exp(r), -L2, L2, 5)
# ln(1+f) = f - f^2/2 + f^3 P(f), f in [sqrt(.5)-1, sqrt(2)/2... ]
FLO, FHI = math.sqrt(0.5) - 1, math.sqrt(2) - 1
COEF['P'] = fit(lambda f: (math.log1p(f) - f + f * f / 2) / f ** 3,
                lambda f: abs(f ** 3 / math.log1p(f)), FLO, FHI, 7)
# atan x = x + x z A(z), |x| <= tan(pi/8)
TP8 = math.tan(math.pi / 8)
COEF['A'] = fit(lambda z: (math.atan(math.sqrt(z)) - math.sqrt(z)) / z ** 1.5,
                lambda z: z ** 1.5 / math.atan(math.sqrt(z)), 0, TP8 * TP8, 3)
# asin t = t + t z B(z), |t| <= 0.5
COEF['B'] = fit(lambda z: (math.asin(math.sqrt(z)) - math.sqrt(z)) / z ** 1.5,
                lambda z: z ** 1.5 / math.asin(math.sqrt(z)), 0, 0.25, 4)


def split(x, bits):
    """Truncate x to `bits` significant bits (for exact Cody-Waite products)."""
    e = math.frexp(x)[1]
    s = 2.0 ** (bits - e)
    return math.floor(x * s) / s


C1 = 0.693359375                                       # ln2 high part (9 bits)
C2 = math.log(2) - C1
DP1 = split(math.pi / 4, 8)
DP2 = split(math.pi / 4 - DP1, 12)
DP3 = math.pi / 4 - DP1 - DP2

KONST = dict(ZERO=0.0, HALF=0.5, ONE=1.0, K32=32.0, LOG2E=1 / math.log(2), LN2HI=C1, LN2LO=C2,
             SQRTHF=math.sqrt(0.5), LOG10E=math.log10(math.e), FOPI=4 / math.pi,
             DP1=DP1, DP2=DP2, DP3=DP3, TSMALL=2.0 ** -12, TAN3PI8=math.tan(3 * math.pi / 8),
             TANPI8=TP8, PIO2=math.pi / 2, PIO4=math.pi / 4, PI=math.pi)
for name, cs in COEF.items():
    for i, c in enumerate(cs):
        KONST['%s%d' % (name, i)] = c


# ======================================================== microcode source
def horner(prefix, n, x, acc='r4', tmp='r3'):
    """acc = c[n] ; acc = acc*x + c[k] ... -> acc = P(x)"""
    out = [('LDK', acc, '%s%d' % (prefix, n))]
    for k in range(n - 1, -1, -1):
        out += [('FMUL', acc, acc, x), ('LDK', tmp, '%s%d' % (prefix, k)), ('FADD', acc, acc, tmp)]
    return out


def source():
    P = []
    L = lambda name: P.append(('LABEL', name))
    I = lambda *ins: P.append(tuple(ins))

    # -------- errors
    L('err_arg'); I('ERR', 'ARG')
    L('err_neg'); I('ERR', 'NEG')

    # -------- EXP: |x| <= 32 else ARG
    L('EXP')
    I('ABS', 'r2', 'r0'); I('LDK', 'r3', 'K32'); I('FSUB', 'r2', 'r2', 'r3'); I('JPOS', 'r2', 'err_arg')
    I('CALL', 'expc'); I('END', 'r2')

    # expc: r2 = e^r0   (uses r2..r5)
    L('expc')
    I('LDK', 'r3', 'LOG2E'); I('FMUL', 'r2', 'r0', 'r3'); I('LDK', 'r3', 'HALF')
    I('JNEG', 'r2', 'e_neg'); I('FADD', 'r2', 'r2', 'r3'); I('JMP', 'e_fix')
    L('e_neg'); I('FSUB', 'r2', 'r2', 'r3')
    L('e_fix'); I('FIX', 'r2'); I('FLT', 'r4')
    I('LDK', 'r3', 'LN2HI'); I('FMUL', 'r5', 'r4', 'r3'); I('FSUB', 'r2', 'r0', 'r5')
    I('LDK', 'r3', 'LN2LO'); I('FMUL', 'r5', 'r4', 'r3'); I('FSUB', 'r2', 'r2', 'r5')
    P.extend(horner('Q', 5, 'r2'))
    I('FMUL', 'r5', 'r2', 'r2'); I('FMUL', 'r4', 'r4', 'r5'); I('FADD', 'r4', 'r4', 'r2')
    I('LDK', 'r3', 'ONE'); I('FADD', 'r4', 'r4', 'r3')
    I('SCALE', 'r2', 'r4'); I('RET')

    # -------- LN / LOG: x <= 0 -> NEG
    L('LN')
    I('JZ', 'r0', 'err_neg'); I('JNEG', 'r0', 'err_neg'); I('CALL', 'lnc'); I('END', 'r2')
    L('LOG')
    I('JZ', 'r0', 'err_neg'); I('JNEG', 'r0', 'err_neg'); I('CALL', 'lnc')
    I('LDK', 'r3', 'LOG10E'); I('FMUL', 'r2', 'r2', 'r3'); I('END', 'r2')

    # lnc: r2 = ln(r0), r0 > 0   (uses r2..r7)
    L('lnc')
    I('GETX', 'r2', 'r0'); I('LDK', 'r3', 'SQRTHF'); I('FSUB', 'r4', 'r2', 'r3'); I('JNEG', 'r4', 'l_small')
    I('LDK', 'r3', 'ONE'); I('FSUB', 'r2', 'r2', 'r3'); I('JMP', 'l_poly')
    L('l_small'); I('ADDN', -1); I('FADD', 'r2', 'r2', 'r2'); I('LDK', 'r3', 'ONE'); I('FSUB', 'r2', 'r2', 'r3')
    L('l_poly'); I('FMUL', 'r5', 'r2', 'r2')
    P.extend(horner('P', 7, 'r2'))
    I('FMUL', 'r4', 'r4', 'r2'); I('FMUL', 'r4', 'r4', 'r5'); I('FLT', 'r6')
    I('LDK', 'r3', 'LN2LO'); I('FMUL', 'r7', 'r6', 'r3'); I('FADD', 'r4', 'r4', 'r7')
    I('LDK', 'r3', 'HALF'); I('FMUL', 'r7', 'r5', 'r3'); I('FSUB', 'r4', 'r4', 'r7')
    I('FADD', 'r2', 'r2', 'r4')
    I('LDK', 'r3', 'LN2HI'); I('FMUL', 'r7', 'r6', 'r3'); I('FADD', 'r2', 'r2', 'r7'); I('RET')

    # -------- PWR: r1 = B (base, NOS), r0 = A (TOS); result B^A
    L('PWR')
    I('JNEG', 'r1', 'err_neg'); I('JZ', 'r1', 'err_arg')
    I('MOV', 'r2', 'r0'); I('MOV', 'r0', 'r1'); I('MOV', 'r1', 'r2')   # r0 = B, r1 = A
    I('CALL', 'lnc'); I('FMUL', 'r0', 'r2', 'r1')
    I('ABS', 'r2', 'r0'); I('LDK', 'r3', 'K32'); I('FSUB', 'r2', 'r2', 'r3'); I('JPOS', 'r2', 'err_arg')
    I('CALL', 'expc'); I('END', 'r2')

    # -------- trig reduction: r6 = |x| -> N even octant, r2 = r, r5 = r^2
    L('trig_red')
    I('LDK', 'r3', 'FOPI'); I('FMUL', 'r2', 'r6', 'r3'); I('FIX', 'r2'); I('JBIT', 0, 't_odd'); I('JMP', 't_even')
    L('t_odd'); I('ADDN', 1)
    L('t_even'); I('FLT', 'r4')
    for k in ('DP1', 'DP2', 'DP3'):
        I('LDK', 'r3', k); I('FMUL', 'r5', 'r4', 'r3')
        I('FSUB', 'r2', 'r6' if k == 'DP1' else 'r2', 'r5')
    I('FMUL', 'r5', 'r2', 'r2'); I('RET')

    # sincos: r4 = sin/cos(r2) chosen by N bit1, negated by N bit2
    L('sincos')
    I('JBIT', 1, 's_cos')
    P.extend(horner('S', 2, 'r5'))
    I('FMUL', 'r4', 'r4', 'r5'); I('FMUL', 'r4', 'r4', 'r2'); I('FADD', 'r4', 'r4', 'r2'); I('JMP', 's_sign')
    L('s_cos')
    P.extend(horner('C', 2, 'r5'))
    I('FMUL', 'r4', 'r4', 'r5'); I('FMUL', 'r4', 'r4', 'r5')
    I('LDK', 'r3', 'HALF'); I('FMUL', 'r7', 'r5', 'r3'); I('FSUB', 'r4', 'r4', 'r7')
    I('LDK', 'r3', 'ONE'); I('FADD', 'r4', 'r4', 'r3')
    L('s_sign'); I('JBIT', 2, 's_neg'); I('RET')
    L('s_neg'); I('NEG', 'r4', 'r4'); I('RET')

    L('SIN')
    I('ABS', 'r6', 'r0'); I('CALL', 'trig_red'); I('CALL', 'sincos')
    I('JNEG', 'r0', 'sin_n'); I('END', 'r4')
    L('sin_n'); I('NEG', 'r4', 'r4'); I('END', 'r4')
    L('COS')
    I('ABS', 'r6', 'r0'); I('CALL', 'trig_red'); I('ADDN', 2); I('CALL', 'sincos'); I('END', 'r4')

    L('TAN')
    I('ABS', 'r2', 'r0'); I('LDK', 'r3', 'TSMALL'); I('FSUB', 'r2', 'r2', 'r3'); I('JNEG', 'r2', 'tan_tiny')
    I('ABS', 'r6', 'r0'); I('CALL', 'trig_red')
    P.extend(horner('T', 5, 'r5'))
    I('FMUL', 'r4', 'r4', 'r5'); I('FMUL', 'r4', 'r4', 'r2'); I('FADD', 'r4', 'r4', 'r2')
    I('JBIT', 1, 'tan_inv'); I('JMP', 'tan_sg')
    L('tan_inv'); I('LDK', 'r3', 'ONE'); I('FDIV', 'r4', 'r3', 'r4'); I('NEG', 'r4', 'r4')
    L('tan_sg'); I('JNEG', 'r0', 'tan_n'); I('END', 'r4')
    L('tan_n'); I('NEG', 'r4', 'r4'); I('END', 'r4')
    L('tan_tiny'); I('END', 'r0')

    # -------- ATAN
    L('ATAN')
    I('ABS', 'r2', 'r0')
    I('LDK', 'r3', 'TAN3PI8'); I('FSUB', 'r4', 'r2', 'r3'); I('JPOS', 'r4', 'at_big')
    I('LDK', 'r3', 'TANPI8'); I('FSUB', 'r4', 'r2', 'r3'); I('JPOS', 'r4', 'at_mid')
    I('LDK', 'r6', 'ZERO'); I('JMP', 'at_poly')
    L('at_big'); I('LDK', 'r3', 'ONE'); I('FDIV', 'r2', 'r3', 'r2'); I('NEG', 'r2', 'r2')
    I('LDK', 'r6', 'PIO2'); I('JMP', 'at_poly')
    L('at_mid'); I('LDK', 'r3', 'ONE'); I('FSUB', 'r4', 'r2', 'r3'); I('FADD', 'r5', 'r2', 'r3')
    I('FDIV', 'r2', 'r4', 'r5'); I('LDK', 'r6', 'PIO4')
    L('at_poly'); I('FMUL', 'r5', 'r2', 'r2')
    P.extend(horner('A', 3, 'r5'))
    I('FMUL', 'r4', 'r4', 'r5'); I('FMUL', 'r4', 'r4', 'r2'); I('FADD', 'r4', 'r4', 'r2')
    I('FADD', 'r4', 'r4', 'r6')
    I('JNEG', 'r0', 'at_n'); I('END', 'r4')
    L('at_n'); I('NEG', 'r4', 'r4'); I('END', 'r4')

    # asinc: r4 = asin(r2), |r2| <= 0.5   (uses r3..r5)
    L('asinc')
    I('FMUL', 'r5', 'r2', 'r2')
    P.extend(horner('B', 4, 'r5'))
    I('FMUL', 'r4', 'r4', 'r5'); I('FMUL', 'r4', 'r4', 'r2'); I('FADD', 'r4', 'r4', 'r2'); I('RET')
    # half-angle helper: r2 = sqrt((1 - |x|)/2), from r2 = |x|
    L('half')
    I('LDK', 'r3', 'ONE'); I('FSUB', 'r5', 'r3', 'r2'); I('LDK', 'r3', 'HALF')
    I('FMUL', 'r5', 'r5', 'r3'); I('SQRT', 'r2', 'r5'); I('RET')

    # -------- ASIN / ACOS: |x| > 1 -> ARG
    for fn in ('ASIN', 'ACOS'):
        L(fn)
        I('ABS', 'r2', 'r0'); I('LDK', 'r3', 'ONE'); I('FSUB', 'r4', 'r2', 'r3'); I('JPOS', 'r4', 'err_arg')
        I('LDK', 'r3', 'HALF'); I('FSUB', 'r4', 'r2', 'r3'); I('JPOS', 'r4', fn + '_big')
        if fn == 'ASIN':
            I('CALL', 'asinc'); I('JMP', 'as_sg')
            L('ASIN_big'); I('CALL', 'half'); I('CALL', 'asinc'); I('FADD', 'r4', 'r4', 'r4')
            I('LDK', 'r3', 'PIO2'); I('FSUB', 'r4', 'r3', 'r4')
            L('as_sg'); I('JNEG', 'r0', 'as_n'); I('END', 'r4')
            L('as_n'); I('NEG', 'r4', 'r4'); I('END', 'r4')
        else:
            I('MOV', 'r2', 'r0'); I('CALL', 'asinc'); I('LDK', 'r3', 'PIO2'); I('FSUB', 'r4', 'r3', 'r4')
            I('END', 'r4')
            L('ACOS_big'); I('CALL', 'half'); I('CALL', 'asinc'); I('FADD', 'r4', 'r4', 'r4')
            I('JNEG', 'r0', 'ac_n'); I('END', 'r4')
            L('ac_n'); I('LDK', 'r3', 'PI'); I('FSUB', 'r4', 'r3', 'r4'); I('END', 'r4')
    return P


ENTRY = ['SIN', 'COS', 'TAN', 'ASIN', 'ACOS', 'ATAN', 'LOG', 'LN', 'EXP', 'PWR']   # codes 2..0x0B


# ======================================================== assembler
def assemble():
    src = source()
    kidx = {name: i for i, name in enumerate(KONST)}
    labels, pc = {}, 0
    for ins in src:
        if ins[0] == 'LABEL':
            labels[ins[1]] = pc
        else:
            pc += 1
    reg = lambda r: int(r[1])
    code = []
    for ins in src:
        if ins[0] == 'LABEL':
            continue
        op, args = ins[0], ins[1:]
        d = b = a = imm = 0
        if op in ('FADD', 'FSUB', 'FMUL', 'FDIV'):
            d, b, a = reg(args[0]), reg(args[1]), reg(args[2])
        elif op in ('SQRT', 'MOV', 'NEG', 'ABS', 'SCALE', 'GETX'):
            d, a = reg(args[0]), reg(args[1])
        elif op == 'LDK':
            d, imm = reg(args[0]), kidx[args[1]]
        elif op in ('END', 'FIX'):
            a = reg(args[0])
        elif op == 'FLT':
            d = reg(args[0])
        elif op == 'ERR':
            imm = ERRCODE[args[0]]
        elif op in ('JMP', 'CALL'):
            imm = labels[args[0]]
        elif op in ('JNEG', 'JZ', 'JPOS'):
            a, imm = reg(args[0]), labels[args[1]]
        elif op == 'JBIT':
            a, imm = args[0], labels[args[1]]
        elif op == 'ADDN':
            imm = args[0] & 0x3FF
        code.append((OPC[op] << 19) | (d << 16) | (b << 13) | (a << 10) | imm)
    kwords = [am.fl(v) for v in KONST.values()]
    entries = [labels[f] for f in ENTRY]
    return code, kwords, entries, labels


CODE, KWORDS, ENTRIES, LABELS = assemble()


# ======================================================== interpreter
def _neg(v):
    return v ^ 0x80000000 if v & 0x800000 else v


def run_function(code5, a_word, b_word):
    """Execute derived function `code5` (2..0x0B) -> (result_word or None, err)."""
    r = [0] * 8
    r[0], r[1] = a_word, b_word
    N, link, pend = 0, 0, 0
    pc = ENTRIES[code5 - 2]
    for _ in range(10000):
        ins = CODE[pc]
        opc, d, b, a, imm = ins >> 19, (ins >> 16) & 7, (ins >> 13) & 7, (ins >> 10) & 7, ins & 0x3FF
        pc += 1
        if opc == 0:
            return (None, pend) if pend else (r[a], 0)
        if opc == 1:
            return None, imm << 1                       # ERR field -> status bits
        if opc in (2, 3, 4, 5):
            x, y = am.am_unpack(r[b]), am.am_unpack(r[a])
            if opc == 2:
                v = x + y
            elif opc == 3:
                v = x - y
            elif opc == 4:
                v = x * y
            else:
                if y == 0:
                    r[d] = 0 if not r[b] & 0x800000 else r[b]
                    continue
                v = x / y
            r[d] = am.am_round(v)[0]
        elif opc == 6:
            if r[a] & 0x800000 and r[a] & 0x80000000:
                return None, am.ERR_ARG
            r[d] = am.sqrt_round(r[a])
        elif opc == 7:
            r[d] = KWORDS[imm]
        elif opc == 8:
            r[d] = r[a]
        elif opc == 9:
            r[d] = _neg(r[a])
        elif opc == 10:
            r[d] = r[a] & 0x7FFFFFFF
        elif opc == 11:
            x = am.am_unpack(r[a])
            if x < -(1 << 31) or x >= (1 << 31):
                return None, am.ERR_ARG
            N = int(x)
        elif opc == 12:
            r[d] = am.am_round(Fraction(N))[0]
        elif opc == 13:
            v = r[a]
            if not v & 0x800000:
                r[d] = 0
            else:
                e = (v >> 24) & 0x7F
                e = e - 128 if e & 0x40 else e
                n = max(-255, min(255, N))
                e2 = e + n
                if e2 > 63:
                    pend |= am.ERR_OVF
                elif e2 < -64:
                    pend |= am.ERR_UND
                r[d] = (v & 0x80FFFFFF) | ((e2 & 0x7F) << 24)
        elif opc == 14:
            v = r[a]
            e = (v >> 24) & 0x7F
            N = e - 128 if e & 0x40 else e
            r[d] = v & 0x80FFFFFF
        elif opc == 15:
            pc = imm
        elif opc == 16:
            if r[a] & 0x800000 and r[a] & 0x80000000:
                pc = imm
        elif opc == 17:
            if not r[a] & 0x800000:
                pc = imm
        elif opc == 18:
            if (N >> a) & 1:
                pc = imm
        elif opc == 19:
            N += imm - 1024 if imm & 0x200 else imm
            N = ((N + (1 << 31)) & 0xFFFFFFFF) - (1 << 31)
        elif opc == 20:
            link, pc = pc, imm
        elif opc == 21:
            pc = link
        elif opc == 22:
            if r[a] & 0x800000 and not r[a] & 0x80000000:
                pc = imm
    raise RuntimeError("microcode did not terminate")


# ======================================================== accuracy report
REF = {2: math.sin, 3: math.cos, 4: math.tan, 5: math.asin, 6: math.acos, 7: math.atan,
       8: math.log10, 9: math.log, 0x0A: math.exp}
NAMES = {2: 'SIN', 3: 'COS', 4: 'TAN', 5: 'ASIN', 6: 'ACOS', 7: 'ATAN', 8: 'LOG', 9: 'LN',
         0x0A: 'EXP', 0x0B: 'PWR'}
DOMAIN = {2: (-10, 10), 3: (-10, 10), 4: (-1.5, 1.5), 5: (-1, 1), 6: (-1, 1), 7: (-50, 50),
          8: (1e-6, 1e6), 9: (1e-6, 1e6), 0x0A: (-32, 32)}


def ulp_err(word, true):
    """Error of `word` against the true value, in ulps of the correctly rounded result."""
    if true == 0:
        return 0.0 if not word & 0x800000 else float('inf')
    cr = am.am_round(Fraction(true))[0]
    e = (cr >> 24) & 0x7F
    e = e - 128 if e & 0x40 else e
    ulp = 2.0 ** (e - 24)
    return abs(float(am.am_unpack(word)) - true) / ulp


def accuracy(n=4000, seed=7):
    rng = random.Random(seed)
    rep = {}
    for c in list(REF) + [0x0B]:
        worst, tot, cnt, exact = 0.0, 0.0, 0, 0
        for _ in range(n):
            if c == 0x0B:
                bv = rng.uniform(0.01, 100)
                av = rng.uniform(-4, 4)
                bw, aw = am.fl(bv), am.fl(av)
                true = float(am.am_unpack(bw)) ** float(am.am_unpack(aw))
            else:
                lo, hi = DOMAIN[c]
                if c in (8, 9):
                    xv = math.exp(rng.uniform(math.log(lo), math.log(hi)))
                else:
                    xv = rng.uniform(lo, hi)
                aw, bw = am.fl(xv), 0
                true = REF[c](float(am.am_unpack(aw)))
            res, err = run_function(c, aw, bw)
            if res is None:
                continue
            u = ulp_err(res, true)
            worst = max(worst, u)
            tot += u
            cnt += 1
            exact += (res == am.am_round(Fraction(true))[0])
        rep[NAMES[c]] = (worst, tot / max(cnt, 1), exact / max(cnt, 1))
    return rep


def write_vh(path):
    with open(path, "w", newline="\n") as f:
        f.write("// Generated by fpga/sim/apu_ucode.py - do not edit.\n")
        f.write("// Am9511 derived-function microcode (%d words) and constants (%d).\n"
                % (len(CODE), len(KWORDS)))
        f.write("initial begin\n")
        for i in range(512):
            f.write("    urom[%d] = 24'h%06x;\n" % (i, CODE[i] if i < len(CODE) else 0))
        for i in range(64):
            f.write("    krom[%d] = 32'h%08x;\n" % (i, KWORDS[i] if i < len(KWORDS) else 0))
        f.write("end\n")
        f.write("function [9:0] uentry(input [4:0] c);\n    case (c)\n")
        for i, e in enumerate(ENTRIES):
            f.write("        5'h%02x: uentry = 10'd%d;   // %s\n" % (i + 2, e, ENTRY[i]))
        f.write("        default: uentry = 10'd0;\n    endcase\nendfunction\n")


if __name__ == "__main__":
    assert len(CODE) <= 512 and len(KWORDS) <= 64
    out = os.path.normpath(os.path.join(HERE, "..", "src", "am9511_ucode.vh"))
    write_vh(out)
    print("microcode: %d words, constants: %d -> %s" % (len(CODE), len(KWORDS), out))
    print("%-5s %10s %10s %8s" % ("fn", "max ulp", "mean ulp", "exact"))
    for k, (w, m, ex) in accuracy().items():
        print("%-5s %10.2f %10.3f %7.1f%%" % (k, w, m, ex * 100))
