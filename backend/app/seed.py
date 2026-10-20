"""Example plant profiles. Thresholds are editable starting points, not biological facts.

No historical readings are generated: charts stay empty until the simulator runs.
"""
from . import settings as settings_store
from .db import transaction, utc_now
from .plants import EDITABLE, _insert, validate_plant

EXAMPLE_PLANTS = [
    {
        "name": "Money Plant", "species": "Epipremnum aureum",
        "description": "Trailing indoor vine; example starter profile.",
        "moisture_min": 40, "moisture_max": 60, "moisture_warning": 35,
        "temperature_min": 18, "temperature_max": 30, "temperature_warning": 32,
        "humidity_min": 40, "humidity_max": 70, "light_min": 40, "light_max": 70,
        "watering_guidance": "Water when the top layer of soil feels dry; let excess water drain away.",
        "care_notes": "Prefers bright, indirect light. Direct afternoon sun can scorch leaves.",
    },
    {
        "name": "Aloe Vera", "species": "Aloe vera",
        "description": "Succulent that stores water in its leaves; example starter profile.",
        "moisture_min": 15, "moisture_max": 35, "moisture_warning": 10,
        "temperature_min": 18, "temperature_max": 32, "temperature_warning": 35,
        "humidity_min": 20, "humidity_max": 50, "light_min": 60, "light_max": 90,
        "watering_guidance": "Water deeply but infrequently, only after the soil has dried out.",
        "care_notes": "Needs bright light and well-draining soil. Overwatering is the common problem.",
    },
    {
        "name": "Tulsi", "species": "Ocimum tenuiflorum",
        "description": "Holy basil; example starter profile.",
        "moisture_min": 50, "moisture_max": 70, "moisture_warning": 45,
        "temperature_min": 20, "temperature_max": 35, "temperature_warning": 38,
        "humidity_min": 40, "humidity_max": 70, "light_min": 65, "light_max": 95,
        "watering_guidance": "Keep soil lightly moist; water when the surface begins to dry.",
        "care_notes": "Likes several hours of strong light. Pinch flower buds to encourage leaf growth.",
    },
    {
        "name": "Snake Plant", "species": "Dracaena trifasciata",
        "description": "Hardy, drought-tolerant foliage plant; example starter profile.",
        "moisture_min": 10, "moisture_max": 30, "moisture_warning": 8,
        "temperature_min": 15, "temperature_max": 32, "temperature_warning": 35,
        "humidity_min": 30, "humidity_max": 60, "light_min": 30, "light_max": 80,
        "watering_guidance": "Let the soil dry thoroughly between waterings; reduce watering in cool seasons.",
        "care_notes": "Tolerates low light. Soggy soil is more harmful than dry soil.",
    },
]


def seed_example_plants(conn):
    """Insert the example plants once. Returns the number inserted (0 if already seeded)."""
    if settings_store.get_raw(conn, "seeded"):
        return 0
    now = utc_now()
    with transaction(conn):
        first_id = None
        for profile in EXAMPLE_PLANTS:
            clean = validate_plant(profile)
            plant_id = _insert(conn, {f: clean[f] for f in EDITABLE}, now)
            first_id = first_id or plant_id
        settings_store.set_raw(conn, "seeded", True)
        if settings_store.get_raw(conn, "active_plant_id") is None:
            settings_store.set_raw(conn, "active_plant_id", first_id)
    return len(EXAMPLE_PLANTS)
