`timescale 1ns/1ps
// Single-port synchronous RAM (read-first), inferred as Gowin BSRAM.
module spram #(parameter AW = 10, parameter DW = 8, parameter DEPTH = (1 << AW)) (
    input  wire          clk,
    input  wire          we,
    input  wire [AW-1:0] a,
    input  wire [DW-1:0] d,
    output reg  [DW-1:0] q
);
    reg [DW-1:0] m [0:DEPTH-1];
    always @(posedge clk) begin
        if (we) m[a] <= d;
        q <= m[a];
    end
endmodule
