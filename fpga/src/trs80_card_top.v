`timescale 1ns/1ps
// ---------------------------------------------------------------------------
// TRS-80 Model I FPGA card - top level for the Sipeed Tang Nano 9K (GW1NR-9)
//
// Board I/O, the shared FD bus controller (Z80 port cycles + IDT7132 right
// port), and the blocks behind the four Z80 ports:
//   +0  Am9511 data          (apu_stub, later the APU core)
//   +1  Am9511 cmd/status
//   +2  sprite PARAM/RESULT  (gfx_regs + sprite_engine)
//   +3  sprite CMD/STATUS
// Pin numbers are in constraints/trs80_card.cst; names follow the schematic.
// ---------------------------------------------------------------------------
module trs80_card_top #(
    parameter AUTO_TICK = 450000           // RENDER_AUTO unit: 1/60 s at 27 MHz
) (
    input  wire        clk27,          // 27 MHz on-board oscillator
    input  wire        btn_s1_n,       // on-board button S1 = reset

    // IDT7132 right port (3.3 V outputs into 5 V TTL-level inputs)
    output wire [10:0] ra,
    output wire        r_ce_n,
    output wire        r_rw_n,
    input  wire        r_busy_n,       // via U6

    // shared data bus (FD, via 2N7000 shifters to XD)
    inout  wire [7:0]  fd,

    // Z80 port block (via U5 decode and U6 level shift)
    input  wire        iord,           // IN  to 0x50-0x53 (active high)
    input  wire        iowr,           // OUT to 0x50-0x53 (active high)
    input  wire [1:0]  pa,             // Z80 A1:A0
    output wire        port_oe_n,      // U3 enable
    output wire        wait_drv,       // Q9 -> WAIT*
    output wire        int_drv,        // Q10 -> INT* (via JP2)
    input  wire        sysres_n,       // Model I system reset via U6

    output wire [5:0]  led_n           // on-board LEDs, active low
);
    // ---------------- reset ----------------
    wire sysres_n_s, btn_n_s;
    sync2 #(.W(1), .INIT(1'b1)) u_sr (.clk(clk27), .d(sysres_n), .q(sysres_n_s));
    sync2 #(.W(1), .INIT(1'b1)) u_bt (.clk(clk27), .d(btn_s1_n), .q(btn_n_s));

    reg [15:0] por = 16'd0;            // ~2.4 ms power-on reset
    always @(posedge clk27)
        if (!por[15]) por <= por + 16'd1;
    reg rst = 1'b1;                    // registered: one clean, low-skew source
    always @(posedge clk27)
        rst <= !por[15] || !sysres_n_s || !btn_n_s;

    // ---------------- synchronised Z80-side inputs ----------------
    wire iord_s, iowr_s, busy_n_s;
    wire [1:0] pa_s;
    sync2 #(.W(1))             u_rd (.clk(clk27), .d(iord),     .q(iord_s));
    sync2 #(.W(1))             u_wr (.clk(clk27), .d(iowr),     .q(iowr_s));
    sync2 #(.W(2))             u_pa (.clk(clk27), .d(pa),       .q(pa_s));
    sync2 #(.W(1), .INIT(1'b1)) u_by (.clk(clk27), .d(r_busy_n), .q(busy_n_s));

    // ---------------- shared bus controller ----------------
    wire [7:0] fd_out;
    wire       fd_oe;
    wire       port_oe_n_q, in_drive;

    // When IN* rises, U3's DIR flips to "Z80 bus -> XD" at once, but the
    // synchronised strobe only reaches the state machine ~3 clocks later.
    // Gate both the FD drive and U3's enable with the *raw* strobe pins so
    // they drop within the GAL + 4050 delay (~30 ns) of the strobe ending.
    wire fd_oe_pin = fd_oe & ~(in_drive & ~iord);
    assign fd        = fd_oe_pin ? fd_out : 8'hzz;
    assign port_oe_n = port_oe_n_q | ~(iord | iowr);

    wire [1:0]  p_addr;
    wire [7:0]  p_wdata;
    wire        p_rd_pop, p_wr_stb;
    wire [7:0]  apu_rdata, gfx_rdata;
    wire        apu_rrdy, apu_wrdy, gfx_rrdy, gfx_wrdy;

    wire        dp_req, dp_we, dp_ack;
    wire [10:0] dp_addr;
    wire [7:0]  dp_wdata, dp_rdata;
    wire        wait_tmo, port_active, dp_active;

    xbus u_xbus (
        .clk(clk27), .rst(rst),
        .ra(ra), .r_ce_n(r_ce_n), .r_rw_n(r_rw_n), .r_busy(~busy_n_s),
        .fd_out(fd_out), .fd_oe(fd_oe), .fd_in(fd),
        .iord(iord_s), .iowr(iowr_s), .pa(pa_s),
        .port_oe_n(port_oe_n_q), .wait_drv(wait_drv),
        .p_addr(p_addr),
        .p_rdata   (p_addr[1] ? gfx_rdata : apu_rdata),
        .p_rd_ready(p_addr[1] ? gfx_rrdy  : apu_rrdy),
        .p_wr_ready(p_addr[1] ? gfx_wrdy  : apu_wrdy),
        .p_rd_pop(p_rd_pop), .p_wr_stb(p_wr_stb), .p_wdata(p_wdata),
        .dp_req(dp_req), .dp_we(dp_we), .dp_addr(dp_addr), .dp_wdata(dp_wdata),
        .dp_ack(dp_ack), .dp_rdata(dp_rdata),
        .wait_timeout(wait_tmo), .port_active(port_active), .dp_active(dp_active),
        .in_drive(in_drive)
    );

    // ---------------- port register blocks ----------------
    wire apu_svreq;
    am9511 u_apu (
        .clk(clk27), .rst(rst), .sel_c(p_addr[0]),
        .wr_stb(p_wr_stb & ~p_addr[1]), .wdata(p_wdata),
        .rd_pop(p_rd_pop & ~p_addr[1]),
        .rdata(apu_rdata), .rd_ready(apu_rrdy), .wr_ready(apu_wrdy),
        .svreq(apu_svreq)
    );

    wire        gfx_busy, gfx_frame, gfx_hit;
    wire        cmd_start, p_avail, p_pop, r_push, eng_busy, eng_done, eng_err, fifo_clr;
    wire [7:0]  cmd_code, p_data, r_data;
    wire [6:0]  cmd_np;
    gfx_regs u_gfx (
        .clk(clk27), .rst(rst), .sel_c(p_addr[0]),
        .wr_stb(p_wr_stb & p_addr[1]), .wdata(p_wdata),
        .rd_pop(p_rd_pop & p_addr[1]),
        .rdata(gfx_rdata), .rd_ready(gfx_rrdy), .wr_ready(gfx_wrdy),
        .cmd_start(cmd_start), .cmd_code(cmd_code), .cmd_np(cmd_np),
        .p_data(p_data), .p_avail(p_avail), .p_pop(p_pop),
        .r_push(r_push), .r_data(r_data),
        .eng_busy(eng_busy), .eng_done(eng_done), .eng_err(eng_err), .fifo_clr(fifo_clr),
        .frame(gfx_frame), .hit(gfx_hit), .busy(gfx_busy)
    );
    sprite_engine #(.AUTO_TICK(AUTO_TICK)) u_spr (
        .clk(clk27), .rst(rst),
        .cmd_start(cmd_start), .cmd_code(cmd_code), .cmd_np(cmd_np),
        .p_data(p_data), .p_avail(p_avail), .p_pop(p_pop),
        .r_push(r_push), .r_data(r_data),
        .busy(eng_busy), .done(eng_done), .err_p(eng_err), .fifo_clr(fifo_clr),
        .frame(gfx_frame), .hit_any(gfx_hit),
        .dp_req(dp_req), .dp_we(dp_we), .dp_addr(dp_addr), .dp_wdata(dp_wdata),
        .dp_ack(dp_ack), .dp_rdata(dp_rdata)
    );

    // INT* (only reaches the bus when JP2 is fitted): Am9511 service request,
    // raised when a command with the SR bit (0x80) completes, cleared by the
    // next command or a status read.
    assign int_drv = apu_svreq;

    // ---------------- LEDs (active low) ----------------
    reg [24:0] hb = 25'd0;
    always @(posedge clk27) hb <= hb + 25'd1;

    // stretch short events so they are visible (~40 ms)
    reg [20:0] s_port = 0, s_dp = 0, s_tmo = 0;
    always @(posedge clk27) begin
        s_port <= port_active ? {21{1'b1}} : (s_port != 0 ? s_port - 21'd1 : 21'd0);
        s_dp   <= dp_active   ? {21{1'b1}} : (s_dp   != 0 ? s_dp   - 21'd1 : 21'd0);
        s_tmo  <= wait_tmo    ? {21{1'b1}} : (s_tmo  != 0 ? s_tmo  - 21'd1 : 21'd0);
    end

    assign led_n[0] = ~hb[24];          // heartbeat (~0.8 Hz)
    assign led_n[1] = ~(s_port != 0);   // Z80 port activity
    assign led_n[2] = ~(s_dp != 0);     // DPRAM activity
    assign led_n[3] = ~(s_tmo != 0);    // WAIT timeout happened
    assign led_n[4] = ~gfx_frame;       // FRAME ready
    assign led_n[5] = ~rst;             // in reset
endmodule
