/* Pico pin use on the ECB SD card (hardware/card-sd). */
#ifndef BOARD_H
#define BOARD_H

#define PIN_PD0      0    /* GP0-GP7: data PD0-PD7, via 2N7000 shifters to XD (U1 245 to ECB D0-D7) */
#define PIN_PA0      8    /* GP8-GP11: ECB A0-A3 via U3 (CD74HC4050) */
#define PIN_SELRD    12   /* GAL: IN from C0-CF in progress (active high) */
#define PIN_SELWR    13   /* GAL: OUT to C0-CF in progress (active high) */
#define PIN_ACK      14   /* to GAL: high releases WAIT* (10k pull-up on the card) */
#define PIN_RESET    15   /* ECB RESET* via U4 (active low) */

#define SD_SPI       spi0
#define PIN_SD_MISO  16
#define PIN_SD_CS    17
#define PIN_SD_SCK   18
#define PIN_SD_MOSI  19
#define PIN_SD_CD    20   /* card detect from the module, 10k pull-up; see USE_CARD_DETECT */
#define PIN_LED      21   /* ACT LED, active high */

#define RTC_I2C      i2c1
#define PIN_SDA      26
#define PIN_SCL      27

/* Card-detect switch: 0 = ignore it and probe the card instead (works with any module).
   Set to 1 and CD_INSERTED_LEVEL to the module's level with a card fitted to use it. */
#define USE_CARD_DETECT   0
#define CD_INSERTED_LEVEL 1

#define MASK_PD   (0xFFu << PIN_PD0)
#define MASK_SEL  ((1u << PIN_SELRD) | (1u << PIN_SELWR))

#endif
