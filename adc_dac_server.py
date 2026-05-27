#!/usr/bin/env python3
"""
ADC/DAC Function Generator + Oscilloscope Server
Run with: python adc_dac_server.py
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import smbus2, time, math, threading

app = Flask(__name__)
CORS(app)

# Hardware constants 
ADC_ADDR = 0x49

CHANNELS = {
    "OUT1": {"type": "dac5571", "addr": 0x4D, "adc_cfg": 0xD3, "max_code": 255},
    "OUT2": {"type": "dac5571", "addr": 0x4C, "adc_cfg": 0xD3, "max_code": 255},
    "OUT3": {"type": "mcp4725", "addr": 0x61, "adc_cfg": 0xF3, "max_code": 4095},
    "OUT4": {"type": "mcp4725", "addr": 0x60, "adc_cfg": 0xC3, "max_code": 4095},
}

ADC_CONFIGS = {
    "IN1": 0xC3,
    "IN2": 0xD3,
    "IN3": 0xF3,
    "IN4": 0xE3,
}

#Bus 
_bus = None
def get_bus():
    global _bus
    if _bus is None:
        _bus = smbus2.SMBus(1)
    return _bus

#  DAC helpers
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

def dac_write(ch_id, code):
    ch = CHANNELS[ch_id]
    if ch["type"] == "mcp4725":
        mcp4725_write(ch["addr"], code)
    else:
        dac5571_write(ch["addr"], code)

def adc_read(config=0xC3):
    bus = get_bus()
    bus.write_i2c_block_data(ADC_ADDR, 0x01, [config, 0x83])
    for _ in range(20):
        time.sleep(0.01)
        bus.read_i2c_block_data(ADC_ADDR, 0x01, 2)
    d = bus.read_i2c_block_data(ADC_ADDR, 0x00, 2)
    raw = (d[0] << 8) | d[1]
    if raw > 32767:
        raw -= 65536
    return round(raw / 32767 * 4.096, 4)

# Waveform generator 
_gen_thread   = None
_gen_stop     = threading.Event()
_gen_state    = {"running": False, "channel": None, "waveform": None,
                 "freq": 1.0, "amplitude": 1.5, "offset": 1.65}

def _waveform_sample(waveform, phase):
    """Return normalised sample in [-1, 1] for given phase [0, 2π]."""
    t = phase / (2 * math.pi)
    if waveform == "sine":
        return math.sin(phase)
    elif waveform == "square":
        return 1.0 if t < 0.5 else -1.0
    elif waveform == "sawtooth":
        return 2.0 * t - 1.0
    elif waveform == "triangle":
        return 1.0 - 4.0 * abs(t - 0.5) if t < 1.0 else 0.0
    return 0.0

def _generator_loop(ch_id, waveform, freq, amplitude, offset, step_ms):
    ch       = CHANNELS[ch_id]
    max_code = ch["max_code"]
    vref     = 3.3
    phase    = 0.0
    dt       = step_ms / 1000.0
    omega    = 2 * math.pi * freq

    while not _gen_stop.is_set():
        t0      = time.monotonic()
        sample  = _waveform_sample(waveform, phase)
        voltage = offset + amplitude * sample
        voltage = max(0.0, min(vref, voltage))
        code    = int(voltage / vref * max_code)
        try:
            dac_write(ch_id, code)
        except Exception:
            pass
        phase = (phase + omega * dt) % (2 * math.pi)
        elapsed = time.monotonic() - t0
        sleep   = max(0, dt - elapsed)
        time.sleep(sleep)

    # zero output on stop
    try:
        dac_write(ch_id, 0)
    except Exception:
        pass

#  Routes 

@app.route("/api/channels", methods=["GET"])
def list_channels():
    return jsonify({
        "channels": [
            {"id": ch, "type": info["type"],
             "max_code": info["max_code"], "addr": hex(info["addr"])}
            for ch, info in CHANNELS.items()
        ]
    })

@app.route("/api/write", methods=["POST"])
def write_dac():
    body  = request.get_json(force=True)
    ch_id = body.get("channel", "").upper()
    code  = body.get("code")
    if ch_id not in CHANNELS:
        return jsonify({"error": f"Unknown channel '{ch_id}'"}), 400
    if code is None:
        return jsonify({"error": "Missing 'code'"}), 400
    try:
        dac_write(ch_id, code)
        max_code    = CHANNELS[ch_id]["max_code"]
        dac_voltage = round(int(code) / max_code * 3.3, 4)
        return jsonify({"ok": True, "channel": ch_id,
                        "code": int(code), "dac_voltage": dac_voltage})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/read", methods=["POST"])
def read_adc():
    body   = request.get_json(force=True)
    adc_id = body.get("adc", "").upper()
    if adc_id not in ADC_CONFIGS:
        return jsonify({"error": f"Unknown ADC '{adc_id}'"}), 400
    try:
        voltage = adc_read(ADC_CONFIGS[adc_id])
        return jsonify({"ok": True, "adc": adc_id, "voltage": voltage})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/generate", methods=["POST"])
def generate():
    """Start the waveform generator on a background thread."""
    global _gen_thread
    body     = request.get_json(force=True)
    ch_id    = body.get("channel", "OUT1").upper()
    waveform = body.get("waveform", "sine")
    freq     = float(body.get("freq", 1.0))
    amp      = float(body.get("amplitude", 1.5))
    offset   = float(body.get("offset", 1.65))
    step_ms  = float(body.get("step_ms", 20))     # DAC update interval

    if ch_id not in CHANNELS:
        return jsonify({"error": f"Unknown channel '{ch_id}'"}), 400
    if waveform not in ("sine", "square", "sawtooth", "triangle"):
        return jsonify({"error": "Unknown waveform"}), 400

    # stop any existing thread
    _gen_stop.set()
    if _gen_thread and _gen_thread.is_alive():
        _gen_thread.join(timeout=1.0)

    _gen_stop.clear()
    _gen_state.update(running=True, channel=ch_id, waveform=waveform,
                      freq=freq, amplitude=amp, offset=offset)

    _gen_thread = threading.Thread(
        target=_generator_loop,
        args=(ch_id, waveform, freq, amp, offset, step_ms),
        daemon=True
    )
    _gen_thread.start()
    return jsonify({"ok": True, "state": _gen_state})

@app.route("/api/stop", methods=["POST"])
def stop_gen():
    """Stop the generator."""
    _gen_stop.set()
    _gen_state["running"] = False
    return jsonify({"ok": True})

@app.route("/api/status", methods=["GET"])
def gen_status():
    return jsonify(_gen_state)

@app.route("/api/sample", methods=["POST"])
def sample_adc():
    """
    Take N fast ADC samples, return voltages + timestamps.
    Body: { "adc": "IN1", "n": 50 }
    Note: each sample takes ~200 ms (ADC conversion time).
    For a faster burst, pass "fast": true to skip the poll loop (less accurate).
    """
    body   = request.get_json(force=True)
    adc_id = body.get("adc", "IN1").upper()
    n      = min(int(body.get("n", 20)), 100)
    fast   = body.get("fast", False)

    if adc_id not in ADC_CONFIGS:
        return jsonify({"error": f"Unknown ADC '{adc_id}'"}), 400

    config  = ADC_CONFIGS[adc_id]
    samples = []
    t0      = time.monotonic()

    try:
        bus = get_bus()
        for _ in range(n):
            if fast:
                # single conversion trigger, minimal wait
                bus.write_i2c_block_data(ADC_ADDR, 0x01, [config, 0x83])
                time.sleep(0.008)
                d   = bus.read_i2c_block_data(ADC_ADDR, 0x00, 2)
            else:
                bus.write_i2c_block_data(ADC_ADDR, 0x01, [config, 0x83])
                for _ in range(20):
                    time.sleep(0.01)
                    bus.read_i2c_block_data(ADC_ADDR, 0x01, 2)
                d = bus.read_i2c_block_data(ADC_ADDR, 0x00, 2)

            raw = (d[0] << 8) | d[1]
            if raw > 32767:
                raw -= 65536
            v = round(raw / 32767 * 4.096, 4)
            samples.append({"t": round(time.monotonic() - t0, 4), "v": v})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"ok": True, "adc": adc_id, "samples": samples})

@app.route("/api/test", methods=["POST"])
def run_test():
    body   = request.get_json(force=True)
    ch_id  = body.get("channel", "").upper()
    adc_id = body.get("adc", "IN1").upper()
    if ch_id not in CHANNELS or adc_id not in ADC_CONFIGS:
        return jsonify({"error": "Unknown channel or ADC"}), 400
    ch       = CHANNELS[ch_id]
    max_code = ch["max_code"]
    steps    = [0, max_code//4, max_code//2, 3*max_code//4, max_code]
    results  = []
    try:
        for code in steps:
            dac_write(ch_id, code)
            time.sleep(0.3)
            adc_v = adc_read(ADC_CONFIGS[adc_id])
            dac_v = round(code / max_code * 3.3, 4)
            results.append({"code": code, "dac_voltage": dac_v,
                            "adc_voltage": adc_v, "error": round(abs(dac_v - adc_v), 4)})
        return jsonify({"ok": True, "channel": ch_id, "adc": adc_id, "results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def index():
    return send_from_directory(".", "adc_dac_ui.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)