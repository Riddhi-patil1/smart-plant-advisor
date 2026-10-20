"""Plant profile management (CRUD and active-plant selection)."""
import re
import sqlite3
from datetime import date, datetime

from . import settings as settings_store
from .constants import SENSORS
from .db import transaction, utc_now
from .errors import ConflictError, NotFoundError, ValidationError, read_number, read_text

TEXT_FIELDS = ("name", "species", "image_url", "planting_date", "description", "watering_guidance", "care_notes")
NUMBER_FIELDS = (
    "moisture_min", "moisture_max", "moisture_warning",
    "temperature_min", "temperature_max", "temperature_warning",
    "humidity_min", "humidity_max", "light_min", "light_max",
)
EDITABLE = TEXT_FIELDS + NUMBER_FIELDS
URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


def validate_plant(data):
    """Validate a complete plant payload and return cleaned values."""
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.")
    errors = {}
    clean = {
        "name": read_text(data, "name", errors, "Name", 80, required=True),
        "species": read_text(data, "species", errors, "Species", 120),
        "description": read_text(data, "description", errors, "Description", 1000),
        "watering_guidance": read_text(data, "watering_guidance", errors, "Watering guidance", 1000),
        "care_notes": read_text(data, "care_notes", errors, "Care notes", 1000),
    }

    image = read_text(data, "image_url", errors, "Image URL", 500)
    if image and not URL_RE.match(image):
        errors["image_url"] = "Image URL must start with http:// or https://."
    clean["image_url"] = image or None

    planted = read_text(data, "planting_date", errors, "Planting date", 10)
    if planted:
        try:
            parsed = datetime.strptime(planted, "%Y-%m-%d").date()
            if parsed > date.today():
                errors["planting_date"] = "Planting date cannot be in the future."
        except ValueError:
            errors["planting_date"] = "Planting date must be a valid date (YYYY-MM-DD)."
    clean["planting_date"] = planted or None

    for sensor in SENSORS.values():
        prefix, lo, hi, label = sensor["prefix"], sensor["min"], sensor["max"], sensor["label"]
        low = read_number(data, f"{prefix}_min", errors, f"{label} minimum", lo, hi)
        high = read_number(data, f"{prefix}_max", errors, f"{label} maximum", lo, hi)
        clean[f"{prefix}_min"], clean[f"{prefix}_max"] = low, high
        if low is not None and high is not None and low >= high:
            errors[f"{prefix}_max"] = f"{label} maximum must be greater than the minimum."

    # Warning thresholds are optional and default to the preferred bounds.
    low, high = clean["moisture_min"], clean["moisture_max"]
    warn = read_number(data, "moisture_warning", errors, "Soil moisture warning threshold", 0, 100,
                       default=low)
    if warn is not None and low is not None and warn > low:
        errors["moisture_warning"] = "Warning threshold must not exceed the preferred minimum."
    clean["moisture_warning"] = warn

    low, high = clean["temperature_min"], clean["temperature_max"]
    warn = read_number(data, "temperature_warning", errors, "Temperature warning threshold",
                       SENSORS["temperature"]["min"], SENSORS["temperature"]["max"], default=high)
    if warn is not None and high is not None and warn < high:
        errors["temperature_warning"] = "Warning threshold must not be below the preferred maximum."
    clean["temperature_warning"] = warn

    if errors:
        raise ValidationError("The plant profile has invalid fields.", errors)
    return clean


def _row(row):
    return dict(row) if row else None


def list_plants(conn):
    rows = conn.execute(
        "SELECT p.*, (SELECT COUNT(*) FROM sensor_readings r WHERE r.plant_id = p.id) AS reading_count, "
        "(SELECT COUNT(*) FROM alerts a WHERE a.plant_id = p.id AND a.status = 'active') AS active_alert_count "
        "FROM plants p ORDER BY p.name COLLATE NOCASE"
    ).fetchall()
    return [dict(r) for r in rows]


def get_plant(conn, plant_id):
    row = conn.execute(
        "SELECT p.*, (SELECT COUNT(*) FROM sensor_readings r WHERE r.plant_id = p.id) AS reading_count, "
        "(SELECT COUNT(*) FROM alerts a WHERE a.plant_id = p.id) AS alert_count "
        "FROM plants p WHERE p.id = ?",
        (plant_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Plant {plant_id} was not found.")
    return dict(row)


def _insert(conn, clean, now):
    columns = ", ".join(EDITABLE)
    marks = ", ".join("?" for _ in EDITABLE)
    cursor = conn.execute(
        f"INSERT INTO plants ({columns}, created_at, updated_at) VALUES ({marks}, ?, ?)",
        [clean[f] for f in EDITABLE] + [now, now],
    )
    return cursor.lastrowid


def create_plant(conn, data):
    clean = validate_plant(data)
    now = utc_now()
    try:
        with transaction(conn):
            plant_id = _insert(conn, clean, now)
            if get_active_plant_id(conn) is None:
                settings_store.set_raw(conn, "active_plant_id", plant_id)
    except sqlite3.IntegrityError as exc:
        raise _integrity_error(exc)
    return get_plant(conn, plant_id)


def update_plant(conn, plant_id, data):
    """Full update. Missing fields keep their stored value. Alerts are re-evaluated afterwards."""
    from . import ingestion  # local import avoids a circular dependency

    existing = get_plant(conn, plant_id)
    if not isinstance(data, dict):
        raise ValidationError("Request body must be a JSON object.")
    merged = {f: existing[f] for f in EDITABLE}
    merged.update({k: v for k, v in data.items() if k in EDITABLE})
    clean = validate_plant(merged)
    assignments = ", ".join(f"{f} = ?" for f in EDITABLE)
    try:
        with transaction(conn):
            conn.execute(
                f"UPDATE plants SET {assignments}, updated_at = ? WHERE id = ?",
                [clean[f] for f in EDITABLE] + [utc_now(), plant_id],
            )
            # Thresholds may have changed: recalculate alert state from the latest reading.
            ingestion.reevaluate_plant(conn, plant_id)
    except sqlite3.IntegrityError as exc:
        raise _integrity_error(exc)
    return get_plant(conn, plant_id)


def delete_plant(conn, plant_id):
    """Delete a plant and (via ON DELETE CASCADE) its readings and alerts, atomically."""
    plant = get_plant(conn, plant_id)
    with transaction(conn):
        alerts_removed = conn.execute("SELECT COUNT(*) FROM alerts WHERE plant_id = ?", (plant_id,)).fetchone()[0]
        conn.execute("DELETE FROM plants WHERE id = ?", (plant_id,))
        active = settings_store.get_raw(conn, "active_plant_id")
        if active == plant_id:
            nxt = conn.execute("SELECT id FROM plants ORDER BY name COLLATE NOCASE LIMIT 1").fetchone()
            if nxt:
                settings_store.set_raw(conn, "active_plant_id", nxt["id"])
            else:
                conn.execute("DELETE FROM app_settings WHERE key = 'active_plant_id'")
    return {
        "deleted_id": plant_id,
        "readings_removed": plant["reading_count"],
        "alerts_removed": alerts_removed,
        "active_plant_id": get_active_plant_id(conn),
    }


def get_active_plant_id(conn):
    plant_id = settings_store.get_raw(conn, "active_plant_id")
    if plant_id is None:
        return None
    row = conn.execute("SELECT id FROM plants WHERE id = ?", (plant_id,)).fetchone()
    return row["id"] if row else None


def set_active_plant(conn, plant_id):
    if isinstance(plant_id, bool) or not isinstance(plant_id, int):
        raise ValidationError("plant_id must be an integer.", {"plant_id": "Must be an integer."})
    get_plant(conn, plant_id)
    with transaction(conn):
        settings_store.set_raw(conn, "active_plant_id", plant_id)
    return plant_id


def _integrity_error(exc):
    if "plants.name" in str(exc) or "UNIQUE" in str(exc):
        return ConflictError("A plant with this name already exists.",
                             {"name": "A plant with this name already exists."})
    return ValidationError("The plant could not be saved: " + str(exc))
