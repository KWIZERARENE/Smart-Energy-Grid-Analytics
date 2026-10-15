-- Meter metadata (from meter_metadata())
CREATE TABLE IF NOT EXISTS meters (
    meter_id        BIGINT PRIMARY KEY,
    region          TEXT NOT NULL,
    customer_type   TEXT NOT NULL,
    base_power_kw   DOUBLE PRECISION,
    power_factor    DOUBLE PRECISION
);

-- Pilot landing table: plain table, duplicates allowed
CREATE TABLE IF NOT EXISTS energy_live (
    meter_id        BIGINT,
    event_time      TIMESTAMPTZ,
    received_time   TIMESTAMPTZ,
    power_kw        DOUBLE PRECISION,
    voltage_v       DOUBLE PRECISION,
    current_a       DOUBLE PRECISION,
    frequency_hz    DOUBLE PRECISION,
    energy_kwh      DOUBLE PRECISION
);

-- Main table: hypertable with 1-day chunks, duplicates allowed (no PK/unique)
CREATE TABLE IF NOT EXISTS energy_readings (
    meter_id        BIGINT,
    event_time      TIMESTAMPTZ NOT NULL,
    received_time   TIMESTAMPTZ,
    power_kw        DOUBLE PRECISION,
    voltage_v       DOUBLE PRECISION,
    current_a       DOUBLE PRECISION,
    frequency_hz    DOUBLE PRECISION,
    energy_kwh      DOUBLE PRECISION
);

SELECT create_hypertable(
    'energy_readings',
    'event_time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);


SELECT count(*) FROM meters;
SELECT region, count(*) FROM meters GROUP BY region ORDER BY 1;
SELECT customer_type, count(*) FROM meters GROUP BY customer_type ORDER BY 1;
SELECT * FROM meters ORDER BY meter_id LIMIT 5;