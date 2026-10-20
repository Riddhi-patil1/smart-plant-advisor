"""The single ingestion entry point for sensor data.

Every data source goes through ``ingest_reading``: the simulator today, and an ESP32 in the
future. The function validates the values, analyses them against the plant's thresholds,
stores the reading, and runs the alert lifecycle in one transaction. Nothing downstream
(dashboard, analytics, advisory engine) cares which source produced the data; the source is
recorded on every reading and alert via ``source`` / ``is_simulated``.

Future ESP32 integration: a device-facing endpoint would authenticate the device, then call
``ingest_reading(conn, plant_id, values, source="esp32", scenario=None)``. Only the
``SOURCES`` registry (constants.py) and the HTTP layer need to change.
"""
import math

from . import advisory, alerts, readings
from . import settings as settings_store
from .constants import PARAMS, SENSORS, SOURCES
from .db import transaction, utc_now
from .errors import NotFoundError, ValidationError, to_number


def validate_values(values):
    """Return a clean {sensor: float} dict, or raise ValidationError with per-field messages."""
    if not isinstance(values, dict):
        raise ValidationError("Sensor values must be a JSON object.")
    errors, clean = {}, {}
    for parameter, meta in SENSORS.items():
        raw = values.get(parameter)
        if raw is None or raw == "":
            errors[parameter] = f"{meta['label']} is required."
            continue
        number = to_number(raw)
        if number is None or not math.isfinite(number):
            errors[parameter] = f"{meta['label']} must be a number."
        elif number < meta["min"] or number > meta["max"]:
            errors[parameter] = f"{meta['label']} must be between {meta['min']:g} and {meta['max']:g} {meta['unit']}."
        else:
            clean[parameter] = round(number, 2)
    unknown = [k for k in values if k not in SENSORS]
    for key in unknown:
        errors[key] = "Unknown sensor."
    if errors:
        raise ValidationError("Invalid sensor values.", errors)
    return clean


def _load_plant(conn, plant_id):
    row = conn.execute("SELECT * FROM plants WHERE id = ?", (plant_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Plant {plant_id} was not found.")
    return dict(row)


def ingest_reading(conn, plant_id, values, source="simulator", scenario=None, recorded_at=None):
    if source not in SOURCES:
        raise ValidationError("Unknown data source.", {"source": f"Must be one of: {', '.join(SOURCES)}."})
    clean = validate_values(values)
    plant = _load_plant(conn, plant_id)
    settings = settings_store.get_all(conn)
    analysis = advisory.analyze(plant, clean, settings)
    is_simulated = SOURCES[source]["is_simulated"]
    with transaction(conn):
        reading_id = readings.insert(conn, plant_id, clean, source, is_simulated, scenario,
                                     recorded_at or utc_now(), analysis)
        events = alerts.evaluate(conn, plant, reading_id, source, is_simulated, analysis, settings)
    return {"reading": readings.get(conn, reading_id), "analysis": analysis, "alert_events": events}


def reevaluate_plant(conn, plant_id):
    """Recompute alert state from the latest reading after a profile change.

    Caller owns the transaction. The stored reading is left untouched (history is preserved);
    only the alert lifecycle follows the plant's new thresholds.
    """
    latest = readings.latest(conn, plant_id)
    if latest is None:
        return []
    plant = _load_plant(conn, plant_id)
    settings = settings_store.get_all(conn)
    values = {p: latest[p] for p in PARAMS}
    analysis = advisory.analyze(plant, values, settings)
    return alerts.evaluate(conn, plant, latest["id"], latest["source"], latest["is_simulated"], analysis, settings)
