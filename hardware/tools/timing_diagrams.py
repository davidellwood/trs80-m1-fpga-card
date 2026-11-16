#!/usr/bin/env python3
"""
timing_diagrams.py - SVG timing diagrams for docs/bridge-card-timing.md.

    python timing_diagrams.py            (writes docs/img/timing_*.svg)

Each diagram is a list of rows. A row is (label, group, segments); a segment is
(t0, t1, state, text) with times in Z80 T-states (T = 564 ns at 1.774 MHz) and state
'1' high, '0' low, 'z' floating, 'v' valid bus value (text shown), 'x' don't care.
Propagation delays through the bridge (10-30 ns) are drawn exaggerated so the edges
can be told apart; the annotations give the real figures.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "..", "docs", "img"))

LW, TW, RH, TOP = 250, 150, 30, 46        # label width, px per T-state, row height, top margin
D = 0.07                                  # drawn propagation delay (T-states)
COL = {"z80": "#7a7a7a", "m1": "#1f5fa8", "br": "#8a4fbf", "ecb": "#c0392b", "card": "#1e8449"}
GROUP = {"z80": "Z80 inside the Model I (not on the bus)", "m1": "Model I expansion bus",
         "br": "Bridge card", "ecb": "ECB bus", "card": "ECB card"}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def x(t):
    return LW + t * TW


def wave(segs, y, color):
    hi, lo, mid = y + 5, y + RH - 7, y + RH / 2
    out = []
    for i, (t0, t1, st, txt) in enumerate(segs):
        a, b = x(t0), x(t1)
        if st in "01":
            yy = hi if st == "1" else lo
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="2"/>' % (a, yy, b, yy, color))
            if i + 1 < len(segs) and segs[i + 1][2] in "01" and segs[i + 1][2] != st:
                out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="2"/>' % (b, hi, b, lo, color))
            elif i + 1 < len(segs) and segs[i + 1][2] not in "01":
                out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="2"/>' % (b, yy, b + 3, mid, color))
        elif st == "z":
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1.5" stroke-dasharray="4 3"/>' % (a, mid, b, mid, color))
        else:
            k = min(5, (b - a) / 3)
            fill = "#ececec" if st == "x" else "#ffffff"
            out.append('<polygon points="%.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f %.1f,%.1f" fill="%s" stroke="%s" stroke-width="1.5"/>'
                       % (a, mid, a + k, hi, b - k, hi, b, mid, b - k, lo, a + k, lo, fill, color))
            if st == "x":
                for xx in range(int(a + 6), int(b - 4), 8):
                    out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#bbbbbb" stroke-width="1"/>' % (xx, lo, xx + 6, hi))
            if txt:
                out.append('<text x="%.1f" y="%.1f" font-size="11" text-anchor="middle" fill="#222">%s</text>' % ((a + b) / 2, mid + 4, esc(txt)))
    return out


def diagram(name, title, tstates, rows, marks=(), notes=(), arrows=()):
    """tstates: list of (label, t0, t1); marks: (t, text); arrows: (row_from, t_from, row_to, t_to, text)."""
    width = LW + TW * max(t1 for _, _, t1 in tstates) + 30
    height = TOP + 26 + RH * len(rows) + 30 + 16 * len(notes) + 24
    s = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
         'font-family="Segoe UI, Helvetica, Arial, sans-serif">' % (width, height, width, height),
         '<rect width="100%" height="100%" fill="#ffffff"/>',
         '<text x="14" y="24" font-size="16" font-weight="600" fill="#111">%s</text>' % esc(title)]
    y0 = TOP
    for lab, t0, t1 in tstates:                                # T-state ruler
        s.append('<rect x="%.1f" y="%d" width="%.1f" height="20" fill="#f4f6f8" stroke="#c8ccd0"/>' % (x(t0), y0, x(t1) - x(t0)))
        s.append('<text x="%.1f" y="%d" font-size="12" text-anchor="middle" fill="#333">%s</text>' % ((x(t0) + x(t1)) / 2, y0 + 14, lab))
    y = y0 + 26
    prev = None
    for i, (lab, grp, segs) in enumerate(rows):
        if grp != prev:
            s.append('<rect x="0" y="%d" width="6" height="%d" fill="%s"/>' % (y, RH * sum(1 for r in rows[i:] if r[1] == grp and True) if False else RH, COL[grp]))
        s.append('<rect x="0" y="%d" width="6" height="%d" fill="%s"/>' % (y, RH, COL[grp]))
        s.append('<text x="14" y="%d" font-size="12.5" fill="%s">%s</text>' % (y + RH / 2 + 4, COL[grp], esc(lab)))
        if i % 2 == 0:
            s.append('<rect x="%d" y="%d" width="%d" height="%d" fill="#fafbfc"/>' % (LW, y, width - LW - 20, RH))
        s += wave(segs, y, COL[grp])
        prev = grp
        y += RH
    for t, txt in marks:                                        # sample points etc.
        s.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#e67e22" stroke-width="1.2" stroke-dasharray="5 4"/>' % (x(t), y0 + 22, x(t), y))
        s.append('<text x="%.1f" y="%d" font-size="11" text-anchor="middle" fill="#e67e22">%s</text>' % (x(t), y + 13, esc(txt)))
    rowy = lambda r: y0 + 26 + RH * r + RH / 2
    for r0, t0, r1, t1, txt in arrows:                          # cause -> effect
        x0, ya, x1, yb = x(t0), rowy(r0), x(t1), rowy(r1)
        s.append('<path d="M%.1f %.1f C %.1f %.1f, %.1f %.1f, %.1f %.1f" fill="none" stroke="#555" stroke-width="1" marker-end="url(#ah)"/>'
                 % (x0, ya, x0 + 18, ya, x1 - 18, yb, x1, yb - 6))
        s.append('<text x="%.1f" y="%.1f" font-size="10.5" fill="#555">%s</text>' % (max(x0, x1) + 6, (ya + yb) / 2, esc(txt)))
    s.insert(1, '<defs><marker id="ah" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">'
                '<path d="M0,0 L6,3 L0,6 z" fill="#555"/></marker></defs>')
    yl = y + 30
    leg = [(g, COL[g]) for g in ("z80", "m1", "br", "ecb", "card") if any(r[1] == g for r in rows)]
    xx = 14
    for g, c in leg:
        s.append('<rect x="%d" y="%d" width="10" height="10" fill="%s"/>' % (xx, yl - 9, c))
        s.append('<text x="%d" y="%d" font-size="11" fill="#333">%s</text>' % (xx + 14, yl, esc(GROUP[g])))
        xx += 14 + 7 * len(GROUP[g]) + 18
    for k, n in enumerate(notes):
        s.append('<text x="14" y="%d" font-size="11" fill="#444">%s</text>' % (yl + 18 + 16 * k, esc(n)))
    s.append("</svg>")
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n").write("\n".join(s) + "\n")
    print("wrote", os.path.join(OUT, name))


def clk(n):
    """Z80 clock: high first half of each T-state."""
    segs = []
    for i in range(int(n * 2)):
        segs.append((i * 0.5, (i + 1) * 0.5, "1" if i % 2 == 0 else "0", ""))
    return segs


def pulse(t_on, t_off, end, lo="0", hi="1"):
    return [(0, t_on, hi, ""), (t_on, t_off, lo, ""), (t_off, end, hi, "")]


NOTE_D = "Bridge delays (10-30 ns) are drawn wider than scale so the edges can be told apart; one T-state is 564 ns."

# ---------------------------------------------------------------- 1. memory read
E = 4.0
R0, R1 = 1.5, 3.0                      # Z80 MREQ*/RD* active: T1 falling edge to T3 falling edge... (read ends at T3 middle)
diagram("timing_mem_read.svg", "Memory read (e.g. Z80 reads 3000h from the FPGA card's dual-port RAM)",
        [("T1", 0, 1), ("T2", 1, 2), ("T3", 2, 3), ("T1 (next)", 3, 4)],
        [("CLK", "z80", clk(E)),
         ("MREQ*  (internal)", "z80", pulse(0.5, 2.5, E)),
         ("RD*  (internal)", "z80", pulse(0.5, 2.5, E)),
         ("A0-A15", "m1", [(0, 0.15, "x", ""), (0.15, 3.15, "v", "address"), (3.15, E, "x", "")]),
         ("RD*  (Model I: MREQ* + RD*)", "m1", pulse(0.5 + D, 2.5 + D, E)),
         ("U5 RD* (LS244, +12 ns)", "br", pulse(0.5 + 2 * D, 2.5 + 2 * D, E)),
         ("EA0-EA15 (HCT244, +15 ns)", "ecb", [(0, 0.3, "x", ""), (0.3, 3.3, "v", "address"), (3.3, E, "x", "")]),
         ("MREQ*  = RD* | WR*  (GAL)", "ecb", pulse(0.5 + 3 * D, 2.5 + 3 * D, E)),
         ("RD*  = RD* | IN*  (GAL)", "ecb", pulse(0.5 + 3 * D, 2.5 + 3 * D, E)),
         ("U7 DIR (claim GAL)", "br", pulse(0.5 + 3 * D, 2.5 + 3 * D, E)),
         ("D0-D7 (ECB, card drives)", "card", [(0, 0.9, "z", ""), (0.9, 2.6 + 3 * D, "v", "data"), (2.6 + 3 * D, E, "z", "")]),
         ("D0-D7 (Model I, via U7)", "m1", [(0, 1.0, "z", ""), (1.0, 2.6 + 4 * D, "v", "data"), (2.6 + 4 * D, E, "z", "")])],
        marks=[(2.5, "Z80 samples data (T3 falling edge)")],
        arrows=[(4, 0.5 + D, 7, 0.5 + 3 * D, "GAL +15 ns"), (7, 0.5 + 3 * D, 10, 0.9, "card access")],
        notes=[NOTE_D,
               "ECB MREQ* and RD* both come from the Model I's memory RD*, so they start and end together, as on a real Z80.",
               "The claim GAL turns U7 toward the Model I only because 3000h is a card address; for a ROM or video read it stays off."])

# ---------------------------------------------------------------- 2. memory write
diagram("timing_mem_write.svg", "Memory write (e.g. Z80 writes the banked RAM at 8000h)",
        [("T1", 0, 1), ("T2", 1, 2), ("T3", 2, 3), ("T1 (next)", 3, 4)],
        [("CLK", "z80", clk(E)),
         ("MREQ*  (internal)", "z80", pulse(0.5, 2.5, E)),
         ("WR*  (internal)", "z80", pulse(1.5, 2.5, E)),
         ("A0-A15", "m1", [(0, 0.15, "x", ""), (0.15, 3.15, "v", "address"), (3.15, E, "x", "")]),
         ("D0-D7 (Model I)", "m1", [(0, 0.6, "x", ""), (0.6, 3.05, "v", "data"), (3.05, E, "x", "")]),
         ("WR*  (Model I: MREQ* + WR*)", "m1", pulse(1.5 + D, 2.5 + D, E)),
         ("MREQ*  = RD* | WR*  (GAL)", "ecb", pulse(1.5 + 3 * D, 2.5 + 3 * D, E)),
         ("WR*  = WR* | OUT*  (GAL)", "ecb", pulse(1.5 + 3 * D, 2.5 + 3 * D, E)),
         ("U7: always Model I -> ECB", "br", [(0, E, "v", "enabled, A -> B (DIR high)")]),
         ("D0-D7 (ECB, via U7)", "ecb", [(0, 0.6 + D, "x", ""), (0.6 + D, 3.05 + D, "v", "data"), (3.05 + D, E, "x", "")])],
        marks=[(2.5 + 3 * D, "card latches at WR* rising")],
        arrows=[(5, 1.5 + D, 6, 1.5 + 3 * D, "GAL +15 ns")],
        notes=[NOTE_D,
               "Difference from a real Z80: there, MREQ* starts in T1, a full T-state before WR*. The Model I bus only has the",
               "combined WR*, so ECB MREQ* starts with WR*. Cards must not rely on MREQ* leading WR* (ours latch on WR* or CE).",
               "U7 passes Model I data to ECB whenever no claimed read is in progress, so write data is ready long before WR*."])

# ---------------------------------------------------------------- 3. I/O read with WAIT
E = 6.0
diagram("timing_io_read.svg", "I/O read with WAIT (IN A,(C0h): the SD card's Pico stretches the cycle)",
        [("T1", 0, 1), ("T2", 1, 2), ("TW", 2, 3), ("TW", 3, 4), ("T3", 4, 5), ("T1 (next)", 5, 6)],
        [("CLK", "z80", clk(E)),
         ("IORQ*  (internal)", "z80", pulse(1.0, 4.5, E)),
         ("RD*  (internal)", "z80", pulse(1.0, 4.5, E)),
         ("A0-A7  (port)", "m1", [(0, 0.15, "x", ""), (0.15, 5.15, "v", "C0h"), (5.15, E, "x", "")]),
         ("IN*  (Model I: IORQ* + RD*)", "m1", pulse(1.0 + D, 4.5 + D, E)),
         ("IORQ*  = IN* | OUT* | INTAK*", "ecb", pulse(1.0 + 3 * D, 4.5 + 3 * D, E)),
         ("RD*  = RD* | IN*", "ecb", pulse(1.0 + 3 * D, 4.5 + 3 * D, E)),
         ("M1*  (stays high)", "ecb", [(0, E, "1", "")]),
         ("WAIT*  (SD card GAL)", "card", [(0, 1.0 + 4 * D, "1", ""), (1.0 + 4 * D, 3.7, "0", ""), (3.7, E, "1", "")]),
         ("WAIT*  (Model I, via 74HC07)", "m1", [(0, 1.0 + 5 * D, "1", ""), (1.0 + 5 * D, 3.7 + D, "0", ""), (3.7 + D, E, "1", "")]),
         ("U7 DIR (claimed port read)", "br", pulse(1.0 + 3 * D, 4.5 + 3 * D, E)),
         ("D0-D7 (ECB, Pico drives)", "card", [(0, 1.2, "z", ""), (1.2, 3.4, "x", ""), (3.4, 4.6 + 3 * D, "v", "data"), (4.6 + 3 * D, E, "z", "")]),
         ("D0-D7 (Model I, via U7)", "m1", [(0, 1.3, "z", ""), (1.3, 3.5, "x", ""), (3.5, 4.6 + 4 * D, "v", "data"), (4.6 + 4 * D, E, "z", "")])],
        marks=[(2.5, "WAIT* sampled: low -> extra TW"), (3.5, "sampled high: go to T3"), (4.5, "data sampled")],
        arrows=[(4, 1.0 + D, 5, 1.0 + 3 * D, "GAL"), (5, 1.0 + 3 * D, 8, 1.0 + 4 * D, "card GAL")],
        notes=[NOTE_D,
               "IORQ* + RD* with M1* high is an ordinary I/O read on ECB. The Z80 always adds one TW to I/O cycles; any card can add",
               "more by pulling ECB WAIT*, which the bridge's 74HC07 copies onto the Model I's WAIT*. Data must be valid at T3's falling edge."])

# ---------------------------------------------------------------- 4. I/O write
E = 5.0
diagram("timing_io_write.svg", "I/O write (OUT (43h),A: selects a 32K page on the banked-memory card)",
        [("T1", 0, 1), ("T2", 1, 2), ("TW", 2, 3), ("T3", 3, 4), ("T1 (next)", 4, 5)],
        [("CLK", "z80", clk(E)),
         ("IORQ*  (internal)", "z80", pulse(1.0, 3.5, E)),
         ("WR*  (internal)", "z80", pulse(1.0, 3.5, E)),
         ("A0-A7  (port)", "m1", [(0, 0.15, "x", ""), (0.15, 4.15, "v", "43h"), (4.15, E, "x", "")]),
         ("D0-D7 (Model I)", "m1", [(0, 0.6, "x", ""), (0.6, 4.05, "v", "page"), (4.05, E, "x", "")]),
         ("OUT*  (Model I: IORQ* + WR*)", "m1", pulse(1.0 + D, 3.5 + D, E)),
         ("IORQ*  = IN* | OUT* | INTAK*", "ecb", pulse(1.0 + 3 * D, 3.5 + 3 * D, E)),
         ("WR*  = WR* | OUT*", "ecb", pulse(1.0 + 3 * D, 3.5 + 3 * D, E)),
         ("D0-D7 (ECB, via U7)", "ecb", [(0, 0.6 + D, "x", ""), (0.6 + D, 4.05 + D, "v", "page"), (4.05 + D, E, "x", "")]),
         ("CLK_LO/HI (banked-memory GAL)", "card", [(0, 1.0 + 4 * D, "0", ""), (1.0 + 4 * D, 3.5 + 4 * D, "1", ""), (3.5 + 4 * D, E, "0", "")])],
        marks=[(1.0 + 4 * D, "page registers clock here")],
        arrows=[(5, 1.0 + D, 6, 1.0 + 3 * D, "GAL"), (7, 1.0 + 3 * D, 9, 1.0 + 4 * D, "card GAL")],
        notes=[NOTE_D,
               "The data is on ECB from T1 (U7 passes it through all the time), so registers that clock on the leading edge of",
               "WR* see stable data. IORQ* + WR* with M1* high is an ordinary I/O write."])

# ---------------------------------------------------------------- 5. interrupt acknowledge
E = 5.0
diagram("timing_inta.svg", "Interrupt acknowledge (Model I INTAK* -> ECB M1* + IORQ*)",
        [("T1", 0, 1), ("T2", 1, 2), ("TW", 2, 3), ("TW", 3, 4), ("T3", 4, 5)],
        [("CLK", "z80", clk(E)),
         ("M1*  (internal)", "z80", pulse(0.0, 4.5, E)),
         ("IORQ*  (internal)", "z80", pulse(2.5, 4.5, E)),
         ("INTAK*  (Model I: M1* + IORQ*)", "m1", pulse(2.5 + D, 4.5 + D, E)),
         ("M1*  = INTAK*  (GAL)", "ecb", pulse(2.5 + 3 * D, 4.5 + 3 * D, E)),
         ("IORQ*  = IN* | OUT* | INTAK*", "ecb", pulse(2.5 + 3 * D, 4.5 + 3 * D, E)),
         ("RD* / WR*  (stay high)", "ecb", [(0, E, "1", "")]),
         ("U7 (no claim: A -> B)", "br", [(0, E, "v", "not reversed: the Model I needs no vector (IM 1)")])],
        notes=[NOTE_D,
               "Difference from a real Z80: there, M1* is low on every opcode fetch. The Model I bus only reports M1* during",
               "interrupt acknowledge (INTAK*), so ECB M1* is low only then. Cards use M1* just to tell INTA apart from an I/O",
               "cycle (IORQ* with M1* high), which works. A card that needs opcode-fetch M1* (rare) won't work on this bridge."])

# ---------------------------------------------------------------- 5b. opcode fetch vs memory read
E = 7.0
diagram("timing_m1_fetch.svg", "Opcode fetch (M1 cycle) then a memory read: identical on the Model I bus",
        [("T1", 0, 1), ("T2", 1, 2), ("T3", 2, 3), ("T4", 3, 4), ("T1", 4, 5), ("T2", 5, 6), ("T3", 6, 7)],
        [("CLK", "z80", clk(E)),
         ("M1*  (internal)", "z80", pulse(0.0, 2.0, E)),
         ("MREQ*  (internal)", "z80", [(0, 0.5, "1", ""), (0.5, 2.0, "0", ""), (2.0, 2.5, "1", ""), (2.5, 3.5, "0", ""),
                                        (3.5, 4.5, "1", ""), (4.5, 6.5, "0", ""), (6.5, E, "1", "")]),
         ("RD*  (internal)", "z80", [(0, 0.5, "1", ""), (0.5, 2.0, "0", ""), (2.0, 4.5, "1", ""), (4.5, 6.5, "0", ""), (6.5, E, "1", "")]),
         ("RFSH*  (internal)", "z80", pulse(2.0, 4.0, E)),
         ("A0-A15", "m1", [(0, 0.15, "x", ""), (0.15, 2.15, "v", "PC"), (2.15, 4.15, "v", "refresh (I,R)"), (4.15, 7.0, "v", "operand address")]),
         ("RD*  (Model I: MREQ* + RD*)", "m1", [(0, 0.5 + D, "1", ""), (0.5 + D, 2.0 + D, "0", ""), (2.0 + D, 4.5 + D, "1", ""),
                                                 (4.5 + D, 6.5 + D, "0", ""), (6.5 + D, E, "1", "")]),
         ("D0-D7 (Model I)", "m1", [(0, 1.4, "z", ""), (1.4, 2.05, "v", "opcode"), (2.05, 5.4, "z", ""), (5.4, 6.55, "v", "data"), (6.55, E, "z", "")]),
         ("MREQ* / RD*  (ECB, GAL)", "ecb", [(0, 0.5 + 3 * D, "1", ""), (0.5 + 3 * D, 2.0 + 3 * D, "0", ""), (2.0 + 3 * D, 4.5 + 3 * D, "1", ""),
                                              (4.5 + 3 * D, 6.5 + 3 * D, "0", ""), (6.5 + 3 * D, E, "1", "")]),
         ("M1*  = INTAK*  (ECB)", "ecb", [(0, E, "1", "")]),
         ("RFSH*  (ECB, held by RN1)", "ecb", [(0, E, "1", "")])],
        marks=[(2.0, "opcode sampled (T3 rising)"), (6.5, "data sampled (T3 falling)")],
        notes=[NOTE_D,
               "Inside the Model I, M1* marks the fetch and RFSH* the refresh that follows it. Neither reaches the expansion bus:",
               "the fetch arrives as an ordinary RD* pulse, and the refresh doesn't arrive at all, because RD* stays high during it.",
               "So ECB M1* and RFSH* stay high. The only visible difference, a fetch's shorter RD*, is known only once RD* ends."])

# ---------------------------------------------------------------- 6. reset
E = 4.0
diagram("timing_reset.svg", "Reset (Model I SYSRES* -> ECB RESET*), and the cable unplugged",
        [("power-up / reset", 0, 2), ("running", 2, 3), ("cable unplugged", 3, 4)],
        [("SYSRES*  (Model I)", "m1", [(0, 1.6, "0", ""), (1.6, 3.0, "1", ""), (3.0, 4.0, "z", "")]),
         ("SYSRES* at U3 (R4 10k pull-down)", "br", [(0, 1.6 + D, "0", ""), (1.6 + D, 3.0, "1", ""), (3.0, 4.0, "0", "")]),
         ("RESET*  = SYSRES*  (GAL)", "ecb", [(0, 1.6 + 2 * D, "0", ""), (1.6 + 2 * D, 3.0 + D, "1", ""), (3.0 + D, 4.0, "0", "")]),
         ("Strobes at U5 (LS244 inputs)", "br", [(0, 3.0, "v", "follow the Model I"), (3.0, 4.0, "v", "float high = idle")])],
        notes=["With the ribbon unplugged, R4 holds RESET* low, so every ECB card stays in reset, and the LS244's open inputs",
               "read high, so no strobe is active. A connected Model I drives SYSRES* and overrides R4."])
