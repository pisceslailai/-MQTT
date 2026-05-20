from __future__ import annotations

from datetime import datetime
import json
import logging
from urllib import request

from .config import get_settings

logger = logging.getLogger(__name__)

_last_alert_state: dict[str, str] = {}


def _format_time(value) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _payload(text: str) -> dict:
    settings = get_settings()
    if settings.alert_webhook_type.lower() == "dingtalk":
        return {"msgtype": "text", "text": {"content": text}}
    return {"msgtype": "text", "text": {"content": text}}


def send_alert(text: str) -> bool:
    settings = get_settings()
    if not settings.alert_webhook_url:
        return False

    body = json.dumps(_payload(text), ensure_ascii=False).encode("utf-8")
    req = request.Request(
        settings.alert_webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=8) as resp:
            ok = 200 <= resp.status < 300
            if not ok:
                logger.warning("Alert webhook returned HTTP %s", resp.status)
            return ok
    except Exception:
        logger.exception("Failed to send alert webhook")
        return False


def alert_for_meter(row: dict) -> tuple[str, str] | None:
    meter_id = row.get("meter_id", "unknown")
    status = str(row.get("status") or "").lower()
    interval_status = str(row.get("recent_interval_status") or "").lower()

    if status == "offline":
        return (
            f"{meter_id}:offline",
            f"流量计 {meter_id} 离线，最后接收时间：{_format_time(row.get('last_received_ts'))}",
        )
    if status == "clock_skew":
        reason = row.get("anomaly_reason") or "设备时间与服务器接收时间偏差超过阈值"
        return (
            f"{meter_id}:clock_skew",
            f"流量计 {meter_id} 时钟偏差：{reason}",
        )
    if interval_status in {"gap", "counter_reset"}:
        label = "15分钟窗口缺数据" if interval_status == "gap" else "累计流量回退"
        return (
            f"{meter_id}:interval:{interval_status}",
            f"流量计 {meter_id} {label}，窗口开始：{_format_time(row.get('recent_interval_start'))}",
        )
    return None


def send_meter_alerts(rows: list[dict]) -> int:
    sent = 0
    active_keys: set[str] = set()

    for row in rows:
        alert = alert_for_meter(row)
        if not alert:
            continue
        key, text = alert
        active_keys.add(key)
        if _last_alert_state.get(key) == text:
            continue
        if send_alert(f"【流量计监控告警】{text}"):
            _last_alert_state[key] = text
            sent += 1

    for key in list(_last_alert_state):
        if key not in active_keys:
            _last_alert_state.pop(key, None)

    return sent
