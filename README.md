# modbus-s7-mqtt-bridge

A lightweight, production-ready Python bridge that reads tags from industrial PLCs (Modbus TCP/RTU and Siemens S7) and publishes them to an MQTT broker. Designed as a building block for industrial IoT gateways — the OT edge component in a full IT/OT integration stack.

---

## The OT/IT Problem

Industrial automation and IT systems speak fundamentally different languages:

| OT (Field Level) | IT (Cloud/Software Level) |
|------------------|--------------------------|
| Siemens S7, Modbus RTU | REST APIs, WebSockets |
| Polling cycles (100ms–10s) | Event-driven architecture |
| Register addresses, DB blocks | JSON, time-series databases |
| Deterministic, real-time | Scalable, distributed |
| 20–30 year lifecycles | Continuous deployment |

This bridge closes that gap. It speaks the OT protocols natively and produces clean, structured MQTT messages that any IT system can consume.

---

## Where This Fits

```
┌─────────────────────────────────────────────────────────────────────┐
│  OT LAYER (Field)                                                   │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │ Siemens S7   │  │ Modbus RTU   │  │ Modbus TCP   │             │
│  │ 1200 / 1500  │  │ Energy meter │  │ VFD / Sensor │             │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘             │
│         │  S7comm          │  RS-485          │  TCP/IP             │
└─────────┼──────────────────┼──────────────────┼────────────────────┘
          │                  │                  │
┌─────────▼──────────────────▼──────────────────▼────────────────────┐
│  EDGE LAYER (this repo)                                             │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │              modbus-s7-mqtt-bridge (Python)             │       │
│  │  • Async polling per device, configurable interval      │       │
│  │  • Tag scaling, type conversion                         │       │
│  │  • SQLite offline buffer (survives broker outage)       │       │
│  │  • Reconnect logic for both PLC and MQTT sides          │       │
│  └─────────────────────────┬───────────────────────────────┘       │
│                             │  MQTT (QoS 1)                        │
│                     Raspberry Pi / x86 edge device                 │
└─────────────────────────────┼──────────────────────────────────────┘
                              │
┌─────────────────────────────▼──────────────────────────────────────┐
│  IT LAYER (Cloud / On-Premise Platform)                            │
│                                                                     │
│  MQTT Broker (EMQX)  →  Ingestion Service  →  TimescaleDB          │
│                                →  Kafka (stream processing)        │
│                                →  REST API (FastAPI)               │
│                                →  Dashboard / Alerting             │
└─────────────────────────────────────────────────────────────────────┘
```

This bridge is the OT edge layer. For a full IoT platform reference implementation, see the production architecture notes below.

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
factory/line1/conveyor-plc/motor_speed       → 145.3
factory/line1/conveyor-plc/motor_running     → true
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

## Real-World Protocol Notes

**Modbus register addressing:**
- Coils: `0xxxx` (read/write digital)
- Discrete inputs: `1xxxx` (read-only digital)
- Input registers: `3xxxx` (read-only analog)
- Holding registers: `4xxxx` (read/write analog)
- Some devices use zero-based addressing; set `address_mode: raw` in config if register 40001 maps to address 0.

**Siemens S7 — known quirks:**
- S7-300/400: rack/slot from hardware config (usually rack=0, slot=2)
- S7-1200/1500: rack=0, slot=1 — but must enable "PUT/GET" in TIA Portal → Device properties → Protection
- DB blocks must not be optimized (uncheck "Optimized block access" in TIA Portal)
- PCS7: uses S7-400 hardware; same snap7 protocol but larger DB numbers

**IEC 104 (power grid RTUs):**
Not in this repo, but commonly used alongside Modbus in energy applications. IEC 104 is TCP-based, carries time-stamped measurements (IOA addressing), and is standard in SCADA ↔ distribution company communication.

---

## Deployment (Raspberry Pi / Edge Device)

```bash
# As a systemd service
sudo cp modbus-s7-mqtt-bridge.service /etc/systemd/system/
sudo systemctl enable modbus-s7-mqtt-bridge
sudo systemctl start modbus-s7-mqtt-bridge
```

**Production tips:**
- Use a static IP or hostname reservation for PLCs — avoid DHCP for field devices
- Set `TIOCEXCL` exclusive lock on RS-485 serial port to prevent multiple processes from accessing the port simultaneously
- For RS-485 RTU: if using a USB-RS485 adapter, pin the device by serial number in udev rules (`/etc/udev/rules.d/`) — USB ports re-enumerate on reboot
- Test RTU at 9600 baud first; most meters default to 9600 even if the datasheet says otherwise
- On factory networks: many Modbus devices don't handle TCP keepalive well. If polling stalls silently, force reconnect after N consecutive timeouts.

---

## IT-Side Integration Example

Once data reaches the MQTT broker, a minimal FastAPI consumer:

```python
import asyncio
import json
from aiomqtt import Client
from datetime import datetime, timezone

async def consume():
    async with Client("192.168.1.100") as client:
        await client.subscribe("factory/#")
        async for message in client.messages:
            topic_parts = str(message.topic).split("/")
            device = topic_parts[-2]
            tag = topic_parts[-1]
            value = float(message.payload)
            timestamp = datetime.now(timezone.utc)
            # Insert into TimescaleDB, push to Kafka, trigger alerts...
            print(f"{timestamp} | {device}.{tag} = {value}")

asyncio.run(consume())
```

For production platform architecture (multi-tenant, Kafka, TimescaleDB, on-premise deployment), see my other work: [SolarTools Platform](https://portal.solartools.com.tr) — source is private (production system).

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

## Related Projects

- [industrial-commissioning-checklist](https://github.com/ekicimustafa/industrial-commissioning-checklist) — Field commissioning checklist for 10+ industrial facility types

---

## License

MIT
