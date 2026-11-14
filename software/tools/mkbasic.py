#!/usr/bin/env python3
"""
Build basic/demo.bas: a Level II BASIC demo that POKEs the USR module
(build/cardusr.bin, ORG 7D00h) from DATA lines and then drives the sprite
engine with OUT/INP and the Am9511 through USR().

  python mkbasic.py ../build/cardusr.bin ../basic/demo.bas
"""
import sys

PROGRAM = r"""10 CLS:PRINT "TRS-80 FPGA CARD - BASIC DEMO"
20 IF PEEK(16561)+256*PEEK(16562)>31999 THEN PRINT "PLEASE RESTART AND ANSWER MEMORY SIZE? 32000":END
30 IF (INP(83) AND 14)<>0 THEN PRINT "FPGA CARD NOT FOUND":END
40 PRINT "LOADING USR MODULE...":S=0
50 FOR I=0 TO {n}:READ B:POKE 32000+I,B:S=S+B:NEXT
60 IF S<>{sum} THEN PRINT "CHECKSUM ERROR IN DATA LINES":END
70 POKE 16526,0:POKE 16527,125
100 REM *** SPRITE ENGINE: PARAMS -> OUT 82, COMMAND -> OUT 83
110 OUT 83,1:GOSUB 900:REM RESET
120 OUT 82,32:OUT 83,8:GOSUB 900:REM BLANK BACKGROUND
130 OUT 82,0:OUT 82,3:OUT 82,128:OUT 82,42:OUT 82,1:OUT 82,0:OUT 83,13:GOSUB 900:REM FRAME
140 OUT 82,0:OUT 82,8:OUT 82,8:FOR R=1 TO 8:READ B:OUT 82,B:OUT 82,0:NEXT
150 OUT 83,16:GOSUB 900:REM SHAPE 0 = BALL
160 FOR N=0 TO 3:READ X,Y,DX(N),DY(N)
170 OUT 82,N:OUT 82,0:OUT 82,X:OUT 82,Y:OUT 82,1:OUT 83,32:GOSUB 900
180 OUT 82,N:OUT 82,DX(N) AND 255:OUT 82,DY(N) AND 255:OUT 83,36:GOSUB 900
190 NEXT N
200 FOR F=1 TO 300
210 R=USR(0):REM RENDER + COPY TO SCREEN
220 FOR N=0 TO 3:OUT 82,N:OUT 83,37:GOSUB 900:X=INP(82):Y=INP(82):C=0
230 IF (X>117 AND DX(N)>0) OR (X<3 AND DX(N)<0) THEN DX(N)=-DX(N):C=1
240 IF (Y>35 AND DY(N)>0) OR (Y<5 AND DY(N)<0) THEN DY(N)=-DY(N):C=1
250 IF C THEN OUT 82,N:OUT 82,DX(N) AND 255:OUT 82,DY(N) AND 255:OUT 83,36:GOSUB 900
260 NEXT N
270 IF PEEK(14400) AND 128 THEN 300:REM SPACE BAR ENDS THE ANIMATION
280 NEXT F
300 REM *** AM9511 ON A BASIC VARIABLE
310 CLS:A=.5:V=VARPTR(A)
320 POKE 32004,V AND 255:POKE 32005,INT(V/256):POKE 32003,2:R=USR(2)
330 PRINT "SIN(.5) BY THE AM9511:";A;"  BY BASIC:";SIN(.5)
340 A=10:B=2:V=VARPTR(A):W=VARPTR(B)
350 POKE 32004,V AND 255:POKE 32005,INT(V/256)
360 POKE 32006,W AND 255:POKE 32007,INT(W/256):POKE 32003,11:R=USR(3)
370 PRINT "2^10 BY THE AM9511:";A
380 END
900 IF INP(83)>127 THEN 900
910 RETURN
"""

TRAILER = """2000 DATA 60,126,255,255,255,255,126,60
2010 DATA 10,5,1,1,40,20,-1,1,70,10,2,-1,100,30,-1,-1
"""


def make(code):
    lines = PROGRAM.format(n=len(code) - 1, sum=sum(code))
    ln = 1000
    for i in range(0, len(code), 24):
        lines += "%d DATA %s\n" % (ln, ",".join(str(b) for b in code[i:i + 24]))
        ln += 10
    assert ln < 2000, "too many DATA lines"
    return lines + TRAILER


if __name__ == "__main__":
    code = open(sys.argv[1], "rb").read()
    text = make(code)
    with open(sys.argv[2], "w", newline="\r\n") as f:
        f.write(text)
    print("%s: %d bytes of machine code in %d DATA lines -> %s"
          % (sys.argv[1], len(code), (len(code) + 23) // 24, sys.argv[2]))
