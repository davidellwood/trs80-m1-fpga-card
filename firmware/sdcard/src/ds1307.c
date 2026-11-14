/*
 * ds1307.c - DS1307 real-time clock on I2C1, plus the FreHD time hooks.
 * FreHD time order: sec, min, hour, year (0-99 = 2000-2099), day, month, binary.
 * Without an RTC (no chip, or no battery) a software clock runs from the
 * build date so GETTIME still answers.
 */
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/i2c.h"
#include "board.h"
#include "ds1307.h"
#include "frehd.h"
#include "ff.h"

#define ADDR 0x68

static int present;
static uint8_t soft[6];          /* software clock, same order as FreHD */
static uint64_t soft_base_us;

static uint8_t bcd2bin(uint8_t v) { return (uint8_t)((v >> 4) * 10 + (v & 0x0F)); }
static uint8_t bin2bcd(uint8_t v) { return (uint8_t)(((v / 10) << 4) | (v % 10)); }

static int rd(uint8_t reg, uint8_t *buf, int n)
{
    if (i2c_write_timeout_us(RTC_I2C, ADDR, &reg, 1, true, 2000) != 1) return -1;
    return i2c_read_timeout_us(RTC_I2C, ADDR, buf, (size_t)n, false, 5000) == n ? 0 : -1;
}

static int wr(const uint8_t *buf, int n)
{
    return i2c_write_timeout_us(RTC_I2C, ADDR, buf, (size_t)n, false, 5000) == n ? 0 : -1;
}

static void soft_now(uint8_t t[6])
{
    static const uint8_t mdays[12] = { 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31 };
    uint64_t s = (time_us_64() - soft_base_us) / 1000000u;
    uint32_t sec = soft[0] + (uint32_t)(s % 60), min = soft[1], hour = soft[2], day = soft[4], mon = soft[5];
    uint32_t year = soft[3], days;
    s /= 60; min += (uint32_t)(s % 60); s /= 60; hour += (uint32_t)(s % 24); days = (uint32_t)(s / 24);
    if (sec >= 60) { sec -= 60; min++; }
    if (min >= 60) { min -= 60; hour++; }
    if (hour >= 24) { hour -= 24; days++; }
    while (days--) {
        uint8_t md = mdays[mon - 1] + (mon == 2 && (year % 4) == 0);
        if (++day > md) { day = 1; if (++mon > 12) { mon = 1; year = (year + 1) % 100; } }
    }
    t[0] = (uint8_t)sec; t[1] = (uint8_t)min; t[2] = (uint8_t)hour;
    t[3] = (uint8_t)year; t[4] = (uint8_t)day; t[5] = (uint8_t)mon;
}

void ds1307_init(void)
{
    static const char *mon = "JanFebMarAprMayJunJulAugSepOctNovDec";
    const char *d = __DATE__;            /* "Nov 13 2026" */
    uint8_t r[8];
    int i;

    i2c_init(RTC_I2C, 100 * 1000);
    gpio_set_function(PIN_SDA, GPIO_FUNC_I2C);
    gpio_set_function(PIN_SCL, GPIO_FUNC_I2C);

    for (i = 0; i < 12; i++)
        if (!memcmp(d, mon + 3 * i, 3)) soft[5] = (uint8_t)(i + 1);
    soft[4] = (uint8_t)((d[4] == ' ' ? 0 : (d[4] - '0') * 10) + (d[5] - '0'));
    soft[3] = (uint8_t)((d[9] - '0') * 10 + (d[10] - '0'));
    soft[0] = soft[1] = soft[2] = 0;
    soft_base_us = time_us_64();

    present = rd(0, r, 7) == 0;
    if (present && (r[0] & 0x80)) {      /* oscillator halted (new chip / flat cell): start it */
        uint8_t w[2] = { 0, (uint8_t)(r[0] & 0x7F) };
        wr(w, 2);
    }
    if (present && (r[2] & 0x40)) {      /* 12-hour mode: switch to 24-hour */
        uint8_t h = bcd2bin(r[2] & 0x1F) % 12 + ((r[2] & 0x20) ? 12 : 0);
        uint8_t w[2] = { 2, bin2bcd(h) };
        wr(w, 2);
    }
}

int ds1307_present(void) { return present; }

void plat_get_time(uint8_t t[6])
{
    uint8_t r[7];
    if (present && rd(0, r, 7) == 0) {
        t[0] = bcd2bin(r[0] & 0x7F);
        t[1] = bcd2bin(r[1] & 0x7F);
        t[2] = bcd2bin(r[2] & 0x3F);
        t[3] = bcd2bin(r[6]);
        t[4] = bcd2bin(r[4] & 0x3F);
        t[5] = bcd2bin(r[5] & 0x1F);
        return;
    }
    soft_now(t);
}

void plat_set_time(const uint8_t t[6])
{
    memcpy(soft, t, 6);
    soft_base_us = time_us_64();
    if (present) {
        uint8_t w[8] = { 0, bin2bcd(t[0] % 60), bin2bcd(t[1] % 60), bin2bcd(t[2] % 24), 1,
                         bin2bcd(t[4]), bin2bcd(t[5]), bin2bcd(t[3] % 100) };
        wr(w, 8);
    }
}

/* FatFs timestamp for files the TRS-80 creates */
DWORD get_fattime(void)
{
    uint8_t t[6];
    plat_get_time(t);
    return ((DWORD)(t[3] + 20) << 25) | ((DWORD)t[5] << 21) | ((DWORD)t[4] << 16) |
           ((DWORD)t[2] << 11) | ((DWORD)t[1] << 5) | (t[0] >> 1);
}
