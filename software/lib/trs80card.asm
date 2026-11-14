; ===========================================================================
; trs80card.asm - Z80 library for the TRS-80 Model I FPGA card
; (sprite engine on ports 52h/53h, Am9511 APU on 50h/51h, dual-port RAM at
; 3000h-37DFh). sjasmplus syntax; INCLUDE it into your program.
;
; Conventions
;   * Routines return CF=1 on error (engine ERR / APU error / timeout);
;     A usually holds the status byte.
;   * Registers not listed under "out" or "destroys" are preserved.
;   * No ROM calls, no interrupts used; safe under Level II BASIC or DOS.
;
; If you moved the card to the alternate ports with JP4, change the four
; port EQUs (70h-73h).
; ===========================================================================

CARD_APU_DATA   EQU 50h
CARD_APU_CMD    EQU 51h
CARD_GFX_PARAM  EQU 52h
CARD_GFX_CMD    EQU 53h

CARD_FB         EQU 3000h          ; 1 KB frame buffer (sprite engine output)
CARD_BULK       EQU 3400h          ; bulk area (DPRAM offset 400h), 992 bytes
CARD_VIDEO      EQU 3C00h          ; Model I video RAM

; ---- sprite engine commands (docs/sprite-engine.md)
G_NOP           EQU 00h
G_RESET         EQU 01h
G_VERSION       EQU 02h
G_BG_FILL       EQU 08h
G_BG_LOAD       EQU 09h
G_BG_PUTC       EQU 0Ah
G_BG_PLOT       EQU 0Bh
G_BG_LINE       EQU 0Ch
G_BG_BOX        EQU 0Dh
G_BG_SCROLL     EQU 0Eh
G_SHAPE_DEF     EQU 10h
G_SHAPE_LOAD    EQU 11h
G_SPR_SET       EQU 20h
G_SPR_MOVE      EQU 21h
G_SPR_FLAGS     EQU 22h
G_SPR_SHAPE     EQU 23h
G_SPR_VEL       EQU 24h
G_SPR_GET       EQU 25h
G_COLLIDE       EQU 30h
G_RENDER        EQU 40h
G_RENDER_AUTO   EQU 41h

; sprite flags
SF_VISIBLE      EQU 01h
SF_XOR          EQU 02h
SF_MIRROR_X     EQU 04h
SF_MIRROR_Y     EQU 08h
SF_OPAQUE       EQU 10h
SF_NOCOLLIDE    EQU 20h

; engine status bits
GS_BUSY         EQU 7
GS_FRAME        EQU 6
GS_ERR          EQU 5
GS_HIT          EQU 4
GS_RDY          EQU 0

; ---- Am9511 commands (add A_SINGLE / A_DOUBLE for integer forms)
A_SINGLE        EQU 60h
A_DOUBLE        EQU 20h
A_SR            EQU 80h
A_NOP           EQU 00h
A_SQRT          EQU 01h
A_SIN           EQU 02h
A_COS           EQU 03h
A_TAN           EQU 04h
A_ASIN          EQU 05h
A_ACOS          EQU 06h
A_ATAN          EQU 07h
A_LOG           EQU 08h
A_LN            EQU 09h
A_EXP           EQU 0Ah
A_PWR           EQU 0Bh
A_ADD           EQU 0Ch
A_SUB           EQU 0Dh
A_MUL           EQU 0Eh
A_DIV           EQU 0Fh
A_FADD          EQU 10h
A_FSUB          EQU 11h
A_FMUL          EQU 12h
A_FDIV          EQU 13h
A_CHS           EQU 14h
A_CHSF          EQU 15h
A_MUU           EQU 16h
A_PTO           EQU 17h
A_POP           EQU 18h
A_XCH           EQU 19h
A_PUPI          EQU 1Ah
A_FLTD          EQU 1Ch
A_FLTS          EQU 1Dh
A_FIXD          EQU 1Eh
A_FIXS          EQU 1Fh

; ===========================================================================
; Sprite engine - low level
; ===========================================================================

; GFX_WAIT - wait until the engine is not BUSY (timeout ~1.5 s)
;   out: A = status, CF = 1 if ERR set or timeout
GFX_WAIT:
        push bc
        ld bc,0
.poll:  in a,(CARD_GFX_CMD)
        bit GS_BUSY,a
        jr z,.done
        dec bc
        ld a,b
        or c
        jr nz,.poll
        pop bc
        scf
        ret
.done:  pop bc
        bit GS_ERR,a
        scf
        ret nz
        ccf
        ret

; GFX_CMD - issue command A, wait for completion
;   out: A = status, CF = 1 on error
GFX_CMD:
        out (CARD_GFX_CMD),a
        jr GFX_WAIT

; GFX_BLOCK - send a parameter block and run it
;   in:  HL -> [command, count, param1 ... paramN]
;   out: A = status, CF = 1 on error, HL -> byte after the block
GFX_BLOCK:
        push bc
        ld c,(hl)
        inc hl
        ld b,(hl)
        inc hl
        ld a,b
        or a
        jr z,.go
.par:   ld a,(hl)
        out (CARD_GFX_PARAM),a
        inc hl
        djnz .par
.go:    ld a,c
        pop bc
        jr GFX_CMD

; CARD_DETECT - is the card there?
;   out: CF = 1 if not found; else A = sprite engine minor version
;   destroys: B
CARD_DETECT:
        in a,(CARD_GFX_CMD)
        and 0Eh                    ; bits 3..1 always read 0 on the card,
        jr nz,.none                ; an empty bus reads FFh
        ld a,G_VERSION
        call GFX_CMD
        jr c,.none
        in a,(CARD_GFX_PARAM)      ; major (0)
        or a
        jr nz,.none
        in a,(CARD_GFX_PARAM)      ; minor
        ld b,a
        in a,(CARD_GFX_PARAM)      ; sprites
        in a,(CARD_GFX_PARAM)      ; shapes
        ld a,b
        or a                       ; CF = 0
        ret
.none:  scf
        ret

; ===========================================================================
; Sprite engine - commands (all: out A = status, CF = 1 on error)
; ===========================================================================

; SPR_SET - A = sprite, B = shape, D = x, E = y, C = flags
SPR_SET:
        out (CARD_GFX_PARAM),a
        ld a,b
        out (CARD_GFX_PARAM),a
        ld a,d
        out (CARD_GFX_PARAM),a
        ld a,e
        out (CARD_GFX_PARAM),a
        ld a,c
        out (CARD_GFX_PARAM),a
        ld a,G_SPR_SET
        jr GFX_CMD

; SPR_MOVE - A = sprite, D = x, E = y
SPR_MOVE:
        out (CARD_GFX_PARAM),a
        ld a,d
        out (CARD_GFX_PARAM),a
        ld a,e
        out (CARD_GFX_PARAM),a
        ld a,G_SPR_MOVE
        jr GFX_CMD

; SPR_VEL - A = sprite, D = dx, E = dy (signed, applied on every RENDER)
SPR_VEL:
        out (CARD_GFX_PARAM),a
        ld a,d
        out (CARD_GFX_PARAM),a
        ld a,e
        out (CARD_GFX_PARAM),a
        ld a,G_SPR_VEL
        jr GFX_CMD

; SPR_FLAGS - A = sprite, C = flags
SPR_FLAGS:
        out (CARD_GFX_PARAM),a
        ld a,c
        out (CARD_GFX_PARAM),a
        ld a,G_SPR_FLAGS
        jp GFX_CMD

; SPR_SHAPE - A = sprite, B = shape
SPR_SHAPE:
        out (CARD_GFX_PARAM),a
        ld a,b
        out (CARD_GFX_PARAM),a
        ld a,G_SPR_SHAPE
        jp GFX_CMD

; SPR_GET - A = sprite;  out: D = x, E = y
SPR_GET:
        out (CARD_GFX_PARAM),a
        ld a,G_SPR_GET
        call GFX_CMD
        ret c
        in a,(CARD_GFX_PARAM)
        ld d,a
        in a,(CARD_GFX_PARAM)
        ld e,a
        or a
        ret

; SPR_COLLIDE - A = sprite, HL -> 4-byte buffer for the mask (sprites 0-7 first)
;   out: A = OR of the mask bytes (Z = no collision), CF = 1 on error
;   destroys: B, C
SPR_COLLIDE:
        out (CARD_GFX_PARAM),a
        ld a,G_COLLIDE
        call GFX_CMD
        ret c
        push hl
        ld b,4
        ld c,0                      ; note: destroys C
.rd:    in a,(CARD_GFX_PARAM)
        ld (hl),a
        or c
        ld c,a
        inc hl
        djnz .rd
        pop hl
        ld a,c
        or a
        ret

; BG_FILL - A = character for the whole background
BG_FILL:
        out (CARD_GFX_PARAM),a
        ld a,G_BG_FILL
        jp GFX_CMD

; BG_PUTC - B = column (0-63), C = row (0-15), A = character
BG_PUTC:
        push af
        ld a,b
        out (CARD_GFX_PARAM),a
        ld a,c
        out (CARD_GFX_PARAM),a
        pop af
        out (CARD_GFX_PARAM),a
        ld a,G_BG_PUTC
        jp GFX_CMD

; BG_PRINT - print zero-terminated text at B = column, C = row
;   in:  HL -> text;  out: HL -> after the 0, B = next column
BG_PRINT:
.nx:    ld a,(hl)
        inc hl
        or a
        ret z
        ld a,b
        cp 64
        jr nc,.skip                 ; clip at the right edge
        dec hl
        ld a,(hl)
        inc hl
        call BG_PUTC
        ret c
.skip:  inc b
        jr .nx

; BG_PLOT - D = x (0-127), E = y (0-47), A = mode (0 clear, 1 set, 2 xor)
BG_PLOT:
        push af
        ld a,d
        out (CARD_GFX_PARAM),a
        ld a,e
        out (CARD_GFX_PARAM),a
        pop af
        out (CARD_GFX_PARAM),a
        ld a,G_BG_PLOT
        jp GFX_CMD

; BG_SCROLL - D = dx, E = dy (signed character cells)
BG_SCROLL:
        ld a,d
        out (CARD_GFX_PARAM),a
        ld a,e
        out (CARD_GFX_PARAM),a
        ld a,G_BG_SCROLL
        jp GFX_CMD

; BG_FROM - load the background from 1024 bytes of Z80 memory
;   in: HL -> 64x16 screen image.  Uses the frame buffer area as transfer space.
;   destroys: BC, DE, HL
BG_FROM:
        ld de,CARD_FB
        ld bc,1024
        ldir
        xor a                       ; DPRAM offset 000h
        out (CARD_GFX_PARAM),a
        out (CARD_GFX_PARAM),a
        ld a,G_BG_LOAD
        jp GFX_CMD

; SHAPE_FROM - define shape A (w = B, h = C) from rows in Z80 memory
;   in: HL -> h rows of 2 bytes (left 8 pixels first, MSB = leftmost)
;   Copies through the bulk area (fast for large shapes).  destroys: DE, HL
SHAPE_FROM:
        push bc
        push af
        ld de,CARD_BULK
        ld a,c
        add a,a                     ; 2 * h bytes
        ld c,a
        ld b,0
        ldir
        pop af
        pop bc
        out (CARD_GFX_PARAM),a      ; id
        ld a,b
        out (CARD_GFX_PARAM),a      ; w
        ld a,c
        out (CARD_GFX_PARAM),a      ; h
        xor a
        out (CARD_GFX_PARAM),a      ; offset low  (400h = CARD_BULK)
        ld a,04h
        out (CARD_GFX_PARAM),a      ; offset high
        ld a,G_SHAPE_LOAD
        jp GFX_CMD

; FRAME_SHOW - RENDER, wait for it, copy the frame to the screen (~12 ms)
;   out: A = status, CF = 1 on error.  destroys: BC, DE, HL
FRAME_SHOW:
        ld a,G_RENDER
        call GFX_CMD
        ret c
        ; fall through
; FRAME_COPY - copy the frame buffer to video RAM (use after RENDER_AUTO
;   when FRAME is set).  destroys: BC, DE, HL
FRAME_COPY:
        ld hl,CARD_FB
        ld de,CARD_VIDEO
        ld bc,1024
        ldir
        in a,(CARD_GFX_CMD)
        or a                        ; CF = 0
        ret

; ===========================================================================
; Am9511 APU
; ===========================================================================

; APU_WAIT - wait until not BUSY;  out: A = status, CF = 1 on error/timeout
APU_WAIT:
        push bc
        ld bc,0
.poll:  in a,(CARD_APU_CMD)
        bit 7,a
        jr z,.done
        dec bc
        ld a,b
        or c
        jr nz,.poll
        pop bc
        scf
        ret
.done:  pop bc
        push af
        and 1Eh                     ; error field
        jr z,.ok
        pop af
        scf
        ret
.ok:    pop af
        or a                        ; CF = 0
        ret

; APU_CMD - run APU command A;  out: A = status, CF = 1 on error
APU_CMD:
        out (CARD_APU_CMD),a
        jr APU_WAIT

; APU_PUSH4 / APU_PUSH2 - push 4 / 2 bytes from (HL), least significant first
;   out: HL advanced.  destroys: A, B
APU_PUSH4:
        ld b,4
        jr APU_PUSHN
APU_PUSH2:
        ld b,2
APU_PUSHN:
        ld a,(hl)
        out (CARD_APU_DATA),a
        inc hl
        djnz APU_PUSHN
        ret

; APU_POP4 - pop a 32-bit value to (HL)..(HL+3) (stored least significant first)
;   destroys: A, B
APU_POP4:
        push hl
        inc hl
        inc hl
        inc hl
        ld b,4
.rd:    in a,(CARD_APU_DATA)
        ld (hl),a
        dec hl
        djnz .rd
        pop hl
        ret

; APU_POP2 - pop a 16-bit value to (HL),(HL+1).  destroys: A
APU_POP2:
        inc hl
        in a,(CARD_APU_DATA)
        ld (hl),a
        dec hl
        in a,(CARD_APU_DATA)
        ld (hl),a
        ret

; ---------------------------------------------------------------------------
; Level II BASIC single precision <-> Am9511 float, in place at (HL).
; BASIC: m0 m1 (s|m2) exp, value 0.1m x 2^(exp-128), exp 0 = zero.
; Am9511: m0 m1 (1|m2) (s|E7), value 0.1m x 2^E, E = -64..63.
; ---------------------------------------------------------------------------

; MBF_TO_AM - out: CF = 1 if the exponent is outside the Am9511 range
;   destroys: A, B, C
MBF_TO_AM:
        push hl
        inc hl
        inc hl
        ld c,(hl)                   ; s|m2
        inc hl
        ld a,(hl)                   ; exp
        or a
        jr z,.zero
        sub 128                     ; E
        ld b,a
        add a,64
        bit 7,a                     ; E+64 must be 0..127
        jr nz,.range
        ld a,b
        and 7Fh
        ld b,a
        ld a,c
        and 80h
        or b
        ld (hl),a                   ; s|E7
        dec hl
        ld a,c
        or 80h
        ld (hl),a                   ; 1|m2
        pop hl
        or a
        ret
.zero:  xor a
        ld (hl),a
        dec hl
        ld (hl),a
        dec hl
        ld (hl),a
        dec hl
        ld (hl),a
        pop hl
        ret
.range: pop hl
        scf
        ret

; AM_TO_MBF - destroys: A, B, C
AM_TO_MBF:
        push hl
        inc hl
        inc hl
        ld a,(hl)                   ; 1|m2
        bit 7,a
        jr z,.zero
        ld c,a
        inc hl
        ld a,(hl)                   ; s|E7
        ld b,a
        and 7Fh
        bit 6,a
        jr z,.pos
        or 80h                      ; sign-extend E
.pos:   add a,128
        ld (hl),a                   ; exp = E + 128
        dec hl
        ld a,b
        and 80h
        ld b,a
        ld a,c
        and 7Fh
        or b
        ld (hl),a                   ; s|m2
        pop hl
        or a
        ret
.zero:  xor a
        inc hl
        ld (hl),a
        dec hl
        ld (hl),a
        dec hl
        ld (hl),a
        dec hl
        ld (hl),a
        pop hl
        ret

; FP1 - BASIC variable at (HL) = f(itself); C = APU float command (A_SIN ...)
;   out: A = APU status, CF = 1 on error (variable unchanged)
;   destroys: B, C, DE
FP1:
        ld a,c
        ld (fp_cmd),a
        push hl
        ld de,fp_t1
        ld bc,4
        ldir
        ld hl,fp_t1
        call MBF_TO_AM
        jr c,fp_rng
        call APU_PUSH4
        jr fp_run

; FP2 - (HL) = (DE) op (HL) on BASIC variables; C = APU command (A_FADD,
;   A_FSUB = (DE)-(HL), A_FMUL, A_FDIV = (DE)/(HL), A_PWR = (DE)^(HL))
;   out: A = APU status, CF = 1 on error (variable unchanged)
;   destroys: B, C, DE
FP2:
        ld a,c
        ld (fp_cmd),a
        push hl
        ex de,hl                    ; first operand (NOS) from (DE)
        ld de,fp_t1
        ld bc,4
        ldir
        pop hl
        push hl
        ld de,fp_t2
        ld bc,4
        ldir
        ld hl,fp_t1
        call MBF_TO_AM
        jr c,fp_rng
        ld hl,fp_t2
        call MBF_TO_AM
        jr c,fp_rng
        ld hl,fp_t1
        call APU_PUSH4              ; NOS
        call APU_PUSH4              ; TOS (fp_t2 follows fp_t1)
fp_run:
        ld a,(fp_cmd)
        call APU_CMD
        jr c,fp_err
        ld (fp_st),a
        ld hl,fp_t1
        call APU_POP4
        call AM_TO_MBF
        pop de                      ; destination
        ld bc,4
        ldir
        ex de,hl
        ld bc,-4
        add hl,bc                   ; HL = destination again
        ld a,(fp_st)
        or a                        ; CF = 0
        ret
fp_err:                             ; leave the operands on the APU stack;
        pop hl                      ; a following APU command reuses it
        ret
fp_rng: pop hl
        ld a,0FFh
        scf
        ret

fp_cmd: DB 0
fp_st:  DB 0
fp_t1:  DS 4
fp_t2:  DS 4
