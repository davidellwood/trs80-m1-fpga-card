#!/usr/bin/env python3
"""
Bootstrap hardware/card-bridge/trs80_card_bridge.kicad_pcb from the schematic.
Run with KiCad's Python:
    & "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" gen_card_bridge_pcb.py [--force] [--boxes]

100 x 160 mm Eurocard (drawn 160 wide x 100 high): ECB plug J1 on the left (rear) edge,
the Model I right-angle box header J2 on the right (front) edge, logic in between.
2.5 mm card-guide strips top and bottom stay clear. Once routed, do not re-run this.
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
    "J2": (146.0, 50.0 - 24.13, 0),          # pins 1..39 down the left row, body/opening to the front edge
    # cable side: strobe receiver, data buffer + series resistors next to the Model I header
    "U5": (114.0, 12.0, 0), "C6": (114.0, 8.0, 0),
    "U7": (114.0, 42.0, 0), "C8": (114.0, 38.0, 0),
    **{"R%d" % (5 + k): (126.0, 44.0 + 3.3 * k, 0) for k in range(8)},
    "R1": (126.0, 12.0, 0), "R2": (126.0, 16.0, 0), "R4": (126.0, 20.0, 0),
    # address buffers, bridge GAL, claim GAL, WAIT/INT driver
    "U1": (96.0, 12.0, 0), "C2": (96.0, 8.0, 0),
    "U2": (96.0, 42.0, 0), "C3": (96.0, 38.0, 0),
    "U3": (78.0, 12.0, 0), "C4": (78.0, 8.0, 0),
    "U4": (78.0, 44.0, 0), "C5": (78.0, 40.0, 0),
    "U6": (60.0, 12.0, 0), "C7": (60.0, 8.0, 0),
    # ECB-side pull-ups next to the plug
    "RN1": (30.0, 12.0, 270), "RN2": (30.0, 46.0, 270),
    # power
    "C1": (40.0, 70.0, 0), "D1": (150.0, 88.0, 90), "R3": (134.0, 88.0, 0),
    "JP1": (130.0, 80.0, 90),
}
K = 0.6
cfg = {
    "dir": os.path.join(HERE, "..", "card-bridge"),
    "name": "trs80_card_bridge",
    "place": place,
    "overhang": ["J1"],
    "outline": [(0, 0), (W, 0), (W, H), (0, H)],
    "pour_rect": (0, 0, W, H),
    "keepout_bands": [(0, 0, W, RAIL), (0, H - RAIL, W, H), (W - K, 0, W, H), (0, 0, K, H)],
    "silk": [("TRS-80 MODEL I -> ECB BRIDGE  REV 3.1  BUFFERED", 70.0, 94.0, 1.5),
             ("MODEL I BUS", 150.0, 16.0, 1.2), ("EDGE 5V", 130.0, 76.5, 0.8), ("PWR", 154.0, 88.0, 1.0)],
    "power_nets": ["+5V", "GND", "/EDGE_5V"],
}

if __name__ == "__main__":
    boxes, problems = pcbgen.build(cfg, force="--force" in sys.argv, report_boxes="--boxes" in sys.argv)
    sys.exit(1 if problems else 0)
