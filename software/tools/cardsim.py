#!/usr/bin/env python3
"""
A Model I with the FPGA card, for testing Z80 software: the z80emu CPU plus
the verified card models from fpga/sim (sprite_model.Engine and
apu_model.Am9511, both checked bit-for-bit against the Verilog).

Memory map: 3000h-37DFh -> card dual-port RAM (engine.dpram), 3800h-3BFFh
keyboard (callable), 3C00h-3FFFh video RAM, everything else plain RAM.
Ports 50h-53h -> card; other ports read FFh (empty bus).

The models finish every command instantly, so BUSY is never seen; real
render and APU times are added separately when estimating speed.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOFT = os.path.normpath(os.path.join(HERE, ".."))
FPGA_SIM = os.path.normpath(os.path.join(SOFT, "..", "fpga", "sim"))
sys.path.insert(0, HERE)
sys.path.insert(0, FPGA_SIM)

import z80emu                      # noqa: E402
import sprite_model                # noqa: E402
import apu_model                   # noqa: E402

DEFAULT_SJASM = os.environ.get("SJASMPLUS", "sjasmplus")


def assemble(src, name, sjasm=DEFAULT_SJASM):
    """Assemble `src` (path) -> (bytes, {symbol: value}); output in software/build."""
    out = os.path.join(SOFT, "build")
    os.makedirs(out, exist_ok=True)
    binf, symf = os.path.join(out, name + ".bin"), os.path.join(out, name + ".sym")
    r = subprocess.run([sjasm, "--nologo", "--msg=war", "--raw=" + binf, "--sym=" + symf,
                        os.path.basename(src)], cwd=os.path.dirname(src),
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("assembly failed:\n" + r.stdout + r.stderr)
    syms = {}
    for line in open(symf):
        m = re.match(r"(\S+): EQU 0x([0-9A-Fa-f]+)", line)
        if m:
            syms[m.group(1)] = int(m.group(2), 16)
    return open(binf, "rb").read(), syms


class Machine:
    def __init__(self, card=True):
        self.mem = bytearray(65536)
        self.card = card
        self.gfx = sprite_model.Engine()
        self.apu = apu_model.Am9511()
        self.kbd = lambda addr: 0
        self.traps = {}                 # pc -> fn(machine) ; return True to stop
        self.io_log = []
        self.cpu = z80emu.Z80(self.rd, self.wr, self.inp, self.out)

    # ---------------------------------------------------------------- bus
    def rd(self, a):
        if self.card and 0x3000 <= a < 0x37E0:
            return self.gfx.dpram[a - 0x3000]
        if 0x3800 <= a < 0x3C00:
            return self.kbd(a) & 0xFF
        return self.mem[a]

    def wr(self, a, v):
        if self.card and 0x3000 <= a < 0x37E0:
            self.gfx.dpram[a - 0x3000] = v
        elif a >= 0x3C00 or a < 0x3000:
            self.mem[a] = v

    def inp(self, port):
        if not self.card:
            return 0xFF
        if port == 0x50:
            return self.apu.pop()
        if port == 0x51:
            return self.apu.status & 0x7F
        if port in (0x52, 0x53):
            return self.gfx.inp(port)
        return 0xFF

    def out(self, port, v):
        if not self.card:
            return
        self.io_log.append((port, v))
        if port == 0x50:
            self.apu.push(v)
        elif port == 0x51:
            self.apu.command(v)
        elif port in (0x52, 0x53):
            self.gfx.out(port, v)

    # ---------------------------------------------------------------- run
    def load(self, data, org):
        self.mem[org:org + len(data)] = data

    def call(self, pc, sp=0x7F00, max_steps=50_000_000):
        """Run from `pc` until HALT, a trap returning True, or RET to 0000h."""
        c = self.cpu
        c.pc, c.sp, c.halted = pc, sp, False
        c.push(0x0000)                   # returning to 0 ends the run
        for _ in range(max_steps):
            if c.halted or c.pc == 0x0000:
                return
            fn = self.traps.get(c.pc)
            if fn and fn(self):
                return
            c.step()
        raise RuntimeError("step limit at %04x" % c.pc)

    def video(self):
        return list(self.mem[0x3C00:0x4000])

    def peek(self, a, n=1):
        return bytes(self.rd(a + i) for i in range(n))

    def poke(self, a, data):
        for i, b in enumerate(data):
            self.wr(a + i, b)
