#!/usr/bin/env python3
"""
Bootstrap hardware/card-sd/trs80_card_sd.kicad_pcb from the schematic.
Run with KiCad's Python:
    & "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" gen_card_sd_pcb.py [--force] [--boxes]

100 x 160 mm Eurocard (drawn 160 wide x 100 high): ECB plug J1 on the left (rear) edge,
bus logic, level shifters, then the Pico with its USB port at the right (front) edge.
The SD module socket, RTC and LEDs sit near the front. 2.5 mm card-guide strips top
and bottom stay clear. Once routed or edited in KiCad, do not re-run this.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbgen  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 160.0, 100.0
RAIL = 2.5

place = {
    "J1": (5.3, 50.0 + 39.37, 90),
    # bus logic
    "U1": (16.0, 30.0, 0), "U2": (16.0, 60.0, 0), "C1": (16.0, 26.0, 0), "C2": (16.0, 56.0, 0),
    "U3": (30.0, 30.0, 0), "U4": (30.0, 58.0, 0), "C3": (30.0, 26.0, 0), "C4": (30.0, 54.0, 0),
    "JP1": (16.0, 88.0, 90), "R5": (22.0, 88.0, 0),
    # level shifters
    "RN2": (42.0, 30.0, 270),
    **{"Q%d" % (i + 1): (47.0 + 12.0 * (i // 4), 31.0 + 9.0 * (i % 4), 0) for i in range(8)},
    "RN1": (70.0, 30.0, 270),
    # Pico, USB toward the front edge
    "U5": (150.0, 12.0, 270),
    "D1": (100.0, 40.0, 0), "R6": (76.0, 62.0, 0), "C7": (80.0, 40.0, 0),
    # SD module socket at the front
    "J2": (155.0, 44.0, 0), "R7": (140.0, 44.0, 270),
    # RTC
    "U6": (110.0, 52.0, 0), "C5": (110.0, 48.0, 0), "Y1": (124.0, 54.0, 90),
    "R1": (96.0, 52.0, 270), "R2": (100.0, 52.0, 270),
    "BT1": (89.0, 78.0, 0),
    # misc, LEDs at the front
    "J3": (72.0, 80.0, 90), "C6": (62.0, 72.0, 0),
    "D2": (150.0, 80.0, 90), "R3": (136.0, 80.0, 0),
    "D3": (150.0, 88.0, 90), "R4": (136.0, 88.0, 0),
}

K = 0.6
cfg = {
    "dir": os.path.join(HERE, "..", "card-sd"),
    "name": "trs80_card_sd",
    "place": place,
    "overhang": ["J1"],
    "outline": [(0, 0), (W, 0), (W, H), (0, H)],
    "pour_rect": (0, 0, W, H),
    "keepout_bands": [(0, 0, W, RAIL), (0, H - RAIL, W, H), (W - K, 0, W, H), (0, 0, K, H)],
    "silk": [("ECB SD CARD  FreHD C0-CF  PICO  REV 2.0", 70.0, 96.0, 1.5),
             ("ACT", 154.0, 80.0, 1.0), ("PWR", 154.0, 88.0, 1.0), ("SD", 155.0, 40.0, 1.0),
             ("SD MODULE AREA (lies flat)", 137.0, 63.8, 0.8)],
    # the SD breakout (about 32 x 25 mm) plugs into J2 pins-down and overhangs this area at ~8.5 mm:
    # keep anything taller than ~5 mm out of it
    "silk_rects": [(121.0, 40.2, 153.0, 65.6)],
    "power_nets": ["+5V", "+3V3", "GND", "/VSYS", "/VBAT"],
}

if __name__ == "__main__":
    boxes, problems = pcbgen.build(cfg, force="--force" in sys.argv, report_boxes="--boxes" in sys.argv)
    sys.exit(1 if problems else 0)
