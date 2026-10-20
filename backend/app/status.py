"""Current plant status: latest reading analysed with the plant's *current* thresholds."""
from . import advisory, alerts, plants, readings
from . import settings as settings_store
from .constants import PARAMS


def plant_status(conn, plant_id):
    plant = plants.get_plant(conn, plant_id)
    settings = settings_store.get_all(conn)
    latest = readings.latest(conn, plant_id)
    result = {
        "plant": plant,
        "has_data": latest is not None,
        "latest_reading": latest,
        "thresholds": advisory.thresholds(plant, settings),
        "trends": readings.trends(conn, plant_id, settings["trend_window"]),
        "alert_counts": alerts.counts(conn, plant_id),
        "advisory_note": advisory.ADVISORY_NOTE,
        "data_source_note": "All values are simulated; they are not measurements from physical sensors.",
        "classifications": None,
        "health": None,
        "recommendations": [],
    }
    if latest:
        # Recomputed on every request so profile/threshold edits take effect immediately.
        analysis = advisory.analyze(plant, {p: latest[p] for p in PARAMS}, settings)
        result["classifications"] = analysis["classifications"]
        result["health"] = analysis["health"]
        result["recommendations"] = analysis["recommendations"]
    return result
