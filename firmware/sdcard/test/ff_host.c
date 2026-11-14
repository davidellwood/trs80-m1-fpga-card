/* Host stand-in for FatFs (see ff.h). Directory listing uses Win32 FindFirstFile. */
#define _CRT_SECURE_NO_WARNINGS
#include <string.h>
#include <windows.h>
#include "ff.h"

static char root[MAX_PATH];
static int open_count;
static char dir_names[64][13];
static DWORD dir_sizes[64];
static int dir_n;

void ffhost_root(const char *dir) { strncpy(root, dir, sizeof root - 1); }
int ffhost_open_count(void) { return open_count; }

static void full(char *out, const char *path)
{
    while (*path == '/' || *path == '\\') path++;
    snprintf(out, MAX_PATH, "%s\\%s", root, path);
}

FRESULT f_open(FIL *fp, const char *path, BYTE mode)
{
    char p[MAX_PATH];
    DWORD attr;
    full(p, path);
    attr = GetFileAttributesA(p);
    fp->fp = NULL;
    fp->pos = 0;
    fp->writable = (mode & FA_WRITE) != 0;
    if (attr == INVALID_FILE_ATTRIBUTES) {
        if (!(mode & (FA_CREATE_NEW | FA_CREATE_ALWAYS | FA_OPEN_ALWAYS))) return FR_NO_FILE;
        fp->fp = fopen(p, "w+b");
    } else {
        if (mode & FA_CREATE_NEW) return FR_EXIST;
        if ((mode & FA_WRITE) && (attr & FILE_ATTRIBUTE_READONLY)) return FR_DENIED;
        fp->fp = fopen(p, (mode & FA_CREATE_ALWAYS) ? "w+b" : (mode & FA_WRITE) ? "r+b" : "rb");
    }
    if (!fp->fp) return FR_DENIED;
    open_count++;
    return FR_OK;
}

FRESULT f_close(FIL *fp)
{
    if (!fp->fp) return FR_INVALID_OBJECT;
    fclose(fp->fp);
    fp->fp = NULL;
    open_count--;
    return FR_OK;
}

FRESULT f_read(FIL *fp, void *buff, UINT btr, UINT *br)
{
    fseek(fp->fp, (long)fp->pos, SEEK_SET);
    *br = (UINT)fread(buff, 1, btr, fp->fp);
    fp->pos += *br;
    return FR_OK;
}

FRESULT f_write(FIL *fp, const void *buff, UINT btw, UINT *bw)
{
    if (!fp->writable) return FR_DENIED;
    fseek(fp->fp, (long)fp->pos, SEEK_SET);
    *bw = (UINT)fwrite(buff, 1, btw, fp->fp);
    fp->pos += *bw;
    return FR_OK;
}

FRESULT f_lseek(FIL *fp, FSIZE_t ofs) { fp->pos = ofs; return FR_OK; }
FRESULT f_sync(FIL *fp) { fflush(fp->fp); return FR_OK; }

FSIZE_t f_size(FIL *fp)
{
    long cur = ftell(fp->fp), end;
    fseek(fp->fp, 0, SEEK_END);
    end = ftell(fp->fp);
    fseek(fp->fp, cur, SEEK_SET);
    return (FSIZE_t)end;
}

FRESULT f_opendir(DIR *dp, const char *path)
{
    char p[MAX_PATH];
    WIN32_FIND_DATAA fd;
    HANDLE h;
    full(p, path);
    strcat(p, "\\*");
    dir_n = 0;
    h = FindFirstFileA(p, &fd);
    if (h == INVALID_HANDLE_VALUE) return FR_NO_PATH;
    do {
        if (fd.cFileName[0] == '.' || strlen(fd.cFileName) > 12 || dir_n == 64) continue;
        strcpy(dir_names[dir_n], fd.cFileName);
        dir_sizes[dir_n++] = fd.nFileSizeLow;
    } while (FindNextFileA(h, &fd));
    FindClose(h);
    dp->idx = 0;
    return FR_OK;
}

FRESULT f_closedir(DIR *dp) { (void)dp; return FR_OK; }

FRESULT f_readdir(DIR *dp, FILINFO *fno)
{
    memset(fno, 0, sizeof *fno);
    if (dp->idx < dir_n) {
        strcpy(fno->fname, dir_names[dp->idx]);
        fno->fsize = dir_sizes[dp->idx];
        fno->fattrib = 0x20;
        dp->idx++;
    }
    return FR_OK;
}
