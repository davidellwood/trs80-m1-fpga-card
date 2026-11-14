# Build and run the host tests for the FreHD core with MSVC (Visual Studio Build Tools).
#   powershell -ExecutionPolicy Bypass -File build_test.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vcvars = $null
foreach ($vs in @(& $vswhere -all -products * -property installationPath)) {
    $c = Join-Path $vs "VC\Auxiliary\Build\vcvars64.bat"
    if (Test-Path $c) { $vcvars = $c; break }
}
if (-not $vcvars) { throw "MSVC build tools (vcvars64.bat) not found" }
$out = Join-Path $env:TEMP "frehd_test_build"
New-Item -ItemType Directory -Force $out | Out-Null
$cmd = "`"$vcvars`" >nul && cl /nologo /W4 /WX /wd4996 /I`"$here`" /Fe`"$out\test_frehd.exe`" /Fo`"$out\\`" " +
       "`"$here\test_frehd.c`" `"$here\ff_host.c`" `"$here\..\src\frehd.c`" `"$here\..\src\image.c`""
cmd /c $cmd
if ($LASTEXITCODE) { throw "build failed" }
& "$out\test_frehd.exe"
if ($LASTEXITCODE) { exit $LASTEXITCODE }

# Syntax-check the Pico-only sources against declaration stubs of the SDK (no ARM toolchain needed).
$src = Join-Path $here "..\src"
$chk = "`"$vcvars`" >nul && cl /nologo /W4 /WX /Zs /wd4996 /DFREHD_PICO=1 /DFF_USE_LFN=1 " +
       "/I`"$here\pico_stubs`" /I`"$here`" /I`"$src`" `"$src\main.c`" `"$src\bus.c`" `"$src\frehd.c`" `"$src\image.c`" " +
       "`"$src\sd_spi.c`" `"$src\diskio.c`" `"$src\ds1307.c`""
cmd /c $chk
if ($LASTEXITCODE) { throw "Pico source syntax check failed" }
Write-Host "Pico sources: syntax check OK"
