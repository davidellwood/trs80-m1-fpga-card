`timescale 1ns/1ps
// Two-flop synchroniser for asynchronous inputs (Z80-side strobes, BUSY, reset).
module sync2 #(parameter W = 1, parameter [W-1:0] INIT = {W{1'b0}}) (
    input  wire         clk,
    input  wire [W-1:0] d,
    output wire [W-1:0] q
);
    reg [W-1:0] s1 = INIT, s2 = INIT;
    always @(posedge clk) begin
        s1 <= d;
        s2 <= s1;
    end
    assign q = s2;
endmodule
