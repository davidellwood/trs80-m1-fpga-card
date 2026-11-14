# Gowin EDA batch build for the TRS-80 Model I FPGA card (Tang Nano 9K).
# Run from this folder:
#   C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe build.tcl
# Output bitstream: impl/pnr/trs80_card.fs

set_device GW1NR-LV9QN88PC6/I5 -name GW1NR-9C

add_file src/sync2.v
add_file src/xbus.v
add_file src/am9511.v
add_file src/gfx_regs.v
add_file src/spram.v
add_file src/sprite_engine.v
add_file src/trs80_card_top.v
add_file constraints/trs80_card.cst
add_file constraints/trs80_card.sdc

set_option -top_module trs80_card_top
set_option -include_path {src}
set_option -verilog_std v2001
set_option -output_base_name trs80_card
# several header pins are dual-purpose configuration pins on the GW1NR-9
set_option -use_mspi_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -use_ready_as_gpio 1
set_option -use_done_as_gpio 1
set_option -use_reconfign_as_gpio 1

run all
