/* FatFs R0.15 diskio.h declarations (stub) */
#include "ff.h"
typedef BYTE DSTATUS; typedef enum { RES_OK = 0, RES_ERROR, RES_WRPRT, RES_NOTRDY, RES_PARERR } DRESULT;
#define STA_NOINIT 0x01
#define CTRL_SYNC 0
#define GET_SECTOR_COUNT 1
#define GET_SECTOR_SIZE 2
#define GET_BLOCK_SIZE 3
