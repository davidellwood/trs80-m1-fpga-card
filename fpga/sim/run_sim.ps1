# Run the testbench with Icarus Verilog (from OSS CAD Suite or any iverilog on PATH).
#   powershell -ExecutionPolicy Bypass -File run_sim.ps1 [-IverilogDir <folder with iverilog.exe>] [-Tang20K]
# -Tang20K runs the same tests through the rev 2 Tang Nano 20K top (trs80_card20k_top).
param([string]$IverilogDir = "", [switch]$Tang20K)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$iv = if ($IverilogDir) { Join-Path $IverilogDir "iverilog.exe" } else { "iverilog" }
$vvp = if ($IverilogDir) { Join-Path $IverilogDir "vvp.exe" } else { "vvp" }
$src = Join-Path $here "..\src"
$extra = @()
if ($Tang20K) { $extra = @("-DTANG20K", "$src\trs80_card20k_top.v") }
Push-Location $here
try {
    & $iv -g2005 -Wall -I "$src" -o tb_top.vvp @extra tb_top.v `
        "$src\sync2.v" "$src\xbus.v" "$src\am9511.v" "$src\gfx_regs.v" "$src\spram.v" `
        "$src\sprite_engine.v" "$src\trs80_card_top.v"
    if ($LASTEXITCODE) { throw "iverilog failed" }
    & $vvp -n tb_top.vvp
} finally { Pop-Location }
