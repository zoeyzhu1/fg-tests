# ADC/DAC Function Generator & Oscilloscope

A Flask-based server and web UI for driving DAC outputs and reading ADC inputs on a Raspberry Pi over I2C. Provides a function generator (sine/square/sawtooth/triangle) and a live oscilloscope, plus DAC/ADC sweep and pairing tests.

## Hardware

| Channel | Type | I2C Address |
|---|---|---|
| OUT1 | DAC5571 | 0x4D |
| OUT2 | DAC5571 | 0x4C |
| OUT3 | MCP4725 | 0x61 |
| OUT4 | MCP4725 | 0x60 |
| IN1 | ADS1115 | 0x49 |
| IN2 | ADS1115 | 0x49 |
| IN3 | ADS1115 | 0x49 |
| IN4 | ADS1115 | 0x49 |

ADC reference voltage: ±4.096 V, DAC reference: 3.3 V.

## Files

- `adc_dac_server.py` — Flask server exposing server endpoints for DAC writes, ADC reads, waveform generation, and sweep tests
- `adc_dac_ui.html` — Single-page UI: oscilloscope display, function generator controls, step sweep, and operation log
- `tests/` — Standalone ADC/DAC functionality test scripts

## Setup

```bash
pip install flask flask-cors smbus2
python adc_dac_server.py
```

Then open `http://<raspberry-pi-ip>:5000` in a browser.

## UI Features

- **Oscilloscope**: live-polling chart of any ADC input, with min/max/last readout and configurable sample interval/buffer size
- **Function generator**: sine, square, sawtooth, and triangle waveforms with adjustable frequency, amplitude, and offset
- **Step sweep**: writes 0%, 25%, 50%, 75%, 100% of full-scale DAC code and reads back the corresponding ADC voltage
- **Single shot**: writes mid-scale DAC code and reads ADC for a quick DAC↔ADC pairing check
- **Log**: timestamped record of generator runs, DAC/ADC pairs, and errors
