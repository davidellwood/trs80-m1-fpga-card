#!/usr/bin/env python3
"""
Bootstrap hardware/card-fpga/trs80_card_fpga.kicad_pcb from the schematic.
Run with KiCad's Python:
    & "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" gen_card_fpga_pcb.py [--force] [--boxes]

100 x 160 mm Eurocard (drawn 160 wide x 100 high). The ECB plug J1 is on the left
(rear) edge and the Tang Nano 20K's USB-C faces the right (front) edge, with the
LEDs beside it. Signal flow runs left to right: bus logic, then the DPRAM, then
the level shifters, then the FPGA. 2.5 mm strips along the top and bottom edges
are kept clear for the card guides.
Once the board has been routed or edited in KiCad, do not re-run this.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbgen  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 160.0, 100.0
RAIL = 2.5

place = {
    # ECB plug: board edge 5.3 mm behind pin row a; pins a1 (bottom) .. a32 (top), centred
    "J1": (5.3, 50.0 + 39.37, 90),
    # bus side (column A / B)
    "U2": (18.0, 9.0, 0), "U3": (18.0, 37.0, 0), "U4": (18.0, 65.0, 0),
    "U5": (32.0, 9.0, 0),
    "C2": (14.0, 15.0, 90), "C3": (14.0, 43.0, 90), "C4": (14.0, 72.0, 90), "C5": (32.0, 5.0, 0),
    "R8": (30.5, 36.0, 270), "R9": (34.5, 36.0, 270), "JP3": (30.5, 50.0, 90), "JP4": (30.5, 54.5, 90),
    "Q9": (31.0, 61.0, 0), "Q10": (31.0, 67.0, 0),
    "R1": (30.5, 72.0, 0), "R2": (30.5, 76.0, 0),
    "D3": (30.5, 81.0, 0), "JP1": (30.5, 86.0, 90), "JP2": (30.5, 91.0, 90),
    # DPRAM
    "U1": (48.0, 13.0, 0), "C1": (48.0, 8.0, 0),
    "R3": (46.0, 80.0, 0), "R4": (46.0, 85.0, 0), "R5": (46.0, 90.0, 0),
    "R6": (60.0, 80.0, 0), "R7": (60.0, 85.0, 0),
    "RN2": (70.0, 50.0, 270),
    # level shifters (2 columns x 4)
    **{"Q%d" % (i + 1): (76.0 + 12.0 * (i // 4), 52.0 + 9.0 * (i % 4), 0) for i in range(8)},
    "RN1": (100.0, 50.0, 270),
    # 5V -> 3.3V and FPGA
    "U6": (108.0, 46.0, 0), "C6": (108.0, 42.0, 0),
    "U7": (152.0, 9.5, 270),
    "C8": (120.0, 50.0, 0),
    # power, LEDs at the front edge
    "D2": (120.0, 62.0, 0), "C7": (122.0, 72.0, 0),
    "R10": (120.0, 82.0, 0), "R11": (120.0, 88.0, 0),
    "D4": (150.0, 80.0, 90), "D5": (150.0, 88.0, 90),
}

K = 0.6
cfg = {
    "dir": os.path.join(HERE, "..", "card-fpga"),
    "name": "trs80_card_fpga",
    "place": place,
    "overhang": ["J1"],
    "outline": [(0, 0), (W, 0), (W, H), (0, H)],
    "pour_rect": (0, 0, W, H),
    "keepout_bands": [(0, 0, W, RAIL), (0, H - RAIL, W, H), (W - K, 0, W, H), (0, 0, K, H)],
    "silk": [("ECB FPGA CARD  TANG NANO 20K  REV 2.0", 80.0, 96.0, 1.5),
             ("ACT", 154.0, 80.0, 1.0), ("PWR", 154.0, 88.0, 1.0)],
    "power_nets": ["+5V", "+3V3", "GND", "/TANG_5V"],
}

if __name__ == "__main__":
    boxes, problems = pcbgen.build(cfg, force="--force" in sys.argv, report_boxes="--boxes" in sys.argv)
    sys.exit(1 if problems else 0)
