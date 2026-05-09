#ADC DAC Test
import smbus2, time

bus = smbus2.SMBus(1)
ADC_ADDR = 0x49

# 0x60 (DAC4) with 0x48(ADC) In4- TESTED!


def dac_write(code):
    # code is 0-4095
    high = (code >> 4) & 0xFF
    low  = (code & 0x0F) << 4
    bus.write_i2c_block_data(0x60, 0x40, [high, low])

def adc_read():
    bus.write_i2c_block_data(ADC_ADDR, 0x01, [0xE3, 0x83])
    for _ in range(20):
        time.sleep(0.01)
        cfg = bus.read_i2c_block_data(ADC_ADDR, 0x01, 2)
    d = bus.read_i2c_block_data(ADC_ADDR, 0x00, 2)
    raw = (d[0] << 8 | d[1])
    if raw > 32767: raw -= 65536
    return raw / 32767 * 4.096

print(f"{'DAC Code':>10} | {'DAC Voltage (V)':>15} | {'ADC Voltage (V)':>15}")
print("-" * 50)

for code in [0, 1024, 2048, 3072, 4095]:
    dac_write(code)
    time.sleep(2)
    adc_v = adc_read()
    dac_v = code / 4095 * 3.3
    print(f"{code:>10} | {dac_v:>15.3f} | {adc_v:>15.3f}")