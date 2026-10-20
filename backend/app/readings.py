"""Sensor reading storage, history retrieval and trend calculation."""
import math

from .constants import PARAMS
from .errors import NotFoundError

# Changes smaller than this are reported as "stable".
TREND_BANDS = {"soil_moisture": 1.5, "temperature": 0.4, "humidity": 1.5, "light": 1.5}


def to_dict(row):
    d = dict(row)
    d["is_simulated"] = bool(d["is_simulated"])
    d["classes"] = {p: d.pop(f"class_{p}") for p in PARAMS}
    d["recommendation_ids"] = [r for r in d["recommendation_ids"].split(",") if r]
    return d


def insert(conn, plant_id, values, source, is_simulated, scenario, recorded_at, analysis):
    from .advisory import actionable_rule_ids

    classes = analysis["classifications"]
    cursor = conn.execute(
        "INSERT INTO sensor_readings (plant_id, recorded_at, soil_moisture, temperature, humidity, light, source, "
        "is_simulated, scenario, class_soil_moisture, class_temperature, class_humidity, class_light, "
        "health_status, recommendation_ids) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (plant_id, recorded_at, values["soil_moisture"], values["temperature"], values["humidity"], values["light"],
         source, int(is_simulated), scenario,
         classes["soil_moisture"]["classification"], classes["temperature"]["classification"],
         classes["humidity"]["classification"], classes["light"]["classification"],
         analysis["health"]["status"], ",".join(actionable_rule_ids(analysis["recommendations"]))),
    )
    return cursor.lastrowid


def latest(conn, plant_id):
    row = conn.execute(
        "SELECT * FROM sensor_readings WHERE plant_id = ? ORDER BY recorded_at DESC, id DESC LIMIT 1", (plant_id,)
    ).fetchone()
    return to_dict(row) if row else None


def get(conn, reading_id):
    row = conn.execute("SELECT * FROM sensor_readings WHERE id = ?", (reading_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Reading {reading_id} was not found.")
    return to_dict(row)


def count(conn, plant_id, start=None, end=None):
    sql, params = "SELECT COUNT(*) FROM sensor_readings WHERE plant_id = ?", [plant_id]
    if start:
        sql += " AND recorded_at >= ?"
        params.append(start)
    if end:
        sql += " AND recorded_at <= ?"
        params.append(end)
    return conn.execute(sql, params).fetchone()[0]


def history(conn, plant_id, start, end, max_points=600):
    """Readings in [start, end] oldest first. Large ranges are averaged into at most max_points buckets."""
    rows = conn.execute(
        "SELECT recorded_at, soil_moisture, temperature, humidity, light, scenario, health_status "
        "FROM sensor_readings WHERE plant_id = ? AND recorded_at >= ? AND recorded_at <= ? "
        "ORDER BY recorded_at ASC, id ASC LIMIT 500000",
        (plant_id, start, end),
    ).fetchall()
    total = len(rows)
    points = [dict(r) for r in rows]
    downsampled = False
    if total > max_points:
        downsampled = True
        size = math.ceil(total / max_points)
        merged = []
        for i in range(0, total, size):
            chunk = points[i:i + size]
            item = {"recorded_at": chunk[len(chunk) // 2]["recorded_at"], "scenario": chunk[-1]["scenario"],
                    "health_status": chunk[-1]["health_status"], "samples": len(chunk)}
            for p in PARAMS:
                item[p] = round(sum(c[p] for c in chunk) / len(chunk), 2)
            merged.append(item)
        points = merged
    return {"points": points, "count": total, "downsampled": downsampled}


def direction(delta, parameter):
    band = TREND_BANDS[parameter]
    if delta > band:
        return "rising"
    if delta < -band:
        return "falling"
    return "stable"


def trends(conn, plant_id, window):
    """Compare the latest reading with the mean of the previous `window` readings."""
    rows = conn.execute(
        "SELECT soil_moisture, temperature, humidity, light FROM sensor_readings WHERE plant_id = ? "
        "ORDER BY recorded_at DESC, id DESC LIMIT ?",
        (plant_id, window + 1),
    ).fetchall()
    result = {}
    for p in PARAMS:
        if len(rows) < 2:
            result[p] = {"direction": "insufficient_data", "delta": None, "compared_with": 0}
            continue
        prev = [r[p] for r in rows[1:]]
        delta = rows[0][p] - sum(prev) / len(prev)
        result[p] = {"direction": direction(delta, p), "delta": round(delta, 2), "compared_with": len(prev)}
    return result
