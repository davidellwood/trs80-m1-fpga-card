# Sprite Engine — Port Command Protocol (0.2, implemented)

> Implemented in `fpga/src/sprite_engine.v` and checked against the reference model `fpga/sim/sprite_model.py`. The model is the precise definition of the rules below. The parameter FIFO is 64 bytes deep, so a full 16×15 SHAPE_DEF (33 bytes) fits.
>
> **Drawing rules, in detail:**
> - **Background drawing** (BG_PLOT, BG_LINE, BG_BOX) always produces a graphics cell. A text cell under a plotted pixel becomes a graphics cell that starts empty.
> - **Sprites** never change text cells, unless the sprite is OPAQUE.
> - **Collisions** are tested on the sprites' own pixels, even where they cross text.
> - **COLLIDE** returns its mask with byte 0 first, holding sprites 0–7.

The FPGA implements a sprite and graphics engine. The Z80 drives it entirely through two I/O ports, and the engine writes each finished frame into the **frame buffer** (dual-port RAM 0x3000–0x33FF). The Z80 then copies that to video RAM with one `LDIR`.

This draft fixes the port interface, so the hardware, the HDL and a Z80 command library can be built against it. Command codes and limits can change until the HDL is written.

## Ports

| Port | OUT | IN |
|---|---|---|
| 0x52 (0x72 with JP4) | **PARAM**: push a parameter byte into the engine's FIFO (64 deep) | **RESULT**: pop a result byte |
| 0x53 (0x73 with JP4) | **CMD**: execute a command using the parameters pushed so far | **STATUS** |

To issue a command, push its parameters to PARAM in the listed order, then write the command code to CMD. Writing CMD always empties the parameter FIFO. Too few parameters sets ERR, and extra parameters are ignored.

### STATUS register (IN 0x53)

| Bit | Name | Meaning |
|---|---|---|
| 7 | BUSY | A command is still executing. Wait for it to clear before the next CMD (parameters may be pushed while BUSY) |
| 6 | FRAME | The last `RENDER` has finished writing the frame buffer, so it is safe to `LDIR` now. Cleared by the next `RENDER` |
| 5 | ERR | The last command was rejected (bad id, too few parameters). Cleared by the next CMD |
| 4 | HIT | At least one sprite collision was found in the last `RENDER` |
| 0 | RDY | RESULT has at least one byte to read |

## Screen model

The Model I screen is 64×16 characters. Character codes 0x80–0xBF are 2×3 block graphics, which gives **128×48 pixels**. Each character cell covers a 2-pixel by 3-pixel block of pixels. Within a cell, the bits are laid out like this, with bit 0 at the top left and bit 5 at the bottom right:

```
 bit0 bit1      code = 0x80 + bits
 bit2 bit3
 bit4 bit5
```

The engine keeps three things in FPGA block RAM:
- **Background:** a 64×16 character map. It can hold text or graphics characters, so text and sprites mix.
- **Shapes:** sprite bitmaps.
- **Sprite table.**

On each `RENDER`, the engine starts from the background, ORs or XORs every visible sprite's pixels into the graphics cells they overlap, and writes the resulting 1024 bytes into the frame buffer.

A sprite only modifies cells that are already graphics characters, or blanks (0x20). Text characters under a sprite are left alone, unless the sprite has the OPAQUE flag, which converts the cell to graphics.

**Limits (draft):** 32 sprites and 64 shapes. A shape is at most 16×15 pixels, stored as 2 bytes per row, MSB = leftmost pixel. Sprite coordinates are signed 8-bit, so a sprite can be partly off-screen.

## Commands

| Code | Name | Parameters (PARAM, in order) | Results |
|---|---|---|---|
| 0x00 | NOP | — | — |
| 0x01 | RESET | — | Clears all sprites, shapes and the background |
| 0x02 | VERSION | — | 4 bytes: major, minor, sprites, shapes (currently 0, 2, 32, 64) |
| 0x08 | BG_FILL | char | — |
| 0x09 | BG_LOAD | src_lo, src_hi (DPRAM offset 0x000–0x7FF) | Copies 1024 bytes from DPRAM into the background |
| 0x0A | BG_PUTC | col, row, char | — |
| 0x0B | BG_PLOT | x, y, mode (0 clear, 1 set, 2 xor) | — |
| 0x0C | BG_LINE | x0, y0, x1, y1, mode | — |
| 0x0D | BG_BOX | x, y, w, h, mode, fill (0/1) | — |
| 0x0E | BG_SCROLL | dx, dy (signed characters; vacated cells = 0x20) | — |
| 0x10 | SHAPE_DEF | id, w, h, then h×2 bitmap bytes | — |
| 0x11 | SHAPE_LOAD | id, w, h, src_lo, src_hi | Reads the bitmap from DPRAM, for bulk loads at `LDIR` speed |
| 0x20 | SPR_SET | n, shape, x, y, flags | — |
| 0x21 | SPR_MOVE | n, x, y | — |
| 0x22 | SPR_FLAGS | n, flags | — |
| 0x23 | SPR_SHAPE | n, shape (for animation frames) | — |
| 0x24 | SPR_VEL | n, dx, dy (applied automatically on every RENDER) | — |
| 0x25 | SPR_GET | n | 2 bytes: x, y |
| 0x30 | COLLIDE | n | 4 bytes: bit mask of the sprites that n touched in the last RENDER |
| 0x40 | RENDER | — | Composes the frame and copies it to 0x3000–0x33FF, then sets FRAME |
| 0x41 | RENDER_AUTO | rate (0 = off, else every *rate* × 16.7 ms) | Free-running RENDERs; the Z80 still checks FRAME before each LDIR |

**Sprite flags:**

| Bit | Name | Effect |
|---|---|---|
| 0 | VISIBLE | Sprite is drawn |
| 1 | XOR | Pixels are XORed instead of ORed |
| 2 | MIRROR_X | Shape is flipped left to right |
| 3 | MIRROR_Y | Shape is flipped top to bottom |
| 4 | OPAQUE | Clears the sprite's bounding box before drawing, so it hides what is behind it |
| 5 | NOCOLLIDE | Sprite is skipped in collision tests |

## Example: move a sprite and show the frame

```z80
PARAM   EQU 52H
CMD     EQU 53H

        LD   A,3        ; sprite 3
        OUT  (PARAM),A
        LD   A,(XPOS)
        OUT  (PARAM),A
        LD   A,(YPOS)
        OUT  (PARAM),A
        LD   A,21H      ; SPR_MOVE
        OUT  (CMD),A
        LD   A,40H      ; RENDER
        OUT  (CMD),A
WAITF:  IN   A,(CMD)
        BIT  6,A        ; FRAME?
        JR   Z,WAITF
        LD   HL,3000H   ; frame buffer (dual-port RAM)
        LD   DE,3C00H   ; video RAM
        LD   BC,0400H
        LDIR            ; about 12 ms at 1.774 MHz
```

Rendering happens in the FPGA's own block RAM. The dual-port frame buffer is written only at the end of a RENDER, so frames never tear as long as the Z80 does not start a new RENDER in the middle of an `LDIR`.

## Still to decide (software phase)

- Command library packaging: Z80 assembler include file, BASIC `USR` routines, or both.
- Whether RENDER should also raise INT* (JP2) when FRAME sets.
- Larger sprites and tile-map backgrounds that scroll at pixel resolution.
- How the Am9511 and the sprite engine share the FPGA: they are independent blocks behind the same port decoder, so no conflict is expected.
