`timescale 1ns/1ps
// ---------------------------------------------------------------------------
// gfx_regs: sprite-engine port front end (ports +2 PARAM/RESULT, +3 CMD/STATUS)
// implementing the protocol in docs/sprite-engine.md. Commands are executed by
// sprite_engine.v.
//
//   OUT +2  push parameter byte (64-deep FIFO; overflow sets ERR)
//   IN  +2  pop result byte (16-deep FIFO; empty reads 0xFF and sets ERR)
//   OUT +3  command: the parameters pushed so far belong to it
//   IN  +3  STATUS = {BUSY, FRAME, ERR, HIT, 3'b0, RDY}
//
// A command written while BUSY is ignored and sets ERR. When a command
// finishes, any of its parameters the engine did not consume are discarded;
// parameters pushed while it was running are kept for the next command.
// ---------------------------------------------------------------------------
module gfx_regs (
    input  wire        clk,
    input  wire        rst,
    // port interface
    input  wire        sel_c,       // 0 = PARAM/RESULT, 1 = CMD/STATUS
    input  wire        wr_stb,
    input  wire [7:0]  wdata,
    input  wire        rd_pop,
    output wire [7:0]  rdata,
    output wire        rd_ready,
    output wire        wr_ready,
    // engine interface
    output reg         cmd_start,   // 1-clock pulse
    output reg  [7:0]  cmd_code,
    output reg  [6:0]  cmd_np,      // parameters available to this command
    output wire [7:0]  p_data,      // head of the parameter FIFO
    output wire        p_avail,
    input  wire        p_pop,       // same-cycle pop of p_data
    input  wire        r_push,
    input  wire [7:0]  r_data,
    input  wire        eng_busy,
    input  wire        eng_done,    // 1-clock pulse at the end of a command
    input  wire        eng_err,     // 1-clock pulse: command rejected
    input  wire        fifo_clr,    // RESET command: clear both FIFOs
    input  wire        frame,
    input  wire        hit,
    output wire        busy
);
    reg [7:0] pf [0:63];
    reg [5:0] pf_wp = 0, pf_rp = 0;
    reg [6:0] pf_n = 0;
    reg [7:0] rf [0:15];
    reg [3:0] rf_wp = 0, rf_rp = 0;
    reg [4:0] rf_n = 0;
    reg       err = 1'b0;
    reg       running = 1'b0;
    reg [6:0] popped = 0;

    assign busy     = running | eng_busy;
    wire [7:0] status = {busy, frame, err, hit, 3'b000, (rf_n != 0)};
    assign rdata    = sel_c ? status : ((rf_n != 0) ? rf[rf_rp] : 8'hFF);
    assign rd_ready = 1'b1;
    assign wr_ready = 1'b1;
    assign p_data   = pf[pf_rp];
    assign p_avail  = running && (popped != cmd_np) && (pf_n != 0);

    wire push_ok  = wr_stb && !sel_c && (pf_n != 7'd64);
    wire pop_ok   = p_pop && p_avail;
    wire rpop_ok  = rd_pop && !sel_c && (rf_n != 0);
    wire rpush_ok = r_push && (rf_n != 5'd16);
    // on completion, drop this command's unconsumed parameters
    wire [6:0] drop = (eng_done && running) ? (cmd_np - popped - (pop_ok ? 7'd1 : 7'd0)) : 7'd0;

    always @(posedge clk) begin
        cmd_start <= 1'b0;
        if (rst) begin
            pf_wp <= 0; pf_rp <= 0; pf_n <= 0;
            rf_wp <= 0; rf_rp <= 0; rf_n <= 0;
            err <= 1'b0; running <= 1'b0; popped <= 0;
            cmd_code <= 8'h00; cmd_np <= 0;
        end else begin
            // ---------- parameter FIFO ----------
            if (wr_stb && !sel_c && !push_ok) err <= 1'b1;   // overflow
            if (push_ok) begin
                pf[pf_wp] <= wdata;
                pf_wp <= pf_wp + 6'd1;
            end
            pf_rp <= pf_rp + (pop_ok ? 6'd1 : 6'd0) + drop[5:0];
            pf_n  <= pf_n + (push_ok ? 7'd1 : 7'd0) - (pop_ok ? 7'd1 : 7'd0) - drop;
            if (pop_ok) popped <= popped + 7'd1;

            // ---------- result FIFO ----------
            if (rd_pop && !sel_c && !rpop_ok) err <= 1'b1;   // read when empty
            if (r_push && !rpush_ok) err <= 1'b1;             // overflow
            if (rpush_ok) begin
                rf[rf_wp] <= r_data;
                rf_wp <= rf_wp + 4'd1;
            end
            if (rpop_ok) rf_rp <= rf_rp + 4'd1;
            rf_n <= rf_n + (rpush_ok ? 5'd1 : 5'd0) - (rpop_ok ? 5'd1 : 5'd0);

            // ---------- commands ----------
            if (wr_stb && sel_c) begin
                if (busy)
                    err <= 1'b1;                 // CMD while BUSY: ignored
                else begin
                    err       <= 1'b0;           // ERR clears on an accepted CMD
                    cmd_code  <= wdata;
                    cmd_np    <= pf_n;
                    popped    <= 0;
                    running   <= 1'b1;
                    cmd_start <= 1'b1;
                end
            end
            if (eng_err) err <= 1'b1;
            if (eng_done && running) running <= 1'b0;

            // ---------- RESET command ----------
            if (fifo_clr) begin
                pf_wp <= 0; pf_rp <= 0; pf_n <= 0;
                rf_wp <= 0; rf_rp <= 0; rf_n <= 0;
                popped <= cmd_np;
            end
        end
    end
endmodule
