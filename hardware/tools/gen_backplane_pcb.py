#!/usr/bin/env python3
"""
Bootstrap hardware/backplane/trs80_backplane.kicad_pcb from the schematic.
Run with KiCad's Python:
    & "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" gen_backplane_pcb.py [--force] [--boxes]

Layout (mm, board origin top-left):
  left  0..86   : power entry (top), bridge ICs U1-U4 + resistor packs (middle),
                  J2 IDC to the Expansion Interface and the J1 card-edge tab (bottom)
  right 86..W   : five DIN 41612 C96 ECB sockets at 20.32 mm pitch; in the gap to the
                  right of each socket: 100 nF (top), chain-bridge header (middle,
                  level with BAI/BAO and IEI/IEO), 10 uF (bottom)
Once the board has been routed or edited in KiCad, do not re-run this.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbgen  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
NS = 5                                             # ECB slots
W, H = 156.0 + 20.32 * (NS - 3), 108.0
TAB_X0, TAB_X1, TAB_D = 16.0, 72.0, 10.0
EDGE_CX = (TAB_X0 + TAB_X1) / 2
SLOT_X0, SLOT_PITCH, SLOT_Y = 92.0, 20.32, 14.0    # pin a1 of slot 1
GAP = 12.7                                         # gap centre, right of each socket

place = {
    # Model I side
    "J1": (EDGE_CX, H + TAB_D - 3.81, 0),
    "J2": (EDGE_CX + 24.13, H - 13.0, 270),
    "JP7": (78.0, 78.0, 0),
    # bridge logic
    "U1": (8.0, 40.0, 0), "U2": (22.0, 40.0, 0), "U3": (36.0, 40.0, 0), "U4": (50.0, 40.0, 0),
    "C2": (8.0, 34.5, 0), "C3": (22.0, 34.5, 0), "C4": (36.0, 34.5, 0), "C5": (50.0, 34.5, 0),
    "RN1": (8.0, 72.0, 0), "RN2": (36.0, 72.0, 0),
    "R2": (50.0, 62.0, 0),                             # EXTMEM* (ECB c10) pull-up
    "R3": (62.0, 42.0, 270), "R4": (66.0, 42.0, 270),  # Model I WAIT*/INT* pull-ups (optional)
    "JP8": (64.0, 76.0, 90), "JP9": (64.0, 80.0, 90),  # EI RD*/WR* source: 1-2 direct, 2-3 via U3
    # power entry
    "J3": (15.0, 12.0, 0),
    "J4": (24.0, 22.0, 0),
    "F1": (40.0, 10.0, 0),
    "JP6": (52.0, 10.0, 0),
    "C1": (62.0, 12.0, 0),
    "R1": (64.0, 26.0, 0),
    "D1": (78.0, 12.0, 270),
    # mounting holes
    "H1": (5.0, H - 5.0, 0), "H2": (82.0, 4.5, 0), "H3": (W - 4.5, 4.5, 0), "H4": (W - 4.5, H - 4.5, 0),
}
for s in range(NS):
    xa = SLOT_X0 + SLOT_PITCH * s
    place["J1%d" % (s + 1)] = (xa, SLOT_Y, 0)
    place["C%d" % (6 + s)] = (xa + GAP, SLOT_Y - 2.0, 90)      # 100 nF, near pins 1 (+5V)
    place["JP%d" % (1 + s)] = (xa + GAP - 1.27, SLOT_Y + 30.0, 0)
    place["C%d" % (6 + NS + s)] = (xa + GAP, SLOT_Y + 78.0, 270)    # 10 uF, near pins 32 (GND)

K = 0.6   # edge keep-out band
cfg = {
    "dir": os.path.join(HERE, "..", "backplane"),
    "name": "trs80_backplane",
    "place": place,
    "outline": [(0, 0), (W, 0), (W, H), (TAB_X1, H), (TAB_X1, H + TAB_D), (TAB_X0, H + TAB_D),
                (TAB_X0, H), (0, H)],
    "pour_rect": (0, 0, W, H),
    "keepout_bands": [(0, 0, W, K), (0, 0, K, H), (W - K, 0, W, H),
                      (0, H - K, TAB_X0, H), (TAB_X1, H - K, W, H),
                      (TAB_X0, H - K, TAB_X0 + K, H + TAB_D), (TAB_X1 - K, H - K, TAB_X1, H + TAB_D)],
    "silk": [("TRS-80 MODEL I  ECB BACKPLANE  REV 2.0", 40.0, 86.0, 1.5),
             ("M1 BUS", EDGE_CX, H - 3.5, 1.2),
             ("TO EXPANSION INTERFACE", EDGE_CX, H - 19.5, 1.0),
             *[("SLOT %d" % (s + 1), SLOT_X0 + s * SLOT_PITCH + 2.54, 2.5, 1.2) for s in range(NS)],
             ("FIT CHAIN LINKS ON EMPTY SLOTS", SLOT_X0 + (NS - 1) / 2 * SLOT_PITCH + 2.54, H - 2.5, 1.0),
             ("5V IN", 6.0, 3.0, 1.0),
             ("EI RD/WR: 1-2 DIRECT  2-3 VIA GAL (X-MEM)", 68.0, 72.5, 0.8)],
    "power_nets": ["+5V", "GND", "/VIN", "/VSW", "/EDGE_5V"],
    "layers": 4,                                       # 5 fully bused slots do not fit on 2 layers
}

if __name__ == "__main__":
    boxes, problems = pcbgen.build(cfg, force="--force" in sys.argv, report_boxes="--boxes" in sys.argv)
    sys.exit(1 if problems else 0)
