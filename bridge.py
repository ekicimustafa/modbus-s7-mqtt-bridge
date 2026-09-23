"""
modbus-s7-mqtt-bridge
---------------------
Reads tags from Modbus TCP/RTU and Siemens S7 PLCs,
publishes to an MQTT broker with offline buffering.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import paho.mqtt.client as mqtt
import yaml
from pymodbus.client import AsyncModbusTcpClient
import snap7

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


@dataclass
class Tag:
    name: str
    type: str
    scale: float = 1.0
    offset: float = 0.0
    # Modbus
    register: int = 0
    # S7
    db: int = 0
    db_offset: int = 0
    bit: int = 0


@dataclass
class Device:
    name: str
    protocol: str
    host: str
    poll_interval_ms: int
    tags: list[Tag]
    port: int = 502
    rack: int = 0
    slot: int = 1


class MqttPublisher:
    def __init__(self, cfg: dict):
        self.host = cfg["host"]
        self.port = cfg.get("port", 1883)
        self.topic_prefix = cfg.get("topic_prefix", "factory")
        self.qos = cfg.get("qos", 1)
        self._client = mqtt.Client()
        if cfg.get("username"):
            self._client.username_pw_set(cfg["username"], cfg.get("password"))
        self._client.on_connect = lambda c, u, f, rc: log.info("MQTT connected (rc=%d)", rc)
        self._client.on_disconnect = lambda c, u, rc: log.warning("MQTT disconnected (rc=%d)", rc)
        self._client.connect_async(self.host, self.port)
        self._client.loop_start()

    def publish(self, device_name: str, tag_name: str, value: Any) -> None:
        topic = f"{self.topic_prefix}/{device_name}/{tag_name}"
        payload = json.dumps(value) if not isinstance(value, str) else value
        self._client.publish(topic, payload, qos=self.qos)


async def poll_modbus(device: Device, publisher: MqttPublisher) -> None:
    client = AsyncModbusTcpClient(device.host, port=device.port)
    await client.connect()
    log.info("Modbus connected: %s @ %s:%d", device.name, device.host, device.port)

    while True:
        start = time.monotonic()
        if client.connected:
            for tag in device.tags:
                try:
                    if tag.type == "bool":
                        r = await client.read_discrete_inputs(tag.register - 10001, count=1)
                        value = bool(r.bits[0])
                    else:
                        r = await client.read_holding_registers(tag.register - 40001, count=1)
                        raw = r.registers[0]
                        value = raw * tag.scale + tag.offset
                    publisher.publish(device.name, tag.name, value)
                except Exception as e:
                    log.warning("Modbus read error [%s.%s]: %s", device.name, tag.name, e)
        else:
            log.warning("Modbus disconnected, reconnecting: %s", device.name)
            await client.connect()

        elapsed = time.monotonic() - start
        sleep = max(0.0, device.poll_interval_ms / 1000.0 - elapsed)
        await asyncio.sleep(sleep)


async def poll_s7(device: Device, publisher: MqttPublisher) -> None:
    client = snap7.client.Client()

    def connect() -> bool:
        try:
            client.connect(device.host, device.rack, device.slot, device.port)
            log.info("S7 connected: %s @ %s", device.name, device.host)
            return True
        except Exception as e:
            log.warning("S7 connect failed [%s]: %s", device.name, e)
            return False

    connect()

    while True:
        start = time.monotonic()
        if not client.get_connected():
            connect()
            await asyncio.sleep(5)
            continue

        for tag in device.tags:
            try:
                data = await asyncio.to_thread(client.db_read, tag.db, tag.db_offset, 8)
                if tag.type == "bool":
                    from snap7.util import get_bool
                    value = get_bool(data, 0, tag.bit)
                elif tag.type == "real":
                    from snap7.util import get_real
                    value = round(float(get_real(data, 0)) * tag.scale + tag.offset, 4)
                elif tag.type in ("int16", "int"):
                    from snap7.util import get_int
                    value = get_int(data, 0) * tag.scale + tag.offset
                elif tag.type in ("uint16", "uint"):
                    from snap7.util import get_uint
                    value = get_uint(data, 0) * tag.scale + tag.offset
                else:
                    continue
                publisher.publish(device.name, tag.name, value)
            except Exception as e:
                log.warning("S7 read error [%s.%s]: %s", device.name, tag.name, e)

        elapsed = time.monotonic() - start
        sleep = max(0.0, device.poll_interval_ms / 1000.0 - elapsed)
        await asyncio.sleep(sleep)


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


async def main():
    cfg = load_config()
    publisher = MqttPublisher(cfg["mqtt"])

    tasks = []
    for dev_cfg in cfg.get("devices", []):
        tags = [Tag(**t) for t in dev_cfg.pop("tags", [])]
        device = Device(**dev_cfg, tags=tags)

        if device.protocol == "modbus_tcp":
            tasks.append(asyncio.create_task(poll_modbus(device, publisher)))
        elif device.protocol == "s7":
            tasks.append(asyncio.create_task(poll_s7(device, publisher)))
        else:
            log.warning("Unknown protocol: %s", device.protocol)

    log.info("Bridge started — %d device(s)", len(tasks))
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
