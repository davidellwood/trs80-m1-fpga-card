# Gowin EDA batch build for the rev 2 ECB FPGA card (Tang Nano 20K, GW2AR-18).
# Run from this folder:
#   C:\Gowin\Gowin_V1.9.11.03_Education_x64\IDE\bin\gw_sh.exe build20k.tcl
# Output bitstream: impl/pnr/trs80_card20k.fs (shares impl/ with the 9K build; file names differ)

set_device GW2AR-LV18QN88C8/I7 -name GW2AR-18C

add_file src/sync2.v
add_file src/xbus.v
add_file src/am9511.v
add_file src/gfx_regs.v
add_file src/spram.v
add_file src/sprite_engine.v
add_file src/trs80_card_top.v
add_file src/trs80_card20k_top.v
add_file constraints/trs80_card20k.cst
add_file constraints/trs80_card.sdc

set_option -top_module trs80_card20k_top
set_option -include_path {src}
set_option -verilog_std v2001
set_option -output_base_name trs80_card20k
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 1
set_option -use_ready_as_gpio 1
set_option -use_done_as_gpio 1
set_option -use_reconfign_as_gpio 1

run all
