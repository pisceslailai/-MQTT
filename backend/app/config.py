from functools import lru_cache
import os


class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://flow_user:flow_password@localhost:5432/flow_monitor",
    )
    mqtt_host: str = os.getenv("MQTT_HOST", "localhost")
    mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))
    mqtt_topic: str = os.getenv("MQTT_TOPIC", "meters/+/reading")
    mqtt_username: str = os.getenv("MQTT_USERNAME", "")
    mqtt_password: str = os.getenv("MQTT_PASSWORD", "")
    clock_skew_seconds: int = int(os.getenv("CLOCK_SKEW_SECONDS", "120"))
    offline_after_seconds: int = int(os.getenv("OFFLINE_AFTER_SECONDS", "180"))
    alert_webhook_url: str = os.getenv("ALERT_WEBHOOK_URL", "")
    alert_webhook_type: str = os.getenv("ALERT_WEBHOOK_TYPE", "wechat")


@lru_cache
def get_settings() -> Settings:
    return Settings()
