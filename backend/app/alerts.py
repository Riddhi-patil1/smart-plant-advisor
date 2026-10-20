"""Alert lifecycle: create, update (de-duplicate), resolve, list and read-state.

Rules
* At most one *active* alert per (plant, alert_type); a database unique index enforces it.
* A continuing condition updates the existing alert instead of creating a duplicate.
* When the condition recovers the alert becomes 'resolved'. If the condition returns later,
  a brand new alert is created.
"""
from .constants import PARAMS, SENSORS
from .db import transaction, utc_now
from .errors import NotFoundError, ValidationError

SEVERITY_RANK = {"warning": 1, "critical": 2}
ALERT_TYPES = [f"{p}_{d}" for p in PARAMS for d in ("low", "high")]


def alert_type(parameter, direction):
    return f"{parameter}_{direction}"


def _present(classification, min_severity):
    sev = classification["severity"]
    return sev is not None and SEVERITY_RANK[sev] >= SEVERITY_RANK[min_severity]


def evaluate(conn, plant, reading_id, source, is_simulated, analysis, settings):
    """Apply the alert lifecycle for one analysed reading. Caller owns the transaction.

    Returns a list of events: {"event": created|updated|resolved|escalated, "alert_id", "alert_type"}.
    """
    now = utc_now()
    events = []
    classes = analysis["classifications"]
    recs = {r["rule_id"]: r for r in analysis["recommendations"]}
    active = {
        r["alert_type"]: r
        for r in conn.execute("SELECT * FROM alerts WHERE plant_id = ? AND status = 'active'", (plant["id"],))
    }

    present = {}
    for parameter in PARAMS:
        c = classes[parameter]
        if _present(c, settings["alert_min_severity"]):
            present[alert_type(parameter, c["direction"])] = (parameter, c)

    for atype in ALERT_TYPES:
        existing = active.get(atype)
        if atype in present:
            parameter, c = present[atype]
            rec = recs[f"{parameter}_{c['classification']}"]
            th = analysis["thresholds"][parameter]
            critical = c["severity"] == "critical"
            threshold = (th["crit_low"] if c["direction"] == "low" else th["crit_high"]) if critical else (
                th["warn_low"] if c["direction"] == "low" else th["warn_high"])
            fields = {
                "severity": c["severity"], "title": f"{SENSORS[parameter]['label']} {c['direction']}",
                "description": rec["message"], "explanation": rec["explanation"],
                "recommended_action": rec["actions"][0], "sensor_value": c["value"],
                "threshold_value": threshold, "threshold_kind": c["severity"],
            }
            if existing is None:
                cursor = conn.execute(
                    "INSERT INTO alerts (plant_id, alert_type, parameter, direction, severity, status, is_read, title, "
                    "description, explanation, recommended_action, sensor_value, threshold_value, threshold_kind, "
                    "reading_id, source, is_simulated, occurrence_count, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 'active', 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                    (plant["id"], atype, parameter, c["direction"], fields["severity"], fields["title"],
                     fields["description"], fields["explanation"], fields["recommended_action"],
                     fields["sensor_value"], fields["threshold_value"], fields["threshold_kind"],
                     reading_id, source, int(is_simulated), now, now),
                )
                events.append({"event": "created", "alert_id": cursor.lastrowid, "alert_type": atype})
            else:
                escalated = SEVERITY_RANK[fields["severity"]] > SEVERITY_RANK[existing["severity"]]
                conn.execute(
                    "UPDATE alerts SET severity = ?, title = ?, description = ?, explanation = ?, recommended_action = ?, "
                    "sensor_value = ?, threshold_value = ?, threshold_kind = ?, reading_id = ?, "
                    "occurrence_count = occurrence_count + 1, updated_at = ?, "
                    "is_read = CASE WHEN ? THEN 0 ELSE is_read END WHERE id = ?",
                    (fields["severity"], fields["title"], fields["description"], fields["explanation"],
                     fields["recommended_action"], fields["sensor_value"], fields["threshold_value"],
                     fields["threshold_kind"], reading_id, now, int(escalated), existing["id"]),
                )
                events.append({"event": "escalated" if escalated else "updated",
                               "alert_id": existing["id"], "alert_type": atype})
        elif existing is not None and settings["auto_resolve_alerts"]:
            conn.execute(
                "UPDATE alerts SET status = 'resolved', resolved_at = ?, updated_at = ? WHERE id = ?",
                (now, now, existing["id"]),
            )
            events.append({"event": "resolved", "alert_id": existing["id"], "alert_type": atype})
    return events


# ----------------------------------------------------------------------- queries
def _to_dict(row):
    d = dict(row)
    d["is_read"] = bool(d["is_read"])
    d["is_simulated"] = bool(d["is_simulated"])
    return d


def list_alerts(conn, plant_id=None, severity=None, status=None, is_read=None, start=None, end=None, limit=500):
    where, params = [], []
    if plant_id is not None:
        where.append("a.plant_id = ?")
        params.append(plant_id)
    if severity:
        if severity not in SEVERITY_RANK:
            raise ValidationError("Invalid severity.", {"severity": "Must be warning or critical."})
        where.append("a.severity = ?")
        params.append(severity)
    if status:
        if status not in ("active", "resolved"):
            raise ValidationError("Invalid status.", {"status": "Must be active or resolved."})
        where.append("a.status = ?")
        params.append(status)
    if is_read is not None:
        where.append("a.is_read = ?")
        params.append(1 if is_read else 0)
    if start:
        where.append("a.updated_at >= ?")
        params.append(start)
    if end:
        where.append("a.created_at <= ?")
        params.append(end)
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(
        f"SELECT a.*, p.name AS plant_name FROM alerts a JOIN plants p ON p.id = a.plant_id {clause} "
        f"ORDER BY a.updated_at DESC, a.id DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    return [_to_dict(r) for r in rows]


def get_alert(conn, alert_id):
    row = conn.execute(
        "SELECT a.*, p.name AS plant_name FROM alerts a JOIN plants p ON p.id = a.plant_id WHERE a.id = ?",
        (alert_id,),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Alert {alert_id} was not found.")
    return _to_dict(row)


def mark_read(conn, alert_id, is_read=True):
    get_alert(conn, alert_id)
    with transaction(conn):
        conn.execute("UPDATE alerts SET is_read = ? WHERE id = ?", (1 if is_read else 0, alert_id))
    return get_alert(conn, alert_id)


def mark_all_read(conn, plant_id=None):
    with transaction(conn):
        if plant_id is None:
            cur = conn.execute("UPDATE alerts SET is_read = 1 WHERE is_read = 0")
        else:
            cur = conn.execute("UPDATE alerts SET is_read = 1 WHERE is_read = 0 AND plant_id = ?", (plant_id,))
    return cur.rowcount


def resolve_manually(conn, alert_id):
    alert = get_alert(conn, alert_id)
    if alert["status"] == "resolved":
        return alert
    now = utc_now()
    with transaction(conn):
        conn.execute("UPDATE alerts SET status = 'resolved', resolved_at = ?, updated_at = ? WHERE id = ?",
                     (now, now, alert_id))
    return get_alert(conn, alert_id)


def counts(conn, plant_id=None):
    where, params = "", []
    if plant_id is not None:
        where, params = "WHERE plant_id = ?", [plant_id]
    row = conn.execute(
        f"SELECT "
        f"COALESCE(SUM(status='active' AND severity='warning'),0) AS active_warning, "
        f"COALESCE(SUM(status='active' AND severity='critical'),0) AS active_critical, "
        f"COALESCE(SUM(is_read=0),0) AS unread, COUNT(*) AS total FROM alerts {where}",
        params,
    ).fetchone()
    return {k: int(row[k]) for k in row.keys()}
