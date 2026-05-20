CREATE TABLE IF NOT EXISTS raw_readings (
    id BIGSERIAL PRIMARY KEY,
    meter_id TEXT NOT NULL,
    device_ts TIMESTAMPTZ NOT NULL,
    received_ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    instant_flow DOUBLE PRECISION NOT NULL,
    total_flow DOUBLE PRECISION NOT NULL,
    unit TEXT NOT NULL DEFAULT 'm3/h',
    topic TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'valid',
    anomaly_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_raw_readings_meter_device_ts
    ON raw_readings (meter_id, device_ts DESC);

CREATE INDEX IF NOT EXISTS idx_raw_readings_status
    ON raw_readings (status);

CREATE TABLE IF NOT EXISTS interval_readings (
    id BIGSERIAL PRIMARY KEY,
    meter_id TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    first_total_flow DOUBLE PRECISION NOT NULL,
    last_total_flow DOUBLE PRECISION NOT NULL,
    interval_usage DOUBLE PRECISION NOT NULL,
    avg_instant_flow DOUBLE PRECISION,
    min_instant_flow DOUBLE PRECISION,
    max_instant_flow DOUBLE PRECISION,
    sample_count INTEGER NOT NULL,
    has_gap BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL DEFAULT 'valid',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (meter_id, window_start)
);

CREATE INDEX IF NOT EXISTS idx_interval_readings_meter_window
    ON interval_readings (meter_id, window_start DESC);

CREATE TABLE IF NOT EXISTS meter_status (
    meter_id TEXT PRIMARY KEY,
    last_device_ts TIMESTAMPTZ,
    last_received_ts TIMESTAMPTZ,
    instant_flow DOUBLE PRECISION,
    total_flow DOUBLE PRECISION,
    unit TEXT NOT NULL DEFAULT 'm3/h',
    online BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL DEFAULT 'unknown',
    anomaly_reason TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO meter_status (meter_id, status)
VALUES ('FM001', 'unknown'), ('FM002', 'unknown')
ON CONFLICT (meter_id) DO NOTHING;

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
);

CREATE INDEX IF NOT EXISTS idx_gateway_configs_enabled_priority
    ON gateway_configs (enabled, priority, id);

INSERT INTO gateway_configs (
    name, enabled, priority, topic_pattern, meter_id_path, meter_id_topic_index,
    device_ts_path, instant_flow_path, total_flow_path, unit_path, default_unit,
    instant_flow_scale, total_flow_scale, sample_payload, notes
)
VALUES (
    '标准 MQTT JSON', true, 100, 'meters/+/reading', 'meter_id', 1,
    'device_ts', 'instant_flow', 'total_flow', 'unit', 'm3/h',
    1, 1,
    '{"meter_id":"FM001","device_ts":"2026-05-20T10:15:00+08:00","instant_flow":12.34,"total_flow":56789.01,"unit":"m3/h"}',
    '默认配置，兼容当前模拟器和推荐网关 payload。'
)
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS runtime_settings (
    id BOOLEAN PRIMARY KEY DEFAULT true,
    clock_skew_seconds INTEGER NOT NULL,
    offline_after_seconds INTEGER NOT NULL,
    expected_interval_samples INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT runtime_settings_singleton CHECK (id = true)
);

INSERT INTO runtime_settings (
    id, clock_skew_seconds, offline_after_seconds, expected_interval_samples
)
VALUES (true, 120, 180, 10)
ON CONFLICT (id) DO NOTHING;
