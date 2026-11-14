#!/usr/bin/env python3
"""
Rev 2 SD daughter card: 100 x 160 mm Eurocard on the ECB bus, FreHD-compatible
hard-disk emulator on ports C0h-CFh, built around a Raspberry Pi Pico (RP2040).
See docs/rev2-architecture.md and firmware/sdcard/. Writes hardware/card-sd/.

Bus interface: U2 GAL decodes C0-CF and holds WAIT* until the Pico raises ACK.
Data: U1 74HCT245 (5 V) <-> XD <-> 2N7000 shifters <-> PD0-7 on Pico GP0-7.
Address A0-A3 and the strobes reach the Pico through CD74HC4050 buffers.
One-shot bootstrap: don't re-run after hand edits in KiCad.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kicadgen import Project, I, O, B, P, PO, PAS, NCT   # noqa: E402
import ecb   # noqa: E402
import parts   # noqa: E402

OUT = os.path.normpath(os.path.join(HERE, "..", "card-sd"))
LIB = "trs80_card_sd"
os.makedirs(OUT, exist_ok=True)
p = Project("trs80_card_sd", OUT, LIB, "ECB SD Card (Raspberry Pi Pico): FreHD-compatible hard disk on C0h-CFh",
            rev="2.0", date="2026-11-13", paper="A2",
            comments=("ECB Eurocard 100x160, DIN 41612 C96 male right-angle, RetroBrew ECB pinout",
                      "All through-hole. Pico socketed on 2x 1x20 headers; SD card on a breakout module"))

left, right = ecb.symbol_pins()
p.ic("ECB_C96", "J", "ECB bus connector, DIN 41612 type C 3x32 (rows a/b/c), RetroBrew ECB pinout",
     ecb.FP_MALE_RA, left, right, half_w=12.7)
parts.hct245(p)
parts.atf16v8(p)
parts.hc4050(p)

# Raspberry Pi Pico: custom symbol so the GND/AGND pins don't clash as power outputs in ERC
PICO_L = [("1", "GP0"), ("2", "GP1"), ("3", "GND"), ("4", "GP2"), ("5", "GP3"), ("6", "GP4"), ("7", "GP5"),
          ("8", "GND"), ("9", "GP6"), ("10", "GP7"), ("11", "GP8"), ("12", "GP9"), ("13", "GND"),
          ("14", "GP10"), ("15", "GP11"), ("16", "GP12"), ("17", "GP13"), ("18", "GND"), ("19", "GP14"),
          ("20", "GP15")]
PICO_R = [("40", "VBUS"), ("39", "VSYS"), ("38", "GND"), ("37", "3V3_EN"), ("36", "3V3"), ("35", "ADC_VREF"),
          ("34", "GP28"), ("33", "AGND"), ("32", "GP27"), ("31", "GP26"), ("30", "RUN"), ("29", "GP22"),
          ("28", "GND"), ("27", "GP21"), ("26", "GP20"), ("25", "GP19"), ("24", "GP18"), ("23", "GND"),
          ("22", "GP17"), ("21", "GP16")]


def ptype(name, num):
    if name == "3V3":
        return PO
    if name in ("GND", "AGND"):
        return P
    if name == "VSYS":
        return PAS          # fed through D1 from +5V
    return B if name.startswith("GP") else PAS


FP_PICO = "Module:RaspberryPi_Pico_Common_THT"
p.ic("RaspberryPi_Pico", "U", "Raspberry Pi Pico (RP2040) module, 2x 1x20 0.1in headers, 17.78 mm row spacing",
     FP_PICO, left=[(n, nm, ptype(nm, n)) for n, nm in PICO_L],
     right=[(n, nm, ptype(nm, n)) for n, nm in PICO_R], half_w=10.16,
     datasheet="https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf")

for lib, name in [("Device", "R"), ("Device", "C"), ("Device", "C_Polarized"), ("Device", "LED"),
                  ("Device", "D_Schottky"), ("Device", "R_Network08"), ("Device", "Crystal"),
                  ("Device", "Battery_Cell"), ("Transistor_FET", "2N7000"), ("Timer_RTC", "DS1307+"),
                  ("Connector_Generic", "Conn_01x02"), ("Connector_Generic", "Conn_01x04"),
                  ("Connector_Generic", "Conn_01x08")]:
    p.stock(lib, name)

FP_R = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal"
FP_C = "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm"
FP_CP = "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm"
FP_JP = "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"
FP_TO92 = "Package_TO_SOT_THT:TO-92_Inline_Wide"
FP_DO41 = "Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal"
FP_LED = "LED_THT:LED_D3.0mm"
FP_SIP9 = "Resistor_THT:R_Array_SIP9"

# ---------------------------------------------------------------- ECB connector
USED = {"+5V": "+5V", "GND": "GND", "WAIT*": "WAIT_N", "M1*": "M1_N", "IORQ*": "IORQ_N",
        "RD*": "RD_N", "WR*": "WR_N", "RESET*": "RESET_N",
        "BAI": "BA_LINK", "BAO": "BA_LINK", "IEI": "IE_LINK", "IEO": "IE_LINK"}
for k in range(8):
    USED["D%d" % k] = "D%d" % k
for k in range(8):
    USED["A%d" % k] = "A%d" % k
j1 = {pin: USED.get(name, "NC") for pin, name in ecb.ECB.items()}
p.text("ECB BUS  (DIN 41612 C96 male, right angle)", 25.4, 30.48, 2.5)
p.place("J1", LIB + ":ECB_C96", "ECB bus", ecb.FP_MALE_RA, 63.5, 127, j1,
        "ECB bus plug; rows a/b/c, RetroBrew ECB pinout")
p.text("Signals used: D0-D7, A0-A7, IORQ*, RD*, WR*, M1*, RESET*  (in)\n"
       "WAIT*  (open drain from the GAL; pull-up on the backplane)\n"
       "BAI->BAO and IEI->IEO are linked on the card (daisy chains pass through).", 25.4, 236.22)

# ---------------------------------------------------------------- decode + buffer
p.text("PORT DECODE  C0h-CFh  +  WAIT HANDSHAKE", 152.4, 30.48, 2.5)
p.place("U2", LIB + ":ATF16V8B", "ATF16V8B-15PU  ECB_SD_DECODE", "Package_DIP:DIP-20_W7.62mm_Socket",
        177.8, 76.2,
        {"1": "A7", "2": "A6", "3": "A5", "4": "A4", "5": "IORQ_N", "6": "RD_N", "7": "WR_N", "8": "M1_N",
         "9": "ACK", "11": "EN_N", "12": "WAIT_N", "13": "SELRD", "14": "SELWR", "15": "BUF_OE_N",
         "16": "NC", "17": "NC", "18": "NC", "19": "NC", "20": "+5V", "10": "GND"})
p.text("U2 (hardware/gal/ecb_sd_decode.pld):\n"
       "  SEL = A7..A4 = 1100 & IORQ* & M1* high & EN\n"
       "  SELRD / SELWR = SEL & RD* / WR*    BUF_OE_N = SEL & (RD*|WR*)\n"
       "  WAIT* pulled low (open-drain emulation) while SEL & !ACK\n"
       "ACK has a pull-up: with no Pico running the card never holds WAIT.",
       152.4, 101.6)
u1 = {"1": "RD_N", "19": "BUF_OE_N", "20": "+5V", "10": "GND"}
for i in range(8):
    u1[str(2 + i)] = "D%d" % i
    u1[str(18 - i)] = "XD%d" % i
p.place("U1", LIB + ":74HCT245", "74HCT245  BUS<->XD", "Package_DIP:DIP-20_W7.62mm", 177.8, 152.4, u1)
p.text("U1: A = ECB D0-D7, B = XD0-XD7 (5 V side of the shifters).\n"
       "RD* low = card drives the bus (IN), else bus -> card (OUT).", 152.4, 177.8)

p.text("5V -> 3.3V", 279.4, 30.48, 2.5)
p.place("U3", LIB + ":CD74HC4050", "CD74HC4050E", "Package_DIP:DIP-16_W7.62mm", 304.8, 66.04,
        {"3": "A0", "2": "PA0", "5": "A1", "4": "PA1", "7": "A2", "6": "PA2", "9": "A3", "10": "PA3",
         "11": "SELRD", "12": "SELRD_3V3", "14": "SELWR", "15": "SELWR_3V3",
         "1": "+3V3", "8": "GND", "13": "NC", "16": "NC"})
p.place("U4", LIB + ":CD74HC4050", "CD74HC4050E", "Package_DIP:DIP-16_W7.62mm", 304.8, 116.84,
        {"3": "RESET_N", "2": "RESET_3V3_N", "5": "GND", "4": "NC", "7": "GND", "6": "NC",
         "9": "GND", "10": "NC", "11": "GND", "12": "NC", "14": "GND", "15": "NC",
         "1": "+3V3", "8": "GND", "13": "NC", "16": "NC"})
p.text("U4: spare inputs grounded.", 279.4, 137.16)

# ---------------------------------------------------------------- shifters
p.text("DATA LEVEL SHIFT  (3.3V PD <-> 5V XD, bidirectional, 2N7000)", 25.4, 279.4, 2.5)
for i in range(8):
    p.place("Q%d" % (i + 1), "Transistor_FET:2N7000", "2N7000", FP_TO92, 50.8 + i * 33.02, 307.34,
            {"1": "PD%d" % i, "2": "+3V3", "3": "XD%d" % i})
p.place("RN1", "Device:R_Network08", "4.7k", FP_SIP9, 325.12, 307.34,
        {"1": "+3V3", **{str(2 + i): "PD%d" % i for i in range(8)}}, "PD pull-ups to 3.3V (bussed SIP-9)")
p.place("RN2", "Device:R_Network08", "4.7k", FP_SIP9, 383.54, 307.34,
        {"1": "+5V", **{str(2 + i): "XD%d" % i for i in range(8)}}, "XD pull-ups to 5V (bussed SIP-9)")

# ---------------------------------------------------------------- Pico
p.text("RASPBERRY PI PICO  (socketed)", 381, 30.48, 2.5)
pico = {"1": "PD0", "2": "PD1", "4": "PD2", "5": "PD3", "6": "PD4", "7": "PD5", "9": "PD6", "10": "PD7",
        "11": "PA0", "12": "PA1", "14": "PA2", "15": "PA3", "16": "SELRD_3V3", "17": "SELWR_3V3",
        "19": "ACK", "20": "RESET_3V3_N",
        "21": "SD_MISO", "22": "SD_CS", "24": "SD_SCK", "25": "SD_MOSI", "26": "SD_CD", "27": "LED_ACT",
        "29": "GP22", "31": "I2C_SDA", "32": "I2C_SCL", "34": "GP28",
        "39": "VSYS", "40": "NC", "37": "NC", "36": "+3V3", "35": "NC", "30": "NC",
        "3": "GND", "8": "GND", "13": "GND", "18": "GND", "23": "GND", "28": "GND", "38": "GND", "33": "GND"}
p.place("U5", LIB + ":RaspberryPi_Pico", "Raspberry Pi Pico", FP_PICO, 419.1, 88.9, pico)
p.place("D1", "Device:D_Schottky", "1N5819", FP_DO41, 393.7, 152.4, {"1": "VSYS", "2": "+5V"},
        "Pico VSYS from +5V; blocks back-feed when the Pico is on USB")
p.place("R6", "Device:R", "10k", FP_R, 444.5, 152.4, {"1": "+3V3", "2": "ACK"},
        "ACK pull-up: no WAIT when the Pico is absent or not yet running")
p.text("GP0-7 PD0-7 (data)   GP8-11 PA0-3 (A0-A3)   GP12 SELRD   GP13 SELWR\n"
       "GP14 ACK   GP15 RESET_N   GP16-19 SPI0 to SD (MISO, CS, SCK, MOSI)\n"
       "GP20 SD card detect   GP21 ACT LED   GP26/27 I2C1 to the DS1307\n"
       "GP22, GP28 spare (J3).  Pico 3V3 OUT powers the card's 3.3 V logic.",
       381, 167.64)

# ---------------------------------------------------------------- SD module, RTC, misc
p.text("SD CARD MODULE  (Adafruit MicroSD breakout+ #254 pin order)", 508, 30.48, 2.5)
p.place("J2", "Connector_Generic:Conn_01x08", "SD module",
        "Connector_PinSocket_2.54mm:PinSocket_1x08_P2.54mm_Vertical", 533.4, 63.5,
        {"1": "+5V", "2": "+3V3", "3": "GND", "4": "SD_SCK", "5": "SD_MISO", "6": "SD_MOSI",
         "7": "SD_CS", "8": "SD_CD"},
        "5V 3V GND CLK DO DI CS CD: plug an Adafruit #254 (or wire any SPI microSD module)")
p.place("R7", "Device:R", "10k", FP_R, 533.4, 99.06, {"1": "+3V3", "2": "SD_CD"}, "Card-detect pull-up")

p.text("REAL-TIME CLOCK  (FreHD GETTIME/SETTIME)", 508, 124.46, 2.5)
p.place("U6", "Timer_RTC:DS1307+", "DS1307", "Package_DIP:DIP-8_W7.62mm", 533.4, 157.48,
        {"1": "RTC_X1", "2": "RTC_X2", "3": "VBAT", "4": "GND", "5": "I2C_SDA", "6": "I2C_SCL", "7": "NC",
         "8": "+5V"})
p.place("Y1", "Device:Crystal", "32.768kHz", "Crystal:Crystal_C26-LF_D2.1mm_L6.5mm_Horizontal", 508, 157.48,
        {"1": "RTC_X1", "2": "RTC_X2"}, "12.5 pF watch crystal")
p.place("BT1", "Device:Battery_Cell", "CR2032", "Battery:BatteryHolder_Keystone_103_1x20mm", 568.96, 162.56,
        {"1": "VBAT", "2": "GND"}, "RTC backup cell")
p.place("R1", "Device:R", "4.7k", FP_R, 584.2, 139.7, {"1": "+3V3", "2": "I2C_SDA"})
p.place("R2", "Device:R", "4.7k", FP_R, 599.44, 139.7, {"1": "+3V3", "2": "I2C_SCL"})
p.text("I2C pulled up to 3.3 V: DS1307 inputs (VIH 2.2 V) accept it,\nand the Pico pins never see 5 V.",
       508, 187.96)

p.text("SPARE / CONFIG / LEDS", 508, 218.44, 2.5)
p.place("J3", "Connector_Generic:Conn_01x04", "SPARE", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
        533.4, 246.38, {"1": "+3V3", "2": "GP22", "3": "GP28", "4": "GND"}, "Spare Pico GPIO (3.3 V only)")
p.place("JP1", "Connector_Generic:Conn_01x02", "CARD EN", FP_JP, 571.5, 246.38,
        {"1": "EN_N", "2": "GND"}, "Fit to enable the card (ports C0h-CFh)")
p.place("R5", "Device:R", "10k", FP_R, 599.44, 246.38, {"1": "+5V", "2": "EN_N"})
p.place("D2", "Device:LED", "ACT (green)", FP_LED, 533.4, 276.86, {"1": "LED_K", "2": "LED_ACT"})
p.place("R3", "Device:R", "330", FP_R, 553.72, 276.86, {"1": "LED_K", "2": "GND"})
p.place("D3", "Device:LED", "PWR (red)", FP_LED, 579.12, 276.86, {"1": "GND", "2": "PWR_A"})
p.place("R4", "Device:R", "1k", FP_R, 599.44, 276.86, {"1": "+5V", "2": "PWR_A"})

# ---------------------------------------------------------------- power + decoupling
p.text("POWER  (+5V from the ECB bus)  /  DECOUPLING", 25.4, 355.6, 2.5)
p.power("+5V", 50.8, 370.84, flag=True)
p.power("GND", 63.5, 370.84, flag=True)
p.flag("VBAT", 76.2, 370.84)
for i, ic in enumerate(["U1", "U2", "U3", "U4", "U6"]):
    vcc = "+3V3" if ic in ("U3", "U4") else "+5V"
    p.place("C%d" % (i + 1), "Device:C", "100nF", FP_C, 50.8 + i * 20.32, 393.7, {"1": vcc, "2": "GND"},
            "Decoupling for " + ic)
p.place("C6", "Device:C_Polarized", "10uF 10V", FP_CP, 160.02, 393.7, {"1": "+5V", "2": "GND"})
p.place("C7", "Device:C_Polarized", "10uF 10V", FP_CP, 180.34, 393.7, {"1": "+3V3", "2": "GND"})

p.text("FreHD-COMPATIBLE REGISTER MAP (C0h-CFh), served by the Pico firmware:\n"
       "  C0 WP   C1 control   C2 DATA2   C3 SIZE2   C4 COMMAND2 (OUT) / ROM (IN)\n"
       "  C5 ERROR2 (IN) / ROM RAM byte (OUT)   C8 data   C9 error   CA seccnt   CB secnum\n"
       "  CC cyl lo   CD cyl hi   CE SDH   CF status (IN) / command (OUT)\n\n"
       "ALL PARTS THROUGH-HOLE. Socket U2 and the Pico.\n"
       "VERIFY before ordering: SD module pin order (J2); Keystone 103 holder footprint.",
       279.4, 355.6, 2.2)

n_sym, n_net = p.write()
print("wrote %s: %d symbols, %d labelled nets" % (OUT, n_sym, n_net))
