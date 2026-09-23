# modbus-s7-mqtt-bridge

A lightweight, production-ready Python bridge that reads tags from industrial PLCs (Modbus TCP/RTU and Siemens S7) and publishes them to an MQTT broker. Designed as a building block for industrial IoT gateways.

---

## Features

- **Modbus TCP & RTU** — reads coils, discrete inputs, holding registers, input registers
- **Siemens S7** — reads DB blocks, I/Q/M areas via native S7comm (snap7)
- **MQTT publish** — configurable topic structure, QoS 1, auto-reconnect
- **Offline buffer** — SQLite-backed local storage when broker is unreachable; flushes on reconnect
- **Multi-device** — poll multiple PLCs in parallel with independent intervals
- **Configurable** — single YAML config file, no code changes needed
- **Lightweight** — runs on Raspberry Pi 4 / DietPi with < 100MB RAM

---

## Quick Start

```bash
git clone https://github.com/ekicimustafa/modbus-s7-mqtt-bridge.git
cd modbus-s7-mqtt-bridge
pip install -r requirements.txt
cp config.example.yaml config.yaml
# Edit config.yaml with your PLC and broker settings
python bridge.py
```

---

## Configuration

```yaml
mqtt:
  host: "192.168.1.100"
  port: 1883
  username: "gateway"
  password: "secret"
  topic_prefix: "factory/line1"
  qos: 1

devices:
  - name: "conveyor-plc"
    protocol: modbus_tcp
    host: "192.168.1.10"
    port: 502
    poll_interval_ms: 1000
    tags:
      - name: "motor_speed"
        register: 40001
        type: uint16
        scale: 0.1        # raw value × 0.1 = RPM
      - name: "motor_running"
        register: 10001
        type: bool

  - name: "s7-1500-main"
    protocol: s7
    host: "192.168.1.20"
    rack: 0
    slot: 1
    poll_interval_ms: 500
    tags:
      - name: "temperature_zone1"
        db: 10
        offset: 0
        type: real         # 32-bit float
      - name: "pump_enabled"
        db: 10
        offset: 4
        bit: 0
        type: bool
```

MQTT output:
```
factory/line1/conveyor-plc/motor_speed    → 145.3
factory/line1/conveyor-plc/motor_running  → true
factory/line1/s7-1500-main/temperature_zone1 → 87.4
```

---

## Supported Tag Types

| Type | Modbus | S7 |
|------|--------|----|
| bool | coil / discrete input | DB bit |
| uint16 | holding / input register | DB UINT |
| int16 | holding / input register | DB INT |
| uint32 | 2× registers | DB UDINT |
| int32 | 2× registers | DB DINT |
| float32 | 2× registers (IEEE 754) | DB REAL |
| float64 | 4× registers (IEEE 754) | DB LREAL |

---

## Architecture

```
┌─────────────┐    S7comm/     ┌──────────────────┐
│ Siemens S7  │─── Modbus ────▶│                  │
│  1200/1500  │                │   bridge.py       │──── MQTT ────▶ Broker
└─────────────┘                │  (async Python)  │
                               │                  │──── SQLite ──▶ Offline
┌─────────────┐    Modbus TCP  │   buffer         │               Buffer
│  Any Modbus │───────────────▶│                  │
│    Device   │                └──────────────────┘
└─────────────┘
```

---

## Requirements

```
pymodbus>=3.5.0
python-snap7>=1.3
paho-mqtt>=1.6.1
aiosqlite>=0.19.0
pyyaml>=6.0
```

Python 3.10+

---

## Deployment (Raspberry Pi / Edge Device)

```bash
# As a systemd service
sudo cp modbus-s7-mqtt-bridge.service /etc/systemd/system/
sudo systemctl enable modbus-s7-mqtt-bridge
sudo systemctl start modbus-s7-mqtt-bridge
```

---

## Related Projects

- [industrial-commissioning-checklist](https://github.com/ekicimustafa/industrial-commissioning-checklist) — Field commissioning checklist for industrial facilities

---

## License

MIT
