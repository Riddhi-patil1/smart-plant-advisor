import os
import sqlite3
import unittest

from app import create_app
from app.db import connect, init_db
from helpers import AppCase


class DatabaseInitTests(AppCase):
    def test_tables_indexes_and_foreign_keys_exist(self):
        names = {r["name"] for r in self.conn.execute("SELECT name FROM sqlite_master")}
        for expected in ("plants", "sensor_readings", "alerts", "app_settings", "simulation_state",
                         "idx_readings_plant_time", "uq_alerts_active"):
            self.assertIn(expected, names)
        self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_init_is_idempotent_and_seed_runs_once(self):
        init_db(self.db_path)
        create_app(self.db_path)  # second start must not duplicate seed data
        count = self.conn.execute("SELECT COUNT(*) FROM plants").fetchone()[0]
        self.assertEqual(count, 4)

    def test_seeded_example_profiles_and_no_fake_history(self):
        names = {r["name"] for r in self.conn.execute("SELECT name FROM plants")}
        self.assertEqual(names, {"Money Plant", "Aloe Vera", "Tulsi", "Snake Plant"})
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0], 0)

    def test_deleting_all_plants_does_not_reseed_on_restart(self):
        for p in self.data("get", "/api/plants")["plants"]:
            self.data("delete", f"/api/plants/{p['id']}")
        self.sim.shutdown()
        create_app(self.db_path)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM plants").fetchone()[0], 0)

    def test_database_constraints_reject_bad_rows(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO sensor_readings (plant_id, recorded_at, soil_moisture, temperature, humidity, light, source,"
                " is_simulated, class_soil_moisture, class_temperature, class_humidity, class_light, health_status)"
                " VALUES (999, 'x', 50, 20, 50, 50, 'simulator', 1, 'normal','normal','normal','normal','healthy')")
        pid = self.plant_id("Tulsi")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO sensor_readings (plant_id, recorded_at, soil_moisture, temperature, humidity, light, source,"
                " is_simulated, class_soil_moisture, class_temperature, class_humidity, class_light, health_status)"
                " VALUES (?, 'x', 150, 20, 50, 50, 'simulator', 1, 'normal','normal','normal','normal','healthy')", (pid,))


class PlantCrudTests(AppCase):
    def test_create_read_update_delete(self):
        created = self.data("post", "/api/plants", 201, json=self.plant_payload())
        pid = created["id"]
        self.assertEqual(created["name"], "Test Fern")
        self.assertTrue(created["created_at"].endswith("Z"))
        self.assertEqual(self.data("get", f"/api/plants/{pid}")["species"], "Nephrolepis")

        updated = self.data("put", f"/api/plants/{pid}", json={"species": "Boston fern", "moisture_min": 45})
        self.assertEqual(updated["species"], "Boston fern")
        self.assertEqual(updated["moisture_min"], 45)
        self.assertEqual(updated["name"], "Test Fern")  # untouched fields are kept
        self.assertGreaterEqual(updated["updated_at"], created["updated_at"])

        result = self.data("delete", f"/api/plants/{pid}")
        self.assertEqual(result["deleted_id"], pid)
        self.call("get", f"/api/plants/{pid}", 404)

    def test_list_marks_active_plant(self):
        body = self.data("get", "/api/plants")
        self.assertEqual(len(body["plants"]), 4)
        self.assertIsNotNone(body["active_plant_id"])

    def test_field_level_errors(self):
        r = self.call("post", "/api/plants", 422, json=self.plant_payload(
            name="", moisture_min=80, moisture_max=40, image_url="ftp://x", temperature_min="abc",
            planting_date="2999-01-01", humidity_max=150))
        fields = r.get_json()["error"]["fields"]
        for key in ("name", "moisture_max", "image_url", "temperature_min", "planting_date", "humidity_max"):
            self.assertIn(key, fields)

    def test_warning_threshold_rules(self):
        r = self.call("post", "/api/plants", 422, json=self.plant_payload(moisture_warning=50))
        self.assertIn("moisture_warning", r.get_json()["error"]["fields"])
        r = self.call("post", "/api/plants", 422, json=self.plant_payload(temperature_warning=20))
        self.assertIn("temperature_warning", r.get_json()["error"]["fields"])

    def test_warning_thresholds_default_to_range_bounds(self):
        payload = self.plant_payload()
        del payload["moisture_warning"], payload["temperature_warning"]
        created = self.data("post", "/api/plants", 201, json=payload)
        self.assertEqual(created["moisture_warning"], created["moisture_min"])
        self.assertEqual(created["temperature_warning"], created["temperature_max"])

    def test_duplicate_name_conflict_is_case_insensitive(self):
        r = self.call("post", "/api/plants", 409, json=self.plant_payload(name="aloe vera"))
        self.assertIn("name", r.get_json()["error"]["fields"])

    def test_first_plant_becomes_active_when_none_exists(self):
        for p in self.data("get", "/api/plants")["plants"]:
            self.data("delete", f"/api/plants/{p['id']}")
        self.assertIsNone(self.data("get", "/api/plants")["active_plant_id"])
        created = self.data("post", "/api/plants", 201, json=self.plant_payload())
        self.assertEqual(self.data("get", "/api/plants/active")["active_plant_id"], created["id"])

    def test_sql_injection_text_is_stored_literally(self):
        evil = "x'); DROP TABLE plants;--"
        created = self.data("post", "/api/plants", 201, json=self.plant_payload(name=evil))
        self.assertEqual(created["name"], evil)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM plants").fetchone()[0], 5)


class ActivePlantAndDeleteTests(AppCase):
    def test_select_active_plant(self):
        pid = self.plant_id("Tulsi")
        self.data("put", "/api/plants/active", json={"plant_id": pid})
        self.assertEqual(self.data("get", "/api/plants/active")["plant"]["name"], "Tulsi")

    def test_select_unknown_or_invalid_active_plant(self):
        self.call("put", "/api/plants/active", 404, json={"plant_id": 9999})
        self.call("put", "/api/plants/active", 422, json={"plant_id": "abc"})
        self.call("put", "/api/plants/active", 422, json={})

    def test_delete_removes_only_that_plants_records_and_reassigns_active(self):
        a, b = self.plant_id("Aloe Vera"), self.plant_id("Tulsi")
        self.ingest("Aloe Vera", soil=5)   # creates a critical alert for Aloe
        self.ingest("Tulsi", soil=55)
        self.data("put", "/api/plants/active", json={"plant_id": a})
        result = self.data("delete", f"/api/plants/{a}")
        self.assertEqual(result["readings_removed"], 1)
        self.assertGreaterEqual(result["alerts_removed"], 1)
        self.assertNotEqual(result["active_plant_id"], a)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sensor_readings WHERE plant_id = ?", (a,)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM alerts WHERE plant_id = ?", (a,)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sensor_readings WHERE plant_id = ?", (b,)).fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
