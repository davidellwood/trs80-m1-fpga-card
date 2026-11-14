# Build the Pico firmware with the portable toolchain in C:\path\to\tools\pico
# (Arm GNU 15.3.rel2, CMake 4.4.2, Ninja 1.13.2, Pico SDK 2.3.1 + TinyUSB, picotool 2.3.1).
#   powershell -ExecutionPolicy Bypass -File build.ps1 [-Tools <folder>] [-Clean]
# Output: build\frehd_pico.uf2 (hold BOOTSEL, plug in the Pico, copy the .uf2 onto it).
param([string]$Tools = "C:\path\to\tools\pico", [switch]$Clean)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$cmakeDir = (Get-ChildItem (Join-Path $Tools "cmake") -Directory | Select-Object -First 1).FullName
$env:PATH = "$cmakeDir\bin;$Tools\ninja;$Tools\armgcc\bin;$env:PATH"
$env:PICO_SDK_PATH = Join-Path $Tools "pico-sdk"
$env:PICO_TOOLCHAIN_PATH = Join-Path $Tools "armgcc"
$picotool = Join-Path $Tools "picotool\picotool"
$build = Join-Path $here "build"
if ($Clean -and (Test-Path $build)) { Remove-Item $build -Recurse -Force }
if (-not (Test-Path (Join-Path $build "build.ninja"))) {
    cmake -S $here -B $build -G Ninja -DPICO_BOARD=pico "-Dpicotool_DIR=$picotool"
    if ($LASTEXITCODE) { throw "cmake configure failed" }
}
cmake --build $build
if ($LASTEXITCODE) { throw "build failed" }
& (Join-Path $Tools "armgcc\bin\arm-none-eabi-size.exe") (Join-Path $build "frehd_pico.elf")
Write-Host "UF2: $build\frehd_pico.uf2"
