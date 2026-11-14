#!/usr/bin/env python3
"""
pcbgen - shared PCB bootstrap helpers (run under KiCad's bundled Python).

build(cfg) creates <dir>/<name>.kicad_pcb from the schematic netlist:
footprints loaded, linked to their symbols, placed, nets assigned, outline,
GND pours, edge keep-out band, silkscreen notes, net classes and rules in
the .kicad_pro, then zones refilled and saved by kicad-cli.

cfg keys: dir, name, place {ref: (x, y, rot)}, outline [(x, y), ...] (closed),
          pour_rect (x0, y0, x1, y1), keepout_bands [(x0, y0, x1, y1)], silk
          [(text, x, y, size)], power_nets [...], origin (ox, oy), overhang [refs allowed past the edge]
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
CLI = os.path.join(KICAD, "bin", "kicad-cli.exe")


def _netlist(sch):
    out = os.path.join(tempfile.gettempdir(), os.path.basename(sch) + "_net.xml")
    subprocess.run([CLI, "sch", "export", "netlist", "--format", "kicadxml", "-o", out, sch],
                   check=True, capture_output=True)
    return ET.parse(out).getroot()


def build(cfg, force=False, report_boxes=False):
    d, name = cfg["dir"], cfg["name"]
    OX, OY = cfg.get("origin", (50.0, 50.0))
    sch, pcb, pro = (os.path.join(d, name + ext) for ext in (".kicad_sch", ".kicad_pcb", ".kicad_pro"))
    if os.path.exists(pcb) and not force:
        sys.exit("%s exists; pass --force to overwrite (this discards any routing!)" % pcb)
    root = _netlist(sch)
    libs = {}
    for line in open(os.path.join(d, "fp-lib-table")):
        if "(name" in line:
            n = line.split('(name "')[1].split('"')[0]
            libs[n] = os.path.join(d, n + ".pretty")
    board = pcbnew.NewBoard(pcb)
    nlayers = cfg.get("layers", 2)
    board.GetDesignSettings().SetCopperLayerCount(nlayers)
    ls = board.GetEnabledLayers()
    for lid in ([pcbnew.In1_Cu, pcbnew.In2_Cu] if nlayers >= 4 else []):
        ls.AddLayer(lid)
    board.SetEnabledLayers(ls)
    fps = {}
    for comp in root.find("components"):
        ref, fpname = comp.get("ref"), comp.findtext("footprint")
        if not fpname:
            continue
        nick, fn = fpname.split(":")
        fp = pcbnew.FootprintLoad(libs.get(nick, os.path.join(SHARE_FP, nick + ".pretty")), fn)
        if fp is None:
            sys.exit("cannot load %s for %s" % (fpname, ref))
        fp.SetFPID(pcbnew.LIB_ID(nick, fn))
        fp.SetReference(ref)
        fp.SetValue(comp.findtext("value"))
        sp = comp.find("sheetpath")
        fp.SetPath(pcbnew.KIID_PATH(sp.get("tstamps") + comp.findtext("tstamps")))
        fp.SetSheetname(sp.get("names"))
        fp.SetSheetfile(name + ".kicad_sch")
        fields = {f.get("name"): (f.text or "") for f in comp.iter("field")}
        for fname in ("Datasheet", "Description"):
            val = comp.findtext(fname.lower()) or fields.get(fname, "")
            fld = fp.GetField(fname) if hasattr(fp, "GetField") else None
            if fld is None:
                fld = fp.GetFieldByName(fname)
            if fld is not None:
                fld.SetText("" if val == "~" else val)
                fld.SetVisible(False)
        if comp.find("property[@name='exclude_from_bom']") is not None:
            fp.SetExcludedFromBOM(True)
        if ref not in cfg["place"]:
            sys.exit("no placement for %s" % ref)
        x, y, rot = cfg["place"][ref]
        fp.SetOrientationDegrees(rot)
        fp.SetPosition(VECTOR2I_MM(OX + x, OY + y))
        board.Add(fp)
        fps[ref] = fp
    extra = set(cfg["place"]) - set(fps)
    if extra:
        sys.exit("placement entries without a part: %s" % sorted(extra))
    for net in root.find("nets"):
        nname = net.get("name")
        if nname.startswith("unconnected-("):      # eeschema escapes "/" in pin names here
            nname = "unconnected-(" + nname[len("unconnected-("):].replace("/", "{slash}")
        ni = pcbnew.NETINFO_ITEM(board, nname)
        board.Add(ni)
        for node in net.findall("node"):
            fp = fps.get(node.get("ref"))
            if fp is None:
                continue
            pads = [pd for pd in fp.Pads() if pd.GetNumber() == node.get("pin")]
            if not pads:
                sys.exit("%s has no pad %s" % (node.get("ref"), node.get("pin")))
            for pd in pads:
                pd.SetNet(ni)

    def seg(x0, y0, x1, y1, layer=pcbnew.Edge_Cuts, w=0.1):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(VECTOR2I_MM(OX + x0, OY + y0))
        s.SetEnd(VECTOR2I_MM(OX + x1, OY + y1))
        s.SetLayer(layer)
        s.SetWidth(FromMM(w))
        board.Add(s)
    pts = cfg["outline"]
    for (a, b), (c, e) in zip(pts, pts[1:] + pts[:1]):
        seg(a, b, c, e)

    gnd = board.FindNet("GND")
    x0, y0, x1, y1 = cfg["pour_rect"]
    pour_layers = [pcbnew.B_Cu, pcbnew.F_Cu] + ([pcbnew.In1_Cu, pcbnew.In2_Cu] if nlayers >= 4 else [])
    for layer in pour_layers:
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(gnd)
        z.SetLocalClearance(FromMM(0.3))
        z.SetMinThickness(FromMM(0.25))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        o = z.Outline()
        o.NewOutline()
        for a, b in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
            o.Append(FromMM(OX + a), FromMM(OY + b))
        board.Add(z)
    for (a0, b0, a1, b1) in cfg.get("keepout_bands", []):
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
        for a, b in [(a0, b0), (a1, b0), (a1, b1), (a0, b1)]:
            o.Append(FromMM(OX + a), FromMM(OY + b))
        board.Add(ra)
    for (a0, b0, a1, b1) in cfg.get("silk_rects", []):     # e.g. outline of a plug-in module
        for (u0, v0, u1, v1) in ((a0, b0, a1, b0), (a1, b0, a1, b1), (a1, b1, a0, b1), (a0, b1, a0, b0)):
            seg(u0, v0, u1, v1, pcbnew.F_SilkS, 0.15)
    for s, x, y, size in cfg.get("silk", []):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(s)
        t.SetPosition(VECTOR2I_MM(OX + x, OY + y))
        t.SetLayer(pcbnew.F_SilkS)
        t.SetTextSize(VECTOR2I_MM(size, size))
        t.SetTextThickness(FromMM(max(0.12, size * 0.15)))
        board.Add(t)

    # courtyard / outline sanity
    def box(fp):
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        bb = cy.BBox() if not cy.IsEmpty() else fp.GetBoundingBox(False)
        return (pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY,
                pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY)
    boxes = {r: box(fp) for r, fp in fps.items()}
    problems = []
    refs = sorted(boxes)
    for i, a in enumerate(refs):
        for bref in refs[i + 1:]:
            A, B = boxes[a], boxes[bref]
            if A[0] < B[2] and B[0] < A[2] and A[1] < B[3] and B[1] < A[3]:
                problems.append("courtyard overlap %s / %s" % (a, bref))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    for r, (l, t, rr, b) in boxes.items():
        if r in cfg.get("overhang", ()):      # e.g. a right-angle connector body past the edge
            continue
        if l < min(xs) - 0.05 or t < min(ys) - 0.05 or rr > max(xs) + 0.05 or b > max(ys) + 0.05:
            problems.append("%s outside board bbox: %.1f,%.1f..%.1f,%.1f" % (r, l, t, rr, b))
    board.Save(pcb)

    # net classes + rules into the project file
    prj = json.load(open(pro)) if os.path.exists(pro) else {}
    base = {"clearance": 0.2, "via_diameter": 0.8, "via_drill": 0.4, "microvia_diameter": 0.3,
            "microvia_drill": 0.1, "diff_pair_width": 0.2, "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25,
            "wire_width": 6, "bus_width": 12, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)",
            "schematic_color": "rgba(0, 0, 0, 0.000)"}
    prj["net_settings"] = {
        "classes": [dict(base, name="Default", track_width=0.3, priority=2147483647),
                    dict(base, name="Power", track_width=1.0, clearance=0.25, via_diameter=1.0,
                         via_drill=0.5, priority=0)],
        "meta": {"version": 4}, "netclass_assignments": None,
        "netclass_patterns": [{"netclass": "Power", "pattern": pn} for pn in cfg.get("power_nets", [])]}
    rules = prj.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})
    rules["min_track_width"] = 0.15
    rules["min_copper_edge_clearance"] = 0.4
    prj.setdefault("meta", {"filename": name + ".kicad_pro", "version": 3})
    json.dump(prj, open(pro, "w", newline="\n"), indent=2)
    subprocess.run([CLI, "pcb", "drc", "--refill-zones", "--save-board", "-o",
                    os.path.join(tempfile.gettempdir(), name + "_drc.rpt"), pcb], check=True, capture_output=True)
    print("wrote %s: %d footprints" % (pcb, len(fps)))
    for pr in problems:
        print("WARN", pr)
    if report_boxes:
        for r in refs:
            print(r, ["%.1f" % v for v in boxes[r]])
    return boxes, problems
