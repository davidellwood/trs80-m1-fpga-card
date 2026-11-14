#!/usr/bin/env python3
"""
Rev 2 banked-memory card: 512 KB SRAM paged into 8000h-FFFFh, software-compatible
with X-MEM/80 (lambdamikel/x-mem-80, Model I) - an independent circuit for the ECB
backplane, not a copy of that GPL design.

  X-MEM mode:    OUT 41h = 16K page at 8000h, OUT 42h = 16K page at C000h (32 pages)
  SuperMem mode: OUT 43h = 32K page at 8000h (16 pages), IN 43h reads it back
Page registers are cleared by RESET* (defined at power-up). While enabled the card
pulls ECB c10 (EXTMEM*) low so the backplane keeps the EI's own RAM off 8000h-FFFFh.
Writes hardware/card-xmem/. One-shot bootstrap: don't re-run after hand edits.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kicadgen import Project   # noqa: E402
import ecb   # noqa: E402
import parts   # noqa: E402

OUT = os.path.normpath(os.path.join(HERE, "..", "card-xmem"))
LIB = "trs80_card_xmem"
os.makedirs(OUT, exist_ok=True)
p = Project("trs80_card_xmem", OUT, LIB, "ECB Banked Memory Card: 512 KB, X-MEM/80 and SuperMem compatible",
            rev="2.0", date="2026-11-13", paper="A3",
            comments=("ECB Eurocard 100x160, DIN 41612 C96 male right-angle, RetroBrew ECB pinout",
                      "All through-hole. Ports 41h-43h; ECB c10 = EXTMEM* to the backplane"))

left, right = ecb.symbol_pins()
p.ic("ECB_C96", "J", "ECB bus connector, DIN 41612 type C 3x32 (rows a/b/c), RetroBrew ECB pinout",
     ecb.FP_MALE_RA, left, right, half_w=12.7)
for f in (parts.sram512k, parts.hct245, parts.hct244, parts.hct273, parts.hct157, parts.atf16v8):
    f(p)
for lib, name in [("Device", "R"), ("Device", "C"), ("Device", "C_Polarized"), ("Device", "LED"),
                  ("Connector_Generic", "Conn_01x02")]:
    p.stock(lib, name)

FP_R = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"
FP_C = "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"
FP_JP = "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"

# ---------------------------------------------------------------- ECB
USED = {"+5V": "+5V", "GND": "GND", "M1*": "M1_N", "IORQ*": "IORQ_N", "MREQ*": "MREQ_N", "RD*": "RD_N",
        "WR*": "WR_N", "RESET*": "RESET_N", "c10": "EXTMEM_N",
        "BAI": "BA_LINK", "BAO": "BA_LINK", "IEI": "IE_LINK", "IEO": "IE_LINK"}
for k in range(8):
    USED["D%d" % k] = "D%d" % k
for k in range(16):
    USED["A%d" % k] = "A%d" % k
p.text("ECB BUS", 25.4, 22.86, 2.5)
p.place("J1", LIB + ":ECB_C96", "ECB bus", ecb.FP_MALE_RA, 50.8, 106.68,
        {pin: USED.get(name, "NC") for pin, name in ecb.ECB.items()}, "ECB bus plug")
p.text("c10 = EXTMEM* (driven low while the card is enabled).\n"
       "BAI->BAO and IEI->IEO linked on the card.", 25.4, 200.66)

# ---------------------------------------------------------------- SRAM + data buffer
p.text("512 KB SRAM at 8000h-FFFFh", 127, 22.86, 2.5)
sram = {"12": "A0", "11": "A1", "10": "A2", "9": "A3", "8": "A4", "7": "A5", "6": "A6", "5": "A7",
        "27": "A8", "26": "A9", "23": "A10", "25": "A11", "4": "A12", "28": "A13",
        "3": "SA14", "31": "SA15", "2": "SA16", "30": "SA17", "1": "SA18",
        "22": "RAM_CE_N", "24": "RD_N", "29": "WR_N", "32": "+5V", "16": "GND"}
for i, pin in enumerate(["13", "14", "15", "17", "18", "19", "20", "21"]):
    sram[pin] = "MD%d" % i
p.place("U1", LIB + ":AS6C4008", "AS6C4008-55PCN", "Package_DIP:DIP-32_W15.24mm_Socket", 152.4, 66.04, sram)
u2 = {"1": "RD_N", "19": "BUF_OE_N", "20": "+5V", "10": "GND"}
for i in range(8):
    u2[str(2 + i)] = "D%d" % i
    u2[str(18 - i)] = "MD%d" % i
p.place("U2", LIB + ":74HCT245", "74HCT245  BUS<->RAM", "Package_DIP:DIP-20_W7.62mm", 223.52, 63.5, u2)
p.text("U2: A = ECB D0-D7, B = SRAM DQ0-7; RD* low = card drives the bus.", 127, 106.68)

# ---------------------------------------------------------------- decode
p.text("DECODE (GALs)", 127, 124.46, 2.5)
p.place("U3", LIB + ":ATF16V8B", "ATF16V8B-15PU  ECB_XMEM_IO", "Package_DIP:DIP-20_W7.62mm_Socket", 152.4, 152.4,
        {"1": "A7", "2": "A6", "3": "A5", "4": "A4", "5": "A3", "6": "A2", "7": "A1", "8": "A0", "9": "IORQ_N",
         "11": "WR_N", "13": "RD_N", "14": "M1_N", "12": "CLK_LO", "15": "CLK_HI", "16": "RB_OE_N",
         "17": "EN_N", "18": "NC", "19": "NC", "20": "+5V", "10": "GND"})
p.place("U4", LIB + ":ATF16V8B", "ATF16V8B-15PU  ECB_XMEM_MEM", "Package_DIP:DIP-20_W7.62mm_Socket", 223.52, 152.4,
        {"1": "A15", "2": "A14", "3": "MREQ_N", "4": "RD_N", "5": "WR_N", "6": "SM_N", "7": "EN_N", "8": "LO4",
         "9": "HI4", "11": "GND", "12": "EXTMEM_N", "13": "RAM_CE_N", "14": "BUF_OE_N", "15": "SA14",
         "16": "NC", "17": "NC", "18": "NC", "19": "NC", "20": "+5V", "10": "GND"})
p.text("U3 (hardware/gal/ecb_xmem_io.pld): OUT 41h -> LO, OUT 42h -> HI, OUT 43h -> both; IN 43h reads LO (only when enabled).\n"
       "U4 (hardware/gal/ecb_xmem_mem.pld): RAM_CE_N = MREQ* & A15 & (RD*|WR*) & EN;\n"
       "   SA14 = CPU A14 (SuperMem) or LO4/HI4 by A14 (X-MEM); EXTMEM_N low while enabled.",
       127, 175.26)

# ---------------------------------------------------------------- page registers
p.text("PAGE REGISTERS  (cleared by RESET*)", 254, 22.86, 2.5)
for ref, clk, pref, x in (("U5", "CLK_LO", "LO", 279.4), ("U6", "CLK_HI", "HI", 330.2)):
    reg = {"3": "D0", "4": "D1", "7": "D2", "8": "D3", "13": "D4", "14": "GND", "17": "GND", "18": "GND",
           "11": clk, "1": "RESET_N", "2": pref + "0", "5": pref + "1", "6": pref + "2", "9": pref + "3",
           "12": pref + "4", "15": "NC", "16": "NC", "19": "NC", "20": "+5V", "10": "GND"}
    p.place(ref, LIB + ":74HCT273", "74HCT273  %s PAGE" % pref, "Package_DIP:DIP-20_W7.62mm", x, 63.5, reg)
p.place("U7", LIB + ":74HCT157", "74HCT157", "Package_DIP:DIP-16_W7.62mm", 279.4, 127,
        {"1": "A14", "15": "GND", "2": "LO0", "3": "HI0", "4": "SA15", "5": "LO1", "6": "HI1", "7": "SA16",
         "11": "LO2", "10": "HI2", "9": "SA17", "14": "LO3", "13": "HI3", "12": "SA18", "16": "+5V", "8": "GND"})
p.text("U7: SRAM A15-A18 = LO Q0-3 (CPU A14 = 0, window 8000h) or HI Q0-3 (A14 = 1, window C000h).",
       254, 152.4)
p.place("U8", LIB + ":74HCT244", "74HCT244  READBACK", "Package_DIP:DIP-20_W7.62mm", 330.2, 127,
        {"2": "LO0", "4": "LO1", "6": "LO2", "8": "LO3", "11": "LO4", "13": "GND", "15": "GND", "17": "GND",
         "18": "D0", "16": "D1", "14": "D2", "12": "D3", "9": "D4", "7": "D5", "5": "D6", "3": "D7",
         "1": "RB_OE_N", "19": "RB_OE_N", "20": "+5V", "10": "GND"})

# ---------------------------------------------------------------- jumpers, power
p.text("JUMPERS / POWER / DECOUPLING", 25.4, 228.6, 2.5)
p.place("JP1", "Connector_Generic:Conn_01x02", "SUPERMEM", FP_JP, 38.1, 246.38, {"1": "SM_N", "2": "GND"},
        "Fit: SuperMem mode (32K pages, OUT 43h). Open: X-MEM mode (16K pages, OUT 41h/42h)")
p.place("R1", "Device:R", "10k", FP_R, 55.88, 246.38, {"1": "+5V", "2": "SM_N"})
p.place("JP2", "Connector_Generic:Conn_01x02", "ENABLE", FP_JP, 81.28, 246.38, {"1": "EN_N", "2": "GND"},
        "Fit to enable the card")
p.place("R2", "Device:R", "10k", FP_R, 99.06, 246.38, {"1": "+5V", "2": "EN_N"})
p.place("D1", "Device:LED", "PWR (red)", "LED_THT:LED_D3.0mm", 124.46, 246.38, {"1": "GND", "2": "LED_A"})
p.place("R3", "Device:R", "1k", FP_R, 142.24, 246.38, {"1": "+5V", "2": "LED_A"})
p.power("+5V", 165.1, 241.3, flag=True)
p.power("GND", 177.8, 246.38, flag=True)
for i, ic in enumerate(["U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8"]):
    p.place("C%d" % (i + 1), "Device:C", "100nF", FP_C, 38.1 + i * 17.78, 271.78, {"1": "+5V", "2": "GND"},
            "Decoupling for " + ic)
p.place("C9", "Device:C_Polarized", "10uF 10V", "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm", 185.42, 271.78,
        {"1": "+5V", "2": "GND"})
p.text("Software: run X-MEM/80's MEMRES/CMD, Hyperdrive, Sidekick, LeScript, MIDI/80 loaders as on the original.\n"
       "Set JP1 to match the software's mode. VERIFY the AS6C4008 DIP-32 pinout against the datasheet.",
       203.2, 241.3, 2.0)

n_sym, n_net = p.write()
print("wrote %s: %d symbols, %d labelled nets" % (OUT, n_sym, n_net))
