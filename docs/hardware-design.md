# TRS-80 Model I FPGA Card — Hardware Design (rev 0.1)

The card plugs into the Model I 40-pin expansion bus and passes the bus through to an Expansion Interface. It gives the Z80 two things:

1. **A hardware sprite engine**, commanded through Z80 I/O ports 0x52/0x53. The FPGA keeps the sprite shapes and positions, composes each frame, and writes the result into the **frame buffer**. The frame buffer is 1 KB of shared dual-port RAM at 0x3000, laid out exactly like video RAM, and the Z80 copies it to the screen with a single `LDIR`. The command set is drafted in [sprite-engine.md](sprite-engine.md).
2. **An Am9511 APU (maths coprocessor)** on Z80 I/O ports 0x50/0x51, implemented in the FPGA. The behavioural reference is the MIT-licensed C emulator at <https://github.com/ratboy666/am9511>.
3. **2 KB of shared memory**, an IDT7132 dual-port RAM in the unused gap at 0x3000–0x37DF. It holds the frame buffer plus a bulk area that the Z80 can fill at `LDIR` speed, for example with sprite shapes or tile maps.

The FPGA cannot write into the Model I's own video RAM, because the Model I bus has no DMA or bus-request signals. That is why the FPGA's output goes through the shared frame buffer.

The bus-interface approach (Tang Nano 9K module, open-drain WAIT/INT, 1:1 bus pass-through, card-edge geometry) borrows from the TRS-IO M1 v1.3-xray board by Arno Puder: <https://github.com/apuder/TRS-IO/tree/nano-9k/kicad/m1/v1.3-xray>.

**Constraint: every component is through-hole.** The reference design's SMD 74LVC245 and SN74LVCH8T245 translators have no DIP equivalents. They are replaced by 5 V parts on the Z80 side, 2N7000 bidirectional shifters on the FPGA data bus, and a CD74HC4050 for the 5 V → 3.3 V control signals.

## Block diagram

```
 M1 bus (J1 edge) ══╤══════════════════════════════════════╗ 1:1 ══ J2 → Expansion Interface
                    │ A0-A15, RD*, WR*, IN*, OUT*           ║
           ┌────────┴────────┐                              ║ D0-D7
           │ U4 ATF22V10C    │ DP_CE_N ─┐                   ║
           │ memory decode   │          │      ┌────────────╨──────┐
           ├─────────────────┤          ├─────►│ U2 74HCT245       │◄─ RD_N (dir)
           │ U5 ATF16V8B     │ IORD/IOWR│      └────────┬──────────┘
           │ I/O decode      │ (+A1:A0) │          LD0-7│
           └─────────────────┘          │     ┌─────────┴──────────┐
                    │                   └────►│ U1 IDT7132  2Kx8   │ left port: Z80 (5V)
                    │                         │ dual-port SRAM     │ right port: FPGA
                    │                         └─────────┬──────────┘
                    │                           XD0-7 (5V)│  RA0-RA10, R_CE_N, R_RW_N (3.3V direct)
                    │   ┌──────────────────┐            │
                    │   │ U3 74HCT245      │◄───────────┤  (port data shares XD bus)
                    │   │ PORT <-> D0-D7   │◄─ PORT_OE_N (FPGA), IN_N (dir)
                    │   └──────────────────┘            │
                    │                       Q1-Q8 2N7000 + RN1/RN2 (bidirectional 5V<->3.3V)
                    ▼                                    │ FD0-7 (3.3V)
              U6 CD74HC4050 (5V→3.3V) ───────────►  U7 Tang Nano 9K (GW1NR-9)
                                                         │ WAIT_DRV, INT_DRV
                                         Q9/Q10 2N7000 ◄─┘ open drain → WAIT*, INT*
```

## Z80 memory map (IDT7132 left port)

| Address | Size | Use |
|---|---|---|
| 0x3000–0x33FF | 1024 | **Frame buffer**: sprite engine output, 64×16, laid out exactly like video RAM at 0x3C00 |
| 0x3400–0x37DF | 992 | Bulk data area: sprite shapes, tile maps, APU vectors. The FPGA reads it when told to by a port command |
| 0x37E0–0x37FF | 32 | Expansion Interface memory-mapped I/O. **Not decoded** unless JP3 (FULL) is fitted, and fit it only when no EI is attached |

Showing a frame:

```z80
        LD   HL,3000H     ; screen buffer in DPRAM
        LD   DE,3C00H     ; Model I video RAM
        LD   BC,0400H
        LDIR              ; ~21.5k T-states ≈ 12 ms at 1.774 MHz
```

If the FPGA writes a byte while the Z80 is reading the same address, the IDT7132 arbitrates. With JP1 fitted, the left-port BUSY signal stretches the Z80 cycle through WAIT*, so nothing tears at byte level. To avoid frame-level tearing, the FPGA composes each frame in its own block RAM. It copies the frame into the DPRAM frame buffer only on a `RENDER` command, and status reports when the copy is finished.

## Z80 I/O map

U5 decodes a block of four ports. A1:A0 are passed to the FPGA (PA1/PA0) to pick the register.

| Port (default) | Port (JP4 fitted) | OUT (write) | IN (read) |
|---|---|---|---|
| 0x50 | 0x70 | Am9511 data push | Am9511 data pop |
| 0x51 | 0x71 | Am9511 command | Am9511 status |
| 0x52 | 0x72 | Sprite engine parameter byte | Sprite engine result byte |
| 0x53 | 0x73 | Sprite engine command | Sprite engine status |

0x50/0x51 match the default ports used by the am9511 emulator's hardware test programs (80/81 decimal).

**I/O cycle mechanics:**
1. U5 asserts `IORD` or `IOWR`. PA1:PA0 select the register.
2. The FPGA finishes any DPRAM access in progress, deselects the right port, and then drives `PORT_OE_N` low. U3 then connects D0–D7 to the shared XD bus, with direction set by IN*.
3. If the APU is busy, the FPGA holds WAIT* through Q9 until data is ready. This is how the real Am9511 PAUSE pin behaves. The sprite engine never holds WAIT; it reports BUSY in its status register instead.

## FPGA (Tang Nano 9K) pin allocation

| Header pin | GW1NR pin | Net | Dir | Notes |
|---|---|---|---|---|
| 1–4 | P38/P37/P36/P39 | — | | Used by the module's own TF card slot (SD available to the FPGA) |
| 5–15 | P25–P30, P33, P34, P40, P35, P41 | RA0–RA10 | out | DPRAM right-port address |
| 16–22, 27 | P42, P51, P53–P57, P32 | FD0–FD7 | bidir | via 2N7000 shifters to XD0–XD7 |
| 28 | P31 | R_BUSY_3V3_N | in | DPRAM right-port BUSY (via U6) |
| 29 / 30 | P49 / P48 | IORD_3V3 / IOWR_3V3 | in | port-block strobes from U5 via U6 |
| 38 / 39 | P76 / P77 | PA0_3V3 / PA1_3V3 | in | Z80 A0 / A1 via U6: register select within the port block |
| 48 | P63 | SYSRES_3V3_N | in | Model I system reset via U6 |
| 32 | P70 | PORT_OE_N | out | U3 enable, 10k pull-up (off while configuring) |
| 33 / 34 | P71 / P72 | R_CE_N / R_RW_N | out | DPRAM right port, 10k pull-ups |
| 36 / 37 | P74 / P75 | WAIT_DRV / INT_DRV | out | Q9/Q10 gates, 10k pull-downs |
| 23, 24, 35 | P68, P69, P73 | GPIO | | spare → J4 |
| 40–47 | P79–P86 | GPIO (**1.8 V bank**) | | spare → J4, 1.8 V only |
| 25 | 3V3 | +3V3 | out | module regulator powers the board's 3.3 V logic |
| 31 | 5V | TANG_5V | in | from +5V through D2 |

Header numbering matches the TRS-IO xray symbol: pins 1–24 run along one row and 25–48 come back along the other.

## Power

- **J3**: 5 V regulated barrel jack (centre positive, ≥1 A), through D1 (1N5819) to +5V. Estimated load is about 0.5 A: IDT7132SA ~165 mA typ, two GALs ~60–90 mA each, Tang Nano ~100–150 mA.
- **D2** feeds the Tang Nano 5V pin and blocks back-feed when the module is plugged into USB for programming.
- **JP5** links bus pin 40 to +5V. Leave it open unless that supply has been confirmed on your machine.
- **3.3 V** comes from the Tang Nano's own regulator. It only feeds U6, pull-ups and MOSFET gates, so there is no second regulator.

## Jumpers

| Ref | Fitted means |
|---|---|
| JP1 BUSY→WAIT | DPRAM collision stretches the Z80 cycle (recommended) |
| JP2 INT EN | FPGA may interrupt the Z80 via INT* |
| JP3 FULL 2K | Window extends to 0x37FF. **Only without an Expansion Interface** |
| JP4 PORT ALT | Port block at 0x70–0x73 instead of 0x50–0x53 |
| JP5 EDGE 5V | Board powered from bus pin 40 |

## Programmable logic

- `hardware/gal/mem_decode.pld`: U4 ATF22V10C (WinCUPL, device `g22v10`)
- `hardware/gal/io_decode.pld`: U5 ATF16V8B (WinCUPL, device `g16v8a`)

Compile with WinCUPL (or galette) and program with a TL866II+/T48.

## Bill of materials (all through-hole)

| Ref | Qty | Part | Footprint |
|---|---|---|---|
| U1 | 1 | IDT7132SA/LA (2K×8 DPRAM) + 48-pin 600 mil socket | DIP-48 |
| U2, U3 | 2 | 74HCT245 | DIP-20 |
| U4 | 1 | ATF22V10C-15PU + socket | DIP-24 (300 mil) |
| U5 | 1 | ATF16V8B-15PU + socket | DIP-20 |
| U6 | 1 | CD74HC4050E | DIP-16 |
| U7 | 1 | Sipeed Tang Nano 9K + 2× 1×24 female headers | 0.9" row spacing |
| Q1–Q10 | 10 | 2N7000 | TO-92 |
| RN1, RN2 | 2 | 4.7k ×8 bussed SIP-9 | SIP-9 |
| R1, R2, R5–R9 | 7 | 10k ¼W | axial |
| R3, R4 | 2 | 4.7k ¼W | axial |
| R10 / R11 | 2 | 470R / 1k ¼W | axial |
| C1–C6 | 6 | 100 nF ceramic disc | 5 mm |
| C7 / C8 | 2 | 100 µF / 10 µF 10 V electrolytic | radial 6.3 mm |
| D1, D2 | 2 | 1N5819 | DO-41 |
| D3 | 1 | BAT85 | DO-35 |
| D4 / D5 | 2 | 3 mm LED green / red | |
| J1 | 1 | Card-edge fingers (part of the PCB, beveled, hard gold) | |
| J2 | 1 | 2×20 shrouded IDC box header | |
| J3 | 1 | 2.1 mm barrel jack | |
| J4 | 1 | 2×8 pin header | |
| JP1–JP5 | 5 | 1×2 pin header + shunt | |

## PCB (rev 0.1: fully routed, DRC clean)

`hardware/kicad/trs80_fpga_card.kicad_pcb` was placed by `hardware/tools/gen_pcb.py` and autorouted with Freerouting 2.5.0. The last two connections were then finished with `hardware/tools/route_net.py`. Each footprint is linked to its schematic symbol, so *Update PCB from Schematic* (F8) works normally. Views are in `hardware/pcb_routed_copper.png` and `hardware/pcb_render_top.png`.

**Do not re-run `gen_pcb.py --force` now**: it would throw away the routing.

**Routing status:**
- All nets are routed. The DRC shows **0 violations, 0 unconnected items and 0 schematic-parity issues**.
- GND is routed as real tracks, and pours on both layers add copper on top of that.
- Seven GND pins (U2.10, U5.10, J2.30, J2.38, C6.2, J4.2, J4.6) have a solid pour connection instead of thermal spokes. It joins a small pour scrap that otherwise failed the "starved thermal" check, and the scraps are small enough not to hurt hand soldering.
- **SYSRES_N** (U6.3 → bus) and **A11** (bus → U4.5) were finished by the grid maze router. They are long, at ~119 mm and ~189 mm with 10 vias each, because the board is crowded there. That is harmless at the Model I's 1.77 MHz, but they are the first candidates if you want to tidy the layout by hand.
- `route_net.py` (KiCad Python) routes a single connection: `route_net.py board.kicad_pcb NET REF PAD X Y`, where X, Y are the target track's position from the DRC "unconnected items" report. It uses 0.25 mm tracks, keeps 0.27 mm clearance, and avoids keep-outs and the board edge.

**How it was autorouted** (to repeat after changes):
1. Export a Specctra DSN (*File → Export → Specctra DSN*).
2. Delete the `(plane GND …)` line so Freerouting routes GND as a net. Left as a plane, its own tracks cut the pour into islands.
3. Run `java -jar freerouting-2.5.0.jar --gui.enabled=false -de board.dsn -do board.ses`. This needs Java 25; the self-contained Windows CLI build crashes on this board.
4. Import the `.ses` and refill the zones (B).
5. The 0.6 mm edge keep-out strips stop the router from running tracks along the board edge, because Freerouting ignores KiCad's edge-clearance rule.

- **Board:** 2 layers, 150 × 110 mm, plus a 56 × 10 mm card-edge tab for J1 centred under J2. Order with **beveled edge and hard gold (or ENIG) fingers**, 1.6 mm thick.
- **Placement by function:**
  - J1 fingers sit directly under J2, so the 40 bus lines run straight through.
  - Z80-side logic (U2–U5) is in a row above J2.
  - U1 is in the middle, with its left port facing the bus and its right port facing the FPGA.
  - The 2N7000 shifters and SIP pull-ups sit between U1 and the Tang Nano (top right).
  - Power is top left, with the barrel jack opening at the left edge.
  - Jumpers, WAIT/INT and J4 are bottom right.
- **Net classes** (in the `.kicad_pro`): Default 0.3 mm tracks and 0.2 mm clearance. Power (+5V, +3V3, GND, VIN, TANG_5V, EDGE_5V) gets 0.8 mm tracks and 0.25 mm clearance.
- **Board rules:** minimum track 0.15 mm, because the autorouter necks down to that width at some pins. Copper-to-edge clearance is 0.4 mm. Both are inside typical fab limits (0.127 mm tracks, 0.3 mm edge).
- **GND pours** on both layers over the main body; the finger tab is left clear.

## Open items to verify before ordering PCBs

1. **IDT7132 DIP-48 pinout.** The symbol was transcribed from the IDT7132/7142 datasheet layout. Check it pin by pin against the datasheet for the exact part you buy.
2. ~~Tang Nano 9K pins P70–P75 voltage bank.~~ **Resolved:** the Gowin pin report puts P70–P77 in bank 1, alongside the 3.3 V clock pin 52 and P48/P49/P63. Bank 3 (LEDs, buttons, P79–P86) is the 1.8 V bank. Avoid fitting an LCD to the module, because P70–P75 are shared with its LCD connector.
3. **Tang Nano 9K header row spacing.** The footprint uses 0.9" (22.86 mm). The TRS-IO footprint uses 22.9 mm. Measure your module.
4. **Model I RD*/WR* qualification.** Confirm whether the expansion-bus RD*/WR* are MREQ-qualified. The MEMQ term covers either case.
5. **The Model I must accept read data from the bus at 0x3000–0x37DF.** Confirm on the target machine that the M1 enables its external data buffer for this range, as it does for the 0x37E0 EI registers.
6. **Card-edge orientation.** Even pins are on the top copper and odd on the bottom, matching TRS-IO M1. Check the mating ribbon socket before release.
