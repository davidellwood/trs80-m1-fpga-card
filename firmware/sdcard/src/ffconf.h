/*---------------------------------------------------------------------------/
/  FatFs configuration for the FreHD-compatible SD card (FatFs R0.15).
/  CMake copies this over lib/fatfs/source/ffconf.h. If you use another FatFs
/  revision, set FFCONF_DEF to the FF_DEFINED value in its ff.h and compare
/  with that revision's own ffconf.h for new options.
/---------------------------------------------------------------------------*/
#define FFCONF_DEF 80286

/* function configuration */
#define FF_FS_READONLY   0
#define FF_FS_MINIMIZE   0      /* f_opendir/f_readdir/f_lseek needed */
#define FF_USE_FIND      0
#define FF_USE_MKFS      0
#define FF_USE_FASTSEEK  0
#define FF_USE_EXPAND    0
#define FF_USE_CHMOD     0
#define FF_USE_LABEL     0
#define FF_USE_FORWARD   0
#define FF_USE_STRFUNC   0
#define FF_PRINT_LLI     0
#define FF_PRINT_FLOAT   0
#define FF_STRF_ENCODE   3

/* locale and namespace */
#define FF_CODE_PAGE     437
#define FF_USE_LFN       1      /* long names on the card; READDIR reports the 8.3 alias */
#define FF_MAX_LFN       255
#define FF_LFN_UNICODE   0
#define FF_LFN_BUF       255
#define FF_SFN_BUF       12
#define FF_FS_RPATH      0

/* drive/volume */
#define FF_VOLUMES       1
#define FF_STR_VOLUME_ID 0
#define FF_VOLUME_STRS   "SD"
#define FF_MULTI_PARTITION 0
#define FF_MIN_SS        512
#define FF_MAX_SS        512
#define FF_LBA64         0
#define FF_MIN_GPT       0x10000000
#define FF_USE_TRIM      0

/* system */
#define FF_FS_TINY       0
#define FF_FS_EXFAT      0
#define FF_FS_NORTC      0      /* get_fattime() from the DS1307 (ds1307.c) */
#define FF_NORTC_MON     1
#define FF_NORTC_MDAY    1
#define FF_NORTC_YEAR    2026
#define FF_FS_NOFSINFO   0
#define FF_FS_LOCK       0
#define FF_FS_REENTRANT  0      /* FatFs is only used from core 0 */
#define FF_FS_TIMEOUT    1000
