#!/usr/bin/env python3
"""
Post-route DRC clean-up for the generated boards (run with KiCad's Python):
    pcb_fixup.py <board.kicad_pcb>

Runs DRC (zones refilled, schematic parity) and fixes the routine leftovers:
  * starved_thermal   -> that GND pad gets a solid zone connection
  * net_conflict on an auto "unconnected-(...)" net whose pin name has "/"
                      -> renamed to the schematic's {slash} spelling
  * silk overlaps of a Reference field: an IC's reference moves to the
    centre of its body; any other reference is mirrored to the far side of its
    footprint, and hidden if it still collides on the next pass
  * mounting-hole references are hidden
Repeats up to 4 passes and prints the final DRC summary.
"""
import os
import re
import subprocess
import sys
import tempfile

import pcbnew

CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"


def drc(path):
    rpt = os.path.join(tempfile.gettempdir(), os.path.basename(path) + "_fix.rpt")
    subprocess.run([CLI, "pcb", "drc", "--refill-zones", "--save-board", "--schematic-parity", "-o", rpt, path],
                   check=True, capture_output=True)
    return open(rpt, encoding="utf-8").read()


def main(path):
    moved = set()
    for npass in range(4):
        txt = drc(path)
        b = pcbnew.LoadBoard(path)
        changed = False
        blocks = re.split(r"\n(?=\[)", txt)
        for blk in blocks:
            if blk.startswith("[starved_thermal]"):
                m = re.search(r"PTH pad (\w+) \[GND\] of (\w+)", blk)
                if m:
                    for p in b.FindFootprintByReference(m.group(2)).Pads():
                        if p.GetNumber() == m.group(1) and p.GetLocalZoneConnection() != pcbnew.ZONE_CONNECTION_FULL:
                            p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
                            changed = True
                            print("solid pad", m.group(2), m.group(1))
            elif blk.startswith("[net_conflict]"):
                m = re.search(r"schematic \((unconnected-\(([^)-]+)-[^)]*\))\)", blk)
                mp = re.search(r"PTH pad (\w+) \[", blk)
                if m and mp:
                    fp = b.FindFootprintByReference(m.group(2))
                    for p in fp.Pads():
                        if p.GetNumber() == mp.group(1):
                            ni = pcbnew.NETINFO_ITEM(b, m.group(1))
                            b.Add(ni)
                            p.SetNet(ni)
                            changed = True
                            print("rename net", m.group(1))
            elif blk.startswith("[silk_overlap]") or blk.startswith("[silk_over_copper]") \
                    or blk.startswith("[silk_edge_clearance]"):
                for ref in re.findall(r"Reference field of (\w+)", blk):
                    fp = b.FindFootprintByReference(ref)
                    t = fp.Reference()
                    if ref.startswith("H"):
                        t.SetVisible(False)
                    elif ref in moved:
                        t.SetVisible(False)
                        print("hide ref", ref)
                    elif ref.startswith("U"):
                        t.SetPosition(fp.GetCourtyard(pcbnew.F_CrtYd).BBox().GetCenter())
                        print("centre ref", ref)
                    else:
                        c, pos = fp.GetPosition(), t.GetPosition()
                        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
                        cc = bb.GetCenter()
                        t.SetPosition(pcbnew.VECTOR2I(2 * cc.x - pos.x, 2 * cc.y - pos.y))
                        print("mirror ref", ref)
                    moved.add(ref)
                    changed = True
        if not changed:
            break
        b.Save(path)
    txt = drc(path)
    for line in txt.splitlines():
        if line.startswith("** Found"):
            print(line)
    for line in txt.splitlines():
        if line.startswith("["):
            print("  ", line[:140])


if __name__ == "__main__":
    main(sys.argv[1])
