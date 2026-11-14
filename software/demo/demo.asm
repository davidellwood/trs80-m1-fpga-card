; ===========================================================================
; demo.asm - TRS-80 Model I FPGA card demo (/CMD, runs from DOS)
;
;   * six balls bounce around a frame using hardware velocities, the Z80
;     only flips a ball's velocity when it reaches an edge
;   * a ship flies an ellipse whose coordinates are computed every frame by
;     the Am9511: x = 56 + 40 cos(a), y = 19 + 12 sin(a)
;   * collisions between the ship and the balls show "HIT!"
;   Press BREAK to return to DOS.
;
;   sjasmplus demo.asm --raw=demo.bin   (then tools/bin2cmd.py -> DEMO/CMD)
; ===========================================================================
        DEVICE NONE
        ORG 6000h

DOS_EXIT        EQU 402Dh           ; TRSDOS / NEWDOS "DOS ready"
KBD_ROW6        EQU 3840h           ; ENTER CLEAR BREAK UP DOWN LEFT RIGHT SPACE
NBALLS          EQU 6

START:
        call CARD_DETECT
        jr nc,card_ok
        ld hl,msg_nocard
        ld de,CARD_VIDEO
.cp:    ld a,(hl)
        or a
        jp z,DOS_EXIT
        ld (de),a
        inc hl
        inc de
        jr .cp

card_ok:
        ld a,G_RESET
        call GFX_CMD
        call c,err_inc

        ; ---- background: blank, frame, title
        ld a,20h
        call BG_FILL
        call c,err_inc
        ld hl,blk_box
        call GFX_BLOCK
        call c,err_inc
        ld hl,msg_title
        ld b,17
        ld c,0
        call BG_PRINT
        call c,err_inc

        ; ---- shapes: 0 = ball (through the bulk area), 1 = ship (parameters)
        xor a
        ld b,8
        ld c,8
        ld hl,shape_ball
        call SHAPE_FROM
        call c,err_inc
        ld hl,blk_ship
        call GFX_BLOCK
        call c,err_inc

        ; ---- ship = sprite 0
        xor a
        ld b,1
        ld d,56
        ld e,19
        ld c,SF_VISIBLE
        call SPR_SET
        call c,err_inc

        ; ---- balls = sprites 1..6
        ld b,NBALLS
        ld hl,ball_init                 ; x, y per ball
        ld a,1
        ld (ix_n),a
ball_lp:
        push bc
        ld a,(ix_n)
        ld d,(hl)
        inc hl
        ld e,(hl)
        inc hl
        push hl
        ld b,0
        ld c,SF_VISIBLE
        call SPR_SET
        call c,err_inc
        ld a,(ix_n)
        call ball_vel_set
        pop hl
        ld a,(ix_n)
        inc a
        ld (ix_n),a
        pop bc
        djnz ball_lp

; ================================================================ main loop
main_lp:
        call ship_pos
        call FRAME_SHOW                 ; render + copy to the screen
        call c,err_inc
        ld hl,frames
        inc (hl)
        call bounce
        ; ship collisions
        xor a
        ld hl,cmask
        call SPR_COLLIDE
        call c,err_inc
        ld hl,msg_hit
        jr nz,.show
        ld hl,msg_nohit
.show:  ld b,2
        ld c,15
        call BG_PRINT
        call c,err_inc
        ld a,(KBD_ROW6)
        bit 2,a                         ; BREAK
        jr z,main_lp
        jp DOS_EXIT

; ------------------------------------------------- ship position via Am9511
ship_pos:
        ld hl,f_ang
        call APU_PUSH4                  ; a
        ld a,A_PTO
        call APU_CMD                    ; a a
        ld a,A_COS
        call APU_CMD                    ; cos(a) a
        ld hl,f_rx
        call APU_PUSH4
        ld a,A_FMUL
        call APU_CMD
        ld hl,f_cx
        call APU_PUSH4
        ld a,A_FADD
        call APU_CMD
        ld a,A_FIXS
        call APU_CMD                    ; x(int16) a
        call c,err_inc
        ld hl,ship_x
        call APU_POP2
        ld a,A_SIN
        call APU_CMD                    ; sin(a)
        ld hl,f_ry
        call APU_PUSH4
        ld a,A_FMUL
        call APU_CMD
        ld hl,f_cy
        call APU_PUSH4
        ld a,A_FADD
        call APU_CMD
        ld a,A_FIXS
        call APU_CMD
        call c,err_inc
        ld hl,ship_y
        call APU_POP2
        ; a = a + step
        ld hl,f_ang
        call APU_PUSH4
        ld hl,f_step
        call APU_PUSH4
        ld a,A_FADD
        call APU_CMD
        call c,err_inc
        ld hl,f_ang
        call APU_POP4
        ; move sprite 0
        xor a
        ld hl,ship_x
        ld d,(hl)
        ld hl,ship_y
        ld e,(hl)
        call SPR_MOVE
        call c,err_inc
        ret

; ---------------------------------------------- bounce balls off the frame
bounce:
        ld a,1
.lp:    ld (ix_n),a
        call SPR_GET                    ; D = x, E = y
        call c,err_inc
        ld a,d
        ld (bx),a
        ld a,e
        ld (by),a
        ld a,(ix_n)
        call vel_ptr                    ; HL -> vx, (HL+NBALLS) = vy
        ld c,0                          ; changed?
        ; x
        ld a,(bx)
        ld b,a
        ld a,(hl)
        bit 7,a
        jr nz,.xneg
        ld a,b
        cp 118
        jr c,.xok
        jr .xflip
.xneg:  ld a,b
        cp 3
        jr nc,.xok
.xflip: ld a,(hl)
        neg
        ld (hl),a
        inc c
.xok:   ld de,NBALLS                    ; y
        add hl,de
        ld a,(by)
        ld b,a
        ld a,(hl)
        bit 7,a
        jr nz,.yneg
        ld a,b
        cp 37
        jr c,.yok
        jr .yflip
.yneg:  ld a,b
        cp 5
        jr nc,.yok
.yflip: ld a,(hl)
        neg
        ld (hl),a
        inc c
.yok:   ld a,c
        or a
        ld a,(ix_n)
        call nz,ball_vel_set
        ld a,(ix_n)
        inc a
        cp NBALLS+1
        jr c,.lp
        ret

; ball_vel_set - A = ball sprite number: send its vx/vy to the engine
ball_vel_set:
        push af
        call vel_ptr
        ld d,(hl)
        push de
        ld de,NBALLS
        add hl,de
        pop de
        ld e,(hl)
        pop af
        call SPR_VEL
        call c,err_inc
        ret

; vel_ptr - A = ball (1..6) -> HL = &vx[A-1]
vel_ptr:
        dec a
        ld hl,vel_x
        add a,l
        ld l,a
        ld a,h
        adc a,0
        ld h,a
        ret

err_inc:
        push hl
        ld hl,errors
        inc (hl)
        pop hl
        ret

; ================================================================== data
msg_nocard: DB "FPGA CARD NOT FOUND", 0
msg_title:  DB " TRS-80 FPGA CARD ", 0
msg_hit:    DB "HIT!", 0
msg_nohit:  DB "    ", 0

blk_box:    DB G_BG_BOX, 6, 0, 3, 128, 42, 1, 0
blk_ship:   DB G_SHAPE_DEF, 15, 1, 10, 6
            DB 0Ch,00h, 1Eh,00h, 3Fh,00h, 7Fh,80h, 0FFh,0C0h, 0CCh,0C0h
shape_ball: DB 3Ch,0, 7Eh,0, 0FFh,0, 0FFh,0, 0FFh,0, 0FFh,0, 7Eh,0, 3Ch,0

ball_init:  DB 10,6, 30,20, 50,10, 70,30, 90,8, 110,25
vel_x:      DB 1, -1, 2, -2, 1, -1
vel_y:      DB 1, 1, -1, -1, 2, -1

; Am9511 floats (m0 m1 m2 s|e): angle, step 0.08, radii 40/12, centre 56/19
f_ang:      DB 00h, 00h, 00h, 00h
f_step:     DB 0Ah, 0D7h, 0A3h, 7Dh
f_rx:       DB 00h, 00h, 0A0h, 06h
f_ry:       DB 00h, 00h, 0C0h, 04h
f_cx:       DB 00h, 00h, 0E0h, 06h
f_cy:       DB 00h, 00h, 98h, 05h

ship_x:     DW 0
ship_y:     DW 0
ix_n:       DB 0
bx:         DB 0
by:         DB 0
frames:     DB 0
errors:     DB 0
cmask:      DS 4

        INCLUDE "../lib/trs80card.asm"
END_OF_PROGRAM:
