# Sprite-engine check: generate vectors + expected results from the Python model,
# run them through the Verilog testbench, and compare.
#   powershell -ExecutionPolicy Bypass -File run_sprite_sim.ps1 -IverilogDir <folder with iverilog.exe>
param([string]$IverilogDir = "", [string]$Python = "python")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$iv = if ($IverilogDir) { Join-Path $IverilogDir "iverilog.exe" } else { "iverilog" }
$vvp = if ($IverilogDir) { Join-Path $IverilogDir "vvp.exe" } else { "vvp" }
$src = Join-Path $here "..\src"
Push-Location $here
try {
    & $Python -I sprite_model.py gen
    if ($LASTEXITCODE) { throw "model failed" }
    & $iv -g2005 -Wall -I "$src" -o tb_sprite.vvp tb_sprite.v `
        "$src\sync2.v" "$src\xbus.v" "$src\am9511.v" "$src\gfx_regs.v" "$src\spram.v" `
        "$src\sprite_engine.v" "$src\trs80_card_top.v"
    if ($LASTEXITCODE) { throw "iverilog failed" }
    & $vvp -n tb_sprite.vvp
    & $Python -I sprite_model.py check
} finally { Pop-Location }
