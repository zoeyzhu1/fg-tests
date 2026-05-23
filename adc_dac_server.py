#!/usr/bin/env python3
"""
ADC/DAC Test Server
Flask backend exposing REST endpoints for DAC write and ADC read operations.
Run with: python adc_dac_server.py
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import smbus2
import time

app = Flask(__name__)
CORS(app)

# Address constants
ADC_ADDR = 0x49

CHANNELS = {
    "OUT1": {"type": "dac5571", "addr": 0x4D, "adc_cfg": 0xD3, "max_code": 255},
    "OUT2": {"type": "dac5571", "addr": 0x4C, "adc_cfg": 0xD3, "max_code": 255},
    "OUT3": {"type": "mcp4725",  "addr": 0x61, "adc_cfg": 0xF3, "max_code": 4095},
    "OUT4": {"type": "mcp4725",  "addr": 0x60, "adc_cfg": 0xC3, "max_code": 4095},
}

ADC_CONFIGS = {
    "IN1": 0xC3,
    "IN2": 0xD3,
    "IN3": 0xF3,
    "IN4": 0xE3,
}

_bus = None

def get_bus():
    global _bus
    if _bus is None:
        _bus = smbus2.SMBus(1)
    return _bus

# DAC
def mcp4725_write(addr, code):
    code = max(0, min(4095, int(code)))
    high = (code >> 4) & 0xFF
    low  = (code & 0x0F) << 4
    get_bus().write_i2c_block_data(addr, 0x40, [high, low])

def dac5571_write(addr, code):
    code = max(0, min(255, int(code)))
    byte1 = (code >> 4) & 0x0F
    byte2 = (code & 0x0F) << 4
    get_bus().write_i2c_block_data(addr, byte1, [byte2])

def adc_read(config=0xC3):
    bus = get_bus()
    bus.write_i2c_block_data(ADC_ADDR, 0x01, [config, 0x83])
    for _ in range(20):
        time.sleep(0.01)
        bus.read_i2c_block_data(ADC_ADDR, 0x01, 2)   # poll until ready
    d = bus.read_i2c_block_data(ADC_ADDR, 0x00, 2)
    raw = (d[0] << 8) | d[1]
    if raw > 32767:
        raw -= 65536
    return round(raw / 32767 * 4.096, 4)

#Routes 

@app.route("/api/channels", methods=["GET"])
def list_channels():
    """Return available channel metadata."""
    return jsonify({
        "channels": [
            {
                "id": ch,
                "type": info["type"],
                "max_code": info["max_code"],
                "addr": hex(info["addr"]),
            }
            for ch, info in CHANNELS.items()
        ]
    })


@app.route("/api/write", methods=["POST"])
def write_dac():
    body = request.get_json(force=True)
    ch_id = body.get("channel", "").upper()
    code  = body.get("code")

    if ch_id not in CHANNELS:
        return jsonify({"error": f"Unknown channel '{ch_id}'"}), 400
    if code is None:
        return jsonify({"error": "Missing 'code' field"}), 400

    ch = CHANNELS[ch_id]
    try:
        if ch["type"] == "mcp4725":
            mcp4725_write(ch["addr"], code)
        else:
            dac5571_write(ch["addr"], code)

        max_code = ch["max_code"]
        dac_voltage = round(int(code) / max_code * 3.3, 4)
        return jsonify({
            "ok": True,
            "channel": ch_id,
            "code": int(code),
            "dac_voltage": dac_voltage,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/read", methods=["POST"])
def read_adc():
    """
    Read an ADC channel.
    """
    body = request.get_json(force=True)
    adc_id = body.get("adc", "").upper()

    if adc_id not in ADC_CONFIGS:
        return jsonify({"error": f"Unknown ADC channel '{adc_id}'"}), 400

    try:
        voltage = adc_read(ADC_CONFIGS[adc_id])
        return jsonify({"ok": True, "adc": adc_id, "voltage": voltage})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/test", methods=["POST"])
def run_test():
    """
    Full sweep
    """
    body    = request.get_json(force=True)
    ch_id   = body.get("channel", "").upper()
    adc_id  = body.get("adc", "IN1").upper()

    if ch_id not in CHANNELS:
        return jsonify({"error": f"Unknown channel '{ch_id}'"}), 400
    if adc_id not in ADC_CONFIGS:
        return jsonify({"error": f"Unknown ADC '{adc_id}'"}), 400

    ch = CHANNELS[ch_id]
    max_code = ch["max_code"]
    steps = [0, max_code//4, max_code//2, 3*max_code//4, max_code]
    results = []

    try:
        for code in steps:
            if ch["type"] == "mcp4725":
                mcp4725_write(ch["addr"], code)
            else:
                dac5571_write(ch["addr"], code)

            time.sleep(0.3)
            adc_v = adc_read(ADC_CONFIGS[adc_id])
            dac_v = round(code / max_code * 3.3, 4)
            results.append({
                "code": code,
                "dac_voltage": dac_v,
                "adc_voltage": adc_v,
                "error": round(abs(dac_v - adc_v), 4),
            })

        return jsonify({"ok": True, "channel": ch_id, "adc": adc_id, "results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def index():
    return send_from_directory(".", "adc_dac_ui.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)