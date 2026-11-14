#!/usr/bin/env python3
"""
Bootstrap the PCB for the TRS-80 Model I FPGA card.

Run with KiCad's bundled Python (it needs the pcbnew module):
    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" gen_pcb.py

It exports the netlist from the schematic with kicad-cli, then creates
../kicad/trs80_fpga_card.kicad_pcb with:
  - 2-layer board outline including the card-edge tab for J1,
  - every footprint loaded, linked to its schematic symbol (so later
    "Update PCB from Schematic" works) and placed by function,
  - all pad nets assigned (ratsnest ready to route),
  - a GND pour on B.Cu.
It also writes net classes into the .kicad_pro.

One-shot: it refuses to overwrite an existing .kicad_pcb unless --force is
given, so hand routing is never lost by accident.
"""
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

import pcbnew
from pcbnew import FromMM, VECTOR2I_MM

KICAD = r"C:\Program Files\KiCad\10.0"
SHARE_FP = os.path.join(KICAD, "share", "kicad", "footprints")
HERE = os.path.dirname(os.path.abspath(__file__))
KDIR = os.path.normpath(os.path.join(HERE, "..", "kicad"))
PROJ = "trs80_fpga_card"
LIB = PROJ
SCH = os.path.join(KDIR, PROJ + ".kicad_sch")
PCB = os.path.join(KDIR, PROJ + ".kicad_pcb")
PRO = os.path.join(KDIR, PROJ + ".kicad_pro")

# Board geometry (board-local mm; the board is drawn at page offset OX, OY).
OX, OY = 50.0, 50.0
W, H = 150.0, 110.0
TAB_X0, TAB_X1, TAB_D = 20.0, 76.0, 10.0       # card-edge tab below the board
EDGE_CX = (TAB_X0 + TAB_X1) / 2                 # J1 finger centre line

# Placement: ref -> (x, y, rotation_deg). x/y is the footprint origin:
# pin 1 for DIP/headers/axials, centre for the Tang Nano, edge fingers, holes.
PLACE = {
    # bus connectors: J1 fingers on the tab, J2 directly above (straight bus runs)
    "J1": (EDGE_CX, H + TAB_D - 3.81, 0),
    "J2": (EDGE_CX + 24.13, 96.0, 270),
    # Z80-side logic
    "U4": (8.0, 84.0, 90), "U5": (8.0, 66.0, 90),
    "U2": (44.0, 84.0, 90), "U3": (76.0, 84.0, 90),
    "U1": (42.0, 66.0, 90),
    # FPGA side
    "U7": (113.0, 18.0, 0),
    "U6": (56.0, 26.0, 90),
    "RN1": (42.0, 37.0, 0), "RN2": (66.0, 37.0, 0),
    # WAIT / INT / jumpers
    "Q9": (82.0, 104.0, 0), "Q10": (90.0, 104.0, 0),
    "R1": (82.0, 98.0, 0), "R2": (82.0, 92.5, 0),
    "D3": (100.0, 100.0, 0),
    "JP1": (110.0, 94.0, 0), "JP2": (114.0, 94.0, 0), "JP3": (118.0, 94.0, 0), "JP4": (122.0, 94.0, 0),
    # power
    "J3": (15.0, 10.0, 0),          # body extends -x from pin 1; socket opening at the left edge
    "D1": (22.0, 5.0, 0), "D2": (22.0, 11.0, 0),
    "C7": (36.0, 6.0, 0), "C8": (46.0, 6.0, 0),
    "JP5": (40.0, 14.0, 0),
    # indicators
    "D4": (134.0, 56.0, 0), "D5": (140.0, 56.0, 0),
    "R10": (134.0, 72.0, 90), "R11": (140.0, 72.0, 90),
    # expansion header
    "J4": (144.0, 76.0, 0),
    # decoupling, next to each IC
    "C1": (37.5, 60.0, 90), "C2": (46.0, 71.5, 0), "C3": (78.0, 71.5, 0),
    "C4": (10.0, 71.5, 0), "C5": (10.0, 53.0, 0), "C6": (56.0, 30.0, 0),
    # mounting holes
    "H1": (5.0, 26.0, 0), "H2": (146.0, 45.0, 0), "H3": (8.0, 104.0, 0), "H4": (146.0, 104.0, 0),
}
for i in range(8):                                   # 2N7000 data shifters in a row
    PLACE["Q%d" % (i + 1)] = (42.0 + i * 7.62, 43.0, 0)
for i, r in enumerate(["R3", "R4", "R5", "R6", "R7", "R8", "R9"]):   # pull-ups
    PLACE[r] = (105.0 + i * 5.08, 50.0, 90)

SILK = [
    ("TRS-80 MODEL I FPGA CARD  rev 0.1", 116.0, 108.2, 1.5),
    ("TO EXPANSION INTERFACE", EDGE_CX, 89.5, 1.0),
    ("M1 BUS", EDGE_CX, 108.0, 1.2),
    ("5V DC", 9.0, 19.5, 1.0),
    ("JP1 BUSY>WAIT  JP2 INT  JP3 FULL2K  JP4 PORT70", 116.0, 89.5, 0.8),
    ("JP5 BUS 5V", 40.0, 19.5, 0.8),
    ("ACT  PWR", 137.0, 75.5, 0.8),
    ("J4 PINS 7-14 = 1.8V ONLY", 133.0, 100.0, 0.8),
]


def export_netlist():
    out = os.path.join(tempfile.gettempdir(), PROJ + "_net.xml")
    subprocess.run([os.path.join(KICAD, "bin", "kicad-cli.exe"), "sch", "export", "netlist",
                    "--format", "kicadxml", "-o", out, SCH], check=True, capture_output=True)
    return ET.parse(out).getroot()


def fp_path(nick):
    if nick == LIB:
        return os.path.join(KDIR, LIB + ".pretty")
    return os.path.join(SHARE_FP, nick + ".pretty")


def seg(board, x0, y0, x1, y1, layer=pcbnew.Edge_Cuts, w=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(VECTOR2I_MM(OX + x0, OY + y0))
    s.SetEnd(VECTOR2I_MM(OX + x1, OY + y1))
    s.SetLayer(layer)
    s.SetWidth(FromMM(w))
    board.Add(s)


def write_netclasses():
    pro = {}
    if os.path.exists(PRO):
        with open(PRO) as fh:
            pro = json.load(fh)
    base = {"clearance": 0.2, "via_diameter": 0.8, "via_drill": 0.4, "microvia_diameter": 0.3,
            "microvia_drill": 0.1, "diff_pair_width": 0.2, "diff_pair_gap": 0.25,
            "diff_pair_via_gap": 0.25, "wire_width": 6, "bus_width": 12, "line_style": 0,
            "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)"}
    pro["net_settings"] = {
        "classes": [dict(base, name="Default", track_width=0.3, priority=2147483647),
                    dict(base, name="Power", track_width=0.8, clearance=0.25, via_diameter=1.0,
                         via_drill=0.5, priority=0)],
        "meta": {"version": 4},
        "netclass_assignments": None,
        "netclass_patterns": [{"netclass": "Power", "pattern": p}
                              for p in ("+5V", "+3V3", "GND", "/VIN", "/TANG_5V", "/EDGE_5V")],
    }
    rules = pro.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})
    rules["min_track_width"] = 0.15            # autorouter necks down to 0.15 at some pads
    rules["min_copper_edge_clearance"] = 0.4   # fab limit is ~0.3 for routed edges
    pro.setdefault("meta", {"filename": PROJ + ".kicad_pro", "version": 3})
    with open(PRO, "w", newline="\n") as fh:
        json.dump(pro, fh, indent=2)
        fh.write("\n")


def main():
    if os.path.exists(PCB) and "--force" not in sys.argv:
        sys.exit("%s exists; pass --force to overwrite (this discards any routing!)" % PCB)

    root = export_netlist()
    board = pcbnew.NewBoard(PCB)
    board.GetDesignSettings().SetCopperLayerCount(2)

    # ---- footprints
    fps = {}
    for comp in root.find("components"):
        ref = comp.get("ref")
        fpname = comp.findtext("footprint")
        if not fpname:
            continue                          # power symbols / flags
        nick, name = fpname.split(":")
        fp = pcbnew.FootprintLoad(fp_path(nick), name)
        if fp is None:
            sys.exit("cannot load footprint %s for %s" % (fpname, ref))
        fp.SetFPID(pcbnew.LIB_ID(nick, name))
        fp.SetReference(ref)
        fp.SetValue(comp.findtext("value"))
        sheet = comp.find("sheetpath").get("tstamps")
        fp.SetPath(pcbnew.KIID_PATH(sheet + comp.findtext("tstamps")))
        fp.SetSheetname(comp.find("sheetpath").get("names"))
        fp.SetSheetfile(PROJ + ".kicad_sch")
        # carry schematic fields over so schematic-parity DRC is clean
        fields = {f.get("name"): (f.text or "") for f in comp.iter("field")}
        for fname in ("Datasheet", "Description"):
            val = comp.findtext(fname.lower()) or fields.get(fname, "")
            if val == "~":
                val = ""
            fld = fp.GetField(fname) if hasattr(fp, "GetField") else None
            if fld is None:
                fld = fp.GetFieldByName(fname)
            if fld is not None:
                fld.SetText(val)
                fld.SetVisible(False)
        if comp.find("property[@name='exclude_from_bom']") is not None:
            fp.SetExcludedFromBOM(True)
        if ref not in PLACE:
            sys.exit("no placement for %s" % ref)
        x, y, rot = PLACE[ref]
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(VECTOR2I_MM(OX + x, OY + y))
        board.Add(fp)
        fps[ref] = fp
    unused = set(PLACE) - set(fps)
    if unused:
        sys.exit("placement entries without a part: %s" % sorted(unused))

    # ---- nets
    for net in root.find("nets"):
        ni = pcbnew.NETINFO_ITEM(board, net.get("name"))
        board.Add(ni)
        for node in net.findall("node"):
            fp = fps.get(node.get("ref"))
            if fp is None:
                continue
            pads = [p for p in fp.Pads() if p.GetNumber() == node.get("pin")]
            if not pads:
                sys.exit("%s has no pad %s" % (node.get("ref"), node.get("pin")))
            for p in pads:
                p.SetNet(ni)

    # ---- outline with card-edge tab
    pts = [(0, 0), (W, 0), (W, H), (TAB_X1, H), (TAB_X1, H + TAB_D), (TAB_X0, H + TAB_D),
           (TAB_X0, H), (0, H), (0, 0)]
    for (a, b), (c, d) in zip(pts, pts[1:]):
        seg(board, a, b, c, d)

    # ---- GND pours on both layers (main body only, not the finger tab).
    # GND is still routed as a normal net (see docs); the pours add copper.
    gnd = board.FindNet("GND")
    for layer in (pcbnew.B_Cu, pcbnew.F_Cu):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(gnd)
        z.SetLocalClearance(FromMM(0.3))
        z.SetMinThickness(FromMM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        ol = z.Outline()
        ol.NewOutline()
        for a, b in [(0.5, 0.5), (W - 0.5, 0.5), (W - 0.5, H - 0.5), (0.5, H - 0.5)]:
            ol.Append(FromMM(OX + a), FromMM(OY + b))
        board.Add(z)

    # ---- edge keep-out band (no tracks/vias): the autorouter honours rule areas,
    # but not KiCad's copper-to-edge clearance.
    K = 0.6
    bands = [(0, 0, W, K), (0, 0, K, H), (W - K, 0, W, H),
             (0, H - K, TAB_X0, H), (TAB_X1, H - K, W, H),
             (TAB_X0, H - K, TAB_X0 + K, H + TAB_D), (TAB_X1 - K, H - K, TAB_X1, H + TAB_D)]
    for (x0, y0, x1, y1) in bands:
        ra = pcbnew.ZONE(board)
        ra.SetIsRuleArea(True)
        ra.SetDoNotAllowTracks(True)
        ra.SetDoNotAllowVias(True)
        ra.SetDoNotAllowZoneFills(False)
        ra.SetDoNotAllowPads(False)
        ra.SetDoNotAllowFootprints(False)
        ra.SetLayerSet(pcbnew.LSET.AllCuMask())
        ra.SetZoneName("edge_keepout")
        o = ra.Outline()
        o.NewOutline()
        for a, b in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
            o.Append(FromMM(OX + a), FromMM(OY + b))
        board.Add(ra)

    # ---- silkscreen notes
    for s, x, y, size in SILK:
        t = pcbnew.PCB_TEXT(board)
        t.SetText(s)
        t.SetPosition(VECTOR2I_MM(OX + x, OY + y))
        t.SetLayer(pcbnew.F_SilkS)
        t.SetTextSize(VECTOR2I_MM(size, size))
        t.SetTextThickness(FromMM(max(0.12, size * 0.15)))
        board.Add(t)

    # ---- placement sanity: courtyard overlaps and parts outside the board
    def box(fp):
        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox() if not fp.GetCourtyard(pcbnew.F_CrtYd).IsEmpty() \
            else fp.GetBoundingBox(False)
        return (pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY,
                pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY)

    problems = []
    boxes = {r: box(fp) for r, fp in fps.items()}
    for r, (l, t, rr, b) in boxes.items():
        e = 0.05
        in_tab = TAB_X0 - e <= l and rr <= TAB_X1 + e and b <= H + TAB_D + e
        if l < -e or t < -e or rr > W + e or (b > H + e and not in_tab):
            problems.append("%s outside board: %.1f,%.1f..%.1f,%.1f" % (r, l, t, rr, b))
    refs = sorted(boxes)
    for i, a in enumerate(refs):
        for bref in refs[i + 1:]:
            A, B = boxes[a], boxes[bref]
            if A[0] < B[2] and B[0] < A[2] and A[1] < B[3] and B[1] < A[3]:
                problems.append("courtyard overlap %s / %s" % (a, bref))

    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(PCB)
    write_netclasses()
    # The in-process filler does not apply hole clearances reliably; refill with
    # kicad-cli (reads the project rules) and save, which also runs a DRC pass.
    subprocess.run([os.path.join(KICAD, "bin", "kicad-cli.exe"), "pcb", "drc", "--refill-zones",
                    "--save-board", "-o", os.path.join(tempfile.gettempdir(), PROJ + "_drc.rpt"), PCB],
                   check=True, capture_output=True)
    print("wrote %s: %d footprints, %d nets" % (PCB, len(fps), board.GetNetCount()))
    for p in problems:
        print("WARN", p)
    if "--boxes" in sys.argv:
        for r in refs:
            print(r, ["%.1f" % v for v in boxes[r]])


if __name__ == "__main__":
    main()
