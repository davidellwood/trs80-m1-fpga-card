# Build the TRS-80 FPGA card software and run the tests.
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Sjasm <path to sjasmplus.exe> [-NoTest]
# Outputs in build\: DEMO.CMD, cardusr.bin, and basic\demo.bas (regenerated).
param([string]$Sjasm = "sjasmplus", [string]$Python = "python", [switch]$NoTest)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
New-Item -ItemType Directory -Force "$here\build" | Out-Null

function Asm($dir, $file, $name) {
    Push-Location "$here\$dir"
    try {
        & $Sjasm --nologo --msg=war --raw="$here\build\$name.bin" --sym="$here\build\$name.sym" $file
        if ($LASTEXITCODE) { throw "assembly of $file failed" }
    } finally { Pop-Location }
}

Asm "demo"  "demo.asm"    "demo"
Asm "basic" "cardusr.asm" "cardusr"
Asm "test"  "libtest.asm" "libtest"
& $Python -I "$here\tools\bin2cmd.py" "$here\build\demo.bin" 6000 "$here\build\DEMO.CMD"
& $Python -I "$here\tools\mkbasic.py" "$here\build\cardusr.bin" "$here\basic\demo.bas"

if (-not $NoTest) {
    $env:SJASMPLUS = $Sjasm
    & $Python -I "$here\tools\test_lib.py"
    if ($LASTEXITCODE) { throw "tests failed" }
}
