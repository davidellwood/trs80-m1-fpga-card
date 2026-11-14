/* diskio.c - FatFs (R0.15) low-level glue for the SPI SD driver. */
#include "ff.h"
#include "diskio.h"
#include "sd_spi.h"

static DSTATUS stat = STA_NOINIT;

DSTATUS disk_status(BYTE pdrv)
{
    return pdrv ? STA_NOINIT : stat;
}

DSTATUS disk_initialize(BYTE pdrv)
{
    if (pdrv) return STA_NOINIT;
    stat = sd_init() == 0 ? 0 : STA_NOINIT;
    return stat;
}

DRESULT disk_read(BYTE pdrv, BYTE *buff, LBA_t sector, UINT count)
{
    if (pdrv || (stat & STA_NOINIT)) return RES_NOTRDY;
    return sd_read(buff, (uint32_t)sector, count) ? RES_ERROR : RES_OK;
}

DRESULT disk_write(BYTE pdrv, const BYTE *buff, LBA_t sector, UINT count)
{
    if (pdrv || (stat & STA_NOINIT)) return RES_NOTRDY;
    return sd_write(buff, (uint32_t)sector, count) ? RES_ERROR : RES_OK;
}

DRESULT disk_ioctl(BYTE pdrv, BYTE cmd, void *buff)
{
    if (pdrv || (stat & STA_NOINIT)) return RES_NOTRDY;
    switch (cmd) {
    case CTRL_SYNC:        return RES_OK;      /* writes complete before sd_write returns */
    case GET_SECTOR_COUNT: *(LBA_t *)buff = sd_sectors(); return RES_OK;
    case GET_SECTOR_SIZE:  *(WORD *)buff = 512; return RES_OK;
    case GET_BLOCK_SIZE:   *(DWORD *)buff = 1; return RES_OK;
    default:               return RES_PARERR;
    }
}

void disk_force_reinit(void) { stat = STA_NOINIT; }
