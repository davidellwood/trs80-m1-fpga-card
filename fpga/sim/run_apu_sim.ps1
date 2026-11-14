# Am9511 core check: generate vectors + expected results from apu_model.py,
# run them through the Verilog testbench (tb_sprite.v player), and compare.
#   powershell -ExecutionPolicy Bypass -File run_apu_sim.ps1 -IverilogDir <folder with iverilog.exe>
param([string]$IverilogDir = "", [string]$Python = "python")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$iv = if ($IverilogDir) { Join-Path $IverilogDir "iverilog.exe" } else { "iverilog" }
$vvp = if ($IverilogDir) { Join-Path $IverilogDir "vvp.exe" } else { "vvp" }
$src = Join-Path $here "..\src"
Push-Location $here
try {
    & $Python -I apu_ucode.py                     # regenerate ../src/am9511_ucode.vh
    if ($LASTEXITCODE) { throw "microcode assembly failed" }
    & $Python -I apu_model.py gen
    if ($LASTEXITCODE) { throw "model failed" }
    & $iv -g2005 -Wall -I "$src" -o tb_apu.vvp tb_sprite.v `
        "$src\sync2.v" "$src\xbus.v" "$src\am9511.v" "$src\gfx_regs.v" "$src\spram.v" `
        "$src\sprite_engine.v" "$src\trs80_card_top.v"
    if ($LASTEXITCODE) { throw "iverilog failed" }
    & $vvp -n tb_apu.vvp +VEC=apu_vectors.hex +READS=apu_reads.txt +FRAMES=apu_frames.txt
    & $Python -I apu_model.py check
} finally { Pop-Location }
