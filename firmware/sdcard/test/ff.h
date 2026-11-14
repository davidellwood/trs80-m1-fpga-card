/* Host test stand-in for FatFs: the subset frehd.c uses, backed by stdio in a directory. */
#ifndef FF_HOST_H
#define FF_HOST_H
#include <stdio.h>
#include <stdint.h>

typedef unsigned int UINT;
typedef unsigned char BYTE;
typedef uint16_t WORD;
#ifdef _WIN32
typedef unsigned long DWORD;    /* same as <windows.h> */
#else
typedef uint32_t DWORD;
#endif
typedef DWORD FSIZE_t;

typedef enum {
    FR_OK = 0, FR_DISK_ERR, FR_INT_ERR, FR_NOT_READY, FR_NO_FILE, FR_NO_PATH, FR_INVALID_NAME, FR_DENIED,
    FR_EXIST, FR_INVALID_OBJECT, FR_WRITE_PROTECTED, FR_INVALID_DRIVE, FR_NOT_ENABLED, FR_NO_FILESYSTEM,
    FR_MKFS_ABORTED, FR_TIMEOUT, FR_LOCKED, FR_NOT_ENOUGH_CORE, FR_TOO_MANY_OPEN_FILES, FR_INVALID_PARAMETER
} FRESULT;

#define FA_READ          0x01
#define FA_WRITE         0x02
#define FA_OPEN_EXISTING 0x00
#define FA_CREATE_NEW    0x04
#define FA_CREATE_ALWAYS 0x08
#define FA_OPEN_ALWAYS   0x10

typedef struct { FILE *fp; DWORD pos; int writable; } FIL;
typedef struct { int idx; } DIR;
typedef struct { FSIZE_t fsize; WORD fdate, ftime; BYTE fattrib; char altname[13]; char fname[13]; } FILINFO;
typedef DWORD LBA_t;
typedef struct { int dummy; } FATFS;
FRESULT f_mount(FATFS *fs, const char *path, BYTE opt);

FRESULT f_open(FIL *fp, const char *path, BYTE mode);
FRESULT f_close(FIL *fp);
FRESULT f_read(FIL *fp, void *buff, UINT btr, UINT *br);
FRESULT f_write(FIL *fp, const void *buff, UINT btw, UINT *bw);
FRESULT f_lseek(FIL *fp, FSIZE_t ofs);
FRESULT f_sync(FIL *fp);
FRESULT f_opendir(DIR *dp, const char *path);
FRESULT f_closedir(DIR *dp);
FRESULT f_readdir(DIR *dp, FILINFO *fno);
FSIZE_t f_size(FIL *fp);
#define f_tell(fp) ((fp)->pos)

void ffhost_root(const char *dir);     /* directory standing in for the SD card */
int ffhost_open_count(void);
#endif
