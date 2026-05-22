import logging

import paho.mqtt.client as mqtt

from .config import get_settings
from .gateway_config import IgnoredMqttPayload, enabled_gateway_configs, parse_readings_with_configs
from .storage import insert_reading, record_gateway_heartbeat

logger = logging.getLogger(__name__)


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

    def is_connected(self) -> bool:
        return self.client.is_connected()

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        logger.info("MQTT connected: %s", reason_code)
        for topic in self._subscription_topics():
            client.subscribe(topic, qos=1)
            logger.info("MQTT subscribed topic: %s", topic)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        logger.warning("MQTT disconnected: %s", reason_code)

    def _on_message(self, client, userdata, message) -> None:
        try:
            readings, config = parse_readings_with_configs(message.topic, message.payload)
            for reading in readings:
                inserted = insert_reading(reading)
                logger.info(
                    "Stored reading id=%s meter=%s device_ts=%s status=%s config=%s",
                    inserted["id"],
                    inserted["meter_id"],
                    inserted["device_ts"],
                    inserted["status"],
                    config["name"] if config else "default",
                )
        except IgnoredMqttPayload as exc:
            status = record_gateway_heartbeat(message.topic, exc.payload_text)
            logger.info(
                "Recorded gateway heartbeat gateway=%s topic=%s reason=%s",
                status["gateway_id"],
                message.topic,
                exc.reason,
            )
        except Exception:
            logger.exception("Failed to process MQTT message topic=%s payload=%r", message.topic, message.payload)

    def _subscription_topics(self) -> list[str]:
        topics = [self.settings.mqtt_topic]
        try:
            topics.extend(config["topic_pattern"] for config in enabled_gateway_configs() if config.get("topic_pattern"))
        except Exception:
            logger.exception("Failed to load gateway MQTT subscriptions")

        seen = set()
        result = []
        for topic in topics:
            topic = str(topic or "").strip()
            if topic and topic not in seen:
                seen.add(topic)
                result.append(topic)
        return result
