/*
 * image.c - read-only DMK / JV3 / JV1 floppy images for the FreHD IMAGE command.
 * See image.h for the Z80 protocol. Behaviour follows FreHD's (sectors are always
 * returned as 256 bytes; sector numbers at or above the per-side count select side 1).
 *
 * DMK: 16-byte header (byte 1 tracks, bytes 2-3 track length, byte 4 bit 4 single-sided,
 *      bit 6 single-density). Each track starts with 64 little-endian IDAM pointers
 *      (bit 15 = double-density sector, bits 13-0 = offset of the FE byte in the track).
 *      Single-density data in a mixed-density image is stored with every byte doubled.
 * JV3: 2901 three-byte entries (track, sector, flags) in an 8704-byte header, data after
 *      it in entry order; track FFh = free entry (its data slot still counts).
 * JV1: no header; 35 tracks x 10 sectors x 256 bytes, single-sided, single-density.
 */
#include <string.h>
#include "ff.h"
#include "image.h"

#define JV3_ENTRIES   2901
#define JV3_HDR       8704
#define DMK_HDR       16
#define DMK_IDAMS     64

typedef struct {
    char name[64];
    uint8_t type;
    uint8_t tracks;          /* value reported as "highest track" */
    uint8_t nsec;            /* sectors per side */
    uint8_t sside, sdens;    /* 1 = single-sided / single-density */
    uint16_t tlen;           /* DMK track length */
    uint8_t hdr_ss, hdr_sd;  /* DMK header flags */
} unit_t;

static unit_t unit[IM_UNITS];
static FIL file;
static int cur = -1;                         /* unit whose file is open */
static uint8_t jv3[JV3_ENTRIES * 3];         /* JV3 table of the open unit */
static uint8_t raw[(7 + 43 + 1 + 256) * 2];  /* DMK ID + gap + DAM + data window */

static int read_at(uint32_t off, void *p, unsigned n)
{
    UINT got;
    if (f_lseek(&file, off) != FR_OK || f_read(&file, p, n, &got) != FR_OK)
        return -1;
    return (int)got;
}

static void close_cur(void)
{
    if (cur >= 0) f_close(&file);
    cur = -1;
}

void image_reset(void)
{
    close_cur();
    memset(unit, 0, sizeof unit);
}

/* ---------------------------------------------------------------- DMK */
static uint32_t dmk_track_off(const unit_t *u, unsigned idx)
{
    return DMK_HDR + (uint32_t)idx * u->tlen;
}

/* IDAM table of track slot idx; returns entries before the first zero (max 64) */
static int dmk_idams(const unit_t *u, unsigned idx, uint16_t *ids)
{
    uint8_t t[DMK_IDAMS * 2];
    int i;
    if (read_at(dmk_track_off(u, idx), t, sizeof t) != (int)sizeof t) return 0;
    for (i = 0; i < DMK_IDAMS; i++) {
        ids[i] = (uint16_t)(t[2 * i] | (t[2 * i + 1] << 8));
        if (!ids[i]) break;
    }
    return i;
}

static int dmk_open(unit_t *u, const uint8_t *h)
{
    uint16_t ids[DMK_IDAMS];
    unsigned idx;
    int n, i;
    u->tracks = (uint8_t)(h[1] ? h[1] - 1 : 0);
    u->tlen = (uint16_t)(h[2] | (h[3] << 8));
    u->hdr_ss = (h[4] & 0x10) != 0;
    u->hdr_sd = (h[4] & 0x40) != 0;
    u->sside = 1;
    u->sdens = 1;
    idx = u->hdr_ss ? 0 : 1;                  /* track 0 side 1, else side 0 */
    n = dmk_idams(u, idx, ids);
    if (!n && idx) n = dmk_idams(u, idx = 0, ids);
    if (n > 32) n = 32;
    u->nsec = (uint8_t)n;
    for (i = 0; i < n; i++) {
        unsigned stride = (u->hdr_sd || (ids[i] & 0x8000)) ? 1 : 2;
        uint8_t id[8];
        if (ids[i] & 0x8000) u->sdens = 0;
        if (read_at(dmk_track_off(u, idx) + (ids[i] & 0x3FFF), id, 4 * stride) == (int)(4 * stride) &&
            (id[2 * stride] & 1))
            u->sside = 0;
    }
    if (u->hdr_ss) u->sside = 1;
    if (u->hdr_sd) u->sdens = 1;
    return 0;
}

static uint8_t dmk_read(const unit_t *u, unsigned track, unsigned side, unsigned sector, uint8_t *out)
{
    uint16_t ids[DMK_IDAMS];
    unsigned idx, i, k;
    int n;
    if (u->hdr_ss && side) return IM_DATA_NOT_FOUND;
    idx = u->hdr_ss ? track : track * 2 + side;
    n = dmk_idams(u, idx, ids);
    for (i = 0; i < (unsigned)n; i++) {
        unsigned dd = (ids[i] & 0x8000) != 0;
        unsigned stride = (u->hdr_sd || dd) ? 1 : 2;
        unsigned limit = dd ? 43 : 30, want = (7 + limit + 1 + 256) * stride;
        int got = read_at(dmk_track_off(u, idx) + (ids[i] & 0x3FFF), raw, want);
        if (got < (int)(7 * stride)) continue;
        if (raw[0] != 0xFE || raw[stride] != track || (unsigned)(raw[2 * stride] & 1) != side || raw[3 * stride] != sector)
            continue;
        for (k = 7; k < 7 + limit; k++) {     /* data address mark */
            uint8_t m = raw[k * stride];
            if (m >= 0xF8 && m <= 0xFB) {
                unsigned j;
                if ((int)((k + 1 + 256) * stride) > got) return IM_DATA_NOT_FOUND;
                for (j = 0; j < 256; j++) out[j] = raw[(k + 1 + j) * stride];
                return (m == 0xF8 || m == 0xFA) ? IM_SYSTEM_REC : IM_OK;
            }
        }
        return IM_DATA_NOT_FOUND;
    }
    return IM_DATA_NOT_FOUND;
}

/* ---------------------------------------------------------------- JV3 */
static unsigned jv3_size(uint8_t trk, uint8_t flags)
{
    static const uint16_t used[4] = { 256, 128, 1024, 512 }, freed[4] = { 512, 1024, 128, 256 };
    return trk == 0xFF ? freed[flags & 3] : used[flags & 3];
}

static int jv3_load(void)
{
    return read_at(0, jv3, sizeof jv3) == (int)sizeof jv3 ? 0 : -1;
}

static int jv3_open(unit_t *u)
{
    unsigned i;
    if (jv3_load()) return -1;
    u->tracks = 0; u->nsec = 0; u->sside = 1; u->sdens = 1;
    for (i = 0; i < JV3_ENTRIES; i++) {
        uint8_t t = jv3[3 * i], s = jv3[3 * i + 1], f = jv3[3 * i + 2];
        if (t == 0xFF) continue;
        if (t > u->tracks) u->tracks = t;
        if ((unsigned)s + 1 > u->nsec) u->nsec = (uint8_t)(s + 1);
        if (f & 0x10) u->sside = 0;
        if (f & 0x80) u->sdens = 0;
    }
    return 0;
}

static uint8_t jv3_read(unsigned track, unsigned side, unsigned sector, uint8_t *out)
{
    uint32_t off = JV3_HDR;
    unsigned i;
    for (i = 0; i < JV3_ENTRIES; i++) {
        uint8_t t = jv3[3 * i], s = jv3[3 * i + 1], f = jv3[3 * i + 2];
        if (t == track && s == sector && (unsigned)((f & 0x10) != 0) == side) {
            uint8_t dam = f & 0x60;
            if (read_at(off, out, 256) != 256) return IM_DATA_NOT_FOUND;
            if (f & 0x80) return dam == 0x20 ? IM_SYSTEM_REC : IM_OK;         /* DD: F8 */
            return (dam == 0x20 || dam == 0x60) ? IM_SYSTEM_REC : IM_OK;      /* SD: FA, F8 */
        }
        off += jv3_size(t, f);
    }
    return IM_DATA_NOT_FOUND;
}

/* ---------------------------------------------------------------- JV1 */
static uint8_t jv1_read(unsigned track, unsigned sector, uint8_t *out)
{
    if (sector >= 10) return IM_DATA_NOT_FOUND;
    if (read_at(((uint32_t)track * 10 + sector) * 256, out, 256) != 256) return IM_NOT_FOUND;
    return track == 17 ? IM_SYSTEM_REC : IM_OK;   /* TRSDOS directory track */
}

/* ---------------------------------------------------------------- common */
static int open_unit(int n)
{
    if (cur == n) return 0;
    close_cur();
    if (!unit[n].name[0] || f_open(&file, unit[n].name, FA_READ) != FR_OK) return -1;
    cur = n;
    if (unit[n].type == IM_JV3 && jv3_load()) { close_cur(); return -1; }
    return 0;
}

static uint8_t detect(unit_t *u)
{
    uint8_t h[DMK_HDR], w[8];
    int n = read_at(0, h, sizeof h);
    if (n < (int)sizeof h) return IM_NONE;
    if (h[12] == 0x78 && h[13] == 0x56 && h[14] == 0x34 && h[15] == 0x12)
        return IM_NONE;                                   /* DMK "real disk" pointer file */
    if ((h[0] == 0x00 || h[0] == 0xFF) && !h[12] && !h[13] && !h[14] && !h[15]) {
        uint16_t tl = (uint16_t)(h[2] | (h[3] << 8));
        if (tl >= 16 && tl <= 0x4000) { dmk_open(u, h); return IM_DMK; }
    }
    if (h[0] == 0x00 && h[1] == 0xFE) goto jv1;
    if (read_at(JV3_ENTRIES * 3, w, sizeof w) == (int)sizeof w && (w[0] == 0x00 || w[0] == 0xFF)) {
        if (jv3_open(u) == 0) return IM_JV3;
    }
jv1:
    u->tracks = 35; u->nsec = 10; u->sside = 1; u->sdens = 1;
    return IM_JV1;
}

uint8_t image_cmd(uint8_t *buf, unsigned len, uint16_t *out_len)
{
    unsigned n, track, side, sector;
    unit_t *u;
    if (len < 2 || buf[0] >= IM_UNITS) return IM_DATA_NOT_FOUND;
    n = buf[0];
    u = &unit[n];
    if (buf[1] == 0) {                                    /* open */
        unsigned i;
        char name[sizeof u->name];
        for (i = 0; i + 2 < len && i + 1 < sizeof name && buf[2 + i]; i++) name[i] = (char)buf[2 + i];
        name[i] = 0;
        if (name[0]) memcpy(u->name, name, sizeof name);
        close_cur();
        u->type = IM_NONE;
        if (!u->name[0] || f_open(&file, u->name, FA_READ) != FR_OK) return IM_NOT_FOUND;
        cur = (int)n;
        u->type = detect(u);
        if (u->type == IM_NONE) { close_cur(); return IM_NOT_AVAIL; }
        buf[0] = u->tracks; buf[1] = u->sside; buf[2] = u->sdens; buf[3] = 1; buf[4] = u->type;
        *out_len = 5;
        return IM_OK;
    }
    if (buf[1] == 1) {                                    /* read sector */
        uint8_t r;
        if (len < 4) return IM_DATA_NOT_FOUND;
        if (u->type == IM_NONE) return IM_NOT_AVAIL;
        if (open_unit((int)n)) return IM_NOT_FOUND;
        track = buf[2];
        sector = buf[3];
        side = 0;
        if (u->type != IM_JV1 && u->nsec && sector >= u->nsec) { sector -= u->nsec; side = 1; }
        switch (u->type) {
        case IM_DMK: r = dmk_read(u, track, side, sector, buf); break;
        case IM_JV3: r = jv3_read(track, side, sector, buf); break;
        default:     r = jv1_read(track, sector, buf); break;
        }
        if (r == IM_OK || r == IM_SYSTEM_REC) *out_len = 256;
        return r;
    }
    return IM_OK;
}
