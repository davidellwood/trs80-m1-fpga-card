"""ECB bus pinout (DIN 41612 C96), from the RetroBrew ECB backplane (ecb_backplane-201506)."""
row_a = ["+5V", "D5", "D6", "D3", "D4", "A2", "A4", "A5", "A6", "WAIT*", "BUSRQ*", "BAI", "a13", "a14",
         "a15", "a16", "BAO", "A14", "a19", "M1*", "a21", "a22", "a23", "a24", "a25", "a26", "IORQ*",
         "RFSH*", "A13", "A9", "BUSAK*", "GND"]
row_b = ["+5V", "A20", "A21", "A22", "A23", "D8", "D9", "D10", "D11", "D12", "D13", "D14", "D15", "IRQ7",
         "IRQ6", "IRQ5", "IRQ4", "IRQ3", "IRQ2", "IRQ1", "IRQ0", "IOWR", "b23", "IORC", "MRDC", "b26",
         "MWRC", "DS0", "DS1", "OFF", "LOCK", "GND"]
row_c = ["+5V", "D0", "D7", "D2", "A0", "A3", "A1", "A8", "A7", "c10", "IEI", "c12", "c13", "D1", "c15",
         "IEO", "A11", "A10", "c19", "NMI*", "INT*", "WR*", "c23", "RD*", "HALT*", "c26", "A12", "A15",
         "c29", "MREQ*", "RESET*", "GND"]
ECB = {}
for _row, _names in (("a", row_a), ("b", row_b), ("c", row_c)):
    for _i, _n in enumerate(_names):
        ECB["%s%d" % (_row, _i + 1)] = _n

FP_FEMALE = "Connector_DIN:DIN41612_C_3x32_Female_Vertical_THT"
FP_MALE_RA = "Connector_DIN:DIN41612_C_3x32_Male_Horizontal_THT"


def pin_type(name):
    return "power_in" if name in ("+5V", "GND") else "passive"


def symbol_pins():
    """(left, right) pin lists for kicadgen.Project.ic: left a1-a32 + b1-b16, right b17-b32 + c1-c32."""
    t = lambda pin: (pin, ECB[pin], pin_type(ECB[pin]))
    left = [t("a%d" % i) for i in range(1, 33)] + [t("b%d" % i) for i in range(1, 17)]
    right = [t("b%d" % i) for i in range(17, 33)] + [t("c%d" % i) for i in range(1, 33)]
    return left, right


def pin_of(name):
    """ECB pin(s) carrying a signal name, e.g. pin_of('RD*') -> ['c24']."""
    return [p for p, n in ECB.items() if n == name]
