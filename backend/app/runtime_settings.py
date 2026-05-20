from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from .config import get_settings
from .db import get_conn


def default_runtime_settings() -> dict[str, Any]:
    settings = get_settings()
    return {
        "clock_skew_seconds": settings.clock_skew_seconds,
        "offline_after_seconds": settings.offline_after_seconds,
        "expected_interval_samples": 10,
    }


def ensure_runtime_settings_schema() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_settings (
                id BOOLEAN PRIMARY KEY DEFAULT true,
                clock_skew_seconds INTEGER NOT NULL,
                offline_after_seconds INTEGER NOT NULL,
                expected_interval_samples INTEGER NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT runtime_settings_singleton CHECK (id = true)
            )
            """
        )
        defaults = default_runtime_settings()
        conn.execute(
            """
            INSERT INTO runtime_settings (
                id, clock_skew_seconds, offline_after_seconds, expected_interval_samples
            )
            VALUES (true, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                defaults["clock_skew_seconds"],
                defaults["offline_after_seconds"],
                defaults["expected_interval_samples"],
            ),
        )
        conn.commit()


def get_runtime_settings() -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                SELECT clock_skew_seconds, offline_after_seconds,
                       expected_interval_samples, updated_at
                FROM runtime_settings
                WHERE id = true
                """
            ).fetchone()
            if not row:
                return default_runtime_settings()
            return dict(row)


def update_runtime_settings(data: dict[str, Any]) -> dict[str, Any]:
    current = get_runtime_settings()
    clock_skew_seconds = _positive_int(data.get("clock_skew_seconds", current["clock_skew_seconds"]), "clock_skew_seconds")
    offline_after_seconds = _positive_int(
        data.get("offline_after_seconds", current["offline_after_seconds"]),
        "offline_after_seconds",
    )
    expected_interval_samples = _positive_int(
        data.get("expected_interval_samples", current["expected_interval_samples"]),
        "expected_interval_samples",
    )

    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                INSERT INTO runtime_settings (
                    id, clock_skew_seconds, offline_after_seconds,
                    expected_interval_samples, updated_at
                )
                VALUES (true, %s, %s, %s, now())
                ON CONFLICT (id) DO UPDATE SET
                    clock_skew_seconds = EXCLUDED.clock_skew_seconds,
                    offline_after_seconds = EXCLUDED.offline_after_seconds,
                    expected_interval_samples = EXCLUDED.expected_interval_samples,
                    updated_at = now()
                RETURNING clock_skew_seconds, offline_after_seconds,
                          expected_interval_samples, updated_at
                """,
                (clock_skew_seconds, offline_after_seconds, expected_interval_samples),
            ).fetchone()
        conn.commit()
        return dict(row)


def _positive_int(value: Any, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer") from exc
    if parsed <= 0:
        raise ValueError(f"{label} must be greater than 0")
    return parsed
