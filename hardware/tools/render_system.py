#!/usr/bin/env python3
"""
render_system.py - photo-realistic render of the assembled rev 2 system (KiCad's Python):
    & "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" render_system.py <scratch_dir> [out.jpg]

Works on scratch copies only (the project boards are never modified):
  1. Each daughter card is "dressed": ICs in their DIP sockets, the Pico on its pin sockets,
     pin-socket strips plus a stand-in module for the Tang Nano 20K, and a stand-in SD breakout.
  2. Each card is exported as a STEP model with its origin at ECB pin a1.
  3. The STEP models are attached, standing upright, to slots J11-J13 of a copy of the backplane.
  4. KiCad's raytracer renders that copy (floor, shadows, perspective) to JPEG.
"""
import glob
import os
import shutil
import subprocess
import sys

import pcbnew
from pcbnew import FromMM, VECTOR2I_MM

KICAD = r"C:\Program Files\KiCad\10.0"
CLI = os.path.join(KICAD, "bin", "kicad-cli.exe")
FPLIB = os.path.join(KICAD, "share", "kicad", "footprints")
M3D = "${KICAD10_3DMODEL_DIR}"
HW = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SCR = os.path.abspath(sys.argv[1])
OUT = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(HW, "rev2_system_render.jpg")
os.makedirs(SCR, exist_ok=True)

CARD_A1_HEIGHT = 15.0    # mm above the backplane: ECB pin a1 of a mated card
CARD_X_OFFSET = -4.6     # mm: card top surface relative to socket row a (components face slot+1)
CARD_ROT = (0.0, 90.0, 180.0)   # card (x, y, z) -> backplane (z, -y, x): upright, a1..a32 aligned


def model(path, off=(0, 0, 0), rot=(0, 0, 0)):
    m = pcbnew.FP_3DMODEL()
    m.m_Filename = path
    m.m_Offset = pcbnew.VECTOR3D(*off)
    m.m_Rotation = pcbnew.VECTOR3D(*rot)
    m.m_Scale = pcbnew.VECTOR3D(1, 1, 1)
    m.m_Show = True
    return m


def step_export(pcb, out, origin_mm, extra=()):
    args = [CLI, "pcb", "export", "step", "-f", "--subst-models", "--include-tracks", "--include-pads",
            "--include-silkscreen", "--include-soldermask", "--user-origin",
            "%.4fx%.4fmm" % origin_mm, "-o", out] + list(extra) + [pcb]
    subprocess.run(args, check=True, capture_output=True)


def outline(board, x0, y0, x1, y1):
    for a, b, c, d in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(VECTOR2I_MM(a, b))
        s.SetEnd(VECTOR2I_MM(c, d))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(FromMM(0.1))
        board.Add(s)


def add_fp(board, lib, name, x, y, rot=0):
    fp = pcbnew.FootprintLoad(os.path.join(FPLIB, lib + ".pretty"), name)
    fp.SetPosition(VECTOR2I_MM(x, y))
    fp.SetOrientationDegrees(rot)
    board.Add(fp)
    return fp


def silk(board, text, x, y, size=1.2, rot=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(VECTOR2I_MM(x, y))
    t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(VECTOR2I_MM(size, size))
    t.SetTextThickness(FromMM(size * 0.15))
    t.SetTextAngle(pcbnew.EDA_ANGLE(rot, pcbnew.DEGREES_T))
    board.Add(t)


def first(pattern):
    hits = sorted(glob.glob(os.path.join(FPLIB, pattern)))
    return (os.path.basename(os.path.dirname(hits[0]))[:-7], os.path.basename(hits[0])[:-10]) if hits else None


# ---------------------------------------------------------------- stand-in modules
def make_tang():
    """Tang Nano 20K stand-in: 22.55 x 54.04 board, QFN FPGA, USB-C at the pin-1 end. Origin = pad 1."""
    b = pcbnew.NewBoard(os.path.join(SCR, "tang.kicad_pcb"))
    X, Y = 100.0, 100.0                                   # pad 1 position
    outline(b, X - 1.115, Y - 2.89, X + 21.435, Y + 51.15)
    q = first("Package_DFN_QFN.pretty/QFN-88*") or first("Package_DFN_QFN.pretty/QFN-68-1EP_8x8*") or \
        first("Package_DFN_QFN.pretty/QFN-64-1EP_9x9*")
    if q:
        add_fp(b, q[0], q[1], X + 10.16, Y + 26.0, 45)
    add_fp(b, "Connector_USB", "USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal", X + 10.16, Y - 0.6, 180)
    sm = first("Package_SO.pretty/SOIC-8_3.9x4.9mm*")
    if sm:
        add_fp(b, sm[0], sm[1], X + 10.16, Y + 40.0, 0)
    silk(b, "Tang Nano 20K", X + 10.16, Y + 46.0, 1.4)
    p = os.path.join(SCR, "tang.kicad_pcb")
    b.Save(p)
    out = os.path.join(SCR, "tang.step")
    step_export(p, out, (X, Y))
    return out


def make_sd():
    """SD breakout stand-in (about 32 x 25 mm), header column at x=0 (pin 1 at origin), card socket far end."""
    b = pcbnew.NewBoard(os.path.join(SCR, "sdmod.kicad_pcb"))
    X, Y = 100.0, 100.0
    outline(b, X - 31.0, Y - 3.8, X + 1.9, Y + 21.6)
    ms = first("Connector_Card.pretty/microSD_HC_Molex_104031-0811*") or first("Connector_Card.pretty/microSD*")
    if ms:
        add_fp(b, ms[0], ms[1], X - 20.0, Y + 8.9, 90)
    sot = first("Package_TO_SOT_SMD.pretty/SOT-23-5*")
    if sot:
        add_fp(b, sot[0], sot[1], X - 6.0, Y + 3.0, 0)
    silk(b, "microSD", X - 6.0, Y + 16.0, 1.2)
    p = os.path.join(SCR, "sdmod.kicad_pcb")
    b.Save(p)
    out = os.path.join(SCR, "sdmod.step")
    step_export(p, out, (X, Y))
    return out


# ---------------------------------------------------------------- dress a card copy, export STEP
DIP_CHIP = {"DIP-20_W7.62mm_Socket": "DIP-20_W7.62mm", "DIP-24_W7.62mm_Socket": "DIP-24_W7.62mm",
            "DIP-32_W15.24mm_Socket": "DIP-32_W15.24mm", "DIP-48_W15.24mm_Socket": "DIP-48_W15.24mm"}


STACKUP = """
\t\t(stackup
\t\t\t(layer "F.SilkS" (type "Top Silk Screen") (color "White"))
\t\t\t(layer "F.Mask" (type "Top Solder Mask") (color "Green") (thickness 0.01))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 1" (type "core") (color "FR4 natural") (thickness 1.51) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (color "Green") (thickness 0.01))
\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))
\t\t\t(copper_finish "HAL lead-free")
\t\t\t(dielectric_constraints no)
\t\t)"""


def add_stackup_colours(pcb):
    """Give a 2-layer scratch board green solder mask and white silkscreen (used by the STEP export)."""
    text = open(pcb, encoding="utf-8").read()
    if "(stackup" not in text:
        i = text.index("(setup") + len("(setup")
        text = text[:i] + STACKUP + text[i:]
        open(pcb, "w", encoding="utf-8", newline="\n").write(text)


def card_step(folder, name, tang_step, sd_step):
    src = os.path.join(HW, folder)
    dst = os.path.join(SCR, folder)
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(src):
        if f.endswith((".kicad_pcb", ".kicad_pro")) or f in ("fp-lib-table", "sym-lib-table") or f.endswith(".pretty"):
            s, d = os.path.join(src, f), os.path.join(dst, f)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
    pcb = os.path.join(dst, name + ".kicad_pcb")
    b = pcbnew.LoadBoard(pcb)
    for fp in b.GetFootprints():
        fpname = fp.GetFPID().GetLibItemName().wx_str()
        if fpname in DIP_CHIP:                                   # the IC sitting in its socket
            fp.Models().push_back(model(M3D + "/Package_DIP.3dshapes/%s.step" % DIP_CHIP[fpname], (0, 0, 3.2)))
        if fpname.startswith("TangNano20K"):
            fp.Models().push_back(model(M3D + "/Connector_PinSocket_2.54mm.3dshapes/PinSocket_1x20_P2.54mm_Vertical.step"))
            fp.Models().push_back(model(M3D + "/Connector_PinSocket_2.54mm.3dshapes/PinSocket_1x20_P2.54mm_Vertical.step",
                                        (20.32, 0, 0)))
            fp.Models().push_back(model(tang_step, (0, 0, 11.0)))
        if fp.GetReference() == "J2" and folder == "card-sd":    # SD breakout lying flat over its keep-out
            fp.Models().push_back(model(sd_step, (0, 0, 11.0)))
    j1 = b.FindFootprintByReference("J1")
    a1 = next(p for p in j1.Pads() if p.GetNumber() == "a1").GetPosition()
    b.Save(pcb)
    add_stackup_colours(pcb)
    out = os.path.join(SCR, folder + ".step")
    step_export(pcb, out, (pcbnew.ToMM(a1.x), pcbnew.ToMM(a1.y)))
    return out


# ---------------------------------------------------------------- assemble and render
if __name__ == "__main__":
    tang = os.path.join(SCR, "tang.step") if os.environ.get("REUSE") == "1" else make_tang()
    sdm = os.path.join(SCR, "sdmod.step") if os.environ.get("REUSE") == "1" else make_sd()
    # every card works in any slot; spaced out here so each card's component side is visible
    cards = [("card-xmem", "trs80_card_xmem", "J11"), ("card-sd", "trs80_card_sd", "J13"),
             ("card-fpga", "trs80_card_fpga", "J15")]
    reuse = os.environ.get("REUSE") == "1"
    steps = {slot: (os.path.join(SCR, f + ".step") if reuse and os.path.exists(os.path.join(SCR, f + ".step"))
                    else card_step(f, n, tang, sdm)) for f, n, slot in cards}
    bdir = os.path.join(SCR, "backplane")
    shutil.copytree(os.path.join(HW, "backplane"), bdir, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("gerbers", "*.png", "*.svg", "*.jpg"))
    bp = os.path.join(bdir, "trs80_backplane.kicad_pcb")
    b = pcbnew.LoadBoard(bp)
    for slot, st in steps.items():
        b.FindFootprintByReference(slot).Models().push_back(
            model(st, (CARD_X_OFFSET, 0, CARD_A1_HEIGHT), CARD_ROT))
    b.Save(bp)
    view = os.environ.get("VIEW", "-64,0,-48")
    zoom = os.environ.get("ZOOM", "0.72")
    pivot = os.environ.get("PIVOT", "0,0,6")
    w, h = os.environ.get("SIZE", "2400x1500").split("x")
    subprocess.run([CLI, "pcb", "render", "-o", OUT, "-w", w, "-h", h, "--quality", "high", "--floor",
                    "--perspective", "--rotate", view, "--zoom", zoom, "--pivot", pivot, "--background", "opaque", bp],
                   check=True, capture_output=True)
    print("wrote", OUT)
