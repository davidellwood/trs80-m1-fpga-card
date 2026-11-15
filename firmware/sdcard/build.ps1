# Build the Pico firmware with a portable toolchain folder holding:
#   cmake\<cmake-x.y.z-windows-x86_64>\bin, ninja\ninja.exe, armgcc\bin (Arm GNU Toolchain),
#   pico-sdk\ (with lib\tinyusb), picotool\picotool\ (picotoolConfig.cmake)
#   powershell -ExecutionPolicy Bypass -File build.ps1 [-Tools <folder>] [-Clean]
# The toolchain folder is, in order: -Tools, the PICO_TOOLS environment variable, or
# tools\pico in the folder that contains this repository (i.e. ..\tools\pico from the repo root).
# Output: build\frehd_pico.uf2 (hold BOOTSEL, plug in the Pico, copy the .uf2 onto it).
param([string]$Tools = "", [switch]$Clean)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = (Resolve-Path (Join-Path $here "..\..")).Path
if (-not $Tools) { $Tools = $env:PICO_TOOLS }
if (-not $Tools) { $Tools = Join-Path (Split-Path -Parent $repo) "tools\pico" }
if (-not (Test-Path (Join-Path $Tools "pico-sdk\pico_sdk_init.cmake"))) {
    throw "Pico toolchain not found in '$Tools'. Pass -Tools <folder> or set PICO_TOOLS (see README.md)."
}
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
