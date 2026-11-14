; ===========================================================================
; cardusr.asm - USR() module for Level II BASIC (16K or more)
;
; Lives at 7D00h-7FFFh: answer MEMORY SIZE? with 32000. demo.bas POKEs it
; in from DATA lines and sets the USR vector (16526/16527) to 7D00h.
;
;   R = USR(0)   RENDER, wait, copy the frame to the screen      R = status
;   R = USR(1)   copy the frame buffer only (after RENDER_AUTO)   R = status
;   R = USR(2)   single-precision variable at CTL_A = f(itself),
;                f = Am9511 command at CTL_CMD (2 = SIN, 1 = SQRT ...)
;   R = USR(3)   variable at CTL_A = (variable at CTL_B) op (variable at CTL_A)
;                (16 FADD, 17 FSUB, 18 FMUL, 19 FDIV, 11 PWR = B^A)
;   R >= 256 means an error (R - 256 = status, 511 = number out of range).
;
;   Control block (POKE from BASIC, addresses from V = VARPTR(variable)):
;     32003 CTL_CMD   32004/32005 CTL_A low/high   32006/32007 CTL_B low/high
; ===========================================================================
        DEVICE NONE
        ORG 7D00h

ROM_GETARG      EQU 0A7Fh           ; USR argument -> HL
ROM_RETINT      EQU 0A9Ah           ; return HL to BASIC as an integer

        jp usr_entry
CTL_CMD:  DB 0                      ; 7D03h
CTL_A:    DW 0                      ; 7D04h
CTL_B:    DW 0                      ; 7D06h

usr_entry:
        call ROM_GETARG
        ld a,l
        or a
        jr z,.show
        dec a
        jr z,.copy
        dec a
        jr z,.fp1
        dec a
        jr z,.fp2
        ld hl,-1
        jp ROM_RETINT
.show:  call FRAME_SHOW
        jr .ret
.copy:  call FRAME_COPY
        jr .ret
.fp1:   ld hl,(CTL_A)
        ld a,(CTL_CMD)
        ld c,a
        call FP1
        jr .ret
.fp2:   ld hl,(CTL_A)
        ld de,(CTL_B)
        ld a,(CTL_CMD)
        ld c,a
        call FP2
.ret:   ld l,a
        ld h,0
        jr nc,.out
        inc h                       ; error: 256 + status
.out:   jp ROM_RETINT

        INCLUDE "../lib/trs80card.asm"
USR_END:
        ASSERT USR_END <= 8000h
