# FreHD-compatible SD card firmware (Raspberry Pi Pico)

This is the firmware for the rev 2 ECB SD card (`hardware/card-sd`). It is an independent implementation of the FreHD hard-disk register protocol on ports C0h–CFh, so FreHD drivers and utilities for LDOS, LS-DOS, NEWDOS and CP/M should work unchanged. The protocol was taken from the published FreHD sources (GPL-3.0); no FreHD code is used.

## What it emulates

- **Hard disk:** the WD1010 task file at C8h–CFh (READ, WRITE, SEEK, VERIFY, RESTORE, TEST, plus FORMAT/INIT as no-ops) and 128/256/512/1024-byte sectors chosen by SDH.
- **Images:** up to four `.HDV` images (Reed header, FreHD/xtrs format) named `hard4-0` … `hard4-3` in the card's root.
  - A drive is write-protected when its header write-protect bit is set or the file is read-only.
  - Reading past the end of a sparse image returns zeros.
  - Writes are flushed to the card 3 s after the last one.
- **C0h:** write-protect register. **C1h:** control register.
- **FreHD extension interface:** C2h DATA2, C3h SIZE2, C4h COMMAND2, C5h ERROR2.
  - Supported commands: VERSION, GETTIME, SETTIME, OPENFILE, READFILE, WRITEFILE, CLOSEFILE, OPENDIR, READDIR, MOUNTDRIVE (including create and read-only), SEEKFILE, INFODRIVE and READ_HEADER.
  - VERSION reports 2.16, so the utilities accept the card.
  - BOOTLOADER (key 15h 04h) reboots the Pico into its USB loader, so new firmware can be dropped on as a `.uf2` file.
  - IMAGE (`src/image.c`): read-only floppy images in DMK, JV3 and JV1 format, on up to 8 units, as FreHD does.
    - **Open:** subcommand 0 returns the highest track, single-sided and single-density flags, write-protected (always set) and the type (1 DMK, 2 JV3, 3 JV1).
    - **Read:** subcommand 1 returns one 256-byte sector. A sector number at or above the per-side count selects side 1.
    - **ERROR2:** 0 OK, 6 system or deleted data mark (F8/FA), 5 not found, 8 not an image, 24 file missing.
    - DMK images with mixed single and double density are handled, including single-density data stored byte-doubled. In JV3 images, free and 128-, 512- or 1024-byte sector slots are skipped correctly. Writing to floppy images is not supported, as on FreHD.
- **Boot loader stream (IN C4h):** if the card holds `FREHD.ROM` (the FreHD boot loader image, from the FreHD distribution), it is streamed on IN C4h. OUT C5h rewinds the stream and sets the byte returned at index 2, as on FreHD.
- **Time:** from a DS1307 with a backup cell. Without one, a software clock starts from the build date.

## How it runs

- **Core 1 (`bus.c`, running from RAM):** services every Z80 access.
  - The card's GAL pulls WAIT* low as soon as an IN or OUT to C0h–CFh starts.
  - Core 1 reads the address (and the data, for OUT), or drives the data for IN, then raises ACK. The GAL then releases WAIT*.
- **Core 0 (`main.c`):** mounts the card, runs queued disk work (`frehd_poll`), flushes images and drives the ACT LED.
  - While core 0 is busy, the Z80 sees BUSY in the status register, exactly as with FreHD.
- **Debug output:** printed on the Pico's USB serial port.
- **Pins:** see `src/board.h`.

## Building

On this PC, run:

```bash
powershell -ExecutionPolicy Bypass -File build.ps1
```

It uses a portable toolchain folder: Arm GNU Toolchain 15.3.rel2 in `armgcc`, CMake 4.4.2 in `cmake`, Ninja 1.13.2 in `ninja`, Pico SDK 2.3.1 with its pinned TinyUSB in `pico-sdk`, and picotool 2.3.1 in `picotool`. Nothing is installed system-wide. The script looks for that folder in this order: `-Tools <folder>`, the `PICO_TOOLS` environment variable, then `tools\pico` next to the repository (`..\tools\pico` from the repository root). The output is `build/frehd_pico.uf2`, about 64 KB of flash and 25 KB of RAM. To load it, hold BOOTSEL while plugging the Pico into USB, then copy the `.uf2` onto the drive that appears.

- **FatFs:** ChaN's FatFs R0.15 is included in `lib/fatfs` under its own permissive licence. CMake copies `src/ffconf.h` over its default configuration.
- **Warnings:** the project's own sources build with `-Wall -Wextra` and give no warnings.
- **Check:** the core 1 bus handlers (`bus_loop`, `frehd_in`, `frehd_out`, `frehd_bus_reset`) link into RAM at 0x2000xxxx.
- **On another machine:** install the Pico SDK and an Arm GCC toolchain, then run:
  ```bash
  cmake -S . -B build -DPICO_SDK_PATH=/path/to/pico-sdk
  ```
  ```bash
  cmake --build build
  ```
## Testing without hardware

`test/build_test.ps1` does two things, using MSVC (Visual Studio Build Tools) only:
- It builds `src/frehd.c` against a stdio-backed FatFs stand-in and runs `test_frehd.c`. That test plays the Z80 side of the protocol: image create and mount, sector write and read-back at the right file offsets, sparse reads, bad addresses, write protection, 512-byte sectors, the whole file and directory extension set, time, version, the bootloader key, the ROM stream, an ECB reset arriving mid-action (the stale result is dropped), and floppy images built inside the test: a double-sided DMK with mixed density, a JV3 with free, 128-byte and double-density entries, and a JV1. Result: 79 checks, all passing.
- It then syntax-checks the Pico-only sources against declaration stubs of the SDK.

**Not yet tested:**
- It has not been tried on hardware or with real FreHD drivers.
- Bus timing (`SETTLE_CYCLES` and `DRIVE_CYCLES` in `bus.c`) should be checked with a scope on the first board.

## SD card layout

```
/hard4-0      .HDV image for drive 0 (FreHD/xtrs format; create one with MOUNTDRIVE or the FreHD utilities)
/hard4-1..3   optional further drives
/FREHD.ROM    optional: FreHD boot loader image for IN C4h
/*.DMK, *.DSK optional: floppy images, opened by name through the IMAGE command (read-only)
```
