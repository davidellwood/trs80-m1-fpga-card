; ===========================================================================
; libtest.asm - exercises every library routine; run by tools/test_lib.py
; in the Z80 emulator against the card models. The harness fills the input
; tables (n_mbf/mbf_in, n_fp/fp_tab) before running and checks the outputs.
; ===========================================================================
        DEVICE NONE
        ORG 6000h

START:
        ld sp,7F00h
        ; ---- T1: card detection
        call CARD_DETECT
        ld (r_det),a
        ld a,0
        rla
        ld (r_detcf),a
        ld a,(only_detect)
        or a
        jr z,t2
        halt

        ; ---- T2: BASIC <-> Am9511 float conversion
t2:     ld a,(n_mbf)
        ld (cnt),a
        or a
        jr z,t3
        ld hl,mbf_in
        ld (p_in),hl
        ld hl,am_out
        ld (p_am),hl
        ld hl,back_out
        ld (p_bk),hl
        ld hl,cf_out
        ld (p_cf),hl
.lp:    ld hl,(p_in)
        ld de,wk
        ld bc,4
        ldir
        ld (p_in),hl
        ld hl,wk
        call MBF_TO_AM
        ld a,0
        rla
        ld hl,(p_cf)
        ld (hl),a
        inc hl
        ld (p_cf),hl
        ld hl,wk
        ld de,(p_am)
        ld bc,4
        ldir
        ld (p_am),de
        ld hl,wk
        call AM_TO_MBF
        ld hl,wk
        ld de,(p_bk)
        ld bc,4
        ldir
        ld (p_bk),de
        ld hl,cnt
        dec (hl)
        jr nz,.lp

        ; ---- T3: FP1 / FP2 on BASIC-format variables
t3:     ld a,(n_fp)
        ld (cnt),a
        or a
        jr z,t4
        ld hl,fp_tab
        ld (p_in),hl
        ld hl,fp_out
        ld (p_am),hl
.lp:    ld hl,(p_in)
        ld a,(hl)
        ld (fcmd),a
        inc hl
        ld a,(hl)
        ld (ftype),a
        inc hl
        ld de,va
        ld bc,4
        ldir
        ld de,vb
        ld bc,4
        ldir
        ld (p_in),hl
        ld a,(fcmd)
        ld c,a
        ld a,(ftype)
        cp 1
        jr nz,.bin
        ld hl,va
        call FP1
        jr .st
.bin:   ld hl,va
        ld de,vb
        call FP2
.st:    ld (fst),a
        ld a,0
        rla
        ld (fcf),a
        ld hl,va
        ld de,(p_am)
        ld bc,4
        ldir
        ex de,hl
        ld a,(fst)
        ld (hl),a
        inc hl
        ld a,(fcf)
        ld (hl),a
        inc hl
        ld (p_am),hl
        ld hl,cnt
        dec (hl)
        jr nz,.lp

        ; ---- T4: sprite engine routines
t4:     ld a,G_RESET
        call GFX_CMD
        ld a,'.'
        call BG_FILL
        ld hl,txt
        ld b,10
        ld c,2
        call BG_PRINT
        ld hl,txt2                      ; clipped at column 64
        ld b,60
        ld c,4
        call BG_PRINT
        ld d,5
        ld e,40
        ld a,1
        call BG_PLOT
        ld hl,blkbox
        call GFX_BLOCK
        ld a,3
        ld b,3
        ld c,3
        ld hl,shp3
        call SHAPE_FROM
        xor a
        ld b,3
        ld d,20
        ld e,10
        ld c,SF_VISIBLE
        call SPR_SET
        ld a,1
        ld b,3
        ld d,21
        ld e,11
        ld c,SF_VISIBLE | SF_XOR
        call SPR_SET
        ld a,1
        ld d,1
        ld e,0FFh
        call SPR_VEL
        ld a,2
        ld b,3
        call SPR_SHAPE
        ld a,2
        ld c,SF_VISIBLE | SF_MIRROR_X
        call SPR_FLAGS
        ld a,2
        ld d,100
        ld e,30
        call SPR_MOVE
        call FRAME_SHOW
        ld (r_show),a
        ld a,1
        call SPR_GET
        ld a,d
        ld (r_gx),a
        ld a,e
        ld (r_gy),a
        xor a
        ld hl,r_mask
        call SPR_COLLIDE
        ld (r_any),a
        ld d,2
        ld e,1
        call BG_SCROLL
        ld a,40                         ; bad sprite number -> CF = 1
        ld b,0
        ld d,0
        ld e,0
        ld c,1
        call SPR_SET
        ld a,0
        rla
        ld (r_errcf),a
        ; frame 1 copy for the harness, then a background loaded from memory
        ld hl,CARD_VIDEO
        ld de,vid1
        ld bc,1024
        ldir
        ld hl,img
        ld b,0                          ; build a 1 KB pattern
        ld de,1024
.fill:  ld a,e
        and 3Fh
        or 80h
        ld (hl),a
        inc hl
        dec de
        ld a,d
        or e
        jr nz,.fill
        ld hl,img
        call BG_FROM
        ld a,0
        rla
        ld (r_bgcf),a
        call FRAME_SHOW
        halt

; ---------------------------------------------------------------- data
txt:    DB "LIB TEST", 0
txt2:   DB "CLIPPED", 0
blkbox: DB G_BG_BOX, 6, 40, 20, 30, 10, 2, 0
shp3:   DB 0E0h,0, 0A0h,0, 0E0h,0

only_detect: DB 0
r_det:   DB 0
r_detcf: DB 0
r_show:  DB 0
r_gx:    DB 0
r_gy:    DB 0
r_any:   DB 0
r_mask:  DS 4
r_errcf: DB 0
r_bgcf:  DB 0
cnt:     DB 0
fcmd:    DB 0
ftype:   DB 0
fst:     DB 0
fcf:     DB 0
p_in:    DW 0
p_am:    DW 0
p_bk:    DW 0
p_cf:    DW 0
wk:      DS 4
va:      DS 4
vb:      DS 4

n_mbf:    DB 0
mbf_in:   DS 4*32
am_out:   DS 4*32
back_out: DS 4*32
cf_out:   DS 32
n_fp:     DB 0
fp_tab:   DS 10*24
fp_out:   DS 6*24

        INCLUDE "../lib/trs80card.asm"

vid1:   DS 1024
img:    DS 1024
