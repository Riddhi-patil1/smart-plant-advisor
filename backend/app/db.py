"""SQLite access: connections, transactions, schema and timestamps."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS plants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(name)) BETWEEN 1 AND 80),
    species TEXT NOT NULL DEFAULT '',
    image_url TEXT,
    planting_date TEXT,
    description TEXT NOT NULL DEFAULT '',
    moisture_min REAL NOT NULL,
    moisture_max REAL NOT NULL,
    moisture_warning REAL NOT NULL,
    temperature_min REAL NOT NULL,
    temperature_max REAL NOT NULL,
    temperature_warning REAL NOT NULL,
    humidity_min REAL NOT NULL,
    humidity_max REAL NOT NULL,
    light_min REAL NOT NULL,
    light_max REAL NOT NULL,
    watering_guidance TEXT NOT NULL DEFAULT '',
    care_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (moisture_min >= 0 AND moisture_max <= 100 AND moisture_min < moisture_max),
    CHECK (moisture_warning >= 0 AND moisture_warning <= moisture_min),
    CHECK (temperature_min >= -10 AND temperature_max <= 60 AND temperature_min < temperature_max),
    CHECK (temperature_warning >= temperature_max AND temperature_warning <= 60),
    CHECK (humidity_min >= 0 AND humidity_max <= 100 AND humidity_min < humidity_max),
    CHECK (light_min >= 0 AND light_max <= 100 AND light_min < light_max)
);

CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id INTEGER NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
    recorded_at TEXT NOT NULL,
    soil_moisture REAL NOT NULL CHECK (soil_moisture BETWEEN 0 AND 100),
    temperature REAL NOT NULL CHECK (temperature BETWEEN -10 AND 60),
    humidity REAL NOT NULL CHECK (humidity BETWEEN 0 AND 100),
    light REAL NOT NULL CHECK (light BETWEEN 0 AND 100),
    source TEXT NOT NULL CHECK (source IN ('simulator', 'esp32')),
    is_simulated INTEGER NOT NULL CHECK (is_simulated IN (0, 1)),
    scenario TEXT,
    class_soil_moisture TEXT NOT NULL,
    class_temperature TEXT NOT NULL,
    class_humidity TEXT NOT NULL,
    class_light TEXT NOT NULL,
    health_status TEXT NOT NULL CHECK (health_status IN ('healthy', 'needs_attention', 'critical')),
    recommendation_ids TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_readings_plant_time ON sensor_readings (plant_id, recorded_at);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id INTEGER NOT NULL REFERENCES plants(id) ON DELETE CASCADE,
    alert_type TEXT NOT NULL,
    parameter TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('low', 'high')),
    severity TEXT NOT NULL CHECK (severity IN ('warning', 'critical')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'resolved')),
    is_read INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1)),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    explanation TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    sensor_value REAL NOT NULL,
    threshold_value REAL NOT NULL,
    threshold_kind TEXT NOT NULL CHECK (threshold_kind IN ('warning', 'critical')),
    reading_id INTEGER REFERENCES sensor_readings(id) ON DELETE SET NULL,
    source TEXT NOT NULL DEFAULT 'simulator',
    is_simulated INTEGER NOT NULL DEFAULT 1 CHECK (is_simulated IN (0, 1)),
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    resolved_at TEXT
);
-- At most one active alert per plant and condition: the database enforces de-duplication.
CREATE UNIQUE INDEX IF NOT EXISTS uq_alerts_active ON alerts (plant_id, alert_type) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_alerts_plant_status ON alerts (plant_id, status);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts (created_at);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS simulation_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state TEXT NOT NULL DEFAULT 'stopped' CHECK (state IN ('stopped', 'running', 'paused')),
    scenario TEXT NOT NULL DEFAULT 'normal',
    problems TEXT NOT NULL DEFAULT '["dry_soil","low_humidity"]',
    custom_values TEXT,
    tick_count INTEGER NOT NULL DEFAULT 0,
    last_reading_at TEXT,
    updated_at TEXT NOT NULL
);
"""


def utc_now():
    """ISO-8601 UTC timestamp with millisecond precision, e.g. 2026-01-01T10:00:00.000Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def to_iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def connect(path):
    """Open a connection in autocommit mode; use transaction() for writes."""
    conn = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


@contextmanager
def transaction(conn):
    """BEGIN IMMEDIATE ... COMMIT, rolling back on any error."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def init_db(path):
    """Create the database file and tables (idempotent)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO simulation_state (id, updated_at) VALUES (1, ?)", (utc_now(),)
        )
    finally:
        conn.close()
