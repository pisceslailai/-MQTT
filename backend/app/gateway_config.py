from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import re
from typing import Any

from dateutil.parser import isoparse
from psycopg.rows import dict_row

from .db import get_conn
from .models import MeterReading


DEFAULT_SAMPLE_PAYLOAD = {
    "meter_id": "FM001",
    "device_ts": "2026-05-20T10:15:00+08:00",
    "instant_flow": 12.34,
    "total_flow": 56789.01,
    "unit": "m3/h",
}


@dataclass(frozen=True)
class GatewayConfig:
    id: int | None
    name: str
    enabled: bool
    priority: int
    topic_pattern: str
    meter_id_path: str
    meter_id_topic_index: int | None
    device_ts_path: str
    instant_flow_path: str
    total_flow_path: str
    unit_path: str
    default_unit: str
    instant_flow_scale: float
    total_flow_scale: float
    sample_payload: dict[str, Any]
    notes: str


DEFAULT_CONFIG = GatewayConfig(
    id=None,
    name="标准 MQTT JSON",
    enabled=True,
    priority=100,
    topic_pattern="meters/+/reading",
    meter_id_path="meter_id",
    meter_id_topic_index=1,
    device_ts_path="device_ts",
    instant_flow_path="instant_flow",
    total_flow_path="total_flow",
    unit_path="unit",
    default_unit="m3/h",
    instant_flow_scale=1.0,
    total_flow_scale=1.0,
    sample_payload=DEFAULT_SAMPLE_PAYLOAD,
    notes="默认配置，兼容当前模拟器和推荐网关 payload。",
)


class GatewayParseError(ValueError):
    pass


def ensure_gateway_config_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gateway_configs (
                id BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT true,
                priority INTEGER NOT NULL DEFAULT 100,
                topic_pattern TEXT NOT NULL DEFAULT 'meters/+/reading',
                meter_id_path TEXT NOT NULL DEFAULT 'meter_id',
                meter_id_topic_index INTEGER,
                device_ts_path TEXT NOT NULL DEFAULT 'device_ts',
                instant_flow_path TEXT NOT NULL DEFAULT 'instant_flow',
                total_flow_path TEXT NOT NULL DEFAULT 'total_flow',
                unit_path TEXT NOT NULL DEFAULT 'unit',
                default_unit TEXT NOT NULL DEFAULT 'm3/h',
                instant_flow_scale DOUBLE PRECISION NOT NULL DEFAULT 1,
                total_flow_scale DOUBLE PRECISION NOT NULL DEFAULT 1,
                sample_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                notes TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_gateway_configs_enabled_priority
                ON gateway_configs (enabled, priority, id)
            """
        )
        existing = conn.execute("SELECT id FROM gateway_configs LIMIT 1").fetchone()
        if not existing:
            save_gateway_config(asdict(DEFAULT_CONFIG), conn=conn)
        conn.commit()


def list_gateway_configs() -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT *
                FROM gateway_configs
                ORDER BY priority ASC, id ASC
                """
            ).fetchall()
            return [_row_to_config(row) for row in rows]


def get_gateway_config(config_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute("SELECT * FROM gateway_configs WHERE id = %s", (config_id,)).fetchone()
            return _row_to_config(row) if row else None


def save_gateway_config(data: dict[str, Any], config_id: int | None = None, conn=None) -> dict[str, Any]:
    own_conn = conn is None
    if own_conn:
        conn_ctx = get_conn()
        conn = conn_ctx.__enter__()
    try:
        payload = normalize_config_payload(data)
        with conn.cursor(row_factory=dict_row) as cur:
            if config_id:
                row = cur.execute(
                    """
                    UPDATE gateway_configs
                    SET name = %s,
                        enabled = %s,
                        priority = %s,
                        topic_pattern = %s,
                        meter_id_path = %s,
                        meter_id_topic_index = %s,
                        device_ts_path = %s,
                        instant_flow_path = %s,
                        total_flow_path = %s,
                        unit_path = %s,
                        default_unit = %s,
                        instant_flow_scale = %s,
                        total_flow_scale = %s,
                        sample_payload = %s::jsonb,
                        notes = %s,
                        updated_at = now()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (*payload, config_id),
                ).fetchone()
                if not row:
                    raise GatewayParseError(f"gateway config {config_id} not found")
            else:
                row = cur.execute(
                    """
                    INSERT INTO gateway_configs (
                        name, enabled, priority, topic_pattern, meter_id_path,
                        meter_id_topic_index, device_ts_path, instant_flow_path,
                        total_flow_path, unit_path, default_unit, instant_flow_scale,
                        total_flow_scale, sample_payload, notes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    RETURNING *
                    """,
                    payload,
                ).fetchone()
        if own_conn:
            conn.commit()
        return _row_to_config(row)
    finally:
        if own_conn:
            conn_ctx.__exit__(None, None, None)


def delete_gateway_config(config_id: int) -> bool:
    with get_conn() as conn:
        result = conn.execute("DELETE FROM gateway_configs WHERE id = %s", (config_id,))
        conn.commit()
        return bool(result.rowcount)


def parse_reading_with_configs(topic: str, payload: bytes) -> tuple[MeterReading, dict[str, Any] | None]:
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise GatewayParseError("payload must be a JSON object")

    errors = []
    for config in enabled_gateway_configs():
        if not mqtt_topic_matches(config["topic_pattern"], topic):
            continue
        try:
            return parse_reading_with_config(topic, data, config), config
        except Exception as exc:
            errors.append(f"{config['name']}: {exc}")

    if errors:
        raise GatewayParseError("; ".join(errors))
    return parse_default_reading(topic, data), None


def enabled_gateway_configs() -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                SELECT *
                FROM gateway_configs
                WHERE enabled = true
                ORDER BY priority ASC, id ASC
                """
            ).fetchall()
            return [_row_to_config(row) for row in rows]


def parse_reading_with_config(topic: str, data: dict[str, Any], config: dict[str, Any]) -> MeterReading:
    meter_id = value_at_path(data, config.get("meter_id_path"))
    if meter_id in (None, "") and config.get("meter_id_topic_index") is not None:
        parts = topic.split("/")
        index = int(config["meter_id_topic_index"])
        if 0 <= index < len(parts):
            meter_id = parts[index]
    if meter_id in (None, ""):
        raise GatewayParseError("meter_id is empty")

    device_ts = parse_device_ts(required_value(data, config.get("device_ts_path"), "device_ts"))
    instant_flow = parse_scaled_number(
        required_value(data, config.get("instant_flow_path"), "instant_flow"),
        config.get("instant_flow_scale", 1),
        "instant_flow",
    )
    total_flow = parse_scaled_number(
        required_value(data, config.get("total_flow_path"), "total_flow"),
        config.get("total_flow_scale", 1),
        "total_flow",
    )
    unit = value_at_path(data, config.get("unit_path")) or config.get("default_unit") or "m3/h"

    return MeterReading(
        meter_id=str(meter_id),
        device_ts=device_ts,
        instant_flow=instant_flow,
        total_flow=total_flow,
        unit=str(unit),
        payload=data,
        topic=topic,
    )


def parse_default_reading(topic: str, data: dict[str, Any]) -> MeterReading:
    return parse_reading_with_config(topic, data, _config_from_body(asdict(DEFAULT_CONFIG)))


def test_gateway_config(data: dict[str, Any]) -> dict[str, Any]:
    if "config" not in data and "payload" in data:
        topic = str(data.get("topic") or "meters/FM001/reading")
        payload = data["payload"]
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        reading, config = parse_reading_with_configs(topic, payload_bytes)
        return _reading_result(reading, config)

    config_data = data.get("config") or {
        **asdict(DEFAULT_CONFIG),
        **{key: value for key, value in data.items() if key in asdict(DEFAULT_CONFIG)},
    }
    config = _config_from_body(config_data)
    topic = str(data.get("topic") or config["topic_pattern"].replace("+", "FM001").replace("#", "reading"))
    payload = data.get("payload") or config.get("sample_payload") or DEFAULT_SAMPLE_PAYLOAD
    if isinstance(payload, str):
        payload = json.loads(payload)
    reading = parse_reading_with_config(topic, payload, config)
    return _reading_result(reading, config)


def _reading_result(reading: MeterReading, config: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "ok": True,
        "config": config.get("name") if config else "default",
        "reading": {
            "meter_id": reading.meter_id,
            "device_ts": reading.device_ts.astimezone(UTC).isoformat(),
            "instant_flow": reading.instant_flow,
            "total_flow": reading.total_flow,
            "unit": reading.unit,
            "topic": reading.topic,
        },
    }


def normalize_config_payload(data: dict[str, Any]) -> tuple:
    sample_payload = data.get("sample_payload") or DEFAULT_SAMPLE_PAYLOAD
    if isinstance(sample_payload, str):
        try:
            sample_payload = json.loads(sample_payload)
        except json.JSONDecodeError as exc:
            raise GatewayParseError(f"sample_payload is not valid JSON: {exc}") from exc
    if not isinstance(sample_payload, dict):
        raise GatewayParseError("sample_payload must be a JSON object")

    topic_index = data.get("meter_id_topic_index")
    if topic_index in ("", None):
        topic_index = None
    else:
        topic_index = int(topic_index)

    return (
        str(data.get("name") or "未命名配置").strip(),
        bool(data.get("enabled", True)),
        int(data.get("priority", 100)),
        str(data.get("topic_pattern") or "meters/+/reading").strip(),
        str(data.get("meter_id_path") or "").strip(),
        topic_index,
        str(data.get("device_ts_path") or "device_ts").strip(),
        str(data.get("instant_flow_path") or "instant_flow").strip(),
        str(data.get("total_flow_path") or "total_flow").strip(),
        str(data.get("unit_path") or "").strip(),
        str(data.get("default_unit") or "m3/h").strip(),
        float(data.get("instant_flow_scale") or 1),
        float(data.get("total_flow_scale") or 1),
        json.dumps(sample_payload, ensure_ascii=False),
        str(data.get("notes") or "").strip(),
    )


def _config_from_body(data: dict[str, Any]) -> dict[str, Any]:
    values = normalize_config_payload(data)
    return {
        "name": values[0],
        "enabled": values[1],
        "priority": values[2],
        "topic_pattern": values[3],
        "meter_id_path": values[4],
        "meter_id_topic_index": values[5],
        "device_ts_path": values[6],
        "instant_flow_path": values[7],
        "total_flow_path": values[8],
        "unit_path": values[9],
        "default_unit": values[10],
        "instant_flow_scale": values[11],
        "total_flow_scale": values[12],
        "sample_payload": json.loads(values[13]),
        "notes": values[14],
    }


def _row_to_config(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if isinstance(result.get("sample_payload"), str):
        result["sample_payload"] = json.loads(result["sample_payload"])
    return result


def required_value(data: dict[str, Any], path: str | None, label: str) -> Any:
    value = value_at_path(data, path)
    if value in (None, ""):
        raise GatewayParseError(f"{label} path '{path}' is empty")
    return value


def value_at_path(data: Any, path: str | None) -> Any:
    if not path:
        return None
    current = data
    for part in _path_parts(path):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and str(part).isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


def _path_parts(path: str) -> list[str]:
    normalized = re.sub(r"\[(\d+)\]", r".\1", path.strip())
    normalized = normalized[2:] if normalized.startswith("$.") else normalized
    return [part for part in normalized.split(".") if part]


def parse_device_ts(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        if value > 10_000_000_000:
            value = value / 1000
        return datetime.fromtimestamp(value, tz=UTC)
    parsed = isoparse(str(value))
    if parsed.tzinfo is None:
        raise GatewayParseError("device_ts must include timezone")
    return parsed


def parse_scaled_number(value: Any, scale: Any, label: str) -> float:
    try:
        return float(value) * float(scale or 1)
    except (TypeError, ValueError) as exc:
        raise GatewayParseError(f"{label} must be numeric") from exc


def mqtt_topic_matches(pattern: str, topic: str) -> bool:
    pattern_parts = pattern.split("/")
    topic_parts = topic.split("/")
    for index, part in enumerate(pattern_parts):
        if part == "#":
            return True
        if index >= len(topic_parts):
            return False
        if part != "+" and part != topic_parts[index]:
            return False
    return len(pattern_parts) == len(topic_parts)
