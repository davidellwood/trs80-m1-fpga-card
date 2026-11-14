// ---------------------------------------------------------------------------
// Testbench: trs80_card_top against a model of the board and the Z80.
//
//  * IDT7132 right port: OE_R tied low (drives XD whenever CE low & R/W high),
//    tAA 70 ns, CE-controlled writes latched at CE rising, writes inhibited
//    while BUSY_R is asserted. A left-port "contention" can force BUSY_R.
//  * 2N7000 shifters: slow rising edges (pull-up), fast falling edges.
//  * U3 74HCT245: DIR = IN_N, /OE = PORT_OE_N.
//  * U5/U6: IORD/IOWR/PA reach the FPGA 30 ns after the Z80 signals.
//  * Z80 I/O cycles at 1.774 MHz with the automatic wait state; WAIT* is
//    sampled in every TW, as on the real CPU.
//  * A checker flags any time two devices drive the shared XD bus at once.
// ---------------------------------------------------------------------------
`timescale 1ns/1ps
module tb_top;
    localparam real TCLK = 37.037;      // 27 MHz
    localparam real TZ80 = 563.7;       // 1.774 MHz T-state

    reg clk = 0;
    always #(TCLK/2) clk = ~clk;

    // ---------------- DUT ----------------
    wire [10:0] ra;
    wire r_ce_n, r_rw_n, port_oe_n, wait_drv, int_drv;
    wire [7:0] fd;
    wire [5:0] led_n;
    reg  btn_n = 1'b1, sysres_n = 1'b1;
    wire r_busy_n_fpga;
    reg  [7:0] z80_addr = 8'h00;
    reg  in_n = 1'b1, out_n = 1'b1;
    wire in_blk = (z80_addr[7:2] == 6'b010100);        // 0x50-0x53 (U5)
    wire #30 iord = in_blk & ~in_n;
    wire #30 iowr = in_blk & ~out_n;
    wire #30 pa0  = z80_addr[0];
    wire #30 pa1  = z80_addr[1];

`ifdef TANG20K
    `define CORE dut.u_core
    // rev 2 ECB card: Tang Nano 20K wrapper (no button, no LED outputs)
    wire pa_en, ws2812;
    assign led_n = 6'h3F;
    trs80_card20k_top dut (
        .clk27(clk),
        .ra(ra), .r_ce_n(r_ce_n), .r_rw_n(r_rw_n), .r_busy_n(r_busy_n_fpga),
        .fd(fd),
        .iord(iord), .iowr(iowr), .pa({pa1, pa0}),
        .port_oe_n(port_oe_n), .wait_drv(wait_drv), .int_drv(int_drv),
        .reset_n(sysres_n & btn_n), .pa_en(pa_en), .ws2812(ws2812)
    );
    always @(posedge clk)
        if (pa_en !== 1'b0 || ws2812 !== 1'b0) begin
            $display("FAIL: 20K pa_en/ws2812 not held low"); $finish;
        end
`else
    `define CORE dut
    trs80_card_top dut (
        .clk27(clk), .btn_s1_n(btn_n),
        .ra(ra), .r_ce_n(r_ce_n), .r_rw_n(r_rw_n), .r_busy_n(r_busy_n_fpga),
        .fd(fd),
        .iord(iord), .iowr(iowr), .pa({pa1, pa0}),
        .port_oe_n(port_oe_n), .wait_drv(wait_drv), .int_drv(int_drv),
        .sysres_n(sysres_n), .led_n(led_n)
    );
`endif

    // ---------------- IDT7132 model ----------------
    reg [7:0] mem [0:2047];
    integer k;
    initial for (k = 0; k < 2048; k = k + 1) mem[k] = 8'h5A;

    reg        left_active = 1'b0;      // left port holds this address and won
    reg [10:0] left_addr   = 11'd0;
    wire busy_r = !r_ce_n && left_active && (ra == left_addr);
    assign #15 r_busy_n_fpga = ~busy_r;                 // via U6

    wire dp_drives = !r_ce_n && r_rw_n;                 // OE_R tied low
    wire [7:0] #70 dp_q = mem[ra];

    // ---------------- shared bus (XD side, 5 V) ----------------
    // FPGA drive as seen at the pins (includes the raw-strobe gating)
    wire fpga_drives = `CORE.fd_oe_pin;
    // U3 (74HCT245): new direction drives ~25 ns after DIR changes (tPZx);
    // stops ~20 ns after /OE rises (tPxZ).
    wire #25      in_n_dir   = in_n;
    wire #(20, 0) port_oe_n_d = port_oe_n;
    wire u3_to_xd    = !port_oe_n_d && in_n_dir;        // OUT: Z80 D -> XD
    reg  [7:0] z80_dout = 8'h00;

    // FPGA -> XD through the shifters (rise via body diode/RN2, fall via FET)
    wire [7:0] xd_from_fpga;
    genvar b;
    generate for (b = 0; b < 8; b = b + 1) begin : sh
        assign #(100, 15) xd_from_fpga[b] = fd[b];
    end endgenerate

    wire [7:0] xd = fpga_drives ? xd_from_fpga :
                    dp_drives   ? dp_q :
                    u3_to_xd    ? z80_dout : 8'hFF;      // RN2 pull-ups

    // XD -> FD (what the FPGA sees when it is not driving): slow rise via RN1
    wire [7:0] fd_ext;
    generate for (b = 0; b < 8; b = b + 1) begin : sh2
        assign #(150, 15) fd_ext[b] = xd[b];
    end endgenerate
    assign fd = fpga_drives ? 8'hzz : fd_ext;

    // Z80 data bus during IN: U3 drives it from XD (25 ns)
    wire [7:0] #25 z80_din = (!port_oe_n && !in_n) ? xd : 8'hFF;

    // CE-controlled write: latch at CE rising edge if R/W low and not BUSY
    integer errors = 0, blocked_writes = 0, contention = 0;
    always @(posedge r_ce_n)
        if (!r_rw_n) begin
            if (left_active && ra == left_addr) blocked_writes = blocked_writes + 1;
            else mem[ra] <= xd;
        end

    // ---------------- contention checker ----------------
    // Overlaps shorter than 10 ns are normal buffer switching; longer ones fail.
    wire clash = (fpga_drives + dp_drives + u3_to_xd) > 1;
    realtime clash_t0 = 0, worst_clash = 0;
    integer  short_clashes = 0;
    always @(clash) if ($realtime > 100.0) begin   // tb delay models settle first
        if (clash)
            clash_t0 = $realtime;
        else begin
            if ($realtime - clash_t0 > worst_clash) worst_clash = $realtime - clash_t0;
            if ($realtime - clash_t0 > 10.0) begin
                contention = contention + 1;
                if (contention < 5)
                    $display("%t ERROR bus contention for %0.1f ns", $time, $realtime - clash_t0);
            end else
                short_clashes = short_clashes + 1;
        end
    end

    // longest CE_R-low write pulse (proves BUSY stretches the write)
    realtime ce_t0 = 0, max_wr_pulse = 0;
    always @(negedge r_ce_n) ce_t0 = $realtime;
    always @(posedge r_ce_n)
        if (!r_rw_n && ($realtime - ce_t0) > max_wr_pulse) max_wr_pulse = $realtime - ce_t0;

    // ---------------- Z80 I/O cycles ----------------
    integer wait_states = 0;
    task z80_io(input is_in, input [7:0] port, input [7:0] dout, output [7:0] din);
        begin
            // T1: address (and OUT data) valid
            z80_addr = port;
            z80_dout = dout;
            #(TZ80 * 0.6);
            // T2 rising: IORQ + RD/WR -> IN_N / OUT_N
            if (is_in) in_n = 1'b0; else out_n = 1'b0;
            // automatic TW: WAIT* sampled at its falling edge, ~1.5 T later
            #(TZ80 * 1.5);
            while (wait_drv) begin               // WAIT* low (Q9 on) -> extra TW
                wait_states = wait_states + 1;
                #(TZ80);
            end
            // T3: data read at the falling edge of T3
            #(TZ80 * 1.0);
            din = z80_din;
            if (is_in) in_n = 1'b1; else out_n = 1'b1;
            #(TZ80 * 0.9);
        end
    endtask

    reg [7:0] d;
    task z80_out(input [7:0] port, input [7:0] v); begin z80_io(0, port, v, d); end endtask
    task z80_in (input [7:0] port, output [7:0] v); begin z80_io(1, port, 8'h00, v); end endtask

    task expect(input [255:0] what, input [7:0] got, input [7:0] want);
        begin
            if (got !== want) begin
                errors = errors + 1;
                $display("%t FAIL %0s: got %02h want %02h", $time, what, got, want);
            end else
                $display("%t ok   %0s = %02h", $time, what, got);
        end
    endtask

    task wait_not_busy;
        integer n;
        begin
            n = 0;
            z80_in(8'h53, d);
            while (d[7] && n < 5000) begin z80_in(8'h53, d); n = n + 1; end
            if (d[7]) begin errors = errors + 1; $display("FAIL: engine stuck BUSY"); end
        end
    endtask

    // ---------------- test sequence ----------------
    integer i, bad;
    initial begin
        $dumpfile("tb_top.vcd");
        $dumpvars(0, tb_top);
        // wait for power-on reset (2^15 clocks)
        #(TCLK * 34000);

        $display("--- sprite port: VERSION");
        z80_out(8'h53, 8'h02);
        wait_not_busy;
        expect("STATUS RDY after VERSION", d & 8'h01, 8'h01);
        z80_in(8'h52, d); expect("VERSION major", d, 8'd0);
        z80_in(8'h52, d); expect("VERSION minor", d, 8'd2);
        z80_in(8'h52, d); expect("VERSION sprites", d, 8'd32);
        z80_in(8'h52, d); expect("VERSION shapes", d, 8'd64);
        z80_in(8'h53, d); expect("STATUS after draining", d, 8'h00);

        $display("--- POKE / PEEK through the DPRAM controller");
        z80_out(8'h52, 8'h23); z80_out(8'h52, 8'h01); z80_out(8'h52, 8'hA5);
        z80_out(8'h53, 8'hF2);
        wait_not_busy;
        expect("DPRAM[0x123] after POKE", mem[11'h123], 8'hA5);
        z80_out(8'h52, 8'h23); z80_out(8'h52, 8'h01);
        z80_out(8'h53, 8'hF1);
        wait_not_busy;
        z80_in(8'h52, d); expect("PEEK 0x123", d, 8'hA5);

        $display("--- POKE while the Z80 side holds the same address (BUSY_R)");
        left_addr = 11'h456; left_active = 1'b1;
        z80_out(8'h52, 8'h56); z80_out(8'h52, 8'h04); z80_out(8'h52, 8'h3C);
        z80_out(8'h53, 8'hF2);
        #2000 left_active = 1'b0;               // left port releases after 2 us
        wait_not_busy;
        expect("DPRAM[0x456] after BUSY", mem[11'h456], 8'h3C);
        expect("writes lost to BUSY", blocked_writes[7:0], 8'd0);
        $display("    longest write pulse %0.0f ns (normal ~220 ns)", max_wr_pulse);
        if (max_wr_pulse < 1000.0) begin
            errors = errors + 1;
            $display("FAIL: write pulse was not stretched while BUSY_R was asserted");
        end

        $display("--- FB_FILL 0x80, with status polling during the fill");
        z80_out(8'h52, 8'h80);
        z80_out(8'h53, 8'hF0);
        z80_in(8'h53, d); expect("STATUS BUSY during fill", d & 8'h80, 8'h80);
        wait_not_busy;
        z80_in(8'h53, d); expect("STATUS FRAME after fill", d & 8'h40, 8'h40);
        bad = 0;
        for (i = 0; i < 1024; i = i + 1) if (mem[i] !== 8'h80) bad = bad + 1;
        expect("frame buffer bytes wrong", bad[7:0], 8'd0);
        expect("DPRAM[0x400] untouched", mem[11'h400], 8'h5A);

        $display("--- Am9511 stub: stack push/pop and status");
        z80_out(8'h50, 8'h11); z80_out(8'h50, 8'h22); z80_out(8'h50, 8'h33);
        z80_in(8'h50, d); expect("APU pop 1", d, 8'h33);
        z80_in(8'h50, d); expect("APU pop 2", d, 8'h22);
        z80_in(8'h50, d); expect("APU pop 3", d, 8'h11);
        z80_in(8'h51, d); expect("APU status", d, 8'h00);

        $display("--- error handling");
        z80_out(8'h53, 8'h77);                  // unknown command
        wait_not_busy;
        expect("ERR after unknown command", d & 8'h20, 8'h20);
        z80_out(8'h53, 8'hF1);                  // PEEK with no parameters
        wait_not_busy;
        expect("ERR after missing params", d & 8'h20, 8'h20);
        z80_out(8'h53, 8'h00);                  // NOP clears ERR
        wait_not_busy;
        expect("ERR cleared by NOP", d & 8'h20, 8'h00);

        $display("--- ports outside the block are ignored");
        z80_out(8'h54, 8'hEE);
        z80_in(8'h53, d); expect("STATUS unchanged", d & 8'hA1, 8'h00);

        $display("");
        $display("bus contention events: %0d (>10 ns), %0d brief switching overlaps, worst %0.1f ns",
                 contention, short_clashes, worst_clash);
        $display("WAIT states inserted : %0d", wait_states);
        $display("WAIT timeouts        : %0d", `CORE.u_xbus.tmo);
        if (contention) errors = errors + 1;
        if (errors == 0) $display("RESULT: PASS");
        else             $display("RESULT: FAIL (%0d errors)", errors);
        $finish;
    end
endmodule
