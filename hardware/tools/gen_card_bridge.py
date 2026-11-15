#!/usr/bin/env python3
"""
Bridge card (replaces the rev 2 backplane): a 100 x 160 mm Eurocard that plugs into a
standard ECB backplane (e.g. the RetroBrew ECB backplane) and connects it to the TRS-80
Model I expansion bus through a right-angle 40-pin header at the card's front edge
(ribbon cable with a card-edge socket at the Model I end). No Expansion Interface.

Same interfacing as the backplane: buffered A0-A15, unbuffered D0-D7, a GAL rebuilding
MREQ*/IORQ*/RD*/WR*/M1*/RESET*, WAIT*/INT* back to the Model I through a 74HC07, and
the CPU-card duties on ECB (pull-ups, chain starts, A20-A23 pull-downs).
Writes hardware/card-bridge/. One-shot bootstrap: don't re-run after hand edits.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kicadgen import Project, I, OC, P   # noqa: E402
import ecb   # noqa: E402
import parts   # noqa: E402

OUT = os.path.normpath(os.path.join(HERE, "..", "card-bridge"))
LIB = "trs80_card_bridge"
os.makedirs(OUT, exist_ok=True)
p = Project("trs80_card_bridge", OUT, LIB, "TRS-80 Model I -> ECB Bridge Card", rev="3.1", date="2026-11-15",
            paper="A2",
            comments=("Eurocard 100x160 for a standard ECB backplane; Model I bus on a right-angle 2x20 header",
                      "All through-hole. Buffered: LS244 strobe receivers, claimed HCT245 data buffer. No Expansion Interface"))

left, right = ecb.symbol_pins()
p.ic("ECB_C96", "J", "ECB bus connector, DIN 41612 type C 3x32 (rows a/b/c), RetroBrew ECB pinout",
     ecb.FP_MALE_RA, left, right, half_w=12.7)
parts.hct244(p)
parts.hct244(p, "74LS244", "Octal buffer/line driver, 3-state, LS-TTL with input hysteresis, DIP-20")
parts.hct245(p)
parts.atf16v8(p)
parts.atf22v10(p)
p.ic("74HC07", "U", "Hex buffer, open-drain outputs, CMOS inputs (VIL 1.35 V, no input current), DIP-14",
     "Package_DIP:DIP-14_W7.62mm",
     left=[("1", "1A", I), ("3", "2A", I), ("5", "3A", I), ("9", "4A", I), ("11", "5A", I), ("13", "6A", I),
           None, ("14", "VCC", P), ("7", "GND", P)],
     right=[("2", "1Y", OC), ("4", "2Y", OC), ("6", "3Y", OC), ("8", "4Y", OC), ("10", "5Y", OC),
            ("12", "6Y", OC)], half_w=7.62)
for lib, name in [("Device", "R"), ("Device", "C"), ("Device", "C_Polarized"), ("Device", "LED"),
                  ("Device", "R_Network10"), ("Device", "R_Network04"),
                  ("Connector_Generic", "Conn_02x20_Odd_Even"), ("Connector_Generic", "Conn_01x02")]:
    p.stock(lib, name)

FP_R = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"
FP_C = "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"

# ---------------------------------------------------------------- ECB plug
USED = {"+5V": "+5V", "GND": "GND", "MREQ*": "E_MREQ_N", "IORQ*": "E_IORQ_N", "RD*": "E_RD_N", "WR*": "E_WR_N",
        "M1*": "E_M1_N", "RESET*": "E_RESET_N", "WAIT*": "E_WAIT_N", "INT*": "E_INT_N", "NMI*": "E_NMI_N",
        "BUSRQ*": "E_BUSRQ_N", "HALT*": "E_HALT_N", "BUSAK*": "E_BUSAK_N", "RFSH*": "E_RFSH_N",
        "BAO": "E_BAO", "IEO": "E_IEO", "A20": "E_A20", "A21": "E_A21", "A22": "E_A22", "A23": "E_A23",
        "c10": "E_EXTMEM_N"}
for k in range(8):
    USED["D%d" % k] = "ED%d" % k             # ECB side of the U7 data buffer
for k in range(16):
    USED["A%d" % k] = "EA%d" % k
p.text("ECB BUS  (DIN 41612 C96 male, right angle) - plugs into a standard ECB backplane", 25.4, 22.86, 2.5)
p.place("J1", LIB + ":ECB_C96", "ECB bus", ecb.FP_MALE_RA, 50.8, 106.68,
        {pin: USED.get(name, "NC") for pin, name in ecb.ECB.items()}, "ECB bus plug")
p.text("This card acts as the ECB CPU card: it starts the BAO/IEO daisy chains (pulled high),\n"
       "pulls up WAIT*/INT*/NMI*/BUSRQ* and holds HALT*/BUSAK*/RFSH* inactive, A20-A23 low.\n"
       "c10 (EXTMEM*, used by the banked-memory card) is pulled up. BAI/IEI unused.\n"
       "D8-D15, IRQ0-7 and the other 16-bit/spare lines are left to the backplane.", 25.4, 200.66)

# ---------------------------------------------------------------- Model I header
EDGE = {1: "SYSRES_N", 2: "RAS_N", 3: "A10", 4: "CAS_N", 5: "A13", 6: "A12", 7: "GND", 8: "A15",
        9: "A14", 10: "A11", 11: "OUT_N", 12: "A8", 13: "INTAK_N", 14: "WR_N", 15: "MUX", 16: "RD_N",
        17: "D4", 18: "A9", 19: "D7", 20: "IN_N", 21: "D1", 22: "INT_N", 23: "D6", 24: "TEST_N",
        25: "D3", 26: "A0", 27: "D5", 28: "A1", 29: "D0", 30: "GND", 31: "D2", 32: "A4", 33: "A3",
        34: "WAIT_N", 35: "A7", 36: "A5", 37: "A6", 38: "GND", 39: "A2", 40: "EDGE_5V"}
edge = {str(k): ("NC" if v in ("RAS_N", "CAS_N", "MUX", "TEST_N") else v) for k, v in EDGE.items()}
p.text("TRS-80 MODEL I BUS  (right-angle 2x20 box header)", 254, 22.86, 2.5)
p.place("J2", "Connector_Generic:Conn_02x20_Odd_Even", "Model I bus", "Connector_IDC:IDC-Header_2x20_P2.54mm_Horizontal",
        279.4, 76.2, edge, "Ribbon to the Model I expansion edge (card-edge socket at that end), pin n = pin n")
p.text("Pin numbers follow the TRS-IO M1 convention (as the rev 0.1 card and the backplane).\n"
       "RAS*, CAS*, MUX and TEST* are not used. No Expansion Interface connection.", 254, 129.54)
p.place("JP1", "Connector_Generic:Conn_01x02", "EDGE 5V", "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
        279.4, 147.32, {"1": "EDGE_5V", "2": "+5V"}, "Leave open unless the Model I bus pin 40 supply is known good")

# ---------------------------------------------------------------- bridge logic
p.text("MODEL I -> ECB BRIDGE", 127, 22.86, 2.5)
u1 = {"1": "GND", "19": "GND", "20": "+5V", "10": "GND"}
u2 = dict(u1)
ins = ["2", "4", "6", "8", "11", "13", "15", "17"]
outs = ["18", "16", "14", "12", "9", "7", "5", "3"]
for k in range(8):
    u1[ins[k]], u1[outs[k]] = "A%d" % k, "EA%d" % k
    u2[ins[k]], u2[outs[k]] = "A%d" % (k + 8), "EA%d" % (k + 8)
p.place("U1", LIB + ":74HCT244", "74HCT244", "Package_DIP:DIP-20_W7.62mm", 152.4, 55.88, u1)
p.place("U2", LIB + ":74HCT244", "74HCT244", "Package_DIP:DIP-20_W7.62mm", 152.4, 106.68, u2)
p.place("U3", LIB + ":ATF16V8B", "ATF16V8B-15PU  ECB_BRIDGE_CARD", "Package_DIP:DIP-20_W7.62mm_Socket",
        152.4, 160.02,
        {"1": "MRD_B", "2": "MWR_B", "3": "IN_B", "4": "OUT_B", "5": "INTAK_B", "6": "SYSRES_N",
         "7": "NC", "8": "NC", "9": "NC", "11": "NC", "12": "E_MREQ_N", "13": "E_IORQ_N",
         "14": "E_RD_N", "15": "E_WR_N", "16": "E_M1_N", "17": "E_RESET_N", "18": "NC", "19": "NC",
         "20": "+5V", "10": "GND"})
p.text("U3 (hardware/gal/ecb_bridge_card.pld, rev 3.0):\n  MREQ* = RD* & WR*   IORQ* = IN* & OUT* & INTAK*\n"
       "  RD* = RD* & IN*   WR* = WR* & OUT*   M1* = INTAK*   RESET* = SYSRES*", 127, 180.34)
p.place("U4", LIB + ":74HC07", "74HC07", "Package_DIP:DIP-14_W7.62mm", 213.36, 55.88,
        {"1": "E_WAIT_N", "2": "WAIT_N", "3": "E_INT_N", "4": "INT_N", "5": "+5V", "6": "NC",
         "9": "+5V", "8": "NC", "11": "+5V", "10": "NC", "13": "+5V", "12": "NC", "14": "+5V", "7": "GND"},
        "Open-drain: ECB WAIT*/INT* (wired-OR from cards) onto the Model I bus")
p.place("R1", "Device:R", "4.7k", FP_R, 238.76, 50.8, {"1": "+5V", "2": "WAIT_N"},
        "Model I WAIT* pull-up; leave unfitted if the Model I runs with the ECB system off")
p.place("R2", "Device:R", "4.7k", FP_R, 238.76, 66.04, {"1": "+5V", "2": "INT_N"},
        "Model I INT* pull-up; leave unfitted if the Model I runs with the ECB system off")
p.place("RN1", "Device:R_Network10", "4.7k", "Resistor_THT:R_Array_SIP11", 213.36, 106.68,
        {"1": "+5V", "2": "E_WAIT_N", "3": "E_INT_N", "4": "E_NMI_N", "5": "E_BUSRQ_N", "6": "E_HALT_N",
         "7": "E_BUSAK_N", "8": "E_RFSH_N", "9": "E_BAO", "10": "E_IEO", "11": "E_EXTMEM_N"},
        "Pull-ups: open-drain ECB lines, CPU outputs the Model I can't supply, chain starts, EXTMEM*")
p.place("RN2", "Device:R_Network04", "10k", "Resistor_THT:R_Array_SIP5", 213.36, 144.78,
        {"1": "GND", "2": "E_A20", "3": "E_A21", "4": "E_A22", "5": "E_A23"}, "Pull-downs: A20-A23 read as 0")

# ---------------------------------------------------------------- cable buffering (rev 3.1)
p.text("CABLE BUFFERING  (for a longer Model I ribbon)", 330.2, 22.86, 2.5)
p.place("U5", LIB + ":74LS244", "74LS244  STROBE RX", "Package_DIP:DIP-20_W7.62mm", 355.6, 63.5,
        {"2": "RD_N", "18": "MRD_B", "4": "WR_N", "16": "MWR_B", "6": "IN_N", "14": "IN_B", "8": "OUT_N", "12": "OUT_B",
         "11": "INTAK_N", "9": "INTAK_B", "13": "+5V", "7": "NC", "15": "+5V", "5": "NC", "17": "+5V", "3": "NC",
         "1": "GND", "19": "GND", "20": "+5V", "10": "GND"},
        "LS-TTL inputs with hysteresis: clean strobe edges from a long cable; open inputs read high (inactive)")
p.place("R4", "Device:R", "10k", FP_R, 355.6, 101.6, {"1": "SYSRES_N", "2": "GND"},
        "Holds ECB RESET* asserted when no Model I is connected; the Model I's reset driver overrides it")
p.place("U6", LIB + ":ATF22V10C", "ATF22V10C-15PU  ECB_BRIDGE_CLAIM", "Package_DIP:DIP-24_W7.62mm_Socket",
        411.48, 68.58,
        {"1": "EA15", "2": "EA14", "3": "EA13", "4": "EA12", "5": "EA11", "6": "EA10", "7": "EA9", "8": "EA8",
         "9": "EA7", "10": "EA6", "11": "EA5", "13": "EA4", "14": "EA3", "15": "EA2", "16": "MRD_B", "17": "DIR",
         "18": "BUF_OE_N", "19": "IN_B", "20": "NC", "21": "NC", "22": "NC", "23": "NC", "24": "+5V", "12": "GND"})
u7 = {"1": "DIR", "19": "BUF_OE_N", "20": "+5V", "10": "GND"}
for i in range(8):
    u7[str(2 + i)] = "DS%d" % i
    u7[str(18 - i)] = "ED%d" % i
p.place("U7", LIB + ":74HCT245", "74HCT245  DATA BUFFER", "Package_DIP:DIP-20_W7.62mm", 467.36, 63.5, u7,
        "A = Model I cable (through 33R), B = ECB D0-D7")
for i in range(8):
    p.place("R%d" % (5 + i), "Device:R", "33", FP_R, 495.3 + (i % 4) * 15.24, 50.8 + (i // 4) * 20.32,
            {"1": "D%d" % i, "2": "DS%d" % i}, "Series damping on the cable data line")
p.text("U6 (hardware/gal/ecb_bridge_claim.pld): U7 turns toward the Model I (DIR low) only for reads an ECB card\n"
       "answers: memory 3000-37DF and 8000-FFFF, ports 40-43, 50-53, 70-73, C0-CF. Otherwise it passes Model I\n"
       "data to ECB, and it is disabled during reads nobody answers. Add new cards' read ranges to U6.",
       330.2, 127)
# ---------------------------------------------------------------- power, decoupling
p.text("POWER  (+5V from the ECB backplane)", 25.4, 233.68, 2.5)  # noqa
p.power("+5V", 50.8, 248.92, flag=True)
p.power("GND", 63.5, 256.54, flag=True)
p.place("D1", "Device:LED", "PWR (red)", "LED_THT:LED_D3.0mm", 88.9, 256.54, {"1": "GND", "2": "LED_A"})
p.place("R3", "Device:R", "1k", FP_R, 109.22, 256.54, {"1": "+5V", "2": "LED_A"})
p.place("C1", "Device:C_Polarized", "47uF 10V", "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm", 134.62, 256.54,
        {"1": "+5V", "2": "GND"})
for i, ic in enumerate(["U1", "U2", "U3", "U4", "U5", "U6", "U7"]):
    p.place("C%d" % (i + 2), "Device:C", "100nF", FP_C, 160.02 + i * 20.32, 256.54, {"1": "+5V", "2": "GND"},
            "Decoupling for " + ic)

n_sym, n_net = p.write()
print("wrote %s: %d symbols, %d labelled nets" % (OUT, n_sym, n_net))
