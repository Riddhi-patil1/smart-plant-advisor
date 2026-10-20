"""Shared test fixtures. Tests use unittest so they run with `python -m unittest` or pytest."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app import settings as settings_store  # noqa: E402
from app.db import connect  # noqa: E402
from app.plants import validate_plant  # noqa: E402
from app.seed import EXAMPLE_PLANTS  # noqa: E402


def example_plant(name="Money Plant"):
    profile = next(p for p in EXAMPLE_PLANTS if p["name"] == name)
    return validate_plant(profile)


class AppCase(unittest.TestCase):
    """Fresh temporary database, Flask app and test client for every test."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="plant_test_")
        self.db_path = os.path.join(self.tmp, "test.db")
        self.app = create_app(self.db_path)
        self.client = self.app.test_client()
        self.sim = self.app.extensions["simulation"]
        self.conn = connect(self.db_path)

    def tearDown(self):
        self.sim.shutdown()
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- small helpers ------------------------------------------------
    def plant_id(self, name):
        return self.conn.execute("SELECT id FROM plants WHERE name = ?", (name,)).fetchone()["id"]

    def settings(self):
        return settings_store.get_all(self.conn)

    def call(self, method, url, expected=None, **kwargs):
        response = getattr(self.client, method)(url, **kwargs)
        if expected is not None:
            self.assertEqual(response.status_code, expected, response.get_data(as_text=True))
        return response

    def data(self, method, url, expected=200, **kwargs):
        return self.call(method, url, expected, **kwargs).get_json()["data"]

    def plant_payload(self, **overrides):
        payload = {
            "name": "Test Fern", "species": "Nephrolepis", "moisture_min": 40, "moisture_max": 70,
            "moisture_warning": 35, "temperature_min": 16, "temperature_max": 26, "temperature_warning": 29,
            "humidity_min": 50, "humidity_max": 80, "light_min": 30, "light_max": 60,
            "watering_guidance": "Keep moist.", "care_notes": "",
        }
        payload.update(overrides)
        return payload

    def ingest(self, plant_name, soil=None, temp=None, hum=None, light=None, recorded_at=None, scenario="custom"):
        """Ingest one reading. Unspecified sensors default to the middle of the plant's preferred range."""
        from app.ingestion import ingest_reading

        row = self.conn.execute("SELECT * FROM plants WHERE name = ?", (plant_name,)).fetchone()
        mid = lambda prefix: (row[f"{prefix}_min"] + row[f"{prefix}_max"]) / 2
        values = {
            "soil_moisture": mid("moisture") if soil is None else soil,
            "temperature": mid("temperature") if temp is None else temp,
            "humidity": mid("humidity") if hum is None else hum,
            "light": mid("light") if light is None else light,
        }
        return ingest_reading(self.conn, row["id"], values, scenario=scenario, recorded_at=recorded_at)
