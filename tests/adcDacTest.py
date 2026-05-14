#ADC DAC Test

# OUT 4, (MCP)0x60 (DAC4) -TESTED
# OUT3, (MCP) 0x61 (DAC3) - TESTED
# OUT 1, (DAC 5571_write), 0x4D DAC Address, TESTED
# OUT 2, (DAC 5571_write), 0x4C DAC Address, TESTED
# IN2, ADC_ADDR 0x49, config bit 0xD3 - TESTED
# IN4, ADC_ADDR 0x49, config bit 0xE3 - TESTED
# IN1, ADC_ADDR 0x49, config byte 0xC3 - TESTED
# IN3, ADC_ADDR 0x49, config byte 0xF3 - TESTED

import smbus2, time

bus = smbus2.SMBus(1)
ADC_ADDR = 0x49 
out_4 = 0x60
out_3 = 0x61
out_2 = 0x4C
out_1 = 0x4D

in_1 = 0xC3
in_2 = 0xD3
in_3 = 0xF3
in_4 = 0xE3


def dac_write(code):
    # MCP code is 0-4095
    high = (code >> 4) & 0xFF
    low  = (code & 0x0F) << 4
    bus.write_i2c_block_data(out_4, 0x40, [high, low])  # Out4

def dac5571_write(addr, code):
    # DAC5571 - code is 0-255
    code = max(0, min(255, code))
    byte1 = (code >> 4) & 0x0F
    byte2 = (code & 0x0F) << 4
    bus.write_i2c_block_data(addr, byte1, [byte2])

def adc_read(config=0xC3):
    bus.write_i2c_block_data(ADC_ADDR, 0x01, [config, 0x83])
    for _ in range(20):
        time.sleep(0.01)
        cfg = bus.read_i2c_block_data(ADC_ADDR, 0x01, 2)
    d = bus.read_i2c_block_data(ADC_ADDR, 0x00, 2)
    raw = (d[0] << 8 | d[1])
    if raw > 32767: raw -= 65536
    return raw / 32767 * 4.096

#MCP4725 test
print(f"{'DAC Code':>10} | {'DAC Voltage (V)':>15} | {'ADC Voltage (V)':>15}")
print("-" * 50)
for code in [0, 1024, 2048, 3072, 4095]:
    dac_write(code)
    time.sleep(2)
    adc_v = adc_read(in_1)  
    dac_v = code / 4095 * 3.3
    print(f"{code:>10} | {dac_v:>15.3f} | {adc_v:>15.3f}")

#DAC5571 test
print(f"{'DAC Code':>10} | {'DAC Voltage (V)':>15} | {'ADC Voltage (V)':>15}")
print("-" * 50)
for code in [0, 64, 128, 192, 255]:
    dac5571_write(out_1, code) 
    time.sleep(2)
    adc_v = adc_read(in_2)  
    dac_v = code / 255 * 3.3
    print(f"{code:>10} | {dac_v:>15.3f} | {adc_v:>15.3f}")