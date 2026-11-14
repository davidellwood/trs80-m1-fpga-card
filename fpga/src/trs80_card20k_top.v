`timescale 1ns/1ps
// ---------------------------------------------------------------------------
// Rev 2 ECB FPGA card - top level for the Sipeed Tang Nano 20K (GW2AR-18)
//
// Wraps the unchanged rev 0.1 core (trs80_card_top). Differences on the 20K:
//   - all 30 usable header I/Os carry card signals, so the module LED pins
//     (P15-P20) are card nets (they light on activity by themselves) and the
//     core's led_n outputs are not used;
//   - no reset button: reset comes from power-on and ECB RESET* (via U6);
//   - P51 (audio amplifier enable) and P79 (WS2812 data) are driven low so
//     the I2S pins doubling as FD3/FD4/FD6 cannot make the amplifier buzz
//     and the RGB LED stays dark.
// Pins: constraints/trs80_card20k.cst. Names follow hardware/card-fpga.
// ---------------------------------------------------------------------------
module trs80_card20k_top (
    input  wire        clk27,          // 27 MHz on-board oscillator (P4)

    output wire [10:0] ra,             // IDT7132 right-port address
    output wire        r_ce_n,
    output wire        r_rw_n,
    input  wire        r_busy_n,       // via U6

    inout  wire [7:0]  fd,             // shared data bus (2N7000 shifters to XD)

    input  wire        iord,           // ECB IN  to the port block (active high, via U6)
    input  wire        iowr,           // ECB OUT to the port block (active high, via U6)
    input  wire [1:0]  pa,             // ECB A1:A0 (via U6)
    output wire        port_oe_n,      // U3 enable
    output wire        wait_drv,       // Q9  -> ECB WAIT*
    output wire        int_drv,        // Q10 -> ECB INT* (via JP2)
    input  wire        reset_n,        // ECB RESET* via U6

    output wire        pa_en,          // on-board audio amplifier enable: keep off
    output wire        ws2812          // on-board RGB LED data: keep idle
);
    assign pa_en  = 1'b0;
    assign ws2812 = 1'b0;

    wire [5:0] led_unused;

    trs80_card_top u_core (
        .clk27(clk27), .btn_s1_n(1'b1),
        .ra(ra), .r_ce_n(r_ce_n), .r_rw_n(r_rw_n), .r_busy_n(r_busy_n),
        .fd(fd),
        .iord(iord), .iowr(iowr), .pa(pa), .port_oe_n(port_oe_n),
        .wait_drv(wait_drv), .int_drv(int_drv), .sysres_n(reset_n),
        .led_n(led_unused)
    );
endmodule
