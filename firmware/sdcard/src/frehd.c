/*
 * frehd.c - FreHD-compatible hard-disk emulator core. See frehd.h.
 *
 * Protocol summary (Z80 view, ports C0h-CFh):
 *   C8 DATA streams the sector buffer. READ (cmd 2x) sets BUSY, the main side
 *   reads the sector and sets DRQ; the last byte read drops DRQ. WRITE (3x)
 *   sets DRQ at once; the last byte written sets BUSY while the main side
 *   writes the sector. SEEK/VERIFY (7x/4x) check the address. While BUSY, every
 *   read returns the status and writes are ignored.
 *   C4 COMMAND2 starts an extension command ("step 0"); commands that take
 *   parameters run again ("step 1") once the Z80 has written SIZE2 (C3) bytes
 *   to DATA2 (C2). Results are read back from DATA2, their length from SIZE2,
 *   a FatFs result code from ERROR2 (C5).
 * Image files: 256-byte Reed header, then sectors at
 *   ((cyl * heads + head) * secs + secnum % secs) * secsize + 256.
 */
#include <string.h>
#include "ff.h"
#include "frehd.h"
#include "image.h"

#ifdef FREHD_PICO
#include "pico.h"
#include "hardware/sync.h"
#define FREHD_RAM(f) __not_in_flash_func(f)   /* core 1 calls these; keep them out of XIP flash */
#define FREHD_BARRIER() __dmb()               /* order state updates between the two cores */
#endif

#ifndef FREHD_RAM
#define FREHD_RAM(f) f            /* Pico build: place bus handlers in RAM */
#endif
#ifndef FREHD_BARRIER
#define FREHD_BARRIER() do { } while (0)
#endif

#define DEFAULT_STATUS (ST_READY | ST_SEEKDONE | ST_DRQ)
#define ERROR_STATUS   (ST_READY | ST_SEEKDONE | ST_ERR)
#define HDR_SIZE 256
#define SYNC_DELAY_MS 3000

enum { A_NONE = 0, A_READ, A_WRITE, A_SEEK, A_EXTRA0, A_EXTRA1 };

typedef struct {
    FIL f;
    char name[13];
    uint8_t avail, writeprot;
    uint16_t cyls;
    uint8_t heads, secs;
    uint32_t dirty_ms;
} drive_t;

/* ---- state shared between the bus side and the main side ---- */
static volatile uint8_t st_status = ST_READY, st_error, st_busy, st_action;
static volatile uint8_t st_seccnt, st_secnum, st_sdh, st_drive, st_head, st_control, st_wp, st_command;
static volatile uint16_t st_cyl, st_secsize = 256, st_bytesdone;
static volatile uint8_t st_command2, st_error2, st_present;
static volatile uint16_t st_size2 = 256, st_bytesdone2;
static uint8_t sector_buf[1024];
static uint8_t extra_buf[256];
static uint8_t rom[FREHD_ROM_MAX];
static volatile uint16_t rom_len, rom_ptr;
static volatile uint8_t rom_ram;
static volatile uint8_t st_gen;          /* bumped by every bus reset: cancels an action in progress */

/* ---- main side only ---- */
static drive_t drv[FREHD_MAXDRIVES];
static uint8_t file_open, dir_open, mounted;
static FIL xfile;
static DIR xdir;
static uint32_t recent_ms;

/* ================================================================ bus side */
static void FREHD_RAM(start_action)(uint8_t a)
{
    st_status = ST_BUSY | ST_CIP;
    st_busy = 1;
    FREHD_BARRIER();
    st_action = a;
}

uint8_t FREHD_RAM(frehd_in)(uint8_t reg)
{
    uint8_t v;
    if (st_busy)
        return st_status;
    FREHD_BARRIER();                          /* see core 0's buffer writes before reading them */
    switch (reg & 0xF) {
    case R_WP:       return st_wp;
    case R_CONTROL:  return st_control;
    case R_DATA2:    v = extra_buf[st_bytesdone2 & 0xFF]; st_bytesdone2++; return v;
    case R_SIZE2:    return (uint8_t)st_size2;
    case R_COMMAND2: {                       /* ROM loader stream */
        uint16_t i = rom_ptr++;
        if (i == 2) return rom_ram;
        return i < rom_len ? rom[i] : 0xFF;
    }
    case R_ERROR2:   return st_error2;
    case R_DATA:
        if (st_bytesdone < st_secsize) {
            v = sector_buf[st_bytesdone++];
            if (st_bytesdone == st_secsize)
                st_status = ST_READY | ST_SEEKDONE;
            return v;
        }
        return 0xFF;
    case R_ERROR:    return st_error;
    case R_SECCNT:   return st_seccnt;
    case R_SECNUM:   return st_secnum;
    case R_CYLLO:    return (uint8_t)st_cyl;
    case R_CYLHI:    return (uint8_t)(st_cyl >> 8);
    case R_SDH:      return st_sdh;
    case R_STATUS:   return st_status;
    default:         return 0xFF;            /* C6/C7: no UART */
    }
}

void FREHD_RAM(frehd_out)(uint8_t reg, uint8_t v)
{
    if (st_busy)
        return;
    FREHD_BARRIER();
    switch (reg & 0xF) {
    case R_CONTROL:
        st_control = v;
        if (!(v & 0x08)) {
            st_status = ST_READY | ST_SEEKDONE;
            if (!st_present) { st_status |= ST_ERR; st_error = ER_NF; }
        }
        break;
    case R_DATA2:
        extra_buf[st_bytesdone2 & 0xFF] = v;
        if (++st_bytesdone2 == st_size2)
            start_action(A_EXTRA1);
        break;
    case R_SIZE2:    st_size2 = v ? v : 256; break;
    case R_COMMAND2:
        st_command2 = v;
        st_bytesdone2 = 0;
        start_action(A_EXTRA0);
        break;
    case R_ERROR2:   rom_ram = v; rom_ptr = 0; break;
    case R_DATA:
        if ((st_command & 0xF0) == 0x30 && st_bytesdone < st_secsize) {
            sector_buf[st_bytesdone++] = v;
            if (st_bytesdone == st_secsize)
                start_action(A_WRITE);
        }
        break;
    case R_SECCNT:   st_seccnt = v; break;
    case R_SECNUM:   st_secnum = v; break;
    case R_CYLLO:    st_cyl = (uint16_t)((st_cyl & 0x300) | v); break;
    case R_CYLHI:    st_cyl = (uint16_t)((st_cyl & 0xFF) | ((v & 3) << 8)); break;
    case R_SDH: {
        static const uint16_t sz[4] = { 256, 512, 1024, 128 };
        st_sdh = v;
        st_secsize = sz[(v >> 5) & 3];
        st_drive = (v >> 3) & 3;
        st_head = v & 7;
        st_status = ST_READY | ST_SEEKDONE;
        break;
    }
    case R_STATUS:                           /* command register */
        st_command = v;
        st_bytesdone = 0;
        st_bytesdone2 = 0;
        st_error = 0;
        switch (v & 0xF0) {
        case 0x10: st_cyl = 0; st_status = ST_READY | ST_SEEKDONE; break;      /* RESTORE */
        case 0x20: start_action(A_READ); break;                                 /* READ */
        case 0x30:                                                              /* WRITE */
            if (v & 0x04) { st_error = ER_ABRT; st_status = ERROR_STATUS; }    /* multi-sector: no */
            else st_status = DEFAULT_STATUS;
            break;
        case 0x40: case 0x70: start_action(A_SEEK); break;                      /* VERIFY, SEEK */
        case 0x90: st_status = ST_READY; break;                                 /* TEST */
        default: st_status = ST_READY | ST_SEEKDONE; break;                     /* FORMAT, INIT, ... */
        }
        break;
    default: break;                          /* C0 WP, C9 precomp, C6/C7 */
    }
}

void FREHD_RAM(frehd_bus_reset)(void)
{
    st_gen++;
    st_action = A_NONE;
    st_busy = 0;
    st_status = ST_READY | ST_SEEKDONE;
    st_error = st_seccnt = st_secnum = st_sdh = st_drive = st_head = st_command = 0;
    st_cyl = 0;
    st_secsize = 256;
    st_bytesdone = st_bytesdone2 = 0;
    st_size2 = 256;
    rom_ptr = 0;
}

/* ================================================================ images */
static void put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

static uint32_t get32(const uint8_t *p)
{
    return p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void default_header(uint8_t *h)
{
    /* 840 cylinders x 6 heads x 32 sectors x 256 bytes (~40 MB), as FreHD creates */
    uint8_t t[6];
    unsigned i, sum = 0;
    memset(h, 0, HDR_SIZE);
    plat_get_time(t);
    h[0] = 0x56; h[1] = 0xCB; h[2] = 0x10; h[4] = 1; h[5] = 4; h[6] = 0;
    h[10] = 0x42;
    h[12] = t[5]; h[13] = t[4]; h[14] = (uint8_t)(t[3] + 100);
    h[26] = 6;
    h[27] = 840 >> 8;
    h[28] = 840 & 0xFF;
    h[29] = 192;
    h[30] = 0;
    h[31] = 1;
    for (i = 0; i < 32; i++)
        if (i != 3) sum += h[i];
    h[3] = (uint8_t)(sum ^ 0x4C);
}

static void update_wp(void)
{
    uint8_t wp = 0, present = 0;
    int i;
    for (i = 0; i < FREHD_MAXDRIVES; i++) {
        if (drv[i].avail) present = 1;
        if (drv[i].avail && drv[i].writeprot)
            wp |= (uint8_t)(0x80 >> i) | 0x02;
    }
    st_wp = wp;
    st_present = present;
}

static void close_drive(int i)
{
    if (drv[i].avail) {
        f_sync(&drv[i].f);
        f_close(&drv[i].f);
    }
    drv[i].avail = 0;
    drv[i].dirty_ms = 0;
}

#define OPT_SLOW   0x01
#define OPT_CREATE 0x02
#define OPT_RO     0x04

static FRESULT open_drive(int i, uint8_t opt)
{
    drive_t *d = &drv[i];
    uint8_t h[HDR_SIZE];
    UINT n = 0;
    FRESULT r;
    unsigned spc;
    BYTE mode = FA_READ | ((opt & OPT_RO) ? 0 : FA_WRITE) | ((opt & OPT_CREATE) ? FA_OPEN_ALWAYS : 0);

    close_drive(i);
    if (!d->name[0]) {
        memcpy(d->name, "hard4-0", 8);
        d->name[6] = (char)('0' + i);
    }
    d->writeprot = (opt & OPT_RO) ? 1 : 0;
    r = f_open(&d->f, d->name, mode);
    if (r == FR_DENIED && !(opt & OPT_RO)) {              /* read-only file: mount it protected */
        r = f_open(&d->f, d->name, FA_READ);
        d->writeprot = 1;
    }
    if (r != FR_OK)
        return r;
    if (f_size(&d->f) == 0 && (opt & OPT_CREATE) && !d->writeprot) {
        default_header(h);
        r = f_write(&d->f, h, HDR_SIZE, &n);
        if (r == FR_OK && n != HDR_SIZE) r = FR_DISK_ERR;
        if (r == FR_OK) r = f_lseek(&d->f, 0);
    }
    if (r == FR_OK)
        r = f_read(&d->f, h, HDR_SIZE, &n);
    if (r == FR_OK && (n != HDR_SIZE || h[0] != 0x56 || h[1] != 0xCB || (h[2] != 0x10 && h[2] != 0x11)))
        r = FR_NO_FILESYSTEM;
    if (r == FR_OK) {
        d->cyls = (uint16_t)(((h[27] & 3) << 8) + h[28]);
        spc = h[29] ? h[29] : 256;
        if (h[26]) { d->heads = h[26]; d->secs = (uint8_t)(spc / h[26]); }
        else { d->secs = 32; d->heads = (uint8_t)(spc / 32); }
        if (!d->heads || d->heads > 8 || !d->secs || spc % d->secs || !d->cyls)
            r = FR_NO_FILESYSTEM;
        if (h[7] & 0x80) d->writeprot = 1;
    }
    if (r != FR_OK) {
        f_close(&d->f);
        return r;
    }
    d->avail = 1;
    return FR_OK;
}

/* seek to the sector addressed by the task-file registers; 0 = bad address */
static int seek_sector(drive_t **out)
{
    drive_t *d = &drv[st_drive];
    uint32_t lba, off;
    if (!d->avail || st_head >= d->heads || st_cyl >= d->cyls)
        return 0;
    lba = ((uint32_t)st_cyl * d->heads + st_head) * d->secs + (st_secnum % d->secs);
    off = lba * st_secsize + HDR_SIZE;
    if (f_lseek(&d->f, off) != FR_OK)
        return 0;
    *out = d;
    return 1;
}

static uint8_t do_read(void)
{
    drive_t *d;
    UINT n;
    if (!seek_sector(&d)) { st_error = ER_NF; return ERROR_STATUS; }
    if (f_read(&d->f, sector_buf, st_secsize, &n) != FR_OK) { st_error = ER_DATA; return ERROR_STATUS; }
    if (n < st_secsize)                       /* past the end of a sparse image: blank */
        memset(sector_buf + n, 0, st_secsize - n);
    return DEFAULT_STATUS;
}

static uint8_t do_write(void)
{
    drive_t *d;
    UINT n;
    if (!seek_sector(&d)) { st_error = ER_NF; return ERROR_STATUS; }
    if (d->writeprot) { st_error = ER_ABRT; return ERROR_STATUS | ST_WRERR; }
    if (f_write(&d->f, sector_buf, st_secsize, &n) != FR_OK || n != st_secsize) {
        st_error = ER_DATA;
        return ERROR_STATUS;
    }
    d->dirty_ms = SYNC_DELAY_MS;
    return ST_READY | ST_SEEKDONE;
}

static uint8_t do_seek(void)
{
    drive_t *d;
    if (!seek_sector(&d)) { st_error = ER_NF; return ERROR_STATUS; }
    return ST_READY | ST_SEEKDONE;
}

/* ================================================================ extension commands */
static uint8_t fail(FRESULT r)
{
    st_error2 = (uint8_t)r;
    return ERROR_STATUS;
}

static void cstr(char *dst, unsigned max, const uint8_t *src, unsigned len)
{
    unsigned i;
    for (i = 0; i < len && i + 1 < max && src[i]; i++)
        dst[i] = (char)src[i];
    dst[i] = 0;
}

static uint8_t extra(uint8_t cmd, int step)
{
    FRESULT r;
    UINT n;
    char path[260];
    int i;

    st_error2 = 0;
    switch (cmd) {
    case X_VERSION:
        extra_buf[0] = FREHD_COMPAT_MAJOR; extra_buf[1] = FREHD_COMPAT_MINOR;
        extra_buf[2] = rom_len > 6 ? rom[6] : 0; extra_buf[3] = rom_len > 7 ? rom[7] : 0;
        extra_buf[4] = 0; extra_buf[5] = 0;
        st_size2 = 6;
        return DEFAULT_STATUS;
    case X_GETTIME:
        plat_get_time(extra_buf);
        st_size2 = 6;
        return DEFAULT_STATUS;
    case X_SETTIME:
        if (step == 0) st_size2 = 6;
        else plat_set_time(extra_buf);
        return DEFAULT_STATUS;
    case X_OPENFILE:
        if (step == 0) return DEFAULT_STATUS;
        if (file_open) { f_close(&xfile); file_open = 0; }
        cstr(path, sizeof path, extra_buf + 1, st_size2 - 1u);
        r = f_open(&xfile, path, extra_buf[0]);
        if (r != FR_OK) { st_size2 = 0; return fail(r); }
        file_open = 1;
        put32(extra_buf, (uint32_t)f_size(&xfile));
        st_size2 = 4;
        return DEFAULT_STATUS;
    case X_READFILE:
        if (!file_open) return fail(FR_NO_FILE);
        r = f_read(&xfile, extra_buf, st_size2, &n);
        if (r != FR_OK) return fail(r);
        st_size2 = (uint16_t)n;
        return n ? DEFAULT_STATUS : (ST_READY | ST_SEEKDONE);
    case X_WRITEFILE:
        if (!file_open) return fail(FR_NO_FILE);
        if (step == 0) { st_size2 = 256; return DEFAULT_STATUS; }
        r = f_write(&xfile, extra_buf, st_size2, &n);
        if (r != FR_OK) return fail(r);
        if (n != st_size2) return fail((FRESULT)FR_DISK_FULL_CODE);
        return DEFAULT_STATUS;
    case X_CLOSEFILE:
        if (file_open) {
            r = f_close(&xfile);
            if (r != FR_OK) return fail(r);
            file_open = 0;
        }
        return ST_READY | ST_SEEKDONE;
    case X_BOOTLOADER:
        if (step == 0) { st_size2 = 2; return DEFAULT_STATUS; }
        if (extra_buf[0] == 0x15 && extra_buf[1] == 0x04)
            plat_bootloader();
        return DEFAULT_STATUS;
    case X_OPENDIR:
        if (step == 0) return DEFAULT_STATUS;
        if (dir_open) { f_closedir(&xdir); dir_open = 0; }
        cstr(path, sizeof path, extra_buf, st_size2);
        r = f_opendir(&xdir, path);
        if (r != FR_OK) { st_size2 = 0; return fail(r); }
        dir_open = 1;
        return DEFAULT_STATUS;
    case X_READDIR: {
        FILINFO fno;
        const char *nm;
        if (!dir_open) return fail(FR_NO_PATH);
        r = f_readdir(&xdir, &fno);
        if (r != FR_OK) return fail(r);
        if (!fno.fname[0]) return ST_READY | ST_SEEKDONE;
        nm = fno.fname;
#if defined(FF_USE_LFN) && FF_USE_LFN
        if (strlen(nm) > 12) nm = fno.altname;    /* utilities expect 8.3 names */
#endif
        /* legacy FatFs FILINFO layout: fsize(4) fdate(2) ftime(2) fattrib(1) fname[13] */
        memset(extra_buf, 0, 22);
        put32(extra_buf, (uint32_t)fno.fsize);
        extra_buf[4] = (uint8_t)fno.fdate; extra_buf[5] = (uint8_t)(fno.fdate >> 8);
        extra_buf[6] = (uint8_t)fno.ftime; extra_buf[7] = (uint8_t)(fno.ftime >> 8);
        extra_buf[8] = fno.fattrib;
        for (i = 0; i < 12 && nm[i]; i++) extra_buf[9 + i] = (uint8_t)nm[i];
        st_size2 = 22;
        return DEFAULT_STATUS;
    }
    case X_MOUNTDRIVE:
        if (step == 0) return DEFAULT_STATUS;
        if (st_size2 < 3 || extra_buf[0] >= FREHD_MAXDRIVES) return fail(FR_INVALID_PARAMETER);
        i = extra_buf[0];
        close_drive(i);
        cstr(drv[i].name, sizeof drv[i].name, extra_buf + 2, st_size2 - 2u);
        r = open_drive(i, extra_buf[1]);
        update_wp();
        if (r != FR_OK) return fail(r);
        return DEFAULT_STATUS;
    case X_SEEKFILE:
        if (step == 0) {
            if (!file_open) return fail(FR_NO_FILE);
            put32(extra_buf, (uint32_t)f_tell(&xfile));
            st_size2 = 4;
            return DEFAULT_STATUS;
        }
        if (!file_open) return fail(FR_NO_FILE);
        r = f_lseek(&xfile, get32(extra_buf));
        if (r != FR_OK) return fail(r);
        return DEFAULT_STATUS;
    case X_INFODRIVE:
        for (i = 0; i < FREHD_MAXDRIVES; i++) {
            uint8_t *p = extra_buf + 19 * i;
            memset(p, 0, 19);
            p[0] = drv[i].avail ? 1 : 0;
            p[1] = drv[i].writeprot;
            p[2] = (uint8_t)(drv[i].cyls >> 8); p[3] = (uint8_t)drv[i].cyls;
            p[4] = drv[i].heads; p[5] = drv[i].secs;
            memcpy(p + 6, drv[i].name, 13);
        }
        st_size2 = 19 * FREHD_MAXDRIVES;
        return DEFAULT_STATUS;
    case X_IMAGE: {                              /* read-only DMK/JV3/JV1 floppy images (image.c) */
        uint16_t len = st_size2;
        if (step == 0) return DEFAULT_STATUS;
        st_error2 = image_cmd(extra_buf, len, &len);
        st_size2 = len;
        return DEFAULT_STATUS;
    }
    case X_READ_HEADER:
        if (!drv[st_drive].avail) return ERROR_STATUS;
        r = f_lseek(&drv[st_drive].f, 0);
        if (r != FR_OK) { st_error2 = (uint8_t)r; return DEFAULT_STATUS; }
        r = f_read(&drv[st_drive].f, extra_buf, HDR_SIZE, &n);
        if (r != FR_OK) return fail(r);
        st_size2 = (uint16_t)n;
        return DEFAULT_STATUS;
    default:
        return DEFAULT_STATUS;
    }
}

/* ================================================================ main side */
static void load_rom(void)
{
    FIL f;
    UINT n = 0;
    rom_len = 0;
    if (f_open(&f, "FREHD.ROM", FA_READ) == FR_OK) {
        if (f_read(&f, rom, sizeof rom, &n) == FR_OK)
            rom_len = (uint16_t)n;
        f_close(&f);
    }
}

void frehd_init(void)
{
    memset(drv, 0, sizeof drv);
    file_open = dir_open = mounted = 0;
    frehd_bus_reset();
    st_wp = 0;
}

void frehd_card_mounted(int ok)
{
    int i;
    if (file_open) { f_close(&xfile); file_open = 0; }
    if (dir_open) { f_closedir(&xdir); dir_open = 0; }
    for (i = 0; i < FREHD_MAXDRIVES; i++)
        close_drive(i);
    mounted = (uint8_t)(ok != 0);
    image_reset();
    rom_len = 0;
    if (ok) {
        load_rom();
        for (i = 0; i < FREHD_MAXDRIVES; i++)
            open_drive(i, 0);
    }
    update_wp();
}

int frehd_poll(void)
{
    uint8_t a = st_action, s, gen = st_gen;
    if (a == A_NONE)
        return 0;
    FREHD_BARRIER();
    switch (a) {
    case A_READ:   s = do_read(); break;
    case A_WRITE:  s = do_write(); break;
    case A_SEEK:   s = do_seek(); break;
    case A_EXTRA0: s = extra(st_command2, 0); break;
    case A_EXTRA1: s = extra(st_command2, 1); break;
    default:       s = ST_READY | ST_SEEKDONE; break;
    }
    if (a == A_EXTRA0 || a == A_EXTRA1)
        st_bytesdone2 = 0;                    /* results (or the next parameters) start at byte 0 */
    st_status = s;
    st_action = A_NONE;
    FREHD_BARRIER();
    st_busy = 0;
    if (st_gen != gen) {                      /* the Z80 was reset meanwhile: drop the result */
        st_status = ST_READY | ST_SEEKDONE;
        st_bytesdone = st_bytesdone2 = 0;
    }
    recent_ms = 100;
    return 1;
}

void frehd_tick_ms(uint32_t ms)
{
    int i;
    for (i = 0; i < FREHD_MAXDRIVES; i++) {
        if (!drv[i].dirty_ms) continue;
        if (drv[i].dirty_ms <= ms) {
            drv[i].dirty_ms = 0;
            if (drv[i].avail) f_sync(&drv[i].f);
        } else {
            drv[i].dirty_ms -= ms;
        }
    }
    recent_ms = recent_ms > ms ? recent_ms - ms : 0;
}

int frehd_activity(void)
{
    int i;
    for (i = 0; i < FREHD_MAXDRIVES; i++)
        if (drv[i].dirty_ms) return 1;
    return recent_ms != 0;
}
