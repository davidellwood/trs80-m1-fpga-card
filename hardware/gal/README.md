# GAL logic

The `*.pld` files (CUPL) are the design reference. `galasm/*.gal` hold the same logic in GALasm syntax, and `galasm/*.jed` are the files to program.

| JEDEC file | Board / ref | Program into | Mode | Function |
|---|---|---|---|---|
| `galasm/ecb_bridge_card.jed` | Bridge card U3 | ATF16V8B (as GAL16V8) | simple | Model I → ECB MREQ*/IORQ*/RD*/WR*/M1*/RESET* (rev 3.0, no EI gating) |
| `galasm/ecb_bridge_claim.jed` | Bridge card U6 | ATF22V10C (as GAL22V10) | — | Data-buffer direction and enable: claims reads at 3000–37DF, 8000–FFFF and ports 40–43/50–53/70–73/C0–CF (rev 3.1) |
| `galasm/ecb_bridge.jed` | Backplane U3 | ATF16V8B (as GAL16V8) | simple | Model I → ECB MREQ*/IORQ*/RD*/WR*/M1*/RESET*, EI RD*/WR* gating |
| `galasm/ecb_mem_decode.jed` | FPGA card U4 | ATF22V10C (as GAL22V10) | — | IDT7132 select, 3000h–37DFh (37FFh with FULL) |
| `galasm/ecb_io_decode.jed` | FPGA card U5 | ATF16V8B | complex | Ports 50h–53h (70h–73h with ALT), ACT LED |
| `galasm/ecb_sd_decode.jed` | SD card U2 | ATF16V8B | complex | Ports C0h–CFh, Pico handshake, WAIT* open-drain |
| `galasm/ecb_xmem_io.jed` | Banked memory U3 | ATF16V8B | simple | OUT 41h/42h/43h register clocks, IN 43h readback |
| `galasm/ecb_xmem_mem.jed` | Banked memory U4 | ATF16V8B | complex | SRAM select 8000h–FFFFh, SRAM A14, EXTMEM* |
| `galasm/mem_decode.jed` | Rev 0.1 card U4 | ATF22V10C | — | Rev 0.1 memory decoder |
| `galasm/io_decode.jed` | Rev 0.1 card U5 | ATF16V8B | simple | Rev 0.1 I/O decoder |

**Programming**
- **Programmer:** with a TL866II+ or T48, choose the ATF16V8B or ATF22V10C device and load the `.jed`. GAL16V8 and GAL22V10 fuse maps (2194 and 5892 fuses) are what these Atmel/Microchip parts expect.
- **Security fuse:** left off, so you can read the parts back to verify them.
- **Pin lists:** the `.pin` and `.chp` files next to each `.jed` show the pin assignment.

**Rebuilding and verifying**

```bash
powershell -ExecutionPolicy Bypass -File build_jed.ps1
```

1. **Assemble:** the script assembles every `galasm/*.gal` with GALasm 2.1. That's github.com/daveho/GALasm, built locally into `C:\path\to\tools\galasm`; its licence forbids commercial use.
2. **Verify:** it then runs `hardware/tools/galsim.py`. That reads each `.jed`, checks the JEDEC fuse checksum, and simulates the GAL16V8 or GAL22V10 fuse array on every input combination. The simulated outputs (0, 1 or tri-state) must match a Python model written from the CUPL source.
3. **Current result:** all 10 designs match.
4. **Checking the checker:** a mutation test drops each literal of every live product term, one at a time. The checker caught all but one change; that one is a logically redundant literal in `ecb_xmem_mem`, so its fuse map is equivalent.

**Differences from the CUPL**
- **Equations written out:** GALasm has no parentheses, so each equation is expanded to a sum of products. The two 22V10 memory decoders are written in complement form, so they fit the 8 product terms of pin 23.
- **`ecb_sd_decode` rev 2.1:** a GAL16V8 output enable is a single product term, so WAIT*'s enable is SEL & !ACK. The (RD* | WR*) term is not needed, because with M1* high, IORQ* only asserts together with RD* or WR*. The `.pld` was changed to match.
- **CUPL/WinCUPL:** if you compile the `.pld` files with WinCUPL instead, compare its JEDEC output with galsim the same way.
