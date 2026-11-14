/*
 * frehd.h - FreHD-compatible hard-disk emulator core (ports C0h-CFh)
 *
 * Independent implementation of the FreHD / Radio Shack WD1010 hard-disk
 * register protocol, so existing FreHD drivers and utilities run unchanged.
 * Storage is .HDV ("Reed" header) image files on a FAT SD card via FatFs.
 *
 * Split across the RP2040's two cores:
 *   core 1 (bus.c)  calls frehd_in()/frehd_out() for every Z80 access. These
 *                   only touch RAM and return in well under a microsecond.
 *   core 0 (main.c) calls frehd_poll() in its loop. Slow work (sector read or
 *                   write, extension commands) is queued by the bus side as an
 *                   "action"; the Z80 sees BUSY until core 0 has finished it.
 * The host test (test/) drives the same API single-threaded.
 */
#ifndef FREHD_H
#define FREHD_H

#include <stdint.h>

/* port offsets from C0h */
enum {
    R_WP = 0x0, R_CONTROL = 0x1, R_DATA2 = 0x2, R_SIZE2 = 0x3, R_COMMAND2 = 0x4, R_ERROR2 = 0x5,
    R_UARTST = 0x6, R_UARTDATA = 0x7,
    R_DATA = 0x8, R_ERROR = 0x9, R_SECCNT = 0xA, R_SECNUM = 0xB, R_CYLLO = 0xC, R_CYLHI = 0xD,
    R_SDH = 0xE, R_STATUS = 0xF
};

/* WD1010 status bits */
#define ST_BUSY     0x80
#define ST_READY    0x40
#define ST_WRERR    0x20
#define ST_SEEKDONE 0x10
#define ST_DRQ      0x08
#define ST_ECC      0x04
#define ST_CIP      0x02
#define ST_ERR      0x01

/* WD1010 error bits */
#define ER_BBD   0x80
#define ER_DATA  0x40
#define ER_ID    0x20
#define ER_NF    0x10
#define ER_MCR   0x08
#define ER_ABRT  0x04
#define ER_TRK0  0x02
#define ER_MARK  0x01

/* extension commands (OUT C4h) */
enum {
    X_VERSION = 0x00, X_GETTIME, X_SETTIME, X_OPENFILE, X_READFILE, X_WRITEFILE, X_CLOSEFILE, X_BOOTLOADER,
    X_OPENDIR, X_READDIR, X_MOUNTDRIVE, X_SEEKFILE, X_INFODRIVE, X_IMAGE, X_READ_HEADER
};

#define FREHD_MAXDRIVES 4
#define FREHD_COMPAT_MAJOR 2      /* version reported to FreHD utilities */
#define FREHD_COMPAT_MINOR 16
#define FREHD_ROM_MAX 4096        /* FREHD.ROM loader streamed on IN C4h */
#define FR_DISK_FULL_CODE 20      /* FreHD's extra FRESULT for short writes */

/* ---- bus side (core 1): RAM-only, fast ---- */
uint8_t frehd_in(uint8_t reg);
void frehd_out(uint8_t reg, uint8_t val);
void frehd_bus_reset(void);              /* ECB RESET*: registers only */

/* ---- main side (core 0) ---- */
void frehd_init(void);                   /* once at power-up */
void frehd_card_mounted(int ok);         /* after f_mount succeeds (1) or the card goes away (0) */
int  frehd_poll(void);                   /* run a pending action; returns 1 if one ran */
void frehd_tick_ms(uint32_t ms);         /* flush dirty images after a quiet period */
int  frehd_activity(void);               /* for the ACT LED: a drive is dirty or an action ran recently */

/* ---- platform hooks (main.c on the Pico, test harness on the host) ---- */
void plat_get_time(uint8_t t[6]);        /* sec, min, hour, year (0-99 = 2000+), day, month; binary */
void plat_set_time(const uint8_t t[6]);
void plat_bootloader(void);              /* never returns on the Pico (USB BOOTSEL) */

#endif
