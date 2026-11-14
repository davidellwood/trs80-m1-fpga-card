#!/usr/bin/env python3
"""
Bootstrap hardware/card-xmem/trs80_card_xmem.kicad_pcb from the schematic.
Run with KiCad's Python:
    & "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" gen_card_xmem_pcb.py [--force] [--boxes]

100 x 160 mm Eurocard (drawn 160 wide x 100 high), ECB plug J1 on the left edge; all
logic sits close to the connector to keep the bus runs short (the original X-MEM/80
notes that its timing is tight). Once routed or edited in KiCad, do not re-run this.
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
    # bus side
    "U2": (18.0, 9.0, 0), "U3": (18.0, 38.0, 0), "U4": (18.0, 67.0, 0),
    "C2": (14.0, 15.0, 90), "C3": (14.0, 44.0, 90), "C4": (14.0, 73.0, 90),
    # SRAM and address mux
    "U1": (34.0, 12.0, 0), "C1": (34.0, 7.5, 0),
    "U7": (34.0, 62.0, 0), "C7": (34.0, 58.0, 0),
    # page registers + readback
    "U5": (62.0, 12.0, 0), "C5": (62.0, 7.5, 0),
    "U6": (62.0, 42.0, 0), "C6": (62.0, 38.0, 0),
    "U8": (76.0, 12.0, 0), "C8": (76.0, 7.5, 0),
    # jumpers, bulk, LED
    "JP1": (76.0, 46.0, 90), "R1": (84.0, 46.0, 0),
    "JP2": (76.0, 54.0, 90), "R2": (84.0, 54.0, 0),
    "C9": (80.0, 64.0, 0),
    "D1": (150.0, 88.0, 90), "R3": (134.0, 88.0, 0),
}

K = 0.6
cfg = {
    "dir": os.path.join(HERE, "..", "card-xmem"),
    "name": "trs80_card_xmem",
    "place": place,
    "overhang": ["J1"],
    "outline": [(0, 0), (W, 0), (W, H), (0, H)],
    "pour_rect": (0, 0, W, H),
    "keepout_bands": [(0, 0, W, RAIL), (0, H - RAIL, W, H), (W - K, 0, W, H), (0, 0, K, H)],
    "silk": [("ECB 512K BANKED MEMORY  X-MEM/80 COMPATIBLE  REV 2.0", 80.0, 94.0, 1.5),
             ("JP1 FIT = SUPERMEM (OUT 43h)   OPEN = X-MEM (OUT 41h/42h)", 126.0, 47.0, 1.0),
             ("JP2 FIT = ENABLE", 108.0, 55.0, 1.0),
             ("PWR", 154.0, 88.0, 1.0)],
    "power_nets": ["+5V", "GND"],
}

if __name__ == "__main__":
    boxes, problems = pcbgen.build(cfg, force="--force" in sys.argv, report_boxes="--boxes" in sys.argv)
    sys.exit(1 if problems else 0)
