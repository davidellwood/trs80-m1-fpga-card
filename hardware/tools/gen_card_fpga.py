#!/usr/bin/env python3
"""
Rev 2 FPGA daughter card: 100 x 160 mm Eurocard on the ECB bus (DIN 41612 C96 male,
right angle), Sipeed Tang Nano 20K + IDT7132 dual-port RAM. Rev 0.1's circuit with
the Model I connectors replaced by ECB, decode GALs rewritten for MREQ*/IORQ*/RD*/WR*/M1*.
See docs/rev2-architecture.md. Writes hardware/card-fpga/.

One-shot bootstrap: don't re-run after hand edits in KiCad.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kicadgen import Project, parse, I, O, B, T, P, OC, NCT, PO, PAS   # noqa: E402
import ecb   # noqa: E402
import parts   # noqa: E402

OUT = os.path.normpath(os.path.join(HERE, "..", "card-fpga"))
LIB = "trs80_card_fpga"
os.makedirs(OUT, exist_ok=True)
p = Project("trs80_card_fpga", OUT, LIB, "ECB FPGA Card (Tang Nano 20K): sprite engine + Am9511 + 2K DPRAM",
            rev="2.0", date="2026-11-13", paper="A2",
            comments=("ECB Eurocard 100x160, DIN 41612 C96 male right-angle, RetroBrew ECB pinout",
                      "All through-hole. Tang Nano 20K socketed on 2x 1x20 headers"))

# ---------------------------------------------------------------- symbols
left, right = ecb.symbol_pins()
p.ic("ECB_C96", "J", "ECB bus connector, DIN 41612 type C 3x32 (rows a/b/c), RetroBrew ECB pinout",
     ecb.FP_MALE_RA, left, right, half_w=12.7)

p.ic("IDT7132", "U", "2K x 8 dual-port static RAM (master, with BUSY arbitration), 5V, DIP-48",
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
parts.hct245(p)
parts.atf22v10(p)
parts.atf16v8(p)
parts.hc4050(p)

# Sipeed Tang Nano 20K: two 1x20 headers. Symbol pin n = footprint pad n:
# pads 1-20 = left header, 21-40 = right header, both numbered from the USB-C end.
# Pin name = GW2AR-18 package pin (or the supply).
TANG_L = ["73", "74", "75", "85", "77", "15", "16", "27", "28", "25", "26", "29", "30", "31", "17", "20",
          "19", "18", "3V3", "GND"]
TANG_R = ["5V", "GND", "76", "80", "42", "41", "56", "54", "51", "48", "55", "49", "86", "79", "GND", "3V3",
          "72", "71", "53", "52"]
NOTE = {"75": "HSPI", "76": "HSPI", "85": "SD_D1", "80": "SD_D2", "15": "LED0", "16": "LED1", "17": "LED2",
        "18": "LED3", "19": "LED4", "20": "LED5", "51": "PA_EN", "79": "WS2812", "56": "I2S", "54": "I2S",
        "55": "I2S", "53": "DDC", "52": "DDC"}


def tpin(num, name, first_3v3):
    if name == "3V3":
        return (num, "3V3", PO if first_3v3 else PAS)
    if name == "GND":
        return (num, "GND", P)
    if name == "5V":
        return (num, "5V", PAS)
    return (num, "P" + name + ("/" + NOTE[name] if name in NOTE else ""), B)


tl = [tpin(str(i + 1), n, True) for i, n in enumerate(TANG_L)]
tr = [tpin(str(21 + i), n, False) for i, n in enumerate(TANG_R)]
FP_TANG = LIB + ":TangNano20K_2x20_W20.32mm"
p.ic("TangNano20K", "U", "Sipeed Tang Nano 20K FPGA module (GW2AR-18), 2x 1x20 0.1in headers, 0.8in row spacing",
     FP_TANG, left=tl, right=tr, half_w=12.7,
     datasheet="https://wiki.sipeed.com/hardware/en/tang/tang-nano-20k/nano-20k.html")


def tang_footprint():
    pads = []
    for i in range(40):
        x = 0.0 if i < 20 else 20.32
        y = (i % 20) * 2.54
        shape = "rect" if i == 0 else "oval"
        pads.append('(pad "%d" thru_hole %s (at %g %g) (size 1.7 1.7) (drill 1.0) (layers "*.Cu" "*.Mask") '
                    '(remove_unused_layers no))' % (i + 1, shape, x, y))
    x0, x1, y0, y1 = 10.16 - 11.275, 10.16 + 11.275, 24.13 - 27.02, 24.13 + 27.02
    txt = """(footprint "TangNano20K_2x20_W20.32mm" (version 20241229) (generator "kicadgen") (layer "F.Cu")
  (descr "Sipeed Tang Nano 20K module (22.55 x 54.04 mm) on two 1x20 female headers, rows 20.32 mm apart. Pads 1-20 left header, 21-40 right header, pad 1 and 21 at the USB-C end. VERIFY row spacing and orientation against a real module.")
  (tags "Tang Nano 20K GW2AR-18 FPGA module")
  (property "Reference" "REF**" (at 10.16 -5.5 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
  (property "Value" "TangNano20K" (at 10.16 53 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
  (fp_rect (start %g %g) (end %g %g) (stroke (width 0.12) (type solid)) (fill no) (layer "F.SilkS"))
  (fp_rect (start %g %g) (end %g %g) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))
  (fp_rect (start %g %g) (end %g %g) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))
  (fp_text user "USB-C" (at 10.16 -1.6 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
  (fp_line (start 8.16 -0.4) (end 12.16 -0.4) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))
  %s
)""" % (x0 - 0.12, y0 - 0.12, x1 + 0.12, y1 + 0.12, x0 - 0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5, x0, y0, x1, y1,
        "\n  ".join(pads))
    p.footprints["TangNano20K_2x20_W20.32mm"] = parse(txt)[0]


tang_footprint()

for lib, name in [("Device", "R"), ("Device", "C"), ("Device", "C_Polarized"), ("Device", "LED"),
                  ("Device", "D_Schottky"), ("Device", "R_Network08"), ("Transistor_FET", "2N7000"),
                  ("Connector_Generic", "Conn_01x02")]:
    p.stock(lib, name)

FP_R = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"
FP_C = "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"
FP_CP = "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm"
FP_JP = "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"
FP_TO92 = "Package_TO_SOT_THT:TO-92_Inline_Wide"
FP_DO41 = "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal"
FP_DO35 = "Diode_THT:D_DO-35_SOD27_P7.62mm_Horizontal"
FP_LED = "LED_THT:LED_D3.0mm"
FP_SIP9 = "Resistor_THT:R_Array_SIP9"

# ---------------------------------------------------------------- ECB connector
USED = {"+5V": "+5V", "GND": "GND", "WAIT*": "WAIT_N", "INT*": "INT_N", "M1*": "M1_N", "IORQ*": "IORQ_N",
        "MREQ*": "MREQ_N", "RD*": "RD_N", "WR*": "WR_N", "RESET*": "RESET_N",
        "BAI": "BA_LINK", "BAO": "BA_LINK", "IEI": "IE_LINK", "IEO": "IE_LINK"}
for k in range(8):
    USED["D%d" % k] = "D%d" % k
for k in range(16):
    USED["A%d" % k] = "A%d" % k
j1 = {pin: USED.get(name, "NC") for pin, name in ecb.ECB.items()}
p.text("ECB BUS  (DIN 41612 C96 male, right angle)", 25.4, 30.48, 2.5)
p.place("J1", LIB + ":ECB_C96", "ECB bus", ecb.FP_MALE_RA, 63.5, 127, j1,
        "ECB bus plug; rows a/b/c, RetroBrew ECB pinout")
p.text("Signals used: D0-D7, A0-A15, MREQ*, IORQ*, RD*, WR*, M1*, RESET*  (in)\n"
       "WAIT*, INT*  (open drain out; pull-ups on the backplane)\n"
       "BAI->BAO and IEI->IEO are linked on the card (daisy chains pass through).\n"
       "No CLK used: the card runs from the Tang Nano's own 27 MHz oscillator.", 25.4, 236.22)

# ---------------------------------------------------------------- decode
p.text("ADDRESS DECODE (5V, GALs)", 152.4, 30.48, 2.5)
p.place("U4", LIB + ":ATF22V10C", "ATF22V10C-15PU  ECB_MEM_DECODE", "Package_DIP:DIP-24_W7.62mm_Socket",
        177.8, 73.66,
        {"1": "A15", "2": "A14", "3": "A13", "4": "A12", "5": "A11", "6": "A10", "7": "A9", "8": "A8",
         "9": "A7", "10": "A6", "11": "A5", "13": "FULL_N", "14": "MREQ_N", "15": "RD_N", "16": "WR_N",
         "17": "NC", "18": "NC", "19": "NC", "20": "NC", "21": "NC", "22": "NC", "23": "DP_CE_N",
         "24": "+5V", "12": "GND"})
p.place("U5", LIB + ":ATF16V8B", "ATF16V8B-15PU  ECB_IO_DECODE", "Package_DIP:DIP-20_W7.62mm_Socket",
        177.8, 142.24,
        {"1": "A7", "2": "A6", "3": "A5", "4": "A4", "5": "A3", "6": "A2", "7": "IORQ_N", "8": "RD_N",
         "9": "WR_N", "11": "PORT_ALT_N", "12": "IORD", "13": "IOWR", "14": "M1_N", "15": "DP_CE_N",
         "16": "ACT_LED_N", "17": "NC", "18": "NC", "19": "NC", "20": "+5V", "10": "GND"})
p.text("U4 (hardware/gal/ecb_mem_decode.pld): DP_CE_N = MREQ* & (RD*|WR*) in 0x3000-0x37DF\n"
       "     (0x37FF with the FULL jumper).\n"
       "U5 (hardware/gal/ecb_io_decode.pld): IORD/IOWR = IORQ* & M1* high & RD*/WR*\n"
       "     on ports 0x50-0x53 (0x70-0x73 with PORT ALT).\n"
       "     A1:A0 go to the FPGA: 0 APU data, 1 APU cmd/status, 2 GFX data, 3 GFX cmd/status.",
        152.4, 165.1)

# ---------------------------------------------------------------- DPRAM + buffers
p.text("SHARED DUAL-PORT RAM", 279.4, 30.48, 2.5)
dp = {"6": "A0", "7": "A1", "8": "A2", "9": "A3", "10": "A4", "11": "A5", "12": "A6", "13": "A7",
      "14": "A8", "15": "A9", "4": "A10", "1": "DP_CE_N", "5": "RD_N", "2": "WR_N", "3": "BUSY_L_N",
      "42": "RA0", "41": "RA1", "40": "RA2", "39": "RA3", "38": "RA4", "37": "RA5", "36": "RA6",
      "35": "RA7", "34": "RA8", "33": "RA9", "44": "RA10",
      "47": "R_CE_N", "43": "GND", "46": "R_RW_N", "45": "BUSY_R_N", "48": "+5V", "24": "GND"}
for i in range(8):
    dp[str(16 + i)] = "LD%d" % i
    dp[str(25 + i)] = "XD%d" % i
p.place("U1", LIB + ":IDT7132", "IDT7132SA/LA (2Kx8 DPRAM)", "Package_DIP:DIP-48_W15.24mm_Socket",
        309.88, 93.98, dp)

p.text("BUS BUFFERS", 396.24, 30.48, 2.5)
u2 = {"1": "RD_N", "19": "DP_CE_N", "20": "+5V", "10": "GND"}
u3 = {"1": "RD_N", "19": "PORT_OE_N", "20": "+5V", "10": "GND"}
for i in range(8):
    u2[str(2 + i)] = "D%d" % i
    u2[str(18 - i)] = "LD%d" % i
    u3[str(2 + i)] = "D%d" % i
    u3[str(18 - i)] = "XD%d" % i
p.place("U2", LIB + ":74HCT245", "74HCT245  RAM<->BUS", "Package_DIP:DIP-20_W7.62mm", 419.1, 63.5, u2)
p.place("U3", LIB + ":74HCT245", "74HCT245  PORT<->BUS", "Package_DIP:DIP-20_W7.62mm", 419.1, 134.62, u3)
p.text("U2: Z80 memory cycles to the DPRAM (RD* low = read).\n"
       "U3: Z80 I/O cycles to the FPGA ports; ECB RD* sets the direction (IN = IORQ* + RD*).\n"
       "     The FPGA enables it via PORT_OE_N only after parking its own DPRAM access (shared XD bus).",
       396.24, 157.48)

# ---------------------------------------------------------------- 5V -> 3.3V
p.text("5V -> 3.3V", 505.46, 30.48, 2.5)
p.place("U6", LIB + ":CD74HC4050", "CD74HC4050E", "Package_DIP:DIP-16_W7.62mm", 528.32, 66.04,
        {"3": "RESET_N", "2": "RESET_3V3_N", "5": "A1", "4": "PA1_3V3",
         "7": "IORD", "6": "IORD_3V3", "9": "IOWR", "10": "IOWR_3V3",
         "11": "A0", "12": "PA0_3V3", "14": "BUSY_R_N", "15": "R_BUSY_3V3_N",
         "1": "+3V3", "8": "GND", "13": "NC", "16": "NC"})

# ---------------------------------------------------------------- FPGA
p.text("FPGA  (Sipeed Tang Nano 20K, socketed)", 607.06, 30.48, 2.5)
NETS = {"73": "RA0", "74": "RA1", "85": "RA2", "77": "RA3", "27": "RA4", "28": "RA5", "25": "RA6",
        "26": "RA7", "29": "RA8", "30": "RA9", "31": "RA10",
        "15": "R_CE_N", "16": "R_RW_N", "17": "PORT_OE_N", "20": "RESET_3V3_N", "19": "R_BUSY_3V3_N",
        "18": "IORD_3V3",
        "80": "FD0", "42": "FD1", "41": "FD2", "56": "FD3", "54": "FD4", "48": "FD5", "55": "FD6", "49": "FD7",
        "86": "WAIT_DRV", "72": "INT_DRV", "71": "IOWR_3V3", "53": "PA0_3V3", "52": "PA1_3V3",
        "75": "NC", "76": "NC", "51": "NC", "79": "NC",
        "3V3": "+3V3", "GND": "GND", "5V": "TANG_5V"}
tang = {}
for i, n in enumerate(TANG_L):
    tang[str(i + 1)] = NETS[n]
for i, n in enumerate(TANG_R):
    tang[str(21 + i)] = NETS[n]
p.place("U7", LIB + ":TangNano20K", "Tang Nano 20K", FP_TANG, 645.16, 93.98, tang)
p.text("All 20K header I/O is 3.3 V. 30 of the 34 header I/Os are used; none spare.\n"
       "Left free: P75/P76 (BL616 HSPI), P51 (audio amp enable: the FPGA drives it low),\n"
       "P79 (on-board WS2812: driven low).\n"
       "LED pins P15-P20 carry active-low outputs or push-pull inputs only, so the\n"
       "module LEDs show activity: LED0 DPRAM access, LED1 FPGA write, LED2 port cycle,\n"
       "LED3 lit except during IN, LED4 BUSY collision, LED5 reset.\n"
       "Leave the module's TF slot empty (P80/P85 are its D2/D1 lines).\n"
       "Module +3V3 output powers the card's 3.3 V logic (no second regulator).",
       607.06, 134.62)

# ---------------------------------------------------------------- level shifters
p.text("FPGA DATA BUS LEVEL SHIFT  (3.3V FD <-> 5V XD, bidirectional, 2N7000)", 25.4, 279.4, 2.5)
for i in range(8):
    p.place("Q%d" % (i + 1), "Transistor_FET:2N7000", "2N7000", FP_TO92, 50.8 + i * 33.02, 307.34,
            {"1": "FD%d" % i, "2": "+3V3", "3": "XD%d" % i})
p.place("RN1", "Device:R_Network08", "4.7k", FP_SIP9, 325.12, 307.34,
        {"1": "+3V3", **{str(2 + i): "FD%d" % i for i in range(8)}}, "FD pull-ups to 3.3V (bussed SIP-9)")
p.place("RN2", "Device:R_Network08", "4.7k", FP_SIP9, 383.54, 307.34,
        {"1": "+5V", **{str(2 + i): "XD%d" % i for i in range(8)}}, "XD pull-ups to 5V (bussed SIP-9)")

# ---------------------------------------------------------------- WAIT / INT
p.text("WAIT / INT  (open drain onto ECB)", 431.8, 279.4, 2.5)
p.place("Q9", "Transistor_FET:2N7000", "2N7000", FP_TO92, 444.5, 307.34,
        {"1": "GND", "2": "WAIT_DRV", "3": "WAIT_N"})
p.place("Q10", "Transistor_FET:2N7000", "2N7000", FP_TO92, 477.52, 307.34,
        {"1": "GND", "2": "INT_DRV", "3": "INT_Q"})
p.place("R1", "Device:R", "10k", FP_R, 505.46, 307.34, {"1": "WAIT_DRV", "2": "GND"})
p.place("R2", "Device:R", "10k", FP_R, 523.24, 307.34, {"1": "INT_DRV", "2": "GND"})
p.place("D3", "Device:D_Schottky", "BAT85", FP_DO35, 556.26, 307.34, {"1": "BUSY_L_N", "2": "WAIT_BSY"})
p.place("JP1", "Connector_Generic:Conn_01x02", "BUSY->WAIT", FP_JP, 599.44, 307.34,
        {"1": "WAIT_N", "2": "WAIT_BSY"}, "Fit to stretch Z80 cycles on DPRAM address collisions")
p.place("JP2", "Connector_Generic:Conn_01x02", "INT EN", FP_JP, 632.46, 307.34,
        {"1": "INT_N", "2": "INT_Q"}, "Fit to let the FPGA interrupt the Z80")
p.text("JP1: DPRAM left-port BUSY stretches the Z80 cycle (via D3) on same-address collisions.\n"
       "Q9: FPGA-driven WAIT (Am9511 PAUSE emulation). Gate pull-downs keep both off while the FPGA configures.",
       431.8, 327.66)

# ---------------------------------------------------------------- power
p.text("POWER  (+5V from the ECB bus)", 25.4, 355.6, 2.5)
p.place("D2", "Device:D_Schottky", "1N5819", FP_DO41, 50.8, 378.46, {"1": "TANG_5V", "2": "+5V"},
        "Feeds the Tang Nano 5V pin; blocks back-feed when the module is on USB")
p.power("+5V", 88.9, 370.84, flag=True)
p.power("GND", 106.68, 378.46, flag=True)
p.place("D4", "Device:LED", "ACT (green)", FP_LED, 132.08, 378.46, {"1": "ACT_LED_N", "2": "ACT_A"})
p.place("R10", "Device:R", "470", FP_R, 154.94, 378.46, {"1": "+5V", "2": "ACT_A"})
p.place("D5", "Device:LED", "PWR (red)", FP_LED, 177.8, 378.46, {"1": "GND", "2": "PWR_A"})
p.place("R11", "Device:R", "1k", FP_R, 200.66, 378.46, {"1": "+5V", "2": "PWR_A"})

p.text("PULL-UPS AND CONFIG JUMPERS", 254, 355.6, 2.5)
pulls = [("R3", "4.7k", "BUSY_L_N", "+5V"), ("R4", "4.7k", "BUSY_R_N", "+5V"),
         ("R5", "10k", "R_CE_N", "+3V3"), ("R6", "10k", "R_RW_N", "+3V3"),
         ("R7", "10k", "PORT_OE_N", "+3V3"), ("R8", "10k", "FULL_N", "+5V"),
         ("R9", "10k", "PORT_ALT_N", "+5V")]
for i, (r, v, a, b) in enumerate(pulls):
    p.place(r, "Device:R", v, FP_R, 266.7 + i * 25.4, 378.46, {"1": b, "2": a})
p.place("JP3", "Connector_Generic:Conn_01x02", "FULL 2K", FP_JP, 452.12, 378.46,
        {"1": "FULL_N", "2": "GND"}, "Fit ONLY when no Expansion Interface: window becomes 0x3000-0x37FF")
p.place("JP4", "Connector_Generic:Conn_01x02", "PORT ALT", FP_JP, 482.6, 378.46,
        {"1": "PORT_ALT_N", "2": "GND"}, "Fit to move the port block from 0x50-0x53 to 0x70-0x73")

p.text("DECOUPLING (one 100nF disc per IC, next to its VCC pin)", 25.4, 403.86, 2.5)
for i, ic in enumerate(["U1", "U2", "U3", "U4", "U5"]):
    p.place("C%d" % (i + 1), "Device:C", "100nF", FP_C, 50.8 + i * 20.32, 426.72, {"1": "+5V", "2": "GND"},
            "Decoupling for " + ic)
p.place("C6", "Device:C", "100nF", FP_C, 152.4, 426.72, {"1": "+3V3", "2": "GND"}, "Decoupling for U6")
p.place("C7", "Device:C_Polarized", "100uF 10V", FP_CP, 172.72, 426.72, {"1": "+5V", "2": "GND"})
p.place("C8", "Device:C_Polarized", "10uF 10V", FP_CP, 193.04, 426.72, {"1": "+3V3", "2": "GND"})

p.text("MEMORY MAP (Z80 side, IDT7132 left port)\n"
       "  0x3000-0x33FF  FRAME BUFFER  1024 bytes = 64x16, sprite engine output, LDIR to 0x3C00\n"
       "  0x3400-0x37DF  bulk data area (sprite shapes, tile maps, APU vectors)\n"
       "  0x37E0-0x37FF  Expansion Interface (not decoded unless FULL jumper)\n\n"
       "I/O MAP  (block 0x50-0x53, or 0x70-0x73 with PORT ALT)\n"
       "  0x50 Am9511 data   0x51 Am9511 cmd/status   0x52 sprite param/result   0x53 sprite cmd/status\n\n"
       "ALL PARTS THROUGH-HOLE. Socket U1, U4, U5 and the Tang Nano 20K.\n"
       "VERIFY before ordering: IDT7132 DIP-48 pinout; Tang Nano 20K row spacing (20.32 mm assumed)\n"
       "and header orientation (pads 1/21 at the USB-C end).",
       279.4, 355.6, 2.2)

n_sym, n_net = p.write()
print("wrote %s: %d symbols, %d labelled nets" % (OUT, n_sym, n_net))
