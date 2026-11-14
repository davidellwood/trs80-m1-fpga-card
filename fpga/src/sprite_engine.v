`timescale 1ns/1ps
// ---------------------------------------------------------------------------
// sprite_engine: executes the sprite/graphics command set (docs/sprite-engine.md)
//
// Screen model: 64x16 characters; codes 0x80-0xBF are 2x3 block graphics,
// giving 128x48 pixels. Cell bits: bit0 top-left, bit1 top-right, bit2
// mid-left, bit3 mid-right, bit4 bottom-left, bit5 bottom-right.
//
// Memories (block RAM): background map (1K), working frame (1K), shape
// bitmaps (64 x 16 rows x 16 bits), pixel ownership map (128x48 x 6 bits,
// 0 = none, n+1 = sprite n) for collisions.
//
// Drawing rules (mirrored exactly by sim/sprite_model.py):
//   * background drawing (PLOT/LINE/BOX): the cell becomes a graphics cell;
//     if it was not one, it starts from 0x80 (text is overwritten).
//   * sprites: only graphics cells and blanks (0x20) are modified; text is
//     left alone. OPAQUE first clears every pixel of the sprite's bounding
//     box with the background rule (so text under it becomes graphics).
//   * collisions are on logical pixels (also over text), between sprites
//     without NOCOLLIDE; masks and HIT are rebuilt on every RENDER.
//   * RENDER: velocities added, background copied, sprites 0..31 drawn in
//     order, frame copied to DPRAM 0x000-0x3FF, FRAME set.
// ---------------------------------------------------------------------------
module sprite_engine #(
    parameter        AUTO_TICK = 450000,      // clocks per 1/60 s at 27 MHz
    parameter [7:0]  VER_MAJOR = 8'd0,
    parameter [7:0]  VER_MINOR = 8'd2
) (
    input  wire        clk,
    input  wire        rst,
    // command interface (from gfx_regs)
    input  wire        cmd_start,
    input  wire [7:0]  cmd_code,
    input  wire [6:0]  cmd_np,
    input  wire [7:0]  p_data,
    input  wire        p_avail,
    output wire        p_pop,
    output reg         r_push,
    output reg  [7:0]  r_data,
    output wire        busy,
    output reg         done,
    output reg         err_p,
    output reg         fifo_clr,
    output reg         frame,
    output reg         hit_any,
    // DPRAM (to xbus)
    output reg         dp_req,
    output reg         dp_we,
    output reg  [10:0] dp_addr,
    output reg  [7:0]  dp_wdata,
    input  wire        dp_ack,
    input  wire [7:0]  dp_rdata
);
    // ---------------- memories ----------------
    reg  [9:0]  bg_a;  reg bg_we;  reg [7:0]  bg_d;  wire [7:0]  bg_q;
    reg  [9:0]  wk_a;  reg wk_we;  reg [7:0]  wk_d;  wire [7:0]  wk_q;
    reg  [9:0]  sh_a;  reg sh_we;  reg [15:0] sh_d;  wire [15:0] sh_q;
    reg  [12:0] ow_a;  reg ow_we;  reg [5:0]  ow_d;  wire [5:0]  ow_q;
    spram #(.AW(10), .DW(8))  u_bg (.clk(clk), .we(bg_we), .a(bg_a), .d(bg_d), .q(bg_q));
    spram #(.AW(10), .DW(8))  u_wk (.clk(clk), .we(wk_we), .a(wk_a), .d(wk_d), .q(wk_q));
    spram #(.AW(10), .DW(16)) u_sh (.clk(clk), .we(sh_we), .a(sh_a), .d(sh_d), .q(sh_q));
    spram #(.AW(13), .DW(6), .DEPTH(6144)) u_ow (.clk(clk), .we(ow_we), .a(ow_a), .d(ow_d), .q(ow_q));

    // shape sizes and sprite table
    reg [4:0] shw [0:63];
    reg [3:0] shh [0:63];
    reg [5:0] s_shape [0:31];
    reg [7:0] s_x [0:31], s_y [0:31], s_dx [0:31], s_dy [0:31];
    reg [5:0] s_fl [0:31];
    // single registered write port for the sprite table (applied next clock)
    // sw_en bits: 0 shape, 1 x, 2 y, 3 dx, 4 dy, 5 flags
    reg [5:0] sw_en = 6'd0;
    reg [4:0] sw_a;
    reg [5:0] sw_shape, sw_fl;
    reg [7:0] sw_x, sw_y, sw_dx, sw_dy;
    always @(posedge clk) begin
        if (sw_en[0]) s_shape[sw_a] <= sw_shape;
        if (sw_en[1]) s_x[sw_a]     <= sw_x;
        if (sw_en[2]) s_y[sw_a]     <= sw_y;
        if (sw_en[3]) s_dx[sw_a]    <= sw_dx;
        if (sw_en[4]) s_dy[sw_a]    <= sw_dy;
        if (sw_en[5]) s_fl[sw_a]    <= sw_fl;
    end
    reg [31:0] hit_ram [0:31];            // bit m of word n: sprite n touched m
    reg [4:0]  hm;                        // other sprite in a collision

    localparam F_VIS = 0, F_XOR = 1, F_MX = 2, F_MY = 3, F_OPQ = 4, F_NOC = 5;

    // ---------------- state ----------------
    localparam E_IDLE  = 6'd0,  E_FETCH = 6'd1,  E_DISP  = 6'd2,  E_DONE  = 6'd3,
               E_ERR   = 6'd4,  E_PUSH  = 6'd5,
               E_CLR   = 6'd6,  E_BGF   = 6'd7,
               E_BGL0  = 6'd8,  E_BGL1  = 6'd9,
               E_PIX0  = 6'd10, E_PIX1  = 6'd11, E_PIX2  = 6'd12,
               E_LINE  = 6'd13, E_LINE2 = 6'd14,
               E_BOX   = 6'd15, E_BOX2  = 6'd16,
               E_SCA0  = 6'd17, E_SCA1  = 6'd18, E_SCA2  = 6'd19,
               E_SCB0  = 6'd20, E_SCB1  = 6'd21, E_SCB2  = 6'd22,
               E_SHD0  = 6'd23, E_SHD1  = 6'd24,
               E_SHL0  = 6'd25, E_SHL1  = 6'd26, E_SHL2  = 6'd27,
               E_R0    = 6'd28, E_R1    = 6'd29, E_R2    = 6'd30, E_R3 = 6'd31, E_R4 = 6'd32,
               E_R5    = 6'd33, E_RS    = 6'd34, E_RROW0 = 6'd35, E_RROW1 = 6'd36,
               E_RROW2 = 6'd37, E_RCOL  = 6'd38, E_RADV  = 6'd39, E_RNX = 6'd40,
               E_RO0   = 6'd41, E_RO1   = 6'd42, E_RO2   = 6'd43, E_RO3 = 6'd44,
               E_DFILL = 6'd45, E_PEEK  = 6'd46, E_POKE  = 6'd47,
               E_HIT0  = 6'd48, E_HIT1  = 6'd49;

    reg [5:0]  st = E_CLR;
    reg [7:0]  cmd;
    reg [6:0]  np;
    reg [2:0]  k, kmax;
    reg [7:0]  arg [0:5];
    reg [7:0]  res [0:3];
    reg [2:0]  res_n, res_i;
    reg [12:0] i;                         // general loop counter
    reg        auto_cmd;                  // current RENDER started by the timer

    // pixel unit request
    reg signed [9:0] px, py;
    reg [1:0]  pop_m;                     // 0 clear, 1 set, 2 xor
    reg        p_wk, p_srule, p_coll;
    reg [5:0]  p_ret;
    reg [3:0]  pbit;
    reg [5:0]  cur_id;

    // line / box
    reg signed [10:0] lx, ly, lx1, ly1, ldx, ldy, lerr, lsx, lsy;
    reg [7:0]  bi, bj;

    // render
    reg [4:0]  n;
    reg        pass;                      // 0 = OPAQUE clear pass, 1 = draw
    reg [5:0]  rsh;
    reg [4:0]  rw;
    reg [3:0]  rh, r;
    reg [4:0]  c;
    reg [15:0] roww;

    // shape def/load
    reg [7:0]  tmp_hi;
    reg [10:0] src;

    // auto render
    reg [7:0]  auto_rate = 8'd0;
    reg [7:0]  auto_cnt  = 8'd0;
    reg [19:0] tick      = 20'd0;
    reg        auto_pend = 1'b0;

    assign busy  = (st != E_IDLE);
    assign p_pop = (st == E_FETCH && k != kmax) || (st == E_SHD0) || (st == E_SHD1);

    // parameter counts (fixed part)
    function [2:0] need(input [7:0] cc);
        case (cc)
            8'h08: need = 3'd1;  8'h09: need = 3'd2;  8'h0A: need = 3'd3;
            8'h0B: need = 3'd3;  8'h0C: need = 3'd5;  8'h0D: need = 3'd6;
            8'h0E: need = 3'd2;  8'h10: need = 3'd3;  8'h11: need = 3'd5;
            8'h20: need = 3'd5;  8'h21: need = 3'd3;  8'h22: need = 3'd2;
            8'h23: need = 3'd2;  8'h24: need = 3'd3;  8'h25: need = 3'd1;
            8'h30: need = 3'd1;  8'h41: need = 3'd1;
            8'hF0: need = 3'd1;  8'hF1: need = 3'd2;  8'hF2: need = 3'd3;
            default: need = 3'd0;
        endcase
    endfunction
    function known(input [7:0] cc);
        case (cc)
            8'h00, 8'h01, 8'h02, 8'h08, 8'h09, 8'h0A, 8'h0B, 8'h0C, 8'h0D, 8'h0E,
            8'h10, 8'h11, 8'h20, 8'h21, 8'h22, 8'h23, 8'h24, 8'h25, 8'h30,
            8'h40, 8'h41, 8'hF0, 8'hF1, 8'hF2: known = 1'b1;
            default: known = 1'b0;
        endcase
    endfunction

    // pixel coordinates -> cell / bit
    wire [5:0] pyu   = py[5:0];
    wire [15:0] pmul = {10'b0, pyu} * 16'd171;
    wire [3:0] prow  = pmul[12:9];                       // pyu / 3 for 0..47
    wire [5:0] prem  = pyu - {1'b0, prow, 1'b0} - {2'b0, prow};
    wire [1:0] psub  = prem[1:0];
    wire [9:0] pcell = {prow, px[6:1]};
    wire [3:0] pbitn = {psub, 1'b0} + px[0];
    wire       ponscr = (px >= 0) && (px < 128) && (py >= 0) && (py < 48);

    // pixel RMW result
    wire [7:0] pold  = p_wk ? wk_q : bg_q;
    wire       pisg  = (pold[7:6] == 2'b10);
    wire       pisb  = (pold == 8'h20);
    wire [5:0] pbits = pisg ? pold[5:0] : 6'd0;
    wire [5:0] pmask = 6'd1 << pbit;
    wire [5:0] pnew  = (pop_m == 2'd0) ? (pbits & ~pmask) :
                       (pop_m == 2'd1) ? (pbits | pmask)  : (pbits ^ pmask);

    // render helpers
    wire [3:0] rr      = s_fl[n][F_MY] ? (rh - 4'd1 - r) : r;
    wire [4:0] cc_     = s_fl[n][F_MX] ? (rw - 5'd1 - c) : c;
    wire       rbit    = roww[5'd15 - cc_];

    // collision RAM: single port, address chosen by state
    wire [4:0]  ha = (st == E_HIT0) ? cur_id[4:0] :
                     (st == E_HIT1) ? hm :
                     (st == E_DISP) ? arg[0][4:0] : i[4:0];
    wire [31:0] hq = hit_ram[ha];

    always @(posedge clk) begin
        bg_we <= 1'b0; wk_we <= 1'b0; sh_we <= 1'b0; ow_we <= 1'b0;
        r_push <= 1'b0; done <= 1'b0; err_p <= 1'b0; fifo_clr <= 1'b0;
        sw_en <= 6'd0;

        // ---- auto-render timer ----
        if (auto_rate == 0) begin
            tick <= 0; auto_cnt <= 0;
        end else if (tick == AUTO_TICK - 1) begin
            tick <= 0;
            if (auto_cnt == auto_rate - 1) begin
                auto_cnt  <= 0;
                auto_pend <= 1'b1;
            end else
                auto_cnt <= auto_cnt + 8'd1;
        end else
            tick <= tick + 20'd1;

        case (st)
        // =========================================================
        E_IDLE: begin
            if (cmd_start) begin
                cmd      <= cmd_code;
                np       <= cmd_np;
                auto_cmd <= 1'b0;
                if (!known(cmd_code) || cmd_np < need(cmd_code))
                    st <= E_ERR;
                else begin
                    k <= 0; kmax <= need(cmd_code);
                    st <= E_FETCH;
                end
            end else if (auto_pend) begin
                auto_pend <= 1'b0;
                auto_cmd  <= 1'b1;
                cmd       <= 8'h40;
                st        <= E_R0;
            end
        end
        E_FETCH: begin
            if (k != kmax) begin
                arg[k] <= p_data;
                k <= k + 3'd1;
            end else
                st <= E_DISP;
        end
        E_ERR:  begin err_p <= 1'b1; done <= 1'b1; st <= E_IDLE; end
        E_DONE: begin done <= 1'b1; st <= E_IDLE; end
        E_PUSH: begin
            r_push <= 1'b1;
            r_data <= res[res_i];
            res_i  <= res_i + 3'd1;
            if (res_i == res_n - 3'd1) st <= E_DONE;
        end
        // =========================================================
        E_DISP: begin
            case (cmd)
            8'h00: st <= E_DONE;
            8'h01: begin fifo_clr <= 1'b1; i <= 0; st <= E_CLR; end
            8'h02: begin
                res[0] <= VER_MAJOR; res[1] <= VER_MINOR; res[2] <= 8'd32; res[3] <= 8'd64;
                res_n <= 3'd4; res_i <= 0; st <= E_PUSH;
            end
            8'h08: begin i <= 0; bg_d <= arg[0]; st <= E_BGF; end
            8'h09: begin src <= {arg[1][2:0], arg[0]}; i <= 0; st <= E_BGL0; end
            8'h0A: begin
                if (arg[0] >= 64 || arg[1] >= 16) st <= E_ERR;
                else begin
                    bg_a <= {arg[1][3:0], arg[0][5:0]}; bg_d <= arg[2]; bg_we <= 1'b1;
                    st <= E_DONE;
                end
            end
            8'h0B: begin
                if (arg[2] > 2) st <= E_ERR;
                else begin
                    px <= {2'b00, arg[0]}; py <= {2'b00, arg[1]}; pop_m <= arg[2][1:0];
                    p_wk <= 1'b0; p_srule <= 1'b0; p_coll <= 1'b0; p_ret <= E_DONE;
                    st <= E_PIX0;
                end
            end
            8'h0C: begin
                if (arg[4] > 2) st <= E_ERR;
                else begin
                    lx <= {3'b000, arg[0]}; ly <= {3'b000, arg[1]};
                    lx1 <= {3'b000, arg[2]}; ly1 <= {3'b000, arg[3]};
                    ldx <= (arg[2] >= arg[0]) ? ({3'b000, arg[2]} - {3'b000, arg[0]})
                                              : ({3'b000, arg[0]} - {3'b000, arg[2]});
                    ldy <= (arg[3] >= arg[1]) ? ({3'b000, arg[1]} - {3'b000, arg[3]})
                                              : ({3'b000, arg[3]} - {3'b000, arg[1]});
                    lsx <= (arg[0] < arg[2]) ? 11'sd1 : -11'sd1;
                    lsy <= (arg[1] < arg[3]) ? 11'sd1 : -11'sd1;
                    lerr <= ((arg[2] >= arg[0]) ? ({3'b000, arg[2]} - {3'b000, arg[0]})
                                                : ({3'b000, arg[0]} - {3'b000, arg[2]}))
                          + ((arg[3] >= arg[1]) ? ({3'b000, arg[1]} - {3'b000, arg[3]})
                                                : ({3'b000, arg[3]} - {3'b000, arg[1]}));
                    pop_m <= arg[4][1:0]; p_wk <= 1'b0; p_srule <= 1'b0; p_coll <= 1'b0;
                    st <= E_LINE;
                end
            end
            8'h0D: begin
                if (arg[4] > 2) st <= E_ERR;
                else if (arg[2] == 0 || arg[3] == 0) st <= E_DONE;
                else begin
                    bi <= 0; bj <= 0; pop_m <= arg[4][1:0];
                    p_wk <= 1'b0; p_srule <= 1'b0; p_coll <= 1'b0;
                    st <= E_BOX;
                end
            end
            8'h0E: begin i <= 0; st <= E_SCA0; end
            8'h10: begin
                if (arg[0] >= 64 || arg[1] == 0 || arg[1] > 16 || arg[2] == 0 || arg[2] > 15 ||
                    np < 7'd3 + {arg[2][3:0], 1'b0})
                    st <= E_ERR;
                else begin
                    shw[arg[0][5:0]] <= arg[1][4:0]; shh[arg[0][5:0]] <= arg[2][3:0];
                    r <= 0; st <= E_SHD0;
                end
            end
            8'h11: begin
                if (arg[0] >= 64 || arg[1] == 0 || arg[1] > 16 || arg[2] == 0 || arg[2] > 15)
                    st <= E_ERR;
                else begin
                    shw[arg[0][5:0]] <= arg[1][4:0]; shh[arg[0][5:0]] <= arg[2][3:0];
                    src <= {arg[4][2:0], arg[3]}; r <= 0; st <= E_SHL0;
                end
            end
            8'h20: begin
                if (arg[0] >= 32 || arg[1] >= 64) st <= E_ERR;
                else begin
                    sw_a <= arg[0][4:0]; sw_shape <= arg[1][5:0];
                    sw_x <= arg[2]; sw_y <= arg[3]; sw_fl <= arg[4][5:0];
                    sw_en <= 6'b100111;
                    st <= E_DONE;
                end
            end
            8'h21: begin
                if (arg[0] >= 32) st <= E_ERR;
                else begin
                    sw_a <= arg[0][4:0]; sw_x <= arg[1]; sw_y <= arg[2]; sw_en <= 6'b000110;
                    st <= E_DONE;
                end
            end
            8'h22: begin
                if (arg[0] >= 32) st <= E_ERR;
                else begin sw_a <= arg[0][4:0]; sw_fl <= arg[1][5:0]; sw_en <= 6'b100000; st <= E_DONE; end
            end
            8'h23: begin
                if (arg[0] >= 32 || arg[1] >= 64) st <= E_ERR;
                else begin sw_a <= arg[0][4:0]; sw_shape <= arg[1][5:0]; sw_en <= 6'b000001; st <= E_DONE; end
            end
            8'h24: begin
                if (arg[0] >= 32) st <= E_ERR;
                else begin
                    sw_a <= arg[0][4:0]; sw_dx <= arg[1]; sw_dy <= arg[2]; sw_en <= 6'b011000;
                    st <= E_DONE;
                end
            end
            8'h25: begin
                if (arg[0] >= 32) st <= E_ERR;
                else begin
                    res[0] <= s_x[arg[0][4:0]]; res[1] <= s_y[arg[0][4:0]];
                    res_n <= 3'd2; res_i <= 0; st <= E_PUSH;
                end
            end
            8'h30: begin
                if (arg[0] >= 32) st <= E_ERR;
                else begin
                    res[0] <= hq[7:0];   res[1] <= hq[15:8];
                    res[2] <= hq[23:16]; res[3] <= hq[31:24];
                    res_n <= 3'd4; res_i <= 0; st <= E_PUSH;
                end
            end
            8'h40: st <= E_R0;
            8'h41: begin auto_rate <= arg[0]; auto_pend <= 1'b0; st <= E_DONE; end
            8'hF0: begin frame <= 1'b0; i <= 0; st <= E_DFILL; end
            8'hF1: begin
                dp_addr <= {arg[1][2:0], arg[0]}; dp_we <= 1'b0; dp_req <= 1'b1; st <= E_PEEK;
            end
            8'hF2: begin
                dp_addr <= {arg[1][2:0], arg[0]}; dp_wdata <= arg[2]; dp_we <= 1'b1;
                dp_req <= 1'b1; st <= E_POKE;
            end
            default: st <= E_ERR;
            endcase
        end
        // =========================================================
        // RESET / power-on: clear sprites and shapes, background = blanks
        E_CLR: begin
            if (i < 32) begin
                sw_a <= i[4:0]; sw_shape <= 0; sw_x <= 0; sw_y <= 0;
                sw_dx <= 0; sw_dy <= 0; sw_fl <= 0; sw_en <= 6'b111111;
                hit_ram[i[4:0]] <= 32'd0;
            end
            shw[i[5:0]] <= 0; shh[i[5:0]] <= 0;
            if (i == 63) begin
                hit_any <= 1'b0; frame <= 1'b0;
                auto_rate <= 0; auto_pend <= 1'b0;
                bg_d <= 8'h20; i <= 0; st <= E_BGF;
            end else
                i <= i + 13'd1;
        end
        E_BGF: begin                          // fill background with bg_d
            bg_a <= i[9:0]; bg_we <= 1'b1;
            if (i == 1023) st <= E_DONE;
            else i <= i + 13'd1;
        end
        // ---- BG_LOAD: background <- DPRAM ----
        E_BGL0: begin
            dp_addr <= src + i[10:0]; dp_we <= 1'b0; dp_req <= 1'b1; st <= E_BGL1;
        end
        E_BGL1: begin
            if (dp_ack) begin
                dp_req <= 1'b0;
                bg_a <= i[9:0]; bg_d <= dp_rdata; bg_we <= 1'b1;
                if (i == 1023) st <= E_DONE;
                else begin i <= i + 13'd1; st <= E_BGL0; end
            end
        end
        // ---- pixel read-modify-write ----
        E_PIX0: begin
            if (!ponscr) st <= p_ret;
            else begin
                if (p_wk) wk_a <= pcell; else bg_a <= pcell;
                ow_a <= {pyu, px[6:0]};
                pbit <= pbitn;
                st   <= E_PIX1;
            end
        end
        E_PIX1: st <= E_PIX2;
        E_PIX2: begin
            if (!(p_srule && !pisg && !pisb)) begin
                if (p_wk) begin wk_d <= {2'b10, pnew}; wk_we <= 1'b1; end
                else      begin bg_d <= {2'b10, pnew}; bg_we <= 1'b1; end
            end
            st <= p_ret;
            if (p_coll) begin
                ow_d <= cur_id + 6'd1; ow_we <= 1'b1;
                if (ow_q != 0) begin
                    hm      <= ow_q[4:0] - 5'd1;
                    hit_any <= 1'b1;
                    st      <= E_HIT0;
                end
            end
        end
        E_HIT0: begin                          // hit[cur] |= 1 << hm
            hit_ram[ha] <= hq | (32'd1 << hm);
            st <= E_HIT1;
        end
        E_HIT1: begin                          // hit[hm] |= 1 << cur
            hit_ram[ha] <= hq | (32'd1 << cur_id[4:0]);
            st <= p_ret;
        end
        // ---- BG_LINE (Bresenham) ----
        E_LINE: begin
            px <= lx[9:0]; py <= ly[9:0]; p_ret <= E_LINE2; st <= E_PIX0;
        end
        E_LINE2: begin
            if (lx == lx1 && ly == ly1) st <= E_DONE;
            else begin : step
                reg signed [11:0] e2;
                e2 = {lerr, 1'b0};
                if (e2 >= ldy && e2 <= ldx) begin
                    lerr <= lerr + ldy + ldx; lx <= lx + lsx; ly <= ly + lsy;
                end else if (e2 >= ldy) begin
                    lerr <= lerr + ldy; lx <= lx + lsx;
                end else if (e2 <= ldx) begin
                    lerr <= lerr + ldx; ly <= ly + lsy;
                end
                st <= E_LINE;
            end
        end
        // ---- BG_BOX ----
        E_BOX: begin
            if (arg[5] != 0 || bi == 0 || bi == arg[3] - 8'd1 || bj == 0 || bj == arg[2] - 8'd1) begin
                px <= {2'b00, arg[0]} + {2'b00, bj};
                py <= {2'b00, arg[1]} + {2'b00, bi};
                p_ret <= E_BOX2; st <= E_PIX0;
            end else
                st <= E_BOX2;
        end
        E_BOX2: begin
            if (bj == arg[2] - 8'd1) begin
                bj <= 0;
                if (bi == arg[3] - 8'd1) st <= E_DONE;
                else begin bi <= bi + 8'd1; st <= E_BOX; end
            end else begin
                bj <= bj + 8'd1; st <= E_BOX;
            end
        end
        // ---- BG_SCROLL: bg -> wk shifted, then wk -> bg ----
        E_SCA0: begin : sca
            reg signed [7:0] sr, sc;
            sr = $signed({4'b0, i[9:6]}) - $signed(arg[1]);
            sc = $signed({2'b0, i[5:0]}) - $signed(arg[0]);
            tmp_hi <= (sr >= 0 && sr < 16 && sc >= 0 && sc < 64) ? 8'h01 : 8'h00;
            bg_a <= {sr[3:0], sc[5:0]};
            st <= E_SCA1;
        end
        E_SCA1: st <= E_SCA2;
        E_SCA2: begin
            wk_a <= i[9:0]; wk_d <= tmp_hi[0] ? bg_q : 8'h20; wk_we <= 1'b1;
            if (i == 1023) begin i <= 0; st <= E_SCB0; end
            else begin i <= i + 13'd1; st <= E_SCA0; end
        end
        E_SCB0: begin wk_a <= i[9:0]; st <= E_SCB1; end
        E_SCB1: st <= E_SCB2;
        E_SCB2: begin
            bg_a <= i[9:0]; bg_d <= wk_q; bg_we <= 1'b1;
            if (i == 1023) st <= E_DONE;
            else begin i <= i + 13'd1; st <= E_SCB0; end
        end
        // ---- SHAPE_DEF: stream h rows of 2 bytes from the FIFO ----
        E_SHD0: begin tmp_hi <= p_data; st <= E_SHD1; end
        E_SHD1: begin
            sh_a <= {arg[0][5:0], r}; sh_d <= {tmp_hi, p_data}; sh_we <= 1'b1;
            if (r == arg[2][3:0] - 4'd1) st <= E_DONE;
            else begin r <= r + 4'd1; st <= E_SHD0; end
        end
        // ---- SHAPE_LOAD: rows from DPRAM ----
        E_SHL0: begin
            dp_addr <= src + {r, 1'b0}; dp_we <= 1'b0; dp_req <= 1'b1; st <= E_SHL1;
        end
        E_SHL1: begin
            if (dp_ack) begin
                tmp_hi <= dp_rdata;
                dp_addr <= src + {r, 1'b1};          // keep dp_req high: next byte
                st <= E_SHL2;
            end
        end
        E_SHL2: begin
            if (dp_ack) begin
                dp_req <= 1'b0;
                sh_a <= {arg[0][5:0], r}; sh_d <= {tmp_hi, dp_rdata}; sh_we <= 1'b1;
                if (r == arg[2][3:0] - 4'd1) st <= E_DONE;
                else begin r <= r + 4'd1; st <= E_SHL0; end
            end
        end
        // =========================================================
        // RENDER
        E_R0: begin frame <= 1'b0; hit_any <= 1'b0; i <= 0; st <= E_R1; end
        E_R1: begin                           // velocities, clear collision masks
            hit_ram[ha] <= 32'd0;
            sw_a <= i[4:0];
            sw_x <= s_x[i[4:0]] + s_dx[i[4:0]];
            sw_y <= s_y[i[4:0]] + s_dy[i[4:0]];
            sw_en <= 6'b000110;
            if (i == 31) begin i <= 0; st <= E_R2; end
            else i <= i + 13'd1;
        end
        E_R2: begin bg_a <= i[9:0]; st <= E_R3; end          // bg -> wk
        E_R3: st <= E_R4;
        E_R4: begin
            wk_a <= i[9:0]; wk_d <= bg_q; wk_we <= 1'b1;
            if (i == 1023) begin i <= 0; st <= E_R5; end
            else begin i <= i + 13'd1; st <= E_R2; end
        end
        E_R5: begin                           // clear ownership map
            ow_a <= i; ow_d <= 6'd0; ow_we <= 1'b1;
            if (i == 6143) begin n <= 0; st <= E_RS; end
            else i <= i + 13'd1;
        end
        E_RS: begin
            rsh <= s_shape[n];
            rw  <= shw[s_shape[n]];
            rh  <= shh[s_shape[n]];
            cur_id <= {1'b0, n};
            if (!s_fl[n][F_VIS] || shw[s_shape[n]] == 0 || shh[s_shape[n]] == 0)
                st <= E_RNX;
            else begin
                pass <= s_fl[n][F_OPQ] ? 1'b0 : 1'b1;
                r <= 0; c <= 0;
                st <= E_RROW0;
            end
        end
        E_RROW0: begin sh_a <= {rsh, rr}; st <= E_RROW1; end
        E_RROW1: st <= E_RROW2;
        E_RROW2: begin roww <= sh_q; c <= 0; st <= E_RCOL; end
        E_RCOL: begin
            if (!pass || rbit) begin
                px <= $signed({{2{s_x[n][7]}}, s_x[n]}) + $signed({5'b0, c});
                py <= $signed({{2{s_y[n][7]}}, s_y[n]}) + $signed({6'b0, r});
                pop_m   <= !pass ? 2'd0 : (s_fl[n][F_XOR] ? 2'd2 : 2'd1);
                p_wk    <= 1'b1;
                p_srule <= pass;
                p_coll  <= pass && !s_fl[n][F_NOC];
                p_ret   <= E_RADV;
                st      <= E_PIX0;
            end else
                st <= E_RADV;
        end
        E_RADV: begin
            if (c != rw - 5'd1) begin c <= c + 5'd1; st <= E_RCOL; end
            else if (r != rh - 4'd1) begin r <= r + 4'd1; st <= E_RROW0; end
            else if (!pass) begin pass <= 1'b1; r <= 0; st <= E_RROW0; end
            else st <= E_RNX;
        end
        E_RNX: begin
            if (n == 5'd31) begin i <= 0; st <= E_RO0; end
            else begin n <= n + 5'd1; st <= E_RS; end
        end
        E_RO0: begin wk_a <= i[9:0]; st <= E_RO1; end        // wk -> DPRAM
        E_RO1: st <= E_RO2;
        E_RO2: begin
            dp_addr <= {1'b0, i[9:0]}; dp_wdata <= wk_q; dp_we <= 1'b1; dp_req <= 1'b1;
            st <= E_RO3;
        end
        E_RO3: begin
            if (dp_ack) begin
                dp_req <= 1'b0;
                if (i == 1023) begin frame <= 1'b1; st <= E_DONE; end
                else begin i <= i + 13'd1; st <= E_RO0; end
            end
        end
        // =========================================================
        // diagnostics
        E_DFILL: begin
            if (!dp_req) begin
                dp_addr <= {1'b0, i[9:0]}; dp_wdata <= arg[0]; dp_we <= 1'b1; dp_req <= 1'b1;
            end else if (dp_ack) begin
                dp_req <= 1'b0;
                if (i == 1023) begin frame <= 1'b1; st <= E_DONE; end
                else i <= i + 13'd1;
            end
        end
        E_PEEK: begin
            if (dp_ack) begin
                dp_req <= 1'b0; res[0] <= dp_rdata; res_n <= 3'd1; res_i <= 0; st <= E_PUSH;
            end
        end
        E_POKE: begin
            if (dp_ack) begin dp_req <= 1'b0; st <= E_DONE; end
        end
        default: st <= E_IDLE;
        endcase

        // Reset overrides only the control state; tables are cleared by E_CLR,
        // so their write enables need not depend on rst (shorter paths).
        if (rst) begin
            st <= E_CLR; i <= 0; dp_req <= 1'b0; frame <= 1'b0; hit_any <= 1'b0;
            auto_rate <= 0; auto_pend <= 1'b0; auto_cmd <= 1'b0; cmd <= 8'h01;
            done <= 1'b0; err_p <= 1'b0; r_push <= 1'b0; fifo_clr <= 1'b0;
        end
    end
endmodule
