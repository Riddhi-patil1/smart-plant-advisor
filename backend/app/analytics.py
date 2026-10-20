"""Date-range handling, historical summaries and the generated report."""
from datetime import datetime, timedelta, timezone

from . import readings
from .advisory import RULE_CATALOG
from .constants import PARAMS, RANGE_PRESETS, SENSORS
from .db import to_iso, utc_now
from .errors import ValidationError

MAX_SPAN_DAYS = 366
CLASS_CODES = ("critical_low", "low", "normal", "high", "critical_high")


# ----------------------------------------------------------------------- ranges
def _parse_bound(text, field, end):
    if not isinstance(text, str) or not text.strip():
        raise ValidationError("Invalid date range.", {field: "Provide a date (YYYY-MM-DD) or an ISO timestamp."})
    text = text.strip()
    try:
        if len(text) == 10:
            local = datetime.strptime(text, "%Y-%m-%d")  # naive -> interpreted in the server's local zone
            if end:
                local = local + timedelta(days=1) - timedelta(milliseconds=1)
            return local.astimezone(timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.astimezone().astimezone(timezone.utc)
    except ValueError:
        raise ValidationError("Invalid date range.", {field: "Not a valid date or ISO timestamp."})


def resolve_range(range_key=None, date_from=None, date_to=None, default="7d"):
    """Return (start_iso, end_iso, label). Custom from/to override presets."""
    now = datetime.now(timezone.utc)
    if date_from or date_to:
        if not date_from:
            raise ValidationError("Invalid date range.", {"from": "A start date is required for a custom range."})
        start = _parse_bound(date_from, "from", end=False)
        end = _parse_bound(date_to, "to", end=True) if date_to else now
        if start > end:
            raise ValidationError("Invalid date range.", {"from": "Start must not be after the end date.",
                                                           "to": "End must not be before the start date."})
        if end - start > timedelta(days=MAX_SPAN_DAYS):
            raise ValidationError("Date range is too long.", {"to": f"Choose a range of at most {MAX_SPAN_DAYS} days."})
        return to_iso(start), to_iso(end), "custom"
    key = range_key or default
    if key not in RANGE_PRESETS:
        raise ValidationError("Invalid date range.", {"range": "Must be one of: " + ", ".join(RANGE_PRESETS) + "."})
    if key == "today":
        start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    elif key == "7d":
        start = now - timedelta(days=7)
    else:
        start = now - timedelta(days=30)
    return to_iso(start), to_iso(now), key


# ----------------------------------------------------------------------- summary
def _sensor_stats(conn, plant_id, start, end):
    cols = []
    for p in PARAMS:
        cols += [f"MIN({p}) AS {p}_min", f"MAX({p}) AS {p}_max", f"AVG({p}) AS {p}_avg"]
    row = conn.execute(
        f"SELECT COUNT(*) AS n, {', '.join(cols)} FROM sensor_readings "
        "WHERE plant_id = ? AND recorded_at >= ? AND recorded_at <= ?",
        (plant_id, start, end),
    ).fetchone()
    n = row["n"]
    stats = {}
    for p in PARAMS:
        entry = {"label": SENSORS[p]["label"], "unit": SENSORS[p]["unit"], "count": n}
        if n:
            entry.update(min=round(row[f"{p}_min"], 2), max=round(row[f"{p}_max"], 2), avg=round(row[f"{p}_avg"], 2))
            entry.update(_period_trend(conn, plant_id, start, end, p, n))
        else:
            entry.update(min=None, max=None, avg=None, trend="no_data", change=None)
        stats[p] = entry
    return n, stats


def _period_trend(conn, plant_id, start, end, parameter, n):
    """Compare the mean of the first and last fifth of the period (at least one reading each)."""
    k = max(1, min(n // 5, 500))
    base = ("SELECT AVG(v) FROM (SELECT {p} AS v FROM sensor_readings WHERE plant_id = ? AND recorded_at >= ? "
            "AND recorded_at <= ? ORDER BY recorded_at {o}, id {o} LIMIT ?)")
    args = (plant_id, start, end, k)
    first = conn.execute(base.format(p=parameter, o="ASC"), args).fetchone()[0]
    last = conn.execute(base.format(p=parameter, o="DESC"), args).fetchone()[0]
    if n < 2:
        return {"trend": "insufficient_data", "change": None}
    change = round(last - first, 2)
    return {"trend": readings.direction(change, parameter), "change": change}


def summary(conn, plant_id, start, end):
    n, stats = _sensor_stats(conn, plant_id, start, end)

    conditions = {}
    for p in PARAMS:
        counts = {c: 0 for c in CLASS_CODES}
        for r in conn.execute(
            f"SELECT class_{p} AS c, COUNT(*) AS n FROM sensor_readings WHERE plant_id = ? AND recorded_at >= ? "
            f"AND recorded_at <= ? GROUP BY class_{p}", (plant_id, start, end)):
            counts[r["c"]] = r["n"]
        conditions[p] = counts

    health = {"healthy": 0, "needs_attention": 0, "critical": 0}
    for r in conn.execute(
        "SELECT health_status AS s, COUNT(*) AS n FROM sensor_readings WHERE plant_id = ? AND recorded_at >= ? "
        "AND recorded_at <= ? GROUP BY health_status", (plant_id, start, end)):
        health[r["s"]] = r["n"]

    rule_counts = {}
    for r in conn.execute(
        "SELECT recommendation_ids AS ids, COUNT(*) AS n FROM sensor_readings WHERE plant_id = ? AND recorded_at >= ? "
        "AND recorded_at <= ? AND recommendation_ids != '' GROUP BY recommendation_ids", (plant_id, start, end)):
        for rid in r["ids"].split(","):
            if rid:
                rule_counts[rid] = rule_counts.get(rid, 0) + r["n"]
    recs = [
        {"rule_id": rid, "title": RULE_CATALOG.get(rid, {}).get("title", rid),
         "category": RULE_CATALOG.get(rid, {}).get("category", "environment"), "readings": cnt,
         "share_of_readings": round(cnt / n, 3) if n else 0}
        for rid, cnt in sorted(rule_counts.items(), key=lambda kv: -kv[1])
    ]

    alert_rows = conn.execute(
        "SELECT severity, status, alert_type, substr(created_at, 1, 10) AS day FROM alerts "
        "WHERE plant_id = ? AND created_at >= ? AND created_at <= ?", (plant_id, start, end)).fetchall()
    by_severity, by_type, by_day = {"warning": 0, "critical": 0}, {}, {}
    for a in alert_rows:
        by_severity[a["severity"]] += 1
        by_type[a["alert_type"]] = by_type.get(a["alert_type"], 0) + 1
        by_day[a["day"]] = by_day.get(a["day"], 0) + 1
    alert_summary = {
        "total": len(alert_rows), "by_severity": by_severity, "by_type": by_type,
        "active": sum(1 for a in alert_rows if a["status"] == "active"),
        "resolved": sum(1 for a in alert_rows if a["status"] == "resolved"),
        "by_day_utc": [{"date": d, "count": c} for d, c in sorted(by_day.items())],
    }
    scenarios = [dict(r) for r in conn.execute(
        "SELECT COALESCE(scenario, 'unknown') AS scenario, COUNT(*) AS readings FROM sensor_readings "
        "WHERE plant_id = ? AND recorded_at >= ? AND recorded_at <= ? GROUP BY scenario ORDER BY readings DESC",
        (plant_id, start, end))]
    return {
        "range": {"from": start, "to": end}, "reading_count": n, "has_data": n > 0, "sensors": stats,
        "conditions": conditions, "health": health, "recommendations": recs, "alerts": alert_summary,
        "scenarios": scenarios, "data_source": "simulated",
    }


# ----------------------------------------------------------------------- report
def _pct(part, total):
    return f"{(100.0 * part / total):.0f}%" if total else "0%"


def build_report(conn, plant, start, end, label):
    s = summary(conn, plant["id"], start, end)
    n = s["reading_count"]
    sections = []
    header = [f"Plant: {plant['name']} ({plant['species'] or 'species not set'})",
              f"Period: {start} to {end} (UTC, {label})",
              "Data source: SIMULATED sensor data. No physical sensors were used.",
              f"Readings analysed: {n}"]
    sections.append({"heading": "Overview", "lines": header})
    if n == 0:
        sections.append({"heading": "No data", "lines": ["No simulated readings exist for this plant in the selected period."]})
    else:
        lines = []
        for p, st in s["sensors"].items():
            change = "" if st["change"] is None else f", change over period {st['change']:+g}"
            lines.append(f"{st['label']}: min {st['min']:g}, max {st['max']:g}, average {st['avg']:g} {st['unit']}; "
                         f"trend {st['trend'].replace('_', ' ')}{change}.")
        sections.append({"heading": "Environmental trends", "lines": lines})
        cond = []
        for p in PARAMS:
            c = s["conditions"][p]
            cond.append(f"{SENSORS[p]['label']}: " + ", ".join(
                f"{code.replace('_', ' ')} {_pct(c[code], n)}" for code in CLASS_CODES if c[code]))
        h = s["health"]
        cond.append(f"Overall health: healthy {_pct(h['healthy'], n)}, needs attention {_pct(h['needs_attention'], n)}, "
                    f"critical {_pct(h['critical'], n)} of readings.")
        sections.append({"heading": "Condition classifications", "lines": cond})
        a = s["alerts"]
        sections.append({"heading": "Alerts", "lines": [
            f"{a['total']} alert(s) raised: {a['by_severity']['warning']} warning, {a['by_severity']['critical']} critical; "
            f"{a['active']} still active, {a['resolved']} resolved."] +
            [f"{k.replace('_', ' ')}: {v}" for k, v in sorted(a["by_type"].items())]})
        rec_lines = [f"{r['title']} ({r['category']}): triggered by {r['readings']} reading(s), {_pct(r['readings'], n)}"
                     for r in s["recommendations"]] or ["No watering or environmental actions were triggered."]
        sections.append({"heading": "Recommendations", "lines": rec_lines})
    sections.append({"heading": "Notes", "lines": [
        "Recommendations are advisory, rule-based suggestions using editable plant thresholds.",
        "Simulated values must not be treated as real-world sensor measurements."]})
    md = [f"# Plant condition report: {plant['name']}", ""]
    for sec in sections:
        md += [f"## {sec['heading']}", ""] + [f"- {line}" for line in sec["lines"]] + [""]
    return {
        "title": f"Plant condition report: {plant['name']}", "generated_at": utc_now(), "data_source": "simulated",
        "plant": {"id": plant["id"], "name": plant["name"], "species": plant["species"]},
        "range": {"from": start, "to": end, "label": label}, "sections": sections, "markdown": "\n".join(md),
    }
