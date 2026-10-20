"""Persistent global application settings (key/value rows in app_settings).

Global settings never modify plant profiles. Plant thresholds live on the plant.
"""
import json

from .constants import RANGE_PRESETS
from .db import transaction, utc_now
from .errors import ValidationError, to_number

# type: number | int | bool | choice | text
SCHEMA = {
    "sampling_interval_seconds": {"type": "number", "min": 1, "max": 3600, "default": 5,
                                  "label": "Simulation sampling interval (seconds)"},
    "critical_margin_soil_moisture": {"type": "number", "min": 1, "max": 50, "default": 15,
                                      "label": "Soil moisture critical margin (% beyond the warning threshold)"},
    "critical_margin_temperature": {"type": "number", "min": 1, "max": 30, "default": 5,
                                    "label": "Temperature critical margin (°C beyond the warning threshold)"},
    "critical_margin_humidity": {"type": "number", "min": 1, "max": 50, "default": 15,
                                 "label": "Humidity critical margin (% beyond the warning threshold)"},
    "critical_margin_light": {"type": "number", "min": 1, "max": 50, "default": 20,
                              "label": "Light critical margin (% beyond the warning threshold)"},
    "trend_window": {"type": "int", "min": 2, "max": 50, "default": 5,
                     "label": "Trend window (previous readings compared with the latest)"},
    "alert_min_severity": {"type": "choice", "choices": ["warning", "critical"], "default": "warning",
                           "label": "Lowest severity that raises an alert"},
    "auto_resolve_alerts": {"type": "bool", "default": True, "label": "Resolve alerts automatically on recovery"},
    "default_date_range": {"type": "choice", "choices": list(RANGE_PRESETS), "default": "7d",
                           "label": "Default date range"},
    "display_name": {"type": "text", "max": 40, "default": "Demo user", "label": "Demo profile name"},
    "time_format": {"type": "choice", "choices": ["24h", "12h"], "default": "24h", "label": "Clock format"},
}

DEFAULTS = {key: spec["default"] for key, spec in SCHEMA.items()}


def get_all(conn):
    values = dict(DEFAULTS)
    for row in conn.execute("SELECT key, value FROM app_settings"):
        if row["key"] in SCHEMA:
            try:
                values[row["key"]] = json.loads(row["value"])
            except ValueError:
                pass
    return values


def validate(data):
    if not isinstance(data, dict):
        raise ValidationError("Settings must be a JSON object.")
    errors, clean = {}, {}
    for key, raw in data.items():
        spec = SCHEMA.get(key)
        if spec is None:
            errors[key] = "Unknown setting."
            continue
        kind = spec["type"]
        if kind in ("number", "int"):
            number = to_number(raw)
            if number is None:
                errors[key] = "Must be a number."
            elif kind == "int" and number != int(number):
                errors[key] = "Must be a whole number."
            elif number < spec["min"] or number > spec["max"]:
                errors[key] = f"Must be between {spec['min']} and {spec['max']}."
            else:
                clean[key] = int(number) if kind == "int" else number
        elif kind == "bool":
            if isinstance(raw, bool):
                clean[key] = raw
            else:
                errors[key] = "Must be true or false."
        elif kind == "choice":
            if raw in spec["choices"]:
                clean[key] = raw
            else:
                errors[key] = "Must be one of: " + ", ".join(spec["choices"]) + "."
        else:  # text
            if not isinstance(raw, str) or not raw.strip():
                errors[key] = "Must be non-empty text."
            elif len(raw.strip()) > spec["max"]:
                errors[key] = f"Must be {spec['max']} characters or fewer."
            else:
                clean[key] = raw.strip()
    if errors:
        raise ValidationError("Some settings are invalid.", errors)
    return clean


def update(conn, data):
    clean = validate(data)
    now = utc_now()
    with transaction(conn):
        for key, value in clean.items():
            conn.execute(
                "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (key, json.dumps(value), now),
            )
    return get_all(conn)


def get_raw(conn, key, default=None):
    row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_raw(conn, key, value):
    """Write an internal key (e.g. active_plant_id). Caller controls the transaction."""
    conn.execute(
        "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, json.dumps(value), utc_now()),
    )
