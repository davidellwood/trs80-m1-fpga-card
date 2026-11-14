# Assemble every GAL in hardware/gal/galasm/ to JEDEC with GALasm, then verify each fuse map
# against the CUPL-derived models by exhaustive simulation (hardware/tools/galsim.py).
#   powershell -ExecutionPolicy Bypass -File build_jed.ps1 [-Galasm <path to galasm.exe>]
# GALasm (github.com/daveho/GALasm, built locally with MSVC) is free for non-commercial use only.
param([string]$Galasm = "C:\path\to\tools\galasm\bin\galasm.exe")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location (Join-Path $here "galasm")
try {
    foreach ($f in Get-ChildItem *.gal) {
        & $Galasm $f.Name | Out-Null
        if ($LASTEXITCODE) { throw "GALasm failed on $($f.Name)" }
        Write-Host ("assembled {0} -> {1}" -f $f.Name, ($f.BaseName + ".jed"))
    }
} finally { Pop-Location }
python (Join-Path $here "..\tools\galsim.py")
if ($LASTEXITCODE) { throw "fuse-map verification failed" }
