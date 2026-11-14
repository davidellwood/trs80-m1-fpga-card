# FreHD-compatible SD card firmware for the Raspberry Pi Pico (RP2040).
# Needs the Pico SDK (PICO_SDK_PATH) and ChaN's FatFs R0.15 unpacked into lib/fatfs
# (so lib/fatfs/source/ff.c exists). See README.md.
cmake_minimum_required(VERSION 3.13)
include(pico_sdk_import.cmake)
project(frehd_pico C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()

set(FATFS_DIR ${CMAKE_CURRENT_LIST_DIR}/lib/fatfs/source)
if (NOT EXISTS ${FATFS_DIR}/ff.c)
    message(FATAL_ERROR "FatFs not found: unpack ChaN's FatFs R0.15 into lib/fatfs (lib/fatfs/source/ff.c)")
endif()
# FatFs includes "ffconf.h" from its own folder first, so install our configuration there.
configure_file(${CMAKE_CURRENT_LIST_DIR}/src/ffconf.h ${FATFS_DIR}/ffconf.h COPYONLY)

add_executable(frehd_pico
    src/main.c src/bus.c src/frehd.c src/image.c src/sd_spi.c src/diskio.c src/ds1307.c
    ${FATFS_DIR}/ff.c ${FATFS_DIR}/ffunicode.c)
target_include_directories(frehd_pico PRIVATE src ${FATFS_DIR})
target_compile_definitions(frehd_pico PRIVATE FREHD_PICO=1)
# full warnings on our own sources (not FatFs / the SDK)
set_source_files_properties(src/main.c src/image.c src/sd_spi.c src/diskio.c src/ds1307.c
    PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra")
# core 1 runs the bus handlers from RAM: no switch tables in flash
set_source_files_properties(src/frehd.c src/bus.c PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra;-fno-jump-tables")
target_link_libraries(frehd_pico pico_stdlib pico_multicore hardware_spi hardware_i2c)
pico_enable_stdio_usb(frehd_pico 1)
pico_enable_stdio_uart(frehd_pico 0)
pico_add_extra_outputs(frehd_pico)
