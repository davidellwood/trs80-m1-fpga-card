`timescale 1ns/1ps
// ---------------------------------------------------------------------------
// xbus: owner of the shared 8-bit FD bus (FPGA side of the 2N7000 shifters).
//
// On the board the FD/XD bus connects to BOTH
//   * the IDT7132 right port (enabled by R_CE_N; OE_R is tied low!), and
//   * U3, the 74HCT245 to the Z80 data bus (enabled by PORT_OE_N, DIR = IN_N).
// This single state machine sequences all use of that bus, so the DPRAM,
// U3 and the FPGA can never drive it at the same time.
//
// Z80 port cycles (IORD/IOWR from U5 via U6) have priority. As soon as a
// strobe is seen, WAIT_DRV is raised (the Z80 samples WAIT in the automatic
// I/O wait state), and released only when read data has had time to settle
// through the shifter and U3, or when write data has been captured. This makes
// correctness independent of shifter rise times and of any DPRAM cycle in
// progress. A DPRAM read in progress is aborted (and retried later) when a
// port cycle arrives; a DPRAM write is always completed.
//
// DPRAM writes are CE-controlled with R/W taken low first: with OE_R tied low,
// CE low + R/W high would make the IDT7132 drive the bus.
// ---------------------------------------------------------------------------
module xbus #(
    parameter DP_RD_CLKS  = 10,     // CE low -> sample (includes shifter rise via RN1)
    parameter DP_WR_SETUP = 4,      // data driven, R/W low, before CE low
    parameter DP_WR_CLKS  = 6,      // CE-low write pulse (restarted while BUSY)
    parameter DP_TURN     = 2,      // bus turnaround after any cycle
    parameter IN_DRIVE    = 2,      // FD driven before U3 is enabled
    parameter IN_SETTLE   = 10,     // U3 enabled before WAIT is released
    parameter OUT_SETTLE  = 12,     // U3 enabled before write data is sampled
    parameter WAIT_MAX    = 13500   // WAIT cap in clocks (500 us at 27 MHz)
) (
    input  wire        clk,
    input  wire        rst,

    // ---- board pins (inputs already synchronised except fd_in) ----
    // power-up values = safe idle bus (applied at configuration, before reset)
    output reg  [10:0] ra = 11'd0,
    output reg         r_ce_n = 1'b1,
    output reg         r_rw_n = 1'b1,
    input  wire        r_busy,      // 1 = IDT7132 right-port BUSY asserted (synced)
    output reg  [7:0]  fd_out = 8'h00,
    output reg         fd_oe = 1'b0,
    input  wire [7:0]  fd_in,       // raw pins; registered here
    input  wire        iord,        // synced, active high
    input  wire        iowr,        // synced, active high
    input  wire [1:0]  pa,          // synced Z80 A1:A0
    output reg         port_oe_n = 1'b1,
    output reg         wait_drv = 1'b0,

    // ---- port register clients (selected by p_addr) ----
    output reg  [1:0]  p_addr,
    input  wire [7:0]  p_rdata,
    input  wire        p_rd_ready,
    input  wire        p_wr_ready,
    output reg         p_rd_pop,    // 1-clock pulse at the end of an IN cycle
    output reg         p_wr_stb,    // 1-clock pulse with p_wdata valid
    output reg  [7:0]  p_wdata,

    // ---- DPRAM client (request held until dp_ack) ----
    input  wire        dp_req,
    input  wire        dp_we,
    input  wire [10:0] dp_addr,
    input  wire [7:0]  dp_wdata,
    output reg         dp_ack,      // 1-clock pulse; dp_rdata valid for reads
    output reg  [7:0]  dp_rdata,

    // ---- status ----
    output reg         wait_timeout,  // 1-clock pulse when the WAIT cap was hit
    output wire        port_active,
    output wire        dp_active,
    output wire        in_drive       // FD is being driven for a Z80 IN cycle
);
    localparam S_IDLE    = 4'd0,
               S_DR      = 4'd1,
               S_DW_SET  = 4'd2,
               S_DW_PULS = 4'd3,
               S_DW_END  = 4'd4,
               S_TURN    = 4'd5,
               S_PI_RDY  = 4'd6,
               S_PI_DRV  = 4'd7,
               S_PI_SET  = 4'd8,
               S_PI_HOLD = 4'd9,
               S_PI_END  = 4'd10,
               S_PO_RDY  = 4'd11,
               S_PO_SET  = 4'd12,
               S_PO_HOLD = 4'd13;

    reg [3:0]  st = S_IDLE;
    reg [7:0]  cnt = 8'd0;
    reg [7:0]  fd_q = 8'h00;
    reg        wrel = 1'b0;   // WAIT released for the current port cycle
    reg [13:0] wcnt = 14'd0;  // WAIT duration counter
    reg        tmo = 1'b0;    // WAIT cap reached in this cycle
    reg        busy_seen = 1'b0;

    wire strobe = iord | iowr;

    assign port_active = (st >= S_PI_RDY);
    assign dp_active   = (st >= S_DR) && (st <= S_DW_END);
    assign in_drive    = (st >= S_PI_DRV) && (st <= S_PI_END);

    always @(posedge clk) begin
        fd_q <= fd_in;
        p_rd_pop     <= 1'b0;
        p_wr_stb     <= 1'b0;
        dp_ack       <= 1'b0;
        wait_timeout <= 1'b0;

        // WAIT: raised as soon as a strobe is seen, until released or capped
        if (!strobe) begin
            wrel <= 1'b0;
            tmo  <= 1'b0;
            wcnt <= 14'd0;
        end else if (!wrel) begin
            if (wcnt == WAIT_MAX) begin
                wrel         <= 1'b1;
                tmo          <= 1'b1;
                wait_timeout <= 1'b1;
            end else
                wcnt <= wcnt + 14'd1;
        end
        wait_drv <= strobe & ~wrel;

        if (rst) begin
            st        <= S_IDLE;
            cnt       <= 8'd0;
            ra        <= 11'd0;
            r_ce_n    <= 1'b1;
            r_rw_n    <= 1'b1;
            fd_oe     <= 1'b0;
            fd_out    <= 8'h00;
            port_oe_n <= 1'b1;
            wait_drv  <= 1'b0;
            wrel      <= 1'b0;
            tmo       <= 1'b0;
            wcnt      <= 14'd0;
            busy_seen <= 1'b0;
            p_addr    <= 2'd0;
        end else case (st)
            // ------------------------------------------------------------
            S_IDLE: begin
                if (strobe) begin
                    p_addr <= pa;
                    fd_oe  <= 1'b0;
                    st     <= iord ? S_PI_RDY : S_PO_RDY;
                end else if (dp_req) begin
                    ra <= dp_addr;
                    if (dp_we) begin
                        fd_out <= dp_wdata;
                        fd_oe  <= 1'b1;
                        r_rw_n <= 1'b0;          // R/W low first (CE still high)
                        cnt    <= DP_WR_SETUP;
                        st     <= S_DW_SET;
                    end else begin
                        fd_oe  <= 1'b0;
                        r_rw_n <= 1'b1;
                        r_ce_n <= 1'b0;
                        cnt    <= DP_RD_CLKS;
                        st     <= S_DR;
                    end
                end
            end
            // ---------------- DPRAM read --------------------------------
            S_DR: begin
                if (strobe) begin                // abort; request stays pending
                    r_ce_n <= 1'b1;
                    cnt    <= DP_TURN;
                    st     <= S_TURN;
                end else if (cnt == 0) begin
                    dp_rdata <= fd_q;
                    r_ce_n   <= 1'b1;
                    dp_ack   <= 1'b1;
                    cnt      <= DP_TURN;
                    st       <= S_TURN;
                end else
                    cnt <= cnt - 8'd1;
            end
            // ---------------- DPRAM write -------------------------------
            S_DW_SET: begin
                if (cnt == 0) begin
                    r_ce_n    <= 1'b0;
                    busy_seen <= 1'b0;
                    cnt       <= DP_WR_CLKS;
                    st        <= S_DW_PULS;
                end else
                    cnt <= cnt - 8'd1;
            end
            S_DW_PULS: begin
                if (r_busy)
                    busy_seen <= 1'b1;
                if (cnt == 0) begin
                    if (r_busy) begin            // still blocked: keep pulse going
                        cnt <= DP_WR_CLKS;
                    end else if (busy_seen) begin  // blocked earlier: one clean pulse
                        busy_seen <= 1'b0;
                        cnt       <= DP_WR_CLKS;
                    end else begin
                        r_ce_n <= 1'b1;          // end of write (CE-controlled)
                        st     <= S_DW_END;
                    end
                end else
                    cnt <= cnt - 8'd1;
            end
            S_DW_END: begin
                r_rw_n <= 1'b1;
                fd_oe  <= 1'b0;
                dp_ack <= 1'b1;
                cnt    <= DP_TURN;
                st     <= S_TURN;
            end
            S_TURN: begin
                if (cnt == 0)
                    st <= S_IDLE;
                else
                    cnt <= cnt - 8'd1;
            end
            // ---------------- Z80 IN (port read) ------------------------
            S_PI_RDY: begin
                if (!iord) begin                 // strobe vanished
                    cnt <= DP_TURN;
                    st  <= S_TURN;
                end else if (p_rd_ready || tmo) begin
                    fd_out <= p_rdata;
                    fd_oe  <= 1'b1;
                    cnt    <= IN_DRIVE;
                    st     <= S_PI_DRV;
                end
            end
            S_PI_DRV: begin
                if (cnt == 0) begin
                    port_oe_n <= 1'b0;           // U3: FD/XD -> Z80 D bus
                    cnt       <= IN_SETTLE;
                    st        <= S_PI_SET;
                end else
                    cnt <= cnt - 8'd1;
            end
            S_PI_SET: begin
                if (cnt == 0) begin
                    wrel <= 1'b1;                // data settled: let the Z80 go
                    st   <= S_PI_HOLD;
                end else
                    cnt <= cnt - 8'd1;
            end
            S_PI_HOLD: begin
                if (!iord) begin
                    port_oe_n <= 1'b1;
                    p_rd_pop  <= 1'b1;           // consume (Am9511 pop, result FIFO)
                    cnt       <= 8'd1;
                    st        <= S_PI_END;
                end
            end
            S_PI_END: begin
                if (cnt == 0) begin
                    fd_oe <= 1'b0;
                    cnt   <= DP_TURN;
                    st    <= S_TURN;
                end else
                    cnt <= cnt - 8'd1;
            end
            // ---------------- Z80 OUT (port write) ----------------------
            S_PO_RDY: begin
                if (!iowr) begin
                    cnt <= DP_TURN;
                    st  <= S_TURN;
                end else if (p_wr_ready || tmo) begin
                    port_oe_n <= 1'b0;           // U3: Z80 D bus -> XD/FD
                    cnt       <= OUT_SETTLE;
                    st        <= S_PO_SET;
                end
            end
            S_PO_SET: begin
                if (!iowr) begin                 // too short to trust: drop it
                    port_oe_n <= 1'b1;
                    cnt       <= DP_TURN;
                    st        <= S_TURN;
                end else if (cnt == 0) begin
                    p_wdata  <= fd_q;
                    p_wr_stb <= 1'b1;
                    wrel     <= 1'b1;
                    st       <= S_PO_HOLD;
                end else
                    cnt <= cnt - 8'd1;
            end
            S_PO_HOLD: begin
                if (!iowr) begin
                    port_oe_n <= 1'b1;
                    cnt       <= DP_TURN;
                    st        <= S_TURN;
                end
            end
            default: st <= S_IDLE;
        endcase
    end
endmodule
