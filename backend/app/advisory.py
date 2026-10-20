"""Rule-based plant condition analysis and advisory engine.

Pure functions only (no database access) so every rule can be unit-tested.

Threshold model for each sensor, ordered low to high:

    crit_low < warn_low <= pref_min <= pref_max <= warn_high < crit_high

* Preferred range  : the plant's configured comfortable range.
* Warning bounds   : value beyond which the condition is "Low"/"High" (warning severity).
  For soil moisture the lower warning bound is the plant's moisture_warning; for
  temperature the upper warning bound is the plant's temperature_warning. For humidity and
  light the warning bounds are the preferred min/max.
* Critical bounds  : warning bound plus a global margin from Settings ("Critical").

Everything here is advisory. Watering is never recommended from a timer, only from the
soil-moisture reading compared with the selected plant's configured thresholds.
"""
from .constants import PARAMS, SENSORS

ADVISORY_NOTE = (
    "Advisory only: these suggestions come from transparent rules applied to simulated readings "
    "and editable plant thresholds. They are not a guaranteed plant-health diagnosis."
)

SHORT_UNIT = {"soil_moisture": "%", "temperature": "°C", "humidity": "%", "light": "%"}
LABELS = {
    "critical_low": "Critical", "critical_high": "Critical", "low": "Low", "high": "High", "normal": "Normal",
}

# (parameter, classification) -> (category, title). Single source for the rule catalogue.
RULE_TITLES = {
    ("soil_moisture", "critical_low"): ("watering", "Urgent watering recommended"),
    ("soil_moisture", "low"): ("watering", "Watering recommended"),
    ("soil_moisture", "normal"): ("watering", "No watering needed right now"),
    ("soil_moisture", "high"): ("watering", "Hold off watering: soil may be too wet"),
    ("soil_moisture", "critical_high"): ("watering", "Soil may be waterlogged"),
    ("temperature", "critical_low"): ("environment", "Temperature dangerously low"),
    ("temperature", "low"): ("environment", "Temperature below the plant's range"),
    ("temperature", "high"): ("environment", "Temperature above the plant's range"),
    ("temperature", "critical_high"): ("environment", "Temperature dangerously high"),
    ("humidity", "critical_low"): ("environment", "Air is very dry"),
    ("humidity", "low"): ("environment", "Humidity below the plant's range"),
    ("humidity", "high"): ("environment", "Humidity above the plant's range"),
    ("humidity", "critical_high"): ("environment", "Air is excessively humid"),
    ("light", "critical_low"): ("environment", "Light level very low"),
    ("light", "low"): ("environment", "Light level below the plant's range"),
    ("light", "high"): ("environment", "Light level above the plant's range"),
    ("light", "critical_high"): ("environment", "Light level excessively high"),
}


def rule_id(parameter, classification):
    return f"{parameter}_{classification}"


RULE_CATALOG = {
    rule_id(p, c): {"category": cat, "title": title, "parameter": p, "classification": c}
    for (p, c), (cat, title) in RULE_TITLES.items()
}


# --------------------------------------------------------------------------- thresholds
def thresholds(plant, settings):
    """Return the threshold set for every sensor, derived from the plant and global margins."""
    result = {}
    for parameter, meta in SENSORS.items():
        prefix = meta["prefix"]
        pref_min, pref_max = plant[f"{prefix}_min"], plant[f"{prefix}_max"]
        warn_low, warn_high = pref_min, pref_max
        if parameter == "soil_moisture":
            warn_low = plant["moisture_warning"]
        elif parameter == "temperature":
            warn_high = plant["temperature_warning"]
        margin = float(settings[f"critical_margin_{parameter}"])
        crit_low = warn_low - margin
        if warn_low > 0:
            crit_low = max(crit_low, warn_low / 2.0)
        crit_high = min(warn_high + margin, warn_high + (meta["max"] - warn_high) / 2.0)
        result[parameter] = {
            "pref_min": pref_min, "pref_max": pref_max,
            "warn_low": warn_low, "warn_high": warn_high,
            "crit_low": round(crit_low, 2), "crit_high": round(crit_high, 2),
            "unit": meta["unit"], "label": meta["label"],
        }
    return result


# --------------------------------------------------------------------------- classification
def classify(parameter, value, th):
    if value < th["crit_low"]:
        code = "critical_low"
    elif value < th["warn_low"]:
        code = "low"
    elif value > th["crit_high"]:
        code = "critical_high"
    elif value > th["warn_high"]:
        code = "high"
    else:
        code = "normal"
    direction = None if code == "normal" else ("low" if code.endswith("low") else "high")
    severity = None if code == "normal" else ("critical" if code.startswith("critical") else "warning")
    note = None
    if code == "normal":
        if value < th["pref_min"]:
            note = (f"Slightly below the preferred range ({th['pref_min']:g}–{th['pref_max']:g}) "
                    f"but not past the warning threshold ({th['warn_low']:g}).")
        elif value > th["pref_max"]:
            note = (f"Slightly above the preferred range ({th['pref_min']:g}–{th['pref_max']:g}) "
                    f"but not past the warning threshold ({th['warn_high']:g}).")
    return {
        "parameter": parameter, "value": value, "unit": SENSORS[parameter]["unit"],
        "classification": code, "label": LABELS[code], "direction": direction, "severity": severity,
        "in_preferred_range": th["pref_min"] <= value <= th["pref_max"], "note": note,
    }


def classify_all(values, ths):
    return {p: classify(p, float(values[p]), ths[p]) for p in PARAMS}


# --------------------------------------------------------------------------- overall health
def overall_health(plant, classes):
    """Worst-of rule: any critical reading is Critical; three or more out-of-range readings
    is also Critical; any single out-of-range reading is Needs Attention. One normal reading
    can never hide another parameter's problem."""
    off = [c for c in classes.values() if c["classification"] != "normal"]
    critical = [c for c in off if c["severity"] == "critical"]
    if critical or len(off) >= 3:
        status = "critical"
    elif off:
        status = "needs_attention"
    else:
        status = "healthy"

    factors = []
    for c in off:
        label = SENSORS[c["parameter"]]["label"]
        factors.append({
            "parameter": c["parameter"], "classification": c["classification"], "severity": c["severity"],
            "message": f"{label} is {c['label'].lower()} ({c['direction']}) at {c['value']:g}{SHORT_UNIT[c['parameter']]}.",
        })
    if status == "critical" and not critical:
        factors.append({"parameter": None, "classification": None, "severity": "critical",
                        "message": f"{len(off)} of 4 parameters are outside their thresholds at the same time."})
    for c in classes.values():
        if c["note"]:
            factors.append({"parameter": c["parameter"], "classification": "normal", "severity": None,
                            "message": f"{SENSORS[c['parameter']]['label']}: {c['note']}"})

    name = plant["name"]
    if status == "healthy":
        summary = f"All four simulated readings are inside the thresholds configured for {name}."
    elif status == "needs_attention":
        summary = f"{name} needs attention: " + "; ".join(f["message"] for f in factors if f["severity"])
    else:
        summary = f"{name} is in a critical condition: " + "; ".join(f["message"] for f in factors if f["severity"])
    label = {"healthy": "Healthy", "needs_attention": "Needs Attention", "critical": "Critical"}[status]
    return {"status": status, "label": label, "summary": summary, "factors": factors}


# --------------------------------------------------------------------------- recommendations
def _fmt(v):
    return f"{v:g}"


def _recommendation(plant, parameter, c, th):
    code, value = c["classification"], c["value"]
    category, title = RULE_TITLES[(parameter, code)]
    name, unit = plant["name"], SHORT_UNIT[parameter]
    pref = f"{_fmt(th['pref_min'])}–{_fmt(th['pref_max'])}{unit}"
    guidance = plant.get("watering_guidance") or ""
    actions, message, rule = [], "", ""

    if parameter == "soil_moisture":
        if code in ("low", "critical_low"):
            bound = th["warn_low"] if code == "low" else th["crit_low"]
            word = "below the warning threshold" if code == "low" else "below the critical threshold"
            message = f"Soil moisture is {_fmt(value)}%, {word} of {_fmt(bound)}% for {name}."
            rule = f"soil moisture < {'warning' if code == 'low' else 'critical'} threshold ({_fmt(bound)}%)"
            actions = ["Water gradually until the soil is evenly moist, then re-check the reading.",
                       "Do not water again until the next reading shows how the soil responded."]
            if guidance:
                actions.append(f"Plant guidance: {guidance}")
        elif code in ("high", "critical_high"):
            bound = th["warn_high"] if code == "high" else th["crit_high"]
            message = f"Soil moisture is {_fmt(value)}%, above the {'warning' if code == 'high' else 'critical'} threshold of {_fmt(bound)}% for {name}."
            rule = f"soil moisture > {'warning' if code == 'high' else 'critical'} threshold ({_fmt(bound)}%)"
            actions = ["Do not water until moisture falls back into the preferred range.",
                       "Check that the pot drains freely and empty any standing water from the saucer.",
                       "Improve airflow around the plant."]
        else:
            message = f"Soil moisture is {_fmt(value)}%, within the thresholds for {name}. No watering is advised from this reading."
            rule = f"warning threshold ({_fmt(th['warn_low'])}%) <= soil moisture <= {_fmt(th['warn_high'])}%"
            actions = ["Keep monitoring. Watering advice depends on soil moisture, not on elapsed time."]
    else:
        label = SENSORS[parameter]["label"]
        direction = c["direction"]
        side = "warn_low" if direction == "low" else "warn_high"
        if code.startswith("critical"):
            side = "crit_low" if direction == "low" else "crit_high"
        bound = th[side]
        kind = "critical" if code.startswith("critical") else "warning"
        comparator = "<" if direction == "low" else ">"
        message = (f"{label} is {_fmt(value)}{unit}, {'below' if direction == 'low' else 'above'} the "
                   f"{kind} threshold of {_fmt(bound)}{unit} for {name}.")
        rule = f"{label.lower()} {comparator} {kind} threshold ({_fmt(bound)}{unit})"
        actions = _environment_actions(parameter, direction)

    explanation = (f"Rule: {rule}. Reading: {_fmt(value)}{unit} (simulated). "
                   f"Preferred range for {name}: {pref}.")
    return {
        "rule_id": rule_id(parameter, code), "category": category, "parameter": parameter,
        "classification": code, "severity": c["severity"] or "info", "title": title, "message": message,
        "explanation": explanation, "actions": actions,
        "values": {"value": value, "unit": SENSORS[parameter]["unit"], "preferred_min": th["pref_min"],
                   "preferred_max": th["pref_max"], "warning_threshold": th["warn_low"] if c["direction"] != "high" else th["warn_high"],
                   "critical_threshold": th["crit_low"] if c["direction"] != "high" else th["crit_high"]},
        "advisory": True,
    }


def _environment_actions(parameter, direction):
    table = {
        ("temperature", "low"): ["Move the plant away from cold drafts, windows and air conditioning.",
                                 "Re-check the temperature after relocating."],
        ("temperature", "high"): ["Move the plant out of direct sun and away from heat sources.",
                                  "Improve ventilation or provide shade, then re-check."],
        ("humidity", "low"): ["Group plants together, use a pebble tray or run a humidifier nearby.",
                              "Keep the plant away from heaters and vents."],
        ("humidity", "high"): ["Increase air circulation and avoid crowding plants.",
                               "Watch for mould or leaf spots while humidity stays high."],
        ("light", "low"): ["Move the plant closer to a bright window or add a grow light.",
                           "Make changes gradually and re-check the light level."],
        ("light", "high"): ["Provide partial shade or move the plant back from the window.",
                            "Watch for scorched or bleached leaves."],
    }
    return table[(parameter, direction)]


def recommendations(plant, classes, ths):
    """Actionable recommendations (watering first) plus the soil-moisture 'no watering' note."""
    recs = []
    for parameter in PARAMS:
        c = classes[parameter]
        if c["classification"] != "normal" or parameter == "soil_moisture":
            recs.append(_recommendation(plant, parameter, c, ths[parameter]))
    order = {"critical": 0, "warning": 1, "info": 2}
    recs.sort(key=lambda r: (order[r["severity"]], r["category"] != "watering"))
    return recs


def actionable_rule_ids(recs):
    """Rule ids worth storing/summarising: everything except informational notes."""
    return [r["rule_id"] for r in recs if r["severity"] != "info"]


def analyze(plant, values, settings):
    ths = thresholds(plant, settings)
    classes = classify_all(values, ths)
    return {
        "thresholds": ths,
        "classifications": classes,
        "health": overall_health(plant, classes),
        "recommendations": recommendations(plant, classes, ths),
        "advisory_note": ADVISORY_NOTE,
    }
