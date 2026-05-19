from datetime import datetime
import json
import logging

from dateutil.parser import isoparse
import paho.mqtt.client as mqtt

from .config import get_settings
from .models import MeterReading
from .storage import insert_reading

logger = logging.getLogger(__name__)


def parse_reading(topic: str, payload: bytes) -> MeterReading:
    data = json.loads(payload.decode("utf-8"))
    device_ts = data.get("device_ts") or data.get("ts")
    if not device_ts:
        raise ValueError("payload missing device_ts")

    parsed_ts = isoparse(str(device_ts))
    if parsed_ts.tzinfo is None:
        raise ValueError("device_ts must include timezone")

    meter_id = str(data.get("meter_id") or topic.split("/")[1])
    return MeterReading(
        meter_id=meter_id,
        device_ts=parsed_ts,
        instant_flow=float(data["instant_flow"]),
        total_flow=float(data["total_flow"]),
        unit=str(data.get("unit", "m3/h")),
        payload=data,
        topic=topic,
    )


class MqttSubscriber:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="flow-monitor-backend")
        if self.settings.mqtt_username:
            self.client.username_pw_set(
                self.settings.mqtt_username,
                self.settings.mqtt_password or None,
            )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def start(self) -> None:
        logger.info("Connecting MQTT broker %s:%s", self.settings.mqtt_host, self.settings.mqtt_port)
        self.client.connect(self.settings.mqtt_host, self.settings.mqtt_port, keepalive=60)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        logger.info("MQTT connected: %s", reason_code)
        client.subscribe(self.settings.mqtt_topic, qos=1)
        logger.info("MQTT subscribed topic: %s", self.settings.mqtt_topic)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        logger.warning("MQTT disconnected: %s", reason_code)

    def _on_message(self, client, userdata, message) -> None:
        try:
            reading = parse_reading(message.topic, message.payload)
            inserted = insert_reading(reading)
            logger.info(
                "Stored reading id=%s meter=%s device_ts=%s status=%s",
                inserted["id"],
                inserted["meter_id"],
                inserted["device_ts"],
                inserted["status"],
            )
        except Exception:
            logger.exception("Failed to process MQTT message topic=%s payload=%r", message.topic, message.payload)
