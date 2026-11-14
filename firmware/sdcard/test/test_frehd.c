/* Host tests for frehd.c: plays the Z80 side of the FreHD protocol against the core. */
#define _CRT_SECURE_NO_WARNINGS
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include "ff.h"
#include "../src/frehd.h"

static int fails, checks;
#define CHECK(c, ...) do { checks++; if (!(c)) { fails++; printf("FAIL line %d: ", __LINE__); \
    printf(__VA_ARGS__); printf("\n"); } } while (0)

static uint8_t clock_t6[6] = { 30, 15, 12, 26, 13, 11 };   /* 12:15:30 13 Nov 2026 */
static int boot_called, reset_in_action;
void plat_get_time(uint8_t t[6]) { memcpy(t, clock_t6, 6); if (reset_in_action) { reset_in_action = 0; frehd_bus_reset(); } }
void plat_set_time(const uint8_t t[6]) { memcpy(clock_t6, t, 6); }
void plat_bootloader(void) { boot_called = 1; }

static char root[MAX_PATH];

static uint8_t in(int port) { return frehd_in((uint8_t)(port - 0xC0)); }
static void out(int port, uint8_t v) { frehd_out((uint8_t)(port - 0xC0), v); }

/* poll status like a driver; let the "other core" run while BUSY */
static uint8_t wait_ready(void)
{
    int n = 0;
    uint8_t s;
    while ((s = in(0xCF)) & ST_BUSY) {
        frehd_poll();
        if (++n > 10) { printf("stuck BUSY\n"); exit(2); }
    }
    return s;
}

static uint8_t xcmd(uint8_t cmd, const uint8_t *data, int len)
{
    int i;
    if (len) out(0xC3, (uint8_t)len);
    out(0xC4, cmd);
    wait_ready();
    for (i = 0; i < len; i++) out(0xC2, data[i]);
    return wait_ready();
}

static void path(char *out_, const char *name) { snprintf(out_, MAX_PATH, "%s\\%s", root, name); }

static void task(int drive, int head, int cyl, int sec, int sizecode)
{
    out(0xCE, (uint8_t)((sizecode << 5) | (drive << 3) | head));
    out(0xCC, (uint8_t)cyl);
    out(0xCD, (uint8_t)(cyl >> 8));
    out(0xCB, (uint8_t)sec);
}

static long file_size(const char *name)
{
    char p[MAX_PATH];
    FILE *f;
    long n;
    path(p, name);
    f = fopen(p, "rb");
    if (!f) return -1;
    fseek(f, 0, SEEK_END);
    n = ftell(f);
    fclose(f);
    return n;
}

static void read_at(const char *name, long off, uint8_t *buf, int n)
{
    char p[MAX_PATH];
    FILE *f;
    path(p, name);
    f = fopen(p, "rb");
    memset(buf, 0xEE, n);
    fseek(f, off, SEEK_SET);
    fread(buf, 1, n, f);
    fclose(f);
}

/* ---- floppy image builders for the IMAGE tests ---- */
static uint8_t pat_dmk(int t, int side, int s, int j) { return (uint8_t)(t * 16 + side * 8 + s + j); }
static uint8_t pat_jv3(int t, int s, int side, int j) { return (uint8_t)(t * 31 + s * 7 + side * 100 + j); }

static void make_dmk(const char *name)
{
    /* 2 tracks, double-sided; per track slot: sectors 0-1 double density, 2-3 single
       density stored byte-doubled. Track 0 side 0 sector 1 has an F8 mark, sector 3 FA. */
    enum { TLEN = 0x1900 };
    static uint8_t img[16 + 4 * TLEN];
    char p[MAX_PATH];
    FILE *fp;
    int t, side, s, j, k;
    memset(img, 0, sizeof img);
    img[1] = 2; img[2] = TLEN & 0xFF; img[3] = TLEN >> 8; img[4] = 0;
    for (t = 0; t < 2; t++) for (side = 0; side < 2; side++) {
        uint8_t *tr = img + 16 + (t * 2 + side) * TLEN;
        for (s = 0; s < 4; s++) {
            int dd = s < 2, st = dd ? 1 : 2, pos = 128 + s * 800, q = pos;
            uint8_t dam = (t == 0 && side == 0 && s == 1) ? 0xF8 : (t == 0 && side == 0 && s == 3) ? 0xFA : 0xFB;
            uint8_t id[7] = { 0xFE, (uint8_t)t, (uint8_t)side, (uint8_t)s, 1, 0x12, 0x34 };
            unsigned e = (unsigned)pos | (dd ? 0x8000u : 0);
            tr[2 * s] = (uint8_t)e; tr[2 * s + 1] = (uint8_t)(e >> 8);
            for (j = 0; j < 7; j++) for (k = 0; k < st; k++) tr[q++] = id[j];
            for (j = 0; j < (dd ? 12 : 6); j++) for (k = 0; k < st; k++) tr[q++] = dd ? 0x4E : 0xFF;
            for (k = 0; k < st; k++) tr[q++] = dam;
            for (j = 0; j < 256; j++) for (k = 0; k < st; k++) tr[q++] = pat_dmk(t, side, s, j);
        }
    }
    path(p, name);
    fp = fopen(p, "wb"); fwrite(img, 1, sizeof img, fp); fclose(fp);
}

static const uint8_t jv3e[][3] = {
    { 0, 0, 0x00 }, { 0, 1, 0x00 }, { 0, 2, 0xA0 },           /* (0,2): double density, F8 mark */
    { 0xFF, 0xFF, 0x03 },                                       /* free entry, 256-byte slot */
    { 1, 0, 0x00 }, { 1, 1, 0x01 }, { 1, 2, 0x00 },           /* (1,1): 128-byte sector */
    { 0, 0, 0x10 } };                                           /* side 1 */

static void make_jv3(const char *name)
{
    char p[MAX_PATH];
    FILE *fp;
    unsigned i, j, size;
    static uint8_t hdr[8704];
    memset(hdr, 0xFF, sizeof hdr);
    for (i = 0; i < sizeof jv3e / 3; i++) memcpy(hdr + 3 * i, jv3e[i], 3);
    path(p, name);
    fp = fopen(p, "wb");
    fwrite(hdr, 1, sizeof hdr, fp);
    for (i = 0; i < sizeof jv3e / 3; i++) {
        size = (jv3e[i][2] & 3) == 1 && jv3e[i][0] != 0xFF ? 128 : 256;
        for (j = 0; j < size; j++)
            fputc(pat_jv3(jv3e[i][0], jv3e[i][1], (jv3e[i][2] & 0x10) ? 1 : 0, (int)j), fp);
    }
    fclose(fp);
}

static void make_jv1(const char *name)
{
    char p[MAX_PATH];
    FILE *fp;
    int t, s, j;
    path(p, name);
    fp = fopen(p, "wb");
    for (t = 0; t < 35; t++) for (s = 0; s < 10; s++) for (j = 0; j < 256; j++) {
        int v = (t == 0 && s == 0 && j < 2) ? (j ? 0xFE : 0x00) : (t * 10 + s + j) & 0xFF;
        fputc(v, fp);
    }
    fclose(fp);
}

/* IMAGE open: returns ERROR2, fills info[5] */
static int img_open(int unitn, const char *name, uint8_t *info)
{
    uint8_t rq[64];
    int n = (int)strlen(name), i;
    rq[0] = (uint8_t)unitn; rq[1] = 0;
    memcpy(rq + 2, name, n + 1);
    xcmd(X_IMAGE, rq, n + 3);
    if (in(0xC5) == 0) for (i = 0; i < 5; i++) info[i] = in(0xC2);
    return in(0xC5);
}

static int img_read(int unitn, int track, int sector, uint8_t *out)
{
    uint8_t rq[4] = { (uint8_t)unitn, 1, (uint8_t)track, (uint8_t)sector };
    int e, i;
    xcmd(X_IMAGE, rq, 4);
    e = in(0xC5);
    if (e == 0 || e == 6) for (i = 0; i < 256; i++) out[i] = in(0xC2);
    return e;
}

static int same(const uint8_t *b, uint8_t (*pf)(int, int, int, int), int a1, int a2, int a3)
{
    int j;
    for (j = 0; j < 256; j++) if (b[j] != pf(a1, a2, a3, j)) return 0;
    return 1;
}

int main(void)
{
    uint8_t buf[1024], s, hdr[256];
    int i, ok;
    char p[MAX_PATH];
    FILE *f;

    GetTempPathA(MAX_PATH, root);
    strcat(root, "frehd_test");
    CreateDirectoryA(root, NULL);
    path(p, "*");
    { WIN32_FIND_DATAA fd; HANDLE h = FindFirstFileA(p, &fd);
      if (h != INVALID_HANDLE_VALUE) { do { char q[MAX_PATH]; if (fd.cFileName[0] == '.') continue;
          path(q, fd.cFileName); SetFileAttributesA(q, FILE_ATTRIBUTE_NORMAL); DeleteFileA(q);
      } while (FindNextFileA(h, &fd)); FindClose(h); } }
    ffhost_root(root);

    /* ---- no card ---- */
    frehd_init();
    frehd_card_mounted(0);
    out(0xC1, 0x00);
    CHECK((in(0xCF) & ST_ERR) && in(0xC9) == ER_NF, "control write with no drive -> ERR/NF (st %02X)", in(0xCF));
    out(0xC1, 0x0C);

    /* ---- card with FREHD.ROM, no images yet ---- */
    path(p, "FREHD.ROM");
    f = fopen(p, "wb");
    for (i = 0; i < 100; i++) fputc(i ^ 0x5A, f);
    fclose(f);
    frehd_card_mounted(1);
    CHECK(in(0xC0) == 0, "WP register with no drives");
    out(0xC5, 0x77);
    CHECK(in(0xC4) == (0 ^ 0x5A) && in(0xC4) == (1 ^ 0x5A) && in(0xC4) == 0x77 && in(0xC4) == (3 ^ 0x5A),
          "ROM stream with RAM byte at index 2");

    /* ---- MOUNTDRIVE with create ---- */
    {
        uint8_t m[16] = { 0, 0x02, 'h', 'a', 'r', 'd', '4', '-', '0' };
        s = xcmd(X_MOUNTDRIVE, m, 9);
        CHECK(s == (ST_READY | ST_SEEKDONE | ST_DRQ) && in(0xC5) == 0, "MOUNTDRIVE create (st %02X err2 %d)",
              s, in(0xC5));
        CHECK(file_size("hard4-0") == 256, "new image is just the header (%ld)", file_size("hard4-0"));
        read_at("hard4-0", 0, hdr, 256);
        { unsigned sum = 0; for (i = 0; i < 32; i++) if (i != 3) sum += hdr[i];
          CHECK(hdr[0] == 0x56 && hdr[1] == 0xCB && hdr[3] == (uint8_t)(sum ^ 0x4C), "header magic/checksum"); }
    }

    /* ---- INFODRIVE ---- */
    s = xcmd(X_INFODRIVE, NULL, 0);
    CHECK(in(0xC3) == 76, "INFODRIVE size %d", in(0xC3));
    for (i = 0; i < 76; i++) buf[i] = in(0xC2);
    CHECK(buf[0] == 1 && buf[1] == 0 && (buf[2] << 8 | buf[3]) == 840 && buf[4] == 6 && buf[5] == 32 &&
          !strcmp((char *)buf + 6, "hard4-0") && buf[19] == 0, "INFODRIVE drive 0 geometry");

    /* ---- sector write ---- */
    task(0, 2, 100, 5, 0);
    out(0xCF, 0x30);
    CHECK(in(0xCF) == (ST_READY | ST_SEEKDONE | ST_DRQ), "WRITE -> DRQ at once");
    for (i = 0; i < 256; i++) out(0xC8, (uint8_t)(i * 7 + 3));
    CHECK(in(0xCF) == (ST_BUSY | ST_CIP) && in(0xC8) == (ST_BUSY | ST_CIP), "after last byte: BUSY, reads give status");
    out(0xCA, 0x99);                             /* ignored while busy */
    s = wait_ready();
    CHECK(s == (ST_READY | ST_SEEKDONE), "WRITE done (st %02X)", s);
    frehd_tick_ms(5000);                         /* let the core flush the image */
    read_at("hard4-0", ((100L * 6 + 2) * 32 + 5) * 256 + 256, buf, 256);
    ok = 1;
    for (i = 0; i < 256; i++) if (buf[i] != (uint8_t)(i * 7 + 3)) ok = 0;
    CHECK(ok, "sector landed at the right file offset");
    CHECK(in(0xCA) != 0x99, "register write ignored while BUSY");

    /* ---- sector read back ---- */
    frehd_tick_ms(5000);
    task(0, 2, 100, 5, 0);
    out(0xCF, 0x20);
    CHECK(in(0xCF) & ST_BUSY, "READ -> BUSY");
    s = wait_ready();
    CHECK(s == (ST_READY | ST_SEEKDONE | ST_DRQ), "READ ready with DRQ (st %02X)", s);
    ok = 1;
    for (i = 0; i < 256; i++) if (in(0xC8) != (uint8_t)(i * 7 + 3)) ok = 0;
    CHECK(ok, "read data matches");
    CHECK(in(0xCF) == (ST_READY | ST_SEEKDONE), "DRQ drops after the last byte");

    /* ---- sparse area reads as zeros; bad addresses ---- */
    task(0, 0, 800, 0, 0);
    out(0xCF, 0x20);
    s = wait_ready();
    ok = 1;
    for (i = 0; i < 256; i++) if (in(0xC8) != 0) ok = 0;
    CHECK(s & ST_DRQ && ok, "read past end of sparse image gives zeros");
    task(0, 6, 0, 0, 0);
    out(0xCF, 0x20);
    s = wait_ready();
    CHECK((s & ST_ERR) && in(0xC9) == ER_NF, "head out of range -> NF");
    task(0, 0, 840, 0, 0);
    out(0xCF, 0x70);
    s = wait_ready();
    CHECK((s & ST_ERR) && in(0xC9) == ER_NF, "SEEK beyond last cylinder -> NF");
    task(0, 5, 839, 31, 0);
    out(0xCF, 0x70);
    CHECK(wait_ready() == (ST_READY | ST_SEEKDONE), "SEEK to last sector OK");
    task(1, 0, 0, 0, 0);
    out(0xCF, 0x20);
    CHECK((wait_ready() & ST_ERR) && in(0xC9) == ER_NF, "READ on a drive with no image -> NF");
    out(0xCF, 0x34);
    CHECK((in(0xCF) & ST_ERR) && in(0xC9) == ER_ABRT, "multi-sector WRITE aborted");
    out(0xCF, 0x10);
    CHECK(in(0xCC) == 0 && in(0xCD) == 0 && in(0xCF) == (ST_READY | ST_SEEKDONE), "RESTORE zeroes cylinder");

    /* ---- 512-byte sectors ---- */
    task(0, 1, 3, 2, 1);
    out(0xCF, 0x30);
    for (i = 0; i < 512; i++) out(0xC8, (uint8_t)(255 - (i & 0xFF)));
    CHECK(wait_ready() == (ST_READY | ST_SEEKDONE), "512-byte WRITE");
    frehd_tick_ms(5000);
    read_at("hard4-0", ((3L * 6 + 1) * 32 + 2) * 512 + 256, buf, 512);
    CHECK(buf[0] == 255 && buf[511] == 0, "512-byte sector offset");

    /* ---- write-protected image on drive 1 ---- */
    read_at("hard4-0", 0, hdr, 256);
    hdr[7] = 0x80;
    path(p, "hard4-1");
    f = fopen(p, "wb"); fwrite(hdr, 1, 256, f); fclose(f);
    frehd_card_mounted(1);
    CHECK(in(0xC0) == (0x40 | 0x02), "WP register shows drive 1 (%02X)", in(0xC0));
    task(1, 0, 0, 0, 0);
    out(0xCF, 0x30);
    for (i = 0; i < 256; i++) out(0xC8, 0);
    s = wait_ready();
    CHECK((s & ST_ERR) && (s & ST_WRERR), "write to protected drive refused (st %02X)", s);
    CHECK(file_size("hard4-1") == 256, "protected image untouched");

    /* read-only file attribute mounts protected */
    path(p, "hard4-2");
    hdr[7] = 0;
    f = fopen(p, "wb"); fwrite(hdr, 1, 256, f); fclose(f);
    SetFileAttributesA(p, FILE_ATTRIBUTE_READONLY);
    frehd_card_mounted(1);
    CHECK(in(0xC0) == (0x40 | 0x20 | 0x02), "read-only file mounts write-protected (%02X)", in(0xC0));

    /* ---- extension: file I/O ---- */
    {
        uint8_t o[16] = { FA_WRITE | FA_CREATE_ALWAYS, 'T', 'E', 'S', 'T', '.', 'T', 'X', 'T' };
        uint8_t data[10] = { 'H', 'E', 'L', 'L', 'O', ' ', 'T', 'R', 'S', '!' };
        s = xcmd(X_OPENFILE, o, 9);
        CHECK(s & ST_DRQ && !(s & ST_ERR), "OPENFILE for write");
        out(0xC4, X_WRITEFILE);
        wait_ready();
        out(0xC3, 10);
        for (i = 0; i < 10; i++) out(0xC2, data[i]);
        s = wait_ready();
        CHECK(s == (ST_READY | ST_SEEKDONE | ST_DRQ), "WRITEFILE 10 bytes (st %02X)", s);
        s = xcmd(X_CLOSEFILE, NULL, 0);
        CHECK(s == (ST_READY | ST_SEEKDONE) && file_size("TEST.TXT") == 10, "CLOSEFILE, file is 10 bytes");

        o[0] = FA_READ;
        s = xcmd(X_OPENFILE, o, 9);
        for (i = 0; i < 4; i++) buf[i] = in(0xC2);
        CHECK(in(0xC3) == 4 && buf[0] == 10 && !buf[1] && !buf[2] && !buf[3], "OPENFILE returns size 10");
        out(0xC3, 0);                                /* request 256 */
        s = xcmd(X_READFILE, NULL, 0);
        CHECK(s & ST_DRQ && in(0xC3) == 10, "READFILE got %d bytes", in(0xC3));
        for (i = 0; i < 10; i++) buf[i] = in(0xC2);
        CHECK(!memcmp(buf, data, 10), "READFILE data");
        s = xcmd(X_READFILE, NULL, 0);
        CHECK(s == (ST_READY | ST_SEEKDONE), "READFILE at EOF: no DRQ");
        s = xcmd(X_SEEKFILE, NULL, 0);
        for (i = 0; i < 4; i++) buf[i] = in(0xC2);
        CHECK(buf[0] == 10, "SEEKFILE tell = 10");
        { uint8_t pos[4] = { 6, 0, 0, 0 };
          xcmd(X_SEEKFILE, NULL, 0);
          out(0xC3, 4); for (i = 0; i < 4; i++) out(0xC2, pos[i]); wait_ready(); }
        out(0xC3, 4);
        xcmd(X_READFILE, NULL, 0);
        for (i = 0; i < 4; i++) buf[i] = in(0xC2);
        CHECK(!memcmp(buf, "TRS!", 4), "SEEKFILE then READFILE");
        xcmd(X_CLOSEFILE, NULL, 0);
        o[0] = FA_READ; memcpy(o + 1, "NOPE.TXT", 8);
        s = xcmd(X_OPENFILE, o, 9);
        CHECK((s & ST_ERR) && in(0xC5) == FR_NO_FILE, "OPENFILE missing file -> ERR, ERROR2=NO_FILE");
        out(0xC3, 0);
        s = xcmd(X_READFILE, NULL, 0);
        CHECK((s & ST_ERR) && in(0xC5) == FR_NO_FILE, "READFILE with nothing open");
    }

    /* ---- directory ---- */
    {
        uint8_t d[2] = { '/', 0 };
        int found = 0, n = 0;
        s = xcmd(X_OPENDIR, d, 1);
        CHECK(s & ST_DRQ, "OPENDIR /");
        for (;;) {
            s = xcmd(X_READDIR, NULL, 0);
            if (!(s & ST_DRQ)) break;
            CHECK(in(0xC3) == 22, "READDIR entry size 22");
            for (i = 0; i < 22; i++) buf[i] = in(0xC2);
            if (!strcmp((char *)buf + 9, "TEST.TXT") && buf[0] == 10) found = 1;
            n++;
        }
        CHECK(found && n == 5, "READDIR lists TEST.TXT (entries %d)", n);
    }

    /* ---- time, version, bootloader, image ---- */
    s = xcmd(X_GETTIME, NULL, 0);
    for (i = 0; i < 6; i++) buf[i] = in(0xC2);
    CHECK(!memcmp(buf, clock_t6, 6), "GETTIME");
    { uint8_t t[6] = { 1, 2, 3, 27, 4, 5 };
      xcmd(X_SETTIME, NULL, 0);
      for (i = 0; i < 6; i++) out(0xC2, t[i]);
      wait_ready();
      CHECK(!memcmp(clock_t6, t, 6), "SETTIME"); }
    xcmd(X_VERSION, NULL, 0);
    for (i = 0; i < 6; i++) buf[i] = in(0xC2);
    CHECK(buf[0] == FREHD_COMPAT_MAJOR && buf[1] == FREHD_COMPAT_MINOR && buf[2] == (6 ^ 0x5A), "VERSION");
    { uint8_t b[2] = { 0x15, 0x05 };
      xcmd(X_BOOTLOADER, NULL, 0); out(0xC2, b[0]); out(0xC2, b[1]); wait_ready();
      CHECK(!boot_called, "BOOTLOADER wrong key ignored");
      b[1] = 0x04;
      xcmd(X_BOOTLOADER, NULL, 0); out(0xC2, b[0]); out(0xC2, b[1]); wait_ready();
      CHECK(boot_called, "BOOTLOADER key accepted"); }
    /* ---- floppy images (IMAGE command) ---- */
    {
        uint8_t info[5], b[256];
        int e;
        make_dmk("TEST.DMK"); make_jv3("TEST.DSK"); make_jv1("TEST.JV1");
        e = img_open(0, "TEST.DMK", info);
        CHECK(e == 0 && in(0xC3) == 5 && info[0] == 1 && info[1] == 0 && info[2] == 0 && info[3] == 1 && info[4] == 1,
              "IMAGE open DMK (err %d, %d %d %d %d %d)", e, info[0], info[1], info[2], info[3], info[4]);
        e = img_read(0, 1, 0, b);
        CHECK(e == 0 && in(0xC3) == 0 && same(b, (uint8_t (*)(int, int, int, int))pat_dmk, 1, 0, 0), "DMK DD sector t1 s0");
        e = img_read(0, 0, 1, b);
        CHECK(e == 6 && same(b, (uint8_t (*)(int, int, int, int))pat_dmk, 0, 0, 1), "DMK F8 mark -> 6");
        e = img_read(0, 1, 2, b);
        CHECK(e == 0 && same(b, (uint8_t (*)(int, int, int, int))pat_dmk, 1, 0, 2), "DMK single-density (doubled) sector");
        e = img_read(0, 0, 3, b);
        CHECK(e == 6, "DMK FA mark -> 6");
        e = img_read(0, 1, 4 + 3, b);
        CHECK(e == 0 && same(b, (uint8_t (*)(int, int, int, int))pat_dmk, 1, 1, 3), "DMK side 1 via sector >= per-side count");
        e = img_read(0, 1, 9, b);
        CHECK(e == 5, "DMK missing sector -> 5");

        e = img_open(1, "TEST.DSK", info);
        CHECK(e == 0 && info[0] == 1 && info[1] == 0 && info[2] == 0 && info[4] == 2,
              "IMAGE open JV3 (err %d, %d %d %d %d)", e, info[0], info[1], info[2], info[4]);
        e = img_read(1, 1, 2, b);
        CHECK(e == 0 && same(b, (uint8_t (*)(int, int, int, int))pat_jv3, 1, 2, 0),
              "JV3 sector after a free slot and a 128-byte sector");
        e = img_read(1, 0, 2, b);
        CHECK(e == 6 && same(b, (uint8_t (*)(int, int, int, int))pat_jv3, 0, 2, 0), "JV3 DD F8 mark -> 6");
        e = img_read(1, 0, 3, b);
        CHECK(e == 0 && same(b, (uint8_t (*)(int, int, int, int))pat_jv3, 0, 0, 1), "JV3 side 1");
        e = img_read(1, 2, 0, b);
        CHECK(e == 5, "JV3 missing sector -> 5");

        e = img_read(0, 1, 0, b);                 /* switch back to unit 0 (file reopened) */
        CHECK(e == 0 && same(b, (uint8_t (*)(int, int, int, int))pat_dmk, 1, 0, 0), "unit switch reopens DMK");

        e = img_open(2, "TEST.JV1", info);
        CHECK(e == 0 && info[0] == 35 && info[1] == 1 && info[2] == 1 && info[4] == 3, "IMAGE open JV1");
        e = img_read(2, 5, 3, b);
        { int j, ok2 = 1; for (j = 0; j < 256; j++) if (b[j] != (uint8_t)(53 + j)) ok2 = 0;
          CHECK(e == 0 && ok2, "JV1 sector t5 s3"); }
        CHECK(img_read(2, 17, 0, b) == 6, "JV1 directory track -> 6");
        CHECK(img_read(2, 0, 10, b) == 5, "JV1 sector 10 -> 5");
        CHECK(img_open(3, "NOPE.DSK", info) == 24, "IMAGE open missing file -> 24");
        { uint8_t rq[4] = { 8, 1, 0, 0 }; xcmd(X_IMAGE, rq, 4); CHECK(in(0xC5) == 5, "IMAGE unit 8 -> 5"); }
        CHECK(img_read(4, 0, 0, b) == 8, "read on a never-opened unit -> 8");
        CHECK(in(0xCF) == (ST_READY | ST_SEEKDONE | ST_DRQ), "IMAGE leaves status READY/DRQ");
    }    task(0, 0, 0, 0, 0);
    xcmd(X_READ_HEADER, NULL, 0);
    CHECK(in(0xC3) == 0 && in(0xC2) == 0x56 && in(0xC2) == 0xCB, "READ_HEADER (size2 256 reads as 0)");

    /* ---- reset ---- */
    out(0xCF, 0x20);
    frehd_bus_reset();
    CHECK(in(0xCF) == (ST_READY | ST_SEEKDONE), "bus reset clears BUSY");
    CHECK(frehd_poll() == 0, "no stale action after reset");
    reset_in_action = 1;                         /* ECB RESET* arrives while core 0 runs GETTIME */
    out(0xC4, X_GETTIME);
    frehd_poll();
    CHECK(in(0xCF) == (ST_READY | ST_SEEKDONE), "result of an action cut short by reset is dropped (st %02X)", in(0xCF));

    frehd_card_mounted(0);
    CHECK(ffhost_open_count() == 0, "all files closed on unmount (%d open)", ffhost_open_count());
    path(p, "hard4-2");
    SetFileAttributesA(p, FILE_ATTRIBUTE_NORMAL);

    printf("%d checks, %d failures\nRESULT: %s\n", checks, fails, fails ? "FAIL" : "PASS");
    return fails != 0;
}
