# Ordering the rev 2 PCBs

Each board has a ready-to-upload package in its `gerbers/` folder.

- **Gerbers:** Protel extensions, X2 attributes, solder mask subtracted from the silkscreen.
- **Drill:** Excellon in mm, with plated (PTH) and non-plated (NPTH) holes in separate files. The PDF drill maps are for reference and are not in the zips.

All boards were generated on 2026-11-14 (bridge card 2026-11-15) after a final DRC with schematic parity: 0 violations, 0 unconnected pads and 0 footprint errors on every board.

| Board | Package | Size | Layers | Notes |
|---|---|---|---|---|
| Backplane | `backplane/gerbers/trs80_backplane_fab.zip` | 196.6 × 118 mm (incl. 10 mm finger tab) | **4** | Order as **4 layers**. Card-edge fingers (J1): order **ENIG or hard gold** and a **beveled edge** (about 30° on the finger tab) |
| Bridge card | `card-bridge/gerbers/trs80_card_bridge_fab.zip` | 160 × 100 mm | 2 | Eurocard; an alternative to the backplane. Needs a standard ECB backplane (e.g. RetroBrew) and a 40-way ribbon with a card-edge socket for the Model I |
| FPGA card | `card-fpga/gerbers/trs80_card_fpga_fab.zip` | 160 × 100 mm | 2 | Eurocard |
| SD card | `card-sd/gerbers/trs80_card_sd_fab.zip` | 160 × 100 mm | 2 | Eurocard |
| Banked memory | `card-xmem/gerbers/trs80_card_xmem_fab.zip` | 160 × 100 mm | 2 | Eurocard |

**Settings for any board house (JLCPCB, PCBWay, etc.)**
- **Thickness:** 1.6 mm. This matters for the backplane fingers and the DIN 41612 connectors.
- **Copper:** 1 oz outer. The backplane's inner layers can use the standard stackup.
- **Minimum track:** 0.15 mm in places, 0.3 mm for most signals, 1.0 mm for power. Minimum clearance is 0.2 mm.
- **Minimum drill:** 0.4 mm vias; the largest hole is 1.5 mm.
- **Finish:** HASL is fine for the cards. The backplane needs ENIG or hard gold for its fingers.

**Backplane or bridge card?** Order one of the two, not both:
- **Custom backplane:** 5 slots, its own 5 V supply, and a pass-through to the Expansion Interface, including the EI RD*/WR* gating the banked-memory card needs. It's a 4-layer board.
- **Bridge card:** a 2-layer Eurocard for an existing standard ECB backplane (e.g. RetroBrew). The Model I connects by ribbon to a right-angle header. There's no Expansion Interface support.
- **Assembly:** none. Every part is through-hole and hand-soldered.

**Before you order, check these against real parts.** Each is listed in `docs/rev2-architecture.md`.
1. **Tang Nano 20K:** row spacing (20.32 mm assumed), orientation (pads 1/21 at the USB-C end), and any pull-ups on P86/P72.
2. **IDT7132 DIP-48 pinout:** FPGA card.
3. **AS6C4008 DIP-32 pinout:** banked-memory card (JEDEC 628512 layout assumed).
4. **SD breakout pin order:** SD card J2, in Adafruit #254 order.
5. **Keystone 103 holder footprint:** SD card BT1.
6. **Model I connection:** for the backplane, check the card-edge orientation and finger geometry (rev 0.1 open items). For the bridge card, use a ribbon with a card-edge socket at the Model I end and an IDC socket at the card, wired pin n = pin n, and check pin 1 at both ends.
7. **Model I behaviour:** whether it accepts read data at 3000h, and whether its RD*/WR* are memory-only.

**Also needed before the boards work**
- **GALs:** program the JEDEC files from `hardware/gal/galasm/` with a TL866/T48 programmer. They're already compiled and verified; see `hardware/gal/README.md` for which file goes in which socket.
- **FPGA:** build the 20K bitstream (`fpga/build20k.tcl`).
- **SD card:** build the Pico firmware (`firmware/sdcard/build.ps1`, output `frehd_pico.uf2`).
