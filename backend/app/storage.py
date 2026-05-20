from datetime import UTC, datetime, timedelta
import json

from psycopg.rows import dict_row

from .config import get_settings
from .db import get_conn
from .models import MeterReading


def normalize_window(ts: datetime) -> datetime:
    ts = ts.astimezone(UTC)
    minute = (ts.minute // 15) * 15
    return ts.replace(minute=minute, second=0, microsecond=0)


def insert_reading(reading: MeterReading) -> dict:
    settings = get_settings()
    received_ts = datetime.now(UTC)
    skew_seconds = abs((received_ts - reading.device_ts.astimezone(UTC)).total_seconds())

    status = "valid"
    anomaly_reason = None
    if skew_seconds > settings.clock_skew_seconds:
        status = "clock_skew"
        anomaly_reason = f"device time differs from receive time by {int(skew_seconds)} seconds"

    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO raw_readings (
                    meter_id, device_ts, received_ts, instant_flow, total_flow,
                    unit, topic, payload, status, anomaly_reason
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                RETURNING id, meter_id, device_ts, received_ts, status, anomaly_reason
                """,
                (
                    reading.meter_id,
                    reading.device_ts,
                    received_ts,
                    reading.instant_flow,
                    reading.total_flow,
                    reading.unit,
                    reading.topic,
                    json.dumps(reading.payload, ensure_ascii=False),
                    status,
                    anomaly_reason,
                ),
            ).fetchone()

        conn.execute(
            """
            INSERT INTO meter_status (
                meter_id, last_device_ts, last_received_ts, instant_flow, total_flow,
                unit, online, status, anomaly_reason, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, true, %s, %s, now())
            ON CONFLICT (meter_id) DO UPDATE SET
                last_device_ts = EXCLUDED.last_device_ts,
                last_received_ts = EXCLUDED.last_received_ts,
                instant_flow = EXCLUDED.instant_flow,
                total_flow = EXCLUDED.total_flow,
                unit = EXCLUDED.unit,
                online = true,
                status = EXCLUDED.status,
                anomaly_reason = EXCLUDED.anomaly_reason,
                updated_at = now()
            """,
            (
                reading.meter_id,
                reading.device_ts,
                received_ts,
                reading.instant_flow,
                reading.total_flow,
                reading.unit,
                status,
                anomaly_reason,
            ),
        )
        conn.commit()
        return dict(row)


def refresh_meter_status() -> None:
    settings = get_settings()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE meter_status
            SET
                online = last_received_ts IS NOT NULL
                    AND last_received_ts >= now() - (%s || ' seconds')::interval,
                status = CASE
                    WHEN last_received_ts IS NULL THEN 'unknown'
                    WHEN last_received_ts < now() - (%s || ' seconds')::interval THEN 'offline'
                    ELSE status
                END,
                updated_at = now()
            """,
            (settings.offline_after_seconds, settings.offline_after_seconds),
        )
        conn.commit()


def build_intervals(hours_back: int = 24) -> int:
    now = datetime.now(UTC)
    first_window = normalize_window(now - timedelta(hours=hours_back))
    with get_conn() as conn:
        rows = conn.execute(
            """
            WITH valid_windows AS (
                SELECT
                    meter_id,
                    date_bin('15 minutes', device_ts, TIMESTAMPTZ '2000-01-01 00:00:00+00') AS window_start,
                    min(device_ts) AS first_ts,
                    max(device_ts) AS last_ts,
                    avg(instant_flow) AS avg_instant_flow,
                    min(instant_flow) AS min_instant_flow,
                    max(instant_flow) AS max_instant_flow,
                    count(*)::int AS sample_count
                FROM raw_readings
                WHERE status = 'valid'
                  AND device_ts >= %s
                GROUP BY meter_id, window_start
            ),
            totals AS (
                SELECT
                    vw.*,
                    first_raw.total_flow AS first_total_flow,
                    last_raw.total_flow AS last_total_flow
                FROM valid_windows vw
                JOIN raw_readings first_raw
                  ON first_raw.meter_id = vw.meter_id
                 AND first_raw.device_ts = vw.first_ts
                 AND first_raw.status = 'valid'
                JOIN raw_readings last_raw
                  ON last_raw.meter_id = vw.meter_id
                 AND last_raw.device_ts = vw.last_ts
                 AND last_raw.status = 'valid'
            )
            INSERT INTO interval_readings (
                meter_id, window_start, window_end, first_total_flow, last_total_flow,
                interval_usage, avg_instant_flow, min_instant_flow, max_instant_flow,
                sample_count, has_gap, status, updated_at
            )
            SELECT
                meter_id,
                window_start,
                window_start + interval '15 minutes',
                first_total_flow,
                last_total_flow,
                GREATEST(last_total_flow - first_total_flow, 0),
                avg_instant_flow,
                min_instant_flow,
                max_instant_flow,
                sample_count,
                sample_count < 10,
                CASE
                    WHEN sample_count < 10 THEN 'gap'
                    WHEN last_total_flow < first_total_flow THEN 'counter_reset'
                    ELSE 'valid'
                END,
                now()
            FROM totals
            ON CONFLICT (meter_id, window_start) DO UPDATE SET
                window_end = EXCLUDED.window_end,
                first_total_flow = EXCLUDED.first_total_flow,
                last_total_flow = EXCLUDED.last_total_flow,
                interval_usage = EXCLUDED.interval_usage,
                avg_instant_flow = EXCLUDED.avg_instant_flow,
                min_instant_flow = EXCLUDED.min_instant_flow,
                max_instant_flow = EXCLUDED.max_instant_flow,
                sample_count = EXCLUDED.sample_count,
                has_gap = EXCLUDED.has_gap,
                status = EXCLUDED.status,
                updated_at = now()
            RETURNING id
            """,
            (first_window,),
        ).fetchall()
        conn.commit()
        return len(rows)


def latest_meters() -> list[dict]:
    refresh_meter_status()
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                """
                WITH recent_interval AS (
                    SELECT DISTINCT ON (meter_id)
                        meter_id,
                        interval_usage AS recent_interval_usage,
                        window_start AS recent_interval_start,
                        status AS recent_interval_status
                    FROM interval_readings
                    ORDER BY meter_id, window_start DESC
                ),
                today_usage AS (
                    SELECT meter_id, sum(interval_usage) AS today_usage
                    FROM interval_readings
                    WHERE window_start >= (
                        date_trunc('day', now() AT TIME ZONE 'Asia/Shanghai')
                        AT TIME ZONE 'Asia/Shanghai'
                    )
                    GROUP BY meter_id
                )
                SELECT
                    ms.*,
                    ri.recent_interval_usage,
                    ri.recent_interval_start,
                    ri.recent_interval_status,
                    COALESCE(tu.today_usage, 0) AS today_usage
                FROM meter_status ms
                LEFT JOIN recent_interval ri ON ri.meter_id = ms.meter_id
                LEFT JOIN today_usage tu ON tu.meter_id = ms.meter_id
                ORDER BY ms.meter_id
                """,
            ).fetchall()
            return [dict(row) for row in rows]


def interval_history(
    meter_id: str | None,
    limit: int,
    start_ts: datetime | None = None,
    end_ts: datetime | None = None,
    status: str | None = None,
) -> list[dict]:
    limit = min(max(limit, 1), 500)
    filters = []
    params: list = []
    if meter_id:
        filters.append("meter_id = %s")
        params.append(meter_id)
    if start_ts:
        filters.append("window_start >= %s")
        params.append(start_ts)
    if end_ts:
        filters.append("window_start < %s")
        params.append(end_ts)
    if status:
        filters.append("status = %s")
        params.append(status)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.append(limit)
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT *
                FROM interval_readings
                {where}
                ORDER BY window_start ASC
                LIMIT %s
                """,
                tuple(params),
            ).fetchall()
            return [dict(row) for row in rows]


def recent_raw(
    meter_id: str | None,
    limit: int,
    start_ts: datetime | None = None,
    end_ts: datetime | None = None,
    status: str | None = None,
) -> list[dict]:
    limit = min(max(limit, 1), 500)
    filters = []
    params: list = []
    if meter_id:
        filters.append("meter_id = %s")
        params.append(meter_id)
    if start_ts:
        filters.append("device_ts >= %s")
        params.append(start_ts)
    if end_ts:
        filters.append("device_ts < %s")
        params.append(end_ts)
    if status:
        filters.append("status = %s")
        params.append(status)

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.append(limit)
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""
                SELECT id, meter_id, device_ts, received_ts, instant_flow, total_flow,
                       unit, status, anomaly_reason
                FROM raw_readings
                {where}
                ORDER BY device_ts DESC
                LIMIT %s
                """,
                tuple(params),
            ).fetchall()
            return [dict(row) for row in rows]


def database_ping() -> bool:
    with get_conn() as conn:
        conn.execute("SELECT 1").fetchone()
        return True
