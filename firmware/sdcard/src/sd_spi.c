/*
 * sd_spi.c - SD / SDHC / SDXC card access over SPI (single-block commands).
 */
#include "pico/stdlib.h"
#include "hardware/spi.h"
#include "board.h"
#include "sd_spi.h"

#define CMD0   0
#define CMD8   8
#define CMD9   9
#define CMD12  12
#define CMD13  13
#define CMD16  16
#define CMD17  17
#define CMD24  24
#define CMD55  55
#define CMD58  58
#define ACMD41 41

static int block_addr;       /* SDHC/SDXC: LBA addressing; SDSC: byte addressing */
static uint32_t n_sectors;

static inline void cs(int on) { gpio_put(PIN_SD_CS, !on); }

static uint8_t xfer(uint8_t b)
{
    uint8_t r;
    spi_write_read_blocking(SD_SPI, &b, &r, 1);
    return r;
}

static int wait_ready(uint32_t ms)
{
    absolute_time_t t = make_timeout_time_ms(ms);
    while (xfer(0xFF) != 0xFF)
        if (time_reached(t)) return -1;
    return 0;
}

static void deselect(void)
{
    cs(0);
    xfer(0xFF);              /* release MISO */
}

static int select_card(void)
{
    cs(1);
    xfer(0xFF);
    if (wait_ready(500) == 0) return 0;
    deselect();
    return -1;
}

static uint8_t command(uint8_t cmd, uint32_t arg)
{
    uint8_t r, n, crc = 0x01;
    if (cmd & 0x80) {                         /* ACMD: CMD55 first */
        r = command(CMD55, 0);
        if (r > 1) return r;
        cmd &= 0x7F;
    }
    deselect();
    if (select_card()) return 0xFF;
    if (cmd == CMD0) crc = 0x95;
    if (cmd == CMD8) crc = 0x87;
    xfer(0x40 | cmd);
    xfer((uint8_t)(arg >> 24)); xfer((uint8_t)(arg >> 16)); xfer((uint8_t)(arg >> 8)); xfer((uint8_t)arg);
    xfer(crc);
    if (cmd == CMD12) xfer(0xFF);
    n = 10;
    do r = xfer(0xFF); while ((r & 0x80) && --n);
    return r;
}

static int rx_block(uint8_t *buf, unsigned len)
{
    absolute_time_t t = make_timeout_time_ms(200);
    uint8_t tok;
    do {
        tok = xfer(0xFF);
        if (time_reached(t)) return -1;
    } while (tok == 0xFF);
    if (tok != 0xFE) return -1;
    spi_read_blocking(SD_SPI, 0xFF, buf, len);
    xfer(0xFF); xfer(0xFF);                   /* CRC */
    return 0;
}

static uint32_t csd_sectors(void)
{
    uint8_t csd[16];
    uint32_t r = 0;
    if (command(CMD9, 0) == 0 && rx_block(csd, 16) == 0) {
        if ((csd[0] >> 6) == 1) {             /* CSD v2: (C_SIZE + 1) * 1024 */
            uint32_t c = ((uint32_t)(csd[7] & 0x3F) << 16) | ((uint32_t)csd[8] << 8) | csd[9];
            r = (c + 1) << 10;
        } else {                              /* CSD v1 */
            uint32_t c = ((uint32_t)(csd[6] & 3) << 10) | ((uint32_t)csd[7] << 2) | (csd[8] >> 6);
            uint32_t mult = ((csd[9] & 3) << 1) | (csd[10] >> 7);
            uint32_t bl = csd[5] & 0x0F;
            r = (c + 1) << (mult + 2 + bl - 9);
        }
    }
    deselect();
    return r;
}

int sd_init(void)
{
    uint8_t ocr[4];
    int i, v2 = 0;
    absolute_time_t t;

    spi_init(SD_SPI, 400 * 1000);
    gpio_set_function(PIN_SD_MISO, GPIO_FUNC_SPI);
    gpio_set_function(PIN_SD_SCK, GPIO_FUNC_SPI);
    gpio_set_function(PIN_SD_MOSI, GPIO_FUNC_SPI);
    gpio_pull_up(PIN_SD_MISO);
    gpio_init(PIN_SD_CS);
    gpio_set_dir(PIN_SD_CS, GPIO_OUT);
    cs(0);
    for (i = 0; i < 10; i++) xfer(0xFF);      /* >= 74 clocks with CS high */

    if (command(CMD0, 0) != 1) { deselect(); return -1; }
    t = make_timeout_time_ms(1000);
    if (command(CMD8, 0x1AA) == 1) {
        for (i = 0; i < 4; i++) ocr[i] = xfer(0xFF);
        if (ocr[2] != 0x01 || ocr[3] != 0xAA) { deselect(); return -1; }
        v2 = 1;
        while (command(0x80 | ACMD41, 1u << 30))
            if (time_reached(t)) { deselect(); return -1; }
        if (command(CMD58, 0)) { deselect(); return -1; }
        for (i = 0; i < 4; i++) ocr[i] = xfer(0xFF);
        block_addr = (ocr[0] & 0x40) != 0;
    } else {
        while (command(0x80 | ACMD41, 0))         /* SD v1 (MMC is not supported) */
            if (time_reached(t)) { deselect(); return -1; }
        block_addr = 0;
        if (command(CMD16, 512)) { deselect(); return -1; }
    }
    (void)v2;
    deselect();
    spi_set_baudrate(SD_SPI, 12500 * 1000);   /* conservative: the breakout's level shifter sits in the path */
    n_sectors = csd_sectors();
    return 0;
}

int sd_read(uint8_t *buf, uint32_t lba, uint32_t count)
{
    for (; count; count--, lba++, buf += 512) {
        if (command(CMD17, block_addr ? lba : lba * 512) || rx_block(buf, 512)) {
            deselect();
            return -1;
        }
        deselect();
    }
    return 0;
}

int sd_write(const uint8_t *buf, uint32_t lba, uint32_t count)
{
    for (; count; count--, lba++, buf += 512) {
        uint8_t r;
        if (command(CMD24, block_addr ? lba : lba * 512)) { deselect(); return -1; }
        xfer(0xFE);
        spi_write_blocking(SD_SPI, buf, 512);
        xfer(0xFF); xfer(0xFF);               /* dummy CRC */
        r = xfer(0xFF);
        if ((r & 0x1F) != 0x05 || wait_ready(500)) { deselect(); return -1; }
        deselect();
    }
    return 0;
}

int sd_check(void)
{
    uint8_t r = command(CMD13, 0);
    xfer(0xFF);                               /* second byte of R2 */
    deselect();
    return r == 0 ? 0 : -1;
}

uint32_t sd_sectors(void) { return n_sectors; }
