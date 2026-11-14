/*
 * image.h - read-only floppy images (DMK, JV3, JV1) for the FreHD IMAGE command (0Dh).
 *
 * Z80 side: SIZE2 = n, OUT C4h,0Dh, wait, then n bytes to DATA2:
 *   byte 0  unit 0-7
 *   byte 1  0 = open, 1 = read sector
 *   open:   bytes 2.. filename, NUL-terminated (empty = reopen the unit's last file)
 *           -> SIZE2 5: highest track, single-sided (1/0), single-density (1/0),
 *              write-protected (always 1), type (1 DMK, 2 JV3, 3 JV1)
 *   read:   byte 2 track, byte 3 sector (sector >= sectors-per-side selects side 1)
 *           -> SIZE2 256 (reads as 0): the 256 data bytes
 * The result code goes to ERROR2; the status register shows READY/SEEKDONE/DRQ.
 */
#ifndef IMAGE_H
#define IMAGE_H
#include <stdint.h>

enum { IM_NONE = 0, IM_DMK = 1, IM_JV3 = 2, IM_JV1 = 3 };

/* result codes (ERROR2), as FreHD */
#define IM_OK            0
#define IM_DATA_NOT_FOUND 5
#define IM_SYSTEM_REC    6      /* read OK, but a system/deleted data address mark */
#define IM_NOT_AVAIL     8      /* not a recognised image */
#define IM_NOT_FOUND     24     /* file could not be opened */

#define IM_UNITS 8

/* buf holds the request (len bytes) and receives the reply; returns the result code,
   *out_len = reply length (5 for open, 256 for read, unchanged on error) */
uint8_t image_cmd(uint8_t *buf, unsigned len, uint16_t *out_len);
void image_reset(void);          /* card removed or remounted: close everything */

#endif
