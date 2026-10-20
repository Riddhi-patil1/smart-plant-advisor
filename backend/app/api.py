"""REST routes and request parsing. Business logic lives in the other modules."""
import sqlite3

from flask import Blueprint, current_app, g, jsonify, request

from . import alerts, analytics, plants, readings, status
from . import settings as settings_store
from .advisory import ADVISORY_NOTE
from .constants import PROBLEM_KEYS, RANGE_PRESETS, SCENARIOS, SENSORS, SOURCES
from .db import connect, utc_now
from .errors import ApiError, ValidationError
from .ingestion import validate_values

bp = Blueprint("api", __name__, url_prefix="/api")
VERSION = "1.0.0"


# ----------------------------------------------------------------------- helpers
def db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def sim():
    return current_app.extensions["simulation"]


def ok(data, status_code=200):
    return jsonify({"data": data}), status_code


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object.", code="invalid_json")
    return data


def int_arg(name, required=False):
    raw = request.args.get(name)
    if raw is None or raw == "":
        if required:
            raise ValidationError("Missing query parameter.", {name: f"{name} is required."})
        return None
    try:
        return int(raw)
    except ValueError:
        raise ValidationError("Invalid query parameter.", {name: f"{name} must be an integer."})


def bool_arg(name):
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None
    if raw.lower() in ("1", "true", "yes"):
        return True
    if raw.lower() in ("0", "false", "no"):
        return False
    raise ValidationError("Invalid query parameter.", {name: f"{name} must be true or false."})


def period(default_from_settings=True):
    default = settings_store.get_all(db())["default_date_range"] if default_from_settings else "7d"
    return analytics.resolve_range(request.args.get("range"), request.args.get("from"), request.args.get("to"), default)


# ----------------------------------------------------------------------- meta
@bp.get("/health")
def health():
    db().execute("SELECT 1").fetchone()
    return ok({"status": "ok", "database": "ok", "version": VERSION, "time": utc_now(),
               "simulation_state": sim().status()["state"], "data_source": "simulator"})


@bp.get("/meta")
def meta():
    return ok({
        "sensors": {k: {"label": v["label"], "unit": v["unit"], "min": v["min"], "max": v["max"]} for k, v in SENSORS.items()},
        "scenarios": [{"key": k, **v} for k, v in SCENARIOS.items()],
        "problems": list(PROBLEM_KEYS),
        "sources": SOURCES,
        "range_presets": list(RANGE_PRESETS),
        "advisory_note": ADVISORY_NOTE,
        "version": VERSION,
    })


# ----------------------------------------------------------------------- plants
@bp.get("/plants")
def list_plants():
    return ok({"plants": plants.list_plants(db()), "active_plant_id": plants.get_active_plant_id(db())})


@bp.post("/plants")
def create_plant():
    return ok(plants.create_plant(db(), json_body()), 201)


@bp.get("/plants/active")
def get_active():
    plant_id = plants.get_active_plant_id(db())
    return ok({"active_plant_id": plant_id, "plant": plants.get_plant(db(), plant_id) if plant_id else None})


@bp.put("/plants/active")
def set_active():
    plant_id = plants.set_active_plant(db(), json_body().get("plant_id"))
    return ok({"active_plant_id": plant_id, "plant": plants.get_plant(db(), plant_id)})


@bp.get("/plants/<int:plant_id>")
def get_plant(plant_id):
    return ok(plants.get_plant(db(), plant_id))


@bp.put("/plants/<int:plant_id>")
def update_plant(plant_id):
    return ok(plants.update_plant(db(), plant_id, json_body()))


@bp.delete("/plants/<int:plant_id>")
def delete_plant(plant_id):
    return ok(plants.delete_plant(db(), plant_id))


# ----------------------------------------------------------------------- readings and status
@bp.get("/plants/<int:plant_id>/readings")
def plant_readings(plant_id):
    plants.get_plant(db(), plant_id)
    start, end, label = period()
    max_points = int_arg("max_points") or 600
    if not 10 <= max_points <= 5000:
        raise ValidationError("Invalid query parameter.", {"max_points": "Must be between 10 and 5000."})
    result = readings.history(db(), plant_id, start, end, max_points)
    result["range"] = {"from": start, "to": end, "label": label}
    result["data_source"] = "simulated"
    return ok(result)


@bp.get("/plants/<int:plant_id>/readings/latest")
def latest_reading(plant_id):
    plants.get_plant(db(), plant_id)
    return ok({"reading": readings.latest(db(), plant_id)})


@bp.get("/plants/<int:plant_id>/status")
def plant_status(plant_id):
    return ok(status.plant_status(db(), plant_id))


@bp.get("/plants/<int:plant_id>/recommendations")
def plant_recommendations(plant_id):
    s = status.plant_status(db(), plant_id)
    return ok({
        "plant_id": plant_id, "has_data": s["has_data"], "health": s["health"],
        "recommendations": s["recommendations"], "thresholds": s["thresholds"],
        "latest_reading": s["latest_reading"], "advisory_note": ADVISORY_NOTE,
    })


# ----------------------------------------------------------------------- simulation
@bp.get("/simulation")
def simulation_status():
    return ok(sim().status())


@bp.post("/simulation/start")
def simulation_start():
    return ok(sim().start())


@bp.post("/simulation/pause")
def simulation_pause():
    return ok(sim().pause())


@bp.post("/simulation/resume")
def simulation_resume():
    return ok(sim().resume())


@bp.post("/simulation/stop")
def simulation_stop():
    return ok(sim().stop())


@bp.post("/simulation/reset")
def simulation_reset():
    return ok(sim().reset())


@bp.post("/simulation/tick")
def simulation_tick():
    result = sim().generate_one()
    return ok({"reading": result["reading"], "health": result["analysis"]["health"],
               "alert_events": result["alert_events"], "simulation": sim().status()}, 201)


@bp.put("/simulation/scenario")
def simulation_scenario():
    data = json_body()
    custom = validate_values(data["values"]) if data.get("scenario") == "custom" and "values" in data else None
    return ok(sim().set_scenario(data.get("scenario"), data.get("problems"), custom))


@bp.put("/simulation/custom")
def simulation_custom():
    values = validate_values(json_body().get("values"))
    return ok(sim().set_scenario("custom", custom=values))


# ----------------------------------------------------------------------- alerts
@bp.get("/alerts")
def list_alerts():
    start = end = None
    if any(request.args.get(k) for k in ("range", "from", "to")):
        start, end, _ = period()
    plant_id = int_arg("plant_id")
    items = alerts.list_alerts(db(), plant_id, request.args.get("severity") or None,
                               request.args.get("status") or None, bool_arg("is_read"), start, end)
    return ok({"alerts": items, "counts": alerts.counts(db(), plant_id)})


@bp.get("/alerts/summary")
def alerts_summary():
    return ok(alerts.counts(db(), int_arg("plant_id")))


@bp.post("/alerts/read-all")
def alerts_read_all():
    return ok({"updated": alerts.mark_all_read(db(), int_arg("plant_id"))})


@bp.get("/alerts/<int:alert_id>")
def get_alert(alert_id):
    return ok(alerts.get_alert(db(), alert_id))


@bp.post("/alerts/<int:alert_id>/read")
def read_alert(alert_id):
    return ok(alerts.mark_read(db(), alert_id, True))


@bp.post("/alerts/<int:alert_id>/unread")
def unread_alert(alert_id):
    return ok(alerts.mark_read(db(), alert_id, False))


@bp.post("/alerts/<int:alert_id>/resolve")
def resolve_alert(alert_id):
    return ok(alerts.resolve_manually(db(), alert_id))


# ----------------------------------------------------------------------- analytics
@bp.get("/analytics/summary")
def analytics_summary():
    plant_id = int_arg("plant_id", required=True)
    plant = plants.get_plant(db(), plant_id)
    start, end, label = period()
    data = analytics.summary(db(), plant_id, start, end)
    data["range"]["label"] = label
    data["plant"] = {"id": plant["id"], "name": plant["name"]}
    return ok(data)


@bp.get("/analytics/report")
def analytics_report():
    plant_id = int_arg("plant_id", required=True)
    plant = plants.get_plant(db(), plant_id)
    start, end, label = period()
    return ok(analytics.build_report(db(), plant, start, end, label))


# ----------------------------------------------------------------------- settings
@bp.get("/settings")
def get_settings():
    return ok({"values": settings_store.get_all(db()), "defaults": settings_store.DEFAULTS,
               "schema": settings_store.SCHEMA})


@bp.put("/settings")
def put_settings():
    values = settings_store.update(db(), json_body())
    sim().set_interval(values["sampling_interval_seconds"])
    return ok({"values": values, "defaults": settings_store.DEFAULTS, "schema": settings_store.SCHEMA})


# ----------------------------------------------------------------------- errors
@bp.errorhandler(ApiError)
def handle_api_error(exc):
    return jsonify(exc.to_dict()), exc.status


@bp.errorhandler(sqlite3.Error)
def handle_db_error(exc):
    current_app.logger.exception("Database error")
    return jsonify({"error": {"code": "database_error",
                              "message": "The database could not complete the request. Please try again."}}), 503
