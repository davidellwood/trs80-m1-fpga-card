#!/usr/bin/env python3
"""
Bootstrap generator for the TRS-80 Model I FPGA card KiCad project.

Writes (into ../kicad):
  trs80_fpga_card.kicad_pro / .kicad_sch
  trs80_fpga_card.kicad_sym          project symbol library (custom ICs)
  trs80_fpga_card.pretty/            project footprints (card edge, Tang Nano 9K)
  sym-lib-table, fp-lib-table

This is a one-shot bootstrap: once the schematic has been edited by hand in
KiCad, do NOT re-run it (it overwrites the schematic). It is kept so the
original netlist intent is documented in one readable place.

Every pin of every part is listed explicitly below (pin number -> net name,
or 'NC'), and the script refuses to run if a pin is missing or unknown.
"""
import copy
import math
import os
import re
import sys
import uuid

KICAD_SHARE = r"C:\Program Files\KiCad\10.0\share\kicad"
HERE = os.path.dirname(os.path.abspath(__file__))
KDIR = os.path.normpath(os.path.join(HERE, "..", "kicad"))
PROJ = "trs80_fpga_card"
LIB = "trs80_fpga_card"
ROOT_UUID = "6d1f3c1e-5a0b-4c55-9d1e-7a8b0c0f9e01"

_uuid_ns = uuid.UUID("2f0b8a52-1c7e-4e6b-9f47-1b2b8c9d0e11")
_uuid_ctr = [0]


def uid():
    """Deterministic UUIDs so re-generation produces stable diffs."""
    _uuid_ctr[0] += 1
    return str(uuid.uuid5(_uuid_ns, str(_uuid_ctr[0])))


# --------------------------------------------------------------- s-expr -----
def parse(text):
    toks = re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()"]+', text)
    stack = [[]]
    for t in toks:
        if t == "(":
            stack.append([])
        elif t == ")":
            x = stack.pop()
            stack[-1].append(x)
        else:
            stack[-1].append(t)
    return stack[0]


def ser(x, ind=0):
    if not isinstance(x, list):
        return x
    out = "("
    first, nl = True, False
    for c in x:
        if isinstance(c, list):
            out += "\n" + "\t" * (ind + 1) + ser(c, ind + 1)
            nl = True
        else:
            if nl:
                out += "\n" + "\t" * (ind + 1) + c
            else:
                out += ("" if first else " ") + c
        first = False
    if nl:
        out += "\n" + "\t" * ind
    return out + ")"


def q(s):
    s = str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return '"' + s + '"'


def unq(t):
    if t.startswith('"'):
        return t[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return t


def f(v):
    v = round(float(v), 4)
    if v == 0:
        v = 0.0
    s = ("%.4f" % v).rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def child(node, head):
    for c in node:
        if isinstance(c, list) and c and c[0] == head:
            return c
    return None


def effects(size=1.27, justify=None):
    e = ["effects", ["font", ["size", f(size), f(size)]]]
    if justify:
        e.append(["justify"] + justify.split())
    return e


def prop(name, val, x, y, ang=0, hide=False, justify=None):
    p = ["property", q(name), q(val), ["at", f(x), f(y), f(ang)]]
    if hide:
        p.append(["hide", "yes"])
    p.append(effects(justify=justify))
    return p


# ------------------------------------------------------------- symbols ------
SYMS = {}  # lib_id -> dict(node, pins{num:(x,y,ang)}, props{name:(x,y,ang)})


def register(libid, node):
    pins, props = {}, {}
    for c in node:
        if isinstance(c, list) and c and c[0] == "property":
            at = child(c, "at")
            props[unq(c[1])] = (float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0)
    for sub in node:
        if not (isinstance(sub, list) and sub and sub[0] == "symbol"):
            continue
        m = re.match(r".*_(\d+)_(\d+)$", unq(sub[1]))
        if not m or int(m.group(1)) not in (0, 1) or int(m.group(2)) not in (0, 1):
            continue
        for p in sub:
            if isinstance(p, list) and p and p[0] == "pin":
                at = child(p, "at")
                num = unq(child(p, "number")[1])
                pins[num] = (float(at[1]), float(at[2]), int(float(at[3])))
    SYMS[libid] = dict(node=node, pins=pins, props=props)


def load_stock(lib, name):
    path = os.path.join(KICAD_SHARE, "symbols", lib + ".kicad_sym")
    tree = parse(open(path, encoding="utf-8").read())[0]
    for c in tree:
        if isinstance(c, list) and c[:2] == ["symbol", q(name)]:
            if child(c, "extends"):
                sys.exit("stock symbol %s:%s is derived; pick a base symbol" % (lib, name))
            node = copy.deepcopy(c)
            node[1] = q(lib + ":" + name)
            register(lib + ":" + name, node)
            return
    sys.exit("stock symbol %s:%s not found" % (lib, name))


CUSTOM_LIB_NODES = []


def make_ic(name, ref, desc, fp, left, right, half_w=10.16, datasheet=""):
    """Rectangular IC symbol. left/right: lists of (num, name, type) or None (gap)."""
    n = max(len(left), len(right))
    ytop = math.ceil((n - 1) / 2) * 2.54
    ybot = ytop - (n - 1) * 2.54
    pins = []
    seen = set()
    for side, lst in (("L", left), ("R", right)):
        for i, p in enumerate(lst):
            if p is None:
                continue
            num, pname, ptype = p
            if num in seen:
                sys.exit("duplicate pin %s in %s" % (num, name))
            seen.add(num)
            y = ytop - i * 2.54
            x = -(half_w + 2.54) if side == "L" else (half_w + 2.54)
            ang = 0 if side == "L" else 180
            pins.append(["pin", ptype, "line", ["at", f(x), f(y), str(ang)], ["length", "2.54"],
                         ["name", q(pname), effects()], ["number", q(num), effects()]])
    rect = ["rectangle", ["start", f(-half_w), f(ytop + 2.54)], ["end", f(half_w), f(ybot - 2.54)],
            ["stroke", ["width", "0.254"], ["type", "default"]], ["fill", ["type", "background"]]]
    node = ["symbol", q(name), ["pin_names", ["offset", "1.016"]], ["exclude_from_sim", "no"],
            ["in_bom", "yes"], ["on_board", "yes"],
            prop("Reference", ref, 0, ytop + 5.08),
            prop("Value", name, 0, ybot - 5.08),
            prop("Footprint", fp, 0, ybot - 7.62, hide=True),
            prop("Datasheet", datasheet, 0, 0, hide=True),
            prop("Description", desc, 0, 0, hide=True),
            ["symbol", q(name + "_0_1"), rect],
            ["symbol", q(name + "_1_1")] + pins,
            ["embedded_fonts", "no"]]
    CUSTOM_LIB_NODES.append(copy.deepcopy(node))
    emb = copy.deepcopy(node)
    emb[1] = q(LIB + ":" + name)
    register(LIB + ":" + name, emb)


I, O, B, T, P, OC, NCT, PO = ("input", "output", "bidirectional", "tri_state", "power_in",
                              "open_collector", "no_connect", "power_out")

# IDT7132 2Kx8 dual-port SRAM, 48-pin 600mil DIP.
# Pinout transcribed from the IDT7132/7142 datasheet (P48 package) -- VERIFY before PCB release.
make_ic("IDT7132", "U", "2K x 8 dual-port static RAM (master, with BUSY arbitration), 5V, DIP-48",
        "Package_DIP:DIP-48_W15.24mm_Socket",
        left=[("6", "A0L", I), ("7", "A1L", I), ("8", "A2L", I), ("9", "A3L", I), ("10", "A4L", I),
              ("11", "A5L", I), ("12", "A6L", I), ("13", "A7L", I), ("14", "A8L", I), ("15", "A9L", I),
              ("4", "A10L", I), None,
              ("16", "I/O0L", B), ("17", "I/O1L", B), ("18", "I/O2L", B), ("19", "I/O3L", B),
              ("20", "I/O4L", B), ("21", "I/O5L", B), ("22", "I/O6L", B), ("23", "I/O7L", B), None,
              ("1", "~{CE_L}", I), ("5", "~{OE_L}", I), ("2", "R/~{W_L}", I), ("3", "~{BUSY_L}", OC), None,
              ("48", "VCC", P), ("24", "GND", P)],
        right=[("42", "A0R", I), ("41", "A1R", I), ("40", "A2R", I), ("39", "A3R", I), ("38", "A4R", I),
               ("37", "A5R", I), ("36", "A6R", I), ("35", "A7R", I), ("34", "A8R", I), ("33", "A9R", I),
               ("44", "A10R", I), None,
               ("25", "I/O0R", B), ("26", "I/O1R", B), ("27", "I/O2R", B), ("28", "I/O3R", B),
               ("29", "I/O4R", B), ("30", "I/O5R", B), ("31", "I/O6R", B), ("32", "I/O7R", B), None,
               ("47", "~{CE_R}", I), ("43", "~{OE_R}", I), ("46", "R/~{W_R}", I), ("45", "~{BUSY_R}", OC)],
        half_w=12.7, datasheet="https://www.renesas.com/us/en/document/dst/7132-7142-data-sheet")

make_ic("74HCT245", "U", "Octal bus transceiver, TTL-level inputs, 3-state, DIP-20",
        "Package_DIP:DIP-20_W7.62mm",
        left=[("2", "A0", T), ("3", "A1", T), ("4", "A2", T), ("5", "A3", T), ("6", "A4", T),
              ("7", "A5", T), ("8", "A6", T), ("9", "A7", T), None,
              ("1", "A->B", I), ("19", "~{OE}", I), None,
              ("20", "VCC", P), ("10", "GND", P)],
        right=[("18", "B0", T), ("17", "B1", T), ("16", "B2", T), ("15", "B3", T), ("14", "B4", T),
               ("13", "B5", T), ("12", "B6", T), ("11", "B7", T)],
        half_w=7.62)

make_ic("ATF22V10C", "U", "Microchip ATF22V10C SPLD (GAL22V10 compatible), DIP-24 300mil",
        "Package_DIP:DIP-24_W7.62mm_Socket",
        left=[("1", "I0/CLK", I), ("2", "I1", I), ("3", "I2", I), ("4", "I3", I), ("5", "I4", I),
              ("6", "I5", I), ("7", "I6", I), ("8", "I7", I), ("9", "I8", I), ("10", "I9", I),
              ("11", "I10", I), ("13", "I11", I), None, ("24", "VCC", P), ("12", "GND", P)],
        right=[("14", "IO0", B), ("15", "IO1", B), ("16", "IO2", B), ("17", "IO3", B), ("18", "IO4", B),
               ("19", "IO5", B), ("20", "IO6", B), ("21", "IO7", B), ("22", "IO8", B), ("23", "IO9", B)],
        half_w=7.62)

make_ic("ATF16V8B", "U", "Microchip ATF16V8B SPLD (GAL16V8 compatible), DIP-20 300mil",
        "Package_DIP:DIP-20_W7.62mm_Socket",
        left=[("1", "I0/CLK", I), ("2", "I1", I), ("3", "I2", I), ("4", "I3", I), ("5", "I4", I),
              ("6", "I5", I), ("7", "I6", I), ("8", "I7", I), ("9", "I8", I), ("11", "I9/~{OE}", I), None,
              ("20", "VCC", P), ("10", "GND", P)],
        right=[("12", "IO0", B), ("13", "IO1", B), ("14", "IO2", B), ("15", "IO3", B), ("16", "IO4", B),
               ("17", "IO5", B), ("18", "IO6", B), ("19", "IO7", B)],
        half_w=7.62)

make_ic("CD74HC4050", "U", "Hex non-inverting buffer, inputs tolerate > VCC (5V->3.3V translator), DIP-16",
        "Package_DIP:DIP-16_W7.62mm",
        left=[("3", "A1", I), ("5", "A2", I), ("7", "A3", I), ("9", "A4", I), ("11", "A5", I),
              ("14", "A6", I), None, ("1", "VCC", P), ("8", "GND", P)],
        right=[("2", "Y1", O), ("4", "Y2", O), ("6", "Y3", O), ("10", "Y4", O), ("12", "Y5", O),
               ("15", "Y6", O), None, ("13", "NC", NCT), ("16", "NC", NCT)],
        half_w=7.62)

# Sipeed Tang Nano 9K header: symbol pin n == header position n (DIP-style numbering,
# as in the TRS-IO xray reference). Pin name = GW1NR-9 package pin.
_tang_left = ["P38", "P37", "P36", "P39", "P25", "P26", "P27", "P28", "P29", "P30", "P33", "P34",
              "P40", "P35", "P41", "P42", "P51", "P53", "P54", "P55", "P56", "P57", "P68", "P69"]
_tang_right_25_48 = ["3V3", "GND", "P32", "P31", "P49", "P48", "5V", "P70", "P71", "P72", "P73",
                     "P74", "P75", "P76", "P77", "P79", "P80", "P81", "P82", "P83", "P84", "P85",
                     "P86", "P63"]
_tl = [(str(i + 1), n, B) for i, n in enumerate(_tang_left)]
_tr = []
for i, n in enumerate(_tang_right_25_48):
    num = str(25 + i)
    t = PO if n == "3V3" else P if n == "GND" else "passive" if n == "5V" else B
    _tr.append((num, n + ("_1V8" if n in ("P79", "P80", "P81", "P82", "P83", "P84", "P85", "P86") else ""), t))
_tr.reverse()  # pin 48 at top, pin 25 at bottom (DIP view)
make_ic("TangNano9K", "U", "Sipeed Tang Nano 9K FPGA module (GW1NR-9), 2x24 0.1in headers, 0.9in row spacing",
        LIB + ":TangNano9K_DIP48_W22.86mm", left=_tl, right=_tr, half_w=10.16,
        datasheet="https://wiki.sipeed.com/hardware/en/tang/Tang-Nano-9K/Nano-9K.html")

for lib, name in [("Device", "R"), ("Device", "C"), ("Device", "C_Polarized"), ("Device", "LED"),
                  ("Device", "D_Schottky"), ("Device", "R_Network08"), ("Transistor_FET", "2N7000"),
                  ("Connector_Generic", "Conn_02x20_Odd_Even"), ("Connector_Generic", "Conn_02x08_Odd_Even"),
                  ("Connector_Generic", "Conn_01x02"), ("Connector", "Barrel_Jack"),
                  ("Mechanical", "MountingHole"), ("power", "+5V"), ("power", "+3V3"), ("power", "GND"),
                  ("power", "PWR_FLAG")]:
    load_stock(lib, name)

# ------------------------------------------------------------ placement -----
ITEMS = []
USED_LIBIDS = set()
LABEL_COUNT = {}


def label(net, x, y, ang):
    just = {0: "left bottom", 180: "right bottom", 90: "left bottom", 270: "right bottom"}[ang]
    ITEMS.append(["label", q(net), ["at", f(x), f(y), str(ang)], effects(justify=just), ["uuid", q(uid())]])
    LABEL_COUNT[net] = LABEL_COUNT.get(net, 0) + 1


def place(ref, libid, value, fp, X, Y, pins, desc=None):
    S = SYMS[libid]
    USED_LIBIDS.add(libid)
    missing = set(S["pins"]) - set(pins)
    extra = set(pins) - set(S["pins"])
    if missing or extra:
        sys.exit("%s: missing pins %s, unknown pins %s" % (ref, sorted(missing), sorted(extra)))
    in_bom = (child(S["node"], "in_bom") or ["in_bom", "yes"])[1]
    on_board = (child(S["node"], "on_board") or ["on_board", "yes"])[1]
    inst = ["symbol", ["lib_id", q(libid)], ["at", f(X), f(Y), "0"], ["unit", "1"],
            ["exclude_from_sim", "no"], ["in_bom", in_bom], ["on_board", on_board], ["dnp", "no"],
            ["uuid", q(uid())]]
    for pname, pv in (("Reference", ref), ("Value", value), ("Footprint", fp), ("Datasheet", ""),
                      ("Description", desc or "")):
        if pname == "Datasheet":
            pv = next((unq(c[2]) for c in S["node"]
                       if isinstance(c, list) and c[:2] == ["property", q("Datasheet")]), "")
        px, py, pa = S["props"].get(pname, (0, 0, 0))
        hide = pname in ("Footprint", "Datasheet", "Description") or ref.startswith("#")
        if libid.startswith("power:") and pname == "Value":
            hide = False
        inst.append(prop(pname, pv, X + px, Y - py, pa, hide=hide))
    for num in S["pins"]:
        inst.append(["pin", q(num), ["uuid", q(uid())]])
    inst.append(["instances", ["project", q(PROJ), ["path", q("/" + ROOT_UUID), ["reference", q(ref)],
                                                     ["unit", "1"]]]])
    ITEMS.append(inst)
    if libid.startswith("power:"):
        return  # power symbol / flag: its pin sits on (X, Y) itself
    for num, (px, py, pa) in S["pins"].items():
        net = pins[num]
        ax, ay = X + px, Y - py
        if net == "NC":
            ITEMS.append(["no_connect", ["at", f(ax), f(ay)], ["uuid", q(uid())]])
            continue
        dx, dy = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}[pa]
        ex, ey = ax + dx * 2.54, ay + dy * 2.54
        ITEMS.append(["wire", ["pts", ["xy", f(ax), f(ay)], ["xy", f(ex), f(ey)]],
                      ["stroke", ["width", "0"], ["type", "default"]], ["uuid", q(uid())]])
        if net in POWER_NETS:
            power(net, ex, ey)
        else:
            lang = {(-1, 0): 180, (1, 0): 0, (0, 1): 270, (0, -1): 90}[(dx, dy)]
            label(net, ex, ey, lang)


def text(s, x, y, size=1.8):
    ITEMS.append(["text", q(s), ["exclude_from_sim", "no"], ["at", f(x), f(y), "0"],
                  effects(size=size, justify="left top"), ["uuid", q(uid())]])


_pwr_n = [0]
_flg_n = [0]
POWER_NETS = ("+5V", "+3V3", "GND")


def power(net, x, y, flag=False):
    """Power symbol at (x, y); with flag=True also a PWR_FLAG on the same point."""
    _pwr_n[0] += 1
    place("#PWR%03d" % _pwr_n[0], "power:" + net, net, "", x, y, {"1": net})
    if flag:
        _flg_n[0] += 1
        place("#FLG%02d" % _flg_n[0], "power:PWR_FLAG", "PWR_FLAG", "", x, y, {"1": net})


# Footprint shorthands
FP_R = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"
FP_C = "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"
FP_CP = "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm"
FP_JP = "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"
FP_TO92 = "Package_TO_SOT_THT:TO-92_Inline_Wide"
FP_DO41 = "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal"
FP_DO35 = "Diode_THT:D_DO-35_SOD27_P7.62mm_Horizontal"
FP_LED = "LED_THT:LED_D3.0mm"
FP_SIP9 = "Resistor_THT:R_Array_SIP9"

# ---- TRS-80 Model I 40-pin expansion bus (pin numbering as TRS-IO M1) ----
EDGE = {1: "SYSRES_N", 2: "RAS_N", 3: "A10", 4: "CAS_N", 5: "A13", 6: "A12", 7: "GND", 8: "A15",
        9: "A14", 10: "A11", 11: "OUT_N", 12: "A8", 13: "INTACK_N", 14: "WR_N", 15: "MUX", 16: "RD_N",
        17: "D4", 18: "A9", 19: "D7", 20: "IN_N", 21: "D1", 22: "INT_N", 23: "D6", 24: "TEST_N",
        25: "D3", 26: "A0", 27: "D5", 28: "A1", 29: "D0", 30: "GND", 31: "D2", 32: "A4", 33: "A3",
        34: "WAIT_N", 35: "A7", 36: "A5", 37: "A6", 38: "GND", 39: "A2", 40: "EDGE_5V"}
edge_pins = {str(k): v for k, v in EDGE.items()}

text("TRS-80 MODEL I EXPANSION BUS", 25.4, 40.64, 2.5)
place("J1", "Connector_Generic:Conn_02x20_Odd_Even", "M1 bus (card edge)", LIB + ":TRS80_M1_Edge_40",
      50.8, 88.9, edge_pins, "Card-edge fingers: plug the Model I expansion ribbon socket here")
place("J2", "Connector_Generic:Conn_02x20_Odd_Even", "To Expansion Interface",
      "Connector_IDC:IDC-Header_2x20_P2.54mm_Vertical", 127, 88.9, edge_pins,
      "Pass-through to the Expansion Interface (IDC ribbon with card-edge socket)")
text("J1 and J2 are wired 1:1 (bus pass-through).\nPin numbers follow the TRS-IO M1 convention,\n"
     "NOT the printed Model I connector numbering.", 25.4, 124.46)

# ---- Address decode ----
text("ADDRESS DECODE (5V, GALs)", 190.5, 40.64, 2.5)
place("U4", LIB + ":ATF22V10C", "ATF22V10C-15PU  MEM_DECODE", "Package_DIP:DIP-24_W7.62mm_Socket",
      215.9, 83.82,
      {"1": "A15", "2": "A14", "3": "A13", "4": "A12", "5": "A11", "6": "A10", "7": "A9", "8": "A8",
       "9": "A7", "10": "A6", "11": "A5", "13": "A4", "14": "A3", "15": "A2", "16": "A1", "17": "A0",
       "18": "RD_N", "19": "WR_N", "20": "FULL_N", "21": "MEMQ", "22": "NC", "23": "DP_CE_N",
       "24": "+5V", "12": "GND"})
place("U5", LIB + ":ATF16V8B", "ATF16V8B-15PU  IO_DECODE", "Package_DIP:DIP-20_W7.62mm_Socket",
      215.9, 160.02,
      {"1": "A7", "2": "A6", "3": "A5", "4": "A4", "5": "A3", "6": "A2", "7": "A1", "8": "IN_N",
       "9": "OUT_N", "11": "PORT_ALT_N", "12": "IORD", "13": "IOWR", "14": "DP_CE_N", "15": "MEMQ",
       "16": "ACT_LED_N", "17": "NC", "18": "NC", "19": "NC", "20": "+5V", "10": "GND"})
text("U4: DP_CE_N low for RD/WR in 0x3000-0x37DF (0x37FF with FULL jumper).\n"
     "     Qualified by MEMQ (no I/O cycle). Pin 22 spare.\n"
     "U5: IORD / IOWR high for IN / OUT on ports 0x50-0x53 (0x70-0x73 with ALT jumper).\n"
     "     A1:A0 go to the FPGA: 0 APU data, 1 APU cmd/status, 2 GFX data, 3 GFX cmd/status.",
     190.5, 185.42)

# ---- Dual-port RAM and bus buffers ----
text("SHARED DUAL-PORT RAM", 304.8, 40.64, 2.5)
dp = {"6": "A0", "7": "A1", "8": "A2", "9": "A3", "10": "A4", "11": "A5", "12": "A6", "13": "A7",
      "14": "A8", "15": "A9", "4": "A10",
      "1": "DP_CE_N", "5": "RD_N", "2": "WR_N", "3": "BUSY_L_N",
      "42": "RA0", "41": "RA1", "40": "RA2", "39": "RA3", "38": "RA4", "37": "RA5", "36": "RA6",
      "35": "RA7", "34": "RA8", "33": "RA9", "44": "RA10",
      "47": "R_CE_N", "43": "GND", "46": "R_RW_N", "45": "BUSY_R_N", "48": "+5V", "24": "GND"}
for i in range(8):
    dp[str(16 + i)] = "LD%d" % i
    dp[str(25 + i)] = "XD%d" % i
place("U1", LIB + ":IDT7132", "IDT7132SA/LA (2Kx8 DPRAM)", "Package_DIP:DIP-48_W15.24mm_Socket",
      335.28, 104.14, dp)

text("BUS BUFFERS", 424.18, 40.64, 2.5)
u2 = {"1": "RD_N", "19": "DP_CE_N", "20": "+5V", "10": "GND"}
u3 = {"1": "IN_N", "19": "PORT_OE_N", "20": "+5V", "10": "GND"}
for i in range(8):
    u2[str(2 + i)] = "D%d" % i
    u2[str(18 - i)] = "LD%d" % i
    u3[str(2 + i)] = "D%d" % i
    u3[str(18 - i)] = "XD%d" % i
place("U2", LIB + ":74HCT245", "74HCT245  RAM<->BUS", "Package_DIP:DIP-20_W7.62mm", 444.5, 73.66, u2)
place("U3", LIB + ":74HCT245", "74HCT245  PORT<->BUS", "Package_DIP:DIP-20_W7.62mm", 444.5, 144.78, u3)
text("U2: Z80 memory cycles to the DPRAM (A->B = write, RD_N low = read).\n"
     "U3: Z80 I/O cycles to the FPGA ports (APU + sprite engine); FPGA enables it via PORT_OE_N\n"
     "     only after parking its own DPRAM access (shared XD bus).", 424.18, 167.64)

# ---- 5V -> 3.3V ----
text("5V -> 3.3V", 535.94, 40.64, 2.5)
place("U6", LIB + ":CD74HC4050", "CD74HC4050E", "Package_DIP:DIP-16_W7.62mm", 558.8, 76.2,
      {"3": "SYSRES_N", "2": "SYSRES_3V3_N", "5": "A1", "4": "PA1_3V3",
       "7": "IORD", "6": "IORD_3V3", "9": "IOWR", "10": "IOWR_3V3",
       "11": "A0", "12": "PA0_3V3", "14": "BUSY_R_N", "15": "R_BUSY_3V3_N",
       "1": "+3V3", "8": "GND", "13": "NC", "16": "NC"})

# ---- FPGA ----
text("FPGA  (Sipeed Tang Nano 9K, socketed)", 650.24, 40.64, 2.5)
tang = {"1": "NC", "2": "NC", "3": "NC", "4": "NC",  # P36-P39: on-board TF card slot
        "5": "RA0", "6": "RA1", "7": "RA2", "8": "RA3", "9": "RA4", "10": "RA5", "11": "RA6",
        "12": "RA7", "13": "RA8", "14": "RA9", "15": "RA10",
        "16": "FD0", "17": "FD1", "18": "FD2", "19": "FD3", "20": "FD4", "21": "FD5", "22": "FD6",
        "23": "GPIO_P68", "24": "GPIO_P69",
        "25": "+3V3", "26": "GND", "27": "FD7", "28": "R_BUSY_3V3_N", "29": "IORD_3V3",
        "30": "IOWR_3V3", "31": "TANG_5V", "32": "PORT_OE_N", "33": "R_CE_N", "34": "R_RW_N",
        "35": "GPIO_P73", "36": "WAIT_DRV", "37": "INT_DRV", "38": "PA0_3V3", "39": "PA1_3V3",
        "40": "GPIO_P79", "41": "GPIO_P80", "42": "GPIO_P81", "43": "GPIO_P82", "44": "GPIO_P83",
        "45": "GPIO_P84", "46": "GPIO_P85", "47": "GPIO_P86", "48": "SYSRES_3V3_N"}
place("U7", LIB + ":TangNano9K", "Tang Nano 9K", LIB + ":TangNano9K_DIP48_W22.86mm", 685.8, 99.06, tang)
text("Header pins 1-4 (P36-P39) are used by the module's own TF card slot.\n"
     "P79-P86 are the 1.8V bank: only to J4, never to 3.3V/5V logic.\n"
     "P70-P75 (PORT_OE_N, R_CE_N, R_RW_N, WAIT/INT_DRV): confirm 3.3V bank\n"
     "on the Sipeed schematic before assembly.\n"
     "Module +3V3 output powers the board's 3.3V logic (no second regulator).",
     650.24, 144.78)

# ---- Data level shifters ----
text("FPGA DATA BUS LEVEL SHIFT  (3.3V FD <-> 5V XD, bidirectional, 2N7000)", 25.4, 205.74, 2.5)
for i in range(8):
    place("Q%d" % (i + 1), "Transistor_FET:2N7000", "2N7000", FP_TO92, 50.8 + i * 33.02, 233.68,
          {"1": "FD%d" % i, "2": "+3V3", "3": "XD%d" % i})
place("RN1", "Device:R_Network08", "4.7k", FP_SIP9, 325.12, 233.68,
      {"1": "+3V3", **{str(2 + i): "FD%d" % i for i in range(8)}}, "FD pull-ups to 3.3V (bussed SIP-9)")
place("RN2", "Device:R_Network08", "4.7k", FP_SIP9, 383.54, 233.68,
      {"1": "+5V", **{str(2 + i): "XD%d" % i for i in range(8)}}, "XD pull-ups to 5V (bussed SIP-9)")

# ---- WAIT / INT ----
text("WAIT / INT  (open drain onto the M1 bus)", 431.8, 205.74, 2.5)
place("Q9", "Transistor_FET:2N7000", "2N7000", FP_TO92, 444.5, 233.68,
      {"1": "GND", "2": "WAIT_DRV", "3": "WAIT_N"})
place("Q10", "Transistor_FET:2N7000", "2N7000", FP_TO92, 477.52, 233.68,
      {"1": "GND", "2": "INT_DRV", "3": "INT_Q"})
place("R1", "Device:R", "10k", FP_R, 505.46, 233.68, {"1": "WAIT_DRV", "2": "GND"})
place("R2", "Device:R", "10k", FP_R, 523.24, 233.68, {"1": "INT_DRV", "2": "GND"})
place("D3", "Device:D_Schottky", "BAT85", FP_DO35, 556.26, 233.68, {"1": "BUSY_L_N", "2": "WAIT_BSY"})
place("JP1", "Connector_Generic:Conn_01x02", "BUSY->WAIT", FP_JP, 599.44, 233.68,
      {"1": "WAIT_N", "2": "WAIT_BSY"}, "Fit to stretch Z80 cycles on DPRAM address collisions")
place("JP2", "Connector_Generic:Conn_01x02", "INT EN", FP_JP, 632.46, 233.68,
      {"1": "INT_N", "2": "INT_Q"}, "Fit to let the FPGA interrupt the Z80")
text("JP1: DPRAM left-port BUSY stretches the Z80 cycle (via D3) on same-address collisions.\n"
     "Q9: FPGA-driven WAIT (Am9511 PAUSE emulation). Gate pull-downs keep both off while the FPGA configures.",
     431.8, 254)

# ---- Power ----
text("POWER", 25.4, 281.94, 2.5)
place("J3", "Connector:Barrel_Jack", "5V DC in", "Connector_BarrelJack:BarrelJack_Horizontal",
      50.8, 304.8, {"1": "VIN", "2": "GND"}, "5V regulated, centre positive, >=1A")
place("D1", "Device:D_Schottky", "1N5819", FP_DO41, 96.52, 304.8, {"1": "+5V", "2": "VIN"})
place("D2", "Device:D_Schottky", "1N5819", FP_DO41, 134.62, 304.8, {"1": "TANG_5V", "2": "+5V"},
      "Feeds the Tang Nano 5V pin; blocks back-feed when the module is on USB")
place("JP5", "Connector_Generic:Conn_01x02", "EDGE 5V", FP_JP, 175.26, 304.8,
      {"1": "EDGE_5V", "2": "+5V"}, "Leave open unless the bus pin 40 supply is known good")
power("+5V", 210.82, 297.18, flag=True)
power("GND", 236.22, 304.8, flag=True)
place("D4", "Device:LED", "ACT (green)", FP_LED, 299.72, 304.8, {"1": "ACT_LED_N", "2": "ACT_A"})
place("R10", "Device:R", "470", FP_R, 322.58, 304.8, {"1": "+5V", "2": "ACT_A"})
place("D5", "Device:LED", "PWR (red)", FP_LED, 345.44, 304.8, {"1": "GND", "2": "PWR_A"})
place("R11", "Device:R", "1k", FP_R, 368.3, 304.8, {"1": "+5V", "2": "PWR_A"})

text("PULL-UPS AND CONFIG JUMPERS", 25.4, 337.82, 2.5)
pulls = [("R3", "4.7k", "BUSY_L_N", "+5V"), ("R4", "4.7k", "BUSY_R_N", "+5V"),
         ("R5", "10k", "R_CE_N", "+3V3"), ("R6", "10k", "R_RW_N", "+3V3"),
         ("R7", "10k", "PORT_OE_N", "+3V3"), ("R8", "10k", "FULL_N", "+5V"),
         ("R9", "10k", "PORT_ALT_N", "+5V")]
for i, (r, v, a, b) in enumerate(pulls):
    place(r, "Device:R", v, FP_R, 50.8 + i * 25.4, 360.68, {"1": b, "2": a})
place("JP3", "Connector_Generic:Conn_01x02", "FULL 2K", FP_JP, 241.3, 360.68,
      {"1": "FULL_N", "2": "GND"}, "Fit ONLY when no Expansion Interface: window becomes 0x3000-0x37FF")
place("JP4", "Connector_Generic:Conn_01x02", "PORT ALT", FP_JP, 271.78, 360.68,
      {"1": "PORT_ALT_N", "2": "GND"}, "Fit to move the port block from 0x50-0x53 to 0x70-0x73")

text("DECOUPLING (one 100nF disc per IC, next to its VCC pin)", 25.4, 391.16, 2.5)
for i, ic in enumerate(["U1", "U2", "U3", "U4", "U5"]):
    place("C%d" % (i + 1), "Device:C", "100nF", FP_C, 50.8 + i * 20.32, 414.02, {"1": "+5V", "2": "GND"},
          "Decoupling for " + ic)
place("C6", "Device:C", "100nF", FP_C, 152.4, 414.02, {"1": "+3V3", "2": "GND"}, "Decoupling for U6")
place("C7", "Device:C_Polarized", "100uF 10V", FP_CP, 172.72, 414.02, {"1": "+5V", "2": "GND"})
place("C8", "Device:C_Polarized", "10uF 10V", FP_CP, 193.04, 414.02, {"1": "+3V3", "2": "GND"})

text("FPGA EXPANSION HEADER", 238.76, 391.16, 2.5)
place("J4", "Connector_Generic:Conn_02x08_Odd_Even", "FPGA spare I/O",
      "Connector_PinHeader_2.54mm:PinHeader_2x08_P2.54mm_Vertical", 266.7, 421.64,
      {"1": "+3V3", "2": "GND", "3": "GPIO_P68", "4": "GPIO_P69", "5": "GPIO_P73", "6": "GND",
       "7": "GPIO_P79", "8": "GPIO_P80", "9": "GPIO_P81", "10": "GPIO_P82", "11": "GPIO_P83",
       "12": "GPIO_P84", "13": "GPIO_P85", "14": "GPIO_P86", "15": "GND", "16": "GND"},
      "Pins 7-14 are 1.8V I/O")
for i in range(4):
    place("H%d" % (i + 1), "Mechanical:MountingHole", "MountingHole", "MountingHole:MountingHole_3.2mm_M3",
          340.36 + i * 15.24, 414.02, {})

text("MEMORY MAP (Z80 side, IDT7132 left port)\n"
     "  0x3000-0x33FF  FRAME BUFFER  1024 bytes = 64x16, sprite engine output, LDIR to 0x3C00\n"
     "  0x3400-0x37DF  bulk data area (sprite shapes, tile maps, APU vectors)\n"
     "  0x37E0-0x37FF  Expansion Interface (not decoded unless FULL jumper)\n\n"
     "I/O MAP  (block 0x50-0x53, or 0x70-0x73 with PORT ALT)\n"
     "  0x50  Am9511 data\n"
     "  0x51  Am9511 command (OUT) / status (IN)\n"
     "  0x52  sprite engine parameter (OUT) / result (IN)\n"
     "  0x53  sprite engine command (OUT) / status (IN)\n\n"
     "ALL PARTS THROUGH-HOLE. Socket U1, U4, U5 and the Tang Nano 9K.\n"
     "VERIFY: IDT7132 DIP-48 pinout against the datasheet before ordering PCBs.",
     444.5, 281.94, 2.2)

# ----------------------------------------------------------- write out ------
def check_footprints():
    bad = []
    for it in ITEMS:
        if it[0] != "symbol":
            continue
        for c in it:
            if isinstance(c, list) and c[:2] == ["property", q("Footprint")]:
                fp = unq(c[2])
                if not fp:
                    continue
                nick, name = fp.split(":")
                if nick == LIB:
                    continue
                p = os.path.join(KICAD_SHARE, "footprints", nick + ".pretty", name + ".kicad_mod")
                if not os.path.exists(p):
                    bad.append(fp)
    if bad:
        sys.exit("missing footprints: %s" % sorted(set(bad)))


def footprint_files():
    out = {}
    # Card edge: 20 fingers per side, 0.1in pitch. Even pins on F.Cu, odd pins on B.Cu
    # (same geometry/convention as TRS-IO M1 TRSEDGE).
    fp = ["footprint", q("TRS80_M1_Edge_40"), ["version", "20241229"], ["generator", q("pcbnew")],
          ["generator_version", q("9.0")], ["layer", q("F.Cu")],
          ["descr", q("TRS-80 Model I 40-pin expansion bus card edge, 2x20 fingers, 2.54mm pitch, "
                      "1.6mm board. Board edge at y=+3.81 (bottom of fingers); bevel + hard gold.")],
          ["tags", q("TRS-80 card edge")], ["attr", "exclude_from_pos_files"],
          ["property", q("Reference"), q("REF**"), ["at", "0", "-6.35", "0"], ["layer", q("F.SilkS")],
           ["effects", ["font", ["size", "1", "1"], ["thickness", "0.15"]]]],
          ["property", q("Value"), q("TRS80_M1_Edge_40"), ["at", "0", "-8.35", "0"], ["layer", q("F.Fab")],
           ["effects", ["font", ["size", "1", "1"], ["thickness", "0.15"]]]],
          ["fp_line", ["start", "-27.94", "3.81"], ["end", "27.94", "3.81"],
           ["stroke", ["width", "0.15"], ["type", "dash"]], ["layer", q("Dwgs.User")]],
          ["fp_text", "user", q("BOARD EDGE"), ["at", "0", "5.3", "0"], ["layer", q("Dwgs.User")],
           ["effects", ["font", ["size", "1", "1"], ["thickness", "0.15"]]]],
          ["fp_text", "user", q("2"), ["at", "24.13", "-5", "0"], ["layer", q("F.SilkS")],
           ["effects", ["font", ["size", "1", "1"], ["thickness", "0.15"]]]],
          ["fp_text", "user", q("40"), ["at", "-24.13", "-5", "0"], ["layer", q("F.SilkS")],
           ["effects", ["font", ["size", "1", "1"], ["thickness", "0.15"]]]],
          ["fp_rect", ["start", "-26.5", "-4.3"], ["end", "26.5", "3.81"],
           ["stroke", ["width", "0.05"], ["type", "solid"]], ["fill", "no"], ["layer", q("F.CrtYd")]]]
    for n in range(1, 41):
        k = (n - 1) // 2
        x = 24.13 - k * 2.54
        layers = [q("F.Cu"), q("F.Mask")] if n % 2 == 0 else [q("B.Cu"), q("B.Mask")]
        fp.append(["pad", q(str(n)), "connect", "rect", ["at", f(x), "0"], ["size", "1.778", "7.62"],
                   ["layers"] + layers])
    out["TRS80_M1_Edge_40.kicad_mod"] = fp

    # Tang Nano 9K: 2x24 at 2.54mm, rows 22.86mm apart (0.9in). Pin numbering as TRS-IO xray.
    fp = ["footprint", q("TangNano9K_DIP48_W22.86mm"), ["version", "20241229"], ["generator", q("pcbnew")],
          ["generator_version", q("9.0")], ["layer", q("F.Cu")],
          ["descr", q("Sipeed Tang Nano 9K on 2x 1x24 female headers, 0.9in row spacing")],
          ["tags", q("Tang Nano 9K FPGA module")], ["attr", "through_hole"],
          ["property", q("Reference"), q("REF**"), ["at", "0", "-14.2", "0"], ["layer", q("F.SilkS")],
           ["effects", ["font", ["size", "1", "1"], ["thickness", "0.15"]]]],
          ["property", q("Value"), q("TangNano9K"), ["at", "0", "0", "0"], ["layer", q("F.Fab")],
           ["effects", ["font", ["size", "1", "1"], ["thickness", "0.15"]]]],
          ["fp_rect", ["start", "-30.31", "-12.95"], ["end", "30.31", "12.95"],
           ["stroke", ["width", "0.12"], ["type", "solid"]], ["fill", "no"], ["layer", q("F.SilkS")]],
          ["fp_rect", ["start", "-30.56", "-13.2"], ["end", "30.56", "13.2"],
           ["stroke", ["width", "0.05"], ["type", "solid"]], ["fill", "no"], ["layer", q("F.CrtYd")]],
          ["fp_text", "user", q("1"), ["at", "-29.21", "9.2", "0"], ["layer", q("F.SilkS")],
           ["effects", ["font", ["size", "1", "1"], ["thickness", "0.15"]]]]]
    for n in range(1, 49):
        if n <= 24:
            x, y = -29.21 + (n - 1) * 2.54, 11.43
        else:
            x, y = 29.21 - (n - 25) * 2.54, -11.43
        shape = "rect" if n == 1 else "circle"
        fp.append(["pad", q(str(n)), "thru_hole", shape, ["at", f(x), f(y)], ["size", "1.7", "1.7"],
                   ["drill", "1"], ["layers", q("*.Cu"), q("*.Mask")]])
    out["TangNano9K_DIP48_W22.86mm.kicad_mod"] = fp
    return out


def main():
    check_footprints()
    for net, n in sorted(LABEL_COUNT.items()):
        if n < 2:
            sys.exit("net %s has only one connection" % net)
    os.makedirs(os.path.join(KDIR, LIB + ".pretty"), exist_ok=True)
    lib_symbols = ["lib_symbols"] + [SYMS[l]["node"] for l in sorted(USED_LIBIDS)]
    sch = ["kicad_sch", ["version", "20250610"], ["generator", q("eeschema")],
           ["generator_version", q("10.0")], ["uuid", q(ROOT_UUID)], ["paper", q("A1")],
           ["title_block", ["title", q("TRS-80 Model I FPGA Card")], ["date", q("2026-11-12")],
            ["rev", q("0.1")],
            ["comment", "1", q("Dual-port RAM shared memory + Am9511 APU emulation in a Tang Nano 9K")],
            ["comment", "2", q("All through-hole. Bus interface ideas from TRS-IO M1 v1.3-xray (A. Puder)")]],
           lib_symbols] + ITEMS + [["sheet_instances", ["path", q("/"), ["page", q("1")]]],
                                   ["embedded_fonts", "no"]]
    with open(os.path.join(KDIR, PROJ + ".kicad_sch"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(ser(sch) + "\n")
    lib = ["kicad_symbol_lib", ["version", "20251024"], ["generator", q("kicad_symbol_editor")],
           ["generator_version", q("10.0")]] + CUSTOM_LIB_NODES
    with open(os.path.join(KDIR, LIB + ".kicad_sym"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(ser(lib) + "\n")
    for name, node in footprint_files().items():
        with open(os.path.join(KDIR, LIB + ".pretty", name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(ser(node) + "\n")
    with open(os.path.join(KDIR, "sym-lib-table"), "w", newline="\n") as fh:
        fh.write('(sym_lib_table\n\t(version 7)\n\t(lib (name "%s") (type "KiCad") '
                 '(uri "${KIPRJMOD}/%s.kicad_sym") (options "") (descr "TRS-80 FPGA card parts"))\n)\n'
                 % (LIB, LIB))
    with open(os.path.join(KDIR, "fp-lib-table"), "w", newline="\n") as fh:
        fh.write('(fp_lib_table\n\t(version 7)\n\t(lib (name "%s") (type "KiCad") '
                 '(uri "${KIPRJMOD}/%s.pretty") (options "") (descr "TRS-80 FPGA card footprints"))\n)\n'
                 % (LIB, LIB))
    pro = os.path.join(KDIR, PROJ + ".kicad_pro")
    if not os.path.exists(pro):
        with open(pro, "w", newline="\n") as fh:
            fh.write('{\n  "meta": {\n    "filename": "%s.kicad_pro",\n    "version": 3\n  }\n}\n' % PROJ)
    print("wrote", KDIR, "-", sum(1 for i in ITEMS if i[0] == "symbol"), "symbols,",
          len(LABEL_COUNT), "nets")


if __name__ == "__main__":
    main()
