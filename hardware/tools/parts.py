"""Custom schematic symbols shared by the rev 2 generators (kicadgen.Project.ic definitions)."""
from kicadgen import I, O, B, T, P, OC, NCT


def hct245(p):
    p.ic("74HCT245", "U", "Octal bus transceiver, TTL-level inputs, 3-state, DIP-20", "Package_DIP:DIP-20_W7.62mm",
         left=[("2", "A0", T), ("3", "A1", T), ("4", "A2", T), ("5", "A3", T), ("6", "A4", T),
               ("7", "A5", T), ("8", "A6", T), ("9", "A7", T), None, ("1", "A->B", I), ("19", "~{OE}", I), None,
               ("20", "VCC", P), ("10", "GND", P)],
         right=[("18", "B0", T), ("17", "B1", T), ("16", "B2", T), ("15", "B3", T), ("14", "B4", T),
                ("13", "B5", T), ("12", "B6", T), ("11", "B7", T)], half_w=7.62)


def hct244(p, name="74HCT244", desc="Octal buffer/line driver, 3-state, TTL inputs, DIP-20"):
    p.ic(name, "U", desc, "Package_DIP:DIP-20_W7.62mm",
         left=[("2", "1A1", I), ("4", "1A2", I), ("6", "1A3", I), ("8", "1A4", I), ("11", "2A1", I),
               ("13", "2A2", I), ("15", "2A3", I), ("17", "2A4", I), None, ("1", "~{1OE}", I), ("19", "~{2OE}", I),
               None, ("20", "VCC", P), ("10", "GND", P)],
         right=[("18", "1Y1", T), ("16", "1Y2", T), ("14", "1Y3", T), ("12", "1Y4", T), ("9", "2Y1", T),
                ("7", "2Y2", T), ("5", "2Y3", T), ("3", "2Y4", T)], half_w=7.62)


def hct273(p):
    p.ic("74HCT273", "U", "Octal D flip-flop with master reset, TTL inputs, DIP-20", "Package_DIP:DIP-20_W7.62mm",
         left=[("3", "D0", I), ("4", "D1", I), ("7", "D2", I), ("8", "D3", I), ("13", "D4", I), ("14", "D5", I),
               ("17", "D6", I), ("18", "D7", I), None, ("11", "CP", I), ("1", "~{MR}", I), None,
               ("20", "VCC", P), ("10", "GND", P)],
         right=[("2", "Q0", O), ("5", "Q1", O), ("6", "Q2", O), ("9", "Q3", O), ("12", "Q4", O), ("15", "Q5", O),
                ("16", "Q6", O), ("19", "Q7", O)], half_w=7.62)


def hct157(p):
    p.ic("74HCT157", "U", "Quad 2-input multiplexer, TTL inputs, DIP-16", "Package_DIP:DIP-16_W7.62mm",
         left=[("2", "1I0", I), ("3", "1I1", I), ("5", "2I0", I), ("6", "2I1", I), ("11", "3I0", I),
               ("10", "3I1", I), ("14", "4I0", I), ("13", "4I1", I), None, ("1", "S", I), ("15", "~{E}", I), None,
               ("16", "VCC", P), ("8", "GND", P)],
         right=[("4", "1Y", O), ("7", "2Y", O), ("9", "3Y", O), ("12", "4Y", O)], half_w=7.62)


def sram512k(p):
    p.ic("AS6C4008", "U", "512K x 8 static RAM, 55 ns, 5V, DIP-32 600mil (JEDEC 628512 pinout)",
         "Package_DIP:DIP-32_W15.24mm_Socket",
         left=[("12", "A0", I), ("11", "A1", I), ("10", "A2", I), ("9", "A3", I), ("8", "A4", I), ("7", "A5", I),
               ("6", "A6", I), ("5", "A7", I), ("27", "A8", I), ("26", "A9", I), ("23", "A10", I), ("25", "A11", I),
               ("4", "A12", I), ("28", "A13", I), ("3", "A14", I), ("31", "A15", I), ("2", "A16", I),
               ("30", "A17", I), ("1", "A18", I)],
         right=[("13", "DQ0", B), ("14", "DQ1", B), ("15", "DQ2", B), ("17", "DQ3", B), ("18", "DQ4", B),
                ("19", "DQ5", B), ("20", "DQ6", B), ("21", "DQ7", B), None, ("22", "~{CE}", I), ("24", "~{OE}", I),
                ("29", "~{WE}", I), None, ("32", "VCC", P), ("16", "GND", P)], half_w=10.16,
         datasheet="https://www.alliancememory.com/wp-content/uploads/pdf/AS6C4008.pdf")


def atf22v10(p):
    p.ic("ATF22V10C", "U", "Microchip ATF22V10C SPLD (GAL22V10 compatible), DIP-24 300mil",
         "Package_DIP:DIP-24_W7.62mm_Socket",
         left=[("1", "I0/CLK", I), ("2", "I1", I), ("3", "I2", I), ("4", "I3", I), ("5", "I4", I),
               ("6", "I5", I), ("7", "I6", I), ("8", "I7", I), ("9", "I8", I), ("10", "I9", I),
               ("11", "I10", I), ("13", "I11", I), None, ("24", "VCC", P), ("12", "GND", P)],
         right=[("14", "IO0", B), ("15", "IO1", B), ("16", "IO2", B), ("17", "IO3", B), ("18", "IO4", B),
                ("19", "IO5", B), ("20", "IO6", B), ("21", "IO7", B), ("22", "IO8", B), ("23", "IO9", B)],
         half_w=7.62)


def atf16v8(p):
    p.ic("ATF16V8B", "U", "Microchip ATF16V8B SPLD (GAL16V8 compatible), DIP-20 300mil",
         "Package_DIP:DIP-20_W7.62mm_Socket",
         left=[("1", "I0/CLK", I), ("2", "I1", I), ("3", "I2", I), ("4", "I3", I), ("5", "I4", I),
               ("6", "I5", I), ("7", "I6", I), ("8", "I7", I), ("9", "I8", I), ("11", "I9/~{OE}", I), None,
               ("20", "VCC", P), ("10", "GND", P)],
         right=[("12", "IO0", B), ("13", "IO1", B), ("14", "IO2", B), ("15", "IO3", B), ("16", "IO4", B),
                ("17", "IO5", B), ("18", "IO6", B), ("19", "IO7", B)], half_w=7.62)


def hc4050(p):
    p.ic("CD74HC4050", "U", "Hex non-inverting buffer, inputs tolerate > VCC (5V->3.3V translator), DIP-16",
         "Package_DIP:DIP-16_W7.62mm",
         left=[("3", "A1", I), ("5", "A2", I), ("7", "A3", I), ("9", "A4", I), ("11", "A5", I),
               ("14", "A6", I), None, ("1", "VCC", P), ("8", "GND", P)],
         right=[("2", "Y1", O), ("4", "Y2", O), ("6", "Y3", O), ("10", "Y4", O), ("12", "Y5", O),
                ("15", "Y6", O), None, ("13", "NC", NCT), ("16", "NC", NCT)], half_w=7.62)
