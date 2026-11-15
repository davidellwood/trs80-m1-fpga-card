# Assemble every GAL in hardware/gal/galasm/ to JEDEC with GALasm, then verify each fuse map
# against the CUPL-derived models by exhaustive simulation (hardware/tools/galsim.py).
#   powershell -ExecutionPolicy Bypass -File build_jed.ps1 [-Galasm <path to galasm.exe>]
# galasm.exe is, in order: -Galasm, the GALASM environment variable, tools\galasm\bin\galasm.exe
# in the folder that contains this repository, or galasm on the PATH.
# GALasm (github.com/daveho/GALasm) is free for non-commercial use only.
param([string]$Galasm = "")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $here "..\..")).Path
if (-not $Galasm) { $Galasm = $env:GALASM }
if (-not $Galasm) {
    $local = Join-Path (Split-Path -Parent $repo) "tools\galasm\bin\galasm.exe"
    if (Test-Path $local) { $Galasm = $local }
    else {
        $cmd = Get-Command galasm -ErrorAction SilentlyContinue
        if ($cmd) { $Galasm = $cmd.Source }
    }
}
if (-not $Galasm -or -not (Test-Path $Galasm)) {
    throw "galasm.exe not found. Pass -Galasm <path>, set GALASM, or put galasm on the PATH (see README.md)."
}
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
