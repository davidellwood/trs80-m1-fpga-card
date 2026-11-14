#ifndef SD_SPI_H
#define SD_SPI_H
#include <stdint.h>

int sd_init(void);                                            /* 0 = card ready */
int sd_read(uint8_t *buf, uint32_t lba, uint32_t count);      /* 0 = ok */
int sd_write(const uint8_t *buf, uint32_t lba, uint32_t count);
int sd_check(void);                                           /* 0 = card still answering */
uint32_t sd_sectors(void);                                    /* capacity in 512-byte blocks (0 = unknown) */

#endif
