/*
 * bus.c - Z80 bus service on core 1 (runs from RAM).
 *
 * The GAL pulls WAIT* low as soon as an IN/OUT to C0-CF starts and keeps it
 * there until ACK goes high, so this loop can take its time (a few hundred ns)
 * without racing the Z80:
 *   OUT: wait for the shifters to settle, sample PD0-7 and A0-A3, frehd_out(),
 *        raise ACK.
 *   IN:  frehd_in(), drive PD0-7, wait for the 5 V side to settle, raise ACK.
 * When the Z80 ends the cycle the GAL drops SEL; release PD and lower ACK.
 */
#include "pico/stdlib.h"
#include "hardware/structs/sio.h"
#include "board.h"
#include "frehd.h"

/* at 125 MHz: 8 ns per cycle */
#define SETTLE_CYCLES 50      /* ~400 ns: XD -> PD through the 2N7000 + 4.7k pull-up */
#define DRIVE_CYCLES  60      /* ~480 ns: PD -> XD rising edge into the 245 */

void __not_in_flash_func(bus_loop)(void)
{
    uint32_t g;

    sio_hw->gpio_clr = 1u << PIN_ACK;
    sio_hw->gpio_oe_set = 1u << PIN_ACK;   /* from here on, every C0-CF access waits for us */
    for (;;) {
        while (!((g = sio_hw->gpio_in) & MASK_SEL)) {
            if (!(g & (1u << PIN_RESET))) {
                frehd_bus_reset();
                while (!(sio_hw->gpio_in & (1u << PIN_RESET)))
                    tight_loop_contents();
            }
        }
        busy_wait_at_least_cycles(SETTLE_CYCLES);
        g = sio_hw->gpio_in;
        if (g & (1u << PIN_SELWR)) {
            frehd_out((uint8_t)((g >> PIN_PA0) & 0xF), (uint8_t)(g >> PIN_PD0));
        } else {
            uint32_t v = (uint32_t)frehd_in((uint8_t)((g >> PIN_PA0) & 0xF)) << PIN_PD0;
            sio_hw->gpio_clr = MASK_PD & ~v;
            sio_hw->gpio_set = v;
            sio_hw->gpio_oe_set = MASK_PD;
            busy_wait_at_least_cycles(DRIVE_CYCLES);
        }
        sio_hw->gpio_set = 1u << PIN_ACK;
        while (sio_hw->gpio_in & MASK_SEL)
            tight_loop_contents();
        sio_hw->gpio_oe_clr = MASK_PD;
        sio_hw->gpio_clr = 1u << PIN_ACK;
    }
}
