/* Declarations-only stand-ins for the Pico SDK, used to syntax-check the firmware with MSVC. */
#ifndef PICO_STUBS_H
#define PICO_STUBS_H
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
typedef uint64_t absolute_time_t;
typedef struct spi_inst spi_inst_t;
typedef struct i2c_inst i2c_inst_t;
extern spi_inst_t *spi0;
extern i2c_inst_t *i2c1;
typedef struct { volatile uint32_t gpio_in, gpio_out, gpio_set, gpio_clr, gpio_oe_set, gpio_oe_clr; } sio_hw_t;
extern sio_hw_t *sio_hw;
enum { GPIO_FUNC_SPI = 1, GPIO_FUNC_I2C = 3, GPIO_OUT = 1 };
#define __not_in_flash_func(f) f
#define tight_loop_contents() ((void)0)
#define __dmb() ((void)0)
void gpio_init(unsigned); void gpio_set_dir(unsigned, int); void gpio_put(unsigned, int); int gpio_get(unsigned);
void gpio_pull_up(unsigned); void gpio_disable_pulls(unsigned); void gpio_set_function(unsigned, int);
void busy_wait_at_least_cycles(uint32_t);
unsigned spi_init(spi_inst_t *, unsigned); unsigned spi_set_baudrate(spi_inst_t *, unsigned);
int spi_write_read_blocking(spi_inst_t *, const uint8_t *, uint8_t *, size_t);
int spi_read_blocking(spi_inst_t *, uint8_t, uint8_t *, size_t);
int spi_write_blocking(spi_inst_t *, const uint8_t *, size_t);
unsigned i2c_init(i2c_inst_t *, unsigned);
int i2c_write_timeout_us(i2c_inst_t *, uint8_t, const uint8_t *, size_t, bool, unsigned);
int i2c_read_timeout_us(i2c_inst_t *, uint8_t, uint8_t *, size_t, bool, unsigned);
absolute_time_t make_timeout_time_ms(uint32_t); bool time_reached(absolute_time_t);
absolute_time_t get_absolute_time(void); uint32_t to_ms_since_boot(absolute_time_t); uint64_t time_us_64(void);
void multicore_launch_core1(void (*)(void)); bool stdio_init_all(void); void reset_usb_boot(uint32_t, uint32_t);
#endif
