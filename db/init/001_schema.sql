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
