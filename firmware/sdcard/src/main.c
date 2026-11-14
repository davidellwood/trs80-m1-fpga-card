/*
 * main.c - FreHD-compatible SD card for the TRS-80 ECB backplane (Raspberry Pi Pico).
 *
 * Core 1: bus_loop() services every Z80 IN/OUT to C0h-CFh (bus.c).
 * Core 0: mounts the SD card, runs queued disk actions (frehd_poll), flushes
 *         images, keeps the RTC, drives the ACT LED. Debug text on USB serial.
 *
 * SD card contents: hard4-0 .. hard4-3 (.HDV images, FreHD/xtrs format), and
 * optionally FREHD.ROM (the FreHD boot loader image, streamed on IN C4h).
 */
#include <stdio.h>
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "pico/bootrom.h"
#include "ff.h"
#include "board.h"
#include "frehd.h"
#include "ds1307.h"
#include "sd_spi.h"

void bus_loop(void);
void disk_force_reinit(void);

static FATFS fs;

void plat_bootloader(void)
{
    /* FreHD "enter bootloader": on the Pico, reboot into the USB mass-storage
       loader so new firmware can be dropped on as a .uf2 file */
    reset_usb_boot(0, 0);
}

static void gpio_setup(void)
{
    int i;
    for (i = 0; i < 8; i++) {                 /* PD0-7: inputs until an IN cycle */
        gpio_init(PIN_PD0 + i);
        gpio_disable_pulls(PIN_PD0 + i);
    }
    for (i = 0; i < 4; i++) {
        gpio_init(PIN_PA0 + i);
        gpio_disable_pulls(PIN_PA0 + i);
    }
    gpio_init(PIN_SELRD); gpio_disable_pulls(PIN_SELRD);
    gpio_init(PIN_SELWR); gpio_disable_pulls(PIN_SELWR);
    gpio_init(PIN_RESET); gpio_disable_pulls(PIN_RESET);
    gpio_init(PIN_ACK);                       /* stays an input (pulled up) until core 1 runs */
    gpio_disable_pulls(PIN_ACK);
    gpio_init(PIN_SD_CD); gpio_pull_up(PIN_SD_CD);
    gpio_init(PIN_LED); gpio_set_dir(PIN_LED, GPIO_OUT);
}

static int card_inserted(void)
{
#if USE_CARD_DETECT
    return gpio_get(PIN_SD_CD) == CD_INSERTED_LEVEL;
#else
    return 1;
#endif
}

int main(void)
{
    int mounted = 0;
    uint32_t last_ms, probe_ms = 0, now;

    gpio_setup();
    frehd_init();
    multicore_launch_core1(bus_loop);
    stdio_init_all();
    ds1307_init();
    printf("FreHD-compatible SD card, RTC %s\n", ds1307_present() ? "found" : "not found");

    last_ms = to_ms_since_boot(get_absolute_time());
    for (;;) {
        frehd_poll();

        now = to_ms_since_boot(get_absolute_time());
        if (now != last_ms) {
            frehd_tick_ms(now - last_ms);
            last_ms = now;
            gpio_put(PIN_LED, frehd_activity());
        }

        if (now - probe_ms >= 1000) {         /* once a second: (re)mount or check the card */
            probe_ms = now;
            if (!mounted) {
                if (card_inserted()) {
                    disk_force_reinit();
                    if (f_mount(&fs, "", 1) == FR_OK) {
                        mounted = 1;
                        frehd_card_mounted(1);
                        printf("SD card mounted\n");
                    }
                }
            } else if (!frehd_activity() && (!card_inserted() || sd_check() != 0)) {
                frehd_card_mounted(0);
                f_mount(NULL, "", 0);
                mounted = 0;
                printf("SD card removed\n");
            }
        }
    }
}
