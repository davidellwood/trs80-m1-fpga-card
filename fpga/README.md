# FPGA design: Tang Nano 9K (GW1NR-LV9QN88PC6/I5)

Verilog-2001 with a 27 MHz system clock from the on-board oscillator, built with Gowin EDA.

| Part | Status | Files |
|---|---|---|
| 1. Top level and pin constraints | done | `src/trs80_card_top.v`, `constraints/trs80_card.cst`, `constraints/trs80_card.sdc` |
| 2. Bus logic: Z80 port interface and DPRAM right-port controller | done | `src/xbus.v`, `src/sync2.v` |
| 3. Am9511 core | done | `src/am9511.v` + generated `src/am9511_ucode.vh`: the full command set, including microcoded SIN…PWR. Bit-exact to the models ([docs/am9511.md](../docs/am9511.md)) |
| 4. Sprite engine | done | `src/gfx_regs.v` (port protocol, FIFOs, status), `src/sprite_engine.v` (all commands, RENDER), `src/spram.v` |

## Build

```bash
C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe build.tcl
```

The bitstream lands in `impl/pnr/trs80_card.fs`. Load it with Gowin Programmer over the Tang Nano's USB: SRAM to test, embedded flash to keep it.

Current build:

| Resource | Use |
|---|---|
| Logic (LUTs) | 6,872 of 8,640 (80%) |
| Logic slices | 89% |
| Registers | 2,010 (31%) |
| Block RAMs | 8 of 26 |
| Fmax | 31.3 MHz against the 27 MHz needed |

There are no timing violations and no warnings.

Approximate split: the Am9511 core is about 2,850 LUTs including its microsequencer, and the sprite engine about 1,800. The device is now nearly full, so new features will need area reclaimed first. Candidates:
- Pipeline the float adder's exponent compare and clamp; this is also the slowest timing path.
- Move the sprite table into block RAM.

## How the bus logic works (`xbus.v`)

The FPGA's 8 data pins (FD) reach the 5 V side (XD) through the 2N7000 shifters. XD connects to both the IDT7132 right port and U3, the 74HCT245 to the Z80 data bus. One state machine owns that bus, so no two devices can drive it at once.

- **Z80 port cycles (0x50–0x53) have priority.** WAIT* is raised the moment IORD/IOWR is seen and released only once read data has settled through the shifter and U3, or once write data has been captured. This makes reads and writes independent of shifter rise times and of any DPRAM cycle in progress. A DPRAM read in progress is aborted and retried; a write always completes.
  - **IN:** the FPGA drives FD, then enables U3 (`PORT_OE_N`), and releases WAIT after about 370 ns. The register is "popped" when IN* ends, which is how the Am9511 data stack and the result FIFO consume a byte.
  - **OUT:** the FPGA enables U3 (direction bus → XD), samples FD after about 440 ns, and releases WAIT.
- **WAIT cap:** WAIT is never held longer than 500 µs. That protects the Model I's DRAM refresh, which the Z80 itself performs. If the cap is hit, LED 3 lights.
- **DPRAM writes** are CE-controlled with R/W taken low first, because OE_R is tied low on the board (CE low with R/W high makes the RAM drive the bus). If BUSY_R appears, the write pulse is extended, and one clean pulse is issued after BUSY clears.
- **DPRAM reads** hold CE for 10 clocks (370 ns) before sampling, allowing for the slow rising edge through the RN1 pull-ups.

All timing values are parameters at the top of `xbus.v`.

**End-of-IN handover (found in simulation).** When IN* rises, U3's direction flips straight away to "Z80 bus → XD", because DIR comes from IN*. The synchronised strobe reaches the state machine about 3 clocks later. That would leave U3 and the FPGA both driving the shared bus for about 140 ns. To prevent it, `trs80_card_top.v` gates the FD drive and `PORT_OE_N` with the *raw* IORD/IOWR pins, so both drop within the GAL + 4050 delay (~30 ns) and the overlap is at most a few nanoseconds.

A board rev could close the gap completely by routing `PORT_OE_N` through a spare U5 pin and gating it with the strobe there. U5 has three unused pins (17–19).

**Power-up state.** The bus outputs have initial values (CE and R/W high, U3 disabled, FD released) that apply from configuration, before reset.

## Sprite engine (`sprite_engine.v`)

It implements the full command set in [docs/sprite-engine.md](../docs/sprite-engine.md) and reports VERSION 0.2. It also keeps three diagnostic commands for bring-up:

| CMD (OUT 0x53) | Params (OUT 0x52) | Effect |
|---|---|---|
| 0xF0 FB_FILL | char | fills 0x3000–0x33FF with *char*, sets FRAME |
| 0xF1 PEEK | lo, hi | 1 result byte from DPRAM offset hi:lo |
| 0xF2 POKE | lo, hi, val | writes *val* to DPRAM offset hi:lo |

**Memory** (block RAM):
- background map, 1 KB;
- working frame, 1 KB;
- 64 shapes × 16 rows × 16 bits;
- a 128×48 pixel ownership map (6 bits per pixel) for collisions.

The sprite table and the 32×32 collision masks live in distributed RAM.

**RENDER** takes 2.7 ms, measured in simulation, which is well inside the Z80's 12 ms `LDIR`:
1. Add velocities.
2. Copy the background into the working frame.
3. Clear the ownership map.
4. Draw sprites 0–31 pixel by pixel (3 clocks per set pixel), with OPAQUE clearing first and collisions recorded as it goes.
5. Copy the frame into DPRAM 0x000–0x3FF and set FRAME.

**Power-up:** the engine runs RESET by itself. The background becomes blanks, and all sprites and shapes are cleared.

**First test on real hardware:**
1. `OUT 53H,02H`, then `IN 52H` four times; you should get 0, 2, 32, 64.
2. Push 0BFH to port 52H and send FB_FILL (`OUT 53H,0F0H`).
3. `LDIR` 0x3000 → 0x3C00. The screen should fill with solid blocks.

The Am9511 port pair (0x50/0x51) is described in [docs/am9511.md](../docs/am9511.md). A quick hardware check:
1. Send `OUT 51H,1AH` (PUPI).
2. Read `IN 50H` four times; you should get 02 C9 0F DA.

## On-board LEDs

| LED | Meaning |
|---|---|
| 0 | Heartbeat |
| 1 | Z80 port access |
| 2 | DPRAM access |
| 3 | WAIT cap hit |
| 4 | FRAME ready |
| 5 | In reset |

## Simulation

`sim/tb_top.v` models the board and the CPU:
- the IDT7132, including tied-low OE_R and BUSY;
- the level shifters' slow rising edges;
- U3, and U5/U6 delays;
- Z80 IN/OUT cycles at 1.774 MHz that honour WAIT;
- a checker that fails the run if two devices ever drive the shared bus at once.

It checks VERSION, POKE/PEEK, a POKE blocked by BUSY, FB_FILL with status polling during the fill, the Am9511 stack, error handling, and port decoding.

```bash
powershell -ExecutionPolicy Bypass -File sim/run_sim.ps1 -IverilogDir <oss-cad-suite>\bin
```

Last run, with Icarus Verilog 14 from OSS CAD Suite:

| Measure | Result |
|---|---|
| Overall | **PASS**, 22/22 checks |
| Bus contention events | 0 |
| Worst switching overlap | 5 ns |
| Write pulse while BUSY_R was held for 2 µs | stretched to 2.6 µs, and the write landed |
| WAIT timeouts | 0 |

The run writes `sim/tb_top.vcd`, which you can open in GTKWave (included in OSS CAD Suite) to inspect the bus timing.

### Sprite engine against a reference model

`sim/sprite_model.py` is an independent Python model of the engine's rules. It also defines a test scenario covering every command:
- text, lines, boxes and plots;
- shapes defined through the ports and loaded from DPRAM;
- sprites with XOR, X/Y mirroring, OPAQUE over text, NOCOLLIDE, and positions partly or fully off screen;
- collisions, velocities, scrolling, bulk background load, RESET and auto-render;
- every error case, and dropping of unused parameters.

`sim/tb_sprite.v` replays the same scenario as Z80 port cycles through the full top level and board model. The script then compares every rendered frame and every byte read back.

```bash
powershell -ExecutionPolicy Bypass -File sim/run_sprite_sim.ps1 -IverilogDir <oss-cad-suite>\bin
```

Last run:

| Measure | Result |
|---|---|
| Overall | **PASS** |
| Frames identical to the model | 9/9 |
| Bytes read back that match | 48/48 |
| Bus contention | 0 |
| RENDER time | 2.65–2.77 ms |

`sim/frame_png.py frames.txt out.png` draws frames as images; `sim/sprite_frames.png` shows five of them.

### Am9511 core against its reference model

`sim/apu_model.py` follows the ratboy666 emulator's semantics, plus the documented fixes. It computes float results exactly with fractions and then rounds them, and on every run it cross-checks that rounding against the emulator's IEEE-single path. Its scenario has directed edge cases plus 700 random operations: integer, float, square root, conversions and stack operations, with operands near the limits and near-cancelling float subtractions.

```bash
powershell -ExecutionPolicy Bypass -File sim/run_apu_sim.ps1 -IverilogDir <oss-cad-suite>\bin
```

Last run: **PASS**, with 5,216 of 5,216 status and result bytes identical and 0 bus contention. The longest BUSY time is 57 µs (PWR).

The derived functions run as microcode. `sim/apu_ucode.py` fits the polynomial coefficients, assembles the program into `src/am9511_ucode.vh`, and holds the interpreter the model uses. Run it directly to print the accuracy table.

## Pin banks (confirmed by the Gowin pin report)

- **Bank 1 (3.3 V):** clock pin 52, P48/P49/P63, P70–P77.
- **Bank 2 (3.3 V):** P25–P42 and the FD pins.
- **Bank 3 (1.8 V):** LEDs, buttons and P79–P86.

The five outputs on P70–P75 are therefore safe at 3.3 V.
