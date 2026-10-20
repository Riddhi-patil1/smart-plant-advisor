"""Shared constants: sensor metadata, scenarios and data sources."""
from collections import OrderedDict

# Hard validity bounds for a single reading. "prefix" maps a sensor to the
# column names used in the plants table (e.g. moisture_min / moisture_max).
SENSORS = OrderedDict(
    [
        ("soil_moisture", {"label": "Soil Moisture", "unit": "%", "min": 0.0, "max": 100.0, "prefix": "moisture"}),
        ("temperature", {"label": "Temperature", "unit": "°C", "min": -10.0, "max": 60.0, "prefix": "temperature"}),
        ("humidity", {"label": "Relative Humidity", "unit": "%", "min": 0.0, "max": 100.0, "prefix": "humidity"}),
        # Normalised 0-100 level. It is NOT a lux measurement.
        ("light", {"label": "Light Intensity", "unit": "% (normalized)", "min": 0.0, "max": 100.0, "prefix": "light"}),
    ]
)
PARAMS = tuple(SENSORS)

SCENARIOS = OrderedDict(
    [
        ("normal", {"label": "Normal Conditions", "description": "Readings stay inside the plant's preferred ranges."}),
        ("dry_soil", {"label": "Dry Soil", "description": "Soil moisture falls gradually below the warning threshold."}),
        ("high_temperature", {"label": "High Temperature", "description": "Temperature rises gradually above the warning threshold."}),
        ("low_humidity", {"label": "Low Humidity", "description": "Relative humidity falls gradually below the preferred minimum."}),
        ("low_light", {"label": "Low Light", "description": "Normalized light level falls gradually below the preferred minimum."}),
        ("multiple", {"label": "Multiple Environmental Problems", "description": "Two or more selected problems are combined."}),
        ("custom", {"label": "Custom Conditions", "description": "Readings use the exact values you enter."}),
    ]
)

# Problems that can be combined in the "multiple" scenario.
PROBLEM_KEYS = ("dry_soil", "high_temperature", "low_humidity", "low_light")

# Data sources. Only the simulator is accepted by this version; "esp32" is
# reserved so real hardware can later enter through ingestion.ingest_reading().
SOURCES = {
    "simulator": {"label": "Simulator", "is_simulated": True},
    "esp32": {"label": "ESP32 (reserved, not implemented)", "is_simulated": False},
}

SIMULATION_STATES = ("stopped", "running", "paused")
RANGE_PRESETS = ("today", "7d", "30d")
