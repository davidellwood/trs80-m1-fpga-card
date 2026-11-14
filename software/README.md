# Z80 software for the TRS-80 Model I FPGA card

| Path | Contents |
|---|---|
| `lib/trs80card.asm` | The library: INCLUDE it into your program (sjasmplus syntax) |
| `demo/demo.asm` | Assembly demo. Builds to `build/DEMO.CMD`, loaded at 6000h, run from DOS |
| `basic/cardusr.asm` | USR() module for Level II BASIC, at 7D00h–7FFFh |
| `basic/demo.bas` | Level II BASIC demo, generated, with the USR module in DATA lines |
| `test/libtest.asm` | Test program that exercises every library routine |
| `tools/` | Z80 emulator, Model I + card test harness, tests, /CMD writer, BASIC generator |
| `build.ps1` | Assembles everything and runs the tests |

## Building

You need the free **sjasmplus** assembler (<https://github.com/z00m128/sjasmplus>; the Windows build is a single exe) and Python 3.

```bash
powershell -ExecutionPolicy Bypass -File build.ps1 -Sjasm C:\path\to\sjasmplus.exe
```

## Library reference

The ports and addresses are EQUs at the top of the file: 50h–53h (change them to 70h–73h if JP4 is fitted), 3000h for the frame buffer and 3400h for the bulk area. The library uses no ROM calls and no interrupts.

Every routine returns **CF = 1 on error**: an engine ERR, an APU error, or a timeout of about 1.5 s. A holds the status byte. Registers not listed are preserved.

### Card and sprite engine

| Routine | In | Out / notes |
|---|---|---|
| `CARD_DETECT` | — | CF = 1 if there's no card, without hanging. Else A = engine minor version |
| `GFX_CMD` | A = command | Waits until done |
| `GFX_WAIT` | — | A = status |
| `GFX_BLOCK` | HL → [cmd, n, p1..pn] | Sends any command from a table. HL → after the block |
| `SPR_SET` | A = sprite, B = shape, D = x, E = y, C = flags | |
| `SPR_MOVE` | A = sprite, D = x, E = y | |
| `SPR_VEL` | A = sprite, D = dx, E = dy | Applied by every RENDER |
| `SPR_FLAGS` | A = sprite, C = flags (`SF_VISIBLE`, `SF_XOR`, `SF_MIRROR_X/Y`, `SF_OPAQUE`, `SF_NOCOLLIDE`) | |
| `SPR_SHAPE` | A = sprite, B = shape | |
| `SPR_GET` | A = sprite | D = x, E = y |
| `SPR_COLLIDE` | A = sprite, HL → 4-byte buffer | Mask in (HL); A = OR of the mask (Z = no hit). Destroys B, C |
| `BG_FILL` | A = character | |
| `BG_PUTC` | B = column, C = row, A = character | |
| `BG_PRINT` | HL → text ending in 0, B = column, C = row | Clipped at column 64 |
| `BG_PLOT` | D = x, E = y, A = 0 clear / 1 set / 2 xor | |
| `BG_SCROLL` | D = dx, E = dy (character cells) | |
| `BG_FROM` | HL → 1024-byte screen image | Uses the frame buffer as transfer space |
| `SHAPE_FROM` | A = id, B = width, C = height, HL → rows (2 bytes each) | Copies through the bulk area |
| `FRAME_SHOW` | — | RENDER, wait, copy to the screen. Destroys BC, DE, HL |
| `FRAME_COPY` | — | Copy only, for use with RENDER_AUTO |

### Am9511

| Routine | In | Out / notes |
|---|---|---|
| `APU_CMD` | A = command (`A_FADD`, `A_SIN` …; add `A_SINGLE`/`A_DOUBLE` for integers) | A = status |
| `APU_WAIT` | — | A = status |
| `APU_PUSH4` / `APU_PUSH2` | HL → value, least significant byte first | HL advanced |
| `APU_POP4` / `APU_POP2` | HL → destination | |
| `MBF_TO_AM` / `AM_TO_MBF` | HL → 4 bytes, converted in place | Between Level II BASIC single precision and the Am9511 format. CF = 1 if the number is out of the Am9511's range |
| `FP1` | HL → BASIC variable, C = command | Variable = f(variable) |
| `FP2` | HL → A, DE → B, C = command | A = B op A, e.g. `A_FDIV` gives B/A and `A_PWR` gives B^A |

FP1 and FP2 leave the variable unchanged on an error.

**Fastest maths:** keep numbers in Am9511 format and chain operations on its stack. `demo.asm`'s `ship_pos` is an example. Use FP1/FP2 when you're working with BASIC variables.

## BASIC

1. Power on and answer **MEMORY SIZE? 32000** to protect the USR module.
2. Load and RUN `basic/demo.bas`. It POKEs the module from DATA lines, checks the checksum, and sets the USR vector to 7D00h.

The sprite engine is driven directly with `OUT 82,param` / `OUT 83,command` and `INP(83)` for status.

| Call | What it does |
|---|---|
| `R = USR(0)` | RENDER and copy to the screen |
| `R = USR(1)` | Copy only |
| `R = USR(2)` | Variable at address CTL_A = f(itself), f = command at CTL_CMD |
| `R = USR(3)` | Variable at CTL_A = (variable at CTL_B) op (variable at CTL_A) |

Control block: POKE the command at 32003, CTL_A low/high at 32004/32005 and CTL_B at 32006/32007. Get the addresses with `VARPTR`. A result of 256 or more means an error.

## What has been tested, and how

`tools/test_lib.py` runs the real assembled code in `tools/z80emu.py`, a Z80 interpreter that refuses any instruction it doesn't implement. That's wired to the sprite-engine and Am9511 models, which are themselves verified bit for bit against the FPGA Verilog. The expected results come from the models and from an independent Python version of the BASIC float conversion.

| Area | Checked |
|---|---|
| Library | Every routine. Card detection with and without a card; 18 float-format conversions including out-of-range values; FP1/FP2 for SIN, COS, SQRT, LN, EXP, ATAN, LOG, FADD, FSUB, FMUL, FDIV, PWR plus error cases; all sprite and background routines; the rendered frames |
| USR module | Functions 0–3, the error path, an unknown function |
| Demo | 40 frames with no library errors; the screen matches the rendered frame; collisions seen. `demo/demo_frames.png` shows four frames |

**Last run: PASS.**

**Timing (emulated Z80 at 1.774 MHz):** the demo's Z80 work is 17.4 ms per frame, of which the screen copy is 12 ms. Adding the card's 2.7 ms render gives about **50 frames/s** for six balls, a ship and Am9511 trigonometry every frame.

**Not tested:**
- **Level II BASIC itself.** There's no BASIC ROM in the emulator. The USR module was tested by simulating the ROM's argument and return calls (0A7Fh/0A9Ah), but `demo.bas` hasn't been run. The MEMORY SIZE check at 16561/16562 and the SPACE-bar test are also untested.
- **A real machine.** The card's bus timing is covered by the FPGA simulation, but nothing here has run on a real Model I yet.
