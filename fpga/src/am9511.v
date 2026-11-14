`timescale 1ns/1ps
// ---------------------------------------------------------------------------
// am9511: AMD Am9511A APU compatible core (phase 1)
//
// Behaviour follows the ratboy666/am9511 emulator (see fpga/sim/apu_model.py
// for the executable definition and the list of deliberate bug fixes).
//
//   port +0 (sel_c=0): OUT = push byte, IN = pop byte (LIFO, 16-byte ring)
//   port +1 (sel_c=1): OUT = command,   IN = status
//   status = {BUSY, SIGN, ZERO, ERR[3:0], CARRY}
//   command = {SR, type[1:0], op[4:0]}; type 11 = 16-bit int, 01 = 32-bit
//   int, 00/10 = float.
//
// While BUSY, data reads/writes and command writes are held off (the bus
// controller keeps the Z80 in WAIT, like the real chip's PAUSE); status
// reads are always answered.
//
// Phase 1 implements NOP, PUPI, PTO, POP, XCH, CHS, CHSF, ADD, SUB, MUL,
// MUU, DIV (16/32-bit), FADD, FSUB, FMUL, FDIV, SQRT, FLTS, FLTD, FIXS,
// FIXD - all bit-exact to the model. SIN..PWR are not yet implemented: they
// leave the stack unchanged and report the ARG error.
//
// Datapath (sized for area): operands are read from the stack a byte per
// clock into A/B; one sequential unit computes (shift-add multiply,
// restoring divide, digit-recurrence square root, 1-bit/clock align and
// normalise, one shared 64-bit negator, one 51-bit adder/subtractor for
// float add); results are shifted back a byte per clock; SIGN/ZERO are then
// taken from the new top of stack exactly as the reference does.
// Longest operation ~150 clocks (~6 us).
// ---------------------------------------------------------------------------
module am9511 (
    input  wire       clk,
    input  wire       rst,
    input  wire       sel_c,
    input  wire       wr_stb,
    input  wire [7:0] wdata,
    input  wire       rd_pop,
    output wire [7:0] rdata,
    output wire       rd_ready,
    output wire       wr_ready,
    output reg        svreq        // SR command completed (until the next
);                                  // command or a status read)
    // ---------------- stack and status ----------------
    reg [7:0] stk [0:15];
    reg [3:0] sp = 4'd0;
    reg [7:0] status = 8'h00;
    reg       busy = 1'b0;

    assign rdata    = sel_c ? {busy, status[6:0]} : stk[sp - 4'd1];
    assign rd_ready = sel_c | ~busy;
    assign wr_ready = ~busy;

    // ---------------- command decode ----------------
    reg  [7:0] op = 8'h00;
    reg        um = 1'b0;                 // microcode (derived function) mode
    reg  [4:0] ucode = 5'd0;              // primitive issued by the microcode
    wire [4:0] code   = um ? ucode : op[4:0];
    wire       single = !um && (op[6:5] == 2'b11);
    wire [2:0] w      = single ? 3'd2 : 3'd4;

    localparam C_NOP = 5'h00, C_SQRT = 5'h01, C_PWR = 5'h0B, C_ADD = 5'h0C, C_SUB = 5'h0D,
               C_MUL = 5'h0E, C_DIV = 5'h0F, C_FADD = 5'h10, C_FSUB = 5'h11, C_FMUL = 5'h12,
               C_FDIV = 5'h13, C_CHS = 5'h14, C_CHSF = 5'h15, C_MUU = 5'h16, C_PTO = 5'h17,
               C_POP = 5'h18, C_XCH = 5'h19, C_PUPI = 5'h1A, C_FLTD = 5'h1C, C_FLTS = 5'h1D,
               C_FIXD = 5'h1E, C_FIXS = 5'h1F;

    localparam ERR_DIV0 = 4'b1000, ERR_NEG = 4'b0100, ERR_ARG = 4'b1100,
               ERR_UND = 4'b0010, ERR_OVF = 4'b0001;   // status bits 4:1

    // ---------------- state ----------------
    localparam S_IDLE = 5'd0,  S_LOAD = 5'd1,  S_LADJ = 5'd2,  S_EXEC = 5'd3,
               S_STORE = 5'd4, S_FLAG = 5'd5,  S_FLAG2 = 5'd6, S_MAG  = 5'd7,
               S_MUL  = 5'd8,  S_MULE = 5'd9,  S_DIV  = 5'd10, S_DIVE = 5'd11,
               S_ALGN = 5'd12, S_ADDS = 5'd13, S_NORM = 5'd14, S_RND  = 5'd15,
               S_PACK = 5'd16, S_SQRT = 5'd17, S_SQE  = 5'd18, S_FLTN = 5'd19,
               S_FIXS = 5'd20, S_FIXE = 5'd21, S_NEG  = 5'd22, S_OUT  = 5'd23,
               S_UE1  = 5'd24, S_UF   = 5'd25, S_UD   = 5'd26, S_UK   = 5'd27;
    reg [4:0]  st = S_IDLE;

    // ---------------- microsequencer (derived functions) ----------------
    // Program and constants come from fpga/sim/apu_ucode.py (generated file).
    reg [23:0] urom [0:511];
    reg [31:0] krom [0:63];
    reg [23:0] uq;                        // instruction at upc (1-clock ROM)
    reg [31:0] kq;                        // constant at uq[5:0]
    reg [9:0]  upc = 10'd0, ulink = 10'd0;
    reg [31:0] N = 32'd0;                 // integer register
    reg [3:0]  upend = 4'd0;              // OVF/UND from SCALE
    reg [2:0]  ud;                        // destination of a pending primitive
    reg [31:0] rf [0:7];                  // scratch float registers
    reg        rfw_en = 1'b0;             // registered write port
    reg [2:0]  rfw_a;
    reg [31:0] rfw_d;
    `include "am9511_ucode.vh"
    always @(posedge clk) begin
        uq <= urom[upc];
        kq <= krom[uq[5:0]];
        if (rfw_en) rf[rfw_a] <= rfw_d;
    end
    wire [4:0]  uopc = uq[23:19];
    wire [2:0]  ufd  = uq[18:16], ufb = uq[15:13], ufa = uq[12:10];
    wire [9:0]  uimm = uq[9:0];
    wire [31:0] ura  = rf[ufa];
    wire [31:0] urb  = rf[ufb];
    wire [9:0]  upc1 = upc + 10'd1;
    // SCALE: exponent + N (N clamped to +-255)
    wire signed [10:0] unc = ($signed(N) > 255)  ? 11'sd255 :
                             ($signed(N) < -255) ? -11'sd255 : $signed(N[10:0]);
    wire signed [10:0] uen = $signed({{4{ura[30]}}, ura[30:24]}) + unc;

    reg [2:0]  na, nb;                // operand bytes (0/2/4)
    reg [3:0]  cnt;
    reg [31:0] A, B;
    reg [31:0] R1, R2;
    reg [2:0]  r1n, r2n;
    reg        nostore;
    reg [1:0]  ftype;                 // 11 single, 01 double, else float
    reg [3:0]  errc;
    reg        carry_f;
    reg [31:0] fl;                    // flag bytes read back

    // arithmetic registers
    reg [63:0] X;                     // product / dividend+quotient / shifter
    reg [63:0] T;                     // value to (conditionally) negate
    reg        negf;                  // negate T in S_NEG
    reg        sneg;                  // sign of an integer result
    reg [32:0] Rm;                    // division remainder
    reg [31:0] D;                     // divisor / multiplicand
    reg [5:0]  it;
    reg [50:0] SA, SB;                // float add: |SB| >= |SA| after swap
    reg        addop;                 // 1 = add magnitudes, 0 = subtract
    reg signed [9:0] e;               // working exponent
    reg        sgn;
    reg [24:0] M;                     // mantissa before/after rounding
    reg        g, stk_y;              // guard / sticky
    reg [29:0] srem;                  // sqrt remainder
    reg [26:0] sroot;
    reg [53:0] sx;                    // sqrt radicand

    // unpacked float operands
    wire        az = ~A[23];
    wire        bz = ~B[23];
    wire signed [9:0] ea = {{3{A[30]}}, A[30:24]};
    wire signed [9:0] eb = {{3{B[30]}}, B[30:24]};

    // integer views (sign extended 16-bit when single)
    wire [31:0] ai   = single ? {{16{A[15]}}, A[15:0]} : A;
    wire [31:0] bi   = single ? {{16{B[15]}}, B[15:0]} : B;
    wire [31:0] smin = single ? 32'h0000_8000 : 32'h8000_0000;
    wire [31:0] wmsk = single ? 32'h0000_FFFF : 32'hFFFF_FFFF;

    // the one shared negator
    wire [63:0] nin  = (st == S_MAG) ? {{32{cnt[0] ? bi[31] : ai[31]}}, cnt[0] ? bi : ai} : T;
    wire [63:0] nout = -nin;

    // stack read address
    wire [3:0] base   = sp - {1'b0, na} - {1'b0, nb};
    reg  [3:0] raddr;
    wire [7:0] rbyte  = stk[raddr];
    always @(*) begin
        case (st)
            S_LOAD:  raddr = base + cnt;
            S_FLAG:  raddr = sp - 4'd1 - cnt;
            default: raddr = sp - 4'd1;
        endcase
    end

    always @(posedge clk) begin
        rfw_en <= 1'b0;
        if (rst) begin
            sp <= 4'd0; status <= 8'h00; busy <= 1'b0; st <= S_IDLE; svreq <= 1'b0; um <= 1'b0;
        end else case (st)
        // ====================================================== idle / io
        S_IDLE: begin
            if (wr_stb && !sel_c) begin
                stk[sp] <= wdata;
                sp <= sp + 4'd1;
            end
            if (rd_pop && !sel_c)
                sp <= sp - 4'd1;
            if (rd_pop && sel_c)
                svreq <= 1'b0;                 // status read acknowledges SVREQ
            if (wr_stb && sel_c) begin
                op <= wdata; busy <= 1'b1; svreq <= 1'b0;
                errc <= 4'd0; carry_f <= 1'b0; nostore <= 1'b0;
                r1n <= 0; r2n <= 0; cnt <= 0;
                ftype <= wdata[6:5];
                case (wdata[4:0])
                    C_NOP, 5'h1B, C_PUPI:      begin na <= 0; nb <= 0; end
                    C_FLTS:                    begin na <= 2; nb <= 0; end
                    C_ADD, C_SUB, C_MUL, C_MUU, C_DIV, C_XCH:
                        begin na <= (wdata[6:5] == 2'b11) ? 3'd2 : 3'd4;
                              nb <= (wdata[6:5] == 2'b11) ? 3'd2 : 3'd4; end
                    C_CHS, C_PTO, C_POP:
                        begin na <= (wdata[6:5] == 2'b11) ? 3'd2 : 3'd4; nb <= 0; end
                    C_FADD, C_FSUB, C_FMUL, C_FDIV, C_PWR:
                                               begin na <= 4; nb <= 4; end
                    default:                   begin na <= 4; nb <= 0; end
                endcase
                A <= 0; B <= 0;
                st <= S_LOAD;
            end
        end
        S_LOAD: begin
            if (cnt == na + nb) st <= S_LADJ;
            else begin
                if (cnt < nb) B <= {rbyte, B[31:8]};
                else          A <= {rbyte, A[31:8]};
                cnt <= cnt + 4'd1;
            end
        end
        S_LADJ: begin
            if (na == 2) A <= {16'd0, A[31:16]};
            if (nb == 2) B <= {16'd0, B[31:16]};
            st <= S_EXEC;
        end
        // ====================================================== dispatch
        S_EXEC: begin
            st <= S_STORE;
            cnt <= 0;
            case (code)
            C_NOP, 5'h1B: begin
                status <= 8'h00; busy <= 1'b0; svreq <= op[7]; st <= S_IDLE;
            end
            C_PUPI: begin R1 <= 32'h02C9_0FDA; r1n <= 4; ftype <= 2'b00; end
            C_PTO:  begin R1 <= A; R2 <= A; r1n <= w; r2n <= w; end
            C_POP:  begin end
            C_XCH:  begin R1 <= A; R2 <= B; r1n <= w; r2n <= w; end
            C_CHS: begin
                if ((ai & wmsk) == smin) begin errc <= ERR_OVF; nostore <= 1'b1; end
                else begin T <= {32'd0, ai}; negf <= 1'b1; st <= S_NEG; end
            end
            C_CHSF: begin R1 <= A[23] ? {~A[31], A[30:0]} : A; r1n <= 4; end
            C_ADD: begin : add_b
                reg [32:0] s33;
                s33 = single ? {16'd0, A[15:0]} + {16'd0, B[15:0]} : {1'b0, A} + {1'b0, B};
                carry_f <= single ? s33[16] : s33[32];
                if (single ? (A[15] == B[15] && s33[15] != A[15]) : (A[31] == B[31] && s33[31] != A[31]))
                    errc <= ERR_OVF;
                R1 <= s33[31:0] & wmsk; r1n <= w;
            end
            C_SUB: begin : sub_b
                reg [32:0] d33;                      // borrow in bit 32 / 16
                d33 = single ? {17'd0, B[15:0]} - {17'd0, A[15:0]} : {1'b0, B} - {1'b0, A};
                carry_f <= single ? d33[16] : d33[32];
                if (single ? ((!B[15] && A[15] && d33[15]) || (B[15] && !A[15] && !d33[15]))
                           : ((!B[31] && A[31] && d33[31]) || (B[31] && !A[31] && !d33[31])))
                    errc <= ERR_OVF;
                R1 <= d33[31:0] & wmsk; r1n <= w;
            end
            C_MUL, C_MUU, C_DIV: begin
                sneg <= ai[31] ^ bi[31];
                if (code != C_DIV && ((ai & wmsk) == smin || (bi & wmsk) == smin)) begin
                    errc <= ERR_OVF; R1 <= smin; r1n <= w;
                end else if (code == C_DIV && (ai & wmsk) == 0) begin
                    errc <= ERR_DIV0; R1 <= 0; r1n <= w;
                end else
                    st <= S_MAG;                     // A, B <- magnitudes
            end
            // ---------------- floating point ----------------
            C_FADD, C_FSUB: begin : fadd_b
                reg        sa2, bigb;
                reg signed [9:0] d;
                ftype <= 2'b00; r1n <= 4;
                sa2 = A[31] ^ (code == C_FSUB);
                if (az) R1 <= bz ? 32'd0 : B;
                else if (bz) R1 <= {sa2, A[30:0]};
                else begin
                    bigb = (eb > ea) || (eb == ea && B[23:0] >= A[23:0]);
                    d    = bigb ? eb - ea : ea - eb;
                    if (bigb) begin
                        SB <= {1'b0, B[23:0], 26'd0}; SA <= {1'b0, A[23:0], 26'd0};
                        sgn <= B[31]; e <= eb;
                    end else begin
                        SB <= {1'b0, A[23:0], 26'd0}; SA <= {1'b0, B[23:0], 26'd0};
                        sgn <= sa2; e <= ea;
                    end
                    addop <= (B[31] == sa2);
                    it    <= (d > 10'sd52) ? 6'd52 : d[5:0];
                    st    <= S_ALGN;
                end
            end
            C_FMUL: begin
                ftype <= 2'b00; r1n <= 4;
                if (az || bz) R1 <= 32'd0;
                else begin
                    X <= {40'd0, A[23:0]}; D <= {8'd0, B[23:0]}; it <= 6'd0;
                    sgn <= A[31] ^ B[31]; e <= ea + eb; st <= S_MUL;
                end
            end
            C_FDIV: begin
                ftype <= 2'b00; r1n <= 4;
                if (az) begin errc <= ERR_DIV0; R1 <= bz ? 32'd0 : B; end
                else if (bz) R1 <= 32'd0;
                else begin
                    X <= {B[23:0], 40'd0}; D <= {8'd0, A[23:0]}; Rm <= 0; it <= 6'd50;
                    sgn <= A[31] ^ B[31]; e <= eb - ea; st <= S_DIV;
                end
            end
            C_SQRT: begin
                ftype <= 2'b00; r1n <= 4;
                if (az) R1 <= 32'd0;
                else if (A[31]) begin errc <= ERR_NEG; nostore <= 1'b1; end
                else begin
                    sx <= ea[0] ? {1'b0, A[23:0], 29'd0} : {2'b0, A[23:0], 28'd0};
                    srem <= 0; sroot <= 0; it <= 6'd27; sgn <= 1'b0;
                    e <= (ea + (ea[0] ? 10'sd1 : 10'sd0)) >>> 1;     // signed halving
                    st <= S_SQRT;
                end
            end
            C_FLTS, C_FLTD: begin
                ftype <= 2'b00; r1n <= 4;
                if ((code == C_FLTS ? {16'd0, A[15:0]} : A) == 0) R1 <= 32'd0;
                else begin : flt_b
                    reg [31:0] v;
                    v = (code == C_FLTS) ? {{16{A[15]}}, A[15:0]} : A;
                    sgn <= v[31];
                    T <= {32'd0, v}; negf <= v[31];        // magnitude via S_NEG
                    e <= 10'sd32; st <= S_NEG;
                end
            end
            C_FIXS, C_FIXD: begin
                if (az || ea <= 0) begin                   // zero or |x| < 1 -> 0
                    R1 <= 0; r1n <= (code == C_FIXS) ? 3'd2 : 3'd4;
                    ftype <= (code == C_FIXS) ? 2'b11 : 2'b01;
                end else if (ea > 10'sd33) begin
                    errc <= ERR_OVF; nostore <= 1'b1;
                end else begin
                    X <= {40'd0, A[23:0]}; it <= ea[5:0]; st <= S_FIXS;
                end
            end
            default: begin                                 // SIN..PWR -> microcode
                um <= 1'b1; upc <= uentry(code); N <= 32'd0; upend <= 4'd0;
                rfw_en <= 1'b1; rfw_a <= 3'd0; rfw_d <= A; // r0 = TOS
                st <= S_UE1;
            end
            endcase
        end
        // ====================================================== microsequencer
        S_UE1: begin                                       // r1 = NOS (PWR base)
            rfw_en <= 1'b1; rfw_a <= 3'd1; rfw_d <= B;
            st <= S_UF;
        end
        S_UF: st <= S_UD;                                  // ROM read latency
        S_UK: begin                                        // LDK: constant ready
            rfw_en <= 1'b1; rfw_a <= ud; rfw_d <= kq;
            upc <= upc1; st <= S_UF;
        end
        S_UD: begin
            upc <= upc1;
            st  <= S_UF;
            case (uopc)
            5'd0: begin                                    // END: store r[a]
                um <= 1'b0; R1 <= ura; r1n <= 4; r2n <= 0; cnt <= 0; carry_f <= 1'b0;
                errc <= upend; nostore <= (upend != 0);
                ftype <= (op[4:0] == C_PWR) ? op[6:5] : 2'b00;
                st <= S_STORE;
            end
            5'd1: begin                                    // ERR: error, stack unchanged
                um <= 1'b0; errc <= uimm[3:0]; nostore <= 1'b1; cnt <= 0; carry_f <= 1'b0;
                ftype <= (op[4:0] == C_PWR) ? op[6:5] : 2'b00;
                st <= S_STORE;
            end
            5'd2, 5'd3, 5'd4, 5'd5, 5'd6: begin            // FADD FSUB FMUL FDIV SQRT
                A <= ura; B <= urb; ud <= ufd; nostore <= 1'b0;
                ucode <= (uopc == 5'd2) ? C_FADD : (uopc == 5'd3) ? C_FSUB :
                         (uopc == 5'd4) ? C_FMUL : (uopc == 5'd5) ? C_FDIV : C_SQRT;
                st <= S_EXEC;
            end
            5'd7: begin ud <= ufd; upc <= upc; st <= S_UK; end   // LDK
            5'd8:  begin rfw_en <= 1'b1; rfw_a <= ufd; rfw_d <= ura; end                    // MOV
            5'd9:  begin rfw_en <= 1'b1; rfw_a <= ufd;                                      // NEG
                         rfw_d <= ura[23] ? {~ura[31], ura[30:0]} : ura; end
            5'd10: begin rfw_en <= 1'b1; rfw_a <= ufd; rfw_d <= {1'b0, ura[30:0]}; end      // ABS
            5'd11: begin A <= ura; ucode <= C_FIXD; nostore <= 1'b0; st <= S_EXEC; end   // FIX
            5'd12: begin A <= N; ucode <= C_FLTD; ud <= ufd; nostore <= 1'b0; st <= S_EXEC; end // FLT
            5'd13: begin                                   // SCALE r[d] = r[a] * 2^N
                rfw_en <= 1'b1; rfw_a <= ufd;
                if (!ura[23]) rfw_d <= 32'd0;
                else begin
                    rfw_d <= {ura[31], uen[6:0], ura[23:0]};
                    if (uen > 11'sd63)       upend <= upend | ERR_OVF;
                    else if (uen < -11'sd64) upend <= upend | ERR_UND;
                end
            end
            5'd14: begin                                   // GETX: N = exp, r[d] = mantissa
                N <= {{25{ura[30]}}, ura[30:24]};
                rfw_en <= 1'b1; rfw_a <= ufd; rfw_d <= {ura[31], 7'd0, ura[23:0]};
            end
            5'd15: upc <= uimm;                                            // JMP
            5'd16: if (ura[23] &&  ura[31]) upc <= uimm;                   // JNEG
            5'd17: if (!ura[23])            upc <= uimm;                   // JZ
            5'd18: if (N[ufa])              upc <= uimm;                   // JBIT
            5'd19: N <= N + {{22{uimm[9]}}, uimm};                         // ADDN
            5'd20: begin ulink <= upc1; upc <= uimm; end                   // CALL
            5'd21: upc <= ulink;                                           // RET
            5'd22: if (ura[23] && !ura[31]) upc <= uimm;                   // JPOS
            default: ;
            endcase
        end
        // ====================================================== magnitudes
        S_MAG: begin                                       // cnt 0: A, cnt 1: B
            if (cnt == 0) begin
                A <= ai[31] ? nout[31:0] : ai;
                cnt <= 1;
            end else begin
                B <= bi[31] ? nout[31:0] : bi;
                cnt <= 0;
                if (code == C_DIV) begin
                    X <= {(bi[31] ? nout[31:0] : bi), 32'd0}; D <= A; Rm <= 0; it <= 6'd32;
                    st <= S_DIV;
                end else begin
                    X <= {32'd0, A}; D <= (bi[31] ? nout[31:0] : bi); it <= 6'd0;
                    st <= S_MUL;
                end
            end
        end
        // ====================================================== multiply
        // X = {P_hi, multiplier}; 32 shift-add steps -> X = D * multiplier
        S_MUL: begin : mul_b
            reg [32:0] s;
            s = X[0] ? {1'b0, X[63:32]} + {1'b0, D} : {1'b0, X[63:32]};
            X <= {s, X[31:1]};
            it <= it + 6'd1;
            if (it == 6'd31) st <= S_MULE;
        end
        S_MULE: begin
            if (code == C_FMUL) begin
                if (X[47]) begin M <= {1'b0, X[47:24]}; g <= X[23]; stk_y <= |X[22:0]; end
                else begin M <= {1'b0, X[46:23]}; g <= X[22]; stk_y <= |X[21:0]; e <= e - 10'sd1; end
                st <= S_RND;
            end else begin : imul_b
                reg o, o2;
                o  = single ? (X[31:16] != 0) : (X[63:32] != 0);
                o2 = sneg && (single ? (X[31:0] == 32'h8000_0000) : (X == 64'h8000_0000_0000_0000));
                if ((code == C_MUL && o) || o2) errc <= ERR_OVF;
                T <= single ? {32'd0, X[31:0]} : X; negf <= sneg;
                st <= S_NEG;
            end
        end
        // ====================================================== divide
        // restoring division of X (MSB first) by D, `it` steps
        S_DIV: begin : div_b
            reg [32:0] r2;
            reg [33:0] df;
            r2 = {Rm[31:0], X[63]};
            df = {1'b0, r2} - {2'b0, D};
            if (!df[33]) begin Rm <= df[32:0]; X <= {X[62:0], 1'b1}; end
            else         begin Rm <= r2;       X <= {X[62:0], 1'b0}; end
            it <= it - 6'd1;
            if (it == 6'd1) st <= S_DIVE;
        end
        S_DIVE: begin
            if (code == C_FDIV) begin                      // q = X[26:0]
                if (X[26]) begin M <= {1'b0, X[26:3]}; g <= X[2]; stk_y <= |X[1:0] | (Rm != 0); e <= e + 10'sd1; end
                else begin M <= {1'b0, X[25:2]}; g <= X[1]; stk_y <= X[0] | (Rm != 0); end
                st <= S_RND;
            end else begin
                T <= {32'd0, X[31:0]}; negf <= sneg; st <= S_NEG;
            end
        end
        // ====================================================== negate + output
        S_NEG: begin
            if (negf) T <= nout;
            st <= S_OUT;
        end
        S_OUT: begin
            cnt <= 0; st <= S_STORE; r1n <= w;
            case (code)
                C_MUU:          R1 <= single ? {16'd0, T[31:16]} : T[63:32];
                C_FIXS, C_FIXD: begin
                    R1 <= T[31:0]; r1n <= (code == C_FIXS) ? 3'd2 : 3'd4;
                    ftype <= (code == C_FIXS) ? 2'b11 : 2'b01;
                end
                C_FLTS, C_FLTD: begin X <= {32'd0, T[31:0]}; st <= S_FLTN; r1n <= 4; end
                default:        R1 <= T[31:0] & wmsk;      // MUL, DIV, CHS
            endcase
        end
        // ====================================================== float add
        S_ALGN: begin                                      // shift SA right `it` times
            if (it == 0) st <= S_ADDS;
            else begin
                SA <= {1'b0, SA[50:2], SA[1] | SA[0]};
                it <= it - 6'd1;
            end
        end
        S_ADDS: begin : adds_b
            reg [50:0] s;
            s = SB + (addop ? SA : ~SA) + {50'd0, ~addop};  // |SB| >= |SA|
            if (s == 0) begin R1 <= 32'd0; cnt <= 0; st <= S_STORE; end
            else if (addop && s[50]) begin SB <= {1'b0, s[50:2], s[1] | s[0]}; e <= e + 10'sd1; st <= S_NORM; end
            else begin SB <= addop ? s : {1'b0, s[49:0]}; st <= S_NORM; end
        end
        S_NORM: begin
            if (!SB[49]) begin SB <= {SB[49:0], 1'b0}; e <= e - 10'sd1; end
            else begin
                M <= {1'b0, SB[49:26]}; g <= SB[25]; stk_y <= |SB[24:0];
                st <= S_RND;
            end
        end
        // ====================================================== square root
        S_SQRT: begin : sqrt_b
            reg [29:0] r2, t;
            reg [30:0] df;
            r2 = {srem[27:0], sx[53:52]};
            t  = {1'b0, sroot, 2'b01};
            df = {1'b0, r2} - {1'b0, t};
            sx <= {sx[51:0], 2'b00};
            if (!df[30]) begin srem <= df[29:0]; sroot <= {sroot[25:0], 1'b1}; end
            else         begin srem <= r2;       sroot <= {sroot[25:0], 1'b0}; end
            it <= it - 6'd1;
            if (it == 6'd1) st <= S_SQE;
        end
        S_SQE: begin
            if (A[24]) begin M <= {1'b0, sroot[26:3]}; g <= sroot[2]; stk_y <= |sroot[1:0] | (srem != 0); end
            else begin M <= {1'b0, sroot[25:2]}; g <= sroot[1]; stk_y <= sroot[0] | (srem != 0); end
            st <= S_RND;
        end
        // ====================================================== int -> float
        S_FLTN: begin
            if (!X[31]) begin X <= {X[62:0], 1'b0}; e <= e - 10'sd1; end
            else begin
                M <= {1'b0, X[31:8]}; g <= X[7]; stk_y <= |X[6:0];
                st <= S_RND;
            end
        end
        // ====================================================== float -> int
        S_FIXS: begin                                      // X = mantissa << E
            if (it == 0) st <= S_FIXE;
            else begin X <= {X[62:0], 1'b0}; it <= it - 6'd1; end
        end
        S_FIXE: begin : fixe_b
            reg [32:0] ip;
            reg        fr, ovf;
            ip = X[56:24];
            fr = |X[23:0];
            if (code == C_FIXS)
                ovf = A[31] ? (ip > 33'd32768 || (ip == 33'd32768 && fr))
                            : (ip > 33'd32767 || (ip == 33'd32767 && fr));
            else
                ovf = A[31] ? (ip > 33'h0_8000_0000 || (ip == 33'h0_8000_0000 && fr))
                            : (ip >= 33'h0_8000_0000 || (ip == 33'h0_7FFF_FFFF && fr));
            if (ovf) begin errc <= ERR_OVF; nostore <= 1'b1; cnt <= 0; st <= S_STORE; end
            else begin T <= {31'd0, ip}; negf <= A[31]; st <= S_NEG; end
        end
        // ====================================================== round / pack
        S_RND: begin : rnd_b
            reg [24:0] m2;
            m2 = M + {24'd0, g & (stk_y | M[0])};
            if (m2[24]) begin M <= {1'b0, m2[24:1]}; e <= e + 10'sd1; end
            else M <= m2;
            st <= S_PACK;
        end
        S_PACK: begin : pack_b
            reg signed [9:0] e2;
            e2 = e;
            if (e > 10'sd63) begin errc <= errc | ERR_OVF; e2 = e - 10'sd128; end
            else if (e < -10'sd64) begin errc <= errc | ERR_UND; e2 = e + 10'sd128; end
            R1 <= {sgn, e2[6:0], M[23:0]};
            r1n <= 4; cnt <= 0; st <= S_STORE;
        end
        // ====================================================== write back
        S_STORE: begin
            if (um) begin                                  // primitive done (microcode)
                if (nostore) begin                         // FIX overflow etc.
                    um <= 1'b0; errc <= ERR_ARG; cnt <= 0; carry_f <= 1'b0;
                    ftype <= (op[4:0] == C_PWR) ? op[6:5] : 2'b00;
                end else begin
                    if (ucode == C_FIXD) N <= R1;
                    else begin rfw_en <= 1'b1; rfw_a <= ud; rfw_d <= R1; end
                    st <= S_UF;
                end
            end
            else if (nostore) begin cnt <= 0; st <= S_FLAG; end
            else if (cnt == r1n + r2n) begin
                sp <= base + {1'b0, r1n} + {1'b0, r2n};
                cnt <= 0; st <= S_FLAG;
            end else begin
                if (cnt < r1n) begin stk[base + cnt] <= R1[7:0]; R1 <= {8'd0, R1[31:8]}; end
                else           begin stk[base + cnt] <= R2[7:0]; R2 <= {8'd0, R2[31:8]}; end
                cnt <= cnt + 4'd1;
            end
        end
        S_FLAG: begin                                      // fl = {b1, b2, b3, b4}
            fl <= {fl[23:0], rbyte};
            cnt <= cnt + 4'd1;
            if (cnt == 4'd3) st <= S_FLAG2;
        end
        S_FLAG2: begin : flag_b
            reg z;
            // fl[31:24] = byte at sp-1 (MS), fl[23:16] = sp-2, ...
            if (ftype == 2'b11)      z = (fl[31:24] | fl[23:16]) == 0;
            else if (ftype[0])       z = fl == 0;
            else                     z = ~fl[23];
            status <= {1'b0, fl[31], z, errc, carry_f};
            busy   <= 1'b0;
            svreq  <= op[7];
            st     <= S_IDLE;
        end
        default: st <= S_IDLE;
        endcase
    end
endmodule
