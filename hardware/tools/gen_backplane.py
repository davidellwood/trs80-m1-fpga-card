#!/usr/bin/env python3
"""
Rev 2 backplane: TRS-80 Model I bus -> 5-slot ECB bus (DIN 41612 C96).
Connector pinout follows the RetroBrew ECB backplane (ecb_backplane-201506).
See docs/rev2-architecture.md. Writes hardware/backplane/.

One-shot bootstrap like gen_schematic.py: don't re-run after hand edits.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kicadgen import Project, copy_footprint, I, O, B, T, P, OC, NCT, PAS   # noqa: E402

OUT = os.path.normpath(os.path.join(HERE, "..", "backplane"))
LIB = "trs80_backplane"
os.makedirs(OUT, exist_ok=True)
p = Project("trs80_backplane", OUT, LIB, "TRS-80 Model I ECB Backplane", rev="2.0",
            date="2026-11-13", paper="A1",
            comments=("Model I expansion bus -> 5 ECB slots (DIN 41612 C96), pinout per RetroBrew ECB backplane",
                      "All through-hole. Data bus unbuffered; GAL rebuilds MREQ/IORQ/RD/WR/M1"))

# ---------------------------------------------------------------- ECB pinout
from ecb import ECB, pin_type as ecb_pin_type   # noqa: E402

def ecb_net(name):
    """Bused ECB net for a signal name."""
    if name in ("+5V", "GND"):
        return name
    if name[0] == "D" and name[1:].isdigit() and int(name[1:]) < 8:
        return name                                  # unbuffered: same net as Model I D0-D7
    if name[0] == "A" and name[1:].isdigit() and int(name[1:]) < 16:
        return "E" + name                            # buffered address EA0-EA15
    if name.endswith("*"):
        return "E_" + name[:-1] + "_N"
    if name[0] in "abc" and name[1:].isdigit():
        return "EX_" + name                          # spare line, bused
    return "E_" + name


# 96-pin symbol: left a1-a32 + b1-b16, right b17-b32 + c1-c32
left = [("a%d" % i, ECB["a%d" % i], ecb_pin_type(ECB["a%d" % i])) for i in range(1, 33)] + \
       [("b%d" % i, ECB["b%d" % i], ecb_pin_type(ECB["b%d" % i])) for i in range(1, 17)]
right = [("b%d" % i, ECB["b%d" % i], ecb_pin_type(ECB["b%d" % i])) for i in range(17, 33)] + \
        [("c%d" % i, ECB["c%d" % i], ecb_pin_type(ECB["c%d" % i])) for i in range(1, 33)]
FP_ECB_F = "Connector_DIN:DIN41612_C_3x32_Female_Vertical_THT"
p.ic("ECB_C96", "J", "ECB bus connector, DIN 41612 type C 3x32 (rows a/b/c), RetroBrew ECB pinout",
     FP_ECB_F, left, right, half_w=12.7)

p.ic("74HCT244", "U", "Octal buffer/line driver, 3-state, TTL inputs, DIP-20", "Package_DIP:DIP-20_W7.62mm",
     left=[("2", "1A1", I), ("4", "1A2", I), ("6", "1A3", I), ("8", "1A4", I), ("11", "2A1", I),
           ("13", "2A2", I), ("15", "2A3", I), ("17", "2A4", I), None, ("1", "~{1OE}", I), ("19", "~{2OE}", I),
           None, ("20", "VCC", P), ("10", "GND", P)],
     right=[("18", "1Y1", T), ("16", "1Y2", T), ("14", "1Y3", T), ("12", "1Y4", T), ("9", "2Y1", T),
            ("7", "2Y2", T), ("5", "2Y3", T), ("3", "2Y4", T)], half_w=7.62)
p.ic("ATF16V8B", "U", "Microchip ATF16V8B SPLD (GAL16V8 compatible), DIP-20",
     "Package_DIP:DIP-20_W7.62mm_Socket",
     left=[("1", "I0/CLK", I), ("2", "I1", I), ("3", "I2", I), ("4", "I3", I), ("5", "I4", I),
           ("6", "I5", I), ("7", "I6", I), ("8", "I7", I), ("9", "I8", I), ("11", "I9/~{OE}", I), None,
           ("20", "VCC", P), ("10", "GND", P)],
     right=[("12", "IO0", B), ("13", "IO1", B), ("14", "IO2", B), ("15", "IO3", B), ("16", "IO4", B),
            ("17", "IO5", B), ("18", "IO6", B), ("19", "IO7", B)], half_w=7.62)
p.ic("74HC07", "U", "Hex buffer, open-drain outputs, CMOS inputs (VIL 1.35 V, no input current), DIP-14", "Package_DIP:DIP-14_W7.62mm",
     left=[("1", "1A", I), ("3", "2A", I), ("5", "3A", I), ("9", "4A", I), ("11", "5A", I), ("13", "6A", I),
           None, ("14", "VCC", P), ("7", "GND", P)],
     right=[("2", "1Y", OC), ("4", "2Y", OC), ("6", "3Y", OC), ("8", "4Y", OC), ("10", "5Y", OC),
            ("12", "6Y", OC)], half_w=7.62)

for lib, name in [("Device", "R"), ("Device", "C"), ("Device", "C_Polarized"), ("Device", "LED"),
                  ("Device", "Polyfuse"), ("Device", "R_Network08"), ("Device", "R_Network04"),
                  ("Connector_Generic", "Conn_02x20_Odd_Even"), ("Connector_Generic", "Conn_02x02_Odd_Even"),
                  ("Connector_Generic", "Conn_01x02"), ("Connector_Generic", "Conn_01x03"), ("Connector", "Barrel_Jack"),
                  ("Connector", "Screw_Terminal_01x02"), ("Mechanical", "MountingHole")]:
    p.stock(lib, name)

copy_footprint(os.path.join(HERE, "..", "kicad", "trs80_fpga_card.pretty", "TRS80_M1_Edge_40.kicad_mod"), p)

FP_R = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"
FP_C = "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"
FP_JP = "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"

# ---------------------------------------------------------------- Model I bus
EDGE = {1: "SYSRES_N", 2: "RAS_N", 3: "A10", 4: "CAS_N", 5: "A13", 6: "A12", 7: "GND", 8: "A15",
        9: "A14", 10: "A11", 11: "OUT_N", 12: "A8", 13: "INTAK_N", 14: "WR_N", 15: "MUX", 16: "RD_N",
        17: "D4", 18: "A9", 19: "D7", 20: "IN_N", 21: "D1", 22: "INT_N", 23: "D6", 24: "TEST_N",
        25: "D3", 26: "A0", 27: "D5", 28: "A1", 29: "D0", 30: "GND", 31: "D2", 32: "A4", 33: "A3",
        34: "WAIT_N", 35: "A7", 36: "A5", 37: "A6", 38: "GND", 39: "A2", 40: "EDGE_5V"}
edge = {str(k): v for k, v in EDGE.items()}
# J2 to the EI: same as J1 except memory RD*/WR*, which U3 withholds from the EI for 8000-FFFF
# while a banked-memory card (X-MEM) claims that range on ECB c10 (EXTMEM*)
edge_ei = dict(edge, **{"14": "EI_WR_N", "16": "EI_RD_N"})
p.text("TRS-80 MODEL I BUS", 25.4, 30.48, 2.5)
p.place("J1", "Connector_Generic:Conn_02x20_Odd_Even", "M1 bus (card edge)", LIB + ":TRS80_M1_Edge_40",
        50.8, 88.9, edge, "Card-edge fingers: plug the Model I expansion ribbon socket here")
p.place("J2", "Connector_Generic:Conn_02x20_Odd_Even", "To Expansion Interface",
        "Connector_IDC:IDC-Header_2x20_P2.54mm_Vertical", 127, 88.9, edge_ei)
p.text("J1/J2 wired 1:1 (bus pass-through to the Expansion Interface), except J2 pins 14/16:\n"
       "EI_WR*/EI_RD* via JP8/JP9: 1-2 direct, or 2-3 from U3, which cuts them off for 8000-FFFF\n"
       "while an X-MEM card holds ECB c10 (EXTMEM*) low.\n"
       "D0-D7 go straight to the ECB slots (unbuffered); each card buffers its own data.",
       25.4, 124.46)

# ---------------------------------------------------------------- bridge
p.text("MODEL I -> ECB BRIDGE", 190.5, 30.48, 2.5)
u1 = {"1": "GND", "19": "GND", "20": "+5V", "10": "GND"}
u2 = dict(u1)
ins = ["2", "4", "6", "8", "11", "13", "15", "17"]
outs = ["18", "16", "14", "12", "9", "7", "5", "3"]
for k in range(8):
    u1[ins[k]], u1[outs[k]] = "A%d" % k, "EA%d" % k
    u2[ins[k]], u2[outs[k]] = "A%d" % (k + 8), "EA%d" % (k + 8)
p.place("U1", LIB + ":74HCT244", "74HCT244", "Package_DIP:DIP-20_W7.62mm", 215.9, 63.5, u1)
p.place("U2", LIB + ":74HCT244", "74HCT244", "Package_DIP:DIP-20_W7.62mm", 215.9, 119.38, u2)
p.place("U3", LIB + ":ATF16V8B", "ATF16V8B-15PU  ECB_BRIDGE", "Package_DIP:DIP-20_W7.62mm_Socket",
        215.9, 177.8,
        {"1": "RD_N", "2": "WR_N", "3": "IN_N", "4": "OUT_N", "5": "INTAK_N", "6": "SYSRES_N",
         "7": "A15", "8": "EX_c10", "9": "NC", "11": "NC", "12": "E_MREQ_N", "13": "E_IORQ_N",
         "14": "E_RD_N", "15": "E_WR_N", "16": "E_M1_N", "17": "E_RESET_N", "18": "EI_RD_GAL", "19": "EI_WR_GAL",
         "20": "+5V", "10": "GND"})
p.text("U3 (hardware/gal/ecb_bridge.pld):\n  MREQ* = RD* & WR*      IORQ* = IN* & OUT* & INTAK*\n"
       "  RD* = RD* & IN*    WR* = WR* & OUT*    M1* = INTAK*    RESET* = SYSRES*\n"
       "  EI_RD* / EI_WR* = RD* / WR* except when A15 = 1 and EXTMEM* (ECB c10) is low\n"
       "(active-low AND = low when any input is low)", 190.5, 200.66)
p.place("JP8", "Connector_Generic:Conn_01x03", "EI RD SRC", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
        254, 203.2, {"1": "RD_N", "2": "EI_RD_N", "3": "EI_RD_GAL"},
        "EI RD*: 1-2 direct from the Model I, 2-3 via U3 (needed with the X-MEM card)")
p.place("JP9", "Connector_Generic:Conn_01x03", "EI WR SRC", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
        271.78, 203.2, {"1": "WR_N", "2": "EI_WR_N", "3": "EI_WR_GAL"},
        "EI WR*: 1-2 direct from the Model I, 2-3 via U3 (needed with the X-MEM card)")
p.place("R2", "Device:R", "4.7k", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal", 254, 177.8,
        {"1": "+5V", "2": "EX_c10"}, "Pull-up: ECB c10 = EXTMEM*, pulled low by a banked-memory card")
p.place("U4", LIB + ":74HC07", "74HC07", "Package_DIP:DIP-14_W7.62mm", 299.72, 63.5,
        {"1": "E_WAIT_N", "2": "WAIT_N", "3": "E_INT_N", "4": "INT_N", "5": "+5V", "6": "NC",
         "9": "+5V", "8": "NC", "11": "+5V", "10": "NC", "13": "+5V", "12": "NC", "14": "+5V", "7": "GND"},
        "Open-collector: ECB WAIT*/INT* (wired-OR from cards) onto the Model I bus")
p.place("R3", "Device:R", "4.7k", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal", 325.12, 50.8,
        {"1": "+5V", "2": "WAIT_N"}, "Model I WAIT* pull-up; leave unfitted if the Model I runs with the backplane off")
p.place("R4", "Device:R", "4.7k", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal", 340.36, 50.8,
        {"1": "+5V", "2": "INT_N"}, "Model I INT* pull-up; leave unfitted if the Model I runs with the backplane off")
p.place("RN1", "Device:R_Network08", "4.7k", "Resistor_THT:R_Array_SIP9", 287.02, 116.84,
        {"1": "+5V", "2": "E_WAIT_N", "3": "E_INT_N", "4": "E_NMI_N", "5": "E_BUSRQ_N", "6": "E_HALT_N",
         "7": "E_BUSAK_N", "8": "E_RFSH_N", "9": "IEI_TOP"},
        "Pull-ups: open-collector ECB lines, and CPU outputs the Model I cannot supply (held inactive)")
p.place("RN2", "Device:R_Network04", "10k", "Resistor_THT:R_Array_SIP5", 287.02, 152.4,
        {"1": "GND", "2": "E_A20", "3": "E_A21", "4": "E_A22", "5": "E_A23"},
        "Pull-downs: upper address lines A20-A23 read as 0")

# ---------------------------------------------------------------- ECB slots
p.text("ECB SLOTS (DIN 41612 C96 female, 20.32 mm pitch)", 345.44, 30.48, 2.5)
NS = 5
for s in range(1, NS + 1):
    pins = {}
    for pin, name in ECB.items():
        if name == "BAI":
            net = "E_BUSAK_N" if s == 1 else "BA_%d" % s
        elif name == "BAO":
            net = "BA_%d" % (s + 1)
        elif name == "IEI":
            net = "IEI_TOP" if s == 1 else "IE_%d" % s
        elif name == "IEO":
            net = "IE_%d" % (s + 1)
        else:
            net = ecb_net(name)
        pins[pin] = net
    p.place("J1%d" % s, LIB + ":ECB_C96", "ECB slot %d" % s, FP_ECB_F, 375.92 + (s - 1) * 71.12, 160.02, pins)
    # chain bridge for an empty slot: 1-2 BAI-BAO, 3-4 IEI-IEO
    p.place("JP%d" % s, "Connector_Generic:Conn_02x02_Odd_Even", "CHAIN %d" % s,
            "Connector_PinHeader_2.54mm:PinHeader_2x02_P2.54mm_Vertical", 375.92 + (s - 1) * 71.12, 254,
            {"1": "E_BUSAK_N" if s == 1 else "BA_%d" % s, "2": "BA_%d" % (s + 1),
             "3": "IEI_TOP" if s == 1 else "IE_%d" % s, "4": "IE_%d" % (s + 1)},
            "Fit both links when slot %d is empty (passes the BAI/BAO and IEI/IEO daisy chains)" % s)
p.text("Daisy chains run slot 1 -> 2 -> ... -> 5 (BAO->BAI on a17/a12, IEO->IEI on c16/c11).\n"
       "Fit the CHAIN links of any empty slot. Our cards just link IEI->IEO and BAI->BAO.",
       345.44, 266.7)

# ---------------------------------------------------------------- power
p.text("POWER  (5 V regulated, >= 2 A)", 25.4, 287.02, 2.5)
p.place("J3", "Connector:Barrel_Jack", "5V DC", "Connector_BarrelJack:BarrelJack_Horizontal", 50.8, 304.8,
        {"1": "VIN", "2": "GND"}, "5 V regulated, centre positive")
p.place("J4", "Connector:Screw_Terminal_01x02", "5V terminal",
        "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal", 50.8, 330.2,
        {"1": "VIN", "2": "GND"}, "Alternative 5 V input (do not use both)")
p.place("F1", "Device:Polyfuse", "MF-RHT300 (3A hold)", "Fuse:Fuse_Bourns_MF-RHT300", 88.9, 304.8,
        {"1": "VIN", "2": "VSW"})
p.place("JP6", "Connector_Generic:Conn_01x02", "POWER SW", FP_JP, 114.3, 304.8,
        {"1": "VSW", "2": "+5V"}, "Link for always-on, or wire a panel power switch here")
p.place("JP7", "Connector_Generic:Conn_01x02", "EDGE 5V", FP_JP, 139.7, 304.8,
        {"1": "EDGE_5V", "2": "+5V"}, "Leave open unless the Model I bus pin 40 supply is known good")
p.power("+5V", 165.1, 297.18, flag=True)
p.power("GND", 182.88, 304.8, flag=True)
p.place("D1", "Device:LED", "PWR", "LED_THT:LED_D5.0mm", 203.2, 304.8, {"1": "GND", "2": "LED_A"})
p.place("R1", "Device:R", "470", FP_R, 228.6, 304.8, {"1": "+5V", "2": "LED_A"})
p.place("C1", "Device:C_Polarized", "470uF 10V", "Capacitor_THT:CP_Radial_D10.0mm_P5.00mm", 254, 309.88,
        {"1": "+5V", "2": "GND"})

p.text("DECOUPLING: 100 nF per IC, 100 nF + 10 uF at each slot", 25.4, 350.52, 2.5)
caps = [("C2", "U1"), ("C3", "U2"), ("C4", "U3"), ("C5", "U4")] + [("C%d" % (6 + i), "J1%d" % (i + 1)) for i in range(NS)]
for i, (c, ic) in enumerate(caps):
    p.place(c, "Device:C", "100nF", FP_C, 50.8 + i * 20.32, 373.38, {"1": "+5V", "2": "GND"},
            "Decoupling for " + ic)
for i in range(NS):
    p.place("C%d" % (6 + NS + i), "Device:C_Polarized", "10uF 10V", "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm",
            50.8 + i * 20.32, 398.78, {"1": "+5V", "2": "GND"}, "Bulk at slot %d" % (i + 1))
for i in range(4):
    p.place("H%d" % (i + 1), "Mechanical:MountingHole", "MountingHole", "MountingHole:MountingHole_3.2mm_M3",
            279.4 + i * 15.24, 373.38, {})

n_sym, n_net = p.write()
print("wrote %s: %d symbols, %d labelled nets" % (OUT, n_sym, n_net))
